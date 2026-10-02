"""Whole-group receipt recovery compatibility; disposable file doubles only."""
import copy
import json
import sys
import types
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import workspace_recovery_store as recovery
from workspace_state_snapshot import (LEGACY_TABLES, WORKBENCH_TABLES, TABLES,
    migrate_restore_tables, restore_table_order)
from workspace_recovery_generation import TABLE_NAMES, TABLE_IDS
from test_workspace_recovery_store import scientific_fixture, canonical, identity


class GroupRecoveryTests(unittest.TestCase):
    def test_table_ordinals_append_and_restore_migrates_without_changing_workbench(self):
        self.assertEqual(TABLES[:-1],WORKBENCH_TABLES)
        self.assertEqual(WORKBENCH_TABLES[:len(LEGACY_TABLES)],LEGACY_TABLES)
        self.assertEqual(TABLES[-1],'annotation_group_receipt')
        self.assertEqual(TABLE_NAMES[-1],'annotation_group_receipt')
        self.assertEqual(TABLE_IDS['annotation_group_receipt'],18)
        for old in (LEGACY_TABLES,WORKBENCH_TABLES):
            state,_=scientific_fixture()
            state['tables']={table:state['tables'][table] for table in old}
            if old==WORKBENCH_TABLES:
                state['tables']['workbench_draft']=[dict(project_uuid=identity(1),actor='exact actor',version=2)]
                state['tables']['workbench_decision']=[dict(epoch_uuid=identity(20),reviewed=True)]
                state['tables']['workbench_receipt']=[dict(operation_uuid=identity(70),receipt={'binding':{'version':3}})]
            previous=copy.deepcopy(state['tables'])
            migrate_restore_tables(state)
            self.assertEqual({name:state['tables'][name] for name in old},previous)
            self.assertEqual(set(state['tables']),set(TABLES))
            self.assertEqual(state['tables']['annotation_group_receipt'],[])
            order=restore_table_order(dict(reversed(list(state['tables'].items()))))
            self.assertLess(order.index('workbench_draft'),order.index('workbench_decision'))

    def test_old_workbench_mirror_loads_with_exact_prior_rows_and_no_new_receipt(self):
        state,keys=scientific_fixture()
        state['tables']={table:state['tables'][table] for table in WORKBENCH_TABLES}
        state['tables']['workbench_receipt']=[dict(project_uuid=identity(1),operation_uuid=identity(70),
            candidate_revision_uuid=identity(50),receipt={'actor':'kept','accepted_fingerprints':{identity(20):'b'*64}})]
        keys['workbench_receipt']=['project_uuid','operation_uuid']
        with tempfile.TemporaryDirectory() as folder:
            with patch('workspace_state_snapshot.TABLES',WORKBENCH_TABLES):
                recovery.write(folder,state=copy.deepcopy(state),keys=keys,watermark={'generation':0})
            stored=recovery.inspect(folder)
            loaded=recovery.load_database(stored['path'],expected=stored['pointer'])
            self.assertEqual(canonical(loaded),canonical(state))
            migrate_restore_tables(loaded)
            self.assertEqual(loaded['tables']['workbench_receipt'],state['tables']['workbench_receipt'])
            self.assertEqual(loaded['tables']['annotation_group_receipt'],[])

    def test_1857_changed_only_inverse_receipt_incremental_after_image_round_trip(self):
        state,keys=scientific_fixture()
        keys['annotation_group_receipt']=['project_uuid','operation_uuid']
        inverse=[dict(epoch_uuid=identity(1000+i),metadata_hash='b'*64,after_revision=1) for i in range(1857)]
        row=dict(project_uuid=identity(1),operation_uuid=identity(70),actor='actor',profile_uuid=identity(40),
            request_sha256='a'*64,created_at='2026-10-02T00:00:00',receipt=dict(
                changed=1857,inverse=inverse,scope={'kind':'server_frozen_group'},undone=False))
        columns={table:list(state['tables'][table][0]) if state['tables'][table] else list(names)
            for table,names in keys.items()}
        columns['annotation_group_receipt']=list(row)
        with tempfile.TemporaryDirectory() as folder:
            recovery.write(folder,state=copy.deepcopy(state),keys=keys,columns=columns,watermark={'generation':0})
            header=copy.deepcopy(state);header['tables']={table:[] for table in TABLES}
            recovery.write(folder,state=header,keys=keys,watermark={'generation':1},
                changes={'annotation_group_receipt':[row]})
            stored=recovery.inspect(folder)
            loaded=recovery.load_database(stored['path'],expected=stored['pointer'])
            self.assertEqual(loaded['tables']['annotation_group_receipt'],[row])
            prior={**loaded,'tables':{table:loaded['tables'][table] for table in WORKBENCH_TABLES}}
            expected={**state,'tables':{table:state['tables'][table] for table in WORKBENCH_TABLES}}
            self.assertEqual(canonical(prior),canonical(expected))
            changed={**row,'receipt':{**row['receipt'],'undone':True}}
            recovery.write(folder,state=header,keys=keys,watermark={'generation':2},
                changes={'annotation_group_receipt':[changed]})
            stored=recovery.inspect(folder)
            reopened=recovery.load_database(stored['path'],expected=stored['pointer'])
            self.assertEqual(reopened['tables']['annotation_group_receipt'],[changed])
            self.assertEqual(stored['header']['table_seals']['annotation_group_receipt']['count'],1)


