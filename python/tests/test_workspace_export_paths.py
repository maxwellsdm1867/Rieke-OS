"""Managed export writes must not follow a directory symlink added after startup."""
from pathlib import Path
import tempfile
import unittest

if __package__:
    from . import test_workspace_api as api_fixture
    from . import test_workspace_candidate_exports as candidate_fixture
else:
    import test_workspace_api as api_fixture
    import test_workspace_candidate_exports as candidate_fixture


class ExportPathTests(unittest.TestCase):
    def redirect_exports(self, root):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        exports = Path(root) / 'exports'
        exports.rename(exports.with_name('exports.saved'))
        exports.symlink_to(outside.name, target_is_directory=True)
        return Path(outside.name)

    def test_protocol_export_rejects_live_symlink_without_files_or_sql_publication(self):
        case = api_fixture.WorkspaceAPITests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        outside = self.redirect_exports(case.temp.name)
        response = case.client.post(case.base + '/exports', json={
            'format':'reference-json', 'query_revision':case.revision()}, headers=case.headers)
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertIn('symbolic links', response.get_json()['error'])
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(case.datasets.rows, [])

    def test_candidate_export_rejects_live_symlink_without_files_or_sql_publication(self):
        case = candidate_fixture.CandidateExportTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        candidate = case.save()
        outside = self.redirect_exports(case.case.temp.name)
        response = case.export(candidate)
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertIn('symbolic links', response.get_json()['error'])
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(case.case.datasets.rows, [])

    def test_health_reports_canonical_project_root(self):
        case = api_fixture.WorkspaceAPITests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        response = case.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['project_path'], str(Path(case.temp.name).resolve()))
        self.assertEqual(response.get_json()['project_uuid'], case.service.project['project_uuid'])
