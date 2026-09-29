"""Durable tree settings through real HTTP routes and isolated SQL table doubles."""
import copy
import unittest
from unittest.mock import patch
from test_workspace_api import WorkspaceAPITests
from test_workspace_curation import Table
from workspace_tree_layouts import TreeLayouts


class TreeLayoutTests(unittest.TestCase):
    def setUp(self):
        self.fixture = WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.table = Table(('project_uuid', 'protocol_uuid'))
        self.fixture.connection.tables.append(self.table)
        self.layouts = TreeLayouts(self.fixture.store, table=self.table)
        self.fixture.app.extensions['tree_layouts'] = self.layouts
        self.client = self.fixture.client
        self.url = self.fixture.base + '/tree-layout'

    def put(self, fields, version=0):
        return self.client.put(self.url, json={'split_order': fields, 'expected_version': version},
                               headers=self.fixture.headers)

    def test_restore_after_service_recreation_and_no_membership_change(self):
        before = copy.deepcopy((self.fixture.service.protocols, self.fixture.curation.rows))
        self.assertEqual(self.client.get(self.url).get_json()['version'], 0)
        response = self.put(['cell', 'date', 'parameters/example'])
        self.assertEqual(response.status_code, 200, response.get_json())
        self.fixture.app.extensions['tree_layouts'] = TreeLayouts(self.fixture.store, table=self.table)
        saved = self.client.get(self.url).get_json()
        self.assertEqual(saved['split_order'], ['cell', 'date', 'parameters/example'])
        self.assertEqual(saved['version'], 1)
        self.assertEqual((self.fixture.service.protocols, self.fixture.curation.rows), before)
        self.assertEqual(self.fixture.events.rows, [])

    def test_stale_versions_invalid_fields_and_foreign_protocols_do_not_write(self):
        self.assertEqual(self.put(['cell']).status_code, 200)
        self.assertEqual(self.put(['date']).status_code, 409)
        self.assertEqual(self.put(['does-not-exist'], 1).status_code, 400)
        self.assertEqual(self.put(['cell', 'cell'], 1).status_code, 400)
        self.assertEqual(self.put(['date'], True).status_code, 400)
        self.assertEqual(len(self.table.rows), 1)
        self.assertEqual(len(self.fixture.events.rows), 0)

    def test_flat_layout_idempotency_and_project_isolation(self):
        self.assertEqual(self.put([]).status_code, 200)
        self.assertEqual(self.put([], 1).get_json()['version'], 1)
        self.assertEqual(len(self.fixture.events.rows), 0)
        other = copy.copy(self.fixture.store)
        other.project_uuid = '00000000-0000-0000-0000-000000000001'
        self.assertIsNone(TreeLayouts(other, table=self.table).read(self.fixture.service.protocol_id))

    def test_audit_failure_rolls_back_layout(self):
        with patch.object(self.fixture.store, '_event', side_effect=RuntimeError('Audit unavailable')):
            response = self.put(['cell'])
        self.assertEqual(response.status_code, 500)
        self.assertFalse(self.table.rows)

    def test_write_guard_and_filtered_scope_rejected(self):
        self.assertEqual(self.client.put(self.url, json={'split_order':['cell'], 'expected_version':0}).status_code, 403)
        self.assertEqual(self.client.get(self.url+'?cell_uuid=x').status_code, 400)
        self.assertFalse(self.table.rows)
