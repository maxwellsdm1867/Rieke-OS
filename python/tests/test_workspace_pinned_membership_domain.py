"""Epoch membership, derived cells and frozen exports on isolated HTTP fixtures."""
import copy
import unittest

import test_workspace_pinned_membership as pinned_tests
import test_workspace_workbench as workbench_tests


class PinnedMembershipDomainTests(unittest.TestCase):
    setUp = pinned_tests.PinnedMembershipTests.setUp
    create_pin = pinned_tests.PinnedMembershipTests.create_pin
    removal_body = pinned_tests.PinnedMembershipTests.removal_body
    remove = pinned_tests.PinnedMembershipTests.remove
    undo = pinned_tests.PinnedMembershipTests.undo

    def test_mixed_protocol_shared_cell_removal_and_undo_preserve_sources_and_export(self):
        first, second = self.service.ids
        self.service.rows[second].update(
            protocol_name='lab.OtherProtocol',
            cell_uuid=self.service.rows[first]['cell_uuid'],
            cell_label=self.service.rows[first]['cell_label'])
        saved = self.client.post('/api/explore/revisions', json={
            'predicate': {'all': []}, 'splits': 'cell', 'name': 'Mixed shared cell'},
            headers=self.headers)
        self.assertEqual(saved.status_code, 201, saved.json)
        candidate = saved.json
        created = self.client.post(
            '/api/explore/revisions/' + candidate['revision_uuid'] + '/create-protocol',
            json={'name': 'Mixed shared cell', 'protocol_ids': ['example', 'lab.OtherProtocol'],
                  'expected_recipe_sha256': candidate['recipe']['content_sha256']},
            headers=self.headers)
        self.assertEqual(created.status_code, 201, created.json)
        protocol = created.json['protocol_uuid']
        self.base = '/api/protocols/' + protocol
        original_rows = copy.deepcopy(self.service.rows)
        original_definition = copy.deepcopy(self.service.protocols[protocol]['definition'])

        def assert_counts(epochs, cells):
            response = self.client.get(self.base)
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(response.json['counts']['epochs'], epochs)
            self.assertEqual(response.json['counts']['cells'], cells)
            self.assertEqual(len(response.json['cells']), cells)
            return response.json

        initial = assert_counts(2, 1)
        exported = self.client.post(self.base + '/exports', json={
            'name': 'Before removal', 'review_policy': 'include_unreviewed',
            'query_revision': initial['query_revision'], 'split_order': 'cell'},
            headers=self.headers)
        self.assertEqual(exported.status_code, 201, exported.json)
        download = exported.json['download_url']
        frozen_export = self.client.get(download)
        self.addCleanup(frozen_export.close)
        self.assertEqual(frozen_export.status_code, 200)
        self.assertEqual({row['epoch_uuid'] for row in frozen_export.json['epochs']}, {first, second})

        first_removal = self.remove([first])
        self.assertEqual(first_removal.status_code, 200, first_removal.json)
        assert_counts(1, 1)
        self.assertEqual(self.client.get(self.base + '/epochs').json['epochs'][0]['epoch_uuid'], second)
        second_removal = self.remove([second])
        self.assertEqual(second_removal.status_code, 200, second_removal.json)
        assert_counts(0, 0)

        inverse = self.undo(second_removal.json)
        self.assertEqual(inverse.status_code, 200, inverse.json)
        assert_counts(1, 1)
        self.assertEqual(inverse.json['next_undo']['removal_revision_uuid'],
                         first_removal.json['undo']['removal_revision_uuid'])
        earlier_inverse = self.client.post(self.base + '/membership/undo-remove',
            json=inverse.json['next_undo'], headers=self.headers)
        self.assertEqual(earlier_inverse.status_code, 200, earlier_inverse.json)
        assert_counts(2, 1)
        self.assertEqual(self.service.rows, original_rows)
        self.assertEqual(self.service.protocols[protocol]['definition'], original_definition)
        retained_export = self.client.get(download)
        self.addCleanup(retained_export.close)
        self.assertEqual(retained_export.data, frozen_export.data)
        for result in (first_removal, second_removal, inverse, earlier_inverse):
            self.explorer_history.verify_membership(result.json['binding']['revision_uuid'])


class SharedMergeMembershipDomainTests(unittest.TestCase):
    def test_merge_undo_preserves_another_pin_and_snapshot_using_the_merged_revision(self):
        from workspace_state_snapshot import verify_lineage_state

        fixture = workbench_tests.WorkbenchTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        case = fixture.case
        history = case.explorer_history
        accepted = fixture.accept(fixture.accepted_request())
        self.assertEqual(accepted.status_code, 200, accepted.json)
        merged = accepted.json
        record = history.get(merged['binding']['revision_uuid'])
        expected_members = set(history.members(record['revision_uuid']))
        created = case.client.post(
            '/api/explore/revisions/' + record['revision_uuid'] + '/create-protocol',
            json={'name': 'Independent pin on merged set', 'protocol_id': 'example',
                  'expected_recipe_sha256': record['recipe']['content_sha256']},
            headers=case.headers)
        self.assertEqual(created.status_code, 201, created.json)
        other = created.json['protocol_uuid']
        binding_before = copy.deepcopy(history.protocol_binding_header(other))
        index_before = copy.deepcopy(fixture.membership.rows)
        history.verify_membership(record['revision_uuid'])

        undone = case.client.post(case.base + '/workbench/undo', json={
            'operation_uuid': merged['operation_uuid'],
            'expected_binding_version': merged['binding']['version']}, headers=case.headers)
        self.assertEqual(undone.status_code, 200, undone.json)
        self.assertEqual(set(history.members(undone.json['restored_revision_uuid'])),
                         set(fixture.fixture.before_ids))
        self.assertEqual(history.protocol_binding_header(other), binding_before)
        self.assertEqual(fixture.membership.rows, index_before)
        other_epochs = case.client.get('/api/protocols/' + other + '/epochs')
        self.assertEqual(other_epochs.status_code, 200, other_epochs.json)
        self.assertEqual({row['epoch_uuid'] for row in other_epochs.json['epochs']}, expected_members)
        history.verify_membership(record['revision_uuid'])
        history.verify_membership(undone.json['restored_revision_uuid'])
        verify_lineage_state(dict(
            explorer_revision=copy.deepcopy(case.explorer_revisions.rows),
            protocol_binding=copy.deepcopy(case.protocol_bindings.rows),
            protocol_membership=copy.deepcopy(fixture.membership.rows)))
