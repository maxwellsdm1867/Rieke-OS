"""Typed sidecar memory budget and refresh fallback.

The builder budgets its own growth of process peak memory, so an app already
holding a large published generation can still build the sidecar; any typed
build failure leaves refresh publishing the native generation, and health
reports the typed index as unavailable with its reason.
"""
import resource
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_workspace_api as api_fixture
import test_workspace_explore_queries as explore_fixture


def peak_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == 'darwin' else value * 1024


class TypedBudgetTests(unittest.TestCase):
    def setUp(self):
        self.fixture = api_fixture.WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service, self.client = self.fixture.service, self.fixture.client

    def test_process_already_above_the_budget_still_builds(self):
        from disco.metadata.disk_index import DiskMetadataIndex
        from disco.metadata.typed_index import TypedMetadataIndex, build
        folder = Path(self.fixture.temp.name) / 'budget'
        native = DiskMetadataIndex.build(folder / 'native.sqlite', self.service.rows, self.service.details,
            self.service.sources, 'b' * 64, self.service.project['project_uuid'])
        # The process already holds more than the whole budget.
        budget_gib = peak_bytes() / 2 / 1024**3
        target = folder / 'typed.sqlite'
        build(native.path, target, max_rss_gib=budget_gib, expected_generation='b' * 64,
              expected_project_uuid=self.service.project['project_uuid'])
        reader = TypedMetadataIndex(target, native.path, expected_generation='b' * 64,
                                    expected_project_uuid=self.service.project['project_uuid'])
        self.assertEqual(reader.count(), len(self.service.rows))
        reader.close()

    def test_health_reports_typed_index_availability(self):
        health = self.client.get('/api/health').get_json()
        self.assertEqual(health['typed_index'], {'status': 'unavailable', 'reason': 'not built'})
        self.service.last_successful_refresh = {'typed_metadata_index': 'unavailable',
                                                'typed_metadata_index_error': 'RuntimeError: RSS budget exceeded'}
        status = self.client.get('/api/metadata/status').get_json()
        self.assertEqual(status['typed_index'], {'status': 'unavailable', 'reason': 'RuntimeError: RSS budget exceeded'})
        self.service.typed_index = object()
        self.assertEqual(self.client.get('/api/health').get_json()['typed_index'], {'status': 'available'})


class TypedRefusalRefreshTests(unittest.TestCase):
    """A forced budget refusal: refresh succeeds on the native fallback."""
    setUp = explore_fixture.PublicationCacheTests.setUp

    def test_forced_budget_refusal_keeps_refresh_succeeding(self):
        from disco.metadata import typed_index
        with patch.object(typed_index.Budget, 'check', side_effect=RuntimeError('RSS budget exceeded')):
            # Remove the reusable sidecar so refresh must build one.
            self.service.typed_index = None
            for path in Path(self.fixture.folder).rglob('typed-metadata/*.sqlite'):
                path.unlink()
            result = self.service.refresh()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['typed_metadata_index'], 'unavailable')
        self.assertIn('RSS budget exceeded', result['typed_metadata_index_error'])
        self.assertIsNone(self.service.typed_index)
        self.assertEqual(len(self.service.explore_page({'all': []})['rows']), len(self.service.rows))


if __name__ == '__main__':
    unittest.main()
