"""Owned benchmark publication and SQL-leaf authority adapters.

Production generation/capture algorithms run unchanged. Only schema attestation,
SQL rows, transactional triggers, and source fixtures are doubles. These adapters
are not native-MySQL qualification and never attach to a scientific project.
"""
from __future__ import annotations
import contextlib
import copy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import uuid
from unittest.mock import patch


def journal_transactions(fixture):
    """Journal only changed double rows; never copy an entire frozen recipe."""
    from test_workspace_curation import Table, Connection
    state = {'depth': [0], 'undo': None}
    lock = threading.RLock()
    def install(name, function):
        context = patch.object(Table, name, function)
        context.start(); fixture.addCleanup(context.stop)
    original_insert, original_update, original_batch = Table.insert1, Table.update1, Table.insert
    def insert1(self, row):
        result = original_insert(self, row)
        if state['undo'] is not None:
            state['undo'].append(lambda: self.rows.pop())
        return result
    def update1(self, row):
        target = next((item for item in self.rows if all(item[key] == row[key] for key in self.keys)), None)
        before = dict(target) if target is not None else None
        result = original_update(self, row)
        if state['undo'] is not None and target is not None:
            state['undo'].append(lambda: (target.clear(), target.update(before)))
        return result
    def insert(self, rows, replace=False):
        rows = list(rows)
        keys = {tuple(row[key] for key in self.keys) for row in rows}
        prior = [(item, dict(item)) for item in self.rows if tuple(item[key] for key in self.keys) in keys]
        length = len(self.rows)
        result = original_batch(self, rows, replace=replace)
        if state['undo'] is not None:
            def undo():
                del self.rows[length:]
                for item, before in prior:
                    item.clear(); item.update(before)
            state['undo'].append(undo)
        return result
    install('insert1', insert1); install('update1', update1); install('insert', insert)
    @property
    @contextlib.contextmanager
    def transaction(self):
        with lock:
            outer = state['undo'] is None
            if outer:state['undo'] = []
            mark = len(state['undo'])
            state['depth'][0] += 1
            try:
                yield
            except BaseException:
                while len(state['undo']) > mark:
                    state['undo'].pop()()
                raise
            finally:
                state['depth'][0] -= 1
                if outer:state['undo'] = None
    context = patch.object(Connection, 'transaction', transaction)
    context.start(); fixture.addCleanup(context.stop)
    return state


