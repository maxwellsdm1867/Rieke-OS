import contextlib
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import workspace_curation as curation
from workspace_recipes import capture_query, prepare_export, seal


class Table:
    """Small transactional relation double; no acquisition data or DB needed."""
    def __init__(self, keys, rows=None, restrictions=(), projected=None, read_log=None):
        self.keys = keys
        self.rows = [] if rows is None else rows
        self.restrictions = restrictions
        self.projected = projected
        self.read_log = [] if read_log is None else read_log

    def __and__(self, restriction):
        return Table(self.keys, self.rows, self.restrictions + (restriction,), self.projected, self.read_log)

    def proj(self, *fields):
        return Table(self.keys, self.rows, self.restrictions, set(self.keys) | set(fields), self.read_log)

    def to_dicts(self):
        self.read_log.append({"projected": self.projected, "restrictions": self.restrictions})
        def matches(row, restriction):
            if isinstance(restriction, list):
                return any(matches(row, item) for item in restriction)
            return all(row.get(key) == value for key, value in restriction.items())
        rows = [r for r in self.rows if all(matches(r, q) for q in self.restrictions)]
        return copy.deepcopy([{key: row[key] for key in self.projected} for row in rows]
                             if self.projected is not None else rows)

    def fetch(self, *, as_dict, order_by=None, limit=None, offset=0):
        rows = self.to_dicts()
        for clause in reversed((order_by or '').split(',')):
            if clause.strip():
                field, direction = clause.strip().split()
                rows.sort(key=lambda row: row[field], reverse=direction == 'DESC')
        return rows[offset:None if limit is None else offset + limit]

    def insert1(self, row):
        if any(all(row[k] == old[k] for k in self.keys) for old in self.rows):
            raise ValueError("Duplicate primary key")
        self.rows.append(copy.deepcopy(row))

    def update1(self, row):
        for old in self.rows:
            if all(row[k] == old[k] for k in self.keys):
                old.update(copy.deepcopy(row))
                return
        raise ValueError("Missing row")


