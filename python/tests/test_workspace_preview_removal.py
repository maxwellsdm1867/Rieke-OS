"""Query-building preview paths are gone: results carry no inline statistics.

Summary-only previews, runs and revisions never compute scoped statistics,
whatever catalog_summary says; count-only summary jobs and the candidate
count-preview route are refused.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

import test_workspace_explore_queries as explore_fixture


class PreviewRemovalTests(unittest.TestCase):
    join = explore_fixture.RequestedSummaryTests.join

    def setUp(self):
        from disco.metadata.disk_index import DiskMetadataIndex
        explore_fixture.RequestedSummaryTests.setUp(self)
        from disco.navigation.search_presets import SearchPresets
        from test_workspace_curation import Table
        from test_workspace_search_presets import PresetTable
        tables = (PresetTable(('project_uuid', 'preset_uuid')), Table(('project_uuid', 'preset_uuid', 'version')))
        runs = Table(('project_uuid', 'query_sha256'))
        self.fixture.connection.tables.extend([*tables, runs])
        self.fixture.app.extensions['search_presets'] = SearchPresets(self.fixture.store, tables, runs=runs)
        path = Path(self.fixture.temp.name) / 'cache' / 'metadata' / ('d' * 64 + '.sqlite')
        self.index = DiskMetadataIndex.build(path, self.service.rows, self.service.details,
            self.service.sources, 'd' * 64, self.service.project['project_uuid'])
        self.service.disk_index = self.index

    def post(self, path, body, status=200):
        response = self.client.post(path, json=body, headers=self.fixture.headers)
        self.assertEqual(response.status_code, status, response.get_json())
        return response.get_json()

    def test_summary_only_results_never_compute_scoped_statistics(self):
        from disco.metadata.disk_index import DiskMetadataIndex
        original = DiskMetadataIndex.catalog

        def unscoped(index, ids=None, known_fields=None):
            if ids is not None:
                raise AssertionError('computed scoped statistics')
            return original(index, ids, known_fields)
        body = {'predicate': {'all': []}, 'splits': 'cell', 'summary_only': True}
        with patch.object(DiskMetadataIndex, 'catalog', unscoped):
            requested = self.post('/api/explore/preview', {**body, 'catalog_summary': True})
            plain = self.post('/api/explore/preview', {**body, 'catalog_summary': False})
            omitted = self.post('/api/explore/preview', body)
            run = self.post('/api/explore/run', {'predicate': {'all': []}, 'splits': 'cell', 'catalog_summary': True})
            run_omitted = self.post('/api/explore/run', {'predicate': {'all': []}, 'splits': 'cell'})
        self.assertEqual(requested, plain)
        self.assertEqual(omitted, plain)
        self.assertFalse(requested['catalog_summary'])
        self.assertFalse(run['catalog_summary'])
        self.assertFalse(run_omitted['catalog_summary'])
        run.pop('last_run'); run_omitted.pop('last_run')
        self.assertEqual(run, run_omitted)
        self.post('/api/explore/preview', {**body, 'catalog_summary': 'yes'}, status=400)

    def test_count_only_jobs_are_refused(self):
        self.post('/api/explore/summaries', {'predicate': {'all': []}, 'summary_fields': []}, status=400)


if __name__ == '__main__':
    unittest.main()
