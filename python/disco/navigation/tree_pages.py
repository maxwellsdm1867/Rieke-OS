"""Bounded, revision-checked metadata tree navigation; never reads waveforms.

Branch keys encode exact typed values through a digest, including a distinct
missing marker. They are navigation keys, never queries or scientific IDs.
"""
from __future__ import annotations

import re
import contextlib
import sys
import uuid
from itertools import chain
from collections.abc import Mapping

from disco.workbench.recipes import SPLIT_FIELDS, checksum, parse_splits
from disco.navigation.tree import (field_value_order, joint_definition, joint_value,
                            value_key, protocol_family)
from disco.navigation.predicates import validate as validate_predicate, matches
from workspace_service import validate_filters, WorkspaceService, _frozen_navigation_owner, publication_serial
from disco.decisions.explorer import ExplorerHistory
from disco.operation_timing import elapsed


TREE_SCOPE_BYTE_BUDGET = 64 * 1024 * 1024
TREE_SCOPE_CACHE_OVERHEAD = 16 * 1024  # Reserve for eight keys/entries and generation bookkeeping.
_STRUCTURAL_METHODS = {name: getattr(WorkspaceService, name) for name in (
    '_tree_rows', 'filtered_rows', 'query_result', '_filter_rows',
    '_epoch_page_identities', '_decorate', 'binding', 'source_scope', '_ready')}
_STRUCTURAL_HISTORY_METHODS = {name: getattr(ExplorerHistory, name)
                               for name in ('protocol_binding', 'protocol_binding_header', 'get')}


def _retain_scope_cache(owner, generation, cache, source_fingerprints):
    """One LRU/byte budget for source scopes and protocol-local projections.

    Three-part entries are source scopes; protocol entries also carry their
    cohort fingerprints. The project witness is retained only while a source
    entry needs it, and never consulted to validate a protocol cache hit.
    """
    while True:
        if not any(len(entry) == 3 for entry in cache.values()):
            source_fingerprints = None
        base_bytes = TREE_SCOPE_CACHE_OVERHEAD + (
            sys.getsizeof(source_fingerprints) if source_fingerprints is not None else 0)
        if (not cache or (len(cache) <= 8
                and sum(entry[1] for entry in cache.values()) <= 2_000_000
                and base_bytes + sum(entry[2] for entry in cache.values()) <= TREE_SCOPE_BYTE_BUDGET)):
            break
        cache.pop(next(iter(cache)))
    owner._tree_page_scope_cache = (generation, cache, source_fingerprints)


def _structural_contract(service, *, frozen_protocol=None):
    """Only borrow raw membership when its public policies are unchanged.

    Custom query/filter adapters may narrow or transform rows. Their public
    reader is authoritative, even if initially equivalent to the native reader.
    Header shortcuts additionally require the matching immutable recipe owner.
    """
    for name, expected in _STRUCTURAL_METHODS.items():
        actual = getattr(service, name, None)
        if getattr(actual, '__func__', actual) is not expected:
            return False
    provider = getattr(service, 'binding_provider', None)
    header = getattr(service, 'binding_header_provider', None)
    if frozen_protocol is not None and _frozen_navigation_owner(service, frozen_protocol) is not None:
        return True
    if provider is None:
        return header is None
    owner = getattr(provider, '__self__', None)
    return (type(owner) is ExplorerHistory
            and getattr(provider, '__func__', None) is _STRUCTURAL_HISTORY_METHODS['protocol_binding']
            and getattr(header, '__self__', None) is owner
            and getattr(header, '__func__', None) is _STRUCTURAL_HISTORY_METHODS['protocol_binding_header']
            and all(getattr(getattr(owner, name, None), '__func__', None) is method
                    for name, method in _STRUCTURAL_HISTORY_METHODS.items()))


class _NavigationValues(Mapping):
    """Borrow immutable basic rows rather than copy an epoch×field matrix.

    Only the three structural fields have an exact basic-row representation.
    All dynamic, joint and annotation groupings continue through the index.
    """
    columns = {'date': 'date', 'cell': 'cell_uuid', 'block': 'block_uuid'}
    # Charge this reservation to the scope admission budget up front, even
    # before lazy grouping fills it. Group buckets retain only borrowed rows.
    # Large scopes (1M members) need their root grouping cached or every page
    # regroups the scope; the reservation still counts toward scope admission.
    grouping_budget = 48 * 1024 * 1024

    def __init__(self, rows, fields, *, scope_size=None):
        self.rows, self.fields = rows, tuple(fields)
        self.grouping_budget = min(self.grouping_budget, max(16 * 1024,
            (len(rows) if scope_size is None else scope_size) * 40))
        self.group_cache, self.group_bytes, self.summary = {}, 0, None

    def __sizeof__(self):
        return object.__sizeof__(self) + self.grouping_budget

    def remember_groups(self, key, current, buckets, *, counts_only=False):
        # Compute summaries before admission, so neither later dictionary growth
        # nor newly allocated count/duration values can escape the reservation.
        # Rows and structural values are borrowed from service.rows. Container
        # references are charged conservatively even when another entry shares
        # them. The per-entry allowance covers the cache slot/value tuple/cost.
        for bucket in buckets:
            bucket['summary'] = {'count': len(bucket['rows'])} if counts_only else _summary(bucket['rows'])
        # ``current`` is borrowed: the scope's row list or a parent bucket's list,
        # each already charged where it is owned.
        cost = (256 + sys.getsizeof(key) + sys.getsizeof(key[1])
                + sys.getsizeof(buckets)
                + sum(sys.getsizeof(bucket) + sys.getsizeof(bucket['rows'])
                      + sys.getsizeof(bucket['summary'])
                      + sum(sys.getsizeof(value) for value in bucket['summary'].values())
                      for bucket in buckets))
        if cost > self.grouping_budget:
            return
        while self.group_cache and (len(self.group_cache) >= 128
                                   or self.group_bytes + cost > self.grouping_budget):
            _, _, previous = self.group_cache.pop(next(iter(self.group_cache)))
            self.group_bytes -= previous
        self.group_cache[key] = (current, buckets, cost)
        self.group_bytes += cost

    def __getitem__(self, identity):
        row = self.rows[identity]
        return {field: row.get(self.columns[field]) for field in self.fields}

    def __iter__(self):
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)


