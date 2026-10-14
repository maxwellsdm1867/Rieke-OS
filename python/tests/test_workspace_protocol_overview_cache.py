"""Protocol overview reuse and isolation, using disposable transaction doubles."""
import copy
import unittest
import uuid
from unittest.mock import patch
import test_workspace_protocol_state as state_tests


class ProtocolOverviewCacheTests(unittest.TestCase):
    def setUp(self):
        self.case=state_tests.ProtocolStateTests();self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.native_generation()
        self.client=self.case.client;self.service=self.case.service
        self.path=self.case.case.base+'/overview'

    def test_project_and_protocol_rigs_use_metadata_and_invalidate_conditional_reuse(self):
        source = self.service.sources[0]
        source['filename'] = '20261013FK.h5'
        source['metadata'] = {'rig': 'EF', 'rig_type': 'PATCH'}
        first = self.client.get(self.path)
        self.assertEqual(first.status_code, 200, first.get_json())
        with patch.object(self.service, 'events', return_value=[]):
            self.assertEqual(self.client.get('/api/overview').get_json()['cells'][0]['recording_rigs'], ['EF'])
        for path in (self.case.case.base, self.path):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.get_json())
            for cell in response.get_json()['cells']:
                self.assertEqual(cell['recording_rigs'], ['EF'])
                self.assertFalse(cell['recording_rig_missing'])
        self.assertEqual(self.client.get(self.path, headers={'If-None-Match': first.headers['ETag']}).status_code, 304)
        source['metadata']['rig'] = 'HT'
        changed = self.client.get(self.path, headers={'If-None-Match': first.headers['ETag']})
        self.assertEqual(changed.status_code, 200, changed.get_json())
        self.assertEqual(changed.get_json()['cells'][0]['recording_rigs'], ['HT'])
        self.assertNotEqual(changed.headers['ETag'], first.headers['ETag'])
        self.service.sources = [{**source, 'metadata': {'properties': {'rig': 'Rig C'}}}]
        replacement = self.client.get(self.path)
        self.assertEqual(replacement.get_json()['cells'][0]['recording_rigs'], ['Rig C'])

    def test_summary_matches_full_summary_except_explicitly_omitted_cross_protocol_links(self):
        expected=self.client.get(self.case.case.base).get_json()
        for cell in expected['cells']:cell.pop('protocol_uuids',None)
        actual=self.client.get(self.path)
        self.assertEqual(actual.status_code,200,actual.get_json())
        self.assertEqual(actual.get_json(),expected)
        self.assertTrue(actual.headers['ETag'])

    def test_unchanged_conditional_summary_does_not_read_or_serialize_decisions_again(self):
        first=self.client.get(self.path)
        self.case.case.curation.read_log.clear()
        second=self.client.get(self.path,headers={'If-None-Match':first.headers['ETag']})
        self.assertEqual(second.status_code,304,second.get_data(as_text=True))
        self.assertEqual(second.data,b'')
        self.assertFalse(self.case.case.curation.read_log)
        self.assertEqual(second.headers['ETag'],first.headers['ETag'])

    def test_curation_and_shared_tag_changes_invalidate_cached_summary(self):
        first=self.client.get(self.path)
        self.case.save_curation(ids=self.case.ids[:1],included=False)
        second=self.client.get(self.path,headers={'If-None-Match':first.headers['ETag']})
        self.assertEqual(second.status_code,200,second.get_json())
        self.assertEqual(second.get_json()['counts']['excluded'],1)
        self.case.fixture.edit('cell',self.service.rows[self.case.ids[0]]['cell_uuid'],['new'])
        third=self.client.get(self.path,headers={'If-None-Match':second.headers['ETag']})
        self.assertEqual(third.status_code,200,third.get_json())
        self.assertNotEqual(third.headers['ETag'],second.headers['ETag'])

    def test_unrelated_metadata_changes_do_not_invalidate_the_protocol_summary(self):
        first=self.client.get(self.path)
        other=str(uuid.uuid4())
        self.service._fingerprints[other]='f'*64
        self.service.cells[other]={'label':'Unrelated','cell_uuid':other}
        second=self.client.get(self.path,headers={'If-None-Match':first.headers['ETag']})
        self.assertEqual(second.status_code,304,second.get_data(as_text=True))
        self.service._fingerprints[self.case.ids[0]]='e'*64
        third=self.client.get(self.path,headers={'If-None-Match':first.headers['ETag']})
        self.assertEqual(third.status_code,200,third.get_json())
        self.assertNotEqual(third.headers['ETag'],first.headers['ETag'])

    def test_scoped_row_metadata_and_export_history_invalidate_the_summary(self):
        first=self.client.get(self.path)
        self.service.rows[self.case.ids[0]]['duration_seconds']=12
        second=self.client.get(self.path,headers={'If-None-Match':first.headers['ETag']})
        self.assertEqual(second.status_code,200,second.get_json())
        self.assertEqual(second.get_json()['counts']['duration_seconds'],13)
        with patch.object(self.service,'refresh',return_value={'epochs':2}):
            saved=self.client.post(self.case.case.base+'/exports',headers=self.case.case.headers,json={
                'query_revision':second.get_json()['query_revision'],'review_policy':'include_unreviewed',
                'filters':{},'name':'Owned fixture export','split_order':'date, cell'})
        self.assertEqual(saved.status_code,201,saved.get_json())
        third=self.client.get(self.path,headers={'If-None-Match':second.headers['ETag']})
        self.assertEqual(third.status_code,200,third.get_json())
        self.assertEqual(third.get_json()['counts']['exported'],2)

    def test_filters_cannot_reuse_a_different_scope_or_bypass_validation(self):
        first=self.client.get(self.path)
        cell=self.service.rows[self.case.ids[0]]['cell_uuid']
        filtered=self.client.get(self.path+'?cell_uuid='+cell,headers={'If-None-Match':first.headers['ETag']})
        self.assertEqual(filtered.status_code,200,filtered.get_json())
        self.assertEqual(filtered.get_json()['counts']['epochs'],1)
        self.assertEqual(self.client.get(self.path+'?unknown=1',headers={'If-None-Match':first.headers['ETag']}).status_code,400)

    def test_export_header_reads_are_restricted_to_the_active_protocol(self):
        other=str(uuid.uuid4())
        self.case.case.datasets.rows.append({'project_uuid':self.service.project['project_uuid'],
            'protocol_uuid':other,'dataset_uuid':str(uuid.uuid4()),'artifact_sha256':'c'*64,
            'created_at':'2026-10-11','recipe':{'unrelated':'must not decode'}})
        self.case.case.datasets.read_log.clear()
        response=self.client.get(self.path)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.get_json()['counts']['exported'],0)
        self.assertTrue(self.case.case.datasets.read_log)
        for read in self.case.case.datasets.read_log:
            self.assertIn({'protocol_uuid':self.case.protocol},read['restrictions'])

    def test_cold_and_warm_protocol_reads_never_enumerate_global_rows_fingerprints_or_cells(self):
        class LookupOnly(dict):
            def __iter__(self):raise AssertionError('Global enumeration')
            def keys(self):raise AssertionError('Global keys')
            def values(self):raise AssertionError('Global values')
            def items(self):raise AssertionError('Global items')
        for name in ('rows','_fingerprints','cells'):
            setattr(self.service,name,LookupOnly(getattr(self.service,name)))
        other=str(uuid.uuid4())
        class Unreadable:
            def __deepcopy__(self,memo):raise AssertionError('Other protocol membership read')
        self.service.protocols[other]={'definition':{},'result':Unreadable()}
        first=self.client.get(self.path)
        self.assertEqual(first.status_code,200,first.get_json())
        second=self.client.get(self.path,headers={'If-None-Match':first.headers['ETag']})
        self.assertEqual(second.status_code,304,second.get_data(as_text=True))
        self.assertEqual(self.client.get(self.case.case.base+'/epochs?limit=1').status_code,200)

    def test_custom_reader_cannot_reuse_native_summary_etag(self):
        first=self.client.get(self.path)
        with patch.object(self.case.store,'export_memberships',wraps=self.case.store.export_memberships):
            response=self.client.get(self.path,headers={'If-None-Match':first.headers['ETag']})
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertNotIn('ETag',response.headers)

    def test_linked_file_sizes_do_not_read_the_project_epoch_inventory(self):
        from test_workspace_datastores import DataStoreTests
        fixture=DataStoreTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        expected=fixture.client.get('/api/data-stores').get_json()['data_stores']
        owner=fixture.case.app.extensions['data_stores']
        with patch.object(owner,'inventory',side_effect=AssertionError('No full inventory')):
            response=fixture.client.get(fixture.case.base+'/recording-sizes')
        self.assertEqual(response.status_code,200,response.get_json())
        projected=[{key:row[key] for key in ('source_sha256','file_status','size_bytes')} for row in expected]
        self.assertEqual(response.get_json()['data_stores'],projected)


if __name__=='__main__':unittest.main()
