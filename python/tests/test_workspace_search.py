import tempfile
import threading
import unittest

from workspace_search import register_search_routes, search_workspace
try:
    from .test_workspace_api import FixtureService
except ImportError:
    from test_workspace_api import FixtureService


class WorkspaceSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = FixtureService(self.temp.name)
        for index, identity in enumerate(self.service.ids):
            self.service.details[identity]['parameters'].update(history1=[30, 10] if index == 0 else [10, 30],
                frequencyCutoff=100 if index == 0 else 200, textNumber='100', control=bool(index))

    def test_uuid_uses_exact_identity_and_actual_working_membership(self):
        identity = self.service.ids[0]
        result = search_workspace(self.service, identity.upper())
        self.assertEqual(len(result['results']), 1)
        epoch = result['results'][0]
        self.assertEqual(epoch['epoch_uuid'], identity)
        self.assertEqual(epoch['protocol_uuid'], self.service.protocol_id)
        self.assertEqual(epoch['date'], '2026-09-24')
        self.service.protocols[self.service.protocol_id]['result']['epochs'] = []
        self.assertIsNone(search_workspace(self.service, identity)['results'][0]['protocol_uuid'])

    def test_cell_uuid_and_label_results_remain_separate(self):
        for row in self.service.rows.values():
            row['cell_label'] = 'Cell1'
        result = search_workspace(self.service, 'Cell1')
        cells = [row for row in result['results'] if row['kind'] == 'cell']
        self.assertEqual({row['id'] for row in cells}, set(self.service.cell_ids))
        self.assertEqual(search_workspace(self.service, self.service.cell_ids[1])['results'][0]['kind'], 'cell')

    def test_numeric_and_pair_search_across_fields_is_typed(self):
        numbers = search_workspace(self.service, '100')['results']
        values = [row['predicate']['value'] for row in numbers if row['kind'] == 'value']
        self.assertIn(100, values)
        self.assertNotIn('100', values)
        pair = search_workspace(self.service, '[30,10]')['results']
        self.assertEqual(len(pair), 1)
        self.assertEqual(pair[0]['predicate'], {'field': 'parameters/history1', 'operator': 'eq', 'value': [30,10]})

    def test_exact_field_alias_and_comparison_uses_predicate_engine(self):
        result = search_workspace(self.service, 'frequencyCutoff >= 100')['results'][0]
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['predicate']['operator'], 'gte')
        self.assertEqual(search_workspace(self.service, 'history1 = [30, 10]')['results'][0]['count'], 1)
        with self.assertRaises(ValueError):
            search_workspace(self.service, 'frequencyCutoff = "100"')
        with self.assertRaises(ValueError):
            search_workspace(self.service, 'frequencyCutoff = 9007199254740993')

    def test_effective_parameter_wins_over_source_metadata_copies(self):
        for identity in self.service.ids:
            self.service.details[identity]['metadata']['block'] = {'parameters': {'frequencyCutoff': 999, 'history1': [0,675]}}
            self.service.details[identity]['parameters']['history1'] = [0,675]
        result = search_workspace(self.service, 'frequencyCutoff = 100')['results'][0]
        self.assertEqual(result['field_id'], 'parameters/frequencyCutoff')
        self.assertEqual(result['count'], 1)
        result = search_workspace(self.service, 'history1 = [0,675]')['results'][0]
        self.assertEqual(result['field_id'], 'parameters/history1')
        self.assertEqual(result['count'], 2)
        result = search_workspace(self.service, 'metadata/block/parameters/frequencyCutoff = 999')['results'][0]
        self.assertEqual(result['field_id'], 'metadata/block/parameters/frequencyCutoff')
        self.assertEqual(result['count'], 2)

    def test_unresolved_nonparameter_alias_returns_labeled_choices(self):
        for identity in self.service.ids:
            self.service.details[identity]['metadata']['cell'] = {'properties': {'comment': 'same'}}
            self.service.details[identity]['metadata']['group'] = {'properties': {'comment': 'same'}}
        response = search_workspace(self.service, 'comment = same')
        self.assertTrue(response['field_ambiguous'])
        self.assertEqual(len(response['results']), 2)
        self.assertEqual(len({item['field_id'] for item in response['results']}), 2)

    def test_excluded_sources_remain_identity_searchable_but_not_predicate_members(self):
        self.service.set_source_state_provider(lambda: {'a'*64: {'version': 1, 'query_excluded': True}})
        self.assertTrue(search_workspace(self.service, self.service.ids[0])['results'][0]['query_excluded'])
        self.assertEqual(search_workspace(self.service, 'frequencyCutoff = 100')['results'][0]['count'], 0)

    def test_malformed_limits_fields_and_json_are_rejected(self):
        for query, kwargs in [('a'*513,{}), ('x',{'limit':0}), ('x',{'limit':True}),
                              ('notAField = 3',{}), ('history1 = [3,',{})]:
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    search_workspace(self.service, query, **kwargs)
        self.assertEqual(search_workspace(self.service, '', limit=1)['results'], [])

    def test_numeric_eight_character_query_is_not_forced_into_uuid_lookup(self):
        self.service.details[self.service.ids[0]]['parameters']['large'] = 10000000
        result = search_workspace(self.service, '10000000')['results']
        self.assertTrue(any(item.get('predicate', {}).get('value') == 10000000 for item in result))

    def test_ambiguous_uuid_prefix_never_selects_an_arbitrary_identity(self):
        rows = list(self.service.rows.values())
        ids = ['abcdef12-0000-4000-8000-000000000001', 'abcdef12-0000-4000-8000-000000000002']
        self.service.rows = {identity: {**row, 'epoch_uuid': identity} for identity, row in zip(ids, rows)}
        result = search_workspace(self.service, 'abcdef12', limit=1)
        self.assertTrue(result['identity_ambiguous'])
        self.assertEqual(result['total'], 2)
        self.assertEqual(len(result['results']), 1)

    def test_route_json_value_and_option_validation(self):
        from flask import Flask, jsonify
        app = Flask(__name__)
        app.register_error_handler(ValueError, lambda error: (jsonify(error=str(error)), 400))
        register_search_routes(app, self.service, threading.RLock())
        client = app.test_client()
        response = client.get('/api/search', query_string={'field': 'parameters/history1', 'value': '[30,10]'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['results'][0]['count'], 1)
        for path in ['/api/search?q=x&q=y', '/api/search?unknown=x', '/api/search?field=parameters/history1']:
            self.assertEqual(client.get(path).status_code, 400)


if __name__ == '__main__':
    unittest.main()
