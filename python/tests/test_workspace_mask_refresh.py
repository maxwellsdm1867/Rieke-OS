"""Discovery is read-only; apply shares strict manual UGM validation."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import test_workspace_matlab_routes as fixture
from workspace_matlab_masks import write_ugm


class MaskRefreshTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.MatlabMaskRouteTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.case = self.fixture.case
        self.recipe, self.artifact = self.fixture.export()
        self.path = self.artifact.parent / 'matlab/selection.ugm'
        self.path.parent.mkdir()
        self.before = self.artifact.read_bytes()

    def refresh(self):
        with patch('recording_workspace.workspace_tables',return_value=(None,self.case.sources,self.case.events,None)):
            response=self.case.client.post('/api/metadata/refresh',json={},headers=self.case.headers)
        self.assertEqual(response.status_code,200,response.json)
        return response.json['masks']

    def apply(self, candidate):
        return self.case.client.post('/api/metadata/masks/apply',headers=self.case.headers,
            json={key:candidate[key] for key in ('dataset_uuid','location','input_sha256','query_revision')})

    def test_refresh_detects_and_apply_changes_only_inclusion_then_suppresses_replay(self):
        write_ugm(self.path,self.fixture.service.ids,[True,False])
        before=copy.deepcopy(self.case.curation.rows)
        masks=self.refresh();self.assertEqual(len(masks['candidates']),1)
        self.assertEqual(self.case.curation.rows,before)
        self.assertEqual(masks['candidates'][0]['changed_count'],1)
        response=self.apply(masks['candidates'][0]);self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['included_count'],1)
        self.assertEqual(self.refresh()['candidates'],[])
        self.assertEqual(self.artifact.read_bytes(),self.before)

    def test_changed_file_requires_new_preview(self):
        write_ugm(self.path,self.fixture.service.ids,[True,False])
        candidate=self.refresh()['candidates'][0]
        self.path.unlink();write_ugm(self.path,self.fixture.service.ids,[False,True])
        self.assertEqual(self.apply(candidate).status_code,400)
        self.assertFalse(self.case.curation.rows)

    def test_unknown_uuid_and_redirected_paths_never_apply(self):
        import uuid
        write_ugm(self.path,[str(uuid.uuid4())],[False])
        masks=self.refresh();self.assertFalse(masks['candidates']);self.assertTrue(masks['errors'])
        self.path.unlink();self.path.symlink_to(self.artifact)
        self.assertTrue(self.refresh()['errors']);self.assertFalse(self.case.curation.rows)

    def test_no_changes_not_reported_and_source_scope_staleness_rejected(self):
        write_ugm(self.path,self.fixture.service.ids,[True,True])
        self.assertEqual(self.refresh()['candidates'],[])
        self.path.unlink();write_ugm(self.path,self.fixture.service.ids,[True,False])
        candidate=self.refresh()['candidates'][0]
        self.fixture.service.change_on_refresh=True
        self.assertEqual(self.apply(candidate).status_code,409)
        self.assertFalse(self.case.curation.rows)
