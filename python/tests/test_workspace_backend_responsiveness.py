"""Bounded read work with immutable-index and durable-mutation safeguards."""
import copy
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from workspace_api import create_app
from workspace_disk_index import DiskMetadataIndex
from workspace_service import _SourceDetails
from workspace_tree import joint_id
from workspace_tree_pages import TreePages, StaleTreePage, _retained_scope_bytes, TREE_SCOPE_CACHE_OVERHEAD
import test_workspace_api as api_fixture


class BackendResponsivenessTests(unittest.TestCase):
    def setUp(self):
        self.fixture = api_fixture.WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = self.fixture.service
        self.index = DiskMetadataIndex.build(Path(self.fixture.temp.name)/'responsive.sqlite',
            self.service.rows, self.service.details, self.service.sources, 'responsive-generation',
            self.service.project['project_uuid'])
        self.service.disk_index = self.index
        self.service.details = self.index.details

    def test_fast_preview_avoids_scoped_catalog_and_values_but_keeps_exact_membership(self):
        predicate = {'field':'parameters/example', 'operator':'eq', 'value':0}
        splits = joint_id(['cell', 'parameters/example'])
        expected = self.service.explore_preview(predicate, splits, include_tree=False)
        original_catalog = self.index.catalog
        def registered_only(*args, **kwargs):
            self.assertFalse(args or kwargs, 'Fast preview must not summarize a matched scope')
            return original_catalog()
        with patch.object(self.index, 'catalog', side_effect=registered_only), \
             patch.object(self.index, 'values', side_effect=AssertionError('No field projection')):
            fast = self.service.explore_preview(predicate, splits, include_tree=False, include_catalog_summary=False)
        for field in ('membership', 'matched_count', 'total_source', 'tree_revision', 'tree', 'source_scope'):
            self.assertEqual(fast[field], expected[field])
        self.assertFalse(fast['catalog']['summary_available'])
        self.assertNotIn('suggestions', fast['catalog'])
        for field in fast['catalog']['fields']:
            self.assertNotIn('distinct_count', field)
            self.assertNotIn('examples', field)
        response = self.fixture.client.post('/api/explore/preview', json={
            'predicate':predicate, 'splits':splits, 'summary_only':True, 'catalog_summary':False}, headers=self.fixture.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['tree_revision'], fast['tree_revision'])

    def test_fast_save_retains_complete_recipe_and_rejects_invalid_projection_options(self):
        body = {'predicate':{'all':[]}, 'splits':'cell', 'summary_only':True, 'catalog_summary':False}
        response = self.fixture.client.post('/api/explore/revisions', json=body, headers=self.fixture.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        revision = response.get_json()
        full = self.fixture.client.get('/api/explore/revisions/'+revision['revision_uuid']).get_json()
        self.assertEqual({member['uuid'] for member in full['recipe']['epochs']}, set(self.service.rows))
        for value in (None, 'false', 0):
            invalid = self.fixture.client.post('/api/explore/preview', json={**body,'catalog_summary':value}, headers=self.fixture.headers)
            self.assertEqual(invalid.status_code,400)
        rendered = self.fixture.client.post('/api/explore/preview', json={**body,'summary_only':False}, headers=self.fixture.headers)
        self.assertEqual(rendered.status_code,400)

    def test_repeated_tree_scope_reuses_projection_and_membership_revision_across_adapters(self):
        pager = TreePages(self.service)
        body = {'splits':'cell,parameters/example'}
        root = pager.page(body)
        with patch.object(self.service, '_tree_rows', side_effect=AssertionError('No membership rescan')), \
             patch.object(self.index, 'values', side_effect=AssertionError('No projection reread')), \
             patch('workspace_tree_pages.selection_revision', side_effect=AssertionError('No membership rehash')):
            self.assertEqual(TreePages(self.service).page(body), root)
        child = {**body, 'path':root['branches'][0]['path'], 'revision':root['revision']}
        expected = pager.page(child)
        with patch.object(self.index, 'values', side_effect=AssertionError('No projection reread')):
            self.assertEqual(pager.page(child), expected)
        self.service._fingerprints[self.service.ids[0]] = 'c'*64
        with self.assertRaises(StaleTreePage):
            pager.page({**body, 'revision':root['revision']})
        # Every hit still checks the sealed file signature.
        with self.index.path.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises(ValueError):
            pager.page(body)

    def test_source_eligibility_and_protocol_binding_invalidate_cached_selection(self):
        pager = TreePages(self.service)
        source_root = pager.page({'splits':''})
        self.service.set_source_state_provider(lambda: {'a'*64:{'query_excluded':True}})
        with self.assertRaises(StaleTreePage):
            pager.page({'splits':'', 'revision':source_root['revision']})
        self.assertEqual(pager.page({'splits':''})['total_epochs'],0)
        protocol = self.service.protocol_id
        root = pager.page({'protocol_uuid':protocol, 'splits':''})
        key = self.service.ids[0]
        binding = {'version':1, 'revision_uuid':'new-binding', 'recipe':{
            'epochs':[{'uuid':key, 'metadata_hash':self.service._fingerprints[key]}],
            'source_revisions':['a'*64], 'predicate':{'all':[]}, 'tree_view':{'fields':[]},
            'splits':'', 'name':'One epoch'}}
        self.service.set_binding_provider(lambda identity: binding)
        with self.assertRaises(StaleTreePage):
            pager.page({'protocol_uuid':protocol, 'splits':'', 'revision':root['revision']})
        self.assertEqual(pager.page({'protocol_uuid':protocol, 'splits':''})['total_epochs'],1)

    def test_live_tag_scope_bypasses_cache_and_changes_revision(self):
        selected = {self.service.ids[0]}
        self.service.shared_annotations = SimpleNamespace(for_epochs=lambda rows: {
            row['epoch_uuid']:{'effective_tags':[{'tag':'checked'}] if row['epoch_uuid'] in selected else []}
            for row in rows})
        pager = TreePages(self.service)
        body = {'splits':'cell', 'filters':{'tag':'checked'}}
        first = pager.page(body)
        selected.clear()
        with self.assertRaises(StaleTreePage):
            pager.page({**body, 'revision':first['revision']})
        self.assertEqual(pager.page(body)['total_epochs'],0)

    def test_scope_retention_is_bounded_and_row_generation_rebuilds(self):
        pager = TreePages(self.service)
        for value in range(12):
            pager.page({'splits':'', 'predicate':{'field':'parameters/example','operator':'eq','value':value}})
        cache = self.service._tree_page_scope_cache[1]
        self.assertLessEqual(len(cache),8)
        self.assertLessEqual(sum(entry[1] for entry in cache.values()),2_000_000)
        body = {'splits':'cell'}
        root = pager.page(body)
        self.service.rows = copy.deepcopy(self.service.rows)
        with patch.object(pager, '_build_scope', wraps=pager._build_scope) as rebuild:
            self.assertEqual(pager.page(body),root)
            rebuild.assert_called_once()

    def test_detail_dispatch_touches_exactly_the_owning_source(self):
        rows, sources = {}, {}
        for number in range(500):
            identity, source = str(number), 'source-'+str(number)
            rows[identity] = {'source_sha256':source}
            sources[source] = Mock()
            sources[source].__getitem__ = Mock(return_value={'owner':source})
        details = _SourceDetails(rows,sources)
        self.assertEqual(details['499'],{'owner':'source-499'})
        self.assertEqual(list(details),list(rows))
        self.assertEqual(sum(source.__getitem__.call_count for source in sources.values()),1)
        with self.assertRaises(KeyError):details['unknown']

    def test_large_vector_scope_serves_exact_values_without_cache_retention(self):
        vector = [float(value) / 3 for value in range(2000)]
        projected = {key:{'parameters/example':vector} for key in self.service.rows}
        pager = TreePages(self.service)
        body = {'splits':'parameters/example'}
        # Current catalog discovery excludes very large vectors. Supply a large
        # projection through the index interface to keep cache safety independent
        # of that separate discovery policy and future index formats.
        with patch('workspace_tree_pages.TREE_SCOPE_BYTE_BUDGET',32*1024), \
             patch.object(self.index,'values',return_value=projected), \
             patch.object(pager,'_build_scope',wraps=pager._build_scope) as builds:
            first, second = pager.page(body), pager.page(body)
        self.assertEqual(first,second)
        self.assertEqual(first['branches'][0]['value'],vector)
        self.assertEqual(first['total_epochs'],len(self.service.rows))
        self.assertEqual(builds.call_count,2)
        self.assertEqual(self.service._tree_page_scope_cache[1],{})

    def test_aggregate_byte_budget_evicts_individually_cacheable_scopes(self):
        pager = TreePages(self.service)
        first, second = {'splits':'cell'}, {'splits':'parameters/example'}
        sizes = [_retained_scope_bytes(pager._build_scope(body),self.service.rows,1024*1024)
                 for body in (first,second)]
        # Each scope fits, but the pair cannot remain resident together.
        budget = sys.getsizeof(self.service._fingerprints) + TREE_SCOPE_CACHE_OVERHEAD + max(sizes) + min(sizes)//2
        with patch('workspace_tree_pages.TREE_SCOPE_BYTE_BUDGET',budget), \
             patch.object(pager,'_build_scope',wraps=pager._build_scope) as builds:
            pager.page(first)
            pager.page(second)
            self.assertEqual(len(self.service._tree_page_scope_cache[1]),1)
            pager.page(second)
            self.assertEqual(builds.call_count,2)
            pager.page(first)
            self.assertEqual(builds.call_count,3)
        cache = self.service._tree_page_scope_cache[1]
        self.assertLessEqual(sum(entry[2] for entry in cache.values()),max(sizes))

    def test_byte_estimate_distinguishes_borrowed_rows_from_owned_copies_and_values(self):
        row = copy.deepcopy(self.service.rows[self.service.ids[0]])
        vector = [float(number) for number in range(2000)]
        row['large_metadata'] = vector
        base = {row['epoch_uuid']:row}
        def scope(rows, values=None):
            return (rows,{},values or {},{},[], 'revision')
        borrowed = _retained_scope_bytes(scope([row]),base,4096)
        decorated = {**row, 'curation':{'included':True,'tags':[]}}
        owned = _retained_scope_bytes(scope([decorated]),base,4096)
        self.assertLess(borrowed,owned)  # The new row and curation allocate memory.
        self.assertLess(owned,4096)  # Shared base metadata is not copied.
        copied = {**decorated,'large_metadata':list(vector)}
        self.assertGreater(_retained_scope_bytes(scope([copied]),base,4096),4096)
        projection = {row['epoch_uuid']:{'field':list(vector)}}
        self.assertGreater(_retained_scope_bytes(scope([row],projection),base,4096),4096)


class RecoveryHookTests(unittest.TestCase):
    def setUp(self):
        self.fixture = api_fixture.WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.service.dj.Schema = object()
        self.save = Mock()
        with patch('workspace_annotations.SharedAnnotations', return_value=None), \
             patch('workspace_state_snapshot.save', self.save):
            self.app = create_app(self.fixture.temp.name, self.fixture.temp.name,
                service=self.fixture.service, store=self.fixture.store,
                explorer_history=self.fixture.explorer_history, data_stores=self.fixture.data_stores,
                protocol_suggestions=self.fixture.protocol_suggestions)
        self.addCleanup(self.app.extensions['app_state_session_lock'].close)
        self.addCleanup(lambda:self.app.extensions['backup_scheduler'].close(flush=False))
        self.client = self.app.test_client()
        self.assertEqual(self.save.call_count,1)  # Startup still protects state.
        self.save.reset_mock()

    def test_native_close_refuses_shutdown_when_mandatory_backup_fails(self):
        self.fixture.service.config['connection']={'credential_provider':{'kind':'native-project'}}
        with patch('workspace_annotations.SharedAnnotations',return_value=None), \
             patch('workspace_state_snapshot.save',self.save):
            app=create_app(self.fixture.temp.name,self.fixture.temp.name,
                service=self.fixture.service,store=self.fixture.store,
                explorer_history=self.fixture.explorer_history,data_stores=self.fixture.data_stores,
                protocol_suggestions=self.fixture.protocol_suggestions)
        self.addCleanup(app.extensions['app_state_session_lock'].close)
        scheduler=app.extensions['backup_scheduler']
        self.addCleanup(lambda:scheduler.close(flush=False))
        self.save.side_effect=OSError('Disk full')
        with patch.object(app.extensions['h5_inbox'],'start') as resume, \
             patch('workspace_native_mysql.stop_native_database') as stop:
            with self.assertRaisesRegex(OSError,'Disk full'):app.extensions['desktop_stop_database']()
        stop.assert_not_called();resume.assert_called_once()
        self.assertFalse(scheduler.stopped)
        self.assertEqual(scheduler.status()['status'],'degraded')

    def test_real_read_only_posts_do_not_capture_recovery_state(self):
        body = {'predicate':{'all':[]},'splits':'cell','summary_only':True}
        preview = self.client.post('/api/explore/preview',json=body,headers=self.fixture.headers)
        self.assertEqual(preview.status_code,200,preview.get_json())
        revision = preview.get_json()['tree_revision']
        for path, content in (('/api/tree-pages',{'splits':'cell'}),
                ('/api/explore/epochs',{'predicate':{'all':[]},'splits':'cell','revision':revision})):
            response = self.client.post(path,json=content,headers=self.fixture.headers)
            self.assertEqual(response.status_code,200,response.get_json())
        self.save.assert_not_called()

    def test_route_classification_is_conservative_and_noops_remain_checkpointed(self):
        # Exercise every explicitly exempt endpoint through Flask's actual hook,
        # and ensure unknown future write routes default to protection.
        readonly = ('explorer_preview','tree_page','matching_epochs','annotation_batch_read',
            'tag_import_preview','preview_source_propagation','resolve_search_preset','compare_protocol_revision')
        for index, endpoint in enumerate(readonly):
            self.app.add_url_rule('/api/test-read/'+str(index),endpoint=endpoint,methods=['POST'])
            self.app.view_functions[endpoint] = lambda: ({'read':True},200)
        for method in ('POST','PUT','PATCH','DELETE'):
            self.app.add_url_rule('/api/test-write/'+method,endpoint='new-write-'+method,
                view_func=lambda: ({'changed':False},200),methods=[method])
        for index in range(len(readonly)):
            self.assertEqual(self.client.post('/api/test-read/'+str(index),headers=self.fixture.headers).status_code,200)
        self.save.assert_not_called()
        for method in ('POST','PUT','PATCH','DELETE'):
            self.assertEqual(self.client.open('/api/test-write/'+method,method=method,headers=self.fixture.headers).status_code,200)
        self.assertEqual(self.save.call_count,4)

    def test_search_run_still_checkpoints_its_recorded_last_run(self):
        runs = Mock()
        runs.record_run.return_value = {'epoch_count':2, 'cell_count':2}
        self.app.extensions['search_presets'] = runs
        response = self.client.post('/api/explore/run', json={
            'predicate':{'all':[]}, 'splits':'cell', 'catalog_summary':False}, headers=self.fixture.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        runs.record_run.assert_called_once()
        self.save.assert_called_once()

    def test_committed_mutation_backup_failure_remains_visible_and_retry_is_protected(self):
        body = self.fixture.curation_body({'tags_add':['retained']})
        self.save.side_effect = OSError('full disk')
        with self.assertLogs(self.app.logger,level='ERROR'):
            response = self.client.post(self.fixture.base+'/curation',json=body,headers=self.fixture.headers)
        self.assertEqual(response.status_code,507,response.get_json())
        self.assertTrue(response.get_json()['saved'])
        self.assertTrue(self.fixture.curation.rows)
        self.save.side_effect = None
        body['expected_revisions'] = {row['epoch_uuid']:row['revision'] for row in self.fixture.curation.rows}
        body['query_revision'] = self.fixture.revision()
        response = self.client.post(self.fixture.base+'/curation',json=body,headers=self.fixture.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(self.save.call_count,2)


if __name__ == '__main__':
    unittest.main()
