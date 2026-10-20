"""Cold tag queries reuse exact metadata witnesses prepared at publication."""
import unittest
from unittest.mock import patch
import test_workspace_query_run as query_fixture
from disco.navigation.tag_predicates import _Publication, prepare_publication, TagPredicates
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
                with patch.object(_Publication, 'cell_links', side_effect=AssertionError('rehash')):
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
        prepare_publication(self.service)
        self.case.jobs.autostart = False
        predicate = {'any': [{'field': f'curation/{self.service.protocol_id}/tags', 'operator': 'contains', 'value': 'unused'},
                             {'field': 'parameters/example', 'operator': 'eq', 'value': 1}]}
        with patch.object(_Publication, 'cell_links', side_effect=AssertionError('hashed whole publication')), \
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
