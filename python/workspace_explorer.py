"""Immutable applied source-query/tree revisions with transactional audit."""
from __future__ import annotations

import copy
import contextlib
import hashlib
import datetime as dt
import uuid

from recording_workspace import now, workspace_tables
from workspace_audit import build_audit_payload
from workspace_recipes import checksum, member_map

ACTION = 'explorer_revision_created'


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
    def __init__(self, dj, project_uuid, *, event_table=None, revision_table=None, binding_table=None):
        self.dj = dj
        self.project_uuid = str(uuid.UUID(project_uuid))
        self.Event = workspace_tables(dj)[2] if event_table is None else event_table
        self.Revision = explorer_table(dj) if revision_table is None else revision_table
        self.Binding = protocol_binding_table(dj) if binding_table is None else binding_table
        self._recipe_cache = {}

    def protocol_binding_header(self, protocol_uuid):
        """Read the current binding version without hydrating its frozen recipe."""
        protocol_uuid = str(uuid.UUID(protocol_uuid))
        rows = (self.Binding & {'project_uuid': self.project_uuid, 'protocol_uuid': protocol_uuid}).to_dicts()
        return rows[0] if rows else None

    def protocol_binding(self, protocol_uuid):
        row = self.protocol_binding_header(protocol_uuid)
        if row is None:
            return None
        identity = row['revision_uuid']
        if identity not in self._recipe_cache:
            self._recipe_cache[identity] = self.get(identity)['recipe']
        return {**row, 'recipe': copy.deepcopy(self._recipe_cache[identity])}

    def bind(self, revision_uuid, protocol_uuid, expected_version, actor, diff, previous_count,
             *, expected_query_revision=None, current_query_revision=None, diff_summary=None,
             _in_transaction=False, _lock_held=False, reason=None):
        protocol_uuid = str(uuid.UUID(protocol_uuid))
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError('Expected binding version must be a nonnegative integer')
        record = self.get(revision_uuid)
        connection = self.dj.conn()
        lock = hashlib.sha256((self.project_uuid + protocol_uuid).encode()).hexdigest()
        if not _lock_held and connection.query(f"SELECT GET_LOCK('{lock}', 10)").fetchone()[0] != 1:
            raise RuntimeError('Another protocol dataset update is running')
        try:
            with (contextlib.nullcontext() if _in_transaction else connection.transaction):
                previous = self.protocol_binding(protocol_uuid)
                version = previous['version'] if previous else 0
                from workspace_curation import RevisionConflict
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
                event_uuid = str(uuid.uuid4())
                payload = build_audit_payload('protocol_dataset_bound', actor, {
                    'protocol_uuid': protocol_uuid, 'revision_uuid': record['revision_uuid'],
                    'binding_version': row['version'], 'previous_revision_uuid': previous['revision_uuid'] if previous else None,
                    'previous_count': previous_count, 'epoch_count': len(record['recipe']['epochs']),
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
                  'predicate_version': 1, 'predicate': copy.deepcopy(preview['predicate']),
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
        recipe['content_sha256'] = checksum(recipe)
        # Keep the validated exact recipe separate from audit's human-readable
        # redaction pass; predicate literals must survive a restore unchanged.
        audit['recipe_sha256'] = recipe['content_sha256']
        occurred = dt.datetime.fromisoformat(timestamp).astimezone(dt.timezone.utc).replace(tzinfo=None)
        with (contextlib.nullcontext() if _in_transaction else self.dj.conn().transaction):
            self.Revision.insert1({'project_uuid': self.project_uuid, 'revision_uuid': identity,
                'created_at': occurred, 'name': summary['name'], 'parent_revision_uuid': parent_revision_uuid,
                'summary': summary, 'recipe': recipe})
            self.Event.insert1({'event_uuid': identity, 'project_uuid': self.project_uuid,
                'occurred_at': occurred, 'actor': actor, 'action': ACTION, 'payload': audit})
        return {'revision_uuid': identity, 'recipe': recipe, 'summary': summary}

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

    def get(self, revision_uuid):
        revision_uuid = str(uuid.UUID(revision_uuid))
        rows = (self.Revision & {'project_uuid': self.project_uuid, 'revision_uuid': revision_uuid}).to_dicts()
        if not rows:
            raise KeyError('Explorer revision not found in this project')
        row = rows[0]
        recipe = copy.deepcopy(row['recipe'])
        expected = recipe.pop('content_sha256', None)
        if (expected != checksum(recipe) or recipe.get('format') != 'recording-explorer-revision'
                or recipe.get('version') != 1 or recipe.get('project_uuid') != self.project_uuid
                or recipe.get('revision_uuid') != revision_uuid
                or any(recipe.get(key) != value for key, value in row['summary'].items())):
            raise ValueError('Stored explorer revision failed integrity verification')
        recipe['content_sha256'] = expected
        return {'revision_uuid': revision_uuid, 'recipe': recipe, 'summary': copy.deepcopy(row['summary'])}