def _structural_scope(body):
    """Conservative fast-path eligibility; unsupported scopes retain the oracle."""
    splits = body.get('splits', 'date,cell,block')
    if not isinstance(splits, str):
        return False
    fields = [field.strip() for field in splits.split(',') if field.strip()]
    return (bool(fields) and set(fields) <= {'date', 'cell', 'block'}
            and body.get('predicate', {'all': []}) == {'all': []}
            and not any(field in (body.get('filters') or {})
                        for field in ('tag', 'tagged', 'tag_predicate', 'metadata_predicate')))


def _retained_scope_bytes(result, base_rows, limit):
    """Conservative incremental Python-object estimate, not an RSS ceiling.

    Base rows remain owned by the service independently of this cache. Exclude
    only those exact objects (and exact shared values in decorated row copies),
    while counting the copies, curation state, projections and containers.
    Equal-but-separately-decoded values are distinct allocations and count.
    Walk lazily by identity and stop as soon as the admission budget is exceeded.
    """
    seen = set()
    for row in result[0]:
        original = base_rows.get(row['epoch_uuid'])
        if row is original:
            seen.add(id(row))
        elif original is not None:
            for key, value in row.items():
                if key in original and value is original[key]:
                    seen.add(id(value))
    total = 0
    pending = [iter((result,))]
    while pending:
        try:
            value = next(pending[-1])
        except StopIteration:
            pending.pop()
            continue
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        total += sys.getsizeof(value)
        if total > limit:
            return total
        if isinstance(value, dict):
            pending.append(chain(value.keys(), value.values()))
        elif isinstance(value, (list, tuple, set, frozenset)):
            pending.append(iter(value))
    return total


class StaleTreePage(ValueError):
    pass


def validate_tree_path(path, depth=None):
    if (not isinstance(path, list) or len(path) > 8
            or any(not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key) for key in path)):
        raise ValueError('Tree path must contain at most eight opaque branch keys')
    if depth is not None and len(path) > depth:
        raise ValueError('Tree path exceeds the selected grouping depth')
    return tuple(path)


class TreePath:
    """Exact structural matching on one projected row, without scope resolution.

    The caller supplies validated definitions and already eligible/scoped values.
    This helper never evaluates protocol membership, filters or source authority;
    navigation and a future streaming capture must retain those separate fences.
    """
    def __init__(self, order, definitions, path=None):
        self.order=tuple(order)
        self.path=validate_tree_path([] if path is None else path,len(self.order))
        self.components={}
        fields=set()
        for field in self.order:
            if field not in definitions:
                raise ValueError('Tree path contains an unknown recorded field')
            parts=definitions[field].get('components')
            if parts and (not isinstance(parts,list) or any(part not in definitions for part in parts)):
                raise ValueError('Joint grouping contains an unknown recorded field')
            self.components[field]=tuple(parts) if parts else ()
            fields.update(parts or [field])
        self.fields=frozenset(fields)

    def datum(self, current, field):
        parts=self.components[field]
        if parts:
            return True,joint_value(current,parts)
        value=current.get(field)
        # Match build_tree: scalar built-in nulls are unrecorded; dynamic nulls are values.
        present=field in current and (field not in SPLIT_FIELDS or value is not None)
        return present,value

    def key(self, current, field):
        present,value=self.datum(current,field)
        return checksum({'field':field,'present':present,**({'value':value} if present else {})})

    def matches(self, current):
        return all(self.key(current,field)==key for field,key in zip(self.order,self.path))


def _uuid(value):
    if not isinstance(value, str):
        raise ValueError('Expected an epoch or protocol UUID')
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError('Expected an epoch or protocol UUID') from error


def _summary(rows):
    durations = [row.get('duration_seconds') for row in rows]
    return {'count': len(rows), 'cells': len({row['cell_uuid'] for row in rows}),
            'duration_seconds': sum(durations) if all(value is not None for value in durations) else None}


def _epoch(row):
    return {key: row.get(key) for key in ('epoch_uuid', 'start_time', 'cell_uuid',
            'cell_label', 'date', 'block_uuid', 'epoch_number')} | {
            'label': f"Epoch {row['epoch_number']} · {row['start_time'][11:]}"}


def _chronology(row):
    return row['date'], row['start_time'][11:], row['epoch_uuid']


def predicate_publication(service, filters=None):
    """Membership-free identity of a project-scope predicate tree, or None.

    Available only when the published read model is frozen (publication serial),
    the canonical native index and membership policies are in place, and no
    shared-tag filter contributes membership. Equal identities, predicates,
    filters, splits, source scope and annotation evidence then prove equal
    membership; otherwise callers hash the exact members.
    """
    from disco.metadata.disk_index import DiskMetadataIndex
    serial = publication_serial(service)
    index = getattr(service, 'disk_index', None)
    if serial is None or type(index) is not DiskMetadataIndex or not _structural_contract(service):
        return None
    if any(key in (filters or {}) for key in ('tag', 'tagged', 'tag_predicate')):
        return None
    typed = getattr(service, 'typed_index', None)
    return {'serial': serial, 'index': index.generation,
            'typed': getattr(typed, 'generation_token', None) if typed is not None else None}


