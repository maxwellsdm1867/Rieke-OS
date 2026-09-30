"""Folder navigation stays local, read-only, shallow and explicitly paged."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

import workspace_folder_browser as browser


class FolderBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        for name in ('Beta', 'alpha', 'Zulu', '.hidden'):
            (self.root / name).mkdir()
        (self.root / 'recording.h5').write_bytes(b'file contents must never be served')
        (self.root / 'alias').symlink_to(self.root / 'alpha', target_is_directory=True)
        (self.root / 'broken alias').symlink_to(self.root / 'absent', target_is_directory=True)
        (self.root / 'alpha/nested').mkdir()
        self.app = Flask(__name__)
        browser.register_folder_browser_routes(self.app)
        self.client = self.app.test_client()
        self.headers = {'X-Workspace-Request': '1'}

    def test_sorted_direct_folders_only_and_no_file_reads(self):
        with patch.object(Path, 'open', side_effect=AssertionError('Do not read files')):
            result = browser.list_folder(self.root)
        self.assertEqual(result['directory'], str(self.root))
        self.assertEqual(result['parent'], str(self.root.parent))
        self.assertEqual([folder['name'] for folder in result['folders']], ['alpha', 'Beta', 'Zulu'])
        self.assertEqual([folder['path'] for folder in result['folders']],
                         [str(self.root / name) for name in ('alpha', 'Beta', 'Zulu')])
        self.assertEqual(result['total'], 3)
        self.assertFalse(result['has_more'])
        self.assertFalse(result['truncated'])

    def test_nonexistent_destination_uses_nearest_parent_without_creating_it(self):
        target = self.root / 'alpha/new project/data'
        before = set(self.root.rglob('*'))
        result = browser.list_folder(target)
        self.assertEqual(result['directory'], str(self.root / 'alpha'))
        self.assertEqual([folder['name'] for folder in result['folders']], ['nested'])
        self.assertEqual(before, set(self.root.rglob('*')))
        self.assertFalse(target.exists())
        self.assertFalse(result['requested_exists'])

    def test_home_locations_and_root_parent(self):
        for name in ('Documents', 'Desktop'):
            (self.root / name).mkdir()
        with patch.object(Path, 'home', return_value=self.root):
            result = browser.list_folder()
        self.assertEqual(result['directory'], str(self.root))
        locations = {entry['name']: entry['path'] for entry in result['locations']}
        self.assertEqual(locations['Home'], str(self.root))
        self.assertEqual(locations['Documents'], str(self.root / 'Documents'))
        self.assertEqual(locations['Desktop'], str(self.root / 'Desktop'))
        self.assertIsNone(browser.list_folder('/')['parent'])

    def test_parent_aliases_are_resolved_to_normal_absolute_paths(self):
        alias = self.root / 'directory alias'
        alias.symlink_to(self.root / 'alpha', target_is_directory=True)
        result = browser.list_folder(alias / 'nested/future project')
        self.assertEqual(result['directory'], str(self.root / 'alpha/nested'))
        self.assertNotIn('directory alias', result['directory'])
        self.assertTrue(browser.list_folder(alias)['requested_exists'])

    def test_pagination_is_explicit_and_bounded(self):
        first = browser.list_folder(self.root, limit=2)
        self.assertEqual([entry['name'] for entry in first['folders']], ['alpha', 'Beta'])
        self.assertTrue(first['has_more'])
        self.assertEqual(first['next_offset'], 2)
        last = browser.list_folder(self.root, offset=2, limit=2)
        self.assertEqual([entry['name'] for entry in last['folders']], ['Zulu'])
        self.assertFalse(last['has_more'])
        self.assertIsNone(last['next_offset'])
        self.assertEqual(browser.list_folder(self.root, offset=10)['folders'], [])
        for kwargs in ({'offset': -1}, {'offset': True}, {'limit': 0}, {'limit': 201}, {'limit': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                browser.list_folder(self.root, **kwargs)

    def test_scan_cap_is_reported_without_silent_truncation(self):
        with patch.object(browser, 'MAX_ENTRIES', 1):
            result = browser.list_folder(self.root)
        self.assertTrue(result['truncated'])
        self.assertLessEqual(result['total'], 1)
        self.assertFalse(result['empty'])

    def test_empty_counts_all_entries_including_files_and_hidden_names(self):
        selected = self.root / 'empty folder'
        selected.mkdir()
        self.assertTrue(browser.list_folder(selected)['empty'])
        self.assertTrue(browser.list_folder(selected)['requested_exists'])
        for name in ('recording.h5', '.hidden file'):
            with self.subTest(name=name):
                file = selected / name
                file.write_bytes(b'only entry')
                result = browser.list_folder(selected)
                self.assertEqual(result['folders'], [])
                self.assertFalse(result['empty'])
                file.unlink()

    def test_missing_destination_inside_empty_parent_is_not_an_existing_empty_folder(self):
        parent = self.root / 'Empty parent'
        parent.mkdir()
        result = browser.list_folder(parent / 'New study')
        self.assertEqual(result['directory'], str(parent))
        self.assertTrue(result['empty'])
        self.assertFalse(result['requested_exists'])
        self.assertTrue(browser.list_folder(parent)['requested_exists'])
        self.assertFalse((parent / 'New study').exists())

    def test_inaccessible_children_are_omitted_and_selected_folder_reports_error(self):
        actual_access = os.access
        with patch.object(browser.os, 'access', side_effect=lambda path, mode: (
                False if Path(path) == self.root / 'Beta' else actual_access(path, mode))):
            result = browser.list_folder(self.root)
        self.assertEqual([entry['name'] for entry in result['folders']], ['alpha', 'Zulu'])
        with patch.object(browser.os, 'access', return_value=False):
            with self.assertRaisesRegex(ValueError, 'Access denied'):
                browser.list_folder(self.root)
        with patch.object(browser.os, 'scandir', side_effect=PermissionError('private details')):
            with self.assertRaisesRegex(ValueError, '^Access denied'):
                browser.list_folder(self.root)

    def test_relative_empty_nonstring_and_file_paths_are_rejected(self):
        for value in ('relative/folder', '', [], self.root / 'recording.h5'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                browser.list_folder(value)

    def test_route_accepts_deliberate_local_requests_and_rejects_invalid_queries(self):
        response = self.client.get('/api/folders', query_string={'directory': str(self.root), 'limit': 2},
                                   headers={**self.headers, 'Origin': 'http://localhost'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['next_offset'], 2)
        for query in ({'file': str(self.root / 'recording.h5')}, {'directory': ''},
                      {'directory': 'relative'}, {'offset': '-1'}, {'offset': '1.5'},
                      {'offset': '\u0661'}, {'limit': '201'}, {'offset': '1' * 20}):
            with self.subTest(query=query):
                result = self.client.get('/api/folders', query_string=query, headers=self.headers)
                self.assertEqual(result.status_code, 400)
        response = self.client.get('/api/folders?directory=/&directory=/tmp', headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_privacy_boundary_rejects_untrusted_get_before_filesystem_access(self):
        requests = ({'headers': {}},
                    {'headers': {**self.headers, 'Origin': 'https://other.example'}},
                    {'headers': self.headers, 'base_url': 'http://localhost.evil.example'},
                    {'headers': self.headers, 'environ_overrides': {'REMOTE_ADDR': '192.0.2.1'}})
        with patch.object(browser, 'list_folder', side_effect=AssertionError('No filesystem access')):
            for kwargs in requests:
                with self.subTest(kwargs=kwargs):
                    self.assertEqual(self.client.get('/api/folders', **kwargs).status_code, 403)


class ExportsFolderOpenTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.exports = self.root / 'exports'
        self.exports.mkdir()
        self.app = Flask(__name__)
        browser.register_folder_browser_routes(self.app, project_dir=self.root)
        self.client = self.app.test_client()
        self.headers = {'X-Workspace-Request': '1'}

    def test_fixed_exports_folder_opens_with_platform_command_without_reads_or_shell(self):
        for platform, executable in (('darwin', 'open'), ('win32', 'explorer'), ('linux', 'xdg-open')):
            with self.subTest(platform=platform), patch.object(browser.sys, 'platform', platform), \
                 patch.object(browser.subprocess, 'run') as run, \
                 patch.object(Path, 'open', side_effect=AssertionError('No file contents')):
                result = self.client.post('/api/exports/open-folder', json={}, headers=self.headers)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.get_json(), {'opened': True, 'directory': str(self.exports)})
                run.assert_called_once_with([executable, str(self.exports)], check=True, timeout=10,
                                            stdout=browser.subprocess.DEVNULL, stderr=browser.subprocess.DEVNULL)

    def test_launcher_without_project_cannot_open_an_arbitrary_folder(self):
        launcher = Flask('launcher')
        browser.register_folder_browser_routes(launcher)
        with patch.object(browser.subprocess, 'run') as run:
            result = launcher.test_client().post('/api/exports/open-folder', json={}, headers=self.headers)
            self.assertEqual(result.status_code, 400)
            self.assertIn('Open a project', result.get_json()['error'])
            run.assert_not_called()

    def test_missing_file_or_symlink_exports_never_launch_or_create_a_folder(self):
        self.exports.rmdir()
        with patch.object(browser.subprocess, 'run') as run:
            result = self.client.post('/api/exports/open-folder', json={}, headers=self.headers)
            self.assertEqual(result.status_code, 400)
            self.assertFalse(self.exports.exists())
            self.exports.write_bytes(b'not a folder')
            self.assertEqual(self.client.post('/api/exports/open-folder', json={}, headers=self.headers).status_code, 400)
            self.exports.unlink()
            for target in (self.root, self.root.parent):
                with self.subTest(target=target):
                    self.exports.symlink_to(target, target_is_directory=True)
                    result = self.client.post('/api/exports/open-folder', json={}, headers=self.headers)
                    self.assertEqual(result.status_code, 400)
                    self.assertIn('symbolic link', result.get_json()['error'])
                    self.exports.unlink()
            run.assert_not_called()

    def test_arbitrary_paths_queries_and_malformed_bodies_are_rejected(self):
        with patch.object(browser.subprocess, 'run') as run:
            for body in (None, [], True, {'directory': '/'}, {'path': str(self.root.parent)}):
                with self.subTest(body=body):
                    result = self.client.post('/api/exports/open-folder', json=body, headers=self.headers)
                    self.assertEqual(result.status_code, 400)
            self.assertEqual(self.client.post('/api/exports/open-folder?directory=/', json={}, headers=self.headers).status_code, 400)
            run.assert_not_called()

    def test_file_manager_errors_are_descriptive_and_do_not_modify_storage(self):
        for error in (FileNotFoundError('missing opener'),
                      browser.subprocess.CalledProcessError(1, ['open']),
                      browser.subprocess.TimeoutExpired(['open'], 10)):
            with self.subTest(error=type(error).__name__), patch.object(browser.subprocess, 'run', side_effect=error):
                result = self.client.post('/api/exports/open-folder', json={}, headers=self.headers)
                self.assertEqual(result.status_code, 400)
                self.assertIn('file manager', result.get_json()['error'])
                self.assertTrue(self.exports.is_dir())
                self.assertEqual(list(self.exports.iterdir()), [])

    def test_untrusted_requests_fail_before_filesystem_or_process_access(self):
        requests = ({'headers': {}},
                    {'headers': {**self.headers, 'Origin': 'https://other.example'}},
                    {'headers': self.headers, 'base_url': 'http://localhost.evil.example'},
                    {'headers': self.headers, 'environ_overrides': {'REMOTE_ADDR': '192.0.2.1'}})
        with patch.object(browser, '_open_exports_folder', side_effect=AssertionError('No filesystem/process access')):
            for kwargs in requests:
                with self.subTest(kwargs=kwargs):
                    self.assertEqual(self.client.post('/api/exports/open-folder', json={}, **kwargs).status_code, 403)


if __name__ == '__main__':
    unittest.main()
