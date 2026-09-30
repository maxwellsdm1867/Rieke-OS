"""Versioned audit payloads and read-only presentation of the SQL master log.

This module neither connects to a database nor executes suggested actions. Call
build_audit_payload inside the same transaction as the scientific bookkeeping
change, then store its return value in recording_workspace.Event.payload.
Only pass intentional, structured evidence: never request headers, environment
variables, connection configuration, or unfiltered request bodies.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import copy
import datetime as dt
from functools import lru_cache
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import uuid

AUDIT_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "python/workspace_mask_refresh.py", "python/workspace_matlab_routes.py",
    "python/workspace_export_folder.py", "workspace-app/src/components/MetadataRefresh.jsx",
    "python/workspace_external_tags.py", "workspace-app/src/externalTagMonitor.js",
    "workspace-app/src/components/ExternalTagSync.jsx",
    "python/workspace_annotations.py", "python/workspace_tag_predicates.py", "python/workspace_tag_exchange.py",
    "python/workspace_search_presets.py",
    "python/workspace_audit.py", "python/recording_workspace.py",
    "python/workspace_api.py", "python/workspace_service.py",
    "python/workspace_curation.py", "python/workspace_recipes.py",
    "python/workspace_candidate_exports.py", "workspace-app/src/components/CandidateExportPanel.jsx",
    "workspace-app/src/exportReuse.js",
    "python/workspace_disk_index.py", "python/workspace_projection_cache.py",
    "python/workspace_tree_pages.py", "workspace-app/src/components/PagedTree.jsx",
    "workspace-app/src/components/ColumnTree.jsx", "workspace-app/src/pagedTreeRequest.js",
    "workspace-app/src/components/EpochSkimList.jsx", "workspace-app/src/epochSkimGroups.js",
    "workspace-app/src/components/EpochTags.jsx", "workspace-app/src/components/MetadataPanel.jsx",
    "python/workspace_predicates.py", "python/workspace_explorer.py", "python/workspace_protocol_identity.py", "python/workspace_diff.py", "python/workspace_import_check.py", "python/workspace_import_progress.py", "python/workspace_suggestions.py", "python/workspace_qc.py", "python/workspace_search.py", "python/workspace_datastores.py",
    "workspace-app/src/components/PredicateBuilder.jsx",
    "python/workspace_storage.py", "python/workspace_tree.py", "workspace-app/package.json",
    "python/workspace_import_check.py", "python/workspace_import_progress.py", "python/workspace_suggestions.py", "python/workspace_qc.py", "python/workspace_search.py", "python/workspace_datastores.py", "workspace-app/src/components/DataStores.jsx",
    "workspace-app/src/components/SourcePropagation.jsx", "workspace-app/src/components/ImportHistory.jsx",
    "workspace-app/src/App.jsx", "workspace-app/src/api.js",
    "workspace-app/src/components/Inspector.jsx", "workspace-app/src/components/MasterLog.jsx",
    "workspace-app/src/components/TreeBuilder.jsx", "workspace-app/src/components/EpochConnections.jsx",
    "workspace-app/src/components/MetadataExplorer.jsx", "workspace-app/src/components/TreePreview.jsx",
    "workspace-app/src/components/Common.jsx",
    "workspace-app/src/components/Overview.jsx", "workspace-app/src/components/overviewModel.js",
    "workspace-app/src/components/TraceViewer.jsx", "workspace-app/src/components/traceGeometry.js",
    "workspace-app/src/components/ProtocolSidebar.jsx", "workspace-app/src/ordering.js",
    "workspace-app/src/pointerDrag.js",
    "workspace-app/src/components/ProjectFiles.jsx",
)
CONTRACT_VERSIONS = {
    "shared_annotations": 1, "audit_payload": 1, "workspace_schema": 1, "tree_view": 1,
    "metadata_disk_index": 1, "source_projection_cache": 1, "tree_page": 1,
    "source_eligibility": 2, "source_propagation": 1, "import_preflight": 1,
    "source_predicate": 1, "explorer_revision": 1, "protocol_binding": 1, "data_store_lifecycle": 1,
    "protocol_workspace": 1, "query_snapshot": 1,
    "export_recipe": 1, "reference_package": 1, "metadata_fingerprint": 2,
}
_SECRET_KEY = re.compile(r"(?:^|[_.\-])(password|passwd|secret|token|api_key|authorization|cookie|credentials?|connection|env|environment)(?:$|[_.\-])", re.I)
_SECRET_TEXT = re.compile(r"\b(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*([^\s,;]+)", re.I)
_URL_CREDENTIALS = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@", re.I)


def _safe(value):
    """Copy JSON evidence while removing common credential-bearing fields."""
    if isinstance(value, Mapping):
        return {str(key): "[redacted]" if _SECRET_KEY.search(str(key)) else _safe(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, str):
        value = _URL_CREDENTIALS.sub(r"\1[redacted]@", value)
        return _SECRET_TEXT.sub(lambda match: match.group(1) + "=[redacted]", value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise ValueError(f"Audit evidence must be JSON data, not {type(value).__name__}")


def _signature(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@lru_cache(maxsize=128)
def _cached_digest(path_string, signature):
    path = Path(path_string)
    with path.open("rb") as handle:
        result = hashlib.file_digest(handle, "sha256").hexdigest()
    if _signature(path) != signature:
        raise ValueError("Source code changed during audit fingerprinting")
    return result


def code_fingerprints(source_files=None):
    """Hash known source files; unchanged files require only a stat check.

    Values describe files on disk at the event time, not a claim that Python has
    reloaded edits made after the process started. No shell/Git commands run.
    """
    files = source_files if source_files is not None else {name: ROOT / name for name in SOURCE_FILES}
    if not isinstance(files, Mapping):
        raise ValueError("source_files must map descriptive labels to source paths")
    result = {}
    for label, raw_path in sorted(files.items()):
        if not isinstance(label, str) or not label or _SECRET_KEY.search(label):
            raise ValueError("Source labels must be descriptive non-secret names")
        path = Path(raw_path).resolve()
        if path.suffix not in {".py", ".js", ".jsx", ".ts", ".tsx", ".json"} or (
                path.suffix == ".json" and path.name != "package.json"):
            raise ValueError("Only application source files and package.json can be fingerprinted")
        try:
            signature = _signature(path)
            result[label] = {"sha256": _cached_digest(str(path), signature), "status": "recorded"}
        except FileNotFoundError:
            result[label] = {"status": "missing"}
    return result


@lru_cache(maxsize=8)
def _package_version(path_string, signature):
    path = Path(path_string)
    result = str(json.loads(path.read_text()).get("version", "not_recorded"))
    if _signature(path) != signature:
        raise ValueError("Package version changed during audit capture")
    return result


@lru_cache(maxsize=1)
def _datajoint_version():
    try:
        return importlib.metadata.version("datajoint")
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"


def _provenance(parser_manifest=None, source_files=None):
    package = ROOT / "workspace-app/package.json"
    try:
        version = _package_version(str(package), _signature(package))
    except FileNotFoundError:
        version = "not_recorded"
    parser = {"status": "not_recorded"}
    if parser_manifest is not None:
        if not isinstance(parser_manifest, Mapping):
            raise ValueError("parser_manifest must be structured metadata")
        fields = {key: parser_manifest[key] for key in (
            "parser_sha256", "parser_version", "adapter_version", "adapter_sha256",
            "source_sha256", "metadata_sha256") if key in parser_manifest}
        parser = {"status": "recorded" if fields.get("parser_sha256") else "partial", **fields}
    return {"application": {"name": "recording-workspace", "display_name": "Rieke OS", "version": version},
            "contracts": dict(CONTRACT_VERSIONS), "schema": "recording_workspace",
            "runtime": {"python": platform.python_version(), "datajoint": _datajoint_version()},
            "code_fingerprint_scope": "local_source_files_on_disk_at_event",
            "code": code_fingerprints(source_files), "parser": parser}


def build_audit_payload(action, actor, payload=None, *, operation_uuid=None,
                        inputs=None, outputs=None, context=None, parser_manifest=None,
                        outcome="completed", actor_kind="local_user", source_files=None):
    """Preserve existing payload keys and add a versioned audit envelope.

    actor_kind identifies attribution, not authentication. local_user means the
    server's OS username; agent/system/client_claimed must be chosen explicitly.
    Reuse one operation_uuid across stages of a single operation.
    """
    if not isinstance(action, str) or not action or len(action) > 63:
        raise ValueError("Audit action must contain 1–63 characters")
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 255:
        raise ValueError("Audit actor must contain 1–255 characters")
    if actor_kind not in {"local_user", "agent", "system", "client_claimed"}:
        raise ValueError("Unsupported actor attribution kind")
    if outcome not in {"started", "completed", "failed", "cancelled"}:
        raise ValueError("Unsupported audit outcome")
    payload = {} if payload is None else payload
    if not isinstance(payload, Mapping) or "audit" in payload:
        raise ValueError("Payload must be a mapping without a reserved audit key")
    identity = operation_uuid or payload.get("operation_uuid") or str(uuid.uuid4())
    identity = str(uuid.UUID(str(identity)))
    envelope = {"format": "recording-action-audit", "version": AUDIT_VERSION,
        "operation_uuid": identity, "action": action, "outcome": outcome,
        "actor": {"name": actor, "kind": actor_kind,
                  "attribution": "server_os_user" if actor_kind == "local_user" else actor_kind,
                  "authenticated_identity": False},
        "input": inputs or {}, "output": outputs or {}, "context": context or {},
        "provenance": _provenance(parser_manifest, source_files)}
    result = _safe({**payload, "audit": envelope})
    json.dumps(result, allow_nan=False)  # Reject nonfinite or non-JSON evidence.
    return result


def _count(payload, audit, action):
    for value in (payload.get("epoch_count"), payload.get("counts", {}).get("epochs")
                  if isinstance(payload.get("counts"), dict) else None):
        if type(value) is int and value >= 0:
            return value
    if action == 'curation_updated' and isinstance(payload.get('after'), dict):
        return len(payload['after'])
    for container, key in ((payload, "epoch_uuids"),
                           (audit.get("input", {}), "epoch_uuids")):
        value = container.get(key) if isinstance(container, dict) else None
        if isinstance(value, (list, dict)):
            return len(value)
    return None


def tag_activity_summary(payload):
    """Summarize recorded author attribution; never substitute the OS actor."""
    before = payload.get('before', [])
    after = payload.get('after', [])
    if not isinstance(before, list) or not isinstance(after, list):return None
    def identity(row):return (row.get('profile_uuid'), row.get('target_kind'), row.get('target_uuid'))
    previous = {identity(row): row for row in before if isinstance(row, dict)}
    authors, changes = {}, {}
    for row in after:
        if not isinstance(row, dict):continue
        profile = row.get('profile_uuid')
        author = row.get('author_name') or 'Author not recorded'
        authors[profile] = {'profile_uuid':profile, 'name':author}
        old = previous.get(identity(row), {})
        old_tags = {tag for tag in (old.get('tags') or []) if isinstance(tag, str)}
        new_tags = {tag for tag in (row.get('tags') or []) if isinstance(tag, str)}
        for operation, tags in (('added',new_tags-old_tags), ('removed',old_tags-new_tags)):
            for tag in sorted(tags):
                key = (profile, row.get('target_kind'), operation, tag)
                item = changes.setdefault(key, {'profile_uuid':profile, 'author':author,
                    'scope':row.get('target_kind'), 'operation':operation, 'tag':tag, 'targets':0})
                item['targets'] += 1
    return {'authors':list(authors.values())[:20], 'author_count':len(authors),
            'changes':list(changes.values())[:24], 'change_count':len(changes)}


def normalize_event(row):
    """Add UI summary without fabricating provenance for historical events."""
    result = _safe(copy.deepcopy(row))
    occurred_at = row.get("occurred_at")
    if isinstance(occurred_at, dt.datetime):
        # SQL Event timestamps are written as naive UTC by the workspace.
        result["occurred_at"] = (occurred_at.replace(tzinfo=dt.timezone.utc)
            if occurred_at.tzinfo is None else occurred_at.astimezone(dt.timezone.utc)).isoformat()
    payload = result.get("payload")
    if isinstance(payload, str):
        try:
            payload = _safe(json.loads(payload))
        except (ValueError, TypeError):
            payload = {"legacy_payload": payload}
    if not isinstance(payload, dict):
        payload = {"legacy_payload": payload}
    result["payload"] = payload
    audit = payload.get("audit")
    audit = audit if isinstance(audit, dict) else {}
    versioned = audit.get("format") == "recording-action-audit" and audit.get("version") == AUDIT_VERSION
    action = result.get("action", "unknown")
    context = audit.get("context", {})
    context = context if isinstance(context, dict) else {}
    # Outcome inference is limited to named historical terminal events.
    legacy_success = {"query_refreshed", "dataset_revision_exported", "curation_updated",
                      "imported", "already_imported", "protocol_files_saved", "job_imported",
                      "job_already_imported", "job_validated"}
    legacy_failure = {"import_failed", "workspace_finalize_failed", "job_failed"}
    outcome = audit.get("outcome", "unknown") if versioned else (
        "completed" if action in legacy_success else "failed" if action in legacy_failure else "unknown")
    if audit and (not versioned or audit.get("action") != action):
        outcome = "unknown"  # Unsupported/mismatched envelopes cannot imply success.
    result["audit_summary"] = {"versioned": versioned, "outcome": outcome,
        "operation_uuid": audit.get("operation_uuid") if versioned else payload.get("operation_uuid"),
        "protocol_uuid": payload.get("protocol_uuid") or context.get("protocol_uuid"),
        "entity_count": _count(payload, audit, action)}
    if action == 'shared_annotations_updated':
        result['tag_activity'] = tag_activity_summary(payload)
    elif action == 'annotation_profile_created':
        result['tag_activity'] = {'authors':[{'profile_uuid':payload.get('profile_uuid'),
            'name':payload.get('display_name') or 'Author not recorded'}], 'author_count':1, 'changes':[], 'change_count':0}
    result["provenance"] = audit.get("provenance", {}) if versioned else {}
    return result


def normalize_events(rows):
    return [normalize_event(row) for row in rows]


def _valid_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def repeat_suggestions(rows, *, minimum=2):
    """Offer navigation to review repeated workflows, never execute/reapprove.

    Counts only unique successful SQL events in the provided page of history.
    Suggestions are observations, not claims of intent or global frequency.
    """
    if type(minimum) is not int or minimum < 2:
        raise ValueError("Repeat suggestions require at least two events")
    groups = defaultdict(list)
    seen = set()
    for row in normalize_events(rows):
        action = row.get("action")
        if action not in {"query_refreshed", "dataset_revision_exported"} or row["audit_summary"]["outcome"] != "completed":
            continue
        event_id = _valid_uuid(row.get("event_uuid"))
        project_id = _valid_uuid(row.get("project_uuid"))
        protocol_id = _valid_uuid(row["audit_summary"]["protocol_uuid"])
        if not all((event_id, project_id, protocol_id)) or event_id in seen:
            continue
        seen.add(event_id)
        if action == "dataset_revision_exported" and not _valid_uuid(row["payload"].get("dataset_uuid")):
            continue
        groups[(project_id, protocol_id, action)].append(row)
    suggestions = []
    for (project_id, protocol_id, action), events in sorted(groups.items()):
        if len(events) < minimum:
            continue
        events.sort(key=lambda event: (str(event.get("occurred_at", "")), event["event_uuid"]), reverse=True)
        latest = events[0]
        exporting = action == "dataset_revision_exported"
        suggestion = {"action": action, "project_uuid": project_id, "protocol_uuid": protocol_id,
            "source_event_uuid": latest["event_uuid"], "count": len(events),
            "label": "Review another export from this protocol" if exporting else "Review this protocol's query refresh",
            "source_event_uuids": [row["event_uuid"] for row in events],
            "intent": "open_export_review" if exporting else "open_refresh_review",
            "automatic": False, "evidence_scope": "provided_event_history"}
        if exporting:
            suggestion["dataset_uuid"] = latest["payload"]["dataset_uuid"]
        suggestions.append(suggestion)
    return suggestions
