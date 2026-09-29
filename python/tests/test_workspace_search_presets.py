"""Query-only presets via HTTP: durability, version guards, and transactional audit."""
import copy
import unittest
from unittest.mock import patch
import test_workspace_api as fixtures
from test_workspace_curation import Table
from workspace_search_presets import SearchPresets


class PresetTable(Table):
    def __and__(self, restriction):
        return PresetTable(self.keys, self.rows, self.restrictions + (restriction,), self.projected, self.read_log)

    def __len__(self):
        return len(self.to_dicts())

    def fetch(self, **options):
        self.read_log.append({'fetch_options': options})
        return super().fetch(**options)


class SearchPresetTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.table = PresetTable(('project_uuid', 'preset_uuid'))
        self.versions = Table(('project_uuid', 'preset_uuid', 'version'))
        self.runs = Table(('project_uuid', 'query_sha256'))
        self.fixture.connection.tables.extend([self.table, self.versions, self.runs])
        self.fixture.app.extensions['search_presets'] = SearchPresets(self.fixture.store, (self.table, self.versions), runs=self.runs)
        self.client, self.headers = self.fixture.client, self.fixture.headers
        self.body = dict(name='Example setting', description='Reusable numeric condition',
                         predicate={'field':'parameters/example','operator':'eq','value':1},
                         splits='date,cell', pinned=True)

    def create(self, **changes):
        return self.client.post('/api/search-presets', json={**self.body, **changes}, headers=self.headers)

    def test_save_restore_update_and_immutable_versions(self):
        before = copy.deepcopy(self.fixture.curation.rows)
        response = self.create()
        self.assertEqual(response.status_code, 201, response.get_json())
        saved = response.get_json()
        self.assertEqual(saved['version'], 1)
        self.assertNotIn('epochs', saved)
        self.fixture.app.extensions['search_presets'] = SearchPresets(self.fixture.store, (self.table, self.versions), runs=self.runs)
        self.assertEqual(self.client.get('/api/search-presets').get_json()['presets'][0]['name'], self.body['name'])
        url = '/api/search-presets/' + saved['preset_uuid']
        response = self.client.put(url, json={**self.body, 'name':'Renamed', 'expected_version':1}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['version'], 2)
        original = self.client.get(url+'/versions/1').get_json()
        self.assertEqual(original['name'], self.body['name'])
        self.assertEqual(self.client.get(url+'/versions/2').get_json()['preset_version'], 2)
        self.assertEqual(original['membership_mode'], 'live-query')
        self.assertEqual(self.fixture.curation.rows, before)
        self.assertEqual(self.fixture.events.rows, [])

    def test_stale_update_rejected_and_project_isolated(self):
        saved = self.create().get_json()
        url = '/api/search-presets/' + saved['preset_uuid']
        self.assertEqual(self.client.put(url, json={**self.body,'expected_version':2}, headers=self.headers).status_code,409)
        other=copy.copy(self.fixture.store)
        other.project_uuid='00000000-0000-0000-0000-000000000001'
        self.assertEqual(SearchPresets(other,(self.table,self.versions),runs=self.runs).list()['presets'],[])
        with self.assertRaises(KeyError):
            SearchPresets(other,(self.table,self.versions),runs=self.runs).read(saved['preset_uuid'])
        self.assertEqual(len(self.versions.rows),1)

    def test_invalid_field_split_shape_and_write_guard(self):
        self.assertEqual(self.create(predicate={'field':'unknown','operator':'eq','value':1}).status_code,400)
        self.assertEqual(self.create(splits='unknown').status_code,400)
        self.assertEqual(self.create(pinned='yes').status_code,400)
        self.assertEqual(self.create(name=' ').status_code,400)
        self.assertEqual(self.create(epochs=['not-a-query']).status_code,400)
        self.assertEqual(self.client.post('/api/search-presets',json=self.body).status_code,403)
        self.assertEqual(self.client.get('/api/search-presets?limit=1000').status_code,400)
        self.assertEqual(self.table.rows,[])

    def test_audit_failure_rolls_back_query_and_snapshot(self):
        with patch.object(self.fixture.store,'_event',side_effect=RuntimeError('Audit unavailable')):
            self.assertEqual(self.create().status_code,500)
        self.assertEqual(self.table.rows,[])
        self.assertEqual(self.versions.rows,[])

    def test_oversized_or_deep_requests_are_rejected_without_writes(self):
        for raw in ['{"predicate":'+('['*1200)+'0'+(']'*1200)+'}', '{"name":"'+('x'*70000)+'"}']:
            response=self.client.post('/api/search-presets',data=raw,content_type='application/json',headers=self.headers)
            self.assertEqual(response.status_code,400,response.get_json())
        self.assertEqual(self.table.rows,[])

    def test_list_uses_bounded_database_fetch(self):
        self.create()
        self.create(name='Second',predicate={'field':'parameters/example','operator':'eq','value':0})
        response=self.client.get('/api/search-presets?limit=1&offset=0').get_json()
        self.assertEqual(len(response['presets']),1)
        self.assertTrue(response['has_more'])
        fetches=[item['fetch_options'] for item in self.table.read_log if 'fetch_options' in item]
        self.assertEqual(fetches[-1]['limit'],1)
        self.assertEqual(fetches[-1]['offset'],0)

    def test_download_is_exact_version_and_query_only(self):
        saved=self.create().get_json()
        url='/api/search-presets/'+saved['preset_uuid']
        self.client.put(url,json={**self.body,'name':'Changed','expected_version':1},headers=self.headers)
        response=self.client.get(url+'/download?version=1')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()['name'],self.body['name'])
        self.assertEqual(response.get_json()['version'],1)
        self.assertIn('attachment;',response.headers['Content-Disposition'])
        self.assertNotIn('epochs',response.get_json())
        self.assertEqual(self.client.get(url+'/download?version=999').status_code,400)

    def test_run_counts_unique_cells_survive_reload_and_pinning_does_not_change_time(self):
        saved=self.create().get_json()
        self.assertIsNone(saved['last_run'])
        response=self.client.post('/api/explore/run',json={'predicate':{'all':[self.body['predicate']]},'splits':'date,cell'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        stats=response.get_json()['last_run']
        self.assertEqual(stats['epoch_count'],1)
        self.assertEqual(stats['cell_count'],1)
        self.assertEqual(self.client.get('/api/search-presets').get_json()['presets'][0]['last_run'],stats)
        self.client.put('/api/search-presets/'+saved['preset_uuid'],json={**self.body,'pinned':False,'expected_version':1},headers=self.headers)
        self.assertEqual(self.client.get('/api/search-presets').get_json()['presets'][0]['last_run'],stats)
        self.assertEqual(len(self.runs.rows),1)

    def test_empty_and_failed_runs_do_not_fabricate_cells_or_overwrite_history(self):
        payload={'predicate':{'field':'protocol','operator':'eq','value':'no-match'},'splits':'date,cell'}
        response=self.client.post('/api/explore/run',json=payload,headers=self.headers)
        self.assertEqual(response.get_json()['last_run']['cell_count'],0)
        previous=copy.deepcopy(self.runs.rows)
        with patch.object(self.fixture.store,'_event',side_effect=RuntimeError('Audit unavailable')):
            self.assertEqual(self.client.post('/api/explore/run',json=payload,headers=self.headers).status_code,500)
        self.assertEqual(self.runs.rows,previous)

    def test_multiple_epochs_of_one_cell_count_as_one_cell(self):
        service=self.fixture.service
        service.rows[service.ids[1]]['cell_uuid']=service.rows[service.ids[0]]['cell_uuid']
        response=self.client.post('/api/explore/run',json={'predicate':{'all':[]},'splits':'date,cell'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.get_json()['last_run']['epoch_count'],2)
        self.assertEqual(response.get_json()['last_run']['cell_count'],1)

    def test_duplicate_predicates_reuse_identity_and_noop_does_not_version(self):
        saved=self.create().get_json()
        response=self.create(name='Another name',predicate={'all':[self.body['predicate'],self.body['predicate']]})
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertTrue(response.get_json()['reused'])
        self.assertEqual(response.get_json()['preset_uuid'],saved['preset_uuid'])
        self.assertEqual(response.get_json()['name'],saved['name'])
        url='/api/search-presets/'+saved['preset_uuid']
        self.assertTrue(self.client.put(url,json={**self.body,'expected_version':1},headers=self.headers).get_json()['reused'])
        self.assertEqual(len(self.versions.rows),1)
        resolved=self.client.post('/api/search-presets/resolve',json={'predicate':self.body['predicate']},headers=self.headers).get_json()
        self.assertEqual(resolved['preset']['preset_uuid'],saved['preset_uuid'])

    def test_commutative_normalization_preserves_types_and_array_order(self):
        from workspace_search_presets import query_key
        a={'field':'parameters/example','operator':'eq','value':1}
        b={'field':'protocol','operator':'contains','value':'example'}
        self.assertEqual(query_key({'all':[a,b]}),query_key({'all':[b,{'all':[a,a]}]}))
        self.assertEqual(query_key(a),query_key({**a,'value':1.0}))
        self.assertNotEqual(query_key(a),query_key({**a,'value':True}))
        self.assertNotEqual(query_key({**a,'value':[1,2]}),query_key({**a,'value':[2,1]}))
        self.assertNotEqual(query_key({'all':[a,b]}),query_key({'any':[a,b]}))

    def test_changed_query_cannot_overwrite_a_different_saved_identity(self):
        first=self.create().get_json()
        other_body={**self.body,'predicate':{'field':'parameters/example','operator':'eq','value':0}}
        second=self.create(**other_body).get_json()
        response=self.client.put('/api/search-presets/'+second['preset_uuid'],json={**self.body,'expected_version':1},headers=self.headers)
        self.assertEqual(response.status_code,409)
        history=self.client.get('/api/search-presets/'+first['preset_uuid']+'/versions').get_json()
        self.assertEqual(len(history['versions']),1)
        self.assertEqual(history['versions'][0]['predicate'],self.body['predicate'])
