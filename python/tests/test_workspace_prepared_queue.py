"""Current Workbench proofs survive historical eviction; reads never repair main."""
import copy
import unittest
import uuid
from unittest.mock import patch

from disco.decisions.explorer import MemberView
from disco.navigation.publication_changes import PreparationRequired
from disco.workbench.workbench import WorkbenchConflict
import test_workspace_workbench as fixtures
import test_workspace_prepared_overview as overview_fixtures


class PreparedQueueTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.WorkbenchTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.manager = self.fixture.manager
        self.service = self.fixture.case.service
        self.history = self.fixture.case.explorer_history
        self.protocol = self.fixture.protocol
        self.manager.queue_prepared_policy = lambda: True
        self.manager.queue_new_cells = lambda protocol, state, cells: len(cells)

    def queue(self):
        return self.manager.queue(self.protocol, 'actor-one')

    def test_first_queue_requires_preparation_and_does_not_prepare_profile(self):
        with self.assertRaises(PreparationRequired):self.queue()
        with patch.object(self.manager, '_profile', side_effect=AssertionError('full profile')):
            self.manager.prepare_queue_publication()
            self.manager._checks.clear()
            with patch.object(MemberView, '__iter__', side_effect=AssertionError('main scan')):
                result = self.queue()
        self.assertEqual(result['pending_epoch_count'], 1)

    def test_more_than_64_protocols_keep_current_checks_after_lru_eviction(self):
        original = copy.deepcopy(self.service.protocols[self.protocol])
        main = self.history.protocol_binding_header(self.protocol)
        recipe = self.history.get(main['revision_uuid'])['recipe']
        preview = dict(recipe, membership=recipe['epochs'], tree={'split_order': recipe['tree_view']['fields']})
        for index in range(65):
            protocol = str(uuid.uuid4())
            self.service.protocols[protocol] = copy.deepcopy(original)
            record = self.history.create(preview, self.service.sources, 'catalog.json', 'fixture', name=str(index))
            self.history.bind(record['revision_uuid'], protocol, 0, 'fixture', {}, 2)
        self.manager.prepare_queue_publication()
        self.manager._checks.clear()  # Deterministic historical-cache eviction.
        self.assertFalse(main['revision_uuid'] in self.manager._checks)
        with patch.object(MemberView, '__iter__', side_effect=AssertionError('main scan')):
            self.assertEqual(self.queue()['pending_epoch_count'], 1)
            header, members = self.manager._revision(main['revision_uuid'])
            self.assertEqual(self.manager._member_checks(main['revision_uuid'], header, members,
                self.service.source_scope()), (frozenset(), frozenset()))

    def test_merge_and_latest_undo_keep_proofs_without_main_profile_or_iteration(self):
        self.manager.prepare_queue_publication()
        state = self.manager.pending_pool(self.protocol, prepared_only=True)
        added = {self.fixture.added: self.service._fingerprints[self.fixture.added]}
        delta = self.history.create_delta(state['main']['revision_uuid'], added, [], 'fixture', name='Merge')
        self.history.bind(delta['revision_uuid'], self.protocol, state['binding']['version'], 'fixture', {}, 2)
        header, members = self.manager._revision(delta['revision_uuid'])
        self.manager._pool_after_merge(self.protocol, state, header, members, set(added))
        self.manager._checks.clear();self.manager._pool_cache.clear()
        with patch.object(MemberView, '__iter__', side_effect=AssertionError('main scan')), \
             patch.object(self.manager, '_profile', side_effect=AssertionError('all main cells')):
            self.assertEqual(self.queue()['pending_epoch_count'], 0)
            self.history.bind(state['main']['revision_uuid'], self.protocol, state['binding']['version'] + 1,
                'fixture', {}, 3)
            self.assertEqual(self.queue()['pending_epoch_count'], 1)

    def test_source_or_unavailable_metadata_invalidates_before_cell_lookup(self):
        self.manager.prepare_queue_publication()
        self.manager.queue_new_cells = lambda *args: self.fail('cell lookup before main validation')
        self.service._fingerprints = dict(self.service._fingerprints)
        self.service._fingerprints.pop(next(iter(self.fixture.fixture.before_ids)))
        with self.assertRaises(PreparationRequired):self.queue()

    def test_closing_binding_change_discards_queue(self):
        self.manager.prepare_queue_publication()
        def changed(protocol, state, cells):
            self.history.Binding.rows[0]['version'] += 1
            return len(cells)
        self.manager.queue_new_cells = changed
        with self.assertRaises(WorkbenchConflict):self.queue()

    def test_http_not_ready_requires_explicit_prepare_then_fresh_read(self):
        client = self.fixture.case.client
        path = self.fixture.case.base + '/workbench'
        response = client.get(path)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()['preparation']['resource'], 'workbench')
        self.assertNotIn('candidates', response.get_json())
        response = client.post('/api/workbench/prepare', json={}, headers=self.fixture.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['status'], 'ready')
        self.assertEqual(client.get(path).status_code, 200)
        self.service._fingerprints = dict(self.service._fingerprints)
        self.assertEqual(client.get(path).status_code, 202)

    def test_unbound_and_source_blocked_main_preserve_empty_counts_and_reason(self):
        self.service.set_source_state_provider(lambda: {'a' * 64: {'query_excluded': True}})
        self.manager.prepare_queue_publication()
        blocked = self.queue()
        self.assertIn('excluded', blocked['main_blocked_reason'])
        self.assertEqual((blocked['pending_epoch_count'], blocked['pending_new_cell_count']), (0, 0))
        self.history.Binding.rows.clear()
        empty = self.queue()
        self.assertIsNone(empty['main_blocked_reason'])
        self.assertEqual((empty['pending_epoch_count'], empty['pending_new_cell_count']), (0, 0))


class PreparedQueueCellsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = overview_fixtures.PreparedOverviewTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        f = self.fixture
        history = f.case.explorer_history
        preview = f.service.explore_preview({'all': []}, 'cell', include_tree=False, include_catalog_summary=False)
        record = history.create(preview, f.service.sources, 'catalog.json', 'fixture')
        history.bind(record['revision_uuid'], f.protocol, 0, 'fixture', {}, 2)
        f.prepare()
        self.state = {'binding': history.protocol_binding_header(f.protocol)}
        self.lookup = f.app.extensions['protocol_workbench'].queue_new_cells

    def test_pending_cells_lookup_never_iterates_all_main_cells(self):
        f = self.fixture
        model = f.app.extensions['prepared_overview']['model']
        class Cells(dict):
            def __iter__(self):raise AssertionError('all-main cell iteration')
        model.protocol_cells[f.protocol] = Cells(model.protocol_cells[f.protocol])
        cell = f.service.rows[f.ids[0]]['cell_uuid']
        self.assertEqual(self.lookup(f.protocol, self.state, {cell, 'new-cell'}), 1)

    def test_cell_lookup_closing_binding_change_rejects_count(self):
        from workspace_api import StaleWorkspace
        f = self.fixture
        model = f.app.extensions['prepared_overview']['model']
        class Cells(dict):
            def __contains__(self, key):
                f.case.explorer_history.Binding.rows[0]['version'] += 1
                return super().__contains__(key)
        model.protocol_cells[f.protocol] = Cells(model.protocol_cells[f.protocol])
        with self.assertRaises(StaleWorkspace):self.lookup(f.protocol, self.state, {'new-cell'})


if __name__ == '__main__':unittest.main()
