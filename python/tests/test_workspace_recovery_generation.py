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
