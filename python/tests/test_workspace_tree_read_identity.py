"""Read-only HTTP witness; isolated in-memory fixture, no scientific writes."""
import tempfile
import unittest
from contextlib import nullcontext
from threading import RLock
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from workspace_disk_index import DiskMetadataIndex
from flask import Flask
from workspace_tree_pages import register_tree_page_routes
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
        pager = self.app.extensions['workspace_tree_pages']
        original = pager.page
        def racing(body):
            result = original(body)
            self.annotations['shared'] += 1
            return result
        with patch.object(pager, 'page', side_effect=racing):
            response = self.client.post('/api/tree-pages', json=self.body)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('read_identity', response.get_json())
