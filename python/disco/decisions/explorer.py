"""Immutable applied source-query/tree revisions with transactional audit."""
from __future__ import annotations

import copy
import contextlib
import hashlib
import datetime as dt
import uuid

from recording_workspace import now, workspace_tables
from workspace_audit import build_audit_payload
from workspace_authored_json import write_row
from disco.workbench.recipes import checksum, member_map
from disco.operation_timing import elapsed

# Mirrors disco.navigation.predicates.PREDICATE_VERSION (v2: built-in null = not recorded).
PREDICATE_CONTRACT_VERSION = 2

ACTION = 'explorer_revision_created'

# A delta revision stores its parent, the parent's seal and an exact membership
# delta instead of the full member list. Its seal covers the parent seal, so the
# chain back to a full-recipe root proves the whole membership.
DELTA_STORAGE = 'membership-delta-v1'
_HEADER_LIMIT = 4096
_MEMBER_LIMIT = 8
_OVERLAY_DEPTH = 16
_MISSING = object()
_MULTISET_MODULUS = 1 << 256


def _member_term(identity, fingerprint):
    return int.from_bytes(hashlib.sha256(f'{identity}:{fingerprint}'.encode()).digest(), 'big')


def membership_hash(items, base=None, removed=()):
    """Order-independent multiset hash of (epoch UUID, fingerprint) members.

    Sum of SHA-256 terms modulo 2**256, so a delta updates it in O(delta):
    ``membership_hash(added, base=parent_hash, removed=removed_items)``.
    """
    total = int(base, 16) if base is not None else 0
    for identity, fingerprint in items:
        total += _member_term(identity, fingerprint)
    for identity, fingerprint in removed:
        total -= _member_term(identity, fingerprint)
    return format(total % _MULTISET_MODULUS, '064x')


class MemberView:
    """Read-only UUID->fingerprint view of a sealed revision's exact membership.

    A delta revision overlays its parent's view (added minus removed), so a new
    link costs O(delta); views flatten into one dict past a bounded depth.
    Callers must not mutate it; every reader of that revision shares it.
    """
    __slots__ = ('_base', '_added', '_removed', '_length', 'depth')

    def __init__(self, base, added=None, removed=()):
        if isinstance(base, MemberView) and base.depth >= _OVERLAY_DEPTH:
            base = base.flatten()
        self._base, self._added, self._removed = base, dict(added or {}), frozenset(removed)
        self.depth = base.depth + 1 if isinstance(base, MemberView) else 0
        self._length = len(base) - len(self._removed) + len(self._added)

    def flatten(self):
        flat = {key: value for key, value in self._base.items() if key not in self._removed}
        flat.update(self._added)
        return flat

    def get(self, key, default=None):
        if key in self._added:
            return self._added[key]
        if key in self._removed:
            return default
        return self._base.get(key, default)

    def __getitem__(self, key):
        value = self.get(key, _MISSING)
        if value is _MISSING:
            raise KeyError(key)
        return value

    def __contains__(self, key):
        return key in self._added or (key not in self._removed and key in self._base)

    def __iter__(self):
        for key in self._base:
            if key not in self._removed and key not in self._added:
                yield key
        yield from self._added

    def __len__(self):
        return self._length

    def keys(self):
        return _MemberKeys(self)

    def items(self):
        return ((key, self[key]) for key in self)

    def values(self):
        return (self[key] for key in self)


class _MemberKeys:
    __slots__ = ('view',)

    def __init__(self, view):
        self.view = view

    def __iter__(self):
        return iter(self.view)

    def __len__(self):
        return len(self.view)

    def __contains__(self, key):
        return key in self.view

    def __and__(self, other):
        small, large = (other, self.view) if len(other) <= len(self.view) else (self.view, other)
        return {key for key in small if key in large}

    __rand__ = __and__

    def __sub__(self, other):
        return {key for key in self.view if key not in other}

    def __rsub__(self, other):
        return {key for key in other if key not in self.view}

    def __or__(self, other):
        return set(self.view) | set(other)

    __ror__ = __or__


def _copy_recipe(recipe):
    """Detach canonical member records without recursively copying strings.

    Seed deepcopy's memo only for the exact immutable-value member schema.
    The rest of the recipe still follows ordinary deepcopy, including aliases
    back into membership. Custom member shapes retain their original behavior.
    """
    epochs = recipe.get('epochs') if type(recipe) is dict else None
    if type(epochs) is not list:
        return copy.deepcopy(recipe)
    members, memo = [], {}
    for row in epochs:
        if type(row) is not dict:
            return copy.deepcopy(recipe)
        identity = id(row)
        if identity not in memo:
            member = row.copy()
            if (len(member) != 2 or any(type(key) is not str for key in member)
                    or type(member.get('uuid')) is not str or type(member.get('metadata_hash')) is not str):
                return copy.deepcopy(recipe)
            memo[identity] = member
        members.append(memo[identity])
    memo[id(epochs)] = members
    return copy.deepcopy(recipe, memo)


