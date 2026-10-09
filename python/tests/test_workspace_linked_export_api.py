"""Linked export publication/download through real routes and SQL doubles."""
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import shutil
import tempfile
import threading
import zipfile

from linked_export_loader import LinkedExport
import test_workspace_api as api_tests
import test_workspace_candidate_exports as candidate_tests
import test_workspace_suggestions as suggestion_tests
import test_workspace_workbench_exports as incoming_tests
from test_workspace_linked_sqlite import linked_fixture


class LinkedExportAPITests(unittest.TestCase):
    def prepare_case(self, fixture):
        # Managed recording registries live beside projects, so the project's
        # parent must also belong to this fixture (never the shared system /tmp).
        temporary = tempfile.TemporaryDirectory
        workspace = temporary()
        self.addCleanup(workspace.cleanup)
        self.addCleanup(fixture.doCleanups)
        def child_directory(*args, **kwargs):
            if kwargs.get('dir') is None:
                kwargs['dir'] = workspace.name
            return temporary(*args, **kwargs)
        with patch.object(api_tests.tempfile, 'TemporaryDirectory', side_effect=child_directory):
            fixture.setUp()

    def test_incoming_fixture_does_not_use_ambient_temp_registry(self):
        with tempfile.TemporaryDirectory() as ambient:
            unrelated = Path(ambient) / '.disco-recordings.json'
            unrelated.write_text('unrelated registry bytes')
            fixture = LinkedExportAPITests()
            try:
                with patch.object(tempfile, 'tempdir', ambient):
                    fixture.setup_incoming()
                self.assertNotEqual(Path(fixture.case.temp.name).parent, Path(ambient))
            finally:
                fixture.doCleanups()
            self.assertEqual(unrelated.read_text(), 'unrelated registry bytes')
            self.assertFalse((Path(ambient) / '.disco-recordings.lock').exists())

    def test_failed_nested_fixture_restores_thread_class(self):
        original = threading.Thread
        fixture = LinkedExportAPITests()
        original_setup = suggestion_tests.ImportSuggestionTests.setUp
        def fail_after_import_setup(case):
            original_setup(case)
            raise RuntimeError('Injected fixture failure')
        try:
            with patch.object(suggestion_tests.ImportSuggestionTests, 'setUp', fail_after_import_setup):
                with self.assertRaisesRegex(RuntimeError, 'Injected fixture failure'):
                    fixture.setup_incoming()
        finally:
            fixture.doCleanups()
        self.assertIs(threading.Thread, original)

    def setup_case(self, candidate=False):
        if candidate:
            self.candidate = candidate_tests.CandidateExportTests()
            self.prepare_case(self.candidate)
            case = self.candidate.case
        else:
            case = api_tests.WorkspaceAPITests()
            self.prepare_case(case)
        self.case = case
        service, self.package = linked_fixture(case.temp.name, case.service)
        sha = service.sources[0]['source_sha256']
        case.sources.rows[0].update(source_sha256=sha, manifest=copy.deepcopy(service.manifests[sha]))
        return service

    def verify_download(self, response, expected_ids):
        self.assertEqual(response.status_code, 201, response.get_json())
        receipt = response.get_json()
        self.assertEqual(receipt['format'], 'linked-sqlite')
        download = self.case.client.get(receipt['download_url'])
        try:
            self.assertEqual(download.status_code, 200)
            with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
                folder = Path(self.case.temp.name) / 'downloaded'
                archive.extractall(folder)
        finally:
            download.close()
        with LinkedExport(folder / 'recordings.sqlite') as export:
            self.assertEqual(set(export.members), set(expected_ids))
            for key in expected_ids:
                self.assertEqual(export.record(key)['parameters'], self.case.service.details[key]['parameters'])
        output = Path(self.case.temp.name) / 'exports' / receipt['dataset_uuid']
        self.assertFalse((output / 'recordings.json').exists())
        self.assertTrue((output / 'recipe.json').exists())
        return receipt

    def test_protocol_export_publishes_small_bundle_and_preserves_focused_membership(self):
        service = self.setup_case()
        key = service.ids[0]
        current = self.case.client.get(self.case.base).get_json()
        response = self.case.client.post(self.case.base + '/exports', json={
            'format': 'linked-sqlite', 'query_revision': current['query_revision'],
            'filters': {'epoch_uuid': key}, 'split_order': 'cell,parameters/condition',
            'review_policy': 'include_unreviewed'}, headers=self.case.headers)
        self.verify_download(response, [key])

    def test_candidate_export_publishes_without_creating_protocol_or_accepting(self):
        service = self.setup_case(candidate=True)
        candidate = self.candidate.save(splits='cell,parameters/condition')
        before = copy.deepcopy((self.case.protocol_bindings.rows, self.case.curation.rows))
        response = self.candidate.export(candidate, 'linked-sqlite')
        self.verify_download(response, service.ids)
        self.assertEqual((self.case.protocol_bindings.rows, self.case.curation.rows), before)

    def setup_incoming(self):
        original = suggestion_tests.ImportSuggestionTests.setUp
        added_ids = []
        def prepare(fixture):
            original(fixture)
            case = fixture.case
            donor_root = Path(case.temp.name) / 'owned-incoming-fixture'
            donor_root.mkdir()
            donor, package = linked_fixture(donor_root)
            added_ids.extend(donor.ids)
            source = donor.sources[0]
            sha = source['source_sha256']
            project = case.service.project_dir
            (project / 'project.json').write_text(json.dumps({'format': 'recording-project', 'version': 1, **case.service.project}))
            raw = project / 'raw-uploads' / 'incoming.h5'
            raw.parent.mkdir(exist_ok=True)
            shutil.copyfile(source['source_path'], raw)
            shutil.copyfile(raw, fixture.source)
            fixture.source_sha = sha
            metadata = project / 'imports' / 'incoming' / 'metadata.catalog.json'
            metadata.parent.mkdir(parents=True)
            manifest = {**donor.manifests[sha], 'source_path': str(raw), 'metadata_path': str(metadata)}
            shutil.copyfile(donor.manifests[sha]['metadata_path'], metadata)
            (metadata.parent / 'import-manifest.json').write_text(json.dumps(manifest))
            def add_recording():
                service = case.service
                service.rows.update(copy.deepcopy(donor.rows))
                service.details.update(copy.deepcopy(donor.details))
                service.cells.update(copy.deepcopy(donor.cells))
                service._fingerprints.update(donor._fingerprints)
                service.sources.append({**source, 'source_path': str(raw), 'counts': {'cells': 2, 'epochs': 2}})
                service.manifests[sha] = manifest
                case.sources.insert1({'project_uuid': service.project['project_uuid'], 'source_sha256': sha, 'manifest': manifest})
                result = service.protocols[service.protocol_id]['result']
                result['epochs'].extend({'uuid': key, 'metadata_hash': donor._fingerprints[key]} for key in donor.ids)
                result['source_revisions'].append(sha)
                result['cells'].extend({'uuid': key} for key in donor.cell_ids)
                service._tree_catalog_cache = {}
                service._registered_tree_cache = service._registered_predicate_cache = service._predicate_catalog_cache = None
                return donor.ids[0]
            fixture.add_recording = add_recording
        workflow = incoming_tests.IncomingExportTests()
        with patch.object(suggestion_tests.ImportSuggestionTests, 'setUp', prepare):
            self.prepare_case(workflow)
        self.case = workflow.case
        return workflow, added_ids

    def test_incoming_linked_export_does_not_accept_and_replays_receipt(self):
        workflow, ids = self.setup_incoming()
        request = workflow.standalone_request('linked-sqlite')
        before = copy.deepcopy(self.case.protocol_bindings.rows)
        response = self.case.client.post(workflow.root + '/exports', json=request, headers=self.case.headers)
        receipt = self.verify_download(response, ids)
        self.assertEqual(self.case.protocol_bindings.rows, before)
        replay = self.case.client.post(workflow.root + '/exports', json=request, headers=self.case.headers)
        self.assertEqual(replay.status_code, 200, replay.get_json())
        self.assertEqual(replay.get_json(), receipt)
        self.assertEqual(len(self.case.datasets.rows), 1)

    def test_accepted_new_linked_export_preserves_independent_acceptance(self):
        workflow, ids = self.setup_incoming()
        acceptance = workflow.accept(workflow.accepted_request())
        self.assertEqual(acceptance.status_code, 200, acceptance.get_json())
        root, request = workflow.receipt_export_request(acceptance.get_json(), 'linked-sqlite')
        before = copy.deepcopy(self.case.protocol_bindings.rows)
        response = self.case.client.post(root + '/exports', json=request, headers=self.case.headers)
        self.verify_download(response, ids)
        self.assertEqual(self.case.protocol_bindings.rows, before)


if __name__ == '__main__':
    unittest.main()
