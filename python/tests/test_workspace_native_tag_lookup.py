"""Persistent tag lookup contract, plus opt-in disposable native SQL proof."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from workspace_native_tag_lookup import NativeTagLookup,bootstrap,TRIGGER_MANIFEST,TABLE,MARKER


class TagLookupTests(unittest.TestCase):
    def test_query_parameters_preserve_exact_utf8_and_bounded_kinds(self):
        lookup=NativeTagLookup(None,str(uuid.uuid4()));lookup.ready=True
        sql,args=lookup._target_query('e\u0301',('epoch',))
        self.assertIn('FORCE INDEX (by_tag)',sql)
        self.assertEqual(args[-1],'e\u0301'.encode())
        for tag in ('','x'*256,12):
            with self.assertRaises(ValueError):lookup._target_query(tag,('cell',))
        with self.assertRaises(ValueError):lookup._target_query('QC',('unknown',))


@unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_MYSQL')=='1','opt-in private native tag lookup')
class NativeTagLookupTests(unittest.TestCase):
    def test_migration_exact_unicode_all_writers_rollback_and_reuse(self):
        import pymysql
        from workspace_projects import create_project
        import workspace_native_mysql as native
        with tempfile.TemporaryDirectory(prefix='rieke-native-tag-lookup-') as directory:
            root=Path(create_project(Path(directory)/'projects','Native tag lookup test')['path'])
            raw=None
            try:
                native.ensure_native_database(root);raw=pymysql.connect(**native.connection_parameters(root),autocommit=True)
                class Adapter:
                    in_transaction=False
                    def query(self,sql,args=(),as_dict=False,reconnect=False):
                        cursor=raw.cursor(pymysql.cursors.DictCursor if as_dict else pymysql.cursors.Cursor)
                        cursor.execute(sql,args);return cursor
                    @property
                    @contextlib.contextmanager
                    def transaction(self):
                        raw.begin();self.in_transaction=True
                        try:yield
                        except BaseException:raw.rollback();raise
                        else:raw.commit()
                        finally:self.in_transaction=False
                conn=Adapter();project=str(uuid.uuid4());profile=str(uuid.uuid4())
                conn.query('CREATE DATABASE recording_workspace')
                conn.query('CREATE TABLE recording_workspace.shared_annotation (project_uuid varchar(36),target_kind varchar(8),target_uuid varchar(36),profile_uuid varchar(36),tags JSON NOT NULL,PRIMARY KEY(project_uuid,target_kind,target_uuid,profile_uuid)) ENGINE=InnoDB')
                conn.query('CREATE TABLE recording_workspace.app_state_generation (project_uuid varchar(36),scope_kind varchar(32),scope_uuid varchar(36),generation BIGINT,PRIMARY KEY(project_uuid,scope_kind,scope_uuid)) ENGINE=InnoDB')
                conn.query('INSERT INTO recording_workspace.app_state_generation VALUES (%s,%s,%s,0)',(project,'shared_annotations',project))
                records={}
                def write(identity,values,kind='epoch',author=profile):
                    conn.query('REPLACE INTO recording_workspace.shared_annotation VALUES (%s,%s,%s,%s,%s)',(project,kind,identity,author,json.dumps(values)))
                    records[(kind,identity,author)]=values
                def proof():
                    rows=conn.query('SELECT * FROM recording_workspace.shared_annotation ORDER BY project_uuid,target_kind,target_uuid,profile_uuid',as_dict=True).fetchall()
                    return {'project_uuid':project,'tables':{'shared_annotation':{'count':len(rows),'xor':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}}}
                cases=[['QC'],['qc'],['é'],['e\u0301'],['😀'*255],['😀'*254+chr(0x1f600+i) for i in range(100)],
                    ['legal\x7f','inside\u0085value','inside\u3000value'],[]]
                ids=[str(uuid.uuid4()) for _ in cases]
                for key,values in zip(ids,cases):write(key,values)
                firstproof=proof();lookup=bootstrap(conn,project,firstproof)
                self.assertTrue(lookup.ready,lookup.reason);self.assertFalse(lookup.reused)
                for key,values in zip(ids,cases):
                    for value in values:self.assertIn(('epoch',key),lookup.targets(value))
                self.assertEqual(lookup.targets('QC'),{('epoch',ids[0])})
                self.assertEqual(lookup.targets('qc'),{('epoch',ids[1])})
                self.assertEqual(lookup.targets('é'),{('epoch',ids[2])})
                self.assertEqual(lookup.targets('e\u0301'),{('epoch',ids[3])})
                self.assertNotIn(('epoch',ids[0]),lookup.targets_outside(['QC']))
                self.assertIn(('epoch',ids[1]),lookup.targets_outside(['QC']))
                self.assertEqual(lookup.targets_outside([]),lookup.tagged_targets())
                self.assertNotIn(('epoch',ids[-1]),lookup.tagged_targets())
                sql,args=lookup._target_query('QC',('epoch',))
                plan=conn.query('EXPLAIN FORMAT=JSON '+sql,args).fetchone()[0]
                self.assertIn('by_tag',plan)
                self.assertTrue(bootstrap(conn,project,firstproof).reused)
                ddl_before=conn.query("SHOW GLOBAL STATUS WHERE Variable_name='Com_create_table'").fetchone()
                self.assertTrue(bootstrap(conn,project,firstproof).reused)
                self.assertEqual(conn.query("SHOW GLOBAL STATUS WHERE Variable_name='Com_create_table'").fetchone(),ddl_before)
                # A->B with triggers, then B->A in a trigger gap: the canonical
                # proof matches the old marker, but the sticky dirty bit forbids
                # falsely reusing B after process restart.
                conn.query('UPDATE recording_workspace.shared_annotation SET tags=%s WHERE target_uuid=%s',(json.dumps(['intermediate']),ids[2]))
                trigger_name=next(name for name in TRIGGER_MANIFEST if name.endswith('_au'))
                conn.query('DROP TRIGGER recording_workspace.'+trigger_name)
                conn.query('UPDATE recording_workspace.shared_annotation SET tags=%s WHERE target_uuid=%s',(json.dumps(['é']),ids[2]))
                spec=TRIGGER_MANIFEST[trigger_name]
                conn.query('CREATE TRIGGER recording_workspace.'+trigger_name+' AFTER UPDATE ON recording_workspace.shared_annotation FOR EACH ROW '+spec['body'])
                self.assertEqual(proof(),firstproof)
                aba=bootstrap(conn,project,firstproof)
                self.assertTrue(aba.ready,aba.reason);self.assertFalse(aba.reused)
                self.assertEqual(aba.targets('intermediate'),set())
                self.assertEqual(aba.targets('é'),{('epoch',ids[2])})
                conn.query('UPDATE recording_workspace.shared_annotation SET tags=%s WHERE target_uuid=%s',(json.dumps(['updated']),ids[0]))
                self.assertEqual(lookup.targets('QC'),set());self.assertEqual(lookup.targets('updated'),{('epoch',ids[0])})
                with self.assertRaisesRegex(RuntimeError,'rollback'):
                    with conn.transaction:
                        conn.query('UPDATE recording_workspace.shared_annotation SET tags=%s WHERE target_uuid=%s',(json.dumps(['partial']),ids[0]))
                        self.assertEqual(lookup.targets('partial'),{('epoch',ids[0])})
                        raise RuntimeError('rollback')
                self.assertEqual(lookup.targets('partial'),set());self.assertEqual(lookup.targets('updated'),{('epoch',ids[0])})
                other=str(uuid.uuid4());write(ids[0],['updated'],author=other)
                self.assertEqual(lookup.targets('updated'),{('epoch',ids[0])})
                conn.query('DELETE FROM recording_workspace.shared_annotation WHERE target_uuid=%s AND profile_uuid=%s',(ids[0],profile))
                self.assertEqual(lookup.targets('updated'),{('epoch',ids[0])})
                conn.query('UPDATE recording_workspace.shared_annotation SET tags=JSON_ARRAY() WHERE target_uuid=%s',(ids[0],))
                self.assertEqual(lookup.targets('updated'),set())
                moved=str(uuid.uuid4());moved_author=str(uuid.uuid4())
                conn.query('UPDATE recording_workspace.shared_annotation SET target_kind=%s,target_uuid=%s,profile_uuid=%s WHERE target_uuid=%s',
                    ('cell',moved,moved_author,ids[1]))
                self.assertEqual(lookup.targets('qc'),{('cell',moved)})
                self.assertEqual(lookup.targets('qc',('epoch',)),set())
                write(str(uuid.uuid4()),['legal\x7f','inside\u0085value','inside\u3000value'])
                for invalid in ([1],['duplicate','duplicate'],['x'*256],[' padded'],['\u3000padded'],['padded\u0085'],['bad\x00tag'],['a']*101):
                    with self.subTest(invalid=str(invalid)[:30]),self.assertRaises(Exception):write(str(uuid.uuid4()),invalid)
                changed=proof();rebuilt=bootstrap(conn,project,changed)
                self.assertTrue(rebuilt.ready,rebuilt.reason);self.assertFalse(rebuilt.reused)
                self.assertTrue(rebuilt.validate_current())
                with self.assertRaisesRegex(ValueError,'authority changed'):
                    rebuilt.checkpoint(changed,guard=lambda:False)
                rebuilt.checkpoint(changed);self.assertTrue(bootstrap(conn,project,changed).reused)
                conn.query('DROP TRIGGER recording_workspace.'+next(iter(TRIGGER_MANIFEST)))
                with self.assertRaisesRegex(ValueError,'incomplete'):rebuilt.validate_current()
                fixed=bootstrap(conn,project,changed)
                self.assertTrue(fixed.ready,fixed.reason);self.assertFalse(fixed.reused)
                conn.query('TRUNCATE TABLE recording_workspace.'+TABLE)
                with self.assertRaisesRegex(ValueError,'incarnation'):fixed.checkpoint(changed)
                repaired=bootstrap(conn,project,changed)
                self.assertTrue(repaired.ready,repaired.reason);self.assertFalse(repaired.reused)
                self.assertEqual(repaired.targets('qc'),{('cell',moved)})
                # A clean native restart retains the DB index and proof marker.
                raw.close();raw=None;native.stop_native_database(root);native.ensure_native_database(root)
                raw=pymysql.connect(**native.connection_parameters(root),autocommit=True)
                reopened=bootstrap(conn,project,changed)
                self.assertTrue(reopened.ready,reopened.reason);self.assertTrue(reopened.reused)
                self.assertEqual(reopened.targets('qc'),{('cell',moved)})
            finally:
                if raw is not None:raw.close()
                native.stop_native_database(root)
