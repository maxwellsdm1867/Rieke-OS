"""Opt-in authority proofs against a newly created disposable native database."""
import os
import contextlib
from pathlib import Path
import tempfile
import unittest
import uuid
import contextvars
import threading
from dataclasses import replace
from types import SimpleNamespace

from workspace_projects import create_project
import workspace_native_mysql as native
from workspace_state_generation import bootstrap,MANIFEST,SCHEMA,GENERATION,CHANGES,verify_export_triggers,StateGenerationAuthority


class GenerationReadScopeTests(unittest.TestCase):
    def setUp(self):
        self.project,self.protocol,self.other=[str(uuid.uuid4()) for _ in range(3)]
        self.connection=SimpleNamespace(_conn=object(),in_transaction=False)
        self.authority=StateGenerationAuthority(self.connection,self.project)
        self.authority.ready=True
        self.contract_calls=[]
        self.authority._contract=lambda:self.contract_calls.append(True) or 'verified authority'
        self.authority._scope=lambda kind,identity:('verified epoch',1)

    def test_response_contract_attests_twice_but_generations_stay_live(self):
        del self.authority._contract
        self.authority._attest_contract=lambda:self.contract_calls.append(True) or 'verified authority'
        generation=[1]
        self.authority._scope=lambda kind,identity:('verified epoch',generation[0])
        with self.authority.response_contract():
            first=self.authority.token(self.protocol)
            generation[0]=2
            second=self.authority.token(self.protocol)
            self.assertNotEqual(first,second)
            self.assertEqual(len(self.contract_calls),1)
            escaped=contextvars.copy_context()
        self.assertEqual(len(self.contract_calls),2)
        escaped.run(self.authority.token,self.protocol)
        self.assertEqual(len(self.contract_calls),4)

    def test_response_contract_cannot_cross_threads_or_transactions(self):
        del self.authority._contract
        self.authority._attest_contract=lambda:self.contract_calls.append(True) or 'verified authority'
        with self.authority.response_contract():
            copied=contextvars.copy_context()
            worker=threading.Thread(target=lambda:copied.run(self.authority.token,self.protocol))
            worker.start();worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(self.contract_calls),3)
            self.connection.in_transaction=True
            self.authority._contract()
            self.assertEqual(len(self.contract_calls),4)
            self.connection.in_transaction=False
        self.assertEqual(len(self.contract_calls),5)

    def test_response_contract_rejects_closing_change_and_releases_lease_on_error(self):
        del self.authority._contract
        contract=['before']
        self.authority._attest_contract=lambda:self.contract_calls.append(True) or contract[0]
        with self.assertRaisesRegex(ValueError,'contract changed'):
            with self.authority.response_contract():
                self.authority.token(self.protocol)
                contract[0]='after'
        self.assertIsNone(self.authority._verified_read_token)
        with self.assertRaisesRegex(RuntimeError,'interrupted'):
            with self.authority.response_contract():raise RuntimeError('interrupted')
        self.assertIsNone(self.authority._response_contract.get())

    def test_scoped_shared_token_is_reused_but_other_protocol_and_final_reads_are_fresh(self):
        token=self.authority.token(self.protocol)
        self.assertEqual(len(self.contract_calls),2)
        with self.authority.read_scope(token):
            self.assertEqual(self.authority.token(self.protocol),token)
            self.assertEqual(self.authority.token(),replace(token,protocol_uuid=None,protocol_epoch=None,protocol_generation=None))
            self.assertEqual(len(self.contract_calls),2)
            with self.assertRaisesRegex(ValueError,'nested'):
                with self.authority.read_scope(token):pass
            self.authority.token(self.other)
            self.assertEqual(len(self.contract_calls),4)
        self.authority.token(self.protocol)
        self.assertEqual(len(self.contract_calls),6)

    def test_scope_cannot_cross_threads_outlive_context_or_reuse_unverified_authority(self):
        token=self.authority.token(self.protocol)
        with self.authority.read_scope(token):
            saved=contextvars.copy_context()
            copied=contextvars.copy_context()
            worker=threading.Thread(target=lambda:copied.run(self.authority.token,self.protocol))
            worker.start();worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(self.contract_calls),4)
        saved.run(self.authority.token,self.protocol)
        self.assertEqual(len(self.contract_calls),6)
        with self.assertRaisesRegex(ValueError,'different native authority'):
            with self.authority.read_scope(replace(token,authority='unverified')):pass

    def test_exception_and_connection_change_do_not_leave_a_reusable_generation(self):
        token=self.authority.token(self.protocol)
        with self.assertRaisesRegex(RuntimeError,'interrupted'):
            with self.authority.read_scope(token):
                self.connection._conn=object()
                self.authority.token(self.protocol)
                self.assertEqual(len(self.contract_calls),4)
                raise RuntimeError('interrupted')
        self.authority.token(self.protocol)
        self.assertEqual(len(self.contract_calls),6)


