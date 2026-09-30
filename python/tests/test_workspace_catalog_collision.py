"""Scratch lookup bounds and ownership without touching a real database."""
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from workspace_catalog_collision import CatalogCollisionLookup,KINDS


class Cursor:
    def __init__(self,rows):self.rows=rows
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows


class Relation:
    def __init__(self,name,records=(),requests=None):
        self.full_table_name=f'`schema`.`{name.lower()}`';self.records=records
        self.requests=[] if requests is None else requests
    def __and__(self,batch):
        self.requests.append(batch)
        return Relation('subset',[row for row in self.records if row in {entry['h5_uuid'] for entry in batch}],self.requests)
    def fetch(self,field,limit):return self.records[:limit]


class Connection:
    def __init__(self):
        self.in_transaction=False;self.calls=[];self.owner=17;self.lock=17
        self.collations={};self.indexed=set();self.temporary={};self.closed=False
        self.collision=None;self.fail=None;self.empty=False
    def query(self,sql,args=(),reconnect=None,as_dict=False):
        self.calls.append((sql,args));assert reconnect is False
        if self.fail and self.fail in sql:raise OSError('injected SQL failure')
        if sql=='SELECT CONNECTION_ID()':return Cursor([(self.owner,)])
        if sql.startswith('SELECT CONNECTION_ID(),'):return Cursor([(self.owner,self.lock)])
        if sql.startswith('SHOW FULL COLUMNS'):
            name=sql.split(' FROM ')[1].split(' ')[0]
            return Cursor([{'Type':'varchar(255)','Collation':self.collations.get(name,'utf8mb3_general_ci')}])
        if sql.startswith('SHOW INDEX'):
            name=sql.split(' FROM ')[1]
            return Cursor([{'Seq_in_index':1,'Column_name':'h5_uuid'}] if name in self.indexed else [])
        if sql.startswith('SELECT CHARACTER_SET_NAME'):return Cursor([(args[0].split('_')[0],)])
        if sql.startswith('CREATE TEMPORARY TABLE'):
            assert not self.in_transaction
            self.temporary[sql.split(' ')[3]]=[];return Cursor([])
        if sql.startswith('DROP TEMPORARY TABLE'):
            assert not self.in_transaction
            self.temporary.pop(sql.split(' ')[3]);return Cursor([])
        if sql.startswith('DELETE FROM'):
            assert self.in_transaction
            self.temporary[sql.split(' ')[2]]=[];return Cursor([])
        if sql.startswith('INSERT INTO'):
            assert self.in_transaction and len(args)<=500
            self.temporary[sql.split(' ')[2]].extend(args);return Cursor([])
        if sql.startswith('SELECT existing.h5_uuid'):
            assert self.in_transaction
            return Cursor([(self.collision,)] if self.collision else [])
        if sql.startswith('SELECT h5_uuid FROM'):return Cursor([] if self.empty else [('existing',)])
        raise AssertionError(sql)
    def close(self):self.closed=True;self.temporary.clear()


def catalog(connection=None):
    return SimpleNamespace(schema=SimpleNamespace(connection=connection or Connection()),
        **{kind:Relation(kind) for kind in KINDS})


