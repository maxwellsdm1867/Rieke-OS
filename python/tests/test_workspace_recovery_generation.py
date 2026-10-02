"""Native recovery feed/snapshot proofs, using only a disposable owned server."""
import os
import json
from types import SimpleNamespace
import threading
import time
import unittest
import uuid

import test_workspace_state_generation as fixtures
NativeConnection=fixtures.NativeConnection
from workspace_recovery_generation import RecoveryTracker, CLOCK, FEED, recovery_trigger_manifest
import workspace_native_mysql as native
import workspace_recovery_generation as generation


class RecoveryKeyCapacityTests(unittest.TestCase):
    def connection(self, actor_length=255):
        fields=[('project_uuid',36),('protocol_uuid',36),('candidate_revision_uuid',36),('actor',actor_length),('epoch_uuid',36)]
        rows=[dict(TABLE_NAME='workbench_decision',COLUMN_NAME=name,COLUMN_TYPE=f'varchar({size})',
            DATA_TYPE='varchar',CHARACTER_MAXIMUM_LENGTH=size,IS_NULLABLE='NO') for name,size in fields]
        class Result:
            def __init__(self, value):self.value=value
            def fetchall(self):return self.value
        class Connection:
            def query(self,sql,*args,**kwargs):
                if 'information_schema.TABLES' in sql:return Result([dict(TABLE_NAME='workbench_decision',ENGINE='InnoDB')])
                if 'information_schema.COLUMNS' in sql:return Result(rows)
                return Result([dict(TABLE_NAME='workbench_decision',COLUMN_NAME=name) for name,_ in fields])
        return Connection()

    def test_full_workbench_unicode_actor_keys_fit_versioned_exact_capacity(self):
        specs=generation.table_specs(self.connection())
        self.assertEqual(specs['workbench_decision']['primary_keys'],
            ['project_uuid','protocol_uuid','candidate_revision_uuid','actor','epoch_uuid'])
        self.assertEqual(generation.FEED_KEY_BYTES,4096)
        actor=('\x00\x01東"\\é'*43)[:255]
        encoded=json.dumps([str(uuid.uuid4()),str(uuid.uuid4()),str(uuid.uuid4()),actor,str(uuid.uuid4())],
            ensure_ascii=False).encode()
        self.assertGreater(len(encoded),1024)
        self.assertLessEqual(len(encoded),generation.FEED_KEY_BYTES)
        self.assertEqual(json.loads(encoded)[3],actor)

    def test_larger_unqualified_key_schema_still_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'exact bounded feed key'):
            generation.table_specs(self.connection(actor_length=1000))


@unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_MYSQL')=='1','opt-in native recovery authority proof')
class RecoveryGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.NativeGenerationTests.setUpClass()
        cls.connection=fixtures.NativeGenerationTests.connection;cls.root=fixtures.NativeGenerationTests.root
    @classmethod
    def tearDownClass(cls):fixtures.NativeGenerationTests.tearDownClass()

    def setUp(self):
        self.project,self.protocol,self.epoch=[str(uuid.uuid4()) for _ in range(3)]
        self.tracker=RecoveryTracker(self.connection,self.project).bootstrap()
        self.assertTrue(self.tracker.ready,self.tracker.reason)

    def insert(self, connection=None, epoch=None):
        (connection or self.connection).query('INSERT INTO recording_workspace.curation VALUES (%s,%s,%s,%s,1)',
            (self.project,self.protocol,epoch or self.epoch,'["one","ON","on"]'))

    def capture(self, prior=None):
        with self.tracker.capture(prior) as plan:
            self.assertIsNotNone(plan,self.tracker.reason)
            rows=self.connection.query('SELECT * FROM recording_workspace.curation WHERE project_uuid=%s',
                (self.project,),as_dict=True).fetchall()
            plan.verify()
            return plan,rows

    def test_cached_source_schema_is_reused_and_ddl_invalidates_it(self):
        from unittest.mock import patch
        import workspace_recovery_generation as generation
        initial,_=self.capture()
        with patch.object(generation,'table_specs',wraps=generation.table_specs) as specs:
            repeated,_=self.capture(initial.watermark)
            self.assertTrue(repeated.complete)
            self.assertEqual(specs.call_count,0)
            self.connection.query('ALTER TABLE recording_workspace.curation ADD COLUMN optional_note TEXT NULL')
            try:
                changed,_=self.capture(repeated.watermark)
                self.assertFalse(changed.complete)
                self.assertIn('optional_note',changed.columns['curation'])
                self.assertGreater(specs.call_count,0)
            finally:
                self.connection.query('ALTER TABLE recording_workspace.curation DROP COLUMN optional_note')
                self.tracker.bootstrap()

    def test_known_v1_ring_migrates_losslessly_and_invalidates_prior_watermark(self):
        self.insert()
        before,rows=self.capture()
        retained=self.connection.query(f'SELECT project_uuid,slot,table_id,key_bytes,generation,deleted '
            f'FROM recording_workspace.{FEED} WHERE project_uuid=%s',(self.project,)).fetchall()
        # This class owns a freshly created disposable server. Deliberately
        # recreate only the known earlier owned column width for migration.
        self.connection.query(f'ALTER TABLE recording_workspace.{FEED} MODIFY COLUMN key_bytes varbinary(1024) NOT NULL')
        self.tracker.bootstrap()
        self.assertTrue(self.tracker.ready,self.tracker.reason)
        column=self.connection.query('SELECT COLUMN_TYPE FROM information_schema.COLUMNS '
            'WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s',
            ('recording_workspace',FEED,'key_bytes')).fetchone()[0]
        self.assertEqual(column,'varbinary(4096)')
        self.assertEqual(self.connection.query(f'SELECT project_uuid,slot,table_id,key_bytes,generation,deleted '
            f'FROM recording_workspace.{FEED} WHERE project_uuid=%s',(self.project,)).fetchall(),retained)
        migrated,current=self.capture(before.watermark)
        self.assertFalse(migrated.complete)
        self.assertEqual(migrated.watermark['version'],2)
        self.assertNotEqual(migrated.watermark['authority'],before.watermark['authority'])
        self.assertEqual(current,rows)

    def test_workbench_exact_unicode_keys_native_feed_delta_rollback_and_rebootstrap(self):
        self.connection.query('CREATE TABLE recording_workspace.workbench_draft ('
            'project_uuid varchar(36) NOT NULL,protocol_uuid varchar(36) NOT NULL,candidate_revision_uuid varchar(36) NOT NULL,'
            'actor varchar(255) NOT NULL,version int unsigned NOT NULL,'
            'PRIMARY KEY(project_uuid,protocol_uuid,candidate_revision_uuid,actor)) ENGINE=InnoDB')
        self.connection.query('CREATE TABLE recording_workspace.workbench_decision ('
            'project_uuid varchar(36) NOT NULL,protocol_uuid varchar(36) NOT NULL,candidate_revision_uuid varchar(36) NOT NULL,'
            'actor varchar(255) NOT NULL,epoch_uuid varchar(36) NOT NULL,reviewed bool NOT NULL,'
            'PRIMARY KEY(project_uuid,protocol_uuid,candidate_revision_uuid,actor,epoch_uuid),'
            'FOREIGN KEY(project_uuid,protocol_uuid,candidate_revision_uuid,actor) REFERENCES '
            'recording_workspace.workbench_draft(project_uuid,protocol_uuid,candidate_revision_uuid,actor)) ENGINE=InnoDB')
        try:
            specs=generation.table_specs(self.connection)
            self.assertEqual(len(specs['workbench_decision']['primary_keys']),5)
            self.tracker.bootstrap();self.assertTrue(self.tracker.ready,self.tracker.reason)
            baseline,_=self.capture()
            # Match the supported production utf8mb3 actor authority: preserve
            # BMP Unicode/control/quote/backslash identity byte-for-byte. Astral
            # characters require a separate source-schema charset migration.
            candidate=str(uuid.uuid4());actor=('\x00\x01東"\\é'*43)[:255]
            draft=(self.project,self.protocol,candidate,actor)
            decision=(*draft,self.epoch)
            self.connection.query('INSERT INTO recording_workspace.workbench_draft VALUES (%s,%s,%s,%s,1)',draft)
            self.connection.query('INSERT INTO recording_workspace.workbench_decision VALUES (%s,%s,%s,%s,%s,1)',decision)
            plan,_=self.capture(baseline.watermark)
            self.assertTrue(plan.complete)
            self.assertEqual(plan.keys['workbench_draft'],[draft])
            self.assertEqual(plan.keys['workbench_decision'],[decision])
            raw=self.connection.query(f'SELECT key_bytes FROM recording_workspace.{FEED} '
                'WHERE project_uuid=%s AND table_id=%s ORDER BY generation DESC LIMIT 1',
                (self.project,generation.TABLE_IDS['workbench_decision'])).fetchone()[0]
            self.assertGreater(len(raw),1024)
            self.assertEqual(json.loads(raw),list(decision))
            with self.assertRaisesRegex(RuntimeError,'rollback'):
                with self.connection.transaction:
                    self.connection.query('UPDATE recording_workspace.workbench_decision SET reviewed=0 WHERE project_uuid=%s',(self.project,))
                    raise RuntimeError('rollback')
            unchanged,_=self.capture(plan.watermark)
            self.assertFalse(any(unchanged.keys.values()))
            restarted=RecoveryTracker(self.connection,self.project).bootstrap()
            self.assertTrue(restarted.ready,restarted.reason)
            with restarted.capture(unchanged.watermark) as continued:
                self.assertTrue(continued.complete)
                continued.verify()
            annotation=fixtures.bootstrap(self.connection,self.project)
            self.assertTrue(annotation.ready,annotation.reason)
            self.assertIsNotNone(annotation.token(self.protocol),annotation.reason)
        finally:
            for table in ('workbench_decision','workbench_draft'):
                for suffix in ('ai','au','ad'):
                    self.connection.query(f'DROP TRIGGER IF EXISTS recording_workspace.{generation.PREFIX}{table}_{suffix}')
                self.connection.query(f'DROP TABLE recording_workspace.{table}')
            self.tracker.bootstrap()

    def test_native_v3_baseline_freeze_uses_locked_scope_proof_inside_mysql_transaction(self):
        # Exact reader/ExplorerHistory publication with fixture recording rows;
        # generation, metadata locks and the transaction boundary are native.
        # The real H5 importer resume is separately owned by serialized E2E.
        from test_workspace_protocol_state import ProtocolStateTests
        fixture=ProtocolStateTests()
        fixture.setUp()
        try:
            fixture.service.dj.conn=lambda:self.connection
            tracker=fixtures.bootstrap(self.connection,fixture.service.project['project_uuid'])
            self.assertTrue(tracker.ready,tracker.reason)
            fixture.store.state_generation=tracker
            fixture.reader.shared.state_generation=tracker
            before=fixture.reader.materialized_state(fixture.protocol)[2]
            self.assertTrue(before.startswith('protocol-state-v3:'))
            captures=[]
            def guard(protocol):
                self.assertFalse(self.connection.in_transaction)
                context=fixture.reader.native_context(protocol)
                self.assertEqual(context['query_revision'],before)
                def verify():
                    self.assertTrue(self.connection.in_transaction)
                    self.assertIsNone(tracker.token(protocol))
                    captures.append(True)
                    return fixture.reader.assert_context_locked(protocol,context)
                return verify
            baselines=fixture.case.protocol_suggestions.freeze_baselines('native-fixture',
                fixture.reader.materialized_state,revision_guard=guard)
            self.assertEqual(len(baselines),1)
            self.assertEqual(baselines[0]['binding_version'],1)
            self.assertEqual(captures,[True])
            self.assertEqual({row['uuid'] for row in baselines[0]['recipe']['epochs']},set(fixture.ids))
        finally:
            fixture.doCleanups()

    def test_exact_keys_key_moves_rollback_and_retention_floor(self):
        initial,_=self.capture();self.assertFalse(initial.complete)
        self.insert()
        changed,rows=self.capture(initial.watermark)
        self.assertTrue(changed.complete)
        self.assertEqual(changed.keys['curation'],[(self.project,self.protocol,self.epoch)])
        self.assertEqual(changed.primary_keys['curation'],['project_uuid','protocol_uuid','epoch_uuid'])
        self.assertEqual(changed.json_columns['curation'],['tags'])
        self.assertEqual(len(rows),1)
        moved=str(uuid.uuid4())
        self.connection.query('UPDATE recording_workspace.curation SET epoch_uuid=%s,tags=%s WHERE project_uuid=%s',
            (moved,'["two"]',self.project))
        moved_plan,_=self.capture(changed.watermark)
        self.assertEqual(set(moved_plan.keys['curation']),{(self.project,self.protocol,self.epoch),(self.project,self.protocol,moved)})
        self.connection._conn.begin()
        self.connection.query('DELETE FROM recording_workspace.curation WHERE project_uuid=%s',(self.project,))
        self.connection._conn.rollback()
        unchanged,_=self.capture(moved_plan.watermark)
        self.assertTrue(unchanged.complete);self.assertFalse(any(unchanged.keys.values()))
        self.tracker.prune(unchanged.watermark,keep_generations=0)
        count=self.connection.query(f'SELECT COUNT(*) FROM recording_workspace.{FEED} WHERE project_uuid=%s',(self.project,)).fetchone()[0]
        self.assertEqual(count,0)
        stale,_=self.capture(initial.watermark);self.assertFalse(stale.complete)
        current,_=self.capture(unchanged.watermark);self.assertTrue(current.complete)
        self.assertEqual(len(recovery_trigger_manifest(self.connection)),9)

    def test_shared_instance_watermark_across_clients_and_anchor_loss(self):
        import pymysql
        second=NativeConnection(pymysql.connect(**native.connection_parameters(self.root),autocommit=True))
        try:
            first,_=self.capture()
            other=RecoveryTracker(second,self.project).bootstrap()
            self.assertTrue(other.ready,other.reason)
            with other.capture(first.watermark) as plan:
                self.assertIsNotNone(plan,other.reason);self.assertTrue(plan.complete)
                self.assertEqual(plan.watermark,first.watermark)
            self.insert(second)
            delta,_=self.capture(first.watermark);self.assertTrue(delta.complete)
            self.assertEqual(len(delta.keys['curation']),1)
            # Release the anchor owned by this connection without changing data.
            self.connection.query("SELECT RELEASE_LOCK('rieke_recovery_instance_v1')")
            with other.capture(delta.watermark) as plan:
                self.assertIsNotNone(plan,other.reason);self.assertFalse(plan.complete)
                self.assertNotEqual(plan.watermark['authority'],delta.watermark['authority'])
        finally:second._conn.close()
        self.tracker.bootstrap()

    def test_curation_vocabulary_exact_union_case_unicode_and_incremental_reads(self):
        from workspace_curation_vocabulary import CurationVocabulary
        from unittest.mock import patch
        other,second=str(uuid.uuid4()),str(uuid.uuid4())
        records=[(self.protocol,self.epoch,['ON','Straße','dup','dup']),
            (other,self.epoch,['ON','on','é']), (other,second,['on','İ','z','\ud7ff'])]
        for protocol,epoch,tags in records:
            self.connection.query('INSERT INTO recording_workspace.curation VALUES (%s,%s,%s,%s,1)',
                (self.project,protocol,epoch,json.dumps(tags)))
        store=SimpleNamespace(project_uuid=self.project,dj=SimpleNamespace(conn=lambda:self.connection))
        index=CurationVocabulary(store,self.tracker)
        self.addCleanup(index.close)
        def oracle(query):
            saved=self.connection.query('SELECT epoch_uuid,tags FROM recording_workspace.curation WHERE project_uuid=%s',
                (self.project,),as_dict=True).fetchall()
            membership={}
            for row in saved:
                for tag in set(json.loads(row['tags'])):membership.setdefault(tag,set()).add(row['epoch_uuid'])
            return [{'tag':tag,'count':len(ids)} for tag,ids in sorted(membership.items(),
                key=lambda item:(-len(item[1]),item[0].casefold(),item[0])) if tag.casefold().startswith(query.casefold())]
        for query in ('','on','STRASSE','i','\ud7ff','\ud800'):
            self.assertEqual(index.suggestions(query,100)['tags'],oracle(query))
        self.assertEqual(index.stats['full_builds'],1)
        self.connection.query('UPDATE recording_workspace.curation SET tags=%s WHERE project_uuid=%s AND protocol_uuid=%s AND epoch_uuid=%s',
            ('["on","added"]',self.project,self.protocol,self.epoch))
        watermark=self.tracker.token();self.tracker.prune(watermark)
        with patch.object(index,'records',wraps=index.records) as read:
            self.assertEqual(index.suggestions('',100)['tags'],oracle(''))
        self.assertTrue(read.called);self.assertIsNotNone(read.call_args.args[0])
        self.assertEqual(len(read.call_args.args[0]),1)
        self.assertEqual(index.stats['full_builds'],1);self.assertEqual(index.stats['rows_loaded'],4)
        self.connection.query('DELETE FROM recording_workspace.curation WHERE project_uuid=%s AND protocol_uuid=%s AND epoch_uuid=%s',
            (self.project,other,self.epoch))
        self.assertEqual(index.suggestions('',100)['tags'],oracle(''))
        moved=str(uuid.uuid4())
        self.connection.query('UPDATE recording_workspace.curation SET epoch_uuid=%s WHERE project_uuid=%s AND protocol_uuid=%s',
            (moved,self.project,self.protocol))
        self.assertEqual(index.suggestions('',100)['tags'],oracle(''))
        self.connection.query('UPDATE recording_workspace.curation SET tags=%s WHERE project_uuid=%s AND protocol_uuid=%s',
            ('["after gap"]',self.project,self.protocol))
        with patch.object(self.tracker,'_continues',return_value=False):
            self.assertEqual(index.suggestions('',100)['tags'],oracle(''))
        self.assertEqual(index.stats['full_builds'],2)

    def test_inflight_writer_commits_before_capture_clock_and_new_data_match_watermark(self):
        import pymysql
        self.insert()
        before,_=self.capture()
        writer=NativeConnection(pymysql.connect(**native.connection_parameters(self.root),autocommit=True))
        try:
            writer._conn.begin()
            writer.query('UPDATE recording_workspace.curation SET tags=%s WHERE project_uuid=%s',('["committed while capture waits"]',self.project))
            completed=[]
            def commit():
                time.sleep(.1);writer._conn.commit();completed.append(True)
            worker=threading.Thread(target=commit);worker.start()
            # Simulate DataJoint's eager consistent-snapshot start, not PyMySQL
            # begin(). The capture must choose READ COMMITTED for this one TX.
            import contextlib
            from unittest.mock import patch
            @contextlib.contextmanager
            def transaction(connection):
                connection.query('START TRANSACTION WITH CONSISTENT SNAPSHOT');connection.in_transaction=True
                try:
                    yield;connection._conn.commit()
                except Exception:connection._conn.rollback();raise
                finally:connection.in_transaction=False
            with patch.object(NativeConnection,'transaction',property(transaction)):
                after,rows=self.capture(before.watermark)
            worker.join(5);self.assertTrue(completed)
            self.assertGreater(after.watermark['generation'],before.watermark['generation'])
            self.assertIn('committed while capture waits',rows[0]['tags'])
        finally:writer._conn.rollback();writer._conn.close()


if __name__=='__main__':unittest.main()
