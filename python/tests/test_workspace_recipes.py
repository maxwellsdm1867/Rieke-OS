import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from workspace_recipes import (build_tree, capture_query, compare_query,
                               prepare_export, save_snapshot, verify)


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.ids = [str(uuid.uuid4()) for _ in range(3)]
        self.definition = {"format": "recording-protocol-workspace", "version": 1,
            "project_uuid": str(uuid.uuid4()), "protocol_uuid": str(uuid.uuid4()),
            "query": {"version": 1, "all": [{"field": "EpochBlock.protocol_name",
                "operator": "eq", "value": "example.VMN"}]},
            "view": {"group_by": ["date", "block"]}}
        self.result = {k: self.definition[k] for k in ("project_uuid", "protocol_uuid")}
        self.result.update(source_revisions=["a" * 64], epochs=[
            {"uuid": i, "metadata_hash": "b" * 64} for i in self.ids[:2]])
        self.snapshot = capture_query(self.definition, self.result, "../catalog.json")

    def test_refresh_diff_does_not_change_export(self):
        export = prepare_export(self.snapshot, self.ids[:2], destination="MAT", actor="test",
                                review_policy="approved_only", approved_ids=[self.ids[0]])
        original = copy.deepcopy(export)
        self.result["epochs"] = [{"uuid": self.ids[0], "metadata_hash": "c" * 64},
                                 {"uuid": self.ids[2], "metadata_hash": "b" * 64}]
        current = capture_query(self.definition, self.result, "../catalog.json")
        self.assertEqual(compare_query(self.snapshot, current),
                         {"added": [self.ids[2]], "removed": [self.ids[1]], "changed": [self.ids[0]]})
        self.assertEqual(export, original)
        self.assertEqual(export["selection"]["held_by_review"], [self.ids[1]])
        self.assertEqual(len(export["epochs"]), 1)
        self.assertEqual(export["query"], self.definition["query"])

    def test_invalid_scope_and_unreviewed_export_fail_closed(self):
        for ids, policy in [([self.ids[2]], "include_unreviewed"),
                            ([self.ids[0]] * 2, "include_unreviewed"),
                            ([self.ids[0]], "approved_only"), ([self.ids[0]], "typo")]:
            with self.subTest(ids=ids, policy=policy), self.assertRaises(ValueError):
                prepare_export(self.snapshot, ids, destination="MAT", actor="test", review_policy=policy)
        tampered = copy.deepcopy(self.snapshot)
        tampered["query"]["all"][0]["value"] = "different.Protocol"
        with self.assertRaisesRegex(ValueError, "checksum"):
            verify(tampered)
        mismatched = copy.deepcopy(self.result)
        mismatched["project_uuid"] = str(uuid.uuid4())
        with self.assertRaises(ValueError):
            capture_query(self.definition, mismatched, "../catalog.json")

    def test_existing_revision_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "revision.json"
            save_snapshot(path, self.snapshot)
            with self.assertRaises(FileExistsError):
                save_snapshot(path, self.snapshot)
            self.assertEqual(json.loads(path.read_text()), self.snapshot)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_tree_reordering_preserves_all_members_including_missing_values(self):
        rows = [{"epoch_uuid": identity, "start_time": "2026-09-24T12:00:00",
                 "cell_uuid": "cell-a", "block_uuid": None if n == 0 else "block-b"}
                for n, identity in enumerate(self.ids)]
        def leaves(node):
            return node.get("epoch_uuids", []) + [identity for child in node.get("children", [])
                                                  for identity in leaves(child)]
        for fields in ("date, cell, block", "block → date", ""):
            tree = build_tree(rows, fields)
            self.assertEqual(sorted(leaves(tree)), sorted(self.ids))
            self.assertEqual(tree["count"], 3)
        with self.assertRaises(ValueError):
            build_tree(rows, "date, unknown field")
        with self.assertRaises(ValueError):
            build_tree(rows + rows[:1], "cell")
        rows[0]["start_time"] = "09/24/2026 15:34:37:735822"
        self.assertEqual(len(build_tree(rows, "date")["children"]), 1)
        rows[0]["start_time"] = "unknown-date"
        with self.assertRaisesRegex(ValueError, "recording date"):
            build_tree(rows, "date")


if __name__ == "__main__":
    unittest.main()
