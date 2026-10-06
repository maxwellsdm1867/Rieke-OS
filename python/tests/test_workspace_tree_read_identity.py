"""Read-only HTTP witness; isolated in-memory fixture, no scientific writes."""
import tempfile
import unittest
from contextlib import nullcontext
from threading import RLock
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from disco.metadata.disk_index import DiskMetadataIndex
from flask import Flask
from disco.navigation.tree_pages import register_tree_page_routes
from test_workspace_api import FixtureService
from test_workspace_curation import Connection


class TreeReadIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = FixtureService(self.temp.name)
        connection = Connection([])
        self.service.dj = SimpleNamespace(conn=lambda: connection)
        self.service.disk_index = DiskMetadataIndex.build(Path(self.temp.name)/'read-index.sqlite', self.service.rows, self.service.details, self.service.sources, 'fixture-index', self.service.project['project_uuid'])
        self.addCleanup(self.service.disk_index.close)
        self.annotations = {'shared': 1, 'protocol': 1}
        self.service._explore_state_generation = SimpleNamespace(
            token=lambda protocol: self.annotations['protocol' if protocol else 'shared'])
        self.app = Flask(__name__)
        self.app.register_error_handler(ValueError, lambda error: ({'error': str(error)}, 400))
        register_tree_page_routes(self.app, self.service, RLock(), nullcontext)
        self.client = self.app.test_client()
        self.body = {'protocol_uuid': self.service.protocol_id, 'filters': {},
                     'splits': 'date,cell,block', 'path': [], 'offset': 0, 'limit': 60}

    def read(self, **changes):
        response = self.client.post('/api/tree-pages', json={**self.body, **changes})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_current_read_identity_changes_for_annotation_restart_and_binding(self):
        first = self.read()
        identity = first.get('read_identity')
        self.assertIsNotNone(identity, 'tree revision alone does not attest backend/annotation identity')
        self.assertEqual(identity['project_uuid'], self.service.project['project_uuid'])
        self.assertEqual(identity['project_path'], str(self.service.project_dir.resolve()))
        self.assertEqual(identity['protocol_uuid'], self.service.protocol_id)
        self.assertEqual(identity['tree_revision'], first['revision'])
        self.assertEqual(identity, self.read()['read_identity'])
        for target in ['shared', 'protocol']:
            self.annotations[target] += 1
            changed = self.read()
            self.assertEqual(changed['revision'], first['revision'])
            self.assertNotEqual(changed['read_identity']['generation']['annotation'], identity['generation']['annotation'])
            identity = changed['read_identity']
        self.service._explore_publication = None
        restarted = self.read()['read_identity']
        self.assertNotEqual(restarted['generation']['publication'], identity['generation']['publication'])
        self.service.binding_header_provider = lambda protocol: {'project_uuid': self.service.project['project_uuid'], 'protocol_uuid': protocol, 'revision_uuid': 'new-binding', 'version': 7}
        self.assertNotIn('read_identity', self.read(), 'custom unmatched binding policy cannot attest reuse')

    def test_ineligible_scopes_do_not_advertise_reuse(self):
        self.assertNotIn('read_identity', self.read(filters={'cell_type': 'fixture-type'}))
        body = {key: value for key, value in self.body.items() if key != 'protocol_uuid'}
        result = self.client.post('/api/tree-pages', json=body)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('read_identity', result.get_json())

    def test_unavailable_native_tracker_and_custom_policy_remain_fresh_without_witness(self):
        self.service._explore_state_generation.token = lambda protocol: None
        self.assertNotIn('read_identity', self.read())
        self.service._explore_state_generation = None
        self.assertNotIn('read_identity', self.read())

    def test_mutation_during_construction_is_not_stamped_with_new_generation(self):
        pager = self.app.extensions['disco.navigation.tree_pages']
        original = pager.page
        def racing(body):
            result = original(body)
            self.annotations['shared'] += 1
            return result
        with patch.object(pager, 'page', side_effect=racing):
            response = self.client.post('/api/tree-pages', json=self.body)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('read_identity', response.get_json())

    def test_native_response_contract_attests_twice_while_reading_live_scope_counters(self):
        from workspace_state_generation import StateGenerationAuthority
        tracker = StateGenerationAuthority(SimpleNamespace(_conn=object(), in_transaction=False), self.service.project['project_uuid'])
        tracker.ready = True
        attestations, scopes = [], []
        tracker._attest_contract = lambda: attestations.append(True) or 'verified contract'
        tracker._scope = lambda kind, identity: (scopes.append((kind, identity)) or ('verified epoch', 1))
        self.service._explore_state_generation = tracker
        self.assertIn('read_identity', self.read())
        self.assertEqual(len(attestations), 2)
        self.assertEqual(len(scopes), 6, 'shared and protocol generations remain fresh at both boundaries')
        self.assertIsNone(tracker._response_contract.get())

    def test_native_closing_contract_change_discards_complete_response(self):
        from workspace_state_generation import StateGenerationAuthority
        tracker = StateGenerationAuthority(SimpleNamespace(_conn=object(), in_transaction=False), self.service.project['project_uuid'])
        tracker.ready = True
        calls = []
        tracker._attest_contract = lambda: calls.append(True) or ('before' if len(calls) == 1 else 'after')
        tracker._scope = lambda kind, identity: ('verified epoch', 1)
        self.service._explore_state_generation = tracker
        response = self.client.post('/api/tree-pages', json=self.body)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('read_identity', response.get_json())
        self.assertIsNone(tracker._response_contract.get())

    def test_live_bundle_matches_pages_under_one_witness(self):
        import cProfile
        anchor = next(iter(self.service.rows))
        profiler = cProfile.Profile();profiler.enable()
        result = self.read(anchor_uuid=anchor, include_ancestors=True, counts_only=True)
        profiler.disable()
        self.assertTrue(result['tree_column_pages'])
        parents = result.pop('ancestor_pages')
        self.assertEqual(result, self.read(anchor_uuid=anchor, counts_only=True))
        self.assertEqual(len(parents), len(result['path']))
        for depth, parent in enumerate(parents):
            self.assertEqual(parent, self.read(path=result['path'][:depth],
                offset=result['ancestors'][depth]['parent_offset'], revision=result['revision'], counts_only=True))
        self.assertLessEqual(sum(entry.callcount for entry in profiler.getstats()
            if getattr(entry.code, 'co_name', '') == '_build_scope'), 1)

    def test_live_bundle_bounds_ineligible_and_custom_readers_fail_closed(self):
        for changes in ({'include_ancestors': 1}, {'ancestor_offsets': [0]},
                        {'include_ancestors': True, 'ancestor_offsets': [0]*9},
                        {'include_ancestors': True, 'ancestor_offsets': [True]},
                        {'include_ancestors': True, 'filters': {'cell_type': 'fixture-type'}}):
            self.assertEqual(self.client.post('/api/tree-pages', json={**self.body, **changes}).status_code, 400)
        pager = self.app.extensions['disco.navigation.tree_pages']
        original = pager.page
        with patch.object(pager, 'page', side_effect=original):
            self.assertNotIn('tree_column_pages', self.read())
            self.assertEqual(self.client.post('/api/tree-pages', json={**self.body, 'include_ancestors': True}).status_code, 400)
        self.service._explore_state_generation.token = lambda protocol: None
        self.assertEqual(self.client.post('/api/tree-pages', json={**self.body, 'include_ancestors': True}).status_code, 400)

    def test_live_bundle_closing_generation_discards_all_pages(self):
        pager = self.app.extensions['disco.navigation.tree_pages']
        original = pager.column_pages
        def racing(*args):
            result = original(*args)
            self.annotations['shared'] += 1
            return result
        with patch.object(pager, 'column_pages', side_effect=racing):
            response = self.client.post('/api/tree-pages', json={**self.body,
                'include_ancestors': True, 'anchor_uuid': next(iter(self.service.rows))})
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('ancestor_pages', response.get_json())

    def test_recorded_metadata_layout_shares_one_guarded_projection(self):
        import cProfile
        self.service.disk_index.close()
        for details in self.service.details.values():
            details['metadata'] = {'cell': {'start_time': '2026-01-01T00:00:00'}}
        self.service.disk_index = DiskMetadataIndex.build(Path(self.temp.name)/'metadata-read-index.sqlite',
            self.service.rows, self.service.details, self.service.sources, 'metadata-fixture', self.service.project['project_uuid'])
        self.addCleanup(self.service.disk_index.close)
        splits = 'cell type,metadata/cell/start_time'
        anchor = next(iter(self.service.rows))
        expected = self.read(splits=splits, anchor_uuid=anchor, counts_only=True)
        self.assertTrue(expected['tree_column_pages'])
        profiler = cProfile.Profile();profiler.enable()
        actual = self.read(splits=splits, anchor_uuid=anchor, counts_only=True, include_ancestors=True)
        profiler.disable()
        parents = actual.pop('ancestor_pages');self.assertEqual(actual, expected)
        for depth, parent in enumerate(parents):
            self.assertEqual(parent, self.read(splits=splits, path=actual['path'][:depth],
                revision=actual['revision'], counts_only=True, offset=actual['ancestors'][depth]['parent_offset']))
        self.assertLessEqual(sum(entry.callcount for entry in profiler.getstats()
            if getattr(entry.code, 'co_name', '') == '_build_scope'), 1)
        self.assertEqual(self.client.post('/api/tree-pages', json={**self.body,
            'splits': 'metadata/unknown', 'include_ancestors': True}).status_code, 400)

    def test_bundle_closing_source_change_discards_response(self):
        from disco.metadata import explore_queries
        original = explore_queries.generation
        calls = []
        def changed(*args, **kwargs):
            value = original(*args, **kwargs);calls.append(True)
            return {**value, 'source': 'changed'} if len(calls)>1 else value
        with patch.object(explore_queries, 'generation', side_effect=changed):
            response = self.client.post('/api/tree-pages', json={**self.body, 'include_ancestors': True})
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('ancestor_pages', response.get_json())
