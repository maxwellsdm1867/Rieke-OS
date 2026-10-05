"""Cumulative pending authority and persistent resume on disposable SQL doubles."""
import copy
import contextlib
import json
import unittest
import uuid
from unittest.mock import patch

from test_workspace_workbench import WorkbenchTests


class CumulativePendingTests(unittest.TestCase):
    setUp = WorkbenchTests.setUp
    get_context = WorkbenchTests.get_context

    def native_transaction_receipts(self):
        from workspace_state_generation import GenerationToken
        from disco.workbench.recipes import checksum
        connection=self.case.connection
        original_transaction=type(connection).transaction.fget
        original_state=self.manager.state
        connection.in_transaction=False
        @contextlib.contextmanager
        def transaction():
            with original_transaction(connection):
                connection.in_transaction=True
                try:yield
                finally:connection.in_transaction=False
        transaction_patch=patch.object(type(connection),'transaction',property(lambda _:transaction()))
        transaction_patch.start();self.addCleanup(transaction_patch.stop)
        owner=self
        class NativeReceipts:
            def __init__(self):self.locked_checks=0;self.generation=1;self.tx_token_attempts=0
            def value(self, protocol=None):
                return GenerationToken('native-fixture-authority',owner.manager.project,'shared-epoch',self.generation,
                    protocol,'protocol-epoch' if protocol else None,self.generation if protocol else None)
            def token(self,protocol=None):
                if connection.in_transaction:
                    self.tx_token_attempts+=1
                    return None
                return self.value(protocol)
            def assert_current_locked(self,token):
                self.locked_checks+=1
                owner.assertTrue(connection.in_transaction)
                if token!=self.value(token.protocol_uuid):
                    from disco.decisions.curation import RevisionConflict
                    raise RevisionConflict({'generation':'native fixture changed'})
        tracker=NativeReceipts()
        self.case.service._explore_state_generation=tracker
        def state(protocol):
            result,curation,legacy=original_state(protocol)
            return result,curation,legacy if connection.in_transaction else 'protocol-state-v3:'+legacy
        def capture_guard(protocol):
            owner.assertFalse(connection.in_transaction)
            legacy=original_state(protocol)[2]
            metadata=checksum(owner.case.service._fingerprints)
            def guard():
                owner.assertTrue(connection.in_transaction)
                if original_state(protocol)[2]!=legacy or checksum(owner.case.service._fingerprints)!=metadata:
                    from disco.decisions.curation import RevisionConflict
                    raise RevisionConflict({'query_revision':'changed under native guard'})
                return 'protocol-state-v3:'+legacy
            return guard
        self.manager.state=state
        self.manager.revision_guard=capture_guard
        return tracker

    def test_native_transaction_refusal_prepare_context_accept_and_receipt_retry(self):
        tracker=self.native_transaction_receipts()
        before=self.queue()['queue_revision']
        prepared,request=self.prepare(dict(expected_queue_revision=before))
        self.assertTrue(prepared['context']['expected_query_revision'].startswith('protocol-state-v3:'))
        self.assertEqual(prepared['context']['generation'],self.get_context('/api'+prepared['root'])['generation'])
        self.assertEqual(self.queue()['queue_revision'],before)
        self.assertEqual(tracker.tx_token_attempts,0)
        self.assertGreater(tracker.locked_checks,0)
        prepared=self.patch_draft(prepared,[dict(epoch_uuid=self.added,selected=True,reviewed=True)])
        receipt=self.accept_selected(prepared)
        self.assertEqual(receipt['accepted_epoch_uuids'],[self.added])
        self.assertTrue(receipt['expected_query_revision'].startswith('protocol-state-v3:'))
        self.assertEqual(tracker.tx_token_attempts,0)
        with patch.object(self.case.service,'refresh',side_effect=AssertionError('Receipt precedes native refresh')):
            retry,_=self.prepare(request)
        self.assertEqual(retry['prepare_operation_uuid'],prepared['prepare_operation_uuid'])

    def test_native_locked_generation_change_during_prepare_refuses_and_rolls_back(self):
        tracker=self.native_transaction_receipts()
        request=dict(expected_queue_revision=self.queue()['queue_revision'])
        before=copy.deepcopy([table.rows for table in self.case.connection.tables])
        create=self.manager.history.create
        def race(*args,**kwargs):
            result=create(*args,**kwargs)
            tracker.generation+=1
            return result
        with patch.object(self.manager.history,'create',side_effect=race):
            response=self.case.client.post(self.case.base+'/workbench/prepare',json=request,headers=self.case.headers)
        self.assertEqual(response.status_code,409,response.get_json())
        self.assertEqual([table.rows for table in self.case.connection.tables],before)
        self.assertEqual(tracker.tx_token_attempts,0)

    def queue(self):
        response = self.case.client.get(self.case.base + '/workbench')
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def prepare(self, body=None):
        body = body or dict(expected_queue_revision=self.queue()['queue_revision'])
        response = self.case.client.post(self.case.base + '/workbench/prepare', json=body, headers=self.case.headers)
        self.assertIn(response.status_code, (200, 201), response.get_json())
        return response.get_json(), body

    def more_import(self, same_cell=False):
        self.fixture.source_sha = uuid.uuid4().hex * 2
        identity = self.fixture.add_recording(same_cell=same_cell)
        baselines = self.case.protocol_suggestions.freeze_baselines('actor-one', self.manager.state)
        result = self.case.protocol_suggestions.rerun(baselines, self.fixture.source_sha, 'next.h5', 'actor-one')
        self.assertEqual(result['counts']['created_count'], 1, result)
        return identity, baselines

    def patch_draft(self, prepared, decisions=(), **options):
        root, context = '/api' + prepared['root'], prepared['context']
        response = self.case.client.patch(root + '/draft', json=dict(expected_version=context['draft']['draft_version'],
            expected_candidate_scope_revision=context['candidate_scope_revision'], decisions=list(decisions), **options), headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return {**prepared, 'context': response.get_json()}

    def epochs(self, prepared):
        response = self.case.client.get('/api' + prepared['root'] + '/epochs', query_string={
            'candidate_scope_revision': prepared['context']['candidate_scope_revision']})
        self.assertEqual(response.status_code, 200, response.get_json())
        return {row['epoch_uuid'] for row in response.get_json()['epochs']}

    def accept_selected(self, prepared):
        context = prepared['context']
        root = '/api' + prepared['root']
        body = dict(expected_candidate_scope_revision=context['candidate_scope_revision'],
            expected_draft_version=context['draft']['draft_version'], mode=context['draft']['selection_mode'])
        preview = self.case.client.post(root + '/preview', json=body, headers=self.case.headers)
        self.assertEqual(preview.status_code, 200, preview.get_json())
        body.update(**{field: preview.get_json()[field] for field in ('preview_sha256', 'expected_binding_version', 'expected_query_revision')},
            operation_uuid=str(uuid.uuid4()))
        response = self.case.client.post(root + '/accept', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_three_imports_overlap_duplicate_partial_accept_reopen_and_fourth_discovery(self):
        second, _ = self.more_import()
        third, baselines = self.more_import(same_cell=True)
        self.case.service.rows[third]['cell_uuid'] = self.case.service.rows[self.added]['cell_uuid']
        # Freeze a correct third immutable cell witness after this fixture adjustment.
        third_row = self.case.suggestion_rows.rows[-1]
        third_row['summary']['incoming_cell_uuids'][third] = self.case.service.rows[self.added]['cell_uuid']
        initial_main = copy.deepcopy(self.case.protocol_bindings.rows)
        self.assertEqual(self.queue()['pending_epoch_count'], 3)
        self.assertEqual(self.queue()['pending_cell_count'], 2)
        prepared, request = self.prepare()
        self.assertEqual(self.queue()['queue_revision'], request['expected_queue_revision'])
        self.assertEqual(prepared['kind'], 'workbench_pending_union')
        self.assertEqual(prepared['origin_count'], 3)
        self.assertEqual(self.epochs(prepared), {self.added, second, third})
        self.assertEqual(self.case.protocol_bindings.rows, initial_main)
        counts = (len(self.case.explorer_revisions.rows), len(self.case.suggestion_rows.rows), len(self.tables[2].rows))
        recipe_bytes = sum(len(json.dumps(row['recipe']).encode()) for row in self.case.explorer_revisions.rows)
        repeated, _ = self.prepare(request)
        self.assertEqual(repeated, prepared)
        self.assertEqual((len(self.case.explorer_revisions.rows), len(self.case.suggestion_rows.rows), len(self.tables[2].rows)), counts)
        duplicate = self.case.protocol_suggestions.rerun(baselines, self.fixture.source_sha, 'next.h5', 'actor-one')
        self.assertEqual(duplicate['counts']['deduplicated_count'], 1)
        self.assertEqual(self.queue()['total_candidate_count'], 3)
        self.assertEqual(self.queue()['pending_epoch_count'], 3)
        prepared = self.patch_draft(prepared, [dict(epoch_uuid=self.added, selected=True, reviewed=True),
            dict(epoch_uuid=second, excluded=True)], deferred=True)
        self.assertEqual(self.queue()['pending_epoch_count'], 2)
        receipt = self.accept_selected(prepared)
        self.assertEqual(receipt['accepted_epoch_uuids'], [self.added])
        old = self.case.client.get('/api' + prepared['root'] + '/epochs', query_string={
            'candidate_scope_revision': prepared['context']['candidate_scope_revision']})
        self.assertEqual(old.status_code, 409)
        refreshed = {**prepared, 'context': self.get_context('/api' + prepared['root'])}
        self.assertEqual(self.epochs(refreshed), {second, third})
        before_draft = copy.deepcopy([table.rows for table in self.tables[:2]])
        rejected_patch = self.case.client.patch('/api' + prepared['root'] + '/draft', json=dict(
            expected_version=refreshed['context']['draft']['draft_version'],
            expected_candidate_scope_revision=refreshed['context']['candidate_scope_revision'],
            decisions=[dict(epoch_uuid=self.added, reviewed=False)]), headers=self.case.headers)
        self.assertEqual(rejected_patch.status_code, 400, rejected_patch.get_json())
        self.assertEqual([table.rows for table in self.tables[:2]], before_draft)
        # Detail and trace also subtract already accepted identities.
        for suffix in ('', '/trace'):
            response = self.case.client.get('/api' + prepared['root'] + '/epochs/' + self.added + suffix,
                query_string={'candidate_scope_revision': refreshed['context']['candidate_scope_revision']})
            self.assertEqual(response.status_code, 400, response.get_json())
        resumed, _ = self.prepare()
        self.assertNotEqual(resumed['candidate_revision_uuid'], prepared['candidate_revision_uuid'])
        self.assertEqual(self.epochs(resumed), {second, third})
        self.assertEqual(resumed['context']['draft']['selection_mode'], 'selected')
        self.assertTrue(resumed['context']['draft']['deferred'])
        self.assertTrue(next(row for row in resumed['context']['draft']['decisions'] if row['epoch_uuid'] == second)['excluded'])
        fourth, _ = self.more_import()
        grown, _ = self.prepare()
        self.assertEqual(self.epochs(grown), {second, third, fourth})
        self.assertEqual(grown['context']['protocol']['counts']['epochs'], 3)
        main = self.case.explorer_history.protocol_binding(self.protocol)['recipe']
        self.assertEqual(main['predicate'], baselines[0]['recipe']['predicate'])
        self.assertEqual({row['uuid'] for row in main['epochs']}, set(self.fixture.before_ids) | {self.added})
        grown = self.patch_draft(grown, [dict(epoch_uuid=fourth, selected=True, reviewed=True)])
        self.assertEqual(self.accept_selected(grown)['accepted_epoch_uuids'], [fourth])
        self.assertGreater(prepared['storage']['recipe_json_bytes'], 0)
        self.assertEqual(sum(len(json.dumps(row['recipe']).encode()) for row in self.case.explorer_revisions.rows[:counts[0]]), recipe_bytes)
        print('Cumulative fixture storage:', dict(first_prepare_recipe_bytes=prepared['storage']['recipe_json_bytes'],
            first_prepare_revision_delta=prepared['storage']['revision_count_delta'], repeated_revision_delta=0,
            later_prepare_recipe_bytes=grown['storage']['recipe_json_bytes']))

    def test_unchanged_snapshot_reuses_recipe_across_actors_but_drafts_never_leak(self):
        prepared, body = self.prepare()
        initial_queue = self.queue()['queue_revision']
        self.assertEqual(initial_queue, body['expected_queue_revision'])
        self.assertEqual(self.prepare()[0], prepared)
        edited = self.patch_draft(prepared, [dict(epoch_uuid=self.added, selected=True, reviewed=True, excluded=True)], deferred=True)
        counts = len(self.case.explorer_revisions.rows)
        with patch('disco.decisions.author_preferences.selected_author', return_value={'profile_uuid': 'actor-two'}):
            other, _ = self.prepare()
            self.assertTrue(other['reused'])
            self.assertEqual(other['candidate_revision_uuid'], prepared['candidate_revision_uuid'])
            self.assertFalse(other['context']['draft']['decisions'])
            self.assertFalse(other['context']['draft']['deferred'])
            self.assertEqual(self.queue()['pending_epoch_count'], 1)
        self.assertEqual(len(self.case.explorer_revisions.rows), counts)
        self.assertEqual(self.prepare(body)[0], prepared)  # Immutable initialization receipt.
        context = self.get_context('/api' + prepared['root'])
        self.assertEqual(context['draft'], edited['context']['draft'])
        new, _ = self.prepare()
        self.assertTrue(new['reused'])
        self.assertEqual(new['context']['draft'], edited['context']['draft'])
        self.assertEqual(self.queue()['pending_epoch_count'], 0)

    def test_prepare_after_mutation_and_import_keeps_new_queue_token_stable(self):
        prepared, _ = self.prepare()
        prepared = self.patch_draft(prepared, [dict(epoch_uuid=self.added, selected=True, reviewed=True)], selection_mode='all')
        self.more_import()
        before = self.queue()['queue_revision']
        grown, _ = self.prepare(dict(expected_queue_revision=before))
        self.assertEqual(self.queue()['queue_revision'], before)
        self.assertEqual(grown['context']['draft']['selection_mode'], 'selected')
        counts = (len(self.case.explorer_revisions.rows), len(self.case.suggestion_rows.rows), len(self.tables[2].rows))
        self.assertEqual(self.prepare()[0], grown)
        self.assertEqual((len(self.case.explorer_revisions.rows), len(self.case.suggestion_rows.rows), len(self.tables[2].rows)), counts)

    def test_new_identity_never_inherits_all_consent_and_stale_queue_or_conflict_refuses(self):
        prepared, _ = self.prepare()
        prepared = self.patch_draft(prepared, selection_mode='all')
        old_queue = self.queue()['queue_revision']
        new, _ = self.more_import()
        stale = self.case.client.post(self.case.base + '/workbench/prepare', json=dict(expected_queue_revision=old_queue), headers=self.case.headers)
        self.assertEqual(stale.status_code, 409)
        grown, _ = self.prepare()
        self.assertEqual(grown['context']['draft']['selection_mode'], 'selected')
        self.assertFalse(grown['context']['draft']['decisions'])
        self.case.service._fingerprints[new] = 'c' * 64
        before = len(self.case.explorer_revisions.rows)
        # Changed native fingerprint is visible as a blocked origin; no invented
        # winner is persisted into a new aggregate snapshot.
        response = self.case.client.post(self.case.base + '/workbench/prepare', json=dict(expected_queue_revision=self.queue()['queue_revision']), headers=self.case.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(len(self.case.explorer_revisions.rows), before)

    def test_prepare_carries_actor_original_review_once_and_atomic_receipt_failure_rolls_back(self):
        context = self.get_context()
        saved = self.case.client.patch(self.root + '/draft', json=dict(expected_version=0,
            expected_candidate_scope_revision=context['candidate_scope_revision'],
            decisions=[dict(epoch_uuid=self.added, selected=True, reviewed=True)]), headers=self.case.headers)
        self.assertEqual(saved.status_code, 200, saved.get_json())
        body = dict(expected_queue_revision=self.queue()['queue_revision'], operation_uuid=str(uuid.uuid4()))
        before = copy.deepcopy([table.rows for table in self.case.connection.tables])
        self.case.app.config['TESTING'] = False
        with patch.object(self.tables[2], 'insert1', side_effect=RuntimeError('Prepare receipt unavailable')):
            failed = self.case.client.post(self.case.base + '/workbench/prepare', json=body, headers=self.case.headers)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual([table.rows for table in self.case.connection.tables], before)
        prepared, _ = self.prepare(body)
        decision = prepared['context']['draft']['decisions'][0]
        self.assertTrue(decision['selected'] and decision['reviewed'])
        self.assertEqual(prepared['draft_initialization']['carried_decision_count'], 1)
        before_count = len(self.case.explorer_revisions.rows)
        # Committed prepare receipt survives lost reply / subsequent availability.
        with patch.object(self.case.service, 'refresh', side_effect=ValueError('Source unavailable')), \
                patch.object(self.manager, 'proposal', side_effect=ValueError('Proposal unavailable')):
            retry, _ = self.prepare(body)
        self.assertEqual(retry, prepared)
        self.assertEqual(len(self.case.explorer_revisions.rows), before_count)

    def test_source_authority_change_during_preparation_rolls_back_and_old_scope_never_rebases(self):
        body = dict(expected_queue_revision=self.queue()['queue_revision'])
        before = copy.deepcopy([table.rows for table in self.case.connection.tables])
        import disco.workbench.workbench_pending as pending
        original = pending.snapshot_authority
        calls = [0]
        def changing(*args, **kwargs):
            result = original(*args, **kwargs)
            calls[0] += 1
            if calls[0] == 2:
                result['sha256'] = 'changed-source-authority'
            return result
        with patch.object(pending, 'snapshot_authority', side_effect=changing):
            response = self.case.client.post(self.case.base + '/workbench/prepare', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual([table.rows for table in self.case.connection.tables], before)
        prepared, _ = self.prepare(body)
        self.more_import()
        response = self.case.client.get('/api' + prepared['root'] + '/epochs', query_string={
            'candidate_scope_revision': prepared['candidate_scope_revision']})
        self.assertEqual(response.status_code, 409, response.get_json())

    def test_conflicting_original_actor_flags_and_conflicting_fingerprints_refuse_without_writes(self):
        self.more_import()
        contexts = []
        for row in self.manager.original_records(self.protocol):
            root = self.case.base + '/workbench/candidates/' + row['summary']['candidate_revision_uuid']
            context = self.get_context(root)
            contexts.append((root, context))
        for index, (root, context) in enumerate(contexts):
            decision = dict(epoch_uuid=self.added, selected=True, reviewed=True) if index == 0 else dict(epoch_uuid=self.added, excluded=True)
            response = self.case.client.patch(root + '/draft', json=dict(expected_version=0,
                expected_candidate_scope_revision=context['candidate_scope_revision'], decisions=[decision]), headers=self.case.headers)
            self.assertEqual(response.status_code, 200, response.get_json())
        before = copy.deepcopy([table.rows for table in self.case.connection.tables])
        response = self.case.client.post(self.case.base + '/workbench/prepare', json=dict(expected_queue_revision=self.queue()['queue_revision']), headers=self.case.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertIn('Historical', response.get_json()['error'])
        self.assertEqual([table.rows for table in self.case.connection.tables], before)
        # A later original can contain the SAME native UUID with a new value.
        # The old immutable witness must then block, never silently win or lose.
        self.case.service._fingerprints[self.added] = 'c' * 64
        baselines = self.case.protocol_suggestions.freeze_baselines('actor-one', self.manager.state)
        result = self.case.protocol_suggestions.rerun(baselines, 'changed-source', 'changed.h5', 'actor-one')
        self.assertEqual(result['counts']['created_count'], 1, result)
        before = copy.deepcopy([table.rows for table in self.case.connection.tables])
        response = self.case.client.post(self.case.base + '/workbench/prepare', json=dict(expected_queue_revision=self.queue()['queue_revision']), headers=self.case.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual([table.rows for table in self.case.connection.tables], before)

    def test_recovery_receipt_root_retains_nonparent_original_origin_and_missing_origin_refuses(self):
        from pathlib import Path
        from workspace_state_snapshot import capture
        prepared, _ = self.prepare()
        receipts = [row for row in self.tables[2].rows if row['operation_uuid'] == prepared['prepare_operation_uuid']]
        revisions = {row['revision_uuid']: row for row in self.case.explorer_revisions.rows}
        class RecoveryConnection:
            answer = []
            def query(self, sql, args=None, as_dict=False):
                if 'information_schema.tables' in sql:
                    self.answer = [('workbench_receipt',), ('explorer_revision',)]
                elif sql.startswith('SHOW COLUMNS'):
                    self.answer = [('recipe', 'json'), ('receipt', 'json'), ('summary', 'json')]
                elif '`workbench_receipt`' in sql:
                    self.answer = receipts
                elif '`explorer_revision`' in sql:
                    self.answer = [{**revisions[key], 'recipe': json.dumps(revisions[key]['recipe'])}
                        for key in args[1:] if key in revisions]
                else:
                    raise AssertionError(sql)
                return self
            def fetchall(self): return self.answer
        (Path(self.case.service.project_dir) / 'project.json').write_text(json.dumps(self.case.service.project))
        state = capture(self.case.service.project_dir, RecoveryConnection())
        self.assertIn(self.revision, {row['revision_uuid'] for row in state['tables']['explorer_revision']})
        self.assertEqual(len(state['tables']['explorer_revision']), 3)
        revisions.pop(self.revision)
        with self.assertRaisesRegex(ValueError, 'dependency is unavailable'):
            capture(self.case.service.project_dir, RecoveryConnection())