def install_authority(fixture, app, journal, *, install_state=False):
    """Install real recovery capture over a transactional fixed-slot SQL double."""
    from disco.backup.recovery_generation import RecoveryGenerationAuthority, CLOCK, FEED, RECOVERY_WINDOW, TABLE_IDS
    from workspace_state_generation import StateGenerationAuthority
    from test_workspace_curation import Table
    case, service = fixture.case, fixture.case.service
    project = service.project['project_uuid']
    shared = app.extensions.get('shared_annotations')
    presets = app.extensions.get('search_presets')
    tables = {name: getattr(case, attribute, None) for name, attribute in (
        ('curation', 'curation'), ('dataset_revision', 'datasets'), ('source', 'sources'),
        ('protocol_binding', 'protocol_bindings'), ('explorer_revision', 'explorer_revisions'),
        ('data_store_state', 'data_store_states'), ('protocol_tree_layout', 'layout_rows'),
        ('protocol_suggestion', 'suggestion_rows'), ('annotation_group_receipt', 'group_receipts'))}
    tables.update(zip(('workbench_draft', 'workbench_decision', 'workbench_receipt'), case.workbench_tables))
    if shared is not None:
        tables.update(annotation_profile=shared.Profile, shared_annotation=shared.Annotation)
    if presets is not None:
        tables.update(search_preset=presets.Table, search_preset_version=presets.Version, search_query_last_run=presets.Runs)
    membership = getattr(case.explorer_history, '_membership', None)
    if membership is not None and hasattr(membership, 'rows'):
        tables['protocol_membership'] = membership
    tables = {name: table for name, table in tables.items() if table is not None and hasattr(table, 'rows')}
    watched = {id(table.rows): (name, tuple(table.keys)) for name, table in tables.items()}
    state = {'generation': 0, 'scope_epoch': str(uuid.uuid4()), 'feed': {},
             'state_epochs': {}, 'state_generations': {}, 'annotation_changes': {},
             'sql_reads': 0, 'attestations': 0, 'capture_transactions': 0}
    authority = {'fixture': 'owned-recovery-sql-leaf-v1', 'project_uuid': project}
    class Connection:
        _conn = SimpleNamespace(_sock=object())
        @property
        def in_transaction(self):return journal['depth'][0] > 0
        @property
        @contextlib.contextmanager
        def transaction(self):
            state['capture_transactions'] += 1
            with case.connection.transaction:
                yield
        def query(self, sql, args=(), as_dict=True, reconnect=False):
            state['sql_reads'] += 1
            if CLOCK in sql and sql.startswith('SELECT'):
                rows = [{'scope_epoch': state['scope_epoch'], 'generation': state['generation'],
                         'retained_after': max(0, state['generation'] - RECOVERY_WINDOW)}]
            elif FEED in sql and 'table_id,key_bytes' in sql:
                after, limit = args[1:]
                rows = sorted((dict(row) for row in state['feed'].values() if row['generation'] > after),
                              key=lambda row: row['generation'])[:limit]
            elif 'scope_epoch,generation' in sql and sql.startswith('SELECT'):
                key = tuple(args[1:3])
                rows = [{'scope_epoch': state['state_epochs'].setdefault(key, str(uuid.uuid4())),
                         'generation': state['state_generations'].get(key, 0)}]
            elif 'app_annotation_changes' in sql and 'last_generation>' in sql:
                after, limit = args[1:]
                rows = sorted(({'target_kind': kind, 'target_uuid': target, 'profile_uuid': profile,
                                'last_generation': generation, 'deleted': deleted}
                               for (kind, target, profile), (generation, deleted) in state['annotation_changes'].items()
                               if generation > after), key=lambda row: row['last_generation'])[:limit]
            elif sql.startswith(('SET TRANSACTION ', 'SELECT 1 FROM ', 'INSERT INTO ')):
                rows = []
            else:
                raise AssertionError('Unimplemented owned authority SQL: ' + sql)
            return SimpleNamespace(fetchall=lambda: rows)
    connection = Connection()
    tracker = RecoveryGenerationAuthority(connection, project)
    tracker.ready, tracker.reason = True, None
    tracker.specs = {name: {'primary_keys': list(table.keys),
                            'columns': sorted(set(table.keys).union(*(set(row) for row in table.rows))),
                            'json_columns': []} for name, table in tables.items()}
    def attest():
        state['attestations'] += 1
        return dict(authority)
    tracker._contract = attest  # Same explicit schema-attestation seam as route StateGenerationAuthority.
    service._recovery_tracker = tracker
    app.extensions['benchmark_recovery_authority'] = state
    if install_state:
        generations = StateGenerationAuthority(connection, project)
        generations.ready, generations.reason = True, None
        generations._attest_contract = lambda: 'owned-generation-sql-leaf-v1'
        case.store.state_generation = generations
        if shared is not None:shared.state_generation = generations
        service._explore_state_generation = generations
        app.extensions['state_generation'] = generations

    def trigger(table, row, deleted=False):
        identity = watched.get(id(table.rows))
        if identity is None or row.get('project_uuid') != project:
            return
        name, keys = identity
        before = state['generation']; generation = before + 1
        slot = generation % RECOVERY_WINDOW
        old = state['feed'].get(slot)
        state['generation'] = generation
        state['feed'][slot] = {'table_id': TABLE_IDS[name], 'key_bytes': json.dumps([row[key] for key in keys]),
                               'generation': generation, 'deleted': int(deleted)}
        if journal['undo'] is not None:
            def undo():
                state['generation'] = before
                if old is None:state['feed'].pop(slot, None)
                else:state['feed'][slot] = old
            journal['undo'].append(undo)
        if not install_state:
            return
        scope = (('protocol_curation', row['protocol_uuid']) if name == 'curation' else
                 ('shared_annotations', project) if name in ('annotation_profile', 'shared_annotation') else None)
        if scope is None:return
        previous = state['state_generations'].get(scope, 0)
        state['state_generations'][scope] = previous + 1
        change = ((row['target_kind'], row['target_uuid'], row['profile_uuid']) if name == 'shared_annotation' else
                  ('profile', row['profile_uuid'], row['profile_uuid']) if name == 'annotation_profile' else None)
        prior_change = state['annotation_changes'].get(change) if change else None
        if change:state['annotation_changes'][change] = (previous + 1, int(deleted))
        if journal['undo'] is not None:
            def undo_state():
                state['state_generations'][scope] = previous
                if change:
                    if prior_change is None:state['annotation_changes'].pop(change, None)
                    else:state['annotation_changes'][change] = prior_change
            journal['undo'].append(undo_state)
    for method in ('insert1', 'update1', 'insert'):
        original = getattr(Table, method)
        def write(self, supplied, *args, _original=original, _method=method, **kwargs):
            rows = list(supplied) if _method == 'insert' else [supplied]
            old = {}
            if _method == 'update1' or kwargs.get('replace', False) or (args and args[0]):
                wanted = {tuple(row[key] for key in self.keys) for row in rows}
                old = {tuple(row[key] for key in self.keys): dict(row) for row in self.rows
                       if tuple(row[key] for key in self.keys) in wanted}
            result = _original(self, rows if _method == 'insert' else supplied, *args, **kwargs)
            for row in rows:
                previous = old.get(tuple(row[key] for key in self.keys))
                if previous is not None:trigger(self, previous, True)
                trigger(self, {**(previous or {}), **row})
            return result
        context = patch.object(Table, method, write)
        context.start(); fixture.addCleanup(context.stop)
    return tracker


