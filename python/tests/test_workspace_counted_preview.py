"""Summary-only previews over a frozen publication are counted, not listed.

The count is one typed COUNT and the revision is the frozen publication
identity, so no IDs are collected and no membership is hashed. Published maps
refuse in-place mutation; a publish moves the revision. Unfrozen adapters keep
the exact membership hash.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

import test_workspace_explore_queries as explore_fixture
from disco.navigation.tree_pages import TreePages, StaleTreePage
from workspace_service import WorkspaceService, publish_frozen, publication_serial


class CountedPreviewTests(unittest.TestCase):
    join = explore_fixture.RequestedSummaryTests.join

    def setUp(self):
        from disco.metadata.disk_index import DiskMetadataIndex
        from disco.metadata.typed_lifecycle import prepare
        explore_fixture.RequestedSummaryTests.setUp(self)
        if type(self.service) is not WorkspaceService:
            self.service.__class__ = WorkspaceService
        path = Path(self.fixture.temp.name) / 'cache' / 'metadata' / ('c' * 64 + '.sqlite')
        self.index = DiskMetadataIndex.build(path, self.service.rows, self.service.details,
            self.service.sources, 'c' * 64, self.service.project['project_uuid'])
        self.service.disk_index, self.service.details = self.index, self.index.details
        self.service.typed_index, _ = prepare(self.index)
        self.publish()

    def publish(self, rows=None):
        service = self.service
        service.rows = publish_frozen(rows if rows is not None else service.rows, rows=True)
        service.cells, service.protocols, service._fingerprints = (publish_frozen(service.cells),
            publish_frozen(service.protocols), publish_frozen(service._fingerprints))
        self.assertIsNotNone(publication_serial(service))

    def preview(self, predicate, **body):
        response = self.client.post('/api/explore/preview', json={'predicate': predicate, 'splits': 'cell',
                                    'summary_only': True, 'catalog_summary': False, **body}, headers=self.fixture.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def predicates(self):
        cell = self.service.rows[self.service.ids[0]]['cell_uuid']
        return [{'all': []}, {'field': 'cell', 'operator': 'eq', 'value': cell},
                {'not': {'field': 'cell', 'operator': 'eq', 'value': cell}}]

    def test_counted_preview_collects_no_ids_and_matches_the_exact_path(self):
        from disco.metadata.typed_index import TypedMetadataIndex
        for predicate in self.predicates():
            with self.subTest(predicate=predicate):
                exact = self.preview(predicate, focused_uuid=self.service.ids[0])  # membership path
                with patch.object(TypedMetadataIndex, 'iter_membership', side_effect=AssertionError('collected IDs')), \
                     patch.object(WorkspaceService, 'match_predicate', side_effect=AssertionError('listed membership')):
                    counted = self.preview(predicate)
                for key in ('matched_count', 'total_source', 'tree_revision', 'tree', 'source_scope', 'predicate', 'catalog'):
                    self.assertEqual(counted[key], exact[key], key)
                page = TreePages(self.service).page({'predicate': predicate, 'splits': 'cell',
                                                     'revision': counted['tree_revision']})
                self.assertEqual(page['revision'], counted['tree_revision'])
                self.assertEqual(page['total_epochs'], counted['matched_count'])

    def test_excluded_sources_are_counted_by_source(self):
        excluded = self.service.rows[self.service.ids[0]]['source_sha256']
        with patch.object(self.service, 'source_state_provider',
                          lambda: {excluded: {'archived': False, 'query_excluded': True, 'version': 1}}):
            for predicate in self.predicates():
                with self.subTest(predicate=predicate):
                    exact = self.preview(predicate, focused_uuid=self.service.ids[0])
                    counted = self.preview(predicate)
                    self.assertEqual((counted['matched_count'], counted['total_source'], counted['tree_revision']),
                                     (exact['matched_count'], exact['total_source'], exact['tree_revision']))

    def test_published_maps_refuse_mutation_and_a_publish_moves_the_revision(self):
        predicate = {'all': []}
        before = self.preview(predicate)
        root = TreePages(self.service).page({'predicate': predicate, 'splits': 'cell'})
        self.assertEqual(root['revision'], before['tree_revision'])
        with self.assertRaises(TypeError):
            self.service._fingerprints[self.service.ids[0]] = 'c' * 64
        with self.assertRaises(TypeError):
            self.service.rows[self.service.ids[0]]['date'] = '2000-01-01'
        self.assertEqual(self.preview(predicate)['tree_revision'], before['tree_revision'])
        changed = {**self.service.rows}
        self.publish(changed)
        after = self.preview(predicate)
        self.assertNotEqual(after['tree_revision'], before['tree_revision'])
        with self.assertRaises(StaleTreePage):
            TreePages(self.service).page({'predicate': predicate, 'splits': 'cell', 'path': root['branches'][0]['path'],
                                          'revision': before['tree_revision']})

    def test_unfrozen_adapter_keeps_the_membership_hash(self):
        self.service.rows = dict(self.service.rows)
        self.assertIsNone(publication_serial(self.service))
        self.assertIsNone(self.service._counted_preview({'all': []}, 'cell'))
        result = self.preview({'all': []})
        exact = self.preview({'all': []}, focused_uuid=self.service.ids[0])
        self.assertEqual(result['tree_revision'], exact['tree_revision'])
        self.assertEqual(result['matched_count'], len(self.service.rows))


if __name__ == '__main__':
    unittest.main()
