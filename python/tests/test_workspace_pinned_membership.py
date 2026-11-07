"""Pinned-only membership edits on isolated HTTP and transactional SQL doubles."""
import copy
import json
import unittest
import uuid
from unittest.mock import patch

import test_workspace_api as api_tests
Table = api_tests.Table


class PinnedMembershipTests(unittest.TestCase):
    def setUp(self):
        api_tests.WorkspaceAPITests.setUp(self)
        self.membership = Table(('project_uuid', 'lineage_uuid', 'epoch_uuid', 'added_revision_uuid'))
        self.connection.tables.append(self.membership)
        self.explorer_history._membership = self.membership
        verified = patch.object(self.service, '_verified_source', return_value=(None, None))
        verified.start(); self.addCleanup(verified.stop)
        self.original_base = self.base
        self.pin = self.create_pin('Pinned fixture')
        self.base = '/api/protocols/' + self.pin

    def create_pin(self, name):
        saved = self.client.post('/api/explore/revisions', json={
            'predicate': {'all': []}, 'splits': 'cell', 'name': name}, headers=self.headers)
        self.assertEqual(saved.status_code, 201, saved.json)
        record = saved.json
        response = self.client.post('/api/explore/revisions/' + record['revision_uuid'] + '/create-protocol',
            json={'name': name, 'protocol_id': 'example', 'expected_recipe_sha256': record['recipe']['content_sha256']}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.json)
        return response.json['protocol_uuid']

    def removal_body(self, ids=None, base=None):
        current = self.client.get(base or self.base)
        self.assertEqual(current.status_code, 200, current.json)
        return {'epoch_uuids': self.service.ids[:1] if ids is None else ids,
                'query_revision': current.json['query_revision'],
                'expected_binding_version': current.json['expected_binding_version'],
                'selection_scope': {'filters': {}, 'cell_uuid': None}}

    def remove(self, ids=None, body=None):
        return self.client.post(self.base + '/membership/remove', json=body or self.removal_body(ids), headers=self.headers)

    def undo(self, result):
        return self.client.post(self.base + '/membership/undo-remove', json={
            key: result['undo'][key] for key in ('removal_revision_uuid', 'expected_binding_version')}, headers=self.headers)

    def test_exact_removal_keeps_source_other_protocol_tags_and_old_recipe(self):
        other = self.create_pin('Other pin')
        original_rows = copy.deepcopy(self.service.rows)
        before = self.explorer_history.protocol_binding(self.pin)
        recipe_before = copy.deepcopy(before['recipe'])
        included = self.client.post(self.base + '/curation', json={
            'epoch_uuids': self.service.ids[:1], 'query_revision': self.client.get(self.base).json['query_revision'],
            'changes': {'tags_add': ['keep'], 'included': False}, 'expected_revisions': {self.service.ids[0]: 0}}, headers=self.headers)
        self.assertEqual(included.status_code, 200, included.json)
        curation_before = copy.deepcopy(self.curation.rows)
        result = self.remove()
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual((result.json['previous_count'], result.json['next_count']), (2, 1))
        self.assertEqual(result.json['removed_epoch_uuids'], self.service.ids[:1])
        self.assertEqual(self.client.get(self.base + '/epochs').json['total'], 1)
        self.assertEqual(self.client.get(self.base + '/tree?splits=cell').json['count'], 1)
        self.assertEqual(self.client.get(self.original_base).json['counts']['epochs'], 2)
        self.assertEqual(self.client.get('/api/protocols/' + other).json['counts']['epochs'], 2)
        self.assertEqual(self.client.get('/api/overview').json['counts']['epochs'], 2)
        self.assertEqual(self.service.rows, original_rows)
        self.assertEqual(self.curation.rows, curation_before)
        self.assertEqual(self.explorer_history.get(before['revision_uuid'])['recipe'], recipe_before)
        restored = self.undo(result.json)
        self.assertEqual(restored.status_code, 200, restored.json)
        self.assertEqual(self.curation.rows, curation_before)
        self.assertEqual(self.client.get(self.base + '/epochs').json['total'], 2)

    def test_remove_all_and_inverse_preserve_historical_lineage_then_allow_another_edit(self):
        root = self.explorer_history.protocol_binding_header(self.pin)['revision_uuid']
        self.assertEqual(self.membership.rows, [])
        result = self.remove(self.service.ids)
        self.assertEqual(result.status_code, 200, result.json)
        removed = result.json['binding']['revision_uuid']
        self.assertEqual(self.client.get(self.base).json['counts']['epochs'], 0)
        self.assertEqual(self.client.get(self.base + '/epochs').json['epochs'], [])
        self.assertEqual(self.client.get(self.base + '/tree?splits=cell').json['count'], 0)
        restored = self.undo(result.json)
        self.assertEqual(restored.status_code, 200, restored.json)
        inverse = restored.json['binding']['revision_uuid']
        for identity, expected in [(root, 2), (removed, 0), (inverse, 2)]:
            self.explorer_history.verify_membership(identity)
            self.assertEqual(len(self.explorer_history.verify_lineage(identity)), expected)
        again = self.remove(self.service.ids[1:])
        self.assertEqual(again.status_code, 200, again.json)
        self.explorer_history.verify_membership(again.json['binding']['revision_uuid'])
        second_inverse = self.undo(again.json)
        self.assertEqual(second_inverse.status_code, 200, second_inverse.json)
        self.explorer_history.verify_membership(second_inverse.json['binding']['revision_uuid'])
        for identity in [root, removed, inverse]:
            self.explorer_history.verify_membership(identity)

    def test_regular_protocol_is_refused_even_when_it_has_a_frozen_binding(self):
        binding = self.explorer_history.protocol_binding_header(self.pin)
        self.explorer_history.bind(binding['revision_uuid'], self.service.protocol_id, 0, 'tester',
            {'added': self.service.ids, 'removed': [], 'changed': []}, 0)
        response = self.client.post(self.original_base + '/membership/remove',
            json=self.removal_body(base=self.original_base), headers=self.headers)
        self.assertEqual(response.status_code, 400, response.json)
        self.assertIn('only for a pinned', response.json['error'])

    def test_shared_root_branches_keep_each_other_and_snapshot_verification_intact(self):
        from workspace_state_snapshot import verify_lineage_state
        history = self.explorer_history
        root = history.protocol_binding(self.pin)
        other = self.client.post('/api/explore/revisions/' + root['revision_uuid'] + '/create-protocol',
            json={'name': 'Shared-root pin', 'protocol_id': 'example',
                  'expected_recipe_sha256': root['recipe']['content_sha256']}, headers=self.headers)
        self.assertEqual(other.status_code, 201, other.json)
        other_base = '/api/protocols/' + other.json['protocol_uuid']
        a = self.remove()
        b = self.client.post(other_base + '/membership/remove',
            json=self.removal_body(base=other_base), headers=self.headers)
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        a_inverse = self.undo(a.json)
        self.assertEqual(a_inverse.status_code, 200, a_inverse.json)
        for identity in [root['revision_uuid'], a.json['binding']['revision_uuid'],
                         b.json['binding']['revision_uuid'], a_inverse.json['binding']['revision_uuid']]:
            history.verify_membership(identity)
        verify_lineage_state(dict(explorer_revision=copy.deepcopy(self.explorer_revisions.rows),
            protocol_binding=copy.deepcopy(self.protocol_bindings.rows),
            protocol_membership=copy.deepcopy(self.membership.rows)))
        b_inverse = self.client.post(other_base + '/membership/undo-remove', json={
            key: b.json['undo'][key] for key in ('removal_revision_uuid', 'expected_binding_version')}, headers=self.headers)
        self.assertEqual(b_inverse.status_code, 200, b_inverse.json)
        for identity in [b.json['binding']['revision_uuid'], b_inverse.json['binding']['revision_uuid']]:
            history.verify_membership(identity)

    def test_successive_removals_undo_in_order_without_rewinding_binding(self):
        first = self.remove()
        second = self.remove(self.service.ids[1:])
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(self.undo(first.json).status_code, 409)
        inverse = self.undo(second.json)
        self.assertEqual(inverse.status_code, 200, inverse.json)
        self.assertEqual(inverse.json['next_undo']['removal_revision_uuid'], first.json['undo']['removal_revision_uuid'])
        rebased = copy.deepcopy(first.json)
        rebased['undo'].update(inverse.json['next_undo'])
        restored = self.undo(rebased)
        self.assertEqual(restored.status_code, 200, restored.json)
        self.assertIsNone(restored.json['next_undo'])
        self.assertEqual(restored.json['next_count'], 2)
        self.assertEqual(restored.json['binding']['version'], second.json['binding']['version'] + 2)
        self.assertEqual(self.undo(rebased).status_code, 409)
        for result in [first, second, inverse, restored]:
            self.explorer_history.verify_membership(result.json['binding']['revision_uuid'])

    def test_stale_duplicate_outside_and_changed_view_requests_do_not_write(self):
        valid = self.removal_body()
        invalid = [dict(valid, query_revision='stale'), dict(valid, expected_binding_version=0),
            dict(valid, epoch_uuids=[self.service.ids[0]] * 2), dict(valid, epoch_uuids=[str(uuid.uuid4())]),
            dict(valid, epoch_uuids=[]), dict(valid, selection_scope={'filters': {}, 'cell_uuid': self.service.cell_ids[1]})]
        before = copy.deepcopy([table.rows for table in self.connection.tables])
        for body in invalid:
            response = self.remove(body=body)
            self.assertIn(response.status_code, (400, 409), response.json)
            self.assertEqual([table.rows for table in self.connection.tables], before)
        result = self.remove(body=valid)
        self.assertEqual(result.status_code, 200, result.json)
        snapshot = copy.deepcopy([table.rows for table in self.connection.tables])
        self.assertEqual(self.remove(body=valid).status_code, 409)
        self.assertEqual([table.rows for table in self.connection.tables], snapshot)

    def test_binding_failure_rolls_back_delta_audit_and_lineage(self):
        before = copy.deepcopy([table.rows for table in self.connection.tables])
        with patch.object(self.explorer_history, 'bind', side_effect=ValueError('Injected publication failure')):
            response = self.remove()
        self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual([table.rows for table in self.connection.tables], before)

    def test_undo_derives_exact_inverse_and_refuses_changed_metadata_or_newer_binding(self):
        result = self.remove()
        self.assertEqual(result.status_code, 200, result.json)
        body = {key: result.json['undo'][key] for key in ('removal_revision_uuid', 'expected_binding_version')}
        forged = self.client.post(self.base + '/membership/undo-remove', json={**body, 'epoch_uuids': self.service.ids}, headers=self.headers)
        self.assertEqual(forged.status_code, 400)
        key = self.service.ids[0]
        self.service._fingerprints[key] = 'c' * 64
        rejected = self.undo(result.json)
        self.assertEqual(rejected.status_code, 409, rejected.json)
        self.service._fingerprints[key] = 'b' * 64
        later = self.remove(self.service.ids[1:])
        self.assertEqual(later.status_code, 200, later.json)
        self.assertEqual(self.undo(result.json).status_code, 409)
        self.assertEqual(self.undo(later.json).status_code, 200)


