"""Compact protocol entry keeps legacy summaries and independent page authority."""
import copy
import uuid
from unittest.mock import patch

import test_workspace_api as api_tests
import test_workspace_protocol_state as state_tests
from workspace_service import WorkspaceService


class ProtocolBrowseTests(api_tests.WorkspaceAPITests):
    def browse(self):
        return self.client.get(self.base + '?projection=browse')

    def test_descriptor_matches_summary_identity_without_computing_display_aggregates(self):
        full = self.client.get(self.base).get_json()
        with patch.object(self.service, '_counts', side_effect=AssertionError('Hidden counts')), \
             patch.object(self.service, '_cell_summary', side_effect=AssertionError('Hidden cells')), \
             patch.object(self.store, 'export_memberships', side_effect=AssertionError('Hidden exports')):
            response = self.browse()
        self.assertEqual(response.status_code, 200, response.get_json())
        entry = response.get_json()
        self.assertEqual(set(entry), {'definition', 'starter_query', 'effective_query', 'binding',
            'selection_options', 'groups', 'source_eligibility', 'query_revision',
            'expected_query_revision', 'expected_binding_version'})
        for key in entry:
            self.assertEqual(entry[key], full[key], key)
        self.assertEqual(self.client.get(self.base).get_json(), full)
        page = self.client.get(self.base + '/epochs?limit=1&include_cells=true').get_json()
        self.assertEqual(page['query_revision'], entry['query_revision'])
        self.assertEqual(len(page['epochs']), 1)
        self.assertEqual(sum(cell['epochs'] for cell in page['cells']), full['counts']['epochs'])

    def test_unknown_duplicate_and_filtered_projection_requests_fail_closed(self):
        for query in ('projection=unknown', 'projection=browse&projection=browse',
                      'projection=browse&cell_type=fixture-type', 'projection=browse&limit=1'):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(self.base + '?' + query).status_code, 400)
        self.assertIn('counts', self.client.get(self.base).get_json())

    def test_custom_protocol_projection_keeps_its_public_policy(self):
        original = self.service.protocol
        def custom(protocol, filters=None):
            result = original(protocol, filters)
            result['selection_options'] = {'cell_types': ['custom-visible-type']}
            result['groups'] = ['custom-visible-group']
            return result
        with patch.object(self.service, 'protocol', side_effect=custom) as called:
            response = self.browse()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(called.call_count, 1)
        self.assertEqual(response.get_json()['selection_options'], {'cell_types': ['custom-visible-type']})
        self.assertEqual(response.get_json()['groups'], ['custom-visible-group'])
        self.assertNotIn('counts', response.get_json())

    def test_class_override_is_not_mistaken_for_canonical_projection(self):
        original = WorkspaceService.protocol
        calls = []
        def custom(service, protocol, filters=None):
            calls.append(protocol)
            result = original(service, protocol, filters)
            result['groups'] = ['class policy']
            return result
        with patch.object(WorkspaceService, 'protocol', custom):
            response = self.browse()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(calls, [self.service.protocol_id])
        self.assertEqual(response.get_json()['groups'], ['class policy'])

    def test_nested_filter_override_keeps_its_narrowed_options(self):
        self.service.rows[self.service.ids[1]]['cell_type'] = 'hidden-type'
        self.service.rows[self.service.ids[1]]['group_label'] = 'hidden-group'
        original = self.service._filter_rows
        def narrow(rows, filters, protocol):
            return original([row for row in rows if row['epoch_uuid'] == self.service.ids[0]], filters, protocol)
        with patch.object(self.service, '_filter_rows', side_effect=narrow):
            full = self.client.get(self.base).get_json()
            response = self.browse()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['selection_options'], full['selection_options'])
        self.assertEqual(response.get_json()['groups'], full['groups'])
        self.assertNotIn('hidden-type', response.get_json()['selection_options']['cell_types'])

    def test_service_without_optional_browse_method_keeps_legacy_projection(self):
        full = self.client.get(self.base).get_json()
        with patch.object(self.service, 'protocol_browse', None):
            response = self.browse()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['query_revision'], full['query_revision'])
        self.assertEqual(response.get_json()['groups'], full['groups'])

    def test_legacy_descriptor_refuses_source_change_before_closing_receipt(self):
        original = self.service.protocol_browse
        states = {}
        self.service.source_state_provider = lambda: copy.deepcopy(states)
        def changed(protocol):
            result = original(protocol)
            states['a' * 64] = {'query_excluded': True, 'version': 1}
            return result
        with patch.object(self.service, 'protocol_browse', side_effect=changed):
            response = self.browse()
        self.assertEqual(response.status_code, 409, response.get_json())
        fresh = self.browse()
        self.assertEqual(fresh.status_code, 200, fresh.get_json())
        self.assertTrue(fresh.get_json()['source_eligibility']['propagation_required'])

    def test_interrupted_binding_creation_cannot_open_unbound_descriptor(self):
        self.service.protocols[self.service.protocol_id]['definition']['initial_revision_uuid'] = str(uuid.uuid4())
        response = self.browse()
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertIn('interrupted', response.get_json()['error'])

    def test_bound_descriptor_keeps_exact_query_and_rejects_unavailable_members(self):
        created = self.client.post('/api/explore/revisions', json={'predicate': {'all': [
            {'field': 'protocol', 'operator': 'eq', 'value': 'example'},
            {'field': 'parameters/example', 'operator': 'eq', 'value': 0}]},
            'splits': 'cell', 'name': 'One epoch'}, headers=self.headers)
        self.assertEqual(created.status_code, 201, created.get_json())
        root = '/api/explore/revisions/' + created.get_json()['revision_uuid']
        compared = self.client.post(root + '/compare-to-protocol', json={
            'protocol_uuid': self.service.protocol_id}, headers=self.headers).get_json()
        applied = self.client.post(root + '/apply-to-protocol', json={
            'protocol_uuid': self.service.protocol_id,
            'expected_binding_version': compared['expected_binding_version'],
            'expected_query_revision': compared['expected_query_revision']}, headers=self.headers)
        self.assertEqual(applied.status_code, 200, applied.get_json())
        full = self.client.get(self.base).get_json()
        entry = self.browse().get_json()
        self.assertEqual(entry['binding'], full['binding'])
        self.assertEqual(entry['effective_query'], full['effective_query'])
        self.assertEqual(entry['query_revision'], full['query_revision'])
        page = self.client.get(self.base + '/epochs').get_json()
        self.assertEqual([row['epoch_uuid'] for row in page['epochs']], self.service.ids[:1])
        del self.service.rows[self.service.ids[0]]
        response = self.browse()
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertIn('unavailable', response.get_json()['error'])


