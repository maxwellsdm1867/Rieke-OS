"""Two real HTTP export callers before a format-materialization extraction.

Owned synthetic files and existing transactional DB doubles only. Successful
formats use their real writers and independent JSON/SQLite/MAT readers. Faults
are injected at filesystem/serializer/publication boundaries, not a new port.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scipy.io import loadmat

import test_workspace_candidate_exports as fixtures
import workspace_api
import disco.workbench.candidate_exports as workspace_candidate_exports
import workspace_matlab
import workspace_sqlite


class ExportBoundaryTests(unittest.TestCase):
    def setUp(self):
        preferences = tempfile.TemporaryDirectory()
        self.addCleanup(preferences.cleanup)
        isolated = patch.dict(os.environ, {'RIEKE_PREFERENCES_DIR': preferences.name})
        isolated.start()
        self.addCleanup(isolated.stop)

    @contextmanager
    def caller(self, kind):
        fixture = fixtures.CandidateExportTests()
        fixture.setUp()
        try:
            api = fixture.case
            if kind == 'candidate':
                candidate = fixture.save()
                request = lambda fmt: fixture.export(candidate, fmt)
                owner = workspace_candidate_exports
            else:
                revision = api.revision()
                request = lambda fmt: api.client.post(api.base + '/exports', json={
                    'format': fmt, 'query_revision': revision,
                    'review_policy': 'include_unreviewed', 'split_order': 'date,cell',
                }, headers=api.headers)
                owner = workspace_api
            export_root = (fixture.service.project_dir / 'exports').resolve()
            old_dirs = set(p for p in export_root.iterdir() if p.is_dir())
            before = copy.deepcopy((api.datasets.rows, api.events.rows,
                                    api.curation.rows, api.protocol_bindings.rows))
            yield fixture, owner, request, lambda: sorted(
                set(p for p in export_root.iterdir() if p.is_dir()) - old_dirs), before
        finally:
            fixture.doCleanups()

    def assert_unpublished(self, fixture, before):
        api = fixture.case
        self.assertEqual((api.datasets.rows, api.events.rows,
                          api.curation.rows, api.protocol_bindings.rows), before)

    def success(self, kind, fmt):
        with self.caller(kind) as (fixture, owner, request, outputs, before):
            response = request(fmt)
            self.assertEqual(response.status_code, 201, response.get_json())
            receipt = response.get_json()
            root, = outputs()
            package = json.loads((root / 'recordings.json').read_text())
            recipe = json.loads((root / 'recipe.json').read_text())
            self.assertEqual(package['recipe'], recipe)
            expected = set(fixture.service.ids)
            self.assertEqual({r['epoch_uuid'] for r in package['epochs']}, expected)
            self.assertEqual({r['uuid'] for r in recipe['epochs']}, expected)
            self.assertEqual([r['epoch_uuid'] for r in package['epochs']], fixture.service.ids)
            self.assertEqual([r['uuid'] for r in recipe['epochs']], sorted(fixture.service.ids))
            artifact = Path(receipt['artifact_path'])
            self.assertEqual(receipt['artifact_sha256'], hashlib.sha256(artifact.read_bytes()).hexdigest())
            self.assertEqual(receipt['format'], fmt)
            self.assertFalse((root / 'failure.json').exists())
            if kind == 'candidate':
                self.assertEqual(package['export_scope']['kind'], 'explorer_candidate')
                self.assertFalse(fixture.case.protocol_bindings.rows)
                self.assertFalse(fixture.case.curation.rows)
            else:
                self.assertNotIn('export_scope', package)
            if fmt == 'reference-json':
                self.assertEqual(artifact, root / 'recordings.json')
                self.assertFalse((root / 'annotations').exists())
                self.assertFalse((root / 'matlab').exists())
            elif fmt == 'wheeler-sqlite':
                self.assertEqual(artifact, root / 'recordings.sqlite')
                with sqlite3.connect(artifact.as_uri() + '?mode=ro', uri=True) as db:
                    self.assertEqual({r[0] for r in db.execute('SELECT epoch_uuid FROM epochs')}, expected)
                returns = json.loads((root / 'annotation-return.json').read_text())
                self.assertEqual(returns['export_uuid'], recipe['export_uuid'])
                self.assertTrue((root / 'annotations' / 'incoming').is_dir())
                self.assertEqual({r['target_uuid'] for r in returns['targets']
                                  if r['target_kind'] == 'epoch'}, expected)
            else:
                self.assertEqual(artifact, root / 'matlab' / 'recordings.mat')
                data = loadmat(artifact, simplify_cells=True)
                self.assertEqual({e['h5_uuid'] for e in fixtures.matlab_epochs(data)}, expected)
                report = json.loads((root / 'matlab' / 'export-report.json').read_text())
                self.assertNotIn('mat_path', report)
                self.assertNotIn('recipe_path', report)
                self.assertEqual(set(report['epoch_order']), expected)
                self.assertFalse((root / 'annotations').exists())

    def test_protocol_reference(self): self.success('protocol', 'reference-json')
    def test_candidate_reference(self): self.success('candidate', 'reference-json')
    def test_protocol_sqlite(self): self.success('protocol', 'wheeler-sqlite')
    def test_candidate_sqlite(self): self.success('candidate', 'wheeler-sqlite')
    def test_protocol_matlab(self): self.success('protocol', 'matlab-mat')
    def test_candidate_matlab(self): self.success('candidate', 'matlab-mat')

    def test_reference_json_failure_has_distinct_caller_catch_boundaries(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                write = owner.write_json
                def fail_reference(path, value):
                    if Path(path).name == 'recordings.json':
                        Path(path).write_text('partial reference artifact')
                        raise ValueError('reference artifact fault')
                    return write(path, value)
                with patch.object(owner, 'write_json', side_effect=fail_reference):
                    response = request('reference-json')
                self.assertEqual(response.status_code, 400, response.get_json())
                self.assertEqual(response.get_json()['error'], 'reference artifact fault')
                root, = outputs()
                self.assertTrue((root / 'recipe.json').is_file())
                self.assertEqual((root / 'recordings.json').read_text(), 'partial reference artifact')
                self.assertEqual((root / 'failure.json').exists(), kind == 'candidate')
                self.assert_unpublished(fixture, before)

    def test_recipe_failure_has_distinct_caller_catch_boundaries(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                with patch.object(owner, 'save_snapshot', side_effect=ValueError('recipe fault')):
                    response = request('reference-json')
                self.assertEqual(response.status_code, 400)
                root, = outputs()
                self.assertFalse((root / 'recordings.json').exists())
                self.assertEqual((root / 'failure.json').exists(), kind == 'candidate')
                self.assert_unpublished(fixture, before)

    def test_serializer_failure_retains_artifacts_without_publication(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                writer = workspace_sqlite.build_sqlite_export
                def fail_after_write(package, path):
                    writer(package, path)
                    raise ValueError('serializer fault after artifact')
                with patch.object(workspace_sqlite, 'build_sqlite_export', side_effect=fail_after_write):
                    response = request('wheeler-sqlite')
                self.assertEqual(response.status_code, 400)
                root, = outputs()
                self.assertTrue((root / 'recordings.sqlite').is_file())
                self.assertTrue((root / 'recordings.json').is_file())
                self.assertFalse((root / 'annotations').exists())
                failure = json.loads((root / 'failure.json').read_text())
                self.assertEqual(failure['error'], 'serializer fault after artifact')
                self.assertFalse(failure['artifact_published'])
                self.assertEqual('export_scope' in failure, kind == 'candidate')
                self.assert_unpublished(fixture, before)

    def test_return_folder_failure_retains_sqlite_without_publication(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                with patch('disco.decisions.external_tags.prepare_return_folder', side_effect=ValueError('return folder fault')):
                    response = request('wheeler-sqlite')
                self.assertEqual(response.status_code, 400)
                root, = outputs()
                self.assertTrue((root / 'recordings.sqlite').exists())
                self.assertEqual(json.loads((root / 'failure.json').read_text())['error'], 'return folder fault')
                self.assert_unpublished(fixture, before)

    def test_matlab_report_failure_retains_mat_without_publication(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                write = owner.write_json
                def fail_report(path, value):
                    if Path(path).name == 'export-report.json':
                        raise ValueError('MATLAB report fault')
                    return write(path, value)
                with patch.object(owner, 'write_json', side_effect=fail_report):
                    response = request('matlab-mat')
                self.assertEqual(response.status_code, 400)
                root, = outputs()
                self.assertTrue((root / 'matlab' / 'recordings.mat').is_file())
                self.assertEqual(json.loads((root / 'failure.json').read_text())['error'], 'MATLAB report fault')
                self.assert_unpublished(fixture, before)

    def test_publication_failure_preserves_completed_artifact(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                with patch.object(fixture.store, 'record_dataset_revision', side_effect=ValueError('publication fault')):
                    response = request('reference-json')
                self.assertEqual(response.status_code, 400)
                root, = outputs()
                self.assertEqual(len(json.loads((root / 'recordings.json').read_text())['epochs']), 2)
                self.assertEqual(json.loads((root / 'failure.json').read_text())['error'], 'publication fault')
                self.assert_unpublished(fixture, before)

    def test_missing_mat_path_writes_filtered_report_before_failure(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                report = {'recipe_path': 'private adapter path', 'diagnostic': 'retained detail'}
                with patch('workspace_matlab.build_matlab_export', return_value=report):
                    response = request('matlab-mat')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()['error'], "'mat_path'")
                root, = outputs()
                self.assertEqual(json.loads((root / 'matlab' / 'export-report.json').read_text()),
                                 {'diagnostic': 'retained detail'})
                self.assertTrue((root / 'failure.json').is_file())
                self.assert_unpublished(fixture, before)

    def test_matlab_adapter_returned_path_is_hashed_and_published(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                writer = workspace_matlab.build_matlab_export
                def alternate_path(*args, **kwargs):
                    result = writer(*args, **kwargs)
                    original = Path(result['mat_path'])
                    alternate = original.with_name('adapter-selected.mat')
                    original.rename(alternate)
                    return {**result, 'mat_path': str(alternate)}
                with patch.object(workspace_matlab, 'build_matlab_export', side_effect=alternate_path):
                    response = request('matlab-mat')
                self.assertEqual(response.status_code, 201, response.get_json())
                root, = outputs()
                artifact = root / 'matlab' / 'adapter-selected.mat'
                self.assertEqual(Path(response.get_json()['artifact_path']), artifact)
                self.assertEqual(response.get_json()['artifact_sha256'], hashlib.sha256(artifact.read_bytes()).hexdigest())
                self.assertFalse((root / 'matlab' / 'recordings.mat').exists())
                self.assertFalse((root / 'failure.json').exists())

    def test_artifact_hash_failure_precedes_store_publication(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                with patch.object(owner, 'digest', side_effect=ValueError('artifact hash fault')), \
                     patch.object(fixture.store, 'record_dataset_revision', wraps=fixture.store.record_dataset_revision) as publish:
                    response = request('reference-json')
                self.assertEqual(response.status_code, 400)
                publish.assert_not_called()
                root, = outputs()
                self.assertTrue((root / 'recordings.json').is_file())
                self.assertEqual(json.loads((root / 'failure.json').read_text())['error'], 'artifact hash fault')
                self.assert_unpublished(fixture, before)

    def test_output_directory_failure_is_outside_both_catch_blocks(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                export_root = (fixture.service.project_dir / 'exports').resolve()
                mkdir = Path.mkdir
                def fail_export_directory(path, *args, **kwargs):
                    if path.parent.resolve() == export_root:
                        raise ValueError('fresh output directory fault')
                    return mkdir(path, *args, **kwargs)
                with patch.object(Path, 'mkdir', new=fail_export_directory), \
                     patch.object(owner, 'write_json', wraps=owner.write_json) as writes:
                    response = request('reference-json')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()['error'], 'fresh output directory fault')
                self.assertFalse(any(Path(call.args[0]).name == 'failure.json' for call in writes.call_args_list))
                self.assertEqual(outputs(), [])
                self.assert_unpublished(fixture, before)

    def test_failure_report_oserror_preserves_only_candidate_original_error(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                write = owner.write_json
                def fail_report(path, value):
                    if Path(path).name == 'failure.json':
                        raise OSError('secondary failure report fault')
                    return write(path, value)
                with patch.object(workspace_sqlite, 'build_sqlite_export', side_effect=ValueError('primary serializer fault')), \
                     patch.object(owner, 'write_json', side_effect=fail_report):
                    response = request('wheeler-sqlite')
                self.assertEqual(response.status_code, 400 if kind == 'candidate' else 500)
                if kind == 'candidate':
                    self.assertEqual(response.get_json()['error'], 'primary serializer fault')
                else:
                    incident = response.get_json()['incident']
                    logs = list(fixture.service.project_dir.rglob(incident + '.txt'))
                    self.assertEqual(len(logs), 1)
                    self.assertIn('secondary failure report fault', logs[0].read_text())
                root, = outputs()
                self.assertFalse((root / 'failure.json').exists())
                self.assert_unpublished(fixture, before)

    def test_candidate_failure_report_suppresses_only_oserror(self):
        with self.caller('candidate') as (fixture, owner, request, outputs, before):
            write = owner.write_json
            def fail_report(path, value):
                if Path(path).name == 'failure.json':
                    raise ValueError('non-OS report fault')
                return write(path, value)
            with patch.object(workspace_sqlite, 'build_sqlite_export', side_effect=ValueError('primary serializer fault')), \
                 patch.object(owner, 'write_json', side_effect=fail_report):
                response = request('wheeler-sqlite')
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()['error'], 'non-OS report fault')
            self.assert_unpublished(fixture, before)

    def test_unsupported_format_never_stages_or_publishes(self):
        for kind in ('protocol', 'candidate'):
            with self.subTest(kind=kind), self.caller(kind) as (fixture, owner, request, outputs, before):
                response = request('invented-format')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(outputs(), [])
                self.assert_unpublished(fixture, before)


if __name__ == '__main__':
    unittest.main()
