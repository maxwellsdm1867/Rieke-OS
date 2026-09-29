"""Deterministic large-catalog checks, without timing thresholds or SQL writes."""
import unittest
from types import SimpleNamespace
from workspace_api import summarize_cell_membership
from workspace_curation import CurationStore


class CellSummaryScaleTests(unittest.TestCase):
    def test_large_curation_scope_uses_one_project_protocol_restriction(self):
        restrictions = []
        class SparseRelation:
            def __and__(self, restriction):
                restrictions.append(restriction)
                return self
            def to_dicts(self):
                return [{'epoch_uuid': 7}, {'epoch_uuid': 50001}]
        store = SimpleNamespace(Curation=SparseRelation(), project_uuid='project')
        result = CurationStore._rows(store, 'protocol', list(range(50000)))
        self.assertEqual(result, {7: {'epoch_uuid': 7}})
        self.assertEqual(restrictions, [{'project_uuid': 'project', 'protocol_uuid': 'protocol'}])

    def test_fifty_thousand_epochs_are_counted_in_one_pass(self):
        count = 50000
        class OnePassRows:
            visits = 0
            iterations = 0
            def __iter__(self):
                self.iterations += 1
                if self.iterations != 1:
                    raise AssertionError('Catalog scanned again')
                for index in range(count):
                    self.visits += 1
                    yield {'epoch_uuid': index, 'cell_uuid': index // 50}
        rows = OnePassRows()
        approved = set(range(0, count, 2))
        exported = set(range(0, count, 5))
        included = set(range(count)) - {0}
        result = summarize_cell_membership(rows, approved, exported, included)
        self.assertEqual((rows.iterations, rows.visits), (1, count))
        self.assertEqual(len(result), 1000)
        self.assertEqual(result[0], {'reviewed': 25, 'unreviewed': 25, 'exported': 10, 'included': 49})
        self.assertEqual(sum(row['reviewed'] for row in result.values()), 25000)
        self.assertEqual(sum(row['exported'] for row in result.values()), 10000)


if __name__ == '__main__':
    unittest.main()