class NativeProtocolBrowseTests(state_tests.ProtocolStateTests):
    def test_native_descriptor_uses_current_context_without_full_saved_state(self):
        self.native_generation()
        full = self.client.get(self.case.base).get_json()
        with patch.object(self.reader, 'full_state', side_effect=AssertionError('No full saved state')):
            response = self.client.get(self.case.base + '?projection=browse')
        self.assertEqual(response.status_code, 200, response.get_json())
        entry = response.get_json()
        self.assertEqual(entry['query_revision'], full['query_revision'])
        self.assertEqual(entry['query_revision_contract'], 'protocol-state-v3')
        self.assertEqual(entry['expected_binding_version'], full['expected_binding_version'])
        self.assertNotIn('counts', entry)

    def test_native_descriptor_rejects_generation_change_during_projection(self):
        self.native_generation()
        original = self.service.protocol_browse
        def changed(protocol):
            result = original(protocol)
            self.service._fingerprints[self.ids[0]] = 'f' * 64
            return result
        with patch.object(self.service, 'protocol_browse', side_effect=changed):
            response = self.client.get(self.case.base + '?projection=browse')
        self.assertEqual(response.status_code, 409, response.get_json())


for _class, _base in ((ProtocolBrowseTests, api_tests.WorkspaceAPITests), (NativeProtocolBrowseTests, state_tests.ProtocolStateTests)):
    for _name in dir(_base):
        if _name.startswith('test_') and _name not in _class.__dict__:
            setattr(_class, _name, None)

del _class, _base