def close_typed_publication(service):
    owner = getattr(service, 'typed_index', None)
    if owner is not None:
        owner.reader.close()
        owner.lease.close()
        service.typed_index = None


def close_summary_jobs(service):
    jobs = getattr(service, '_summary_jobs', None)
    if jobs is None:return
    for identity in list(jobs.jobs):jobs.cancel(identity)
    worker = jobs.worker
    if worker is not None:
        worker.join(timeout=60)
        if worker.is_alive():raise RuntimeError('Owned summary worker did not stop')


def prepare_views(app):
    """Named explicit preparation, before requests; retain each owner's timing."""
    import psutil
    process = psutil.Process()
    receipts = {}
    for name in ('tree', 'overview'):
        prepare = app.extensions.get('prepare_' + name + '_publication')
        if prepare is None:continue
        before = process.memory_info().rss
        started = time.perf_counter()
        receipt = prepare()
        receipts[name] = {**receipt, 'elapsed_seconds': time.perf_counter() - started,
                          'rss_before_bytes': before, 'rss_after_bytes': process.memory_info().rss}
        if receipt.get('status') != 'ready':
            raise AssertionError('Owned native publication did not prepare: ' + repr(receipts))
    return receipts


def publish_browser_fixture(fixture, app, output, journal):
    """Promote only this owned fixture to the production immutable/native reader."""
    from disco.metadata.disk_index import DiskMetadataIndex
    from disco.metadata.typed_lifecycle import prepare as prepare_typed
    from workspace_service import WorkspaceService, publish_frozen
    from disco.navigation.tag_predicates import prepare_publication
    case, service = fixture.case, fixture.case.service
    sources = {row['source_sha256'] for row in service.rows.values()}
    known = {source['source_sha256']: source for source in service.sources}
    registered = [known.get(key, {'source_sha256': key, 'source_path': str(output / 'never-open.h5'),
                                'filename': 'never-open.h5'}) for key in sorted(sources)]
    index = DiskMetadataIndex.build(output / 'publication-index.sqlite', service.rows, service.details,
                                    registered, 'workflow-owned-native-v1', service.project['project_uuid'])
    fixture.addCleanup(index.close)
    service.disk_index, service.details = index, index.details
    service.typed_index, typed = prepare_typed(index, None)
    if service.typed_index is not None:fixture.addCleanup(close_typed_publication, service)
    service.__class__ = WorkspaceService
    service.refresh = lambda: {'epochs': len(service.rows)}
    service.events = lambda limit=100: []
    for name in ('rows', 'cells', 'protocols', '_fingerprints'):
        setattr(service, name, publish_frozen(getattr(service, name), rows=name == 'rows'))
    service._explore_publication = str(uuid.uuid4())
    service._tree_page_scope_cache = None
    service._tree_catalog_cache = {}
    for name in ('_registered_tree_cache', '_registered_predicate_cache', '_predicate_catalog_cache'):
        setattr(service, name, None)
    prepare_publication(service)
    install_authority(fixture, app, journal, install_state=True)
    shared = app.extensions.get('shared_annotations')
    if shared is not None:
        original = shared._index_records
        def records(keys):
            if keys is not None:
                yield from original(keys)
            else:
                for kind in ('cell', 'epoch'):
                    yield from sorted((row for row in shared.Annotation.to_dicts()
                                       if row['project_uuid'] == service.project['project_uuid'] and row['target_kind'] == kind),
                                      key=lambda row: (row['target_uuid'], row['profile_uuid']))
        shared._index_records = records
    fixture.addCleanup(close_summary_jobs, service)
    for name in ('tree', 'overview'):
        close = app.extensions.get('close_' + name + '_publication')
        if close is not None:fixture.addCleanup(close)
    navigation = app.extensions.get('disco.navigation.prepared')
    if navigation is not None:fixture.addCleanup(navigation.close)
    return {'authority': 'production owners over transactional SQL leaf doubles',
            'native_sql_qualification': False, 'native_metadata_index': True, 'typed_index': typed,
            'preparation': prepare_views(app)}