class GroupRecoveryHookTests(unittest.TestCase):
    """API integration only: group authority/mutation is owned by its module."""
    def setUp(self):
        from test_workspace_api import WorkspaceAPITests
        from workspace_api import create_app
        module=types.ModuleType('workspace_annotation_groups')
        module.group_receipt_table=Mock()
        self.registered=[];self.operations={};self.writes=0;self.stages=[]
        def register(app,service,shared,db_lock,registration_locks,*,revision_guard=None,receipt_table=None):
            self.registered.append((receipt_table,revision_guard))
            def preview():return {'count':1857,'kind':'server_frozen_group'}
            def apply():
                from flask import request
                operation=request.get_json()['operation_uuid']
                if operation not in self.operations:
                    self.writes+=1
                    self.operations[operation]={'operation_uuid':operation,'changed':1857}
                return self.operations[operation]
            app.add_url_rule('/api/annotations/group-preview','group_annotation_preview',preview,methods=['POST'])
            app.add_url_rule('/api/annotations/group-preview-release','group_annotation_preview_release',
                lambda:{'released':True},methods=['POST'])
            app.add_url_rule('/api/annotations/group','group_annotation_apply',apply,methods=['POST'])
            app.add_url_rule('/api/annotations/group/<original>/undo','group_annotation_undo',
                lambda original:apply(),methods=['POST'])
        module.register_group_annotation_routes=register
        previous=sys.modules.get('workspace_annotation_groups')
        sys.modules['workspace_annotation_groups']=module
        def restore_module():
            if previous is None:sys.modules.pop('workspace_annotation_groups',None)
            else:sys.modules['workspace_annotation_groups']=previous
        self.addCleanup(restore_module)
        self.fixture=WorkspaceAPITests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.service.dj.Schema=object()
        self.save=Mock(side_effect=lambda *args,**kwargs:self.stages.append('save'))
        def declare(_):
            self.stages.append('ddl')
            return self.fixture.group_receipts
        def bootstrap(*args,**kwargs):
            self.stages.append('generation')
            return Mock()
        with patch.object(module,'group_receipt_table',side_effect=declare), \
                patch('workspace_annotations.SharedAnnotations',return_value=None), \
                patch('workspace_state_generation.bootstrap',side_effect=bootstrap), \
                patch('workspace_state_snapshot.save',self.save):
            self.app=create_app(self.fixture.temp.name,self.fixture.temp.name,service=self.fixture.service,
                store=self.fixture.store,explorer_history=self.fixture.explorer_history,
                data_stores=self.fixture.data_stores,protocol_suggestions=self.fixture.protocol_suggestions)
        self.addCleanup(self.app.extensions['app_state_session_lock'].close)
        self.addCleanup(lambda:self.app.extensions['backup_scheduler'].close(flush=False))
        self.client=self.app.test_client()
        self.save.reset_mock()

    def test_native_receipt_ddl_precedes_generation_and_initial_save_reused_on_registration(self):
        self.assertEqual(self.stages,['ddl','generation','save'])
        self.assertIs(self.registered[-1][0],self.fixture.group_receipts)
        self.assertTrue(callable(self.registered[-1][1]))

    def test_preview_readonly_apply_inverse_and_receipt_replay_checkpoint_every_time(self):
        response=self.client.post('/api/annotations/group-preview',json={},headers=self.fixture.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        response=self.client.post('/api/annotations/group-preview-release',
            json={'selection_uuid':identity(72)},headers=self.fixture.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.save.assert_not_called()
        body={'operation_uuid':identity(70)}
        for _ in range(2):
            response=self.client.post('/api/annotations/group',json=body,headers=self.fixture.headers)
            self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(self.writes,1)
        response=self.client.post('/api/annotations/group/'+identity(70)+'/undo',
            json={'operation_uuid':identity(71)},headers=self.fixture.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(self.save.call_count,3)

    def test_507_retains_committed_operation_and_identical_replay_flushes_without_rewrite(self):
        body={'operation_uuid':identity(70)}
        self.save.side_effect=OSError('Disk full')
        with self.assertLogs(self.app.logger,level='ERROR'):
            response=self.client.post('/api/annotations/group',json=body,headers=self.fixture.headers)
        self.assertEqual(response.status_code,507,response.get_json())
        value=response.get_json()
        self.assertTrue(value['saved'])
        self.assertEqual(value['code'],'recovery_unconfirmed')
        self.assertEqual(value['operation_uuid'],body['operation_uuid'])
        self.assertEqual(value['persistence']['database'],'committed')
        self.assertEqual(value['persistence']['backup']['status'],'degraded')
        self.assertEqual(self.writes,1)
        self.save.side_effect=None
        response=self.client.post('/api/annotations/group',json=body,headers=self.fixture.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.get_json()['operation_uuid'],body['operation_uuid'])
        self.assertEqual(self.writes,1)
        self.assertEqual(self.save.call_count,2)


if __name__=='__main__':unittest.main()