class CatalogCollisionTests(unittest.TestCase):
    def test_100000_identities_stage_bounded_parameters_then_scan_existing_once(self):
        data=catalog();conn=data.schema.connection
        with CatalogCollisionLookup(data) as lookup:
            self.assertEqual(len(conn.temporary),1)  # Compatible table collations share a scratch index.
            conn.in_transaction=True
            values=[f'incoming-{number}' for number in range(100000)]
            self.assertIsNone(lookup.first_collision('Epoch',values))
            scans=[sql for sql,args in conn.calls if sql.startswith('SELECT existing.h5_uuid')]
            inserts=[args for sql,args in conn.calls if sql.startswith('INSERT INTO')]
            self.assertEqual(len(scans),1);self.assertEqual(len(inserts),500)
            self.assertEqual([value for args in inserts for value in args],values)
            self.assertEqual(list(conn.temporary.values()),[[]])
            conn.in_transaction=False
        self.assertFalse(conn.temporary)

    def test_small_or_already_indexed_relations_keep_original_bounded_check(self):
        data=catalog();conn=data.schema.connection;conn.indexed.add(data.Epoch.full_table_name)
        data.Epoch.records=['hit']
        with CatalogCollisionLookup(data) as lookup:
            conn.in_transaction=True
            self.assertEqual(lookup.first_collision('Epoch',[f'id-{n}' for n in range(500)]+['hit']),'hit')
            self.assertEqual([len(batch) for batch in data.Epoch.requests],[200,200,101])
            self.assertIsNone(lookup.first_collision('Cell',['only-one']))
            self.assertFalse(any(sql.startswith('INSERT INTO') for sql,args in conn.calls))
            conn.in_transaction=False

    def test_distinct_collations_receive_separate_compatible_scratch_indexes(self):
        data=catalog();conn=data.schema.connection;conn.collations[data.Epoch.full_table_name]='utf8mb4_bin'
        with CatalogCollisionLookup(data):
            creates=[sql for sql,args in conn.calls if sql.startswith('CREATE TEMPORARY')]
            self.assertEqual(len(creates),2)
            self.assertTrue(any('CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci' in sql for sql in creates))
            self.assertTrue(any('CHARACTER SET utf8mb4 COLLATE utf8mb4_bin' in sql for sql in creates))

    def test_candidate_values_are_never_interpolated_and_collision_returns_exact_database_value(self):
        data=catalog();conn=data.schema.connection;conn.collision='Existing-Identity'
        values=[f'id-{n}' for n in range(201)]+["quote'\\;DROP TABLE acquisition"]
        with CatalogCollisionLookup(data) as lookup:
            conn.in_transaction=True
            self.assertEqual(lookup.first_collision('Epoch',values),'Existing-Identity')
            for sql,args in conn.calls:self.assertNotIn(values[-1],sql)
            self.assertTrue(any(values[-1] in args for sql,args in conn.calls if sql.startswith('INSERT')))
            conn.in_transaction=False

    def test_setup_refuses_in_transaction_and_checks_import_lock_before_ddl(self):
        for active,owner in ((True,17),(False,99)):
            data=catalog();conn=data.schema.connection;conn.in_transaction=active;conn.lock=owner
            with self.assertRaises(RuntimeError):CatalogCollisionLookup(data).prepare()
            self.assertFalse(any(sql.startswith('CREATE') for sql,args in conn.calls))

    def test_empty_catalog_skips_candidate_inserts_and_lost_lock_blocks_reads(self):
        data=catalog();conn=data.schema.connection
        with CatalogCollisionLookup(data) as lookup:
            conn.in_transaction=True;conn.empty=True
            self.assertIsNone(lookup.first_collision('Epoch',list(map(str,range(501)))))
            self.assertFalse(any(sql.startswith('INSERT') for sql,args in conn.calls))
            conn.lock=99
            with self.assertRaisesRegex(RuntimeError,'owning connection or import lock'):
                lookup.first_collision('Epoch',['one'])
            conn.lock=17;conn.in_transaction=False

    def test_failed_insert_is_not_retried_with_a_weaker_check(self):
        data=catalog();conn=data.schema.connection
        with CatalogCollisionLookup(data) as lookup:
            conn.in_transaction=True;conn.fail='INSERT INTO'
            with self.assertRaisesRegex(OSError,'injected'):
                lookup.first_collision('Epoch',list(map(str,range(501))))
            self.assertFalse(data.Epoch.requests)
            conn.fail=None;conn.in_transaction=False

    def test_cleanup_failure_closes_only_owning_connection(self):
        data=catalog();conn=data.schema.connection;lookup=CatalogCollisionLookup(data).prepare()
        conn.fail='DROP TEMPORARY'
        with self.assertRaisesRegex(RuntimeError,'owning connection was closed'):lookup.close()
        self.assertTrue(conn.closed);self.assertFalse(conn.temporary)

    def test_relation_doubles_and_unsupported_column_metadata_keep_exact_original_guard(self):
        data=catalog(SimpleNamespace())
        data.Cell.records=['hit']
        with CatalogCollisionLookup(data) as lookup:
            self.assertEqual(lookup.first_collision('Cell',['hit']),'hit')
        data=catalog();data.Cell.full_table_name='unsafe;not-an-identifier'
        data.Cell.records=['hit']
        with CatalogCollisionLookup(data) as lookup:
            data.schema.connection.in_transaction=True
            self.assertEqual(lookup.first_collision('Cell',['hit']),'hit')
            data.schema.connection.in_transaction=False

    def test_import_reports_cleanup_failure_after_commit_as_committed(self):
        import test_workspace_import_identities as fixture
        lookup=Mock()
        lookup.close.side_effect=[RuntimeError('scratch cleanup failed'),None]
        with patch('workspace_catalog_collision.CatalogCollisionLookup',return_value=lookup):
            with self.assertRaisesRegex(RuntimeError,'scratch cleanup failed') as caught:
                fixture.ImportIdentityTests().same_sha_existing_project()
        self.assertTrue(caught.exception.catalog_committed)
        self.assertEqual(caught.exception.workflow_stage,'workspace_files')
        lookup.prepare.assert_called_once()
        self.assertEqual(lookup.close.call_count,2)

    def test_import_setup_failure_preserves_failure_without_claiming_commit(self):
        import test_workspace_import_identities as fixture
        lookup=Mock();lookup.prepare.side_effect=RuntimeError('scratch setup failed')
        with patch('workspace_catalog_collision.CatalogCollisionLookup',return_value=lookup):
            with self.assertRaisesRegex(RuntimeError,'scratch setup failed') as caught:
                fixture.ImportIdentityTests().same_sha_existing_project()
        self.assertIsNone(caught.exception.catalog_committed)
        self.assertEqual(caught.exception.workflow_stage,'database_transaction')
        lookup.close.assert_called_once()


if __name__=='__main__':unittest.main()
