"""Server query receipt/whole-operation rollback using disposable SQL doubles."""
import copy
import json
from contextlib import contextmanager,nullcontext
from threading import RLock
import unittest
from unittest.mock import patch
import uuid

import test_workspace_annotation_batch_guard as guard_fixture
from test_workspace_curation import Table
from workspace_annotation_groups import AnnotationGroups,RetainedBudget,register_group_annotation_routes
from workspace_curation import RevisionConflict
from workspace_recipes import checksum
from workspace_tree import joint_id
from workspace_tree_pages import TreePages


class Authority:
    def __init__(self,case):self.case=case;self.fixed=None;self.locked=[]
    def token(self,protocol=None):
        return self.fixed or dict(authority='test native authority',shared=self.case.store.change_revision(),protocol=protocol)
    def assert_current_locked(self,token):
        if not self.case.connection.in_transaction:raise AssertionError('Generation gate must be inside outer transaction')
        self.locked.append(token['protocol'])
        if token!=self.token(token['protocol']):raise RevisionConflict({'generation':'changed'})


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.case=guard_fixture.GuardedBatchTests();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.service=self.case.case.service;self.store=self.case.store
        self.receipts=Table(('project_uuid','operation_uuid'))
        self.case.connection.delegate.tables.append(self.receipts)
        self.tracker=Authority(self.case)
        self.service._explore_state_generation=self.tracker
        verified=patch.object(self.service,'_verified_source',return_value=('owned synthetic source','signature'))
        verified.start();self.addCleanup(verified.stop)
        self.groups=AnnotationGroups(self.service,self.store,self.receipts,RLock(),nullcontext)
        self.profile=self.case.case.author

    def grow(self,count):
        template=self.service.rows[self.case.case.first]
        self.service.rows={};self.service.details={};self.service._fingerprints={}
        for index in range(count):
            key=str(uuid.UUID(int=index+1))
            self.service.rows[key]={**template,'epoch_uuid':key,'epoch_number':index+1}
            self.service.details[key]={'parameters':{'value':index%3},'properties':{},'attributes':{},'metadata':{}}
            self.service._fingerprints[key]='b'*64
        self.service.protocols[self.service.protocol_id]['result']['epochs']=[
            {'uuid':key,'metadata_hash':'b'*64} for key in self.service.rows]

    def preview(self,scope=None):
        scope=scope or {'splits':''}
        page=TreePages(self.service).page({key:value for key,value in scope.items() if key!='path'})
        return self.groups.preview({'scope':{**scope,'revision':page['revision']},'profile_uuid':self.profile},'OS actor')

    def body(self,preview,tag='server group'):
        return dict(selection_uuid=preview['selection_uuid'],profile_uuid=self.profile,tag=tag,operation_uuid=str(uuid.uuid4()))

    def test_1857_complete_server_targets_small_response_replay_and_changed_only_undo(self):
        self.grow(1857)
        first=next(iter(self.service.rows))
        self.store.update('epoch',[first],self.profile,{'tags_add':['server group']},{first:0},'OS actor')
        preview=self.preview();self.assertEqual(preview['count'],1857)
        self.assertNotIn('target_uuids',json.dumps(preview))
        body=self.body(preview);result=self.groups.apply(body,'OS actor')
        self.assertEqual((result['target_count'],result['changed'],result['unchanged']),(1857,1856,1))
        self.assertLess(len(json.dumps(result)),2048)
        self.assertEqual(len(self.case.case.records.rows),1857)
        self.groups.selections.clear()
        with patch.object(self.service,'_ready',side_effect=AssertionError('Receipt-first replay')):
            replay=self.groups.apply(body,'OS actor')
        self.assertTrue(replay['replayed'])
        operation=str(uuid.uuid4())
        undone=self.groups.undo(body['operation_uuid'],{'operation_uuid':operation},'OS actor')
        self.assertEqual(undone['changed'],1856)
        tags={row['target_uuid']:row['tags'] for row in self.case.case.records.rows}
        self.assertEqual(tags[first],['server group'])
        self.assertTrue(all(value==[] for key,value in tags.items() if key!=first))
        self.assertTrue(self.groups.undo(body['operation_uuid'],{'operation_uuid':operation},'OS actor')['replayed'])

    def test_native_empty_layout_has_no_projected_values_and_selects_complete_scope(self):
        self.grow(1857);original=TreePages._scope
        def empty_projection(tree,scope):
            rows,catalog,values,definitions,order,revision=original(tree,scope)
            self.assertEqual(order,[])
            return rows,catalog,{},definitions,order,revision
        with patch.object(TreePages,'_scope',empty_projection):
            preview=self.preview({'splits':'','path':[]})
        self.assertEqual(preview['count'],1857)
        result=self.groups.apply(self.body(preview),'OS actor')
        self.assertEqual(result['changed'],1857)
        self.assertEqual({row['target_uuid'] for row in self.case.case.records.rows},set(self.service.rows))

    def test_empty_path_without_projection_keeps_predicate_scope_and_nonempty_path_fails_closed(self):
        self.grow(12);original=TreePages._scope
        def no_values(tree,scope):
            rows,catalog,values,definitions,order,revision=original(tree,scope)
            return rows,catalog,{},definitions,order,revision
        scope={'splits':'','predicate':{'field':'parameters/value','operator':'eq','value':1}}
        with patch.object(TreePages,'_scope',no_values):preview=self.preview(scope)
        wanted={key for key,value in self.service.details.items() if value['parameters']['value']==1}
        self.assertEqual({row[0] for row in self.groups.selections[preview['selection_uuid']]['targets']},wanted)
        self.groups.release({'selection_uuid':preview['selection_uuid']},'OS actor')
        scope={'splits':'parameters/value'};root=TreePages(self.service).page(scope)
        body={'scope':{**scope,'path':root['branches'][0]['path'],'revision':root['revision']},'profile_uuid':self.profile}
        with patch.object(TreePages,'_scope',no_values),self.assertRaises(KeyError):
            self.groups.preview(body,'OS actor')
        self.assertEqual(self.groups.selections,{})
        self.assertEqual(self.receipts.rows,[])
        self.assertEqual(self.case.case.records.rows,[])

    def test_private_plan_supports_over2000_without_weakening_public_batch(self):
        self.grow(2001)
        preview=self.preview();body=self.body(preview)
        self.assertEqual(self.groups.apply(body,'OS actor')['changed'],2001)
        operations=[self.case.operation(target) for target in self.service.rows]
        with self.assertRaisesRegex(ValueError,'2000'):
            self.store.apply_batch(operations,'OS actor')

    def test_protocol_predicate_path_freezes_exact_subset(self):
        self.grow(35)
        scope={'protocol_uuid':self.service.protocol_id,'splits':'parameters/value',
            'filters':{'metadata_predicate':json.dumps({'not':{'field':'parameters/value','operator':'eq','value':2}})}}
        root=TreePages(self.service).page(scope)
        branch=root['branches'][1]
        preview=self.preview({**scope,'path':branch['path']})
        result=self.groups.apply(self.body(preview),'OS actor')
        wanted={key for key,value in self.service.details.items() if value['parameters']['value']==1}
        self.assertEqual(result['target_count'],len(wanted))
        self.assertEqual({row['target_uuid'] for row in self.case.case.records.rows},wanted)
        self.assertIn(self.service.protocol_id,self.tracker.locked)

    def test_joint_missing_and_null_path_parity(self):
        self.grow(8)
        ids=list(self.service.rows)
        self.service.details[ids[0]]['parameters']={}
        self.service.details[ids[1]]['parameters']={'value':None}
        field=joint_id(['cell','parameters/value'])
        scope={'splits':field};root=TreePages(self.service).page(scope)
        for branch in root['branches']:
            preview=self.preview({**scope,'path':branch['path']})
            self.assertEqual(preview['count'],branch['count'])
            self.groups.release({'selection_uuid':preview['selection_uuid']},'OS actor')

    def test_late_target_conflict_and_100tag_preflight_write_nothing(self):
        self.grow(500);preview=self.preview();body=self.body(preview)
        entry=self.groups.selections[preview['selection_uuid']]
        entry['targets'][-1][2]=99
        with patch.object(self.case.case.records,'insert1',wraps=self.case.case.records.insert1) as insert:
            with self.assertRaises(RevisionConflict):self.groups.apply(body,'OS actor')
            insert.assert_not_called()
        self.assertEqual(self.receipts.rows,[])
        self.assertEqual(self.case.case.records.rows,[])

    def test_mid_write_and_receipt_failure_roll_back_whole_group_and_hooks(self):
        self.grow(500)
        for location in ('annotation','receipt'):
            preview=self.preview();body=self.body(preview)
            if location=='annotation':
                original=self.case.case.records.insert1;calls=[]
                def fail(row):
                    calls.append(row)
                    if len(calls)==400:raise RuntimeError('late SQL failure')
                    original(row)
                failing=patch.object(self.case.case.records,'insert1',side_effect=fail)
            else:failing=patch.object(self.receipts,'insert1',side_effect=RuntimeError('late SQL failure'))
            with failing,self.assertRaisesRegex(RuntimeError,'late SQL failure'):
                self.groups.apply(body,'OS actor')
            self.assertEqual(self.case.case.records.rows,[])
            self.assertEqual(self.case.case.profiles.rows,[])
            self.assertEqual(self.case.case.case.events.rows,[])
            self.assertEqual(self.receipts.rows,[])
            self.store.on_commit.assert_not_called()
            self.groups.release({'selection_uuid':preview['selection_uuid']},'OS actor')

    def test_external_change_stale_source_profile_actor_and_request_refuse(self):
        self.grow(10);preview=self.preview();body=self.body(preview)
        self.store.update('epoch',[next(iter(self.service.rows))],self.profile,{'tags_add':['external']},
            {next(iter(self.service.rows)):0},'OS actor')
        before=copy.deepcopy(self.case.case.records.rows)
        with self.assertRaises(RevisionConflict):self.groups.apply(body,'OS actor')
        self.assertEqual(before,self.case.case.records.rows)
        preview=self.preview();body=self.body(preview)
        with self.assertRaises(RevisionConflict):self.groups.apply(body,'foreign OS actor')
        self.groups.apply(body,'OS actor')
        with self.assertRaises(RevisionConflict):self.groups.apply({**body,'tag':'changed payload'},'OS actor')

    def test_inverse_ignores_later_filters_binding_and_other_author_preserves_original_cas(self):
        self.grow(6);preview=self.preview();body=self.body(preview);self.groups.apply(body,'OS actor')
        other=self.store.create_profile('Other scientist','OS actor')['profile_uuid']
        target=next(iter(self.service.rows))
        self.store.update('epoch',[target],other,{'tags_add':['other actor']},{target:0},'other OS actor')
        self.service.set_source_state_provider(lambda:{'a'*64:{'query_excluded':True}})
        result=self.groups.undo(body['operation_uuid'],{'operation_uuid':str(uuid.uuid4())},'OS actor')
        self.assertEqual(result['changed'],6)
        records=[row for row in self.case.case.records.rows if row['profile_uuid']==other]
        self.assertEqual(records[0]['tags'],['other actor'])

    def test_expiry_release_project_admission_and_byte_capacity_refuse(self):
        self.grow(20);preview=self.preview()
        self.groups.selections[preview['selection_uuid']]['expires']=0
        with self.assertRaisesRegex(ValueError,'expired'):self.groups.apply(self.body(preview),'OS actor')
        preview=self.preview();self.assertTrue(self.groups.release({'selection_uuid':preview['selection_uuid']},'OS actor')['released'])
        with patch('workspace_annotation_groups.PROJECT_LIMIT',10),self.assertRaisesRegex(ValueError,'scope-resolver'):
            self.preview()
        self.assertEqual(self.case.case.records.rows,[])
        with self.assertRaisesRegex(ValueError,'retained-memory'):
            RetainedBudget(maximum=64).charge({'big':'x'*500})

    def test_candidate_and_client_target_lists_refuse_before_native_write(self):
        for scope in ({'readContext':{'root':'/workbench/candidates'}},{'target_uuids':list(self.service.rows)}):
            with self.assertRaises(ValueError):
                self.groups.preview({'scope':{**scope,'revision':'a'*64},'profile_uuid':self.profile},'OS actor')
        self.assertEqual(self.receipts.rows,[])

    def test_tag_predicate_membership_changes_do_not_retarget_the_saved_operation(self):
        self.grow(30)
        predicate={'not':{'field':'annotations/epoch/tags','operator':'contains','value':'server group'}}
        preview=self.preview({'splits':'','predicate':predicate});body=self.body(preview)
        self.assertEqual(self.groups.apply(body,'OS actor')['changed'],30)
        self.assertEqual(TreePages(self.service).page({'splits':'','predicate':predicate})['total'],0)
        self.assertEqual(self.groups.undo(body['operation_uuid'],{'operation_uuid':str(uuid.uuid4())},'OS actor')['changed'],30)

    def test_budget_failure_precedes_first_write_and_inverse_conflict_is_atomic(self):
        self.grow(15);preview=self.preview();body=self.body(preview)
        with patch('workspace_annotation_groups.OPERATION_BYTES',256):
            with self.assertRaisesRegex(ValueError,'retained-memory'):self.groups.apply(body,'OS actor')
        self.assertEqual(self.case.case.records.rows,[])
        self.groups.apply(body,'OS actor')
        last=list(self.service.rows)[-1]
        self.store.update('epoch',[last],self.profile,{'tags_add':['later edit']},{last:1},'OS actor')
        before=copy.deepcopy(self.case.case.records.rows)
        with self.assertRaises(RevisionConflict):
            self.groups.undo(body['operation_uuid'],{'operation_uuid':str(uuid.uuid4())},'OS actor')
        self.assertEqual(self.case.case.records.rows,before)
        self.assertIsNone(self.receipts.rows[0]['receipt']['undone_by'])

    def test_earlier_overlapping_group_inverse_keeps_original_profile_cas(self):
        self.grow(5)
        first=self.body(self.preview(),tag='first');self.groups.apply(first,'OS actor')
        second=self.body(self.preview(),tag='second');self.groups.apply(second,'OS actor')
        self.groups.undo(second['operation_uuid'],{'operation_uuid':str(uuid.uuid4())},'OS actor')
        before=copy.deepcopy((self.receipts.rows,self.case.case.records.rows))
        with self.assertRaises(RevisionConflict):
            self.groups.undo(first['operation_uuid'],{'operation_uuid':str(uuid.uuid4())},'OS actor')
        self.assertEqual((self.receipts.rows,self.case.case.records.rows),before)

    def test_replay_after_guard_wait_returns_first_apply_and_inverse_receipts(self):
        self.grow(20);preview=self.preview();body=self.body(preview)
        second=AnnotationGroups(self.service,self.store,self.receipts,RLock(),nullcontext)
        second.selections=copy.copy(self.groups.selections)
        @contextmanager
        def first_apply_commits_while_waiting():
            self.groups.apply(body,'OS actor')
            yield
        second.registration_locks=first_apply_commits_while_waiting
        self.assertTrue(second.apply(body,'OS actor')['replayed'])
        self.assertEqual(len(self.receipts.rows),1)
        undo_body={'operation_uuid':str(uuid.uuid4())}
        @contextmanager
        def first_inverse_commits_while_waiting():
            self.groups.undo(body['operation_uuid'],undo_body,'OS actor')
            yield
        second.registration_locks=first_inverse_commits_while_waiting
        self.assertTrue(second.undo(body['operation_uuid'],undo_body,'OS actor')['replayed'])
        self.assertEqual(len(self.receipts.rows),2)

    def test_late_forward_source_and_inverse_fingerprint_changes_roll_back_everything(self):
        self.grow(25);preview=self.preview();body=self.body(preview)
        original_insert=self.receipts.insert1
        def late_source(row):
            original_insert(row)
            self.service._fingerprints[next(iter(self.service.rows))]='c'*64
        with patch.object(self.receipts,'insert1',side_effect=late_source),self.assertRaises(RevisionConflict):
            self.groups.apply(body,'OS actor')
        self.assertEqual(self.receipts.rows,[])
        self.assertEqual(self.case.case.records.rows,[])
        self.assertEqual(self.case.case.case.events.rows,[])
        self.store.on_commit.assert_not_called()
        self.service._fingerprints={key:'b'*64 for key in self.service.rows}
        self.groups.apply(body,'OS actor');self.store.on_commit.reset_mock()
        before=copy.deepcopy((self.receipts.rows,self.case.case.records.rows,self.case.case.case.events.rows))
        original_update=self.receipts.update1
        def late_inverse(row):
            original_update(row)
            self.service._fingerprints[next(iter(self.service.rows))]='c'*64
        with patch.object(self.receipts,'update1',side_effect=late_inverse),self.assertRaises(RevisionConflict):
            self.groups.undo(body['operation_uuid'],{'operation_uuid':str(uuid.uuid4())},'OS actor')
        self.assertEqual((self.receipts.rows,self.case.case.records.rows,self.case.case.case.events.rows),before)
        self.store.on_commit.assert_not_called()

    def test_late_physical_source_and_metadata_publication_changes_roll_back(self):
        self.grow(5)
        for fault in ('physical', 'metadata'):
            with self.subTest(fault=fault):
                preview=self.preview();body=self.body(preview)
                original_insert=self.receipts.insert1;late=[False]
                def insert(row):
                    original_insert(row);late[0]=True
                    if fault=='metadata':self.service._explore_publication='changed publication'
                def verified(manifest):
                    if late[0] and fault=='physical':raise RevisionConflict({'source':'changed physical file'})
                    return ('owned source','signature')
                with patch.object(self.receipts,'insert1',side_effect=insert), \
                     patch.object(self.service,'_verified_source',side_effect=verified), \
                     self.assertRaises(RevisionConflict):
                    self.groups.apply(body,'OS actor')
                self.assertEqual(self.receipts.rows,[])
                self.assertEqual(self.case.case.records.rows,[])
                self.assertEqual(self.case.case.case.events.rows,[])
                self.store.on_commit.assert_not_called()
                self.groups.release({'selection_uuid':preview['selection_uuid']},'OS actor')

    def test_late_inverse_physical_source_and_metadata_changes_roll_back(self):
        self.grow(5);body=self.body(self.preview());self.groups.apply(body,'OS actor')
        self.store.on_commit.reset_mock()
        before=copy.deepcopy((self.receipts.rows,self.case.case.records.rows,self.case.case.case.events.rows))
        for fault in ('physical','metadata'):
            with self.subTest(fault=fault):
                original_update=self.receipts.update1;late=[False]
                def update(row):
                    original_update(row);late[0]=True
                    if fault=='metadata':self.service._explore_publication=str(uuid.uuid4())
                def verified(manifest):
                    if late[0] and fault=='physical':raise RevisionConflict({'source':'changed physical file'})
                    return ('owned source','signature')
                with patch.object(self.receipts,'update1',side_effect=update), \
                     patch.object(self.service,'_verified_source',side_effect=verified), \
                     self.assertRaises(RevisionConflict):
                    self.groups.undo(body['operation_uuid'],{'operation_uuid':str(uuid.uuid4())},'OS actor')
                self.assertEqual((self.receipts.rows,self.case.case.records.rows,self.case.case.case.events.rows),before)
                self.store.on_commit.assert_not_called()

    def test_large_captured_guard_facts_and_inverse_retained_budget_refuse(self):
        self.grow(4)
        revisions=[str(index)+'x'*1000 for index in range(40)]
        def guard_provider(protocol):
            context={'source_revisions':revisions,'generation':self.tracker.token(protocol)}
            return lambda:context['source_revisions']
        self.groups.revision_guard=guard_provider
        with patch('workspace_annotation_groups.RETAINED_BYTES',10000), \
             patch('workspace_annotation_groups.RetainedBudget',side_effect=lambda used=0,maximum=None:RetainedBudget(used,maximum or 10000)):
            with self.assertRaisesRegex(ValueError,'retained-memory'):
                self.preview({'protocol_uuid':self.service.protocol_id,'splits':''})
        self.assertEqual(self.groups.selections,{})
        self.groups.revision_guard=None
        preview=self.preview();body=self.body(preview);self.groups.apply(body,'OS actor')
        before=copy.deepcopy((self.receipts.rows,self.case.case.records.rows))
        with patch('workspace_annotation_groups.OPERATION_BYTES',256),self.assertRaisesRegex(ValueError,'retained-memory'):
            self.groups.undo(body['operation_uuid'],{'operation_uuid':str(uuid.uuid4())},'OS actor')
        self.assertEqual((self.receipts.rows,self.case.case.records.rows),before)


if __name__=='__main__':unittest.main()
