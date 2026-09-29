"""Manual UGM HTTP imports with temporary artifacts and transactional DB doubles."""
import copy
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid
import zipfile

from recording_workspace import digest
from workspace_matlab_masks import write_ugm
from workspace_recipes import capture_query, prepare_export
if __package__:
    from . import test_workspace_api as api_fixture
else:
    import test_workspace_api as api_fixture


class MatlabMaskRouteTests(unittest.TestCase):
    def setUp(self):
        self.case = api_fixture.WorkspaceAPITests('runTest')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.service, self.store = self.case.service, self.case.store
        self.protocol = self.service.protocol_id
        self.path = self.service.project_dir / 'input.ugm'
        self.endpoint = self.case.base + '/masks/import-matlab'

    def export(self, ids=None):
        ids = self.service.ids if ids is None else ids
        result = self.service.query_result(self.protocol)
        result['metadata_fingerprint_version'] = 2
        result['source_scope'] = self.service.source_scope()
        snapshot = capture_query(self.service.protocols[self.protocol]['definition'], result,
                                 str(self.service.project_dir / 'catalog.json'))
        recipe = prepare_export(snapshot, ids, destination='epictree-mat',
            review_policy='include_unreviewed', actor='fixture', options={'name': 'MAT fixture'})
        output = self.service.project_dir / 'exports' / recipe['export_uuid']
        output.mkdir(parents=True)
        artifact = output / 'epictree-bundle.zip'
        with zipfile.ZipFile(artifact, 'w') as bundle:
            bundle.writestr('recordings.mat', b'fixture completion artifact; adapter is tested separately')
        current = self.store.read(self.protocol, self.service.ids,
                                  {key: self.service._fingerprints[key] for key in self.service.ids})
        self.store.record_dataset_revision(recipe, actor='fixture',
            expected_revisions={key: value['revision'] for key, value in current.items()},
            artifact_path=str(artifact), artifact_sha256=digest(artifact))
        return recipe, artifact

    def post(self, *, dataset_uuid=None, revision=None):
        form = {'file': (io.BytesIO(self.path.read_bytes()), 'selection.ugm'),
                'query_revision': self.case.revision() if revision is None else revision}
        if dataset_uuid:
            form['dataset_uuid'] = dataset_uuid
        return self.case.client.post(self.endpoint, data=form, content_type='multipart/form-data', headers=self.case.headers)

    def test_manual_import_matches_reordered_uuids_and_preserves_nonexported_decisions(self):
        third = str(uuid.uuid4())
        first = self.service.ids[0]
        self.service.rows[third] = {**self.service.rows[first], 'epoch_uuid': third}
        self.service.details[third] = copy.deepcopy(self.service.details[first])
        self.service.details[third]['metadata']['epoch']['uuid'] = third
        self.service._fingerprints[third] = 'b' * 64
        self.service.protocols[self.protocol]['result']['epochs'].append({'uuid': third, 'metadata_hash': 'b' * 64})
        self.service.ids.append(third)
        self.store.update(self.protocol, [third], {'included': False, 'tags_add': ['keep']},
                          {third: 0}, {third: 'b' * 64}, 'fixture')
        exported = self.service.ids[:2]
        recipe, artifact = self.export(exported)
        original_artifact = artifact.read_bytes()
        before_third = copy.deepcopy(next(row for row in self.case.curation.rows if row['epoch_uuid'] == third))
        write_ugm(self.path, exported[::-1], [False, True])
        response = self.post()
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual((body['dataset_uuid'], body['imported_count'], body['included_count']), (recipe['export_uuid'], 2, 1))
        states = {row['epoch_uuid']: row for row in self.case.curation.rows}
        self.assertTrue(states[exported[0]]['included'])
        self.assertFalse(states[exported[1]]['included'])
        self.assertEqual(states[third], before_third)
        self.assertEqual(artifact.read_bytes(), original_artifact)
        self.assertEqual(self.case.events.rows[-1]['payload']['query_context']['dataset_uuid'], recipe['export_uuid'])

    def test_ambiguous_same_membership_requires_explicit_dataset(self):
        first, _ = self.export()
        second, _ = self.export()
        write_ugm(self.path, self.service.ids, [True, False])
        response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()['code'], 'ambiguous_export')
        self.assertEqual({row['dataset_uuid'] for row in response.get_json()['matching_exports']},
                         {first['export_uuid'], second['export_uuid']})
        self.assertFalse(self.case.curation.rows)
        self.assertEqual(self.post(dataset_uuid=second['export_uuid']).status_code, 200)

    def test_foreign_or_partial_mask_never_updates_current_rows(self):
        recipe, _ = self.export()
        for ids in ([self.service.ids[0]], [self.service.ids[0], str(uuid.uuid4())]):
            with self.subTest(ids=ids):
                write_ugm(self.path, ids, [True] * len(ids))
                response = self.post(dataset_uuid=recipe['export_uuid'])
                self.assertEqual(response.status_code, 400, response.get_json())
                self.assertFalse(self.case.curation.rows)

    def test_stale_request_and_changed_metadata_fail_without_decisions(self):
        recipe, _ = self.export()
        write_ugm(self.path, self.service.ids, [True, False])
        self.assertEqual(self.post(dataset_uuid=recipe['export_uuid'], revision='stale').status_code, 409)
        self.service._fingerprints[self.service.ids[0]] = 'c' * 64
        response = self.post(dataset_uuid=recipe['export_uuid'])
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertIn('source metadata changed', response.get_json()['error'])
        self.assertFalse(self.case.curation.rows)

    def test_frozen_provenance_or_artifact_tampering_is_rejected(self):
        recipe, artifact = self.export()
        write_ugm(self.path, self.service.ids, [True, False], {'source_scope_revision': 'f' * 64})
        self.assertEqual(self.post(dataset_uuid=recipe['export_uuid']).status_code, 400)
        write_ugm(self.path, self.service.ids, [True, False])
        artifact.write_bytes(b'changed artifact')
        response = self.post(dataset_uuid=recipe['export_uuid'])
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertFalse(self.case.curation.rows)

    def test_event_failure_rolls_back_mask_decisions(self):
        recipe, _ = self.export()
        write_ugm(self.path, self.service.ids, [True, False])
        with patch.object(self.case.events, 'insert1', side_effect=RuntimeError('fixture audit failure')):
            response = self.post(dataset_uuid=recipe['export_uuid'])
        self.assertEqual(response.status_code, 500)
        self.assertFalse(self.case.curation.rows)


if __name__ == '__main__':
    unittest.main()
