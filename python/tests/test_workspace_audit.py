import copy
import datetime as dt
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import workspace_audit as audit


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.project, self.protocol = str(uuid.uuid4()), str(uuid.uuid4())

    def event(self, action="query_refreshed", day=1, **payload):
        return {"event_uuid": str(uuid.uuid4()), "project_uuid": self.project,
                "occurred_at": f"2026-09-{day:02}T12:00:00+00:00", "actor": "scientist",
                "action": action, "payload": {"protocol_uuid": self.protocol, **payload}}

    def test_tag_activity_attributes_changes_to_profiles_not_os_actor(self):
        rows=[{'profile_uuid':'alice','author_name':'Alice','target_kind':'epoch','target_uuid':key,'tags':['old']} for key in ['one','two']]
        after=[{**row,'tags':['new']} for row in rows]
        after.append({'profile_uuid':'bob','author_name':'Bob','target_kind':'cell','target_uuid':'cell','tags':['new']})
        event=self.event(action='shared_annotations_updated',before=rows,after=after)
        snapshot=copy.deepcopy(event)
        summary=audit.normalize_event(event)['tag_activity']
        self.assertEqual([author['name'] for author in summary['authors']],['Alice','Bob'])
        self.assertEqual([(row['author'],row['operation'],row['tag'],row['targets']) for row in summary['changes']],
                         [('Alice','added','new',2),('Alice','removed','old',2),('Bob','added','new',1)])
        self.assertEqual(event,snapshot)
        missing=audit.normalize_event(self.event(action='shared_annotations_updated',before=[],after=[{'target_uuid':'one','tags':['x']}]))
        self.assertEqual(missing['tag_activity']['authors'][0]['name'],'Author not recorded')
        self.assertNotIn('tag_activity',audit.normalize_event(self.event()))

    def test_envelope_preserves_scientific_evidence_and_operation_identity(self):
        operation = str(uuid.uuid4())
        old = {"protocol_uuid": self.protocol, "before": {"included": True}, "after": {"included": False}}
        payload = audit.build_audit_payload("curation_updated", "scientist", old,
            operation_uuid=operation, inputs={"epoch_uuids": [str(uuid.uuid4())]},
            context={"project_uuid": self.project}, source_files={},
            parser_manifest={"parser_sha256": "a" * 64, "adapter_version": 1, "password": "do-not-copy"})
        self.assertEqual(payload["before"], old["before"])
        self.assertEqual(payload["after"], old["after"])
        self.assertNotIn("audit", old)
        envelope = payload["audit"]
        self.assertEqual(envelope["operation_uuid"], operation)
        self.assertEqual(envelope["provenance"]["contracts"]["audit_payload"], 1)
        self.assertEqual(envelope["provenance"]["parser"]["parser_sha256"], "a" * 64)
        self.assertNotIn("password", envelope["provenance"]["parser"])
        self.assertFalse(envelope["actor"]["authenticated_identity"])
        self.assertEqual(envelope["actor"]["attribution"], "server_os_user")

    def test_redacts_nested_credentials_without_losing_hashes(self):
        payload = audit.build_audit_payload("query_refreshed", "scientist", {
            "config": {"database.password": "super-secret", "connection": {"host": "localhost", "password": "secret"}},
            "error": "mysql://user:secret@host/db password=hidden",
            "metadata_fingerprint": "a" * 64}, source_files={})
        self.assertEqual(payload["config"]["database.password"], "[redacted]")
        self.assertEqual(payload["config"]["connection"], "[redacted]")
        self.assertNotIn("user:secret", payload["error"])
        self.assertNotIn("hidden", payload["error"])
        self.assertEqual(payload["metadata_fingerprint"], "a" * 64)

    def test_paged_metadata_implementation_is_in_new_audit_provenance(self):
        paths = {'python/workspace_candidate_exports.py', 'workspace-app/src/components/CandidateExportPanel.jsx',
                 'workspace-app/src/exportReuse.js', 'python/workspace_disk_index.py', 'python/workspace_projection_cache.py',
                 'python/workspace_tree_pages.py', 'workspace-app/src/components/PagedTree.jsx'}
        self.assertTrue(paths <= set(audit.SOURCE_FILES))
        receipt = audit.build_audit_payload('explorer_revision_created', 'fixture', {})
        fingerprints = receipt['audit']['provenance']['code']
        for path in paths:
            self.assertEqual(fingerprints[path]['status'], 'recorded')
            self.assertEqual(len(fingerprints[path]['sha256']), 64)
        contracts = receipt['audit']['provenance']['contracts']
        self.assertEqual(contracts['tree_page'], 1)
        self.assertEqual(contracts['metadata_disk_index'], 1)
        self.assertEqual(contracts['source_projection_cache'], 1)
        self.assertEqual(contracts['query_snapshot'], 1)
        self.assertEqual(contracts['export_recipe'], 1)

    def test_code_hash_is_cached_and_invalidated_on_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "worker.py"
            path.write_text("first")
            audit._cached_digest.cache_clear()
            with patch.object(hashlib, "file_digest", wraps=hashlib.file_digest) as digest:
                first = audit.code_fingerprints({"worker": path})
                self.assertEqual(first, audit.code_fingerprints({"worker": path}))
                self.assertEqual(digest.call_count, 1)
                path.write_text("different version")
                second = audit.code_fingerprints({"worker": path})
                self.assertNotEqual(first["worker"]["sha256"], second["worker"]["sha256"])
                self.assertEqual(digest.call_count, 2)
            missing = audit.code_fingerprints({"gone": Path(temp) / "gone.py"})
            self.assertEqual(missing["gone"], {"status": "missing"})
            with self.assertRaises(ValueError):
                audit.code_fingerprints({"config": Path(temp) / "config.json"})

    def test_normalization_never_backfills_legacy_provenance(self):
        row = self.event(epoch_count=4)
        original = copy.deepcopy(row)
        normalized = audit.normalize_event(row)
        self.assertEqual(row, original)
        self.assertEqual(normalized["payload"], row["payload"])
        self.assertEqual(normalized["provenance"], {})
        self.assertEqual(normalized["audit_summary"], {"versioned": False, "outcome": "completed",
            "operation_uuid": None, "protocol_uuid": self.protocol, "entity_count": 4})
        row["payload"] = audit.build_audit_payload(row["action"], row["actor"], row["payload"], source_files={})
        newer = audit.normalize_event(row)
        self.assertTrue(newer["audit_summary"]["versioned"])
        self.assertEqual(newer["provenance"]["parser"]["status"], "not_recorded")

    def test_registration_fields_are_not_counted_as_changed_epochs(self):
        row = self.event('data_store_archived')
        row['payload'] = {'after': {'version': 1, 'archived': True, 'frozen': False}}
        self.assertIsNone(audit.normalize_event(row)['audit_summary']['entity_count'])
        row['action'] = 'curation_updated'
        row['payload'] = {'after': {'epoch-a': {'tags': []}, 'epoch-b': {'tags': []}}}
        self.assertEqual(audit.normalize_event(row)['audit_summary']['entity_count'], 2)

    def test_suggestions_require_unique_successful_events_in_same_scope(self):
        first, second = self.event(day=1), self.event(day=2)
        failed = self.event(day=3)
        failed["payload"] = audit.build_audit_payload(failed["action"], "scientist", failed["payload"],
                                                     outcome="failed", source_files={})
        other = self.event(day=4)
        other["project_uuid"] = str(uuid.uuid4())
        rows = [first, second, first, failed, other, self.event("curation_updated")]
        suggestions = audit.repeat_suggestions(rows)
        self.assertEqual(len(suggestions), 1)
        item = suggestions[0]
        self.assertEqual(item["count"], 2)
        self.assertEqual(item["source_event_uuid"], second["event_uuid"])
        self.assertEqual(set(item["source_event_uuids"]), {first["event_uuid"], second["event_uuid"]})
        self.assertEqual(item["intent"], "open_refresh_review")
        self.assertFalse(item["automatic"])
        self.assertEqual(audit.repeat_suggestions([first, first]), [])

    def test_export_suggestions_point_to_existing_revision_and_open_review(self):
        first = self.event("dataset_revision_exported", dataset_uuid=str(uuid.uuid4()))
        second = self.event("dataset_revision_exported", day=2, dataset_uuid=str(uuid.uuid4()))
        missing_revision = self.event("dataset_revision_exported", day=3)
        suggestion = audit.repeat_suggestions([first, second, missing_revision])[0]
        self.assertEqual(suggestion["dataset_uuid"], second["payload"]["dataset_uuid"])
        self.assertEqual(suggestion["intent"], "open_export_review")
        self.assertEqual(suggestion["count"], 2)

    def test_unknown_envelope_does_not_create_success_and_sql_time_is_utc(self):
        row = self.event()
        row["occurred_at"] = dt.datetime(2026, 9, 27, 10, 0)
        row["payload"]["audit"] = {"format": "recording-action-audit", "version": 99, "outcome": "failed"}
        normalized = audit.normalize_event(row)
        self.assertEqual(normalized["audit_summary"]["outcome"], "unknown")
        self.assertEqual(normalized["occurred_at"], "2026-09-27T10:00:00+00:00")
        self.assertEqual(normalized["provenance"], {})

    def test_bad_evidence_rejected_and_legacy_unknowns_not_promoted(self):
        with self.assertRaises(ValueError):
            audit.build_audit_payload("query_refreshed", "scientist", {"x": float("nan")}, source_files={})
        with self.assertRaises(ValueError):
            audit.build_audit_payload("query_refreshed", "scientist", {}, operation_uuid="bad", source_files={})
        with self.assertRaises(ValueError):
            audit.build_audit_payload("query_refreshed", "scientist", {"audit": {}}, source_files={})
        self.assertEqual(audit.normalize_event(self.event("some_unknown_action"))["audit_summary"]["outcome"], "unknown")
        self.assertEqual(audit.repeat_suggestions([self.event("curation_updated"), self.event("curation_updated")]), [])


if __name__ == "__main__":
    unittest.main()
