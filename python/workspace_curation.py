"""Versioned, project-scoped curation and immutable reference-export records.

Only bookkeeping tables in recording_workspace are written. Acquisition tables
and raw H5 files are never modified. Reads expose stale approvals as unreviewed;
explicit approval is required for the current metadata fingerprint.
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import time
from pathlib import Path
import uuid

from recording_workspace import workspace_tables
from workspace_recipes import member_map, verify
from workspace_audit import build_audit_payload


class RevisionConflict(ValueError):
    """The submitted revision no longer matches persisted curation."""

    def __init__(self, current):
        super().__init__("Curation changed; reload before saving or exporting")
        self.current = current


def curation_tables(dj):
    schema = dj.Schema("recording_workspace")

    @schema
    class Curation(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        protocol_uuid: varchar(36)
        epoch_uuid: varchar(36)
        ---
        included: bool
        tags: json
        review_state: enum('unreviewed', 'approved')
        revision: int unsigned
        metadata_fingerprint: char(64)
        """

    @schema
    class DatasetRevision(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        dataset_uuid: varchar(36)
        ---
        protocol_uuid: varchar(36)
        created_at: datetime
        actor: varchar(255)
        recipe: json
        artifact_path: varchar(2048)
        artifact_sha256: char(64)
        epoch_count: int unsigned
        """

    return Curation, DatasetRevision


def _uuid(value):
    return str(uuid.UUID(str(value)))


def _fingerprint(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Expected a lowercase SHA256 metadata fingerprint")
    return value


def _scope(epoch_ids, fingerprints):
    ids = [_uuid(value) for value in epoch_ids]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate epoch identity")
    if not isinstance(fingerprints, dict) or set(fingerprints) != set(ids):
        raise ValueError("Fingerprints must cover exactly the requested epochs")
    return ids, {key: _fingerprint(fingerprints[key]) for key in ids}


def _actor(actor):
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 255:
        raise ValueError("An actor of 1–255 characters is required")
    return actor


def _changes(changes):
    if not isinstance(changes, dict) or not changes or set(changes) - {
            "included", "tags_add", "tags_remove", "review_state"}:
        raise ValueError("Use included, tags_add, tags_remove, or review_state changes")
    if "included" in changes and type(changes["included"]) is not bool:
        raise ValueError("included must be a Boolean")
    if "review_state" in changes and (not isinstance(changes["review_state"], str) or
            changes["review_state"] not in {"unreviewed", "approved"}):
        raise ValueError("review_state must be unreviewed or approved")
    for key in ("tags_add", "tags_remove"):
        if key not in changes:
            continue
        tags = changes[key]
        if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() or
                tag != tag.strip() or len(tag) > 255 for tag in tags):
            raise ValueError("Tags must be a list of nonempty trimmed strings up to 255 characters")
        if len(set(tags)) != len(tags):
            raise ValueError("Duplicate tags are not allowed")
    if set(changes.get("tags_add", [])) & set(changes.get("tags_remove", [])):
        raise ValueError("A tag cannot be added and removed in the same change")
    return changes


def _expectations(ids, expected):
    if not isinstance(expected, dict) or set(expected) != set(ids) or any(
            type(value) is not int or value < 0 for value in expected.values()):
        raise ValueError("Expected revisions must cover exactly every epoch with a nonnegative integer")


class CurationStore:
    def __init__(self, dj, project_uuid):
        self.dj = dj
        self.project_uuid = _uuid(project_uuid)
        _, self.Source, self.Event, _ = workspace_tables(dj)
        self.Curation, self.DatasetRevision = curation_tables(dj)

    def tag_suggestions(self, query='', limit=30):
        """Current saved project vocabulary; no epoch metadata or event scans.

        Tag identity remains case-sensitive. Searching ignores case, and counts
        represent distinct source epochs, even if saved in several protocols.
        Removed tags found only in historical audit payloads are not included.
        Cache lifetime is two seconds; successful local tag writes invalidate it.
        """
        if not isinstance(query, str) or len(query) > 255:
            raise ValueError('Tag prefix must be text of at most 255 characters')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Tag suggestion limit must be an integer from 1 to 100')
        query = query.strip()
        prefix = query.casefold()
        tracker=getattr(self,'recovery_tracker',None)
        if tracker is not None and tracker.ready and tracker.token() is not None:
            from workspace_curation_vocabulary import CurationVocabulary
            index=getattr(self,'_curation_vocabulary_index',None)
            if index is None or index.tracker is not tracker:
                if index is not None:index.close()
                index=self._curation_vocabulary_index=CurationVocabulary(self,tracker)
            indexed=index.suggestions(query,limit)
            if indexed is not None:return indexed
        cached = getattr(self, '_tag_vocabulary', None)
        if cached is None or cached[0] != self.project_uuid or time.monotonic() >= cached[1]:
            rows = (self.Curation & {'project_uuid': self.project_uuid}).proj('tags').to_dicts()
            membership = {}
            for row in rows:
                tags = row['tags']
                if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip()
                        or tag != tag.strip() or len(tag) > 255 for tag in tags):
                    raise ValueError('Saved tag vocabulary contains an invalid tag record')
                for tag in set(tags):
                    membership.setdefault(tag, set()).add(row['epoch_uuid'])
            # Store compact immutable pairs, not epoch sets or database rows.
            vocabulary = tuple(sorted(((tag,len(epochs)) for tag,epochs in membership.items()),
                                      key=lambda item:(-item[1],item[0].casefold(),item[0])))
            cached = self._tag_vocabulary = (self.project_uuid,time.monotonic()+2.,vocabulary)
        tags = [{'tag':tag,'count':count} for tag,count in cached[2] if tag.casefold().startswith(prefix)]
        return {'tags':tags[:limit], 'q':query, 'limit':limit, 'total':len(tags),
                'has_more':len(tags)>limit, 'project_uuid':self.project_uuid,
                'scope':'project_saved_curation', 'count_unit':'distinct_epochs',
                'match':'case_insensitive_prefix', 'history_included':False}

    def _rows(self, protocol_uuid, ids, *, selected_only=False):
        if not ids:
            return {}
        relation = self.Curation & {"project_uuid": self.project_uuid,
                                    "protocol_uuid": protocol_uuid}
        if len(ids) <= 250 or selected_only:
            rows = {}
            for start in range(0,len(ids),250):
                selected = (relation & [{"epoch_uuid": key} for key in ids[start:start+250]]).to_dicts()
                rows.update((row['epoch_uuid'],row) for row in selected)
            return rows
        # Full protocol summaries commonly request tens of thousands of epochs.
        # Fetch the sparse saved decisions through the project/protocol key once,
        # instead of emitting an enormous OR expression for every epoch UUID.
        saved = relation.to_dicts()
        if not saved:
            return {}
        allowed = set(ids)
        return {row['epoch_uuid']: row for row in saved if row['epoch_uuid'] in allowed}

    @staticmethod
    def _state(row, fingerprint):
        if row is None:
            return {"included": True, "tags": [], "review_state": "unreviewed",
                    "revision": 0, "metadata_fingerprint": fingerprint,
                    "approval_stale": False}
        stale = row["metadata_fingerprint"] != fingerprint
        return {"included": bool(row["included"]), "tags": list(row["tags"]),
                "review_state": "unreviewed" if stale else row["review_state"],
                "revision": int(row["revision"]), "metadata_fingerprint": fingerprint,
                "approval_stale": stale and row["review_state"] == "approved"}

    def read(self, protocol_uuid, epoch_ids, fingerprints):
        protocol_uuid = _uuid(protocol_uuid)
        ids, fingerprints = _scope(epoch_ids, fingerprints)
        rows = self._rows(protocol_uuid, ids)
        return {key: self._state(rows.get(key), fingerprints[key]) for key in ids}

    def summary_decisions(self, protocol_uuid, epoch_ids, fingerprints):
        """Only decisions that differ from default summary counts; no tag JSON.

        The caller supplies already verified protocol membership. Approval is
        counted only against its exact current metadata fingerprint.
        """
        protocol_uuid=_uuid(protocol_uuid)
        allowed=set(epoch_ids)
        rows=(self.Curation & {'project_uuid':self.project_uuid,'protocol_uuid':protocol_uuid}
            & [{'included':False},{'review_state':'approved'}]).proj('included','review_state','metadata_fingerprint').to_dicts()
        excluded,approved=set(),set()
        for row in rows:
            key=row['epoch_uuid']
            if key not in allowed:continue
            if not row['included']:excluded.add(key)
            if row['review_state']=='approved' and row['metadata_fingerprint']==fingerprints[key]:approved.add(key)
        return excluded,approved

    @contextlib.contextmanager
    def _transaction(self, protocol_uuid):
        # Serialize our read/check/write sequence, including concurrent first
        # inserts. Lock names are generated hex, never interpolated user input.
        connection = self.dj.conn()
        lock = hashlib.sha256((self.project_uuid + protocol_uuid).encode()).hexdigest()
        acquired = connection.query(f"SELECT GET_LOCK('{lock}', 10)").fetchone()[0]
        if acquired != 1:
            raise RuntimeError("Another curation write is running; retry shortly")
        try:
            with connection.transaction:
                yield
        finally:
            with contextlib.suppress(Exception):
                connection.query(f"SELECT RELEASE_LOCK('{lock}')")

    def _event(self, actor, action, payload):
        if action in {'curation_updated', 'protocol_tree_layout_saved', 'search_query_run',
                      'search_preset_created', 'search_preset_updated'}:
            return None  # Recover current state from app-state.json; no action replay.
        identity = str(uuid.uuid4())
        self.Event.insert1({"event_uuid": identity, "project_uuid": self.project_uuid,
                            "occurred_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                            "actor": actor, "action": action, "payload": build_audit_payload(action, actor, payload,
                                context={"project_uuid": self.project_uuid, "protocol_uuid": payload.get("protocol_uuid")})})
        return identity

    def update(self, protocol_uuid, epoch_ids, changes, expected_revisions, fingerprints, actor,
               *, inclusion_by_epoch=None, audit_context=None, expected_binding_version=None, generation_preflight=None):
        protocol_uuid = _uuid(protocol_uuid)
        ids, fingerprints = _scope(epoch_ids, fingerprints)
        if not ids:
            raise ValueError("Select at least one epoch")
        if inclusion_by_epoch is not None:
            if (not isinstance(inclusion_by_epoch, dict) or set(inclusion_by_epoch) != set(ids)
                    or any(type(value) is not bool for value in inclusion_by_epoch.values())):
                raise ValueError("Inclusion mask must cover exactly every epoch with Boolean values")
            if not isinstance(changes, dict) or "included" in changes:
                raise ValueError("An inclusion mask cannot be combined with a uniform included change")
            changes = _changes(changes) if changes else {}
        else:
            changes = _changes(changes)
        actor = _actor(actor)
        _expectations(ids, expected_revisions)
        with self._transaction(protocol_uuid):
            if generation_preflight is not None:generation_preflight()
            provider = getattr(self, 'binding_provider', None)
            if provider and expected_binding_version is not None:
                header_provider=getattr(self,'binding_header_provider',None)
                binding = (header_provider or provider)(protocol_uuid)
                if (binding['version'] if binding else 0) != expected_binding_version:
                    raise RevisionConflict({'binding_version': binding['version'] if binding else 0})
            # Mutation preflight is proportional to its explicit targets, even
            # for a batch larger than one SQL restriction chunk. Full summaries
            # retain the sparse whole-protocol read path above.
            rows = self._rows(protocol_uuid, ids, selected_only=True)
            before = {key: self._state(rows.get(key), fingerprints[key]) for key in ids}
            if any(before[key]["revision"] != expected_revisions[key] for key in ids):
                raise RevisionConflict(before)
            after = {}
            for key in ids:
                state = dict(before[key])
                state["included"] = (inclusion_by_epoch[key] if inclusion_by_epoch is not None
                                     else changes.get("included", state["included"]))
                state["tags"] = sorted((set(state["tags"]) | set(changes.get("tags_add", []))) -
                                       set(changes.get("tags_remove", [])))
                state["review_state"] = changes.get("review_state", state["review_state"])
                state["revision"] += 1
                state["approval_stale"] = False
                row = {"project_uuid": self.project_uuid, "protocol_uuid": protocol_uuid,
                       "epoch_uuid": key, **{k: v for k, v in state.items() if k != "approval_stale"}}
                if key in rows:
                    self.Curation.update1(row)
                else:
                    self.Curation.insert1(row)
                after[key] = state
            event_uuid = self._event(actor, "curation_updated", {
                "protocol_uuid": protocol_uuid,
                "changes": ({**changes, "inclusion_by_epoch": inclusion_by_epoch}
                            if inclusion_by_epoch is not None else changes),
                "before": before, "after": after, "query_context": audit_context or {},
                "previous_metadata_fingerprints": {
                    key: rows[key]["metadata_fingerprint"] if key in rows else None for key in ids}})
        if "tags_add" in changes or "tags_remove" in changes:
            self._tag_vocabulary = None  # Invalidate only after successful commit.
        return {"curation": after, "event_uuid": event_uuid}

    def record_dataset_revision(self, recipe, *, actor, expected_revisions,
                                artifact_path, artifact_sha256):
        """Record a completed reference package after the caller writes it.

        The query snapshot and exact selection are stored unchanged. A curation
        race rejects publication; the caller may clean up the unrecorded file.
        """
        verify(recipe)
        if recipe["format"] != "recording-export-recipe":
            raise ValueError("Dataset revision requires an export recipe")
        if recipe["project_uuid"] != self.project_uuid:
            raise ValueError("Export belongs to another project")
        protocol_uuid, actor = _uuid(recipe["protocol_uuid"]), _actor(actor)
        snapshot = verify(recipe["query_snapshot"])
        if any(snapshot[key] != recipe[key] for key in ("project_uuid", "protocol_uuid", "query_sha256", "catalog_ref")):
            raise ValueError("Recipe and query snapshot scope differ")
        members = member_map(snapshot)
        ids, fingerprints = _scope(list(members), {key: row["metadata_hash"] for key, row in members.items()})
        _expectations(ids, expected_revisions)
        path = Path(artifact_path).resolve()
        artifact_sha256 = _fingerprint(artifact_sha256)
        with path.open("rb") as handle:
            actual_hash = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual_hash != artifact_sha256:
            raise ValueError("Export artifact checksum does not match")
        if len(str(path)) > 2048:
            raise ValueError("Artifact path is too long")
        dataset_uuid = _uuid(recipe["export_uuid"])
        with self._transaction(protocol_uuid):
            provider = getattr(self, 'binding_provider', None)
            if provider:
                binding = provider(protocol_uuid)
                expected_version = recipe.get('dataset_binding', {}).get('version', 0)
                if (binding['version'] if binding else 0) != expected_version:
                    raise RevisionConflict({'binding_version': binding['version'] if binding else 0})
            current = self.read(protocol_uuid, ids, fingerprints)
            if any(current[key]["revision"] != expected_revisions[key] for key in ids):
                raise RevisionConflict(current)
            included = {key for key, state in current.items() if state["included"]}
            approved = {key for key, state in current.items() if state["review_state"] == "approved"}
            selection, review = recipe["selection"], recipe["review"]
            if not set(selection["included"]).issubset(included) or set(review["approved_epoch_ids"]) != approved:
                raise ValueError("Export recipe differs from current curation")
            if review["policy"] not in {"approved_only", "include_unreviewed"}:
                raise ValueError("Unknown export review policy")
            included = set(selection["included"])
            eligible = included & approved if review["policy"] == "approved_only" else included
            if set(selection["excluded"]) != set(ids) - included or set(selection["held_by_review"]) != included - eligible:
                raise ValueError("Export selection partition differs from its query snapshot")
            if not eligible or set(member_map(recipe)) != eligible:
                raise ValueError("Export membership differs from the frozen selection/review policy")
            if any(member_map(recipe)[key] != members[key] for key in eligible):
                raise ValueError("Export member fingerprint differs from its query snapshot")
            sources = (self.Source & {"project_uuid": self.project_uuid}).to_dicts()
            if set(recipe["source_revisions"]) != set(snapshot["source_revisions"]) or not set(
                    recipe["source_revisions"]).issubset({row["source_sha256"] for row in sources}):
                raise ValueError("Export source revision is not registered to this project")
            self.DatasetRevision.insert1({"project_uuid": self.project_uuid, "dataset_uuid": dataset_uuid,
                "protocol_uuid": protocol_uuid, "created_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                "actor": actor, "recipe": recipe, "artifact_path": str(path),
                "artifact_sha256": artifact_sha256, "epoch_count": len(eligible)})
            event_uuid = self._event(actor, "dataset_revision_exported", {
                "protocol_uuid": protocol_uuid, "dataset_uuid": dataset_uuid,
                "artifact_path": str(path), "artifact_sha256": artifact_sha256,
                "recipe_sha256": recipe["content_sha256"], "epoch_count": len(eligible),
                "query_sha256": recipe["query_sha256"], "query_snapshot_uuid": snapshot["snapshot_uuid"],
                "source_revisions": snapshot["source_revisions"],
                "curation_revisions": expected_revisions,
                **({"export_scope":copy.deepcopy(recipe["options"]["export_scope"])}
                   if recipe.get("options",{}).get("export_scope") else {})})
        return {"dataset_uuid": dataset_uuid, "event_uuid": event_uuid,
                "artifact_path": str(path), "artifact_sha256": artifact_sha256,
                "epoch_count": len(eligible)}

    def _export_index(self):
        """Cache frozen memberships; poll only small identity/version columns.

        No current query snapshot is treated as exported membership. Completed
        dataset records are immutable, so the artifact hash and creation time
        identify the recipe version. A changed signature rebuilds the index.
        """
        relation = self.DatasetRevision & {"project_uuid": self.project_uuid}
        headers = relation.proj("artifact_sha256", "created_at").to_dicts()
        signature = tuple(sorted((row["dataset_uuid"], row["artifact_sha256"],
                                  str(row["created_at"])) for row in headers))
        if getattr(self, "_export_signature", None) != signature:
            rows = relation.to_dicts() if headers else []
            index, summaries = {}, []
            for row in rows:
                recipe = verify(row["recipe"])
                if (recipe.get("format") != "recording-export-recipe"
                        or recipe["project_uuid"] != self.project_uuid
                        or recipe["export_uuid"] != row["dataset_uuid"]
                        or recipe["protocol_uuid"] != row["protocol_uuid"]):
                    raise ValueError("Saved export recipe and dataset identity disagree")
                members = member_map(recipe)
                if len(members) != row["epoch_count"]:
                    raise ValueError("Saved export member count disagrees with dataset record")
                name = recipe.get("options", {}).get("name", "Reference export")
                timestamp = row["created_at"]
                timestamp = timestamp.replace(tzinfo=dt.timezone.utc).isoformat() if isinstance(timestamp, dt.datetime) else str(timestamp)
                summary = {**{key: value for key, value in row.items() if key != "recipe"},
                           "name": name, "status": "completed", "format": recipe.get("destination", "reference-json"),
                           **({"export_scope":copy.deepcopy(recipe["options"]["export_scope"])}
                              if recipe.get("options",{}).get("export_scope") else {})}
                summaries.append(summary)
                for key, member in members.items():
                    index.setdefault(key, []).append({"dataset_uuid": row["dataset_uuid"],
                        "name": name, "protocol_uuid": row["protocol_uuid"], "created_at": timestamp,
                        "artifact_sha256": row["artifact_sha256"],
                        "metadata_hash": member["metadata_hash"],
                        "metadata_fingerprint_version": recipe["query_snapshot"].get("metadata_fingerprint_version", 1),
                        **({"export_scope":copy.deepcopy(recipe["options"]["export_scope"])}
                           if recipe.get("options",{}).get("export_scope") else {})})
            for links in index.values():
                links.sort(key=lambda link: (link["created_at"], link["dataset_uuid"]), reverse=True)
            self._export_memberships = index
            self._export_summaries = sorted(summaries,
                key=lambda row: (str(row["created_at"]), row["dataset_uuid"]), reverse=True)
            self._export_signature = signature
        return self._export_memberships

    def export_memberships(self):
        """Project-scoped membership across all protocol export revisions."""
        return copy.deepcopy(self._export_index())

    def epoch_exports(self, epoch_uuid):
        identity = _uuid(epoch_uuid)
        return copy.deepcopy(self._export_index().get(identity, []))

    def list_dataset_revisions(self, protocol_uuid=None):
        protocol_uuid = _uuid(protocol_uuid) if protocol_uuid is not None else None
        self._export_index()
        return copy.deepcopy([row for row in self._export_summaries
                              if protocol_uuid is None or row["protocol_uuid"] == protocol_uuid])

    def get_dataset_revision(self, dataset_uuid):
        rows = (self.DatasetRevision & {"project_uuid": self.project_uuid,
                                        "dataset_uuid": _uuid(dataset_uuid)}).to_dicts()
        if not rows:
            raise KeyError("Dataset revision not found")
        return rows[0]
