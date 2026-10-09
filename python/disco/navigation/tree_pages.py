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
from workspace_service import validate_filters, WorkspaceService
from disco.decisions.explorer import ExplorerHistory
from disco.operation_timing import elapsed


TREE_SCOPE_BYTE_BUDGET = 64 * 1024 * 1024
TREE_SCOPE_CACHE_OVERHEAD = 16 * 1024  # Reserve for eight keys/entries and generation bookkeeping.
_STRUCTURAL_METHODS = {name: getattr(WorkspaceService, name) for name in (
    '_tree_rows', 'filtered_rows', 'query_result', '_filter_rows',
    '_epoch_page_identities', '_decorate', 'binding', 'source_scope', '_ready')}
_STRUCTURAL_HISTORY_METHODS = {name: getattr(ExplorerHistory, name)
                               for name in ('protocol_binding', 'protocol_binding_header', 'get')}


def _structural_contract(service):
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
    grouping_budget = 4 * 1024 * 1024

    def __init__(self, rows, fields):
        self.rows, self.fields = rows, tuple(fields)
        self.grouping_budget = min(self.grouping_budget, max(16 * 1024, len(rows) * 64))
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
        cost = (256 + sys.getsizeof(key) + sys.getsizeof(key[1])
                + sys.getsizeof(buckets) + sys.getsizeof(current)
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


def selection_revision(service, protocol, predicate, filters, order, rows, binding=None, annotation_scope=None):
    """Shared explorer-summary/page identity, independent of page offset/path."""
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
    if isinstance(values, _NavigationValues) and cache_key in values.group_cache:
        return values.group_cache[cache_key][1]
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

        Annotation membership is live and intentionally bypasses this cache.
        Source eligibility and frozen protocol binding are part of every key.
        Keeping this on the service also shares it with matching-epoch reads.
        """
        service = self.service
        service._ready()
        from disco.metadata.disk_index import DiskMetadataIndex
        from disco.navigation.tag_predicates import referenced_fields
        index = getattr(service, 'disk_index', None)
        filters = validate_filters(body.get('filters'))
        if (not isinstance(index, DiskMetadataIndex)
                or any(field in filters for field in ('tag', 'tagged', 'tag_predicate', 'metadata_predicate'))
                or referenced_fields(body.get('predicate', {'all': []}))):
            return self._build_scope(body)
        index._check()  # A cache hit must still refuse changed/corrupt index bytes.
        structural = _structural_scope(body)
        if not _structural_contract(service):
            # An unproven policy cannot reuse a native membership/cache key.
            return self._build_scope(body)
        protocol = body.get('protocol_uuid')
        if protocol is not None:
            protocol = _uuid(protocol)
            if 'predicate' in body:
                raise ValueError('Protocol tree membership cannot be replaced by a source predicate')
        header_provider = getattr(service, 'binding_header_provider', None)
        binding = (header_provider(protocol) if structural and header_provider else service.binding(protocol)) if protocol else None
        # Provider-only/unbound protocol fixtures may mutate their membership in
        # place without replacing service.protocols. Frozen binding headers are
        # immutable; other scopes compare their exact UUID sequence on each hit.
        membership = (tuple(member['uuid'] for member in service.protocols[protocol]['result']['epochs'])
                      if protocol and binding is None else None)
        generation = (id(index), index.generation, id(service.rows),
                      id(service._fingerprints), id(service.protocols))
        base_bytes = sys.getsizeof(service._fingerprints) + TREE_SCOPE_CACHE_OVERHEAD
        if base_bytes >= TREE_SCOPE_BYTE_BUDGET:
            service._tree_page_scope_cache = None
            return self._build_scope(body)
        cached = getattr(service, '_tree_page_scope_cache', None)
        if cached is None or cached[0] != generation or cached[2] != service._fingerprints:
            # The published fingerprint dictionary is also used by reconciliation
            # and test adapters. Detect in-place edits, not only refresh swaps.
            # Equality is a linear lightweight check; it avoids sorting/encoding
            # the full membership for every navigation request.
            cached = service._tree_page_scope_cache = (generation, {}, dict(service._fingerprints))
        cache = cached[1]
        key = (checksum({'protocol': protocol, 'binding': binding and {
            'version': binding['version'], 'revision_uuid': binding.get('revision_uuid')},
            'source_scope': service.source_scope()['revision'] if protocol is None else None,
            'predicate': body.get('predicate'), 'filters': filters,
            'splits': body.get('splits', 'date,cell,block'),
            'depth': None if structural else len(body.get('path', [])),
            'anchor': False if structural else bool(body.get('anchor_uuid'))}), membership)
        if key in cache:
            entry = cache.pop(key)
            cache[key] = entry
            return entry[0]
        result = self._build_scope(body)
        rows, _, values, _, _, _ = result
        # Bound retained row references plus projected values across all scopes.
        # An oversize projection may serve this request but is never retained.
        weight = len(rows) if isinstance(values, _NavigationValues) else len(rows) + sum(len(value) for value in values.values())
        if weight <= 2_000_000:
            byte_limit = TREE_SCOPE_BYTE_BUDGET - base_bytes
            retained_bytes = _retained_scope_bytes(result, service.rows, byte_limit)
            # UUID strings are borrowed from service.protocols, but the exact
            # unbound membership tuple in this cache key is a new container.
            if membership is not None:
                retained_bytes += sys.getsizeof(membership)
            if retained_bytes > byte_limit:
                return result
            cache[key] = (result, weight, retained_bytes)
            while (len(cache) > 8 or sum(entry[1] for entry in cache.values()) > 2_000_000
                    or sum(entry[2] for entry in cache.values()) > byte_limit):
                cache.pop(next(iter(cache)))
        return result

    def _build_scope(self, body, *, all_fields=False):
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
        canonical_index = isinstance(index, DiskMetadataIndex) and _structural_contract(service)
        structural = canonical_index and _structural_scope(body)
        # Recorded/joint splits still project their exact typed values below.
        # Only membership can borrow basic rows: custom and frozen adapters keep
        # their public reader, as do live annotation/metadata-filter policies.
        raw_membership = canonical_index and not any(field in filters for field in (
            'tag', 'tagged', 'tag_predicate', 'metadata_predicate'))
        if raw_membership and protocol:
            # Tree summaries have no curation fields. Use the same checked raw
            # membership as the bounded epoch endpoint; only leaf annotations
            # are subsequently fetched for the displayed page.
            identities, _ = service._epoch_page_identities(protocol, filters)
            rows = [service.rows[identity] for identity in identities]
        else:
            rows = service._tree_rows(protocol, filters)
        if index is not None:
            # Registered definitions remain valid for empty or excluded scopes;
            # paged navigation needs no repeated per-field scope summaries.
            catalog = index.catalog()
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
        definitions = {field['id']: field for field in catalog['fields']}
        splits = body.get('splits', 'date,cell,block')
        order = parse_splits(splits, definitions)
        for field in order:
            if field not in definitions:
                definitions[field] = joint_definition(field, definitions)
        if structural:
            values = _NavigationValues(service.rows, order)
        elif index is not None:
            requested = order if all_fields or body.get('anchor_uuid') else order[:len(body.get('path', []))+1]
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
                    **{name:child[name] for name in ('components','has_missing_components','start_time') if name in child}})
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

    def selection(self, body, expected_count):
        """Exact bounded DFS membership without rendering descendant pages."""
        with elapsed("disco.navigation.tree_pages", "selection"):
            if (not isinstance(body, dict) or set(body) - {'protocol_uuid', 'predicate', 'filters', 'splits', 'path', 'revision'}
                    or type(expected_count) is not int or not 1 <= expected_count <= 1000):
                raise ValueError('Tree selection requires 1–1,000 epochs and a bounded scope')
            path = body.get('path', [])
            validate_tree_path(path)
            expected = body.get('revision')
            if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
                raise ValueError('Tree selection requires a current revision')
            if not self._canonical_reader():
                return self._selection_pages(body, expected_count)
            rows, _, values, definitions, order, revision = self._build_scope(body, all_fields=True)
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
    recorded = {'date', 'cell', 'cell type', 'group', 'block', 'protocol', 'source'}
    eligible = (isinstance(body, dict) and isinstance(body.get('protocol_uuid'), str)
                and body.get('filters', {}) == {} and 'predicate' not in body
                and isinstance(body.get('splits'), str) and body['splits']
                and all(field in recorded or field.startswith(('parameters/', 'properties/', 'metadata/'))
                        for field in body['splits'].split(','))
                and getattr(service, '_explore_state_generation', None) is not None
                and isinstance(index, DiskMetadataIndex) and _structural_contract(service))
    if not eligible:
        return ordinary()
    definitions = {field['id']: field for field in index.catalog()['fields']}
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
