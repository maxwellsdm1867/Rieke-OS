"""Cold tag queries reuse exact metadata witnesses prepared at publication."""
import unittest
from unittest.mock import patch
import test_workspace_query_run as query_fixture
from disco.navigation.tag_predicates import prepare_publication, TagPredicates
from disco.workbench.recipes import checksum
from workspace_service import WorkspaceService, publish_frozen


class PredicatePublicationTests(unittest.TestCase):
    def setUp(self):
        self.case = query_fixture.QueryRunTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.service = self.case.service

    def test_prepared_witness_matches_canonical_evidence_and_reuses_only_same_maps(self):
        prepared = prepare_publication(self.service)
        for revision, fields in [('shared-1', ['annotations/epoch/tags']),
                                 ('non-ascii-é', ['annotations/epoch/tags'])]:
            expected = checksum({'protocols': [], 'shared_revision': revision,
                                 'shared_fields': fields, 'registered_cell_links': prepared.cell_links()})
            if revision == 'shared-1':
                with patch.object(prepared, 'cell_links', side_effect=AssertionError('rehash')):
                    self.assertEqual(prepared.shared_revision([], revision, fields), expected)
            else:
                self.assertEqual(prepared.shared_revision([], revision, fields), expected)
        self.assertEqual(prepared.universe(), checksum(sorted(self.service._fingerprints)))
        self.assertIs(prepare_publication(self.service), prepared)
        self.service.protocols = publish_frozen(dict(self.service.protocols))
        self.assertIs(prepare_publication(self.service), prepared)
        original_rows = prepared.rows
        self.service.rows = publish_frozen(dict(original_rows), rows=True)
        replaced = prepare_publication(self.service)
        self.assertIsNot(replaced, prepared)
        self.assertIs(prepared.rows, original_rows)

    def test_cold_mixed_run_does_not_rehash_metadata_or_enumerate_eligible_rows(self):
        prepared = prepare_publication(self.service)
        self.case.jobs.autostart = False
        predicate = {'any': [{'field': f'curation/{self.service.protocol_id}/tags', 'operator': 'contains', 'value': 'unused'},
                             {'field': 'parameters/example', 'operator': 'eq', 'value': 1}]}
        with patch.object(prepared, 'cell_links', side_effect=AssertionError('hashed whole publication')), \
                patch.object(WorkspaceService, '_eligible', side_effect=AssertionError('enumerated eligible rows')):
            result = self.case.run_query(predicate)
        self.assertEqual(result['total_source'], len(self.service.rows))
        self.assertEqual(result['counts']['status'], 'pending')

    def test_source_cardinality_honors_exclusions_without_row_walk(self):
        prepared = prepare_publication(self.service)
        sources = list(prepared.source_counts)
        for active in (sources, sources[:1], []):
            scope = {'active_source_revisions': active,
                     'excluded_source_revisions': [key for key in sources if key not in active]}
            expected = sum(row['source_sha256'] in active for row in self.service.rows.values())
            with patch.object(WorkspaceService, '_eligible', side_effect=AssertionError('enumerated eligible rows')):
                self.assertEqual(self.service._eligible_total(scope), expected)

    def test_mutable_publication_keeps_fallback(self):
        self.service.rows = dict(self.service.rows)
        self.assertIsNone(prepare_publication(self.service))
        scope = self.service.source_scope()
        with patch.object(WorkspaceService, '_eligible', return_value=((), ('one',), scope, frozenset())) as fallback:
            self.assertEqual(self.service._eligible_total(scope), 1)
        fallback.assert_called_once_with(scope)

    def test_cold_mixed_pages_seek_index_without_project_sort_and_scope_cells(self):
        from disco.metadata.typed_index import TypedMetadataIndex
        prepare_publication(self.service)
        self.case.jobs.autostart = False
        predicate = self.case.tag_predicates()[-1]
        run = self.case.run_query(predicate)
        body = {'predicate': predicate, 'splits': 'cell', 'revision': run['tree_revision'],
                'limit': 3, 'include_cells': True}
        seeks = []
        original = TypedMetadataIndex.chronology_page

        def observed(reader, *args, **kwargs):
            seeks.append(kwargs)
            return original(reader, *args, **kwargs)

        def page(request):
            with patch.object(WorkspaceService, '_eligible', side_effect=AssertionError('enumerated project')), \
                    patch.object(WorkspaceService, '_chronology_ids', side_effect=AssertionError('sorted project')), \
                    patch.object(TypedMetadataIndex, 'chronology_page', observed):
                return self.case.page(request)

        first = page(body)
        second = page({**body, 'offset': 3})
        self.assertTrue(seeks)
        self.assertTrue(all(call['after_rank'] is not None and call['limit'] <= 8192 for call in seeks))
        self.assertGreater(seeks[-1]['after_rank'], 0, 'next page must seek after the prior match')
        cell = first['epochs'][0]['cell_uuid']
        seeks.clear()
        cell_body = {**body, 'cell_uuid': cell}
        cell_page = page(cell_body)
        self.assertTrue(seeks)
        self.assertTrue(all(call['scope'] == {'cell': cell} for call in seeks))
        anchor_body = {**body, 'anchor_uuid': second['epochs'][-1]['epoch_uuid']}
        anchor_page = page(anchor_body)
        for request, actual in ((body, first), ({**body, 'offset': 3}, second),
                                (cell_body, cell_page), (anchor_body, anchor_page)):
            expected = self.case.page(request, exact=True)
            self.assertEqual(actual['counts']['status'], 'pending')
            for key in ('epochs', 'has_more', 'offset', 'anchor_index'):
                self.assertEqual(actual[key], expected[key], key)
        self.case.jobs.drive_worker()
        ready = self.case.page(body)
        ready.pop('counts')
        self.assertEqual(ready, self.case.page(body, exact=True))

    def test_mixed_index_windows_preserve_source_exclusions(self):
        prepare_publication(self.service)
        self.case.jobs.autostart = False
        predicate = self.case.tag_predicates()[-1]
        excluded = self.service.sources[0]['source_sha256']
        self.service.source_state_provider = lambda: {excluded: {'query_excluded': True, 'version': 1}}
        run = self.case.run_query(predicate)
        body = {'predicate': predicate, 'splits': 'cell', 'revision': run['tree_revision'],
                'limit': 3, 'include_cells': True}
        with patch.object(WorkspaceService, '_chronology_ids', side_effect=AssertionError('sorted project')):
            actual = self.case.page(body)
        expected = self.case.page(body, exact=True)
        self.assertEqual((actual['epochs'], actual['has_more']), (expected['epochs'], expected['has_more']))
        self.assertTrue(all(row['source_sha256'] != excluded for row in actual['epochs']))

    def test_mixed_index_windows_refuse_anchor_outside_result(self):
        import uuid
        prepare_publication(self.service)
        self.case.jobs.autostart = False
        predicate = self.case.tag_predicates()[-1]
        run = self.case.run_query(predicate)
        body = {'predicate': predicate, 'splits': 'cell', 'revision': run['tree_revision'],
                'limit': 3, 'anchor_uuid': str(uuid.uuid4())}
        with patch.object(WorkspaceService, '_chronology_ids', side_effect=AssertionError('sorted project')):
            response = self.case.post('/api/explore/epochs', body, status=400)
        self.assertIn('outside', response['error'])