def selection_revision(service, protocol, predicate, filters, order, rows, binding=None, annotation_scope=None):
    """Shared explorer-summary/page identity, independent of page offset/path.

    A project-scope tree over a frozen publication is identified by that
    publication instead of hashing every member (`rows` is then unused).
    """
    if protocol is None:
        identity = predicate_publication(service, filters)
        if identity is not None:
            return checksum({'version':2, 'project_uuid':service.project['project_uuid'], 'protocol_uuid':None,
                'predicate':predicate, 'filters':filters or {}, 'splits':order,
                **({'annotation_scope_revision':annotation_scope['revision']} if annotation_scope else {}),
                'source_scope_revision':service.source_scope()['revision'], 'publication':identity})
    if protocol is not None and binding is None:
        binding = service.binding(protocol)
    return checksum({'version':1, 'project_uuid':service.project['project_uuid'],
        'protocol_uuid':protocol, 'binding':binding and {'version':binding['version'],
            'revision_uuid':binding.get('revision_uuid')},
        'predicate':predicate, 'filters':filters or {}, 'splits':order,
        **({'annotation_scope_revision':annotation_scope['revision']} if annotation_scope else {}),
        'source_scope_revision':service.source_scope()['revision'] if protocol is None else None,
        'members':[(row['epoch_uuid'],service._fingerprints[row['epoch_uuid']])
                   for row in sorted(rows,key=lambda row:row['epoch_uuid'])]})


def _group_buckets(current, depth, order, structural_path, values, *, counts_only):
    field = order[depth]
    cache_key = (field, id(current), counts_only)
    if isinstance(values, _NavigationValues):
        if cache_key in values.group_cache:
            return values.group_cache[cache_key][1]
        # Full-summary groupings carry the same buckets and rows; a counts-only
        # reader (branch selection) reuses them instead of regrouping the scope.
        if counts_only and (field, id(current), False) in values.group_cache:
            return values.group_cache[(field, id(current), False)][1]
    buckets = {}
    for row in current:
        present, value = structural_path.datum(values[row['epoch_uuid']], field)
        canonical = value_key(value) if present else None
        bucket = buckets.setdefault((present, canonical), {'row':row, 'value':value,
            'missing':not present, 'rows':[]})
        bucket['rows'].append(row)
    def sorting(key):
        bucket = buckets[key]
        if field == 'block' and not bucket['missing']:
            row = bucket['row']; stamp = row.get('block_start_time')
            # Same source chronology as the full-tree renderer.
            from workspace_service import _date
            return (0, (_date(stamp) + stamp[11:]) if stamp else '', str(bucket['value']))
        return (1,) if bucket['missing'] else (0, field_value_order(field,bucket['value'],canonical=key[1]))
    # Reuse grouping keys; do not encode every distinct value again.
    result = sorted(buckets, key=sorting)
    for index, key in enumerate(result):
        result[index] = buckets[key]
    if isinstance(values, _NavigationValues):
        values.remember_groups(cache_key, current, result, counts_only=counts_only)
    return result


