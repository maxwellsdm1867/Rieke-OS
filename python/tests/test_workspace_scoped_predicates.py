"""Frozen protocol intersection using isolated rows and disposable curation files."""
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import test_workspace_api as fixture
from workspace_tree_pages import TreePages

class ScopedPredicates(unittest.TestCase):
    def setUp(self):
        self.f=fixture.WorkspaceAPITests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s,self.c=self.f.service,self.f.client
        self.p=self.s.protocol_id
        self.root='/api/protocols/'+self.p
        self.jobs=self.f.app.extensions['metadata_summary_jobs'];self.jobs.autostart=False
    def filters(self,predicate):return {'metadata_predicate':json.dumps(predicate)}
    def test_rows_tree_cells_count_and_frozen_cohort_intersect(self):
        ast={'field':'parameters/example','operator':'eq','value':0}
        filters=self.filters(ast)
        page=self.c.get(self.root+'/epochs',query_string={**filters,'include_cells':'true'}).get_json()
        self.assertEqual(page['total'],1);self.assertEqual([r['epoch_uuid'] for r in page['epochs']],[self.s.ids[0]])
        self.assertEqual(len(page['cells']),1)
        summary=self.c.get(self.root,query_string=filters).get_json()
        self.assertEqual(summary['counts']['epochs'],1)
        tree=self.c.post('/api/tree-pages',json={'protocol_uuid':self.p,'filters':filters,'splits':'date,cell,block'},headers=self.f.headers)
        self.assertEqual(tree.status_code,200,tree.get_json());self.assertEqual(tree.get_json()['total_epochs'],1)
        self.assertEqual(self.s.query_result(self.p)['epochs'],self.s.protocols[self.p]['result']['epochs'])
        # Source eligibility must not remove retained protocol membership.
        self.s.set_source_state_provider(lambda:{'a'*64:{'query_excluded':True}})
        self.assertEqual(self.s.epoch_page(self.p,filters)['total'],1)
        self.assertEqual(self.s._tree_rows(None,filters),[])
    def test_invalid_predicates_reject_even_empty_cohort_and_duplicate_query(self):
        self.s.protocols[self.p]['result']['epochs']=[]
        bad=[{'field':'unknown','operator':'exists'},{'field':'parameters/example','operator':'gt','value':'0'}, {'all':'no'}, {'field':'parameters/example','operator':'eq','value':2**53}]
        node={'all':[]}
        for _ in range(10):node={'not':node}
        bad.append(node)
        for ast in bad:
            with self.subTest(ast=ast):
                response=self.c.get(self.root+'/epochs',query_string=self.filters(ast))
                self.assertEqual(response.status_code,400,response.get_json())
        for text in ['', '{', '"'+('雪'*24000)+'"']:
            self.assertEqual(self.c.get(self.root+'/epochs',query_string={'metadata_predicate':text}).status_code,400)
        self.assertEqual(self.c.get(self.root+'/epochs',query_string=[('metadata_predicate','{"all":[]}'),('metadata_predicate','{"any":[]}')]).status_code,400)
    def test_boolean_null_missing_array_and_anchor(self):
        for ast,count in [({'all':[]},2),({'any':[]},0),({'not':{'any':[]}},2),({'field':'parameters/example','operator':'missing'},0),({'field':'parameters/example','operator':'is_null'},0),({'field':'parameters/example','operator':'in','value':[1]},1)]:
            self.assertEqual(self.s.epoch_page(self.p,self.filters(ast))['total'],count)
        filters=self.filters({'field':'parameters/example','operator':'eq','value':0})
        with self.assertRaises(ValueError):self.s.epoch_page(self.p,filters,anchor_uuid=self.s.ids[1])
    def test_shared_fast_filter_does_not_skip_metadata_intersection(self):
        rows=list(self.s.rows.values())
        shared=SimpleNamespace(filter_epoch_ids=lambda rows,filters:(self.s.ids,None),for_epochs=lambda rows:{row['epoch_uuid']:{'effective_tags':[{'tag':'QC'}]} for row in rows})
        self.s.shared_annotations=shared
        with patch.object(shared,'filter_epoch_ids',create=True,return_value=(self.s.ids,None)):
            result=self.s._filter_rows(rows,{'tagged':'true',**self.filters({'any':[]})},self.p)
        self.assertEqual(result,[])
    def test_foreign_curation_rejected_and_own_scope_supported(self):
        foreign={'field':'curation/00000000-0000-4000-8000-000000000000/tags','operator':'contains','value':'QC'}
        response=self.c.get(self.root+'/epochs',query_string=self.filters(foreign))
        self.assertEqual(response.status_code,400);self.assertIn('foreign',response.get_json()['error'])
        own={'field':f'curation/{self.p}/tags','operator':'eq','value':[]}
        self.assertEqual(self.s.epoch_page(self.p,self.filters(own))['total'],2)
    def test_count_only_summary_fences_filter_annotation_context(self):
        filters=self.filters({'field':'parameters/example','operator':'eq','value':1})
        response=self.c.post('/api/explore/summaries',json={'predicate':{'all':[]},'summary_fields':[],'protocol_uuid':self.p,'filters':filters},headers=self.f.headers)
        self.assertEqual(response.status_code,202,response.get_json());ack=response.get_json();self.jobs.drive_worker()
        result=self.jobs.poll(ack['request_id'])
        self.assertEqual(result['generation'],ack['generation']);self.assertEqual(result['result'],{'matched_count':1,'summaries':{}})
    def test_tree_equal_membership_annotation_witness_changes(self):
        self.s.shared_annotations=SimpleNamespace(snapshot=lambda:{'revision':'a','records':[]},for_epochs=lambda rows:{})
        filters=self.filters({'not':{'field':'annotations/effective/tags','operator':'contains','value':'absent'}})
        body={'protocol_uuid':self.p,'filters':filters,'splits':'date,cell,block'}
        with patch('workspace_explore_queries.generation',return_value={'annotation':'a'}):a=TreePages(self.s).page(body)
        with patch('workspace_explore_queries.generation',return_value={'annotation':'b'}):b=TreePages(self.s).page(body)
        self.assertEqual(a['total_epochs'],b['total_epochs']);self.assertNotEqual(a['revision'],b['revision'])
    def test_selected_curation_scope_enforces_metadata(self):
        summary=self.c.get(self.root).get_json()
        response=self.c.post(self.root+'/curation/read',json={'epoch_uuids':[self.s.ids[1]],'query_revision':summary['query_revision'],'expected_binding_version':summary['expected_binding_version'],'selection_scope':{'filters':self.filters({'field':'parameters/example','operator':'eq','value':0}),'cell_uuid':None}},headers=self.f.headers)
        self.assertEqual(response.status_code,400,response.get_json())

    def test_validation_of_tag_grammar_never_reads_annotation_records(self):
        own={'field':f'curation/{self.p}/tags','operator':'contains','value':'QC'}
        with patch.object(self.s,'annotation_provider',side_effect=AssertionError('validation read live curation')):
            self.s.validate_metadata_filters(self.filters(own),self.p)
    def test_internal_conjunction_budget_preserves_admitted_ast(self):
        import workspace_explore_queries as queries
        leaf={'field':'parameters/example','operator':'eq','value':0}
        deep=leaf
        for _ in range(8):deep={'not':deep}
        for ast in [deep, {'all':[leaf for _ in range(127)]}]:
            with self.subTest(ast=ast):
                filters=self.filters(ast)
                self.s.validate_metadata_filters(filters,self.p)
                context={'predicate':{'all':[]},'protocol_uuid':self.p,'filters':filters,'scope':{}}
                self.assertTrue(queries.typed_combination_over_budget(context))
                with patch('workspace_explore_queries.typed_policy',return_value=True):
                    job=self.jobs.submit({**context,'summary_fields':[]})
                    self.jobs.drive_worker()
                result=self.jobs.poll(job['request_id'])
                self.assertEqual(result['status'],'ready',result)
                self.assertEqual(result['result']['matched_count'],1)
    def test_full_tree_has_surrounding_annotation_fence(self):
        filters=self.filters({'all':[]})
        with patch('workspace_explore_queries.generation',side_effect=[{'a':1},{'a':2}]):
            with self.assertRaisesRegex(ValueError,'annotations changed'):
                self.s.tree(self.p,filters)
