"""H5 registration inventory and reversible manager lifecycle, never file deletion.

Freeze locks registration changes. Archive only hides a manager entry;
query exclusion independently controls eligibility for new queries. Neither
changes acquisition data, historical exports, or existing working datasets.
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import uuid

from recording_workspace import workspace_tables
from workspace_audit import build_audit_payload, normalize_event
from workspace_curation import RevisionConflict
from workspace_recipes import verify
from workspace_diff import summarize_diff

SCOPE_NOTE = 'Freeze locks registration changes. Archive changes list visibility only. Exclude from queries independently skips this source in new queries; existing protocol datasets change only through explicit propagation. H5 files, catalog data, tags and historical exports are preserved.'
ACTIONS = {'freeze': 'data_store_frozen', 'unfreeze': 'data_store_unfrozen',
           'archive': 'data_store_archived', 'restore': 'data_store_restored',
           'exclude': 'data_store_query_excluded', 'include': 'data_store_query_included'}


class DataStoreConflict(RevisionConflict):
    def __init__(self, current, message='Data store registration changed; reload before updating its lifecycle.'):
        super().__init__(current)
        self.args = (message,)


def iso(value):
    if isinstance(value, dt.datetime):
        return (value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value.astimezone(dt.timezone.utc)).isoformat()
    return value


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Source identity must be a lowercase SHA256')
    return value


def migrate_query_eligibility(dj, event_table):
    """Crash-resumable schema upgrade preserving legacy archived exclusions.

    DDL is outside the data transaction. NULL marks unfinished backfill, so a
    failed event write rolls back every state change and the next startup can
    retry. Explicit existing eligibility decisions are never overwritten.
    """
    connection = dj.conn()
    table = '`recording_workspace`.`data_store_state`'
    lock = hashlib.sha256(b'recording_workspace:query_eligibility_migration:v1').hexdigest()
    if connection.query(f"SELECT GET_LOCK('{lock}', 10)").fetchone()[0] != 1:
        raise RuntimeError('Another source eligibility schema upgrade is running')
    try:
        columns = connection.query(f"SHOW COLUMNS FROM {table} LIKE 'query_excluded'", as_dict=True).fetchall()
        if not columns:
            connection.query(f'ALTER TABLE {table} ADD COLUMN query_excluded boolean NULL DEFAULT NULL AFTER archived')
        unfinished = connection.query(f'SELECT project_uuid, source_sha256, archived, version FROM {table} WHERE query_excluded IS NULL', as_dict=True).fetchall()
        if unfinished:
            actor = os.environ.get('USER', 'local-user')
            with connection.transaction:
                for row in unfinished:
                    identity = str(uuid.uuid4())
                    excluded = bool(row['archived'])
                    version = int(row['version']) + 1
                    connection.query(f'UPDATE {table} SET query_excluded=%s, version=%s WHERE project_uuid=%s AND source_sha256=%s AND query_excluded IS NULL',
                        args=(int(excluded), version, row['project_uuid'], row['source_sha256']))
                    payload = build_audit_payload('data_store_query_eligibility_migrated', actor, {
                        'source_sha256': row['source_sha256'], 'migration_version': 1,
                        'before': {'version': row['version'], 'archived': excluded, 'query_excluded': None},
                        'after': {'version': version, 'archived': excluded, 'query_excluded': excluded},
                        'reason': 'Preserve legacy archive-based query exclusion while separating list visibility.',
                        'source_files_changed': False, 'catalog_membership_changed': False,
                        'working_dataset_membership_changed': False, 'new_query_eligibility_changed': False},
                        actor_kind='system', operation_uuid=identity, context={'project_uuid': row['project_uuid']})
                    event_table.insert1({'event_uuid': identity, 'project_uuid': row['project_uuid'],
                        'occurred_at': dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                        'actor': actor, 'action': 'data_store_query_eligibility_migrated', 'payload': payload})
        if not columns or columns[0]['Null'] == 'YES':
            connection.query(f'ALTER TABLE {table} MODIFY COLUMN query_excluded boolean NOT NULL DEFAULT 0')
    finally:
        with contextlib.suppress(Exception):
            connection.query(f"SELECT RELEASE_LOCK('{lock}')")


def lifecycle_table(dj, event_table):
    schema = dj.Schema('recording_workspace')

    @schema
    class DataStoreState(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        source_sha256: char(64)
        ---
        version: int unsigned
        frozen: bool
        archived: bool
        query_excluded: bool
        updated_at: datetime
        actor: varchar(255)
        actor_kind: enum('local_user', 'client_claimed')
        server_actor: varchar(255)
        reason: varchar(2000)
        """
    migrate_query_eligibility(dj, event_table)
    return DataStoreState


