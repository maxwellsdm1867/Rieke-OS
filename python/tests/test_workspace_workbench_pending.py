"""Cumulative pending authority and persistent resume on disposable SQL doubles."""
import copy
import contextlib
import json
import unittest
import uuid
from unittest.mock import patch

from test_workspace_workbench import WorkbenchTests
from disco.workbench.workbench import WorkbenchConflict


class CumulativePendingTests(unittest.TestCase):
    setUp = WorkbenchTests.setUp
    get_context = WorkbenchTests.get_context

    def test_saved_epoch_and_cell_tags_refresh_in_place_without_new_recipe_or_lost_selection(self):
        shared = WorkbenchTests.coverage_annotations(self)
        profile = shared.create_profile('Fixture author', 'actor-one')['profile_uuid']
        prepared, _ = self.prepare()
        prepared = self.patch_draft(prepared, [dict(epoch_uuid=self.added, selected=True, reviewed=True)])
        original = copy.deepcopy(self.manager.history.get(prepared['candidate_revision_uuid']))
        selection = prepared['context']['draft']
        for kind, target in [('epoch', self.added), ('cell', self.case.service.rows[self.added]['cell_uuid'])]:
            shared.update(kind, [target], profile, {'tags_add': ['keep-' + kind]}, {target: 0}, 'actor-one')
            fresh, _ = self.prepare()
            self.assertEqual(fresh['candidate_revision_uuid'], prepared['candidate_revision_uuid'])
            self.assertEqual(fresh['context']['draft'], selection)
            page = self.case.client.get('/api' + fresh['root'] + '/epochs',
                query_string={'candidate_scope_revision': fresh['candidate_scope_revision']})
            self.assertEqual(page.status_code, 200, page.get_json())
            rows = page.get_json()['epochs']
            self.assertEqual([row['epoch_uuid'] for row in rows], [self.added])
            self.assertIn('keep-' + kind, [tag['tag'] for tag in rows[0]['annotations']['effective_tags']])
            self.assertEqual(self.manager.history.get(fresh['candidate_revision_uuid']), original)

    def test_another_authors_tag_keeps_queue_candidate_scope_and_frozen_tokens(self):
        shared = WorkbenchTests.coverage_annotations(self)
        prepared, original_request = self.prepare()
        prepared = self.patch_draft(prepared, [dict(epoch_uuid=self.added, selected=True, reviewed=True)])
        before = self.get_context('/api' + prepared['root'])
        old_queue = self.queue()['queue_revision']
        recipe = copy.deepcopy(self.manager.history.get(prepared['candidate_revision_uuid']))
        revision_count = len(self.case.explorer_revisions.rows)
        # Another author's (or an external import's) tag is not candidate scope.
        WorkbenchTests.tag(self, shared, 'cell', self.case.service.rows[self.added]['cell_uuid'],
                           add=['external'], author='MATLAB import')
        self.assertEqual(self.queue()['queue_revision'], old_queue)
        after = self.get_context('/api' + prepared['root'])
        self.assertEqual(after['candidate_scope_revision'], before['candidate_scope_revision'])
        self.assertEqual(after['draft'], before['draft'])
        root = '/api' + prepared['root']
        page = self.case.client.get(root + '/epochs', query_string={'candidate_scope_revision': before['candidate_scope_revision']})
        self.assertEqual(page.status_code, 200, page.get_json())
        self.assertEqual([row['epoch_uuid'] for row in page.get_json()['epochs']], [self.added])
        self.assertIn('external', [tag['tag'] for tag in page.get_json()['epochs'][0]['annotations']['effective_tags']])
        # The same prepare replays; nothing new is stored.
        replay, _ = self.prepare(original_request)
        self.assertEqual(replay['prepare_operation_uuid'], prepared['prepare_operation_uuid'])
        self.assertEqual(replay['candidate_revision_uuid'], prepared['candidate_revision_uuid'])
        self.assertEqual(self.manager.history.get(prepared['candidate_revision_uuid']), recipe)
        self.assertEqual(len(self.case.explorer_revisions.rows), revision_count)
        # Writes held across the tag still succeed under their membership fences.
        saved = self.case.client.patch(root + '/draft', json=dict(expected_version=before['draft']['draft_version'],
            expected_candidate_scope_revision=before['candidate_scope_revision'], decisions=[]), headers=self.case.headers)
        self.assertEqual(saved.status_code, 200, saved.get_json())
        # Membership changes still fail closed: a draft edit renews the scope.
        stale_write = self.case.client.patch(root + '/draft', json=dict(expected_version=before['draft']['draft_version'],
            expected_candidate_scope_revision=before['candidate_scope_revision'], decisions=[]), headers=self.case.headers)
        self.assertEqual(stale_write.status_code, 409, stale_write.get_json())

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
        create=self.manager.history.create_delta
        def race(*args,**kwargs):
            result=create(*args,**kwargs)
            tracker.generation+=1
            return result
        with patch.object(self.manager.history,'create_delta',side_effect=race):
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

    def test_fresh_context_header_is_response_only_and_receipt_replay_stays_exact(self):
        body = dict(expected_queue_revision=self.queue()['queue_revision'])
        first = self.case.client.post(self.case.base + '/workbench/prepare', json=body, headers=self.case.headers)
        self.assertEqual(first.status_code, 201, first.get_json())
        self.assertEqual(first.headers.get('X-Disco-Workbench-Context'), 'fresh-v1')
        prepared = first.get_json()
        stored = self.manager.receipt(prepared['operation_uuid'], prepared['actor'])
        self.assertEqual(stored, prepared)
        with patch.object(self.case.service, 'refresh', side_effect=AssertionError('Replay must not recompute context')):
            replay = self.case.client.post(self.case.base + '/workbench/prepare', json=body, headers=self.case.headers)
        self.assertEqual(replay.status_code, 200, replay.get_json())
        self.assertIsNone(replay.headers.get('X-Disco-Workbench-Context'))
        self.assertEqual(replay.get_data(), first.get_data())
        # A new operation may reuse the stored candidate while computing a
        # current context. Candidate reuse is not durable receipt replay.
        current = self.case.client.post(self.case.base + '/workbench/prepare', json={
            **body, 'operation_uuid': str(uuid.uuid4())}, headers=self.case.headers)
        self.assertEqual(current.status_code, 200, current.get_json())
        self.assertTrue(current.get_json()['reused'])
        self.assertEqual(current.headers.get('X-Disco-Workbench-Context'), 'fresh-v1')

    def test_prepare_commit_failure_never_advertises_a_fresh_context(self):
        body = dict(expected_queue_revision=self.queue()['queue_revision'])
        connection = self.case.connection
        transaction = type(connection).transaction.fget
        @contextlib.contextmanager
        def failing_commit():
            with transaction(connection):
                yield
                raise RuntimeError('Commit failed after context construction')
        self.case.app.config['TESTING'] = False
        before = copy.deepcopy([table.rows for table in connection.tables])
        with patch.object(type(connection), 'transaction', property(lambda _: failing_commit())):
            response = self.case.client.post(self.case.base + '/workbench/prepare', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 500, response.get_json())
        self.assertIsNone(response.headers.get('X-Disco-Workbench-Context'))
        self.assertEqual([table.rows for table in connection.tables], before)

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

    def apply_candidate(self, revision):
        endpoint = '/api/explore/revisions/' + revision
        body = {'protocol_uuid': self.protocol}
        comparison = self.case.client.post(endpoint + '/compare-to-protocol', json=body, headers=self.case.headers)
        self.assertEqual(comparison.status_code, 200, comparison.get_json())
        response = self.case.client.post(endpoint + '/apply-to-protocol', json={**body,
            'expected_binding_version': comparison.get_json()['expected_binding_version'],
            'expected_query_revision': comparison.get_json()['expected_query_revision']}, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def saved_query_revision(self, without=None):
        """A plain saved query revision, as Search predicate creates; optionally the
        query no longer matches one epoch (e.g. a corrected protocol predicate)."""
        main = self.case.explorer_history.protocol_binding(self.protocol)['recipe']
        original = self.case.service.explore_preview
        def preview(*args, **kwargs):
            result = original(*args, **kwargs)
            membership = [row for row in result['membership'] if row['uuid'] != without]
            return {**result, 'membership': membership, 'matched_count': len(membership)}
        matcher = self.case.service.match_predicate
        def match(*args, **kwargs):
            validated, identities, annotation = matcher(*args, **kwargs)
            return validated, [key for key in identities if key != without], annotation
        for name, effect in (('explore_preview', preview), ('match_predicate', match)):
            patcher = patch.object(self.case.service, name, side_effect=effect)
            patcher.start()
            self.addCleanup(patcher.stop)
        record = self.case.explorer_history.create(preview(main['predicate'], main['splits']),
            self.case.service.sources, self.case.service.project_dir / 'catalog.json', 'actor-one', name='Metadata selection')
        return record['revision_uuid']

    def test_replaced_main_marks_merged_proposals_covered_not_conflict(self):
        self.more_import()
        before = self.queue()
        self.assertEqual(before['pending_epoch_count'], 2)
        self.apply_candidate(self.saved_query_revision())
        queue = self.queue()
        self.assertEqual([item['status'] for item in queue['candidates']], ['covered', 'covered'])
        self.assertEqual(queue['pending_epoch_count'], 0)
        # Later imports diff against the replacement main and merge normally.
        late, _ = self.more_import()
        queue = self.queue()
        self.assertEqual(sorted(item['status'] for item in queue['candidates']), ['covered', 'covered', 'pending'])
        prepared, _ = self.prepare()
        self.assertEqual(self.epochs(prepared), {late})
        prepared = self.patch_draft(prepared, [dict(epoch_uuid=late, selected=True, reviewed=True)])
        self.accept_selected(prepared)
        self.assertEqual(self.queue()['pending_epoch_count'], 0)

    def test_replaced_main_supersedes_epochs_the_current_query_no_longer_matches(self):
        new, _ = self.more_import()
        second = next(row['summary']['candidate_revision_uuid'] for row in self.manager.original_records(self.protocol)
                      if row['summary']['candidate_revision_uuid'] != self.revision)
        self.apply_candidate(self.saved_query_revision(without=new))
        queue = self.queue()
        status = {item['candidate_revision_uuid']: item['status'] for item in queue['candidates']}
        self.assertEqual(set(status.values()), {'covered'})
        self.assertEqual(queue['pending_epoch_count'], 0)
        self.assertEqual(queue['pending_cell_count'], 0)
        # The current query no longer matches the late epoch: nothing pending, nothing refused.
        response = self.case.client.post(self.case.base + '/workbench/prepare',
            json=dict(expected_queue_revision=queue['queue_revision']), headers=self.case.headers)
        self.assertIn(response.status_code, (200, 201), response.get_json())
        self.assertEqual(response.get_json()['counts']['pending_epochs'], 0)
        # The frozen superseded proposal still refuses publication and says why.
        root = self.case.base + '/workbench/candidates/' + second
        context = self.get_context(root)
        self.assertTrue(context['publication_blocked'])
        preview = self.case.client.post(root + '/preview', json=dict(expected_candidate_scope_revision=context['candidate_scope_revision'],
            expected_draft_version=context['draft']['draft_version'], mode=context['draft']['selection_mode']), headers=self.case.headers)
        self.assertEqual(preview.status_code, 409, preview.get_json())
        self.assertIn('newer saved query', preview.get_json()['error'])

    def test_finish_review_leaves_remaining_out_until_new_data_arrives(self):
        first, _ = self.more_import()
        prepared, _ = self.prepare()
        self.assertEqual(self.epochs(prepared), {self.added, first})
        # Merge one, then finish: the rest is left out and nothing stays pending.
        prepared = self.patch_draft(prepared, [dict(epoch_uuid=self.added, selected=True, reviewed=True)])
        self.accept_selected(prepared)
        prepared, _ = self.prepare()
        root, context = '/api' + prepared['root'], prepared['context']
        fences = dict(expected_version=context['draft']['draft_version'], expected_candidate_scope_revision=context['candidate_scope_revision'])
        stale = self.case.client.post(root + '/finish', json={**fences, 'expected_version': fences['expected_version'] + 1}, headers=self.case.headers)
        self.assertEqual(stale.status_code, 409, stale.get_json())
        finished = self.case.client.post(root + '/finish', json=fences, headers=self.case.headers)
        self.assertEqual(finished.status_code, 200, finished.get_json())
        self.assertEqual(self.queue()['pending_epoch_count'], 0)
        # Left-out epochs stay out across later preparations; new data still appears.
        late, _ = self.more_import()
        queue = self.queue()
        self.assertEqual(queue['pending_epoch_count'], 1)
        prepared, _ = self.prepare()
        decisions = {item['epoch_uuid']: item for item in prepared['context']['draft']['decisions']}
        self.assertTrue(decisions[first]['excluded'])
        self.assertFalse(decisions.get(late, {}).get('excluded'))
        self.assertEqual(prepared['context']['counts']['excluded_epochs'], 1)
        original = '/api' + self.case.base.removeprefix('/api') + '/workbench/candidates/' + self.revision
        refused = self.case.client.post(original + '/finish', json=fences, headers=self.case.headers)
        self.assertEqual(refused.status_code, 400, refused.get_json())

    def test_main_level_blocker_offers_nothing_and_names_the_reason(self):
        main = self.case.explorer_history.protocol_binding(self.protocol)['recipe']
        drifted = main['epochs'][0]['uuid']
        self.queue()  # Warm the per-publication main checks first.
        # A refresh publishes a new fingerprint map under a new publication token.
        service = self.case.service
        service._fingerprints = {**service._fingerprints, drifted: 'e' * 64}
        service._explore_publication = str(uuid.uuid4())
        queue = self.queue()
        self.assertEqual(queue['pending_epoch_count'], 0)
        self.assertIn('metadata changed', queue['main_blocked_reason'])

    def undo(self, receipt):
        return self.case.client.post(self.case.base + '/workbench/undo', json=dict(
            operation_uuid=receipt['operation_uuid'], expected_binding_version=receipt['binding']['version']), headers=self.case.headers)

    def test_undo_merge_restores_main_and_pending_then_merge_again(self):
        first, _ = self.more_import()
        before = self.case.explorer_history.protocol_binding(self.protocol)
        prepared, _ = self.prepare()
        prepared = self.patch_draft(prepared, selection_mode='all')
        receipt = self.accept_selected(prepared)
        self.assertEqual(self.queue()['pending_epoch_count'], 0)
        undone = self.undo(receipt)
        self.assertEqual(undone.status_code, 200, undone.get_json())
        self.assertEqual(undone.get_json()['removed_epoch_count'], 2)
        after = self.case.explorer_history.protocol_binding(self.protocol)
        self.assertEqual(after['revision_uuid'], before['revision_uuid'])
        self.assertEqual(after['version'], receipt['binding']['version'] + 1)
        # Undone epochs are pending again, never superseded or conflicting.
        queue = self.queue()
        self.assertEqual(queue['pending_epoch_count'], 2)
        self.assertNotIn('superseded', {item['status'] for item in queue['candidates']})
        self.assertEqual(self.undo(receipt).get_json(), undone.get_json(), 'undo replay is idempotent')
        prepared, _ = self.prepare()
        prepared = self.patch_draft(prepared, selection_mode='all')
        again = self.accept_selected(prepared)
        self.assertEqual(sorted(again['accepted_epoch_uuids']), sorted([self.added, first]))
        self.assertEqual(self.queue()['pending_epoch_count'], 0)
        # Only the latest change to main can be undone.
        replayed = self.undo(receipt)  # Its undo receipt replays; it never undoes the re-merge.
        self.assertEqual(replayed.get_json(), undone.get_json())
        self.assertEqual(self.queue()['pending_epoch_count'], 0)
        late, _ = self.more_import()
        prepared, _ = self.prepare()
        prepared = self.patch_draft(prepared, selection_mode='all')
        latest = self.accept_selected(prepared)
        refused = self.undo(again)
        self.assertEqual(refused.status_code, 409, refused.get_json())
        self.assertIn('can no longer be undone', refused.get_json()['error'])
        self.assertEqual(self.undo(latest).status_code, 200)
        self.assertEqual(self.queue()['pending_epoch_count'], 1)

    def test_pending_follows_the_entry_protocol_ids_including_pinned_multi_protocol(self):
        foreign, _ = self.more_import()
        recorded = self.case.service.rows[self.added]['protocol_name']
        self.case.service.rows[foreign]['protocol_name'] = 'other.lab.protocols.TripleHistory'
        # A protocol entry lists one recorded ID; a foreign protocol is never pending.
        self.assertEqual(self.queue()['pending_epoch_count'], 1)
        prepared, _ = self.prepare()
        self.assertEqual(self.epochs(prepared), {self.added})
        # An entry listing both IDs (as a pinned multi-protocol entry does) offers both.
        definition = self.case.service.protocols[self.protocol]['definition']
        definition['query']['all'][0].update(operator='in', value=sorted([recorded, 'other.lab.protocols.TripleHistory']))
        self.assertEqual(self.queue()['pending_epoch_count'], 2)
        prepared, _ = self.prepare()
        prepared = self.patch_draft(prepared, selection_mode='all')
        receipt = self.accept_selected(prepared)
        self.assertEqual(sorted(receipt['accepted_epoch_uuids']), sorted([self.added, foreign]))

    def test_pool_offers_only_recordings_main_has_not_seen(self):
        late, _ = self.more_import()
        self.assertEqual(self.queue()['pending_epoch_count'], 2)
        # Defining main again (a query save) after both imports marks their
        # recordings as seen: an epoch left out of that main is not re-offered.
        self.apply_candidate(self.saved_query_revision(without=late))
        self.case.service.match_predicate = type(self.case.service).match_predicate.__get__(self.case.service)
        self.assertEqual(self.queue()['pending_epoch_count'], 0)
        # A later recording is new again, even though main's query also matches
        # the previously omitted epoch.
        newest, _ = self.more_import()
        queue = self.queue()
        self.assertEqual(queue['pending_epoch_count'], 1)
        self.assertEqual([item['source_sha256'] for item in queue['pending_recordings']], [self.case.service.rows[newest]['source_sha256']])
        prepared, _ = self.prepare()
        self.assertEqual(self.epochs(prepared), {newest})

    def test_merge_all_adds_every_pending_epoch_in_one_idempotent_request(self):
        first, _ = self.more_import()
        queue = self.queue()
        body = dict(expected_queue_revision=queue['queue_revision'], operation_uuid=str(uuid.uuid4()))
        stale = self.case.client.post(self.case.base + '/workbench/merge-all', json={**body, 'expected_queue_revision': 'old'},
            headers=self.case.headers)
        self.assertEqual(stale.status_code, 409, stale.get_json())
        merged = self.case.client.post(self.case.base + '/workbench/merge-all', json=body, headers=self.case.headers)
        self.assertEqual(merged.status_code, 200, merged.get_json())
        receipt = merged.get_json()
        self.assertEqual(sorted(receipt['accepted_epoch_uuids']), sorted([self.added, first]))
        self.assertEqual(self.queue()['pending_epoch_count'], 0)
        replay = self.case.client.post(self.case.base + '/workbench/merge-all', json=body, headers=self.case.headers)
        self.assertEqual(replay.get_json(), receipt, 'the same operation replays its receipt, never merging twice')
        self.assertEqual(self.undo(receipt).status_code, 200)
        self.assertEqual(self.queue()['pending_epoch_count'], 2)

    def test_prepare_bootstrap_is_response_only_and_replay_reads_fresh_authority(self):
        body = dict(expected_queue_revision=self.queue()['queue_revision'])
        path = self.case.base + '/workbench/prepare'
        response = self.case.client.post(path + '?include_initial_page=true', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        value = response.get_json()
        bootstrap = value.pop('bootstrap')
        self.assertEqual(response.headers.get('X-Disco-Workbench-Context'), 'fresh-v1')
        self.assertEqual(bootstrap['context'], value['context'])
        self.assertEqual(bootstrap['page']['query_revision'], value['candidate_scope_revision'])
        receipt = next(row['receipt'] for row in self.tables[2].rows if row['operation_uuid'] == value['operation_uuid'])
        self.assertEqual(receipt, value)
        self.assertNotIn('bootstrap', receipt)
        self.patch_draft(value, [dict(epoch_uuid=self.added, reviewed=True)])
        replay = self.case.client.post(path + '?include_initial_page=true', json=body, headers=self.case.headers)
        self.assertEqual(replay.status_code, 200, replay.get_json())
        self.assertNotIn('X-Disco-Workbench-Context', replay.headers)
        replay_value = replay.get_json()
        fresh = replay_value.pop('bootstrap')
        self.assertEqual(replay_value, value)
        self.assertNotEqual(fresh['context']['candidate_scope_revision'], value['candidate_scope_revision'])
        self.assertEqual(fresh['page']['candidate_scope_revision'], fresh['context']['candidate_scope_revision'])
        ordinary = self.case.client.post(path, json=body, headers=self.case.headers)
        self.assertEqual(ordinary.get_json(), value)
        self.assertEqual(receipt, value)
        for query in ('include_initial_page=bad', 'include_initial_page=true&include_initial_page=false', 'unknown=true'):
            self.assertEqual(self.case.client.post(path + '?' + query, json=body, headers=self.case.headers).status_code, 400)

    def test_native_bootstrap_and_transaction_race_replay_use_locked_authority(self):
        tracker = self.native_transaction_receipts()
        body = dict(expected_queue_revision=self.queue()['queue_revision'])
        path = self.case.base + '/workbench/prepare?include_initial_page=true'
        first = self.case.client.post(path, json=body, headers=self.case.headers)
        self.assertEqual(first.status_code, 201, first.get_json())
        receipt = first.get_json(); receipt.pop('bootstrap')
        lookup = self.manager.receipt
        calls = []
        def race(*args):
            calls.append(args)
            return None if len(calls) < 2 else lookup(*args)
        with patch.object(self.manager, 'receipt', side_effect=race):
            replay = self.case.client.post(path, json=body, headers=self.case.headers)
        self.assertEqual(replay.status_code, 200, replay.get_json())
        result = replay.get_json(); bootstrap = result.pop('bootstrap')
        self.assertEqual(result, receipt)
        self.assertEqual(bootstrap['page']['candidate_scope_revision'], bootstrap['context']['candidate_scope_revision'])
        self.assertNotIn('X-Disco-Workbench-Context', replay.headers)
        self.assertEqual(tracker.tx_token_attempts, 0)
        self.assertGreater(tracker.locked_checks, 0)
        self.assertEqual(len(calls), 2, 'the in-transaction lookup finds the concurrent receipt')

    def test_prepare_bootstrap_failed_commit_publishes_neither_receipt_nor_page(self):
        request = dict(expected_queue_revision=self.queue()['queue_revision'])
        connection = self.case.connection
        original = type(connection).transaction.fget
        before = copy.deepcopy([table.rows for table in connection.tables])
        @contextlib.contextmanager
        def fail():
            with original(connection):
                yield
                raise RuntimeError('Bootstrap commit failed')
        with patch.object(type(connection), 'transaction', property(lambda _: fail())):
            response = self.case.client.post(self.case.base + '/workbench/prepare?include_initial_page=true',
                json=request, headers=self.case.headers)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('bootstrap', response.get_json())
        self.assertNotIn('X-Disco-Workbench-Context', response.headers)
        self.assertEqual([table.rows for table in connection.tables], before)

    def test_cumulative_list_selection_shares_admission_and_preserves_cell_order(self):
        from disco.operation_timing import capture_timings
        self.more_import()
        prepared, _ = self.prepare()
        root = '/api' + prepared['root']
        context = self.get_context(root)
        cells = [dict(cell_uuid=cell['cell_uuid'], epochs=cell['epochs']) for cell in reversed(context['protocol']['cells'])]
        expected = []
        for cell in cells:
            page = self.case.client.get(root + '/epochs', query_string=dict(
                candidate_scope_revision=context['candidate_scope_revision'], cell_uuid=cell['cell_uuid'], limit=60)).get_json()
            expected.extend(row['epoch_uuid'] for row in page['epochs'])
        body = dict(candidate_scope_revision=context['candidate_scope_revision'], cells=cells)
        with capture_timings() as timings:
            response = self.case.client.post(root + '/list-selection', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['epoch_uuids'], expected)
        self.assertEqual([cell['cell_uuid'] for cell in response.get_json()['cells']], [cell['cell_uuid'] for cell in cells])
        # One full opening context; the close compares current tokens against it.
        self.assertEqual(sum(row['operation'] == 'context' for row in timings), 1)
        self.assertEqual(sum(row['operation'] == 'closing_context' for row in timings), 1)
        canonical_reads = sum(row['operation'] == 'get' and row['module'] == 'disco.decisions.explorer' for row in timings)
        original = self.manager.history.get
        with patch.object(self.manager.history, 'get', side_effect=original), capture_timings() as custom_timings:
            custom = self.case.client.post(root + '/list-selection', json=body, headers=self.case.headers)
        self.assertEqual(custom.status_code, 200, custom.get_json())
        self.assertEqual(custom.get_json(), response.get_json())
        custom_reads = sum(row['operation'] == 'get' and row['module'] == 'disco.decisions.explorer' for row in custom_timings)
        self.assertLessEqual(canonical_reads, custom_reads)

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
        self.assertEqual(prepared['origin_count'], 0, 'the pool is the diff against current main, not a union of proposals')
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
        # Changed metadata is still new data the query matches: it is offered
        # with its current fingerprint in a fresh candidate, never an old value.
        queue = self.queue()
        self.assertEqual(queue['pending_epoch_count'], 2)
        response = self.case.client.post(self.case.base + '/workbench/prepare', json=dict(expected_queue_revision=queue['queue_revision']), headers=self.case.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        recipe = self.manager.history.get(response.get_json()['candidate_revision_uuid'])['recipe']
        self.assertEqual({row['uuid']: row['metadata_hash'] for row in recipe['epochs']}[new], 'c' * 64)

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

    def test_disagreeing_original_flags_leave_epoch_out_and_changed_fingerprint_uses_fresh_proposal(self):
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
        # Overlapping proposals disagree: leaving the epoch out wins, never selection.
        prepared, _ = self.prepare()
        decision = next(item for item in prepared['context']['draft']['decisions'] if item['epoch_uuid'] == self.added)
        self.assertTrue(decision['excluded'])
        self.assertFalse(decision['selected'])
        # A later original can contain the SAME native UUID with a new value.
        # Old proposals no longer match it and contribute nothing; the fresh
        # proposal offers the current value, never an invented winner.
        self.case.service._fingerprints[self.added] = 'c' * 64
        baselines = self.case.protocol_suggestions.freeze_baselines('actor-one', self.manager.state)
        result = self.case.protocol_suggestions.rerun(baselines, 'changed-source', 'changed.h5', 'actor-one')
        self.assertEqual(result['counts']['created_count'], 1, result)
        fresh, _ = self.prepare()
        recipe = self.manager.history.get(fresh['candidate_revision_uuid'])['recipe']
        self.assertEqual({row['uuid']: row['metadata_hash'] for row in recipe['epochs']}[self.added], 'c' * 64)


    def merge_all(self, queue=None, operation=None):
        queue = queue or self.queue()
        return self.case.client.post(self.case.base + '/workbench/merge-all', json=dict(
            expected_queue_revision=queue['queue_revision'], operation_uuid=operation or str(uuid.uuid4())),
            headers=self.case.headers)

    def test_merge_all_never_merges_epochs_left_out_after_recording_exclude_and_reinclude(self):
        # Excluding and re-including a recording returns the pool to an earlier
        # content, so its earlier immutable candidate is reused. The leave-out
        # made in between must carry into it: queue and merge-all read one draft.
        first, _ = self.more_import()
        self.assertEqual(self.queue()['pending_epoch_count'], 2)
        earlier, _ = self.prepare()
        source = self.case.service.rows[first]['source_sha256']
        project = self.case.service.project['project_uuid']
        self.case.data_store_states.insert1(dict(project_uuid=project, source_sha256=source, query_excluded=True,
            archived=False, frozen=False, version=1, updated_at=None, actor='actor-one', server_actor='actor-one', reason='t'))
        self.assertEqual(self.queue()['pending_epoch_count'], 1)
        narrowed, _ = self.prepare()
        self.assertNotEqual(narrowed['candidate_revision_uuid'], earlier['candidate_revision_uuid'])
        self.patch_draft(narrowed, [dict(epoch_uuid=self.added, excluded=True)])
        self.case.data_store_states.rows[:] = [row for row in self.case.data_store_states.rows if row['source_sha256'] != source]
        queue = self.queue()
        self.assertEqual((queue['pending_epoch_count'], queue['left_out_epoch_count']), (1, 1))
        reused, _ = self.prepare()
        self.assertEqual(reused['candidate_revision_uuid'], earlier['candidate_revision_uuid'])
        self.assertTrue(reused['reused'])
        decision = next(item for item in reused['context']['draft']['decisions'] if item['epoch_uuid'] == self.added)
        self.assertTrue(decision['excluded'])
        self.assertEqual(self.queue()['queue_revision'], queue['queue_revision'], 'preparation keeps its own fence')
        merged = self.merge_all(queue)
        self.assertEqual(merged.status_code, 200, merged.get_json())
        self.assertEqual(merged.get_json()['accepted_epoch_uuids'], [first])
        queue = self.queue()
        self.assertEqual((queue['pending_epoch_count'], queue['left_out_epoch_count']), (0, 1))

    def test_draft_edits_on_a_reused_candidate_stay_the_latest_review(self):
        first, _ = self.more_import()
        earlier, _ = self.prepare()
        source = self.case.service.rows[first]['source_sha256']
        project = self.case.service.project['project_uuid']
        self.case.data_store_states.insert1(dict(project_uuid=project, source_sha256=source, query_excluded=True,
            archived=False, frozen=False, version=1, updated_at=None, actor='actor-one', server_actor='actor-one', reason='t'))
        narrowed, _ = self.prepare()
        self.patch_draft(narrowed, [dict(epoch_uuid=self.added, excluded=True)])
        self.case.data_store_states.rows[:] = [row for row in self.case.data_store_states.rows if row['source_sha256'] != source]
        reused, _ = self.prepare()
        # Re-allow the epoch and leave the other out on the reused candidate:
        # the queue must follow that newer draft, not the newer-created one.
        self.patch_draft(reused, [dict(epoch_uuid=self.added, excluded=False), dict(epoch_uuid=first, excluded=True)])
        queue = self.queue()
        self.assertEqual((queue['pending_epoch_count'], queue['left_out_epoch_count']), (1, 1))
        self.assertEqual([item['source_sha256'] for item in queue['pending_recordings']],
                         [self.case.service.rows[self.added]['source_sha256']])
        merged = self.merge_all(queue)
        self.assertEqual(merged.status_code, 200, merged.get_json())
        self.assertEqual(merged.get_json()['accepted_epoch_uuids'], [self.added])

    def test_failed_merge_all_persists_no_all_consent_or_draft_version(self):
        self.more_import()
        prepared, _ = self.prepare()
        draft = prepared['context']['draft']
        queue = self.queue()
        self.case.app.config['TESTING'] = False
        with patch.object(self.manager, 'verify_sources', side_effect=WorkbenchConflict('Source changed')):
            failed = self.merge_all(queue)
        self.assertEqual(failed.status_code, 409, failed.get_json())
        context = self.get_context('/api' + prepared['root'])
        self.assertEqual((context['draft']['selection_mode'], context['draft']['draft_version']),
                         (draft['selection_mode'], draft['draft_version']))
        self.assertEqual(self.queue()['queue_revision'], queue['queue_revision'])
        # Nothing to merge (every epoch left out) also leaves the draft alone.
        prepared = self.patch_draft(prepared, [dict(epoch_uuid=key, excluded=True) 
            for key in self.manager.pending_pool(self.protocol)['pool']])
        draft = prepared['context']['draft']
        queue = self.queue()
        empty = self.merge_all(queue)
        self.assertEqual(empty.status_code, 400, empty.get_json())
        context = self.get_context('/api' + prepared['root'])
        self.assertEqual((context['draft']['selection_mode'], context['draft']['draft_version']),
                         (draft['selection_mode'], draft['draft_version']))
        self.assertEqual(self.queue()['queue_revision'], queue['queue_revision'])

    def test_merge_all_replay_requires_a_merge_receipt_for_the_same_protocol(self):
        self.more_import()
        prepared, _ = self.prepare(dict(expected_queue_revision=self.queue()['queue_revision'],
                                        operation_uuid=str(uuid.uuid4())))
        # A prepare receipt's operation UUID never replays as a merge.
        reused = self.merge_all(operation=prepared['operation_uuid'])
        self.assertEqual(reused.status_code, 409, reused.get_json())
        merged = self.merge_all()
        self.assertEqual(merged.status_code, 200, merged.get_json())
        other = str(uuid.uuid4())
        self.case.service.protocols[other] = self.case.service.protocols[self.protocol]
        response = self.case.client.post('/api/protocols/' + other + '/workbench/merge-all', json=dict(
            expected_queue_revision='unused', operation_uuid=merged.get_json()['operation_uuid']), headers=self.case.headers)
        self.assertEqual(response.status_code, 409, response.get_json())

    def test_published_refresh_recomputes_the_pool_even_when_map_identity_and_size_repeat(self):
        foreign, _ = self.more_import()
        recorded = self.case.service.rows[self.added]['protocol_name']
        self.case.service.rows[foreign]['protocol_name'] = 'other.lab.protocols.TripleHistory'
        self.case.service._explore_publication = 'publication-one'
        self.assertEqual(self.queue()['pending_epoch_count'], 1)
        # A refresh publishes rows under a new publication token. The pool must
        # not depend on fingerprint-map address reuse to notice it.
        self.case.service.rows[foreign]['protocol_name'] = recorded
        self.case.service._explore_publication = 'publication-two'
        self.assertEqual(self.queue()['pending_epoch_count'], 2)

    def recipe_reads(self, action):
        """Stored recipe reads (ExplorerHistory.get fetches and re-hashes) by one action."""
        log = self.case.explorer_revisions.read_log
        start = len(log)
        action()
        return sum(entry['projected'] is None and any('revision_uuid' in restriction for restriction in entry['restrictions']
                   if isinstance(restriction, dict)) for entry in log[start:])

    def test_queue_and_candidate_recipe_reads_stay_flat_as_imports_grow(self):
        queue_reads, page_reads = [], []
        for _ in range(5):
            self.more_import()
            prepared, _ = self.prepare()
            self.queue()  # Admit discovery facts once; later reads must not re-read them.
            self.epochs(prepared)
            queue_reads.append(self.recipe_reads(self.queue))
            page_reads.append(self.recipe_reads(lambda: self.epochs(prepared)))
        self.assertEqual(len(set(queue_reads)), 1, queue_reads)
        self.assertEqual(len(set(page_reads)), 1, page_reads)
        # A candidate read verifies candidate, baseline and main once each.
        self.assertLessEqual(page_reads[0], 3, page_reads)

    def test_candidate_read_builds_one_full_context_and_closes_with_tokens(self):
        prepared, _ = self.prepare()
        with patch.object(self.manager, 'proposal', wraps=self.manager.proposal) as proposals:
            self.epochs(prepared)
        self.assertEqual(proposals.call_count, 1)
        revision, actor = prepared['candidate_revision_uuid'], prepared['actor']
        opened = self.manager.context(self.protocol, revision, actor)
        def closing():
            return self.manager.context(self.protocol, revision, actor, closing=opened)['candidate_scope_revision']
        def full():
            return self.manager.context(self.protocol, revision, actor)['candidate_scope_revision']
        with patch.object(self.manager, 'proposal', side_effect=AssertionError('closing must not rebuild')):
            self.assertEqual(closing(), opened['candidate_scope_revision'])
        service = self.case.service
        original_scope = service.source_scope
        changes = [
            ('draft', lambda: self.patch_draft(prepared, deferred=True), None),
            ('source', lambda: setattr(service, 'source_scope', lambda: {**original_scope(), 'revision': 'changed'}),
             lambda: setattr(service, 'source_scope', original_scope)),
            ('publication', lambda: setattr(service, '_explore_publication', 'replaced'), None),
            ('fingerprint map', lambda: setattr(service, '_fingerprints', dict(service._fingerprints)), None),
        ]
        for name, change, restore in changes:
            with self.subTest(change=name):
                opened = self.manager.context(self.protocol, revision, actor)
                change()
                if name in ('publication', 'fingerprint map'):
                    # Unprovable identity: the close rebuilds in full (same content here).
                    with patch.object(self.manager, 'proposal', wraps=self.manager.proposal) as rebuilt:
                        self.assertEqual(closing(), opened['candidate_scope_revision'])
                    self.assertEqual(rebuilt.call_count, 1)
                    changed = next(iter(opened['pending']))
                    service._fingerprints[changed] = 'c' * 64
                    self.assertNotEqual(closing(), opened['candidate_scope_revision'])
                    service._fingerprints[changed] = opened['pending'][changed]
                else:
                    self.assertNotEqual(closing(), opened['candidate_scope_revision'])
                self.assertEqual(closing(), full(), 'closing tokens agree with a full rebuild')
                if restore:
                    restore()
        # A main rebound to another version of the same revision also refuses.
        opened = self.manager.context(self.protocol, revision, actor)
        binding = next(row for row in self.case.protocol_bindings.rows if row['protocol_uuid'] == self.protocol)
        binding['version'] += 1
        self.assertNotEqual(closing(), opened['candidate_scope_revision'])
        binding['version'] -= 1

    def test_finish_and_carry_write_decisions_in_one_statement(self):
        first, _ = self.more_import()
        prepared, _ = self.prepare()
        root, context = '/api' + prepared['root'], prepared['context']
        with patch.object(self.tables[1], 'insert1', side_effect=AssertionError('per-row insert')), \
                patch.object(self.tables[1], 'insert', wraps=self.tables[1].insert) as inserts:
            finished = self.case.client.post(root + '/finish', json=dict(expected_version=context['draft']['draft_version'],
                expected_candidate_scope_revision=context['candidate_scope_revision']), headers=self.case.headers)
            self.assertEqual(finished.status_code, 200, finished.get_json())
            self.assertEqual(inserts.call_count, 1)
            self.more_import()
            carried, _ = self.prepare()
            self.assertEqual(inserts.call_count, 2)
        self.assertEqual(carried['draft_initialization']['carried_decision_count'], 2)