import test_workspace_workbench as workbench_tests
import test_workspace_workbench_pending as pending_tests


class PinnedMembershipPendingTests(unittest.TestCase):
    setUp = workbench_tests.WorkbenchTests.setUp
    queue = pending_tests.CumulativePendingTests.queue
    prepare = pending_tests.CumulativePendingTests.prepare
    patch_draft = pending_tests.CumulativePendingTests.patch_draft
    accept_selected = pending_tests.CumulativePendingTests.accept_selected
    epochs = pending_tests.CumulativePendingTests.epochs

    def test_removal_from_partial_recording_keeps_unmerged_sibling_and_never_reoffers_removed_epoch(self):
        service = self.case.service
        # This owned fixture's frozen baseline is explicitly declared pinned.
        entry = service.protocols[self.protocol]
        entry['definition']['initial_revision_uuid'] = self.case.explorer_history.protocol_binding_header(self.protocol)['revision_uuid']
        entry['file'].write_text(json.dumps(entry['definition']))
        sibling = str(uuid.uuid4())
        service.rows[sibling] = {**copy.deepcopy(service.rows[self.added]), 'epoch_uuid': sibling}
        service.details[sibling] = copy.deepcopy(service.details[self.added])
        service._fingerprints[sibling] = service._fingerprints[self.added]
        entry['result']['epochs'].append({'uuid': sibling, 'metadata_hash': service._fingerprints[sibling]})
        service._explore_publication = str(uuid.uuid4())
        service._tree_catalog_cache = {}
        service._registered_tree_cache = service._registered_predicate_cache = service._predicate_catalog_cache = None
        self.assertEqual(self.queue()['pending_epoch_count'], 2)
        prepared, _ = self.prepare()
        self.assertEqual(self.epochs(prepared), {self.added, sibling})
        prepared = self.patch_draft(prepared, [dict(epoch_uuid=self.added, selected=True, reviewed=True)], selection_mode='selected')
        accepted = self.accept_selected(prepared)
        self.assertEqual(accepted['accepted_epoch_uuids'], [self.added])
        current = self.case.client.get(self.case.base).json
        result = self.case.client.post(self.case.base + '/membership/remove', json={
            'epoch_uuids': [self.added], 'query_revision': current['query_revision'],
            'expected_binding_version': current['expected_binding_version'],
            'selection_scope': {'filters': {}, 'cell_uuid': None}}, headers=self.case.headers)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(self.queue()['pending_epoch_count'], 1)
        fresh, _ = self.prepare()
        self.assertEqual(self.epochs(fresh), {sibling})
        # Restart the read manager's discovery memos: the suppression is sealed,
        # never a transient renderer/draft exclusion.
        self.manager._discovery.clear(); self.manager._discovery_scopes.clear(); self.manager._pool_cache.clear()
        self.assertEqual(set(self.manager.pending_pool(self.protocol)['pool']), {sibling})
        undo = self.case.client.post(self.case.base + '/membership/undo-remove', json={
            key: result.json['undo'][key] for key in ('removal_revision_uuid', 'expected_binding_version')}, headers=self.case.headers)
        self.assertEqual(undo.status_code, 200, undo.json)
        self.assertEqual(set(self.manager.pending_pool(self.protocol)['pool']), {sibling})
        history = self.case.explorer_history
        for identity in [accepted['binding']['revision_uuid'], result.json['binding']['revision_uuid'], undo.json['binding']['revision_uuid']]:
            history.verify_membership(identity)