class DataStores:
    def __init__(self, service, store, explorer_history, *, state_table=None, source_table=None, event_table=None):
        self.service, self.store, self.explorer_history = service, store, explorer_history
        self.dj, self.project_uuid = service.dj, service.project['project_uuid']
        if source_table is None or event_table is None:
            _, Source, Event, _ = workspace_tables(self.dj)
            source_table = Source if source_table is None else source_table
            event_table = Event if event_table is None else event_table
        self.Source, self.Event = source_table, event_table
        self.State = lifecycle_table(self.dj, self.Event) if state_table is None else state_table
        self._revision_members = {}
        self._snapshot_members = {}

    def _source(self, identity):
        identity = sha(identity)
        if not (self.Source & {'project_uuid': self.project_uuid, 'source_sha256': identity}).to_dicts():
            raise KeyError('Data store not registered in this project')
        source = next((item for item in self.service.sources if item['source_sha256'] == identity), None)
        if source is None:
            raise ValueError('Data store is not in the validated read model; refresh the project')
        return source

    @staticmethod
    def _state(row=None):
        if row is None:
            return {'version': 0, 'frozen': False, 'archived': False, 'query_excluded': False, 'updated_at': None,
                    'actor': None, 'actor_kind': None, 'server_actor': None, 'reason': None}
        return {'version': int(row['version']), 'frozen': bool(row['frozen']), 'archived': bool(row['archived']),
                'query_excluded': bool(row.get('query_excluded', row['archived'])),
                'updated_at': iso(row['updated_at']), 'actor': row['actor'], 'actor_kind': row.get('actor_kind', 'client_claimed'),
                'server_actor': row['server_actor'], 'reason': row['reason']}

    def source_states(self):
        """Read current project state in one query; default registrations stay unwritten."""
        stored = {row['source_sha256']: self._state(row) for row in
                  (self.State & {'project_uuid': self.project_uuid}).to_dicts()}
        return {source['source_sha256']: stored.get(source['source_sha256'], self._state())
                for source in self.service.sources}

    @contextlib.contextmanager
    def registration_locks(self, identities=None):
        """Serialize query eligibility before taking any protocol-specific locks.

        Project-wide because a restoration/import can affect every predicate.
        MySQL advisory locks are reentrant on the same connection; callers may
        wrap transition or compound candidate/binding operations with this lock.
        """
        if identities is not None:
            for identity in identities:
                self._source(identity)
        connection = self.dj.conn()
        lock = hashlib.sha256(('source-eligibility:' + self.project_uuid).encode()).hexdigest()
        if connection.query(f"SELECT GET_LOCK('{lock}', 10)").fetchone()[0] != 1:
            raise RuntimeError('Another source eligibility operation is running')
        try:
            yield
        finally:
            with contextlib.suppress(Exception):
                connection.query(f"SELECT RELEASE_LOCK('{lock}')")

    def propagation_preview(self, identity=None):
        """Rerun saved queries against eligible sources without changing any working set."""
        if identity is not None:
            self._source(identity)
        items = []
        source_ids = {key for key, row in self.service.rows.items()
                      if identity is None or row['source_sha256'] == identity}
        for protocol_uuid, workspace in self.service.protocols.items():
            view_adaptation = None
            binding = self.service.binding(protocol_uuid)
            if binding:
                recipe = binding['recipe']
                predicate, splits = recipe['predicate'], recipe['splits']
                previous = {row['uuid']: row['metadata_hash'] for row in recipe['epochs']}
            else:
                definition = workspace['definition']
                clauses = definition['query'].get('all', [])
                if len(clauses) != 1 or clauses[0].get('field') != 'EpochBlock.protocol_name' or clauses[0].get('operator') != 'eq':
                    raise ValueError('Unsupported starter query for propagation')
                predicate = {'field': 'protocol', 'operator': 'eq', 'value': clauses[0]['value']}
                grouping = definition.get('view', {}).get('group_by', ['date', 'cell'])
                supported = {field['id'] for field in self.service.tree_fields(None)['fields']}
                # Legacy MATLAB paths (e.g. cell.start_time) are not UI field
                # identities. Use an explicit canonical initial view; the
                # original starter definition remains intact and inspectable.
                splits = ','.join(grouping) if all(field in supported for field in grouping) else 'date,cell,block'
                if any(field not in supported for field in grouping):
                    view_adaptation = {'original_group_by': list(grouping),
                        'applied_group_by': ['date', 'cell', 'block'],
                        'reason': 'Legacy tree paths are not current UI field identities; using the initial date/cell/block view.'}
                previous = self.service.fingerprints(protocol_uuid)
            preview = self.service.explore_preview(predicate, splits)
            proposed = {row['uuid']: row['metadata_hash'] for row in preview['membership']}
            # A restored source may have no CURRENT links but add new members.
            if identity is not None and not source_ids & (previous.keys() | proposed.keys()):
                continue
            diff = {'added': sorted(proposed.keys() - previous.keys()),
                    'removed': sorted(previous.keys() - proposed.keys()),
                    'changed': sorted(key for key in previous.keys() & proposed.keys() if previous[key] != proposed[key])}
            items.append({'protocol_uuid': protocol_uuid, 'name': workspace['definition']['name'],
                'predicate': predicate, 'splits': splits, 'binding_version': binding['version'] if binding else 0,
                'current_revision_uuid': binding['revision_uuid'] if binding else None, 'view_adaptation': view_adaptation,
                'diff': diff, 'diff_summary': summarize_diff(self.service.rows, previous, proposed),
                'previous_count': len(previous), 'next_count': len(proposed),
                'matched_count': preview['matched_count'], 'total_source': preview['total_source'], 'preview': preview})
        return {'source_sha256': identity, 'source_scope': self.service.source_scope(), 'protocols': items}

    @staticmethod
    def _quantities(rows):
        durations = [row.get('duration_seconds') for row in rows]
        return {'duration_seconds': sum(durations) if all(value is not None for value in durations) else None,
                'blocks': len({row['block_uuid'] for row in rows}),
                'groups': len({row['group_uuid'] for row in rows}),
                'responses': sum(stream.get('kind') == 'responses' for row in rows for stream in row.get('streams', [])),
                'stimuli': sum(stream.get('kind') == 'stimuli' for row in rows for stream in row.get('streams', []))}

    def _import_times(self):
        relation = self.Event & {'project_uuid': self.project_uuid, 'action': 'imported'}
        headers = relation.proj('occurred_at').to_dicts()
        signature = tuple(sorted((row['event_uuid'], str(row['occurred_at'])) for row in headers))
        if getattr(self, '_import_signature', None) != signature:
            times = {}
            for row in relation.to_dicts() if headers else []:
                payload = row.get('payload') or {}
                identity = payload.get('source_sha256') if isinstance(payload, dict) else None
                if identity:
                    when = iso(row['occurred_at'])
                    times[identity] = min(times.get(identity, when), when)
            self._imports, self._import_signature = times, signature
        return self._imports

    def inventory(self, detail_source=None):
        sources = self.service.sources if detail_source is None else [self._source(detail_source)]
        source_rows = {source['source_sha256']: [] for source in sources}
        for row in self.service.rows.values():
            if row['source_sha256'] in source_rows:
                source_rows[row['source_sha256']].append(row)
        states = {row['source_sha256']: row for row in
                  (self.State & {'project_uuid': self.project_uuid}).to_dicts()}
        imports = self._import_times()
        protocol_members = []
        if detail_source is not None:
            for identity, workspace in self.service.protocols.items():
                query = self.service.query_result(identity)
                protocol_members.append(({'protocol_uuid': identity, 'name': workspace['definition']['name'],
                    'working_dataset_version': query.get('dataset_binding', {}).get('version', 0)},
                    {row['uuid'] for row in query['epochs']}))
        exported = self.store.export_memberships() if detail_source is not None else {}
        results = []
        for source in sources:
            identity = source['source_sha256']
            rows = source_rows[identity]
            ids = {row['epoch_uuid'] for row in rows}
            manifest = self.service.manifests.get(identity, {})
            protocols = [{**details, 'epoch_count': len(ids & members)} for details, members in protocol_members if ids & members]
            exports = {}
            for key in ids:
                for link in exported.get(key, []):
                    result = exports.setdefault(link['dataset_uuid'], {k: link[k] for k in
                        ('dataset_uuid', 'name', 'protocol_uuid', 'created_at', 'artifact_sha256')})
                    result['epoch_count'] = result.get('epoch_count', 0) + 1
                    result['download_url'] = '/api/exports/' + link['dataset_uuid'] + '/download'
            acquisition, cell_types = {}, {}
            for row in rows:
                acquisition.setdefault(row['protocol_name'], []).append(row)
                cell_types.setdefault(row.get('cell_type') or 'Not recorded', []).append(row)
            path = Path(source['source_path'])
            checked_at = dt.datetime.now(dt.timezone.utc).isoformat()
            file_status, size, modified = 'available', None, None
            try:
                stat = path.stat()
                if not path.is_file():
                    file_status = 'missing'
                else:
                    size = stat.st_size
                    modified = dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc).isoformat()
                    if manifest.get('source_size') is not None and size != manifest['source_size']:
                        file_status = 'changed'
            except FileNotFoundError:
                file_status = 'missing'
            except OSError:
                file_status = 'unreadable'
            imported_at = imports.get(identity) or manifest.get('imported_at')
            results.append({'source_sha256': identity, 'filename': source.get('filename', path.name),
                'source_path': str(path), 'file_status': file_status, 'size_bytes': size,
                'checked_at': checked_at, 'check_kind': 'filesystem_availability_and_size',
                'recorded_size_bytes': manifest.get('source_size'), 'modified_at': modified,
                'imported_at': imported_at, 'validated_at': manifest.get('validated_at'),
                'import_time_basis': 'recorded_import' if imported_at else 'not_recorded',
                'recording_dates': sorted({row['date'] for row in rows if row.get('date')}),
                'counts': {**self._quantities(rows), 'cell_types': len(cell_types), 'cells': len({row['cell_uuid'] for row in rows}), 'epochs': len(rows),
                           'acquisition_protocols': len(acquisition), 'protocol_workspaces': len(protocols) if detail_source is not None else None, 'exports': len(exports) if detail_source is not None else None},
                'cell_types': [{'name': name, 'cells': len({row['cell_uuid'] for row in items}), 'epochs': len(items),
                    'duration_seconds': self._quantities(items)['duration_seconds']}
                    for name, items in sorted(cell_types.items())],
                'acquisition_protocols': [{'name': name, **self._quantities(items), 'epoch_count': len(items),
                    'cells': len({item['cell_uuid'] for item in items})} for name, items in sorted(acquisition.items())],
                'protocols': protocols, 'exports': list(exports.values()), 'connections_loaded': detail_source is not None,
                'parser': {key: manifest[key] for key in ('parser_path', 'parser_sha256', 'parser_version',
                    'adapter_version', 'adapter_sha256', 'metadata_sha256', 'status', 'warnings') if key in manifest} if detail_source is not None else None,
                'state': self._state(states.get(identity)), 'scope_note': SCOPE_NOTE})
        return {'data_stores': results, 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'counts': {'total': len(results),
            'active': sum(not row['state']['archived'] for row in results),
            'archived': sum(row['state']['archived'] for row in results),
            'frozen': sum(row['state']['frozen'] for row in results),
            'query_excluded': sum(row['state']['query_excluded'] for row in results)}}

    def detail(self, identity):
        return self.inventory(detail_source=identity)['data_stores'][0]

    def transition(self, identity, action, expected_version, actor=None, reason=""):
        self._source(identity)
        if not isinstance(action, str) or action not in ACTIONS:
            raise ValueError('Use freeze, unfreeze, archive, restore, exclude, or include')
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError('Expected version must be a nonnegative integer')
        server_actor = os.environ.get('USER', 'local-user')
        actor_kind = 'local_user' if actor is None else 'client_claimed'
        actor = server_actor if actor is None else actor
        if not isinstance(actor, str) or not actor.strip() or len(actor) > 255:
            raise ValueError('An actor label of 1–255 characters is required')
        if not isinstance(reason, str) or len(reason) > 2000:
            raise ValueError('Reason must be text up to 2000 characters')
        connection = self.dj.conn()
        with self.registration_locks([identity]):
            with connection.transaction:
                self._source(identity)
                stored = (self.State & {'project_uuid': self.project_uuid, 'source_sha256': identity}).to_dicts()
                before = self._state(stored[0] if stored else None)
                if before['version'] != expected_version:
                    raise DataStoreConflict(before)
                if (action == 'freeze' and before['frozen'] or action == 'unfreeze' and not before['frozen']
                        or action == 'archive' and before['archived'] or action == 'restore' and not before['archived']
                        or action == 'exclude' and before['query_excluded'] or action == 'include' and not before['query_excluded']):
                    raise DataStoreConflict(before)
                if action in {'archive', 'restore', 'exclude', 'include'} and before['frozen']:
                    raise DataStoreConflict(before, 'Unfreeze this data store registration before changing visibility or query eligibility.')
                after = {**before, 'version': before['version'] + 1,
                    'frozen': action == 'freeze' if action in {'freeze', 'unfreeze'} else before['frozen'],
                    'archived': action == 'archive' if action in {'archive', 'restore'} else before['archived'],
                    'query_excluded': action == 'exclude' if action in {'exclude', 'include'} else before['query_excluded'],
                    'updated_at': dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                    'actor': actor.strip(), 'actor_kind': actor_kind, 'server_actor': server_actor, 'reason': reason.strip()}
                row = {'project_uuid': self.project_uuid, 'source_sha256': identity,
                       **after}
                if stored:
                    self.State.update1(row)
                else:
                    self.State.insert1(row)
                event_uuid = str(uuid.uuid4())
                payload = build_audit_payload(ACTIONS[action], actor.strip(), {
                    'source_sha256': identity, 'before': before, 'after': self._state(row), 'reason': reason.strip(),
                    'scope': 'registration_lifecycle_only', 'source_files_changed': False,
                    'catalog_membership_changed': False, 'working_dataset_membership_changed': False,
                    'new_query_eligibility_changed': before['query_excluded'] != after['query_excluded'], 'server_actor': server_actor},
                    actor_kind=actor_kind, operation_uuid=event_uuid,
                    context={'project_uuid': self.project_uuid})
                self.Event.insert1({'event_uuid': event_uuid, 'project_uuid': self.project_uuid,
                    'occurred_at': row['updated_at'], 'actor': server_actor, 'action': ACTIONS[action], 'payload': payload})
        return {'source_sha256': identity, 'state': self._state(row), 'event_uuid': event_uuid}

    def _activity_index(self):
        relation = self.Event & {'project_uuid': self.project_uuid}
        headers = relation.proj('occurred_at', 'action').to_dicts()
        owner = {key: row['source_sha256'] for key, row in self.service.rows.items()}
        signature = (tuple(sorted((row['event_uuid'], str(row['occurred_at']), row['action']) for row in headers)),
                     tuple(sorted(owner.items())))
        if getattr(self, '_activity_signature', None) == signature:
            return self._activities
        cache = getattr(self, '_event_payloads', {})
        cached_headers = getattr(self, '_event_headers', {})
        summaries = getattr(self, '_event_summaries', {})
        current_headers = {row['event_uuid']: (str(row['occurred_at']), row['action']) for row in headers}
        changed = [identity for identity, header in current_headers.items() if cached_headers.get(identity) != header]
        for start in range(0, len(changed), 200):
            for event in (relation & [{'event_uuid': identity} for identity in changed[start:start + 200]]).to_dicts():
                identity = event['event_uuid']
                compact = normalize_event(event)
                compact.pop('payload', None); compact.pop('provenance', None)
                summaries[identity] = compact
                payload = event.get('payload') or {}
                # Full audit/provenance remains available through /events/:id.
                # Keep only the exact identity evidence needed for source links.
                proof = {key: payload[key] for key in ('source_sha256', 'dataset_uuid', 'revision_uuid',
                         'protocol_uuid', 'snapshot_uuid', 'diff') if key in payload} if isinstance(payload, dict) else {}
                for side in ('before', 'after'):
                    if isinstance(payload, dict) and isinstance(payload.get(side), dict):
                        proof[side] = dict.fromkeys(payload[side])
                cache[identity] = {**{key: value for key, value in event.items() if key != 'payload'}, 'payload': proof}
        self._event_payloads = cache = {key: cache[key] for key in current_headers if key in cache}
        self._event_headers, self._event_summaries = current_headers, summaries
        exported = self.store.export_memberships()
        dataset_members = {}
        for key, links in exported.items():
            for link in links:
                dataset_members.setdefault(link['dataset_uuid'], set()).add(key)
        activities = {source['source_sha256']: [] for source in self.service.sources}
        unresolved = 0
        for event in cache.values():
            payload = event.get('payload') or {}
            if not isinstance(payload, dict):
                continue
            linked = {}
            direct = payload.get('source_sha256')
            if isinstance(direct, str) and direct in activities:
                linked[direct] = {'basis': {'source_identity'}, 'epochs': set()}
            def add_members(identities, basis):
                for key in identities:
                    source = owner.get(key)
                    if source in activities:
                        item = linked.setdefault(source, {'basis': set(), 'epochs': set()})
                        item['basis'].add(basis); item['epochs'].add(key)
            if event['action'] == 'curation_updated':
                for side in ('before', 'after'):
                    if isinstance(payload.get(side), dict):
                        add_members(payload[side], 'curation_epochs')
            if event['action'] == 'dataset_revision_exported':
                if payload.get('dataset_uuid') not in dataset_members:
                    unresolved += 1
                add_members(dataset_members.get(payload.get('dataset_uuid'), ()), 'export_membership')
            if event['action'] in {'explorer_revision_created', 'protocol_dataset_bound'}:
                revision = payload.get('revision_uuid')
                if revision:
                    if revision not in self._revision_members:
                        try:
                            recipe = self.explorer_history.get(revision)['recipe']
                            self._revision_members[revision] = [row['uuid'] for row in recipe['epochs']]
                        except KeyError:
                            unresolved += 1
                    add_members(self._revision_members.get(revision, []), 'selected_query_membership')
                delta = payload.get('diff', {})
                if event['action'] == 'protocol_dataset_bound' and isinstance(delta, dict):
                    for kind in ('added', 'removed', 'changed'):
                        add_members(delta.get(kind, []), 'working_dataset_diff')
            if event['action'] == 'query_refreshed' and payload.get('snapshot_uuid'):
                try:
                    protocol = str(uuid.UUID(payload['protocol_uuid']))
                    snapshot = str(uuid.UUID(payload['snapshot_uuid']))
                    if snapshot not in self._snapshot_members:
                        path = self.service.project_dir / 'query-snapshots' / protocol / (snapshot + '.json')
                        recipe = verify(json.loads(path.read_text()))
                        if recipe['project_uuid'] != self.project_uuid:
                            raise ValueError('Snapshot project differs')
                        self._snapshot_members[snapshot] = [row['uuid'] for row in recipe['epochs']]
                    add_members(self._snapshot_members[snapshot], 'selected_query_membership')
                except (KeyError, FileNotFoundError):
                    unresolved += 1  # Missing proof is never guessed from broad source_revisions.
            for source, proof in linked.items():
                normalized = dict(summaries[event['event_uuid']])
                normalized['source_link'] = {'basis': sorted(proof['basis']),
                    'affected_epoch_count': len(proof['epochs']) if proof['epochs'] else None}
                normalized['detail_url'] = '/api/events/' + event['event_uuid']
                activities[source].append(normalized)
        for rows in activities.values():
            rows.sort(key=lambda row: (row['occurred_at'], row['event_uuid']), reverse=True)
        self._activities, self._activity_signature = activities, signature if not unresolved else None
        self._unresolved_references = unresolved
        return activities

    def events(self, identity, limit=50, offset=0):
        self._source(identity)
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise ValueError('Source event page requires limit 1–100 and nonnegative offset')
        rows = self._activity_index()[identity]
        return {'events': copy.deepcopy(rows[offset:offset + limit]), 'limit': limit, 'offset': offset,
                'has_more': len(rows) > offset + limit,
                'attribution': {'basis': 'exact_source_identity_or_selected_epoch_membership',
                                'unresolved_project_history_references': self._unresolved_references}}
