"""Opt-in real native MySQL checks for the private local storage profile."""
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest

from workspace_projects import create_project
from workspace_native_database import ensure_native_database, stop_native_database, sql_connection


@unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_MYSQL') == '1', 'requires bundled native MySQL')
class LocalMySQLIntegrationTests(unittest.TestCase):
    def test_durable_transactions_and_crash_recovery_without_binary_logs(self):
        with tempfile.TemporaryDirectory(prefix='rieke-storage-test-') as directory:
            root = Path(create_project(Path(directory), 'Storage test')['path'])
            try:
                ensure_native_database(root)
                state = json.loads((root/'database/native.json').read_text())
                with sql_connection(state) as connection, connection.cursor() as cursor:
                    cursor.execute('SELECT @@innodb_redo_log_capacity, @@log_bin, '
                                   '@@innodb_flush_log_at_trx_commit, @@innodb_doublewrite, '
                                   '@@innodb_buffer_pool_size')
                    self.assertEqual(cursor.fetchone(), (64*1024**2, 0, 1, 'ON', 128*1024**2))
                    cursor.execute('CREATE DATABASE storage_probe')
                    cursor.execute('CREATE TABLE storage_probe.records (id INT PRIMARY KEY, payload TEXT) ENGINE=InnoDB')
                    cursor.execute('START TRANSACTION')
                    cursor.execute("INSERT INTO storage_probe.records VALUES (1, 'committed annotation')")
                    cursor.execute('COMMIT')
                    cursor.execute('START TRANSACTION')
                    cursor.execute("INSERT INTO storage_probe.records VALUES (2, 'rolled back')")
                    cursor.execute('ROLLBACK')
                # Deliberately crash only this isolated test server, after commit.
                os.kill(state['pid'], signal.SIGKILL)
                for _ in range(100):
                    try:
                        pid, _ = os.waitpid(state['pid'], os.WNOHANG)
                    except ChildProcessError:
                        break
                    if pid:
                        break
                    time.sleep(.05)
                ensure_native_database(root)
                state = json.loads((root/'database/native.json').read_text())
                with sql_connection(state) as connection, connection.cursor() as cursor:
                    cursor.execute('SELECT * FROM storage_probe.records ORDER BY id')
                    self.assertEqual(cursor.fetchall(), ((1, 'committed annotation'),))
                    cursor.execute('SELECT @@log_bin, @@innodb_redo_log_capacity')
                    self.assertEqual(cursor.fetchone(), (0, 64*1024**2))
                self.assertFalse(list((root/'database/mysql').glob('binlog.*')))
            finally:
                stop_native_database(root)

    def test_common_app_operations_save_snapshots_without_action_history(self):
        from types import SimpleNamespace
        import uuid
        from workspace_native_database import connect_native
        from workspace_annotations import SharedAnnotations
        from workspace_curation import CurationStore, RevisionConflict
        from workspace_tree_layouts import TreeLayouts
        from workspace_search_presets import SearchPresets
        from workspace_state_snapshot import save, load, restore
        with tempfile.TemporaryDirectory(prefix='rieke-operations-test-') as directory:
            project = create_project(Path(directory), 'Operations test')
            root = Path(project['path']); dj = None
            try:
                ensure_native_database(root)
                dj = connect_native(root)
                dj.conn(reset=True)
                epoch, cell, protocol = [str(uuid.uuid4()) for _ in range(3)]
                service = SimpleNamespace(dj=dj, project={'project_uuid':project['uuid']},
                    cells={cell:{}}, rows={epoch:{'epoch_uuid':epoch,'cell_uuid':cell}})
                annotations = SharedAnnotations(service)
                store = CurationStore(dj, project['uuid'])
                layouts = TreeLayouts(store)
                presets = SearchPresets(store)
                author = annotations.default_profile['profile_uuid']
                for revision in range(100):
                    annotations.update('epoch', [epoch], author,
                        {'tags_add':['keep' if revision % 2 == 0 else 'review'],
                         'tags_remove':['review' if revision % 2 == 0 else 'keep']},
                        {epoch:revision}, 'scientist')
                count = len(store.Event())
                annotations.update('epoch', [epoch], author, {'tags_add':['review']}, {epoch:100}, 'scientist')
                self.assertEqual(len(store.Event()), count)  # No-op save adds nothing.
                with self.assertRaises(RevisionConflict):
                    annotations.update('epoch', [epoch], author, {'tags_add':['stale']}, {epoch:0}, 'scientist')
                for revision in range(20):
                    fields = ['cell'] if revision % 2 == 0 else ['protocol','cell']
                    layouts.save(protocol, fields, revision, 'scientist')
                count = len(store.Event())
                layouts.save(protocol, fields, 20, 'scientist')
                self.assertEqual(len(store.Event()), count)
                body = {'name':'My query','predicate':{'all':[]},'splits':'cell','pinned':True}
                preset = presets.save(body, 'scientist')
                count = len(store.Event())
                presets.save({**body,'expected_version':1}, 'scientist', preset['preset_uuid'])
                self.assertEqual(len(store.Event()), count)
                # Browsing saved state repeatedly must perform no audit writes.
                for _ in range(100):
                    annotations.read_targets('epoch', [epoch]); layouts.read(protocol); presets.list()
                self.assertEqual(len(store.Event()), count)
                preview={'predicate':body['predicate'],'matched_count':1,'membership':[{'uuid':epoch}],
                    'tree_revision':'tree','source_scope':{'revision':'source','active_source_revisions':['a'*64]},
                    'splits':'cell','metadata_fingerprint_version':2}
                for _ in range(50):presets.record_run(preview,service.rows,'scientist')
                self.assertEqual(len(presets.Runs()),1)
                events = store.Event.to_dicts()
                self.assertEqual(len(annotations.Annotation()), 1)
                self.assertEqual(len(layouts.Table()), 1)
                self.assertEqual(len(presets.Table()), 1)
                connection = dj.conn()
                self.assertEqual(events, [])
                snapshot = save(root, connection)
                data = load(snapshot['path'])
                self.assertNotIn('event',data['tables'])
                self.assertEqual(len(data['tables']['search_query_last_run']),1)
                self.assertNotIn('membership',data['tables']['search_query_last_run'][0]['result'])
                self.assertEqual(data['tables']['shared_annotation'][0]['tags'], ['review'])
                mtime = (root/'app-state.json').stat().st_mtime_ns
                self.assertFalse(save(root,connection)['changed'])
                self.assertEqual((root/'app-state.json').stat().st_mtime_ns,mtime)
                archive=Path(snapshot['daily_backup']); archive_bytes=archive.read_bytes()
                connection.query('DELETE FROM recording_workspace.shared_annotation')
                save(root,connection)
                self.assertEqual(archive.read_bytes(),archive_bytes)
                restore(root,connection,archive)
                self.assertEqual(annotations.Annotation.to_dicts()[0]['tags'], ['review'])
                self.assertEqual(layouts.read(protocol)['version'],20)
                self.assertEqual(presets.read(preset['preset_uuid'])['name'],'My query')
                print(json.dumps({'tag_edits':100, 'layout_changes':20, 'saved_queries':1,
                    'action_events':len(events), 'state_json_bytes':snapshot['bytes'],
                    'daily_sqlite_bytes':archive.stat().st_size}))
                connection.close()
                stop_native_database(root)
                ensure_native_database(root)
                state=json.loads((root/'database/native.json').read_text())
                with sql_connection(state) as connection, connection.cursor() as cursor:
                    cursor.execute('SELECT tags,revision FROM recording_workspace.shared_annotation')
                    tags,revision=cursor.fetchone()
                    self.assertEqual(json.loads(tags), ['review']); self.assertEqual(revision,100)
                    cursor.execute('SELECT version FROM recording_workspace.protocol_tree_layout')
                    self.assertEqual(cursor.fetchone()[0],20)
                    cursor.execute('SELECT COUNT(*) FROM recording_workspace.search_preset')
                    self.assertEqual(cursor.fetchone()[0],1)
            finally:
                if dj is not None and dj.conn().is_connected:
                    dj.conn().close()
                stop_native_database(root)
