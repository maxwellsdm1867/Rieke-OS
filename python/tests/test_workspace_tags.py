"""Autocomplete reads only the project's persisted curation vocabulary."""
import copy
import unittest
import uuid
from unittest.mock import patch

import test_workspace_api as api_fixture


class TagSuggestionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=api_fixture.WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.client,self.store=self.fixture.client,self.fixture.store
        self.project=self.fixture.service.project['project_uuid']
        self.protocol=self.fixture.service.protocol_id
        self.first,self.second=self.fixture.service.ids

    def add(self,tags,epoch=None,protocol=None,project=None):
        self.fixture.curation.insert1({'project_uuid':project or self.project,
            'protocol_uuid':protocol or self.protocol,'epoch_uuid':epoch or str(uuid.uuid4()),
            'tags':tags,'included':False,'review_state':'unreviewed','revision':1,
            'metadata_fingerprint':'a'*64})

    def test_project_scope_distinct_epoch_counts_case_prefix_and_no_writes(self):
        self.add(['ON','ON','on','Control'],self.first)
        self.add(['ON','Other'],self.second)
        self.add(['ON'],self.first,protocol=str(uuid.uuid4()))
        self.add(['ForeignOnly','ON'],project=str(uuid.uuid4()))
        before=copy.deepcopy((self.fixture.curation.rows,self.fixture.events.rows))
        with patch.object(self.fixture.service,'_tree_rows',side_effect=AssertionError('No epoch metadata')), \
             patch.object(self.store.Event,'to_dicts',side_effect=AssertionError('No full audit history')), \
             patch('h5py.File',side_effect=AssertionError('No raw data access')):
            response=self.client.get('/api/tags?q=oN')
        self.assertEqual(response.status_code,200,response.get_json())
        payload=response.get_json()
        self.assertEqual(payload['tags'],[{'tag':'ON','count':2},{'tag':'on','count':1}])
        self.assertEqual(payload['scope'],'project_saved_curation')
        self.assertEqual(payload['count_unit'],'distinct_epochs')
        self.assertEqual(payload['match'],'case_insensitive_prefix')
        self.assertFalse(payload['history_included'])
        self.assertEqual(payload['project_uuid'],self.project)
        self.assertEqual((self.fixture.curation.rows,self.fixture.events.rows),before)
        read=self.fixture.curation.read_log[-1]
        self.assertEqual(read['restrictions'],({'project_uuid':self.project},))
        self.assertEqual(read['projected'],{'project_uuid','protocol_uuid','epoch_uuid','tags'})
        all_tags={row['tag'] for row in self.client.get('/api/tags').get_json()['tags']}
        self.assertNotIn('ForeignOnly',all_tags)

    def test_response_limit_ranking_and_unicode_prefix(self):
        self.add([f'tag-{index:03d}' for index in range(130)]+['Straße'])
        self.add(['tag-110'])
        payload=self.client.get('/api/tags?q=tag-&limit=100').get_json()
        self.assertEqual(len(payload['tags']),100)
        self.assertEqual(payload['total'],130)
        self.assertTrue(payload['has_more'])
        self.assertEqual(payload['tags'][0],{'tag':'tag-110','count':2})
        self.assertEqual(payload['tags'][1],{'tag':'tag-000','count':1})
        unicode=self.client.get('/api/tags',query_string={'q':' STRASS '}).get_json()
        self.assertEqual(unicode['tags'],[{'tag':'Straße','count':1}])
        self.assertEqual(unicode['q'],'STRASS')
        self.assertEqual(self.client.get('/api/tags',query_string={'q':"' OR 1=1"}).get_json()['tags'],[])

    def test_malformed_request_limits_are_rejected_before_curation_read(self):
        for query in ('limit=0','limit=101','limit=-1','limit=1.5','limit=true','limit=',
                      'limit=1000','limit=1&limit=2','q=a&q=b','protocol_uuid=abc','limit=%D9%A1'):
            with self.subTest(query=query):
                before=len(self.fixture.curation.read_log)
                response=self.client.get('/api/tags?'+query)
                self.assertEqual(response.status_code,400,response.get_json())
                self.assertEqual(len(self.fixture.curation.read_log),before)
        self.assertEqual(self.client.get('/api/tags',query_string={'q':'x'*256}).status_code,400)
        for kwargs in ({'query':None},{'query':[]},{'limit':True},{'limit':'3'},{'limit':1.2}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.store.tag_suggestions(**kwargs)

    def test_saved_add_remove_updates_vocabulary_without_audit_history_scan(self):
        self.store.update(self.protocol,[self.first],{'tags_add':['checked']},
            {self.first:0},{self.first:'b'*64},'fixture')
        self.assertEqual(self.client.get('/api/tags').get_json()['tags'],[{'tag':'checked','count':1}])
        self.store.update(self.protocol,[self.first],{'tags_remove':['checked']},
            {self.first:1},{self.first:'b'*64},'fixture')
        self.assertEqual(len(self.fixture.events.rows),2)
        response=self.client.get('/api/tags').get_json()
        self.assertEqual(response['tags'],[])
        self.assertFalse(response['history_included'])
        self.assertEqual(len(self.fixture.events.rows),2)

    def test_prefixes_share_cached_vocabulary_and_external_edits_expire_after_two_seconds(self):
        self.add(['Alpha','Beta'],self.first)
        with patch('workspace_curation.time.monotonic',return_value=10.) as clock:
            self.assertEqual(self.store.tag_suggestions('a')['tags'],[{'tag':'Alpha','count':1}])
            first_reads=len(self.fixture.curation.read_log)
            self.assertEqual(self.store.tag_suggestions('B')['tags'],[{'tag':'Beta','count':1}])
            self.assertEqual(len(self.fixture.curation.read_log),first_reads)
            self.add(['External'],self.second)
            clock.return_value=11.99
            self.assertEqual(self.store.tag_suggestions('ex')['tags'],[])
            self.assertEqual(len(self.fixture.curation.read_log),first_reads)
            clock.return_value=12.
            self.assertEqual(self.store.tag_suggestions('ex')['tags'],[{'tag':'External','count':1}])
            self.assertEqual(len(self.fixture.curation.read_log),first_reads+1)
            # Caller edits cannot corrupt later autocomplete suggestions.
            payload=self.store.tag_suggestions('a')
            payload['tags'][0]['tag']='poisoned'
            self.assertEqual(self.store.tag_suggestions('a')['tags'],[{'tag':'Alpha','count':1}])

    def test_successful_local_tag_edits_invalidate_cache_immediately_but_rollback_does_not(self):
        with patch('workspace_curation.time.monotonic',return_value=20.):
            self.assertEqual(self.store.tag_suggestions()['tags'],[])
            self.store.update(self.protocol,[self.first],{'tags_add':['new']},
                {self.first:0},{self.first:'b'*64},'fixture')
            self.assertIsNone(self.store._tag_vocabulary)
            self.assertEqual(self.store.tag_suggestions()['tags'],[{'tag':'new','count':1}])
            cached=self.store._tag_vocabulary
            with patch.object(self.store,'_event',side_effect=RuntimeError('transaction rolls back')):
                with self.assertRaises(RuntimeError):
                    self.store.update(self.protocol,[self.first],{'tags_add':['unsaved']},
                        {self.first:1},{self.first:'b'*64},'fixture')
            self.assertIs(self.store._tag_vocabulary,cached)
            self.assertEqual(self.store.tag_suggestions()['tags'],[{'tag':'new','count':1}])
            self.store.update(self.protocol,[self.first],{'tags_remove':['new']},
                {self.first:1},{self.first:'b'*64},'fixture')
            self.assertIsNone(self.store._tag_vocabulary)
            self.assertEqual(self.store.tag_suggestions()['tags'],[])

    def test_corrupt_saved_tags_fail_explicitly_instead_of_misleading_empty_result(self):
        self.add({'bad':'record'})
        response=self.client.get('/api/tags')
        self.assertEqual(response.status_code,400)
        self.assertIn('invalid tag record',response.get_json()['error'])

if __name__=='__main__':unittest.main()