def explorer_table(dj):
    schema = dj.Schema('recording_workspace')

    @schema
    class ExplorerRevision(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        revision_uuid: varchar(36)
        ---
        created_at: datetime
        name: varchar(255)
        parent_revision_uuid=null: varchar(36)
        summary: json
        recipe: json
        """
    return ExplorerRevision


def protocol_membership_table(dj):
    """Indexed exact membership of bound additive lineages.

    A lineage is the full-recipe root revision; each bound delta adds its rows
    tagged with the revision that added them. A revision's membership is the
    rows whose adding revision lies on its chain back to the root.
    """
    schema = dj.Schema('recording_workspace')

    @schema
    class ProtocolMembership(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        lineage_uuid: varchar(36)
        epoch_uuid: varchar(36)
        added_revision_uuid: varchar(36)
        ---
        metadata_hash: char(64)
        removed_revision_uuid=null: varchar(36)
        """
    return ProtocolMembership


def protocol_binding_table(dj):
    schema = dj.Schema('recording_workspace')

    @schema
    class ProtocolBinding(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        protocol_uuid: varchar(36)
        ---
        revision_uuid: varchar(36)
        version: int unsigned
        bound_at: datetime
        """
    return ProtocolBinding


class ExplorerHistory:
    def __init__(self, dj, project_uuid, *, event_table=None, revision_table=None, binding_table=None,
                 membership_table=None):
        self.dj = dj
        self._membership = membership_table
        # Injected (custom) revision storage declares no index table of its own.
        self._declare_membership = revision_table is None
        self.project_uuid = str(uuid.UUID(project_uuid))
        self.Event = workspace_tables(dj)[2] if event_table is None else event_table
        self.Revision = explorer_table(dj) if revision_table is None else revision_table
        self.Binding = protocol_binding_table(dj) if binding_table is None else binding_table
        self._recipe_cache = {}
        # Verified seals (revision -> header without members) and bounded shared
        # membership views. Both describe insert-only, sealed revisions.
        self._headers = {}
        self._member_views = {}

    def protocol_binding_header(self, protocol_uuid):
        """Read the current binding version without hydrating its frozen recipe."""
        protocol_uuid = str(uuid.UUID(protocol_uuid))
        rows = (self.Binding & {'project_uuid': self.project_uuid, 'protocol_uuid': protocol_uuid}).to_dicts()
        return rows[0] if rows else None

    def protocol_binding(self, protocol_uuid):
        with elapsed("disco.decisions.explorer", "protocol_binding"):
            row = self.protocol_binding_header(protocol_uuid)
            if row is None:
                return None
            identity = row['revision_uuid']
            if identity not in self._recipe_cache:
                self._recipe_cache[identity] = self.get(identity)['recipe']
            return {**row, 'recipe': _copy_recipe(self._recipe_cache[identity])}

    def bind(self, revision_uuid, protocol_uuid, expected_version, actor, diff, previous_count,
             *, expected_query_revision=None, current_query_revision=None, diff_summary=None,
             _in_transaction=False, _lock_held=False, reason=None):
        protocol_uuid = str(uuid.UUID(protocol_uuid))
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError('Expected binding version must be a nonnegative integer')
        record = {'revision_uuid': str(uuid.UUID(revision_uuid)), 'recipe': self.header(revision_uuid)}
        connection = self.dj.conn()
        lock = hashlib.sha256((self.project_uuid + protocol_uuid).encode()).hexdigest()
        if not _lock_held and connection.query(f"SELECT GET_LOCK('{lock}', 10)").fetchone()[0] != 1:
            raise RuntimeError('Another protocol dataset update is running')
        try:
            with (contextlib.nullcontext() if _in_transaction else connection.transaction):
                # The binding CAS needs the current version and revision only.
                previous = self.protocol_binding_header(protocol_uuid)
                version = previous['version'] if previous else 0
                from disco.decisions.curation import RevisionConflict
                if version != expected_version:
                    raise RevisionConflict({'binding_version': version})
                if current_query_revision is not None and current_query_revision() != expected_query_revision:
                    raise RevisionConflict({'binding_version': version})
                now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
                row = {'project_uuid': self.project_uuid, 'protocol_uuid': protocol_uuid,
                       'revision_uuid': record['revision_uuid'], 'version': version + 1, 'bound_at': now}
                if previous:
                    self.Binding.update1(row)
                else:
                    self.Binding.insert1(row)
                self._extend_lineage(record['recipe'])
                event_uuid = str(uuid.uuid4())
                payload = build_audit_payload('protocol_dataset_bound', actor, {
                    'protocol_uuid': protocol_uuid, 'revision_uuid': record['revision_uuid'],
                    'binding_version': row['version'], 'previous_revision_uuid': previous['revision_uuid'] if previous else None,
                    'previous_count': previous_count, 'epoch_count': record['recipe']['epoch_count'],
                    'diff': diff, 'diff_summary': diff_summary, 'recipe_sha256': record['recipe']['content_sha256'],
                    **({'reason': reason, 'working_dataset_membership_changed': False} if reason == 'pre_import_baseline_freeze' else {})},
                    operation_uuid=event_uuid, context={'project_uuid': self.project_uuid})
                self.Event.insert1({'event_uuid': event_uuid, 'project_uuid': self.project_uuid,
                    'occurred_at': now, 'actor': actor, 'action': 'protocol_dataset_bound', 'payload': payload})
        finally:
            if not _lock_held:
                with contextlib.suppress(Exception):
                    connection.query(f"SELECT RELEASE_LOCK('{lock}')")
        return {'event_uuid': event_uuid, 'version': row['version'], 'revision_uuid': record['revision_uuid']}

    def create(self, preview, sources, catalog_ref, actor, *, name=None, parent_revision_uuid=None, _in_transaction=False):
        if name is None:
            name = 'Applied query'
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise ValueError('Revision name must be 1–255 characters')
        parent = None
        if parent_revision_uuid is not None:
            if not isinstance(parent_revision_uuid, str):
                raise ValueError('Parent revision identity must be a UUID string')
            parent_revision_uuid = str(uuid.UUID(parent_revision_uuid))
            parent = self.get(parent_revision_uuid)['recipe']  # Same-project immutable parent.
        identity, timestamp = str(uuid.uuid4()), now()
        epochs = copy.deepcopy(preview['membership'])
        if len({row['uuid'] for row in epochs}) != len(epochs) or len(epochs) != preview['matched_count']:
            raise ValueError('Applied revision membership is inconsistent')
        members = member_map({'epochs': epochs})
        previous = member_map(parent) if parent else {}
        delta = {'added': sorted(members.keys() - previous.keys()),
                 'removed': sorted(previous.keys() - members.keys()),
                 'changed': sorted(key for key in members.keys() & previous.keys()
                                   if members[key]['metadata_hash'] != previous[key]['metadata_hash'])}
        summary = {'revision_uuid': identity, 'name': name.strip(), 'created_at': timestamp,
                   'parent_revision_uuid': parent_revision_uuid, 'matched_count': len(epochs),
                   'epoch_count': len(epochs), 'total_source': preview['total_source'], 'splits': preview['splits'],
                   'diff_counts': {key: len(value) for key, value in delta.items()}, 'baseline_created': parent is None}
        audit = build_audit_payload(ACTION, actor, {'revision_uuid': identity, **summary},
            operation_uuid=identity, context={'project_uuid': self.project_uuid},
            inputs={'predicate_sha256': checksum(preview['predicate']), 'catalog_ref': str(catalog_ref)},
            outputs={'revision_uuid': identity, 'epoch_count': len(epochs)})
        recipe = {'format': 'recording-explorer-revision', 'version': 1, **summary,
                  'project_uuid': self.project_uuid, 'catalog_ref': str(catalog_ref),
                  'predicate_version': PREDICATE_CONTRACT_VERSION, 'predicate': copy.deepcopy(preview['predicate']),
                  'predicate_sha256': checksum(preview['predicate']),
                  'metadata_fingerprint_version': preview['metadata_fingerprint_version'],
                  'source_revisions': sorted(preview.get('source_revisions', {source['source_sha256'] for source in sources})),
                  'tree_view': {'format': 'recording-tree-view', 'version': 1,
                                'fields': preview['tree']['split_order']},
                  'epochs': epochs, 'diff': delta, 'provenance': audit['audit']['provenance']}
        if 'source_scope' in preview:
            recipe['source_scope'] = copy.deepcopy(preview['source_scope'])
        if 'annotation_scope' in preview:
            recipe['annotation_scope'] = copy.deepcopy(preview['annotation_scope'])
        if preview.get('view_adaptation'):
            recipe['view_adaptation'] = copy.deepcopy(preview['view_adaptation'])
        if preview.get('additive_publication'):
            recipe['membership_kind'] = 'additive_union'
            recipe['additive_publication'] = copy.deepcopy(preview['additive_publication'])
        if preview.get('pending_union_provenance'):
            recipe['membership_kind'] = 'workbench_pending_union'
            recipe['pending_union_provenance'] = copy.deepcopy(preview['pending_union_provenance'])
        recipe['content_sha256'] = checksum(recipe)
        # Keep the validated exact recipe separate from audit's human-readable
        # redaction pass; predicate literals must survive a restore unchanged.
        audit['recipe_sha256'] = recipe['content_sha256']
        occurred = dt.datetime.fromisoformat(timestamp).astimezone(dt.timezone.utc).replace(tzinfo=None)
        with (contextlib.nullcontext() if _in_transaction else self.dj.conn().transaction):
            write_row(self.Revision, {'project_uuid': self.project_uuid, 'revision_uuid': identity,
                'created_at': occurred, 'name': summary['name'], 'parent_revision_uuid': parent_revision_uuid,
                'summary': summary, 'recipe': recipe}, schema='explorer_revision')
            self.Event.insert1({'event_uuid': identity, 'project_uuid': self.project_uuid,
                'occurred_at': occurred, 'actor': actor, 'action': ACTION, 'payload': audit})
        return {'revision_uuid': identity, 'recipe': recipe, 'summary': summary}

    def create_delta(self, parent_revision_uuid, added, removed, actor, *, name, fields=None, _in_transaction=False):
        """Seal a revision as its parent plus an exact delta: O(delta), not O(members).

        ``added`` maps new epoch UUIDs to fingerprints and ``removed`` lists
        parent members that leave. The stored recipe carries the parent seal,
        so verifying it proves the chain; readers resolve membership from the
        chain. ``fields`` override predicate/splits/tree/scope/source fields and
        set additive or pending-union provenance; the rest inherit the parent.
        """
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise ValueError('Revision name must be 1-255 characters')
        parent_revision_uuid = str(uuid.UUID(parent_revision_uuid))
        parent = self.header(parent_revision_uuid)
        parent_members = self.members(parent_revision_uuid)
        added = {str(uuid.UUID(key)): value for key, value in added.items()}
        removed = sorted({str(uuid.UUID(key)) for key in removed})
        member_map({'epochs': [dict(uuid=key, metadata_hash=value) for key, value in added.items()]})
        if (any(key in parent_members for key in added) or any(key not in parent_members for key in removed)
                or set(added) & set(removed)):
            raise ValueError('A delta revision may only add new epochs and remove existing ones')
        fields = copy.deepcopy(fields or {})
        identity, timestamp = str(uuid.uuid4()), now()
        count = parent['epoch_count'] + len(added) - len(removed)
        predicate = fields.pop('predicate', parent['predicate'])
        delta = {'added': [dict(uuid=key, metadata_hash=added[key]) for key in sorted(added)], 'removed': removed}
        diff = {'added': sorted(added), 'removed': removed, 'changed': []}
        summary = {'revision_uuid': identity, 'name': name.strip(), 'created_at': timestamp,
                   'parent_revision_uuid': parent_revision_uuid, 'matched_count': count, 'epoch_count': count,
                   'total_source': fields.pop('total_source', parent['total_source']),
                   'splits': fields.pop('splits', parent['splits']),
                   'diff_counts': {key: len(value) for key, value in diff.items()}, 'baseline_created': False}
        audit = build_audit_payload(ACTION, actor, {'revision_uuid': identity, **summary},
            operation_uuid=identity, context={'project_uuid': self.project_uuid},
            inputs={'predicate_sha256': checksum(predicate), 'catalog_ref': parent['catalog_ref']},
            outputs={'revision_uuid': identity, 'epoch_count': count})
        recipe = {'format': 'recording-explorer-revision', 'version': 1, **summary, 'storage': DELTA_STORAGE,
                  'parent_content_sha256': parent['content_sha256'],
                  'lineage_uuid': parent.get('lineage_uuid', parent_revision_uuid),
                  'membership_hash': membership_hash(added.items(), base=self.membership_hash(parent_revision_uuid),
                                                     removed=((key, parent_members[key]) for key in removed)),
                  'project_uuid': self.project_uuid, 'catalog_ref': parent['catalog_ref'],
                  'predicate': predicate,
                  'predicate_sha256': checksum(predicate),
                  'metadata_fingerprint_version': parent['metadata_fingerprint_version'],
                  'source_revisions': sorted(fields.pop('source_revisions', parent['source_revisions'])),
                  'tree_view': fields.pop('tree_view', parent['tree_view']),
                  'delta': delta, 'diff': diff, 'provenance': audit['audit']['provenance']}
        if 'predicate_version' in parent:
            recipe['predicate_version'] = parent['predicate_version']  # Same predicate semantics as the parent.
        for key in ('source_scope', 'annotation_scope'):
            if key in fields:
                recipe[key] = fields.pop(key)
            elif key in parent:
                recipe[key] = copy.deepcopy(parent[key])
        if 'additive_publication' in fields:
            recipe['membership_kind'] = 'additive_union'
            recipe['additive_publication'] = fields.pop('additive_publication')
        if 'pending_union_provenance' in fields:
            recipe['membership_kind'] = 'workbench_pending_union'
            recipe['pending_union_provenance'] = fields.pop('pending_union_provenance')
        if fields:
            raise ValueError('Unsupported delta revision fields: ' + ', '.join(sorted(fields)))
        recipe['content_sha256'] = checksum(recipe)
        audit['recipe_sha256'] = recipe['content_sha256']
        occurred = dt.datetime.fromisoformat(timestamp).astimezone(dt.timezone.utc).replace(tzinfo=None)
        with (contextlib.nullcontext() if _in_transaction else self.dj.conn().transaction):
            write_row(self.Revision, {'project_uuid': self.project_uuid, 'revision_uuid': identity,
                'created_at': occurred, 'name': summary['name'], 'parent_revision_uuid': parent_revision_uuid,
                'summary': summary, 'recipe': recipe}, schema='explorer_revision')
            self.Event.insert1({'event_uuid': identity, 'project_uuid': self.project_uuid,
                'occurred_at': occurred, 'actor': actor, 'action': ACTION, 'payload': audit})
        return {'revision_uuid': identity, 'recipe': copy.deepcopy(recipe), 'summary': summary}

    def create_and_bind(self, preview, sources, catalog_ref, actor, *, protocol_uuid,
                        expected_version, expected_query_revision, current_query_revision,
                        diff, previous_count, diff_summary, name, parent_revision_uuid=None, reason=None):
        """Publish a propagated candidate and binding in one transaction.

        The caller holds the project source-eligibility guard. Keep the protocol
        advisory lock through COMMIT so curation sees a complete working set.
        """
        protocol_uuid = str(uuid.UUID(protocol_uuid))
        connection = self.dj.conn()
        lock = hashlib.sha256((self.project_uuid + protocol_uuid).encode()).hexdigest()
        if connection.query(f"SELECT GET_LOCK('{lock}', 10)").fetchone()[0] != 1:
            raise RuntimeError('Another protocol dataset update is running')
        try:
            with connection.transaction:
                record = self.create(preview, sources, catalog_ref, actor, name=name,
                    parent_revision_uuid=parent_revision_uuid, _in_transaction=True)
                saved = self.bind(record['revision_uuid'], protocol_uuid, expected_version,
                    actor, diff, previous_count, expected_query_revision=expected_query_revision,
                    current_query_revision=current_query_revision, diff_summary=diff_summary,
                    _in_transaction=True, _lock_held=True, reason=reason)
        finally:
            with contextlib.suppress(Exception):
                connection.query(f"SELECT RELEASE_LOCK('{lock}')")
        return record, saved

    def list(self, limit=20, offset=0):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise ValueError('Revision page requires limit 1–100 and nonnegative offset')
        rows = (self.Revision & {'project_uuid': self.project_uuid}).proj('summary', 'created_at').fetch(
            as_dict=True, order_by='created_at DESC, revision_uuid DESC', limit=limit + 1, offset=offset)
        return {'revisions': [copy.deepcopy(row['summary']) for row in rows[:limit]],
                'limit': limit, 'offset': offset, 'has_more': len(rows) > limit}

    @property
    def Membership(self):
        """The lineage membership table (declared before data transactions), or None."""
        if self._membership is None and self._declare_membership and hasattr(self.dj, 'Schema'):
            self._membership = protocol_membership_table(self.dj)
        return self._membership

    def _chain(self, revision_uuid):
        """Revision UUIDs from a verified revision back to its full-recipe root."""
        chain, header = [], self.header(revision_uuid)
        while True:
            chain.append(header['revision_uuid'])
            if header.get('storage') != DELTA_STORAGE:
                return chain
            header = self.header(header['parent_revision_uuid'])

    def _extend_lineage(self, header):
        """Record a bound delta in its lineage index, in the bind transaction.

        Added rows are inserted; removed members are marked with the removing
        revision. The first additive delta bound on an unindexed lineage
        backfills the chain once (O(root)); a removal on an unindexed lineage
        leaves it unindexed, so pruning stays O(removed).
        """
        table = self.Membership
        if table is None or header.get('storage') != DELTA_STORAGE:
            return
        lineage = header['lineage_uuid']  # Sealed in the delta: no chain walk for the common case.
        restriction = {'project_uuid': self.project_uuid, 'lineage_uuid': lineage}

        def recorded(**fields):  # One bounded existence probe, never the lineage's rows.
            return bool((table & {**restriction, **fields}).proj().fetch(as_dict=True, limit=1))
        revision = header['revision_uuid']
        if recorded(added_revision_uuid=lineage):
            # Indexed lineage: earlier links were recorded when they were bound.
            if recorded(added_revision_uuid=revision) or recorded(removed_revision_uuid=revision):
                return  # Rebinding an already recorded revision (e.g. after an undo).
            links = [revision]
        elif header['delta']['removed'] and not header['delta']['added']:
            return  # A removal on an unindexed lineage leaves it unindexed: O(removed).
        else:
            links = list(reversed(self._chain(revision)))  # One-time backfill of the whole chain.
        pending, marks = {}, []
        for link_uuid in links:
            link = self.header(link_uuid)
            if link.get('storage') != DELTA_STORAGE:
                for key, value in self.members(link_uuid).items():
                    pending[key] = {**restriction, 'epoch_uuid': key, 'added_revision_uuid': link_uuid,
                                    'metadata_hash': value, 'removed_revision_uuid': None}
                continue
            for row in link['delta']['added']:
                pending[row['uuid']] = {**restriction, 'epoch_uuid': row['uuid'], 'added_revision_uuid': link_uuid,
                                        'metadata_hash': row['metadata_hash'], 'removed_revision_uuid': None}
            for key in link['delta']['removed']:
                if key in pending:
                    pending[key]['removed_revision_uuid'] = link_uuid
                else:
                    marks.append((key, link_uuid))
        if pending:
            table.insert(list(pending.values()))
        if marks:
            chain_set = set(self._chain(revision))
            current = {row['epoch_uuid']: row for row in (table & restriction & [
                {'epoch_uuid': key} for key, _ in marks]).to_dicts()
                if row['added_revision_uuid'] in chain_set and row['removed_revision_uuid'] is None}
            for key, link_uuid in marks:
                table.update1({**current[key], 'removed_revision_uuid': link_uuid})

    def retire_delta(self, revision_uuid):
        """Remove an undone delta's rows from its lineage: one DELETE, caller's transaction."""
        table = self.Membership
        header = self.header(revision_uuid)
        if table is None or header.get('storage') != DELTA_STORAGE:
            return
        (table & {'project_uuid': self.project_uuid, 'lineage_uuid': header['lineage_uuid'],
                  'added_revision_uuid': header['revision_uuid']}).delete_quick()

    def verify_lineage(self, revision_uuid):
        """Re-hash a bound revision's indexed membership against its sealed multiset hash.

        O(members); for exports, app-state capture/restore and first use per
        process. Returns the UUID->fingerprint map, or None without a lineage index.
        """
        table = self.Membership
        header = self.header(revision_uuid)
        if table is None:
            return None
        chain = set(self._chain(revision_uuid))
        lineage = header.get('lineage_uuid', header['revision_uuid'])
        rows = (table & {'project_uuid': self.project_uuid, 'lineage_uuid': lineage}).to_dicts()
        if not rows:
            return None
        rows = [row for row in rows if row['added_revision_uuid'] in chain
                and row.get('removed_revision_uuid') not in chain]
        members = {row['epoch_uuid']: row['metadata_hash'] for row in rows}
        if len(members) != len(rows) or membership_hash(members.items()) != self.membership_hash(revision_uuid):
            raise ValueError('Indexed lineage membership failed integrity verification')
        return members

    def verify_membership(self, revision_uuid, items=None):
        """Full re-hash where membership becomes scientific truth (export, capture, restore).

        ``items`` (UUID, fingerprint) pairs, the membership about to be used,
        must hash to the revision's sealed multiset hash; an indexed lineage
        must agree as well. O(members); raises on any mismatch.
        """
        items = list(self.members(revision_uuid).items() if items is None else items)
        if (len({key for key, _ in items}) != len(items)
                or membership_hash(items) != self.membership_hash(revision_uuid)):
            raise ValueError('Revision membership failed integrity verification')
        self.verify_lineage(revision_uuid)

    def membership_hash(self, revision_uuid):
        """The sealed multiset hash of a revision (computed once for a v1 root)."""
        header = self.header(revision_uuid)
        if 'membership_hash' in header:
            return header['membership_hash']
        cached = self._headers[header['revision_uuid']]
        cached['membership_hash'] = membership_hash(self.members(revision_uuid).items())
        return cached['membership_hash']

    @staticmethod
    def _remember(cache, key, value, limit):
        cache.pop(key, None)
        cache[key] = value
        while len(cache) > limit:
            del cache[next(iter(cache))]

    def _row(self, revision_uuid):
        rows = (self.Revision & {'project_uuid': self.project_uuid, 'revision_uuid': revision_uuid}).to_dicts()
        if not rows:
            raise KeyError('Explorer revision not found in this project')
        return rows[0]

    def _verified_recipe(self, row, revision_uuid):
        """Verify one stored row's seal; a delta also proves its parent link."""
        recipe = _copy_recipe(row['recipe'])
        expected = recipe.pop('content_sha256', None)
        if (expected != checksum(recipe) or recipe.get('format') != 'recording-explorer-revision'
                or recipe.get('version') != 1 or recipe.get('project_uuid') != self.project_uuid
                or recipe.get('revision_uuid') != revision_uuid
                or any(recipe.get(key) != value for key, value in row['summary'].items())):
            raise ValueError('Stored explorer revision failed integrity verification')
        recipe['content_sha256'] = expected
        if recipe.get('storage') == DELTA_STORAGE:
            delta, parent = recipe.get('delta'), recipe.get('parent_revision_uuid')
            if (not isinstance(delta, dict) or set(delta) != {'added', 'removed'} or not parent or 'epochs' in recipe
                    or self.header(parent)['content_sha256'] != recipe.get('parent_content_sha256')):
                raise ValueError('Stored explorer revision failed integrity verification')
            parent_members = self.members(parent)
            if (any(row['uuid'] in parent_members for row in delta['added'])
                    or any(key not in parent_members for key in delta['removed'])
                    or recipe.get('membership_hash') != membership_hash(
                        ((row['uuid'], row['metadata_hash']) for row in delta['added']),
                        base=self.membership_hash(parent),
                        removed=((key, parent_members[key]) for key in delta['removed']))
                    or recipe.get('lineage_uuid') != self.header(parent).get('lineage_uuid', parent)
                    or recipe.get('epoch_count') != len(parent_members) + len(delta['added']) - len(delta['removed'])):
                raise ValueError('Stored explorer revision failed integrity verification')
        elif not isinstance(recipe.get('epochs'), list):
            raise ValueError('Stored explorer revision failed integrity verification')
        return recipe

    def header(self, revision_uuid):
        """A verified revision without its member list (O(delta) per new link).

        The row's existence is read every time. Its seal is verified once per
        process and then reused, as it is when the revision is a verified
        ancestor of a later link. A full root's membership view is retained
        from that first verification.
        """
        revision_uuid = str(uuid.UUID(revision_uuid))
        cached = self._headers.get(revision_uuid)
        if cached is not None:
            if not (self.Revision & {'project_uuid': self.project_uuid, 'revision_uuid': revision_uuid}).proj().to_dicts():
                raise KeyError('Explorer revision not found in this project')
            return copy.deepcopy(cached)
        recipe = self._verified_recipe(self._row(revision_uuid), revision_uuid)
        epochs = recipe.pop('epochs', None)
        if epochs is not None:
            recipe.pop('diff', None)  # A root's diff can list every member.
            self._remember(self._member_views, revision_uuid, self._root_view(epochs), _MEMBER_LIMIT)
        self._remember(self._headers, revision_uuid, recipe, _HEADER_LIMIT)
        return copy.deepcopy(recipe)

    @staticmethod
    def _root_view(epochs):
        members = {row['uuid']: row['metadata_hash'] for row in epochs}
        if len(members) != len(epochs):
            raise ValueError('Frozen membership contains duplicate epoch identities')
        return MemberView(members)

    def prepared_delta(self, previous, current, limit=20000):
        """Return an already verified adjacent delta without hydrating membership.

        None requests explicit preparation when the bounded cached proof is no
        longer retained. This is a display projection, never new seal authority.
        """
        if type(limit) is not int or not 0 <= limit <= 20000:
            raise ValueError('Prepared delta limit must be between 0 and 20000')
        if type(self) is not ExplorerHistory or any(
                getattr(getattr(self, name, None), '__func__', getattr(self, name, None)) is not method
                for name, method in _PREPARED_DELTA_METHODS.items()):
            return None
        try:
            previous, current = str(uuid.UUID(previous)), str(uuid.UUID(current))
        except (ValueError, TypeError, AttributeError):
            return None
        before, after = self._headers.get(previous), self._headers.get(current)
        if before is None or after is None:
            return None
        forward = after.get('storage') == DELTA_STORAGE and after.get('parent_revision_uuid') == previous
        inverse = before.get('storage') == DELTA_STORAGE and before.get('parent_revision_uuid') == current
        if not forward and not inverse:
            return None
        child, parent = (after, before) if forward else (before, after)
        delta = child['delta']
        if len(delta['added']) + len(delta['removed']) > limit:
            return None
        if child['parent_content_sha256'] != parent['content_sha256']:
            return None
        view = self._member_views.get(current) if inverse and delta['removed'] else None
        if inverse and delta['removed'] and (type(view) is not MemberView or MemberView.get is not _PREPARED_MEMBER_GET):
            return None
        # The same projected existence checks as the cached header path. Do not
        # call header: a cache miss can verify/hydrate an entire ancestor chain,
        # and copying an unrelated predecessor header can exceed this delta bound.
        for identity in (previous, current):
            if not (self.Revision & {'project_uuid': self.project_uuid,
                    'revision_uuid': identity}).proj().to_dicts():
                return None
        if forward:
            return {'added': {row['uuid']: row['metadata_hash'] for row in delta['added']},
                    'removed': list(delta['removed'])}
        added = {}
        for identity in delta['removed']:
            fingerprint = view.get(identity, _MISSING)
            if fingerprint is _MISSING:
                return None
            added[identity] = fingerprint
        return {'added': added, 'removed': [row['uuid'] for row in delta['added']]}

    def members(self, revision_uuid):
        """Shared, read-only exact membership view of a verified revision."""
        revision_uuid = str(uuid.UUID(revision_uuid))
        header = self.header(revision_uuid)
        view = self._member_views.get(revision_uuid)
        if view is None:
            if header.get('storage') == DELTA_STORAGE:
                delta = header['delta']
                view = MemberView(self.members(header['parent_revision_uuid']),
                    {row['uuid']: row['metadata_hash'] for row in delta['added']}, delta['removed'])
            else:
                view = self._root_view(self._verified_recipe(self._row(revision_uuid), revision_uuid)['epochs'])
        self._remember(self._member_views, revision_uuid, view, _MEMBER_LIMIT)
        return view

    def get(self, revision_uuid):
        with elapsed("disco.decisions.explorer", "get"):
            revision_uuid = str(uuid.UUID(revision_uuid))
            row = self._row(revision_uuid)
            recipe = self._verified_recipe(row, revision_uuid)
            if recipe.get('storage') == DELTA_STORAGE:
                # Compatibility: a delta revision reads as its exact full recipe.
                recipe['epochs'] = [dict(uuid=key, metadata_hash=value)
                                    for key, value in sorted(self.members(revision_uuid).items())]
            return {'revision_uuid': revision_uuid, 'recipe': recipe, 'summary': copy.deepcopy(row['summary'])}


# Retain original identities for canonical binding admission, including when a
# custom adapter later replaces methods on the class rather than an instance.
_QUERY_RESULT_BINDING_METHODS = {
    'protocol_binding': ExplorerHistory.protocol_binding,
    'protocol_binding_header': ExplorerHistory.protocol_binding_header,
    'get': ExplorerHistory.get,
}


def is_canonical_binding_reader(provider):
    """Whether this callable retains the unmodified read-only binding path.

    This identifies implementation behavior, not a current binding or recipe
    receipt. Callers must still invoke the reader and validate their live scope.
    """
    owner = getattr(provider, '__self__', None)
    return (type(owner) is ExplorerHistory
        and getattr(provider, '__func__', None) is _QUERY_RESULT_BINDING_METHODS['protocol_binding']
        and all(getattr(getattr(owner, name, None), '__func__', None) is _QUERY_RESULT_BINDING_METHODS[name]
                for name in ('protocol_binding', 'protocol_binding_header', 'get')))

# Any custom verification or membership implementation declines the prepared
# projection. It must use its own explicit preparation/fallback policy.
_PREPARED_DELTA_METHODS = {name: getattr(ExplorerHistory, name) for name in (
    'prepared_delta', 'header', 'members', 'get', '_row', '_verified_recipe', '_root_view')}

_PREPARED_MEMBER_GET = MemberView.get