class NativeConnection:
    def __init__(self,connection):self._conn=connection;self.in_transaction=False
    @property
    @contextlib.contextmanager
    def transaction(self):
        if self.in_transaction:raise RuntimeError('Nested test transaction')
        self._conn.begin();self.in_transaction=True
        try:
            yield
            self._conn.commit()
        except Exception:
            self._conn.rollback();raise
        finally:self.in_transaction=False

    def query(self,sql,args=(),as_dict=False,reconnect=False):
        import pymysql
        cursor=self._conn.cursor(pymysql.cursors.DictCursor if as_dict else pymysql.cursors.Cursor)
        cursor.execute(sql,args)
        return cursor


@unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_MYSQL')=='1','opt-in isolated native authority proof')
class NativeGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pymysql
        cls.temporary=tempfile.TemporaryDirectory(prefix='rieke-private-authority-test-')
        cls.root=Path(create_project(Path(cls.temporary.name)/'projects','Disposable authority fixture')['path'])
        native.ensure_native_database(cls.root)
        cls.connection=NativeConnection(pymysql.connect(**native.connection_parameters(cls.root),autocommit=True))
        cls.connection.query('CREATE DATABASE recording_workspace')
        for sql in (
            'CREATE TABLE recording_workspace.curation (project_uuid varchar(36),protocol_uuid varchar(36),epoch_uuid varchar(36),tags JSON,revision int, PRIMARY KEY(project_uuid,protocol_uuid,epoch_uuid)) ENGINE=InnoDB',
            'CREATE TABLE recording_workspace.shared_annotation (project_uuid varchar(36),target_kind varchar(16),target_uuid varchar(36),profile_uuid varchar(36),tags JSON,revision int,PRIMARY KEY(project_uuid,target_kind,target_uuid,profile_uuid)) ENGINE=InnoDB',
            'CREATE TABLE recording_workspace.annotation_profile (project_uuid varchar(36),profile_uuid varchar(36),display_name varchar(120),PRIMARY KEY(project_uuid,profile_uuid)) ENGINE=InnoDB'):
            cls.connection.query(sql)

    @classmethod
    def tearDownClass(cls):
        cls.connection._conn.close();native.stop_native_database(cls.root);cls.temporary.cleanup()

    def setUp(self):
        self.project,self.protocol,self.epoch,self.profile=[str(uuid.uuid4()) for _ in range(4)]
        self.authority=bootstrap(self.connection,self.project)
        self.assertTrue(self.authority.ready,self.authority.reason)

    def token(self):
        token=self.authority.token(self.protocol)
        self.assertIsNotNone(token,self.authority.reason)
        return token

    def test_response_contract_fences_ddl_and_disabled_observers_at_exit(self):
        with self.assertRaisesRegex(ValueError,'contract changed'):
            try:
                with self.authority.response_contract():
                    self.assertIsNotNone(self.authority.token(self.protocol))
                    self.connection.query('CREATE TABLE recording_workspace.response_contract_probe (id INT PRIMARY KEY) ENGINE=InnoDB')
            finally:
                self.connection.query('DROP TABLE IF EXISTS recording_workspace.response_contract_probe')
        try:
            with self.assertRaisesRegex(ValueError,'disabled'):
                with self.authority.response_contract():
                    self.assertIsNotNone(self.authority.token(self.protocol))
                    self.connection.query("UPDATE performance_schema.setup_consumers SET ENABLED='NO' WHERE NAME='events_statements_current'")
        finally:
            self.connection.query("UPDATE performance_schema.setup_consumers SET ENABLED='YES' WHERE NAME='events_statements_current'")
        self.assertIsNotNone(self.authority.token(self.protocol))

    def test_read_scope_defers_shared_rechecks_but_fresh_exit_observes_external_commit(self):
        import pymysql
        writer=NativeConnection(pymysql.connect(**native.connection_parameters(self.root),autocommit=True))
        try:
            before=self.token()
            with self.authority.read_scope(before):
                writer.query('INSERT INTO recording_workspace.shared_annotation VALUES (%s,%s,%s,%s,%s,1)',
                    (self.project,'epoch',self.epoch,self.profile,'["external write during read"]'))
                self.assertEqual(self.authority.token(self.protocol),before)
                self.assertEqual(self.authority.token(),replace(before,protocol_uuid=None,protocol_epoch=None,protocol_generation=None))
            after=self.token()
            self.assertGreater(after.shared_generation,before.shared_generation)
            with self.authority.read_scope(after):
                self.assertEqual(self.authority.token(self.protocol),after)
            self.assertEqual(self.token(),after)
            with self.authority.read_scope(after):
                writer._conn.begin()
                writer.query('UPDATE recording_workspace.shared_annotation SET tags=%s WHERE project_uuid=%s',
                    ('["rolled back"]',self.project))
                self.assertEqual(self.authority.token(self.protocol),after)
                writer._conn.rollback()
            self.assertEqual(self.token(),after)
        finally:
            writer._conn.rollback();writer._conn.close()

    def test_same_revision_dml_moves_rollback_replace_and_feed(self):
        before=self.token()
        self.connection.query('INSERT INTO recording_workspace.curation VALUES (%s,%s,%s,%s,1)',
            (self.project,self.protocol,self.epoch,'["one"]'))
        inserted=self.token();self.assertGreater(inserted.protocol_generation,before.protocol_generation)
        self.connection.query('UPDATE recording_workspace.curation SET tags=%s WHERE project_uuid=%s',('["two"]',self.project))
        changed=self.token();self.assertGreater(changed.protocol_generation,inserted.protocol_generation)
        self.connection._conn.begin()
        self.connection.query('DELETE FROM recording_workspace.curation WHERE project_uuid=%s',(self.project,))
        self.connection._conn.rollback();self.assertEqual(self.token(),changed)
        moved=str(uuid.uuid4())
        self.connection.query('UPDATE recording_workspace.curation SET protocol_uuid=%s WHERE project_uuid=%s',(moved,self.project))
        self.assertGreater(self.token().protocol_generation,changed.protocol_generation)
        self.assertGreater(self.authority.token(moved).protocol_generation,0)
        shared=self.authority.token()
        self.connection.query('INSERT INTO recording_workspace.shared_annotation VALUES (%s,%s,%s,%s,%s,1)',
            (self.project,'epoch',self.epoch,self.profile,'["shared"]'))
        changes,after=self.authority.shared_changes(shared)
        self.assertEqual(len(changes),1);self.assertEqual(changes[0]['deleted'],0)
        self.connection.query('REPLACE INTO recording_workspace.shared_annotation VALUES (%s,%s,%s,%s,%s,1)',
            (self.project,'epoch',self.epoch,self.profile,'["replaced"]'))
        changes,replaced=self.authority.shared_changes(after)
        self.assertEqual(len(changes),1);self.assertEqual(changes[0]['deleted'],0)
        self.assertGreater(replaced.shared_generation,after.shared_generation)
        self.connection.query('DELETE FROM recording_workspace.shared_annotation WHERE project_uuid=%s',(self.project,))
        changes,deleted=self.authority.shared_changes(replaced)
        self.assertEqual(changes[0]['deleted'],1)
        self.connection.query('INSERT INTO recording_workspace.annotation_profile VALUES (%s,%s,%s)',(self.project,self.profile,'author'))
        changes,_=self.authority.shared_changes(deleted)
        self.assertEqual(changes[0]['target_kind'],'profile')

    def test_disabled_witnesses_invalidate_and_transaction_lock_checks_reject_stale_tokens(self):
        before=self.token()
        try:
            self.connection.query("UPDATE performance_schema.setup_consumers SET ENABLED='NO' WHERE NAME='events_statements_current'")
            self.assertIsNone(self.authority.token(self.protocol))
        finally:
            self.connection.query("UPDATE performance_schema.setup_consumers SET ENABLED='YES' WHERE NAME='events_statements_current'")
        after=self.token();self.assertNotEqual(before.authority,after.authority)
        try:
            self.connection.query("UPDATE performance_schema.setup_instruments SET ENABLED='NO' WHERE NAME='statement/com/Execute'")
            self.assertIsNone(self.authority.token(self.protocol))
        finally:
            self.connection.query("UPDATE performance_schema.setup_instruments SET ENABLED='YES' WHERE NAME='statement/com/Execute'")
        self.connection.query('INSERT INTO recording_workspace.curation VALUES (%s,%s,%s,%s,1)',
            (self.project,self.protocol,self.epoch,'["before"]'))
        before=self.token()
        self.connection._conn.begin();self.connection.in_transaction=True
        try:
            self.authority.assert_current_locked(before)
            self.connection.query('UPDATE recording_workspace.curation SET tags=%s WHERE project_uuid=%s',('["after"]',self.project))
            self.connection._conn.commit()
        finally:
            self.connection._conn.rollback();self.connection.in_transaction=False
        self.assertNotEqual(before,self.token())
        from workspace_curation import RevisionConflict
        self.connection._conn.begin();self.connection.in_transaction=True
        try:
            with self.assertRaises(RevisionConflict):self.authority.assert_current_locked(before)
        finally:
            self.connection._conn.rollback();self.connection.in_transaction=False

    def test_trigger_gap_missing_row_truncation_and_export_contract(self):
        before=self.token()
        name='rieke_state_v1_curation_au';trigger=MANIFEST[name]
        self.connection.query(f'DROP TRIGGER recording_workspace.{name}')
        self.assertIsNone(self.authority.token(self.protocol))
        self.connection.query(f'CREATE TRIGGER recording_workspace.{name} AFTER UPDATE ON recording_workspace.curation FOR EACH ROW '+trigger['body'])
        self.assertNotEqual(before.authority,self.token().authority)
        before=self.token()
        self.connection.query(f'DELETE FROM recording_workspace.{GENERATION} WHERE project_uuid=%s',(self.project,))
        self.assertNotEqual(before.protocol_epoch,self.token().protocol_epoch)
        before=self.token()
        self.connection.query('TRUNCATE TABLE recording_workspace.curation')
        self.assertNotEqual(before.authority,self.token().authority)
        before=self.token()
        self.connection.query(f'TRUNCATE TABLE recording_workspace.{CHANGES}')
        self.assertNotEqual(before.authority,self.token().authority)
        self.assertTrue(verify_export_triggers(self.connection,[SCHEMA])['safe_to_omit'])
        self.connection.query('CREATE TRIGGER recording_workspace.user_owned AFTER INSERT ON recording_workspace.curation FOR EACH ROW SET @user_test=1')
        self.assertFalse(verify_export_triggers(self.connection,[SCHEMA])['safe_to_omit'])
        self.connection.query('DROP TRIGGER recording_workspace.user_owned')


if __name__=='__main__':unittest.main()
