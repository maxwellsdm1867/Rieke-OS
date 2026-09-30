"""Rieke OS accepts generic JSON curation, never plotting-GUI mask traffic."""
import copy
import io
import unittest
import test_workspace_api as fixtures

class MatlabInteractionRemovalTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.WorkspaceAPITests('runTest');self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_retired_ugm_import_is_not_an_active_route_and_cannot_change_decisions(self):
        before=copy.deepcopy(self.case.curation.rows)
        response=self.case.client.post(self.case.base+'/masks/import-matlab',headers=self.case.headers,
            data={'file':(io.BytesIO(b'opaque legacy UGM bytes'),'selection.ugm'),'query_revision':self.case.revision()})
        self.assertIn(response.status_code,(404,405))
        self.assertEqual(self.case.curation.rows,before)

    def test_retired_metadata_mask_application_cannot_change_decisions(self):
        before=copy.deepcopy(self.case.curation.rows)
        response=self.case.client.post('/api/metadata/masks/apply',headers=self.case.headers,json={})
        self.assertIn(response.status_code,(404,405))
        self.assertEqual(self.case.curation.rows,before)

    def test_generic_uuid_json_mask_export_remains_available(self):
        response=self.case.client.get(self.case.base+'/masks/export')
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertIn('attachment;',response.headers.get('Content-Disposition',''))
        self.assertIn('.json',response.headers['Content-Disposition'])
        self.assertEqual(response.get_json()['format'],'recording-selection-mask')
        self.assertEqual({epoch['epoch_uuid'] for epoch in response.get_json()['epochs']},set(self.case.service.ids))
        mask=response.get_json();mask['epochs'][0]['included']=False
        saved=self.case.client.post(self.case.base+'/masks/import',headers=self.case.headers,
            json={'mask':mask,'query_revision':self.case.revision()})
        self.assertEqual(saved.status_code,200,saved.get_json())
        current=self.case.client.get(self.case.base+'/masks/export').get_json()
        self.assertFalse(next(epoch['included'] for epoch in current['epochs'] if epoch['epoch_uuid']==mask['epochs'][0]['epoch_uuid']))

    def test_native_tree_and_paged_tree_preserve_membership_without_matlab_commands(self):
        tree=self.case.client.get(self.case.base+'/tree').get_json()
        self.assertNotIn('matlab_command',tree)
        self.assertEqual(tree['count'],len(self.case.service.ids))
        response=self.case.client.post('/api/tree-pages',headers=self.case.headers,
            json={'protocol_uuid':self.case.service.protocol_id,'splits':'cell'})
        self.assertEqual(response.status_code,200,response.get_json())
        page=response.get_json();self.assertNotIn('matlab_command',page)
        self.assertEqual(page['total_epochs'],len(self.case.service.ids))


"""Metadata refresh ignores retired plotting sidecars and preserves source facts."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import test_workspace_api as fixtures

class DataOnlyMetadataRefreshTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.WorkspaceAPITests('runTest');self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_metadata_status_and_refresh_never_scan_or_offer_ugm_sidecars(self):
        path=Path(self.case.temp.name)/'exports/legacy-fixture/matlab/selection.ugm'
        path.parent.mkdir(parents=True);path.write_bytes(b'opaque historical mask preserved unchanged')
        original=path.read_bytes();before=copy.deepcopy(self.case.curation.rows)
        status=self.case.client.get('/api/metadata/status').get_json()
        self.assertNotIn('masks',status)
        with patch('recording_workspace.workspace_tables',return_value=(None,self.case.sources,self.case.events,None)):
            response=self.case.client.post('/api/metadata/refresh',json={},headers=self.case.headers)
        self.assertEqual(response.status_code,200,response.get_json())
        result=response.get_json();self.assertNotIn('masks',result)
        self.assertTrue(all('MATLAB' not in warning for warning in result['warnings']))
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(self.case.curation.rows,before)
