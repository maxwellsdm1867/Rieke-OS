"""Previews return results without scoped statistics; fields are summarized on demand.

A summary-only preview that asks for catalog statistics answers immediately
with the result and a pointer to the per-field summary job; the job's facet for
a field reproduces the counts the inline catalog used to report.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

import test_workspace_explore_queries as explore_fixture


class PreviewStatisticsTests(unittest.TestCase):
    join = explore_fixture.RequestedSummaryTests.join

    def setUp(self):
        from disco.metadata.disk_index import DiskMetadataIndex
        from disco.metadata.typed_lifecycle import prepare
        explore_fixture.RequestedSummaryTests.setUp(self)
        path = Path(self.fixture.temp.name) / 'cache' / 'metadata' / ('f' * 64 + '.sqlite')
        self.index = DiskMetadataIndex.build(path, self.service.rows, self.service.details,
            self.service.sources, 'f' * 64, self.service.project['project_uuid'])
        self.service.disk_index = self.index
        self.service.typed_index, _ = prepare(self.index)

    def preview(self, **body):
        response = self.client.post('/api/explore/preview', json={'predicate': {'all': []}, 'splits': 'cell',
                                    'summary_only': True, **body}, headers=self.fixture.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_preview_never_computes_scoped_statistics_inline(self):
        from disco.metadata.disk_index import DiskMetadataIndex
        original = DiskMetadataIndex.catalog

        def unscoped_only(index, ids=None, known_fields=None):
            if ids is not None:
                raise AssertionError('preview computed scoped statistics')
            return original(index, ids, known_fields)
        with patch.object(DiskMetadataIndex, 'catalog', unscoped_only):
            requested = self.preview(catalog_summary=True)
            plain = self.preview(catalog_summary=False)
        self.assertEqual(requested['catalog_summary'], False)
        self.assertEqual(requested['catalog_statistics'], {'inline': False, 'per_field': {
            'method': 'POST', 'path': '/api/explore/summaries',
            'body': {'predicate': requested['predicate'], 'summary_fields': ['<field id>']}}})
        self.assertEqual({key: value for key, value in requested.items() if key != 'catalog_statistics'}, plain)
        self.assertEqual(requested['matched_count'], len(self.service.rows))

    def test_per_field_summary_reproduces_previous_inline_counts(self):
        ids = sorted(self.service.rows)
        inline = {field['id']: field for field in self.index.catalog(ids=ids, known_fields=self.index.catalog()['fields'])['fields']}
        checked = 0
        for field, statistics in inline.items():
            if field.startswith('joint/') or statistics['distinct_count'] > 60:
                continue
            response = self.client.post('/api/explore/summaries', json={'predicate': {'all': []}, 'summary_fields': [field]},
                                        headers=self.fixture.headers)
            self.assertEqual(response.status_code, 202, response.get_json())
            self.join()
            facet = self.jobs.poll(response.get_json()['request_id'])['result']['summaries'][field]
            with self.subTest(field=field):
                self.assertEqual(facet['missing_count'], statistics['missing_count'])
                self.assertEqual(facet['present_count'], statistics['count'] - statistics['missing_count'])
                self.assertEqual(len(facet['values']), statistics['distinct_count'])
                self.assertEqual(sum(item['count'] for item in facet['values'] if item['type'] == 'null'), statistics['null_count'])
            checked += 1
        self.assertGreater(checked, 3)


if __name__ == '__main__':
    unittest.main()
