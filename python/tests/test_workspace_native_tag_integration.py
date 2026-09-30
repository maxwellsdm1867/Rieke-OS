"""Opt-in native autocomplete, lifecycle checkpoint and export integration."""
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from test_workspace_state_generation import NativeConnection
from workspace_annotations import SharedAnnotations
from workspace_annotation_preparation import prepare_project_annotations
from workspace_native_tag_lookup import TABLE,MARKER,TRIGGER_MANIFEST,NativeTagLookup
from workspace_projects import create_project
from workspace_state_generation import bootstrap as generation_bootstrap,verify_export_triggers
from workspace_state_snapshot import save as save_recovery
import workspace_native_mysql as native


def identity(number):return str(uuid.UUID(int=number))


@unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_MYSQL')=='1','opt-in disposable native tag integration')
class NativeTagIntegrationTests(unittest.TestCase):
    def setUp(self):
        import pymysql
        self.temporary=tempfile.TemporaryDirectory(prefix='rieke-native-tag-integration-')
        self.root=Path(create_project(Path(self.temporary.name)/'projects','Native tag integration')['path'])
        self.connection=None
        self.addCleanup(self.cleanup)
        native.ensure_native_database(self.root)
        self.connection=NativeConnection(pymysql.connect(**native.connection_parameters(self.root),autocommit=True))
        self.connection.query('CREATE DATABASE recording_workspace')
        for sql in (
            'CREATE TABLE recording_workspace.curation (project_uuid varchar(36),protocol_uuid varchar(36),epoch_uuid varchar(36),tags JSON NOT NULL,revision int NOT NULL,PRIMARY KEY(project_uuid,protocol_uuid,epoch_uuid)) ENGINE=InnoDB',
            "CREATE TABLE recording_workspace.shared_annotation (project_uuid varchar(36),target_kind enum('cell','epoch'),target_uuid varchar(36),profile_uuid varchar(36),tags JSON NOT NULL,author_name varchar(120) NOT NULL,revision int NOT NULL,updated_at datetime NOT NULL,PRIMARY KEY(project_uuid,target_kind,target_uuid,profile_uuid)) ENGINE=InnoDB",
            'CREATE TABLE recording_workspace.annotation_profile (project_uuid varchar(36),profile_uuid varchar(36),display_name varchar(120),PRIMARY KEY(project_uuid,profile_uuid)) ENGINE=InnoDB'):
            self.connection.query(sql)
        self.project=json.loads((self.root/'project.json').read_text());self.project_id=self.project['project_uuid']
        self.service=SimpleNamespace(project_dir=self.root,project=self.project,dj=SimpleNamespace(conn=lambda:self.connection),_ready=lambda:None)
        self.shared=SharedAnnotations(self.service,tables=(None,None,None))
        self.shared.state_generation=generation_bootstrap(self.connection,self.project_id)
        self.assertTrue(self.shared.state_generation.ready,self.shared.state_generation.reason)
        self.assertIsNotNone(self.shared.generation_token())
        self.store=SimpleNamespace()

    def cleanup(self):
        if self.connection is not None:self.connection._conn.close()
        native.stop_native_database(self.root);self.temporary.cleanup()

    def prepare(self,**kwargs):
        report=prepare_project_annotations(self.service,self.store,self.shared,**kwargs)
        self.assertEqual(report['status'],'ready',report)
        return report

    def write(self,kind,target,profile,tags,name):
        self.connection.query('REPLACE INTO recording_workspace.shared_annotation '
            '(project_uuid,target_kind,target_uuid,profile_uuid,tags,author_name,revision,updated_at) VALUES (%s,%s,%s,%s,%s,%s,1,%s)',
            (self.project_id,kind,target,profile,json.dumps(tags),name,dt.datetime(2026,9,30,12)))

    def canonical(self):
        rows=self.connection.query('SELECT target_kind,target_uuid,profile_uuid,tags,author_name '
            'FROM recording_workspace.shared_annotation WHERE project_uuid=%s ORDER BY target_kind,target_uuid,profile_uuid',
            (self.project_id,),as_dict=True).fetchall()
        for row in rows:row['tags']=json.loads(row['tags'])
        return rows

    def oracle(self,query,limit):
        values={}
        for row in self.canonical():
            for tag in row['tags']:
                record=values.setdefault(tag,{'targets':set(),'authors':{}})
                record['targets'].add((row['target_kind'],row['target_uuid']))
                record['authors'][row['profile_uuid']]=row['author_name']
        selected=[(tag,row) for tag,row in values.items() if tag.casefold().startswith(query.strip().casefold())]
        selected.sort(key=lambda value:(-len(value[1]['targets']),value[0].casefold(),value[0]))
        return {'tags':[{'tag':tag,'count':len(row['targets']),
            'authors':[{'profile_uuid':key,'display_name':name} for key,name in sorted(row['authors'].items())]}
            for tag,row in selected[:limit]],'total':len(selected),'has_more':len(selected)>limit}

    def seed_authors(self):
        for profile,name in ((identity(101),'Current profile one'),(identity(102),'Current profile two')):
            self.connection.query('INSERT INTO recording_workspace.annotation_profile VALUES (%s,%s,%s)',(self.project_id,profile,name))
        cases=[('cell',201,101,['QC','Straße','é','İ'],'Cell-era name'),
            ('epoch',1,101,['QC','STRASSE','e\u0301','i'],'Earlier epoch alias'),
            ('epoch',1,102,['QC','STRASSE','é'],'Second historical scientist'),
            ('epoch',2,101,['QC','Straße','é','İ'],'Latest epoch alias'),
            ('epoch',3,101,['other'],'Later unrelated alias'),
            ('epoch',4,102,['qc','😀'*255],'Other historical scientist'),
            ('cell',202,101,['STRASSE'],'Later cell alias')]
        for kind,target,profile,tags,name in cases:self.write(kind,identity(target),identity(profile),tags,name)

    def test_autocomplete_matches_canonical_unicode_counts_and_historical_authors(self):
        self.seed_authors();self.prepare()
        with patch.object(self.shared,'_membership_index',side_effect=AssertionError('Native autocomplete must not open SQLite')):
            for query in ('',' qC ','STRASSE','strass','é','e\u0301','i','i\u0307','😀','no match'):
                for limit in (1,3,100):
                    with self.subTest(query=query,limit=limit):
                        result=self.shared.suggestions(query,limit);expected=self.oracle(query,limit)
                        self.assertEqual({key:result[key] for key in expected},expected)
            qc=next(row for row in self.shared.suggestions('',100)['tags'] if row['tag']=='QC')
            self.assertEqual(qc['count'],3) # One epoch has two profiles, still one target.
            self.assertEqual(qc['authors'],[{'profile_uuid':identity(101),'display_name':'Latest epoch alias'},
                {'profile_uuid':identity(102),'display_name':'Second historical scientist'}])
            self.connection.query('UPDATE recording_workspace.annotation_profile SET display_name=%s WHERE project_uuid=%s',('Renamed current profile',self.project_id))
            self.assertEqual(self.shared.suggestions('QC',100)['tags'],self.oracle('QC',100)['tags'])
            self.write('epoch',identity(2),identity(101),['new'],'New saved author')
            self.assertEqual(self.shared.suggestions('QC',100)['tags'],self.oracle('QC',100)['tags'])

    def test_lifecycle_bootstrap_checkpoint_reopen_and_dropped_trigger_rebuild(self):
        self.write('epoch',identity(1),identity(101),['before'],'Original author')
        first=self.prepare(reuse=True);self.assertFalse(first['reused'])
        lookup=self.shared.native_tag_lookup;self.assertEqual(lookup.targets('before'),{('epoch',identity(1))})
        self.write('epoch',identity(1),identity(101),['after'],'Edited author')
        self.assertEqual(self.connection.query(f'SELECT dirty FROM recording_workspace.{MARKER} WHERE project_uuid=%s',(self.project_id,)).fetchone()[0],1)
        second=self.prepare();self.assertTrue(second['reused']);self.assertIs(self.shared.native_tag_lookup,lookup)
        self.assertEqual(self.connection.query(f'SELECT dirty FROM recording_workspace.{MARKER} WHERE project_uuid=%s',(self.project_id,)).fetchone()[0],0)
        # A fresh annotation facade simulates reopen without retaining the lookup.
        self.shared=SharedAnnotations(self.service,tables=(None,None,None))
        self.shared.state_generation=generation_bootstrap(self.connection,self.project_id)
        reopened=self.prepare(reuse=True);self.assertTrue(reopened['reused'])
        original=self.shared.native_tag_lookup
        trigger=next(name for name in TRIGGER_MANIFEST if name.endswith('_au'))
        self.connection.query('DROP TRIGGER recording_workspace.'+trigger)
        self.connection.query('UPDATE recording_workspace.shared_annotation SET tags=%s,revision=revision+1 WHERE project_uuid=%s',
            (json.dumps(['written during gap']),self.project_id))
        self.assertNotEqual(self.shared.generation_token().authority,original.authority)
        rebuilt=self.prepare();self.assertFalse(rebuilt['reused'])
        self.assertIsNot(self.shared.native_tag_lookup,original)
        self.assertEqual(self.shared.native_tag_lookup.targets('after'),set())
        self.assertEqual(self.shared.native_tag_lookup.targets('written during gap'),{('epoch',identity(1))})
        self.assertTrue(self.shared.native_tag_lookup.validate_current())

    def test_protocol_preparation_is_bounded_without_shared_sqlite_and_fences_changes(self):
        from workspace_protocol_state import STATE_CACHE_SCOPES
        self.service.protocols={identity(n):{} for n in range(1,STATE_CACHE_SCOPES+4)}
        warmed=[];phases=[]
        reader=SimpleNamespace(native_context=lambda key:warmed.append(key) or {})
        with patch.object(self.shared,'_membership_index',side_effect=AssertionError('Protocol preparation must not warm SQLite')):
            report=self.prepare(protocol_state=reader,progress=phases.append)
        self.assertEqual(warmed,list(self.service.protocols)[:STATE_CACHE_SCOPES])
        self.assertEqual(report['protocols_prepared'],STATE_CACHE_SCOPES)
        self.assertEqual(report['protocols_deferred'],3)
        self.assertIn('preparing_protocol_reads',phases)
        def concurrent_edit(key):
            if key==next(iter(self.service.protocols)):
                self.write('epoch',identity(1),identity(101),['during warm'],'Author')
            return {}
        reader.native_context=concurrent_edit
        report=prepare_project_annotations(self.service,self.store,self.shared,protocol_state=reader)
        self.assertEqual(report['status'],'failed',report)
        self.assertFalse(self.shared.native_tag_lookup.ready)

    def test_checkpoint_rejects_source_change_after_proof_without_clearing_dirty(self):
        self.write('epoch',identity(1),identity(101),['start'],'Author');self.prepare()
        original=NativeTagLookup.checkpoint
        def race(lookup,proof,**kwargs):
            self.connection.query('UPDATE recording_workspace.shared_annotation SET tags=%s,revision=revision+1 WHERE project_uuid=%s',
                (json.dumps(['changed after proof']),self.project_id))
            return original(lookup,proof,**kwargs)
        with patch.object(NativeTagLookup,'checkpoint',race):
            report=prepare_project_annotations(self.service,self.store,self.shared)
        self.assertEqual(report['status'],'failed',report)
        marker=self.connection.query(f'SELECT dirty FROM recording_workspace.{MARKER} WHERE project_uuid=%s',(self.project_id,)).fetchone()[0]
        self.assertEqual(marker,1,'A rejected proof must not clear the durable sticky dirty flag')
        self.prepare();self.assertEqual(self.shared.native_tag_lookup.targets('changed after proof'),{('epoch',identity(1))})

    def test_utf8_canonical_trigger_delete_uses_ascii_primary_key_with_unrelated_rows(self):
        from workspace_native_tag_lookup import _delete
        # Every target has five memberships. Unrelated targets must not turn a
        # ten-target edit into ten scans of all 7,500 index records.
        records=[(self.project_id,'epoch',identity(n),identity(101),json.dumps(['one','two','three','four','five']),
            'Historical author',1,dt.datetime(2026,9,30,12)) for n in range(1,1501)]
        cursor=self.connection._conn.cursor()
        cursor.executemany('INSERT INTO recording_workspace.shared_annotation VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',records)
        self.prepare()
        columns=self.connection.query('SELECT TABLE_NAME,CHARACTER_SET_NAME FROM information_schema.COLUMNS '
            "WHERE TABLE_SCHEMA='recording_workspace' AND TABLE_NAME IN ('shared_annotation','app_shared_tag_lookup') AND COLUMN_NAME='target_uuid'",as_dict=True).fetchall()
        charsets={row['TABLE_NAME']:row['CHARACTER_SET_NAME'] for row in columns}
        self.assertEqual(charsets['app_shared_tag_lookup'],'ascii')
        self.assertIn(charsets['shared_annotation'],('utf8mb3','utf8mb4'))
        statement=_delete('OLD')
        fields=('project_uuid','target_kind','target_uuid','profile_uuid')
        for field in fields:statement=statement.replace('OLD.'+field,'p_'+field)
        parameters=','.join('IN p_'+field+' VARCHAR(36) CHARACTER SET '+charsets['shared_annotation'] for field in fields)
        self.connection.query('CREATE PROCEDURE recording_workspace.explain_indexed_tag_delete('+parameters+
            ') BEGIN EXPLAIN FORMAT=JSON '+statement+' END')
        plan=json.loads(self.connection.query('CALL recording_workspace.explain_indexed_tag_delete(%s,%s,%s,%s)',
            (self.project_id,'epoch',identity(1),identity(101))).fetchone()[0])['query_block']['table']
        self.assertEqual(plan['key'],'PRIMARY',plan)
        self.assertEqual(plan['access_type'],'range',plan)
        self.assertEqual(plan['used_key_parts'],list(fields),plan)
        def scanned():
            return {key:int(value) for key,value in self.connection.query("SHOW SESSION STATUS WHERE Variable_name IN ('Handler_read_next','Handler_read_rnd_next')").fetchall()}
        before=scanned()
        with self.connection.transaction:
            for number in range(1,11):
                self.connection.query('UPDATE recording_workspace.shared_annotation SET tags=%s,revision=revision+1 '
                    'WHERE project_uuid=%s AND target_kind=%s AND target_uuid=%s AND profile_uuid=%s',
                    (json.dumps(['edited']),self.project_id,'epoch',identity(number),identity(101)))
        after=scanned()
        self.assertLess(sum(after[key]-before[key] for key in before),1000,'Ten edits must not scan 7,500 unrelated memberships each')
        self.assertEqual(self.shared.native_tag_lookup.targets('edited'),{('epoch',identity(n)) for n in range(1,11)})
        self.assertEqual(len(self.shared.native_tag_lookup.targets('one')),1490)
        from workspace_native_tag_filter import suggestions
        lookup=self.shared.native_tag_lookup;queries=[];query_reads=[];original=lookup._rows
        def capture(sql,args=()):
            queries.append((sql,args));start=scanned();rows=original(sql,args);end=scanned()
            query_reads.append(sum(end[key]-start[key] for key in start))
            return rows
        before=scanned()
        with patch.object(lookup,'_rows',side_effect=capture):result=suggestions(lookup,'edited',30)
        after=scanned()
        self.assertEqual(result['tags'],[{'tag':'edited','count':10,
            'authors':[{'profile_uuid':identity(101),'display_name':'Historical author'}]}])
        dictionary_plan=json.loads(self.connection.query('EXPLAIN FORMAT=JSON '+queries[0][0],queries[0][1]).fetchone()[0])
        self.assertLess(sum(query_reads[1:]),1000,'Counts and authors must avoid unrelated memberships')
        dictionary_table=dictionary_plan['query_block']['grouping_operation']['table']
        self.assertEqual(dictionary_table['key'],'by_tag')
        self.assertTrue(dictionary_table.get('using_index') or dictionary_table.get('using_index_for_group_by'))
        for sql,args in queries[1:3]:
            plan=json.loads(self.connection.query('EXPLAIN FORMAT=JSON '+sql,args).fetchone()[0])
            self.assertIn('"key": "by_tag"',json.dumps(plan))
        source_sql,source_args=next((sql,args) for sql,args in queries if '`shared_annotation`' in sql)
        source_plan=json.loads(self.connection.query('EXPLAIN FORMAT=JSON '+source_sql,source_args).fetchone()[0])['query_block']['table']
        self.assertEqual(source_plan['key'],'PRIMARY')
        self.assertEqual(source_plan['used_key_parts'],list(fields))

    def test_export_omits_only_exact_managed_trigger_contracts(self):
        self.write('epoch',identity(1),identity(101),['tag'],'Author');self.prepare()
        report=verify_export_triggers(self.connection,('recording_workspace',))
        self.assertTrue(report['managed_present']);self.assertTrue(report['safe_to_omit'],report)
        self.connection.query('CREATE TRIGGER recording_workspace.scientific_custom_audit AFTER INSERT ON recording_workspace.shared_annotation FOR EACH ROW SET @last_scientific_target=NEW.target_uuid')
        refused=verify_export_triggers(self.connection,('recording_workspace',))
        self.assertFalse(refused['safe_to_omit'])
        self.connection.query('DROP TRIGGER recording_workspace.scientific_custom_audit')
        trigger=next(name for name in TRIGGER_MANIFEST if name.endswith('_ai'))
        self.connection.query('DROP TRIGGER recording_workspace.'+trigger)
        self.connection.query('CREATE TRIGGER recording_workspace.'+trigger+' AFTER INSERT ON recording_workspace.shared_annotation FOR EACH ROW SET @altered_lookup=NEW.target_uuid')
        refused=verify_export_triggers(self.connection,('recording_workspace',))
        self.assertFalse(refused['safe_to_omit'])

    def test_bootstrap_rejects_source_change_after_refreshed_proof(self):
        import workspace_native_tag_lookup as module
        self.write('epoch',identity(1),identity(101),['start'],'Author');self.prepare()
        self.shared.native_tag_lookup=None
        original=module.bootstrap
        def race(*args,**kwargs):
            provider=kwargs['proof_provider']
            def changed_after_proof():
                proof=provider()
                self.connection.query('UPDATE recording_workspace.shared_annotation SET tags=%s,revision=revision+1 WHERE project_uuid=%s',
                    (json.dumps(['changed before backfill']),self.project_id))
                return proof
            kwargs['proof_provider']=changed_after_proof
            return original(*args,**kwargs)
        with patch.object(module,'bootstrap',side_effect=race):
            report=prepare_project_annotations(self.service,self.store,self.shared)
        self.assertEqual(report['status'],'failed',report)
        dirty=self.connection.query(f'SELECT dirty FROM recording_workspace.{MARKER} WHERE project_uuid=%s',(self.project_id,)).fetchone()[0]
        self.assertEqual(dirty,1)
        self.prepare();self.assertEqual(self.shared.native_tag_lookup.targets('changed before backfill'),{('epoch',identity(1))})


if __name__=='__main__':unittest.main()