class Connection:
    def __init__(self, tables):
        self.tables = tables
        self.queries = []

    def query(self, sql):
        self.queries.append(sql)
        return self

    def fetchone(self):
        return (1,)

    @property
    @contextlib.contextmanager
    def transaction(self):
        previous = [copy.deepcopy(table.rows) for table in self.tables]
        try:
            yield
        except Exception:
            for table, rows in zip(self.tables, previous):
                table.rows[:] = rows
            raise


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.project, self.protocol = str(uuid.uuid4()), str(uuid.uuid4())
        self.ids = [str(uuid.uuid4()) for _ in range(2)]
        self.fingerprints = {key: "b" * 64 for key in self.ids}
        self.curation = Table(("project_uuid", "protocol_uuid", "epoch_uuid"))
        self.datasets = Table(("project_uuid", "dataset_uuid"))
        self.events = Table(("event_uuid",))
        self.sources = Table(("source_sha256",))
        self.sources.insert1({"source_sha256": "a" * 64, "project_uuid": self.project})
        self.connection = Connection([self.curation, self.datasets, self.events, self.sources])
        class DJ:
            pass
        self.dj = DJ()
        self.dj.conn = lambda: self.connection
        with patch.object(curation, "workspace_tables", return_value=(None, self.sources, self.events, None)), \
             patch.object(curation, "curation_tables", return_value=(self.curation, self.datasets)):
            self.store = curation.CurationStore(self.dj, self.project)

    def update(self, changes, revisions=None, ids=None, fingerprints=None):
        ids = self.ids if ids is None else ids
        return self.store.update(self.protocol, ids, changes,
            revisions or {key: 0 for key in ids},
            fingerprints or {key: self.fingerprints[key] for key in ids}, "researcher")

    def test_defaults_do_not_write_or_approve(self):
        values = self.store.read(self.protocol, self.ids, self.fingerprints)
        self.assertEqual(len(values), 2)
        self.assertTrue(all(v["included"] and v["review_state"] == "unreviewed" and v["revision"] == 0
                            for v in values.values()))
        self.assertEqual(self.curation.rows, [])
        self.assertEqual(self.events.rows, [])

    def test_update_saves_current_state_and_rejects_stale_batch(self):
        result = self.update({"included": False, "tags_add": ["noisy"]})
        self.assertTrue(all(v["revision"] == 1 and v["tags"] == ["noisy"] for v in result["curation"].values()))
        self.assertEqual(self.events.rows, [])
        self.assertFalse(result["curation"][self.ids[0]]["included"])
        with self.assertRaises(curation.RevisionConflict) as error:
            self.update({"included": True}, {self.ids[0]: 1, self.ids[1]: 0})
        self.assertEqual(error.exception.current[self.ids[1]]["revision"], 1)
        self.assertEqual(len(self.events.rows), 0)
        self.assertTrue(all(not row["included"] for row in self.curation.rows))
        self.assertIn("RELEASE_LOCK", self.connection.queries[-1])

    def test_analysis_inclusion_roundtrip_retains_epochs_tags_and_review(self):
        first, second = self.ids
        self.update({"tags_add": ["inspect-later"], "review_state": "approved"}, ids=[first])
        self.update({"included": False}, revisions={first: 1}, ids=[first])
        state = self.store.read(self.protocol, self.ids, self.fingerprints)
        self.assertEqual(set(state), set(self.ids))
        self.assertFalse(state[first]["included"])
        self.assertTrue(state[second]["included"])
        self.assertEqual(state[first]["tags"], ["inspect-later"])
        self.assertEqual(state[first]["review_state"], "approved")
        self.update({"included": True}, revisions={first: 2}, ids=[first])
        restored = self.store.read(self.protocol, self.ids, self.fingerprints)
        self.assertTrue(restored[first]["included"])
        self.assertEqual(restored[first]["tags"], state[first]["tags"])
        self.assertEqual(restored[first]["review_state"], state[first]["review_state"])
        self.assertEqual(restored[second], state[second])

    def test_state_failure_rolls_back_curation(self):
        with patch.object(self.curation, "insert1", side_effect=RuntimeError("state unavailable")):
            with self.assertRaises(RuntimeError):
                self.update({"included": False})
        self.assertEqual(self.curation.rows, [])

    def test_fingerprint_change_requires_explicit_reapproval(self):
        self.update({"review_state": "approved"})
        changed = {key: "c" * 64 for key in self.ids}
        state = self.store.read(self.protocol, self.ids, changed)
        self.assertTrue(all(v["approval_stale"] and v["review_state"] == "unreviewed" for v in state.values()))
        self.assertTrue(all(row["review_state"] == "approved" for row in self.curation.rows))
        result = self.update({"tags_add": ["checked"]}, {key: 1 for key in self.ids}, fingerprints=changed)
        self.assertTrue(all(v["review_state"] == "unreviewed" for v in result["curation"].values()))
        self.update({"review_state": "approved"}, {key: 2 for key in self.ids}, fingerprints=changed)
        self.assertTrue(all(row["review_state"] == "approved" for row in self.curation.rows))

    def test_protocol_scope_is_independent(self):
        self.update({"included": False})
        other = self.store.read(str(uuid.uuid4()), self.ids, self.fingerprints)
        self.assertTrue(all(v["revision"] == 0 and v["included"] for v in other.values()))

    def test_rejects_ambiguous_changes_and_expectations(self):
        invalid = [{"included": 1}, {"tags": ["a"]}, {"tags_add": "a"},
                   {"review_state": "clean"}, {"review_state": []},
                   {"tags_add": [" a"]}, {"tags_add": ["a"], "tags_remove": ["a"]}, {}]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.update(change)
        with self.assertRaises(ValueError):
            self.update({"included": False}, {self.ids[0]: 0})
        self.assertEqual(self.events.rows, [])

    def recipe(self, included=None, approved=(), policy="include_unreviewed"):
        definition = {"format": "recording-protocol-workspace", "version": 1,
            "project_uuid": self.project, "protocol_uuid": self.protocol,
            "query": {"version": 1, "all": [{"field": "EpochBlock.protocol_name", "operator": "eq", "value": "example"}]}}
        result = {"project_uuid": self.project, "protocol_uuid": self.protocol,
            "epochs": [{"uuid": key, "metadata_hash": self.fingerprints[key]} for key in self.ids],
            "source_revisions": ["a" * 64]}
        snapshot = capture_query(definition, result, "../catalog.json")
        return prepare_export(snapshot, self.ids if included is None else included,
            destination="reference-json", review_policy=policy, approved_ids=approved,
            actor="researcher", options={"name": "Frozen sample"})

    def record(self, recipe, revisions=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reference.json"
            raw = json.dumps(recipe).encode()
            path.write_bytes(raw)
            return self.store.record_dataset_revision(recipe, actor="researcher",
                expected_revisions=revisions or {key: 0 for key in self.ids},
                artifact_path=path, artifact_sha256=hashlib.sha256(raw).hexdigest())

    def test_frozen_export_keeps_exact_filtered_members_and_query(self):
        recipe = self.recipe(included=self.ids[:1])
        result = self.record(recipe)
        self.assertEqual(result["epoch_count"], 1)
        saved = self.store.get_dataset_revision(result["dataset_uuid"])
        self.assertEqual(saved["recipe"], recipe)
        self.assertEqual(len(saved["recipe"]["query_snapshot"]["epochs"]), 2)
        self.assertEqual(self.events.rows[0]["action"], "dataset_revision_exported")
        listing = self.store.list_dataset_revisions(self.protocol)
        self.assertEqual(listing[0]["name"], "Frozen sample")
        self.assertEqual(listing[0]["status"], "completed")
        self.assertNotIn("recipe", listing[0])
        with self.assertRaises(ValueError):
            self.record(recipe)  # Immutable dataset identity.
        self.assertEqual(len(self.events.rows), 1)

    def test_export_detects_curation_race_and_false_approval(self):
        recipe = self.recipe()
        self.update({"included": False})
        with self.assertRaises(curation.RevisionConflict):
            self.record(recipe)
        self.assertEqual(self.datasets.rows, [])
        self.update({"included": True}, {key: 1 for key in self.ids})
        fake_approval = self.recipe(approved=self.ids, policy="approved_only")
        with self.assertRaises(ValueError):
            self.record(fake_approval, {key: 2 for key in self.ids})
        self.assertEqual(self.datasets.rows, [])

    def test_export_fingerprint_tamper_and_cross_project_source_rejected(self):
        recipe = self.recipe()
        recipe["epochs"][0]["metadata_hash"] = "d" * 64
        with self.assertRaises(ValueError):
            self.record(seal(recipe))
        self.sources.rows[0]["project_uuid"] = str(uuid.uuid4())
        with self.assertRaises(ValueError):
            self.record(self.recipe())
        self.assertEqual(self.datasets.rows, [])

    def test_dataset_event_failure_rolls_back_record(self):
        with patch.object(self.events, "insert1", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.record(self.recipe())
        self.assertEqual(self.datasets.rows, [])

    def test_atomic_mixed_inclusion_mask_preserves_other_fields(self):
        self.update({'review_state': 'approved', 'tags_add': ['reviewed']})
        mask = dict(zip(self.ids, [False, True]))
        result = self.store.update(self.protocol, self.ids, {}, {key: 1 for key in self.ids},
            self.fingerprints, 'researcher', inclusion_by_epoch=mask)
        self.assertEqual({key: value['included'] for key, value in result['curation'].items()}, mask)
        self.assertTrue(all(value['review_state'] == 'approved' and value['tags'] == ['reviewed']
                            for value in result['curation'].values()))
        self.assertEqual(self.events.rows, [])
        with patch.object(self.curation, 'update1', side_effect=RuntimeError('state unavailable')):
            with self.assertRaises(RuntimeError):
                self.store.update(self.protocol, self.ids, {}, {key: 2 for key in self.ids},
                    self.fingerprints, 'researcher', inclusion_by_epoch={key: True for key in self.ids})
        current = self.store.read(self.protocol, self.ids, self.fingerprints)
        self.assertEqual({key: value['included'] for key, value in current.items()}, mask)
        self.assertEqual(len(self.events.rows), 0)

    def test_mixed_mask_rejects_missing_extra_and_nonboolean_values(self):
        cases = [{self.ids[0]: True}, {**dict.fromkeys(self.ids, True), str(uuid.uuid4()): True},
                 dict.fromkeys(self.ids, 1), []]
        for mask in cases:
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                self.store.update(self.protocol, self.ids, {}, dict.fromkeys(self.ids, 0),
                    self.fingerprints, 'researcher', inclusion_by_epoch=mask)
        with self.assertRaises(ValueError):
            self.store.update(self.protocol, self.ids, {'included': True}, dict.fromkeys(self.ids, 0),
                self.fingerprints, 'researcher', inclusion_by_epoch=dict.fromkeys(self.ids, False))
        self.assertFalse(self.curation.rows)
        self.assertFalse(self.events.rows)

    def test_export_reverse_index_uses_only_frozen_members_and_project_scope(self):
        first = self.record(self.recipe(included=self.ids[:1]))
        links = self.store.epoch_exports(self.ids[0])
        self.assertEqual([link['dataset_uuid'] for link in links], [first['dataset_uuid']])
        self.assertEqual(links[0]['metadata_hash'], self.fingerprints[self.ids[0]])
        self.assertEqual(self.store.epoch_exports(self.ids[1]), [])  # In query snapshot, not export.
        full_reads = sum(item['projected'] is None for item in self.datasets.read_log)
        self.store.export_memberships()
        self.store.list_dataset_revisions()
        self.assertEqual(sum(item['projected'] is None for item in self.datasets.read_log), full_reads)
        self.assertTrue(all('recipe' not in item['projected'] for item in self.datasets.read_log if item['projected']))
        links[0]['name'] = 'caller mutation'
        self.assertNotEqual(self.store.epoch_exports(self.ids[0])[0]['name'], 'caller mutation')
        foreign = copy.deepcopy(self.datasets.rows[0])
        foreign['project_uuid'] = str(uuid.uuid4())
        foreign['dataset_uuid'] = str(uuid.uuid4())
        self.datasets.insert1(foreign)
        self.assertEqual(len(self.store.epoch_exports(self.ids[0])), 1)
        self.assertEqual(sum(item['projected'] is None for item in self.datasets.read_log), full_reads)
        previous_protocol = self.protocol
        self.protocol = str(uuid.uuid4())
        second = self.record(self.recipe())
        latest = self.store.epoch_exports(self.ids[0])
        self.assertEqual({link['dataset_uuid'] for link in latest}, {first['dataset_uuid'], second['dataset_uuid']})
        self.assertEqual({link['protocol_uuid'] for link in latest}, {previous_protocol, self.protocol})
        self.assertEqual([link['dataset_uuid'] for link in self.store.epoch_exports(self.ids[1])], [second['dataset_uuid']])
        self.assertEqual(len(self.store.list_dataset_revisions(self.protocol)), 1)
        self.assertGreater(sum(item['projected'] is None for item in self.datasets.read_log), full_reads)
        before = len(self.datasets.read_log)
        with self.assertRaises(ValueError):
            self.store.epoch_exports('not-an-epoch-id')
        self.assertEqual(len(self.datasets.read_log), before)

    def test_export_reverse_index_detects_changed_revision_signature(self):
        self.record(self.recipe(included=self.ids[:1]))
        self.store.export_memberships()
        self.datasets.rows[0]['artifact_sha256'] = 'c' * 64
        updated = self.store.epoch_exports(self.ids[0])
        self.assertEqual(updated[0]['artifact_sha256'], 'c' * 64)
        self.datasets.rows[0]['recipe']['epochs'][0]['metadata_hash'] = 'd' * 64
        self.datasets.rows[0]['artifact_sha256'] = 'd' * 64
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.store.export_memberships()

    def test_binding_change_between_http_check_and_store_lock_rejects_curation_and_export(self):
        # Models another app process switching the protocol pointer after the
        # HTTP query guard but before this writer acquires the DB advisory lock.
        self.store.binding_provider = lambda protocol: {'version': 2}
        with self.assertRaises(curation.RevisionConflict):
            self.store.update(self.protocol, self.ids, {'tags_add': ['stale selection']},
                dict.fromkeys(self.ids, 0), self.fingerprints, 'researcher', expected_binding_version=1)
        with self.assertRaises(curation.RevisionConflict):
            self.store.update(self.protocol, self.ids, {}, dict.fromkeys(self.ids, 0),
                self.fingerprints, 'researcher', inclusion_by_epoch=dict.fromkeys(self.ids, False),
                expected_binding_version=1)
        with self.assertRaises(curation.RevisionConflict):
            self.record(self.recipe())  # Snapshot had no binding: expected version zero.
        self.assertFalse(self.curation.rows)
        self.assertFalse(self.datasets.rows)
        self.assertFalse(self.events.rows)
        self.assertEqual(sum('GET_LOCK' in sql for sql in self.connection.queries), 3)
        self.assertEqual(sum('RELEASE_LOCK' in sql for sql in self.connection.queries), 3)


if __name__ == "__main__":
    unittest.main()