class TreePages:
    """Service adapter with no retained full trees or per-branch membership copies."""
    def __init__(self, service):
        self.service = service

    def _scope(self, body):
        """Reuse navigation projections only for a checked immutable index.

        Source eligibility and frozen protocol binding are part of every key.
        Keeping this on the service also shares it with matching-epoch reads.
        A frozen publication (``publication_serial``) proves rows, fingerprints
        and protocol membership by its serial, so hits compare no dictionaries.
        Annotation-dependent scopes (tag filters, annotation predicates) are
        cached only for a frozen publication under the verified annotation
        generation tokens of their context, checked unchanged across the build.
        """
        service = self.service
        service._ready()
        from disco.metadata.disk_index import DiskMetadataIndex
        from disco.navigation.tag_predicates import referenced_fields
        index = getattr(service, 'disk_index', None)
        filters = validate_filters(body.get('filters'))
        if not isinstance(index, DiskMetadataIndex):
            return self._build_scope(body)
        serial = publication_serial(service)
        annotation_token = None
        if (any(field in filters for field in ('tag', 'tagged', 'tag_predicate', 'metadata_predicate'))
                or referenced_fields(body.get('predicate', {'all': []}))):
            if serial is None:
                return self._build_scope(body)
            from disco.metadata.explore_queries import generation as annotation_generation, StaleQuery
            context = {'protocol_uuid': _uuid(body['protocol_uuid']) if body.get('protocol_uuid') else None,
                       'filters': filters, 'predicate': body.get('predicate', {'all': []})}
            try:
                annotation_token = checksum(annotation_generation(service, context))
            except StaleQuery:
                return self._build_scope(body)
            annotation_context = context
        index._check()  # A cache hit must still refuse changed/corrupt index bytes.
        structural = _structural_scope(body)
        if not _structural_contract(service, frozen_protocol=body.get('protocol_uuid')):
            # An unproven policy cannot reuse a native membership/cache key.
            return self._build_scope(body)
        protocol = body.get('protocol_uuid')
        if protocol is not None:
            protocol = _uuid(protocol)
            if 'predicate' in body:
                raise ValueError('Protocol tree membership cannot be replaced by a source predicate')
        header_provider = getattr(service, 'binding_header_provider', None)
        cache_owner = _frozen_navigation_owner(service, protocol) or service
        binding = (header_provider(protocol) if header_provider else service.binding(protocol)) if protocol else None
        # Provider-only/unbound protocol fixtures may mutate their membership in
        # place without replacing service.protocols. Frozen binding headers are
        # immutable; other scopes compare their exact UUID sequence on each hit.
        membership = (tuple(member['uuid'] for member in service.protocols[protocol]['result']['epochs'])
                      if protocol and binding is None and serial is None else None)
        # A frozen publication's serial is a complete witness (never reused);
        # unfrozen read models keep identities plus content comparisons below.
        generation = (('publication', serial, index.generation) if serial is not None else
                      (id(index), index.generation, id(service.rows), id(service._fingerprints), id(service.protocols)))
        cached = getattr(cache_owner, '_tree_page_scope_cache', None)
        if cached is None or cached[0] != generation:
            cached = cache_owner._tree_page_scope_cache = (generation, {}, None)
        cache, source_fingerprints = cached[1:]
        if serial is None and protocol is None and (source_fingerprints is None or source_fingerprints != service._fingerprints):
            # The published fingerprint dictionary is also used by reconciliation
            # and test adapters. Detect in-place edits, not only refresh swaps.
            # Invalidate source entries only; protocols still check their complete
            # own cohorts. Merely switching navigation modes invalidates neither.
            for old_key, entry in list(cache.items()):
                if len(entry) == 3:
                    del cache[old_key]
            _retain_scope_cache(cache_owner, generation, cache, None)
            if TREE_SCOPE_CACHE_OVERHEAD + sys.getsizeof(service._fingerprints) >= TREE_SCOPE_BYTE_BUDGET:
                return self._build_scope(body)
            # Publish this witness only if a source projection is admitted below.
            source_fingerprints = dict(service._fingerprints)
        key = (checksum({'protocol': protocol, 'binding': binding and {
            'version': binding['version'], 'revision_uuid': binding.get('revision_uuid'),
            'read_scope_revision': binding.get('read_scope_revision')},
            'source_scope': service.source_scope()['revision'] if protocol is None else None,
            'predicate': body.get('predicate'), 'filters': filters,
            'splits': body.get('splits', 'date,cell,block'),
            'annotations': annotation_token}), membership)
        if key in cache:
            entry = cache.pop(key)
            if protocol is None or serial is not None or all(service._fingerprints.get(identity) == fingerprint
                    for identity, fingerprint in entry[3].items()):
                cache[key] = entry
                return entry[0]
        fingerprints = None
        if protocol is not None and serial is None:
            # Watch the complete cohort, including members hidden by filters:
            # their metadata can change whether they belong in this projection.
            # A native frozen header identifies an immutable recipe; only a cold
            # entry needs its membership. Warm pages read the header once above.
            full_binding = (service.binding(protocol) if binding is not None
                            and 'recipe' not in binding else binding)
            members = (full_binding['recipe']['epochs'] if full_binding else
                       service.protocols[protocol]['result']['epochs'])
            fingerprints = {member['uuid']: service._fingerprints[member['uuid']] for member in members}
        result = self._build_scope(body)
        if annotation_token is not None:
            from disco.metadata.explore_queries import generation as annotation_generation, StaleQuery
            try:
                unchanged = checksum(annotation_generation(service, annotation_context)) == annotation_token
            except StaleQuery:
                unchanged = False
            if not unchanged or publication_serial(service) != serial:
                return result  # Annotations changed during the build: serve, never retain.
        rows, _, values, _, _, _ = result
        # Bound retained row references plus projected values across all scopes.
        # An oversize projection may serve this request but is never retained.
        weight = len(rows) if isinstance(values, _NavigationValues) else len(rows) + sum(len(value) for value in values.values())
        if weight <= 2_000_000:
            # A protocol may evict older source entries and their witness to fit;
            # a source entry must fit together with its full freshness witness.
            base_bytes = TREE_SCOPE_CACHE_OVERHEAD + (
                sys.getsizeof(source_fingerprints) if protocol is None else 0)
            byte_limit = TREE_SCOPE_BYTE_BUDGET - base_bytes
            retained_bytes = _retained_scope_bytes(result, service.rows, byte_limit)
            if fingerprints is not None:
                # Keys/hashes are immutable objects borrowed from this service
                # generation, like basic rows. Charge the owned lookup table.
                retained_bytes += sys.getsizeof(fingerprints)
            # UUID strings are borrowed from service.protocols, but the exact
            # unbound membership tuple in this cache key is a new container.
            if membership is not None:
                retained_bytes += sys.getsizeof(membership)
            if retained_bytes > byte_limit:
                return result
            cache[key] = ((result, weight, retained_bytes, fingerprints) if protocol else
                          (result, weight, retained_bytes))
            _retain_scope_cache(cache_owner, generation, cache, source_fingerprints)
        return result

    def _build_scope(self, body):
        service = self.service
        service._ready()
        protocol = body.get('protocol_uuid')
        if protocol is not None:
            protocol = _uuid(protocol)
            if 'predicate' in body:
                raise ValueError('Protocol tree membership cannot be replaced by a source predicate')
        filters = service.validate_metadata_filters(body.get('filters'), protocol)
        scoped_generation = None
        if 'metadata_predicate' in filters:
            from disco.metadata.explore_queries import generation
            scoped_context = {'protocol_uuid': protocol, 'filters': filters}
            scoped_generation = generation(service, scoped_context)
        index = getattr(service, 'disk_index', None)
        from disco.metadata.disk_index import DiskMetadataIndex
        canonical_index = isinstance(index, DiskMetadataIndex) and _structural_contract(service, frozen_protocol=protocol)
        structural = canonical_index and _structural_scope(body)
        # Recorded/joint splits still project their exact typed values below.
        # Only proven native or owned frozen membership can borrow basic rows.
        # Custom readers and live annotation/metadata filters keep their policy.
        raw_membership = canonical_index and not any(field in filters for field in (
            'tag', 'tagged', 'tag_predicate', 'metadata_predicate'))
        if raw_membership and protocol:
            # Tree summaries have no curation fields. Use the same checked raw
            # membership as the bounded epoch endpoint; only leaf annotations
            # are subsequently fetched for the displayed page.
            identities, _ = service._epoch_page_identities(protocol, filters)
            rows = [service.rows[identity] for identity in identities]
        else:
            rows = service._navigation_rows(protocol, filters)
        shared_definitions = None
        if index is not None:
            # Registered definitions remain valid for empty or excluded scopes;
            # paged navigation needs no repeated per-field scope summaries.
            # The generation's shared read-only definitions view avoids a
            # per-request catalog deep copy; other adapters keep catalog().
            reader = getattr(index, 'catalog_definitions', None)
            shared_definitions = reader() if reader is not None else None
            catalog = {'fields': list(shared_definitions.values())} if shared_definitions is not None else index.catalog()
            values = None
        else:
            catalog, values = service._tree_fields(protocol, filters)
        predicate = None
        annotation_scope = {'revision': checksum(scoped_generation)} if scoped_generation else None
        if protocol is None:
            requested_predicate = body.get('predicate', {'all': []})
            if requested_predicate == {'all': []}:
                predicate = {'all': []}
            else:
                predicate, identities, annotation_scope = service.match_predicate(requested_predicate, ids=[row['epoch_uuid'] for row in rows])
                allowed = set(identities)
                rows = [row for row in rows if row['epoch_uuid'] in allowed]
        catalog = {**catalog, 'protocol_family':protocol_family(rows)}
        definitions = (dict(shared_definitions) if shared_definitions is not None
                       else {field['id']: field for field in catalog['fields']})
        splits = body.get('splits', 'date,cell,block')
        order = parse_splits(splits, definitions)
        for field in order:
            if field not in definitions:
                definitions[field] = joint_definition(field, definitions)
        if structural:
            values = _NavigationValues(service.rows, order, scope_size=len(rows))
        elif index is not None:
            # Project every split column once per scope, so one cached scope
            # serves every depth, anchor and branch selection of this tree.
            requested = order
            columns = set()
            for field in requested:
                columns.update(definitions[field].get('components') or [field])
            # One streaming read, not one SQL lookup per epoch. Retain only the
            # current navigation columns, never the full epoch×field matrix.
            values = dict(index.values(ids=[row['epoch_uuid'] for row in rows], fields=sorted(columns)).items()) if columns else {}
        header_provider = getattr(service, 'binding_header_provider', None)
        binding = (header_provider(protocol) if structural and header_provider else service.binding(protocol)) if protocol else None
        if scoped_generation is not None and generation(service, scoped_context) != scoped_generation:
            raise StaleTreePage('Scoped annotations changed while loading this tree; reload the root')
        revision = selection_revision(service, protocol, predicate, filters, order, rows, binding, annotation_scope=annotation_scope)
        return rows, catalog, values, definitions, order, revision

    def page(self, body):
        with elapsed("disco.navigation.tree_pages", "page"):
            return self._page(body, self._scope)

    def _page(self, body, scope_reader):
        if not isinstance(body, dict) or set(body) - {'protocol_uuid','predicate','filters','splits','path','offset','limit','revision','anchor_uuid','counts_only'}:
            raise ValueError('Malformed tree page request or unsupported fields')
        counts_only = body.get('counts_only', False)
        if type(counts_only) is not bool:
            raise ValueError('counts_only must be a boolean')
        limit, offset = body.get('limit', 80), body.get('offset', 0)
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 10_000_000:
            raise ValueError('Tree pages require limit 1–100 and a nonnegative bounded offset')
        path = body.get('path', [])
        validate_tree_path(path)
        expected = body.get('revision')
        if expected is not None and (not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected)):
            raise ValueError('Malformed tree revision')
        if (path or offset) and expected is None:
            raise ValueError('A tree revision is required for continuation pages')
        anchor = _uuid(body['anchor_uuid']) if 'anchor_uuid' in body else None
        if anchor and (path or offset):
            raise ValueError('An epoch locator cannot also specify a path or offset')
        prepared = getattr(self.service, '_prepared_navigation', None)
        if prepared is not None and self._canonical_reader():
            entry = prepared.read(body)
            if entry is not None:
                if expected is not None and expected != entry.revision:
                    raise StaleTreePage('Tree metadata or membership changed; reload the root before continuing')
                result = self._prepared_page(body, entry)
                prepared.verify(entry)
                return result
        rows, catalog, values, definitions, order, revision = scope_reader(body)
        if expected is not None and expected != revision:
            raise StaleTreePage('Tree metadata or membership changed; reload the root before continuing')
        structural_path = TreePath(order,definitions,path)
        if counts_only:
            root_summary = {'count': len(rows)}
        elif isinstance(values, _NavigationValues):
            if values.summary is None:
                values.summary = _summary(rows)
            root_summary = values.summary
        else:
            root_summary = _summary(rows)
        total_epochs = len(rows)
        levels = [{'field':field,'label':definitions[field]['label'],
                   **({'components':definitions[field]['components']} if definitions[field].get('components') else {})}
                  for field in order]

        def key_for(row, field):
            return structural_path.key(values[row['epoch_uuid']],field)

        def groups(current, depth):
            return _group_buckets(current, depth, order, structural_path, values, counts_only=counts_only)

        def branch_records(buckets, depth, parent_path):
            if not buckets:
                return []
            field = order[depth]
            representatives = [bucket['row'] for bucket in buckets]
            # Reuse the established human labels, but render only one epoch per
            # requested branch, never all members or all descendant levels.
            scoped_values = {row['epoch_uuid']: dict(values[row['epoch_uuid']]) for row in representatives}
            if definitions[field].get('components'):
                for current in scoped_values.values():
                    current[field] = joint_value(current,definitions[field]['components'])
            rendered = self.service._render_tree(representatives,
                {**catalog, 'fields':list(definitions.values())}, scoped_values, field)
            labels = {checksum({'field':field,'present':not child.get('missing',False),
                      **({'value':child['value']} if not child.get('missing',False) else {})}):child
                      for child in rendered.get('children',[])}
            result = []
            for bucket in buckets:
                key = key_for(bucket['row'],field)
                child = labels[key]
                if counts_only:
                    summary = {'count': len(bucket['rows'])}
                elif isinstance(values, _NavigationValues):
                    if 'summary' not in bucket:
                        bucket['summary'] = _summary(bucket['rows'])
                    summary = bucket['summary']
                else:
                    summary = _summary(bucket['rows'])
                result.append({'key':key,'label':child['label'],'value':bucket['value'],
                    'missing':bucket['missing'], 'path':[*parent_path,key],
                    'has_children':depth + 1 < len(order), **summary,
                    **({'shared_tag_coverage': self.service.tree_annotation_coverage(bucket['rows'])}
                       if not counts_only and callable(getattr(self.service, 'tree_annotation_coverage', None)) else {}),
                    **{name:child[name] for name in ('components','has_missing_components','start_time','cell_type') if name in child}})
            return result

        ancestors = []
        if anchor:
            candidate = next((row for row in rows if row['epoch_uuid'] == anchor), None)
            if candidate is None:
                raise KeyError('Epoch is outside this tree selection')
            path = [key_for(candidate,field) for field in order]
        selected = rows
        for depth, key in enumerate(path):
            buckets = groups(selected,depth)
            found = next(((index,bucket) for index,bucket in enumerate(buckets) if key_for(bucket['row'],order[depth]) == key),None)
            current = found[1] if found else None
            if current is None:
                raise KeyError('Tree branch is outside this selection')
            ancestors.extend([{**item,'parent_offset':found[0] // limit * limit} for item in branch_records([current],depth,path[:depth])])
            selected = current['rows']
        depth = len(path)
        if counts_only:
            selected_summary = {'count': len(selected)}
        elif not isinstance(values, _NavigationValues):
            selected_summary = _summary(selected)
        elif ancestors:
            selected_summary = {key: ancestors[-1][key]
                                for key in ('count', 'cells', 'duration_seconds')}
        else:
            selected_summary = root_summary
        payload = {'revision':revision,'split_order':order,'levels':levels,'total_epochs':total_epochs,
            **root_summary,
            'path':path,'depth':depth,'offset':offset,'limit':limit,'branches':[],'epochs':[],
            'selection':selected_summary, 'ancestors':ancestors,
            'source_scope_revision':self.service.source_scope()['revision'] if body.get('protocol_uuid') is None else None}
        if depth < len(order):
            buckets = groups(selected,depth)
            payload.update(kind='branches',total=len(buckets),
                branches=branch_records(buckets[offset:offset+limit],depth,path))
        else:
            selected = sorted(selected,key=_chronology)
            if anchor:
                index = next(index for index,row in enumerate(selected) if row['epoch_uuid']==anchor)
                offset = (index // limit) * limit
                payload['offset'] = offset
                payload['anchor'] = {'epoch_uuid':anchor,'path':path,'index':index,'offset':offset}
            shown=selected[offset:offset+limit]
            payload.update(kind='epochs',total=len(selected),epochs=[_epoch(row) for row in shown])
            shared=getattr(self.service,'shared_annotations',None)
            if shared:
                annotations=shared.for_epochs(shown)
                for row in payload['epochs']:row['annotations']=annotations[row['epoch_uuid']]
        payload['has_more'] = offset + limit < payload['total']
        return payload


    def _prepared_page(self, body, entry):
        """Render only the requested prepared branches using the existing labels."""
        order, definitions = entry.order, entry.definitions
        TreePath(order, definitions, body.get('path', []))
        payload = entry.tree.page(path=body.get('path', []), offset=body.get('offset', 0),
            limit=body.get('limit', 80), anchor_uuid=body.get('anchor_uuid'),
            counts_only=body.get('counts_only', False))
        def rendered(branches, depth):
            if not branches:
                return []
            field = order[depth]
            representatives = [branch['representative'] for branch in branches]
            values = {branch['representative']['epoch_uuid']: dict(branch['values']) for branch in branches}
            if definitions[field].get('components'):
                for value in values.values():
                    value[field] = joint_value(value, definitions[field]['components'])
            tree = self.service._render_tree(representatives,
                {**entry.catalog, 'fields': list(definitions.values())}, values, field)
            labels = {checksum({'field': field, 'present': not child.get('missing', False),
                **({'value': child['value']} if not child.get('missing', False) else {})}): child
                for child in tree.get('children', [])}
            result = []
            for branch in branches:
                child = labels[branch['key']]
                result.append({key: value for key, value in branch.items() if key not in ('representative', 'values', 'parent_index')} |
                    {'label': child['label']} | {name: child[name] for name in
                        ('components', 'has_missing_components', 'start_time', 'cell_type') if name in child})
            return result
        payload['branches'] = rendered(payload['branches'], payload['depth']) if payload['branches'] else []
        payload['ancestors'] = [rendered([branch], depth)[0] for depth, branch in enumerate(payload['ancestors'])]
        if entry.duration_error and not body.get('counts_only', False):
            for summary in (payload, payload['selection'], *payload['branches'], *payload['ancestors']):
                if summary.get('duration_status') == 'pending':
                    summary.update(duration_status='failed', duration_error=entry.duration_error)
        shown = payload['epochs']
        payload['epochs'] = [_epoch(row) for row in shown]
        shared = getattr(self.service, 'shared_annotations', None)
        if shown and shared:
            annotations = shared.for_epochs(shown)
            for row in payload['epochs']:
                row['annotations'] = annotations[row['epoch_uuid']]
        payload.update(revision=entry.revision, split_order=order,
            levels=[{'field': field, 'label': definitions[field]['label'],
                **({'components': definitions[field]['components']} if definitions[field].get('components') else {})}
                for field in order],
            source_scope_revision=entry.witness['source_scope'] if body.get('protocol_uuid') is None else None)
        return payload

    def _canonical_reader(self):
        return all(getattr(getattr(self, name), '__func__', None) is original
                   for name, original in _BATCH_READER_METHODS.items())

    def column_pages(self, body, ancestor_offsets=None):
        """One response-local projection; the caller retains closing authority.

        The target projection includes every ancestor prefix. Custom readers keep
        independent page calls; no cross-request cache or permission is created.
        """
        with elapsed("disco.navigation.tree_pages", "column_pages"):
            offsets = [] if ancestor_offsets is None else ancestor_offsets
            if (not isinstance(offsets, list) or len(offsets) > 8
                    or any(value is not None and (type(value) is not int or not 0 <= value <= 10_000_000)
                           for value in offsets)):
                raise ValueError('Malformed tree column offsets')
            snapshot = None
            def resolve(request):
                nonlocal snapshot
                if snapshot is None:
                    snapshot = self._scope(request)
                return snapshot
            read = (lambda request: self._page(request, resolve)) if self._canonical_reader() else self.page
            target = read(body)
            parents = []
            for depth in range(len(target['path'])):
                recorded = target['ancestors'][depth]['parent_offset']
                offset = (recorded if body.get('anchor_uuid') or depth >= len(offsets) or offsets[depth] is None
                          else offsets[depth])
                request = {key: value for key, value in body.items() if key != 'anchor_uuid'}
                request.update(path=target['path'][:depth], offset=offset, revision=target['revision'])
                parents.append(read(request))
            return target, parents

    def selection(self, body, expected_count, *, max_count=1000):
        """Exact bounded DFS membership without rendering descendant pages."""
        with elapsed("disco.navigation.tree_pages", "selection"):
            if (not isinstance(body, dict) or set(body) - {'protocol_uuid', 'predicate', 'filters', 'splits', 'path', 'revision'}
                    or type(expected_count) is not int or not 1 <= expected_count <= max_count):
                raise ValueError('Tree selection requires 1–1,000 epochs and a bounded scope')
            path = body.get('path', [])
            validate_tree_path(path)
            expected = body.get('revision')
            if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
                raise ValueError('Tree selection requires a current revision')
            if not self._canonical_reader():
                return self._selection_pages(body, expected_count)
            prepared = getattr(self.service, '_prepared_navigation', None)
            entry = prepared.read(body) if prepared is not None else None
            if entry is not None:
                if entry.revision != expected:
                    raise StaleTreePage('Tree selection revision changed')
                ids = entry.tree.select(path=path, max_count=max_count)
                if len(ids) != expected_count:
                    raise StaleTreePage('Tree selection count changed; refresh this branch')
                prepared.verify(entry)
                return dict(revision=entry.revision, path=path, count=expected_count, epoch_uuids=list(ids))
            # Every split column is projected once per scope, so the cached
            # navigation scope (shared with pages) serves branch selection.
            rows, _, values, definitions, order, revision = self._scope(body)
            if revision != expected:
                raise StaleTreePage('Tree selection revision changed')
            structural_path = TreePath(order, definitions, path)
            selected = rows
            for depth, key in enumerate(path):
                buckets = _group_buckets(selected, depth, order, structural_path, values, counts_only=True)
                bucket = next((bucket for bucket in buckets
                    if structural_path.key(values[bucket['row']['epoch_uuid']], order[depth]) == key), None)
                if bucket is None:
                    raise KeyError('Tree branch is outside this selection')
                selected = bucket['rows']
            if len(selected) != expected_count:
                raise StaleTreePage('Tree selection count changed; refresh this branch')
            ids = []
            def visit(current, depth):
                if depth == len(order):
                    ids.extend(row['epoch_uuid'] for row in sorted(current, key=_chronology))
                else:
                    for bucket in _group_buckets(current, depth, order, structural_path, values, counts_only=True):
                        visit(bucket['rows'], depth + 1)
            visit(selected, len(path))
            if len(ids) != expected_count or len(set(ids)) != expected_count:
                raise StaleTreePage('Tree selection is incomplete or contains duplicate epochs')
            return dict(revision=revision, path=path, count=expected_count, epoch_uuids=ids)

    def _selection_pages(self, body, expected_count):
        # Compatibility oracle for custom pager policies and test adapters.
        query = dict(body, limit=60, counts_only=True)
        first = self.page(query)
        if first['selection']['count'] != expected_count:
            raise StaleTreePage('Tree selection count changed; refresh this branch')
        ids = []
        def visit(page):
            if page['revision'] != body['revision']:
                raise StaleTreePage('Tree selection revision changed')
            if page['kind'] == 'epochs':
                ids.extend(row['epoch_uuid'] for row in page['epochs'])
                if len(ids) > expected_count:
                    raise StaleTreePage('Tree selection exceeds its verified count')
            else:
                for branch in page['branches']:
                    visit(self.page({**query, 'path': branch['path'], 'offset': 0}))
            if page['has_more']:
                visit(self.page({**query, 'path': page['path'], 'offset': page['offset'] + 60}))
        visit(first)
        if len(ids) != expected_count or len(set(ids)) != expected_count:
            raise StaleTreePage('Tree selection is incomplete or contains duplicate epochs')
        return dict(revision=first['revision'], path=first['path'], count=expected_count, epoch_uuids=ids)


_BATCH_READER_METHODS = {name: getattr(TreePages, name) for name in ('page', '_page', '_scope', '_build_scope')}


def witnessed_tree_page(pager, body):
    """Attest a narrow recorded-field Protocol read using existing generations.

    No persisted token, new schema, cache permission or mutation receipt. The
    client still obtains this witness from an uncached target/anchor request.
    Older/untracked backends and other tree sources keep the ordinary response.
    """
    if not isinstance(body, dict):
        return pager.page(body)
    body = dict(body)
    batch = body.pop('include_ancestors', False)
    offsets = body.pop('ancestor_offsets', [])
    if (type(batch) is not bool or not isinstance(offsets, list) or len(offsets) > 8
            or any(value is not None and (type(value) is not int or not 0 <= value <= 10_000_000) for value in offsets)
            or offsets and not batch):
        raise ValueError('Malformed tree column navigation options')
    def ordinary():
        if batch:
            raise ValueError('Tree column batching is unavailable for this scope; refresh the current tree')
        return pager.page(body)
    service = pager.service
    from disco.metadata.disk_index import DiskMetadataIndex
    index = getattr(service, 'disk_index', None)
    # Recorded (non-annotation) split names come from the one split registry.
    recorded = set(SPLIT_FIELDS)
    eligible = (isinstance(body, dict) and isinstance(body.get('protocol_uuid'), str)
                and body.get('filters', {}) == {} and 'predicate' not in body
                and isinstance(body.get('splits'), str) and body['splits']
                and all(field in recorded or field.startswith(('parameters/', 'properties/', 'metadata/'))
                        for field in body['splits'].split(','))
                and getattr(service, '_explore_state_generation', None) is not None
                and isinstance(index, DiskMetadataIndex) and _structural_contract(service))
    if not eligible:
        return ordinary()
    reader = getattr(index, 'catalog_definitions', None)
    definitions = reader() if reader is not None else {field['id']: field for field in index.catalog()['fields']}
    if any(field not in definitions or definitions[field].get('annotation_scope')
           or definitions[field].get('components') for field in body['splits'].split(',')):
        return ordinary()
    from disco.metadata.explore_queries import generation, context_annotation_locks, StaleQuery
    context = {'protocol_uuid': str(uuid.UUID(body['protocol_uuid']))}
    from workspace_state_generation import StateGenerationAuthority
    tracker = service._explore_state_generation
    contract = (tracker.response_contract() if type(tracker) is StateGenerationAuthority
                else contextlib.nullcontext())
    # Reuse only schema/DDL attestation within this response. Scope counters
    # remain live at both boundaries; closing contract failure discards it.
    with context_annotation_locks(service, context), contract:
        try:
            before = generation(service, context)
        except StaleQuery:
            return ordinary()  # Unverifiable native tracker: fresh canonical reader only.
        canonical = pager._canonical_reader()
        if batch and not canonical:
            return ordinary()
        result, parents = pager.column_pages(body, offsets) if batch else (pager.page(body), [])
        if generation(service, context) != before:
            raise StaleTreePage('Tree read generation changed; retry the current scope')
        result['read_identity'] = {'version': 1,
            'project_uuid': service.project['project_uuid'],
            'project_path': str(service.project_dir.resolve()),
            'protocol_uuid': context['protocol_uuid'],
            'tree_revision': result['revision'], 'generation': before}
        if canonical:
            result['tree_column_pages'] = True
        if batch:
            for parent in parents:
                parent['read_identity'] = result['read_identity']
                parent['tree_column_pages'] = True
            result['ancestor_pages'] = parents
        return result


def register_tree_page_routes(app, service, db_lock, registration_locks):
    from flask import jsonify, request
    pager = TreePages(service)
    app.extensions['disco.navigation.tree_pages'] = pager
    from disco.navigation.prepared_navigation import PreparedNavigation
    from disco.navigation.publication_changes import PreparationRequired
    prepared = PreparedNavigation(pager, db_lock)
    service._prepared_navigation = prepared
    app.extensions['disco.navigation.prepared'] = prepared

    def prepare_publication():
        if not prepared.supported():
            return {'status': 'unsupported'}
        prepared.reset()
        scopes = [{'splits': 'date,cell,block'}]
        store = app.extensions.get('tree_layouts')
        for identity, protocol in service.protocols.items():
            default = protocol['definition'].get('view', {}).get('group_by', ['date', 'cell', 'block'])
            scopes.append({'protocol_uuid': identity, 'splits': ','.join(default)})
            saved = store.read(identity) if store is not None else None
            if saved and saved['split_order'] != default:
                scopes.append({'protocol_uuid': identity, 'splits': ','.join(saved['split_order'])})
        receipts, deferred = [], []
        for scope in scopes:
            try:
                receipts.append(prepared.prepare(scope))
            except PreparationRequired as error:
                deferred.append({'scope': scope, 'reason': str(error)})
        failed = {prepared.key(item['scope']) for item in deferred}
        for scope in scopes:
            key = prepared.key(scope)
            if key not in prepared.entries and key not in failed:
                deferred.append({'scope': scope, 'reason': 'Prepared view collection exceeds its resource budget'})
                failed.add(key)
        return {'status': 'partial' if deferred else 'ready', 'resource': 'tree', 'views': len(prepared.entries),
                'deferred': deferred, 'elapsed_ms': sum(item.get('elapsed_ms', 0) for item in receipts)}

    app.extensions['prepare_tree_publication'] = prepare_publication

    @app.post('/api/tree-pages/prepare')
    def prepare_tree_page():
        if request.args or (request.content_length is not None and request.content_length > 65536):
            raise ValueError('Tree preparation requires at most 64 KiB of JSON and no URL parameters')
        body = request.get_json()
        if not isinstance(body, dict) or set(body) - {'protocol_uuid', 'predicate', 'filters', 'splits'}:
            raise ValueError('Malformed tree preparation scope')
        with db_lock, registration_locks():
            try:
                return jsonify(prepared.prepare(body))
            except PreparationRequired as error:
                return jsonify(status='preparing', preparation={'status': 'pending', 'resource': 'tree', 'reason': str(error)}), 202

    @app.post('/api/tree-pages')
    def tree_page():
        if request.args or (request.content_length is not None and request.content_length > 65536):
            raise ValueError('Tree page requests require a JSON body of at most 64 KiB and no URL parameters')
        try:
            body = request.get_json()
        except (RecursionError, OverflowError) as error:
            raise ValueError('Tree page JSON nesting or numeric value exceeds limits') from error
        with db_lock, registration_locks():
            try:
                return jsonify(witnessed_tree_page(pager, body))
            except StaleTreePage as error:
                return jsonify(error=str(error),code='stale_tree_revision'),409
            except PreparationRequired as error:
                return jsonify(status='preparing', preparation={'status': 'pending', 'resource': 'tree', 'reason': str(error)}),202
