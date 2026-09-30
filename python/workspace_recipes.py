"""Versioned query/export recipes and metadata-only trees.

No scientific approval is inferred here. Export adapters must consume the frozen
members, write their artifact, then record its checksum and completion event.
This module never reports a prepared recipe as a completed data export.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from recording_workspace import now, validate_protocol_definition


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def member_map(result):
    members = {}
    for row in result["epochs"]:
        identity = str(uuid.UUID(row["uuid"]))
        if identity in members:
            raise ValueError("Duplicate epoch identity in query results")
        fingerprint = row["metadata_hash"]
        if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(
                c not in "0123456789abcdef" for c in fingerprint):
            raise ValueError("Missing or invalid epoch metadata fingerprint")
        members[identity] = {"uuid": identity, "metadata_hash": fingerprint}
    return members


def capture_query(definition, result, catalog_ref):
    """Capture one evaluated query, retaining identities even if it later changes."""
    validate_protocol_definition(definition)
    if any(result.get(k) != definition[k] for k in ("project_uuid", "protocol_uuid")):
        raise ValueError("Query result belongs to a different project/protocol")
    if not catalog_ref:
        raise ValueError("A resolvable main-catalog reference is required")
    query = copy.deepcopy(definition['query'])
    binding = result.get('dataset_binding')
    if 'effective_query' in result:
        effective = result['effective_query']
        if (not isinstance(effective, dict) or set(effective) != {'version', 'kind', 'predicate'}
                or effective['version'] != 2 or effective['kind'] != 'source_predicate'
                or not isinstance(effective['predicate'], dict) or not isinstance(binding, dict)
                or type(binding.get('version')) is not int or binding['version'] < 1):
            raise ValueError('Malformed bound source predicate query')
        uuid.UUID(binding['revision_uuid'])
        if binding.get('changed_epoch_uuids'):
            raise ValueError('Bound metadata changed; rerun and apply a new dataset revision before export')
        query = copy.deepcopy(effective)
    members = member_map(result)
    sources = sorted(set(result["source_revisions"]))
    if members and not sources:
        raise ValueError("Query members have no source revisions")
    payload = {"format": "recording-query-snapshot", "version": 1,
               "snapshot_uuid": str(uuid.uuid4()), "created_at": now(),
               "project_uuid": definition["project_uuid"],
               "protocol_uuid": definition["protocol_uuid"],
               "catalog_ref": str(catalog_ref),
               "query": query,
               "query_sha256": checksum(query),
               "metadata_fingerprint_version": result.get("metadata_fingerprint_version", 1),
               "view": copy.deepcopy(result.get("effective_view", definition.get("view", {}))),
               "source_revisions": sources,
               "epochs": [members[k] for k in sorted(members)]}
    if 'shared_annotations_revision' in result:
        payload['shared_annotations_revision']=result['shared_annotations_revision']
    if 'source_scope' in result:
        payload['source_scope'] = copy.deepcopy(result['source_scope'])
    if binding:
        payload['dataset_binding'] = copy.deepcopy(binding)
        payload['starter_query'] = copy.deepcopy(definition['query'])
    return seal(payload)


def seal(payload):
    payload = copy.deepcopy(payload)
    payload.pop("content_sha256", None)
    return {**payload, "content_sha256": checksum(payload)}


def verify(snapshot):
    payload = copy.deepcopy(snapshot)
    expected = payload.pop("content_sha256", None)
    if expected != checksum(payload):
        raise ValueError("Snapshot checksum mismatch")
    if payload.get("version") != 1 or payload.get("format") not in {
            "recording-query-snapshot", "recording-export-recipe"}:
        raise ValueError("Unsupported snapshot format/version")
    member_map(snapshot)
    return snapshot


def compare_query(previous, current):
    """Compare query results, not an export's filtered membership."""
    verify(previous)
    verify(current)
    if previous.get("metadata_fingerprint_version", 1) != current.get("metadata_fingerprint_version", 1):
        raise ValueError("Metadata fingerprint versions differ; create a new comparison baseline")
    for key in ("project_uuid", "protocol_uuid", "query_sha256", "catalog_ref"):
        if previous[key] != current[key]:
            raise ValueError("Cannot compare different query definitions/catalogs")
    old, new = member_map(previous), member_map(current)
    return {"added": sorted(new.keys() - old.keys()),
            "removed": sorted(old.keys() - new.keys()),
            "changed": sorted(k for k in old.keys() & new.keys()
                              if old[k]["metadata_hash"] != new[k]["metadata_hash"])}


def prepare_export(snapshot, included_ids, *, destination, review_policy,
                   approved_ids=(), actor, options=None):
    """Freeze selection and the query that generated it before adapter execution.

    approved_ids must come from the caller's verified review revision. This
    contract helper does not itself provide a review persistence service.
    """
    verify(snapshot)
    if snapshot["format"] != "recording-query-snapshot":
        raise ValueError("Export requires the original query snapshot")
    if review_policy not in {"approved_only", "include_unreviewed"}:
        raise ValueError("Unknown review policy")
    if not destination or not actor:
        raise ValueError("Export destination and actor are required")
    members = member_map(snapshot)
    included = list(included_ids)
    if len(set(included)) != len(included) or set(included) - members.keys():
        raise ValueError("Selection contains duplicate or out-of-query epochs")
    approved = set(approved_ids)
    if approved - members.keys():
        raise ValueError("Review scope contains out-of-query epochs")
    eligible = set(included) & approved if review_policy == "approved_only" else set(included)
    if not eligible:
        raise ValueError("No epochs eligible for export under this review policy")
    payload = {"format": "recording-export-recipe", "version": 1,
               "export_uuid": str(uuid.uuid4()), "created_at": now(),
               "status": "prepared", "actor": actor, "destination": destination,
               "options": copy.deepcopy(options or {}),
               "project_uuid": snapshot["project_uuid"],
               "protocol_uuid": snapshot["protocol_uuid"],
               "catalog_ref": snapshot["catalog_ref"],
               "query": snapshot["query"], "query_sha256": snapshot["query_sha256"],
               "view": snapshot["view"], "source_revisions": snapshot["source_revisions"],
               "query_snapshot": snapshot,
               "selection": {"included": sorted(included),
                             "excluded": sorted(members.keys() - set(included)),
                             "held_by_review": sorted(set(included) - eligible)},
               "review": {"policy": review_policy, "approved_epoch_ids": sorted(approved)},
               "epochs": [members[k] for k in sorted(eligible)]}
    for key in ('dataset_binding', 'starter_query', 'source_scope'):
        if key in snapshot:
            payload[key] = copy.deepcopy(snapshot[key])
    return seal(payload)


def save_snapshot(path, snapshot):
    """Publish a complete file atomically; never overwrite an earlier revision."""
    verify(snapshot)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(snapshot, indent=2, allow_nan=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".snapshot-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)  # Atomic, and fails if a revision already exists.
    finally:
        Path(temporary).unlink(missing_ok=True)


SPLIT_FIELDS = {"date": "date", "cell": "cell_uuid", "cell type": "cell_type",
                "block": "block_uuid", "group": "group_uuid", "protocol": "protocol_name",
                "group label": "group_label", "block time": "block_start_time"}


# These exact names were emitted by recording_workspace for starter protocol
# views before the tree catalog used opaque field IDs. Preserve their meaning;
# arbitrary dotted paths are still unsupported and every target is validated.
LEGACY_SPLIT_FIELDS = {'cell.type': 'cell type', 'cell.start_time': 'metadata/cell/start_time'}


def parse_splits(text, allowed_fields=None):
    import re
    if not isinstance(text, str):
        raise ValueError("Tree split order must be text")
    fields = [part.strip() for part in text.replace("→", ",").split(",") if part.strip()]
    fields = [LEGACY_SPLIT_FIELDS.get(field, field) for field in fields]
    fields = [field.lower() if field.lower() in SPLIT_FIELDS else field for field in fields]
    def valid(field):
        if field.startswith('joint/'):
            from workspace_tree import joint_components
            parts = joint_components(field, allowed_fields)
            return all(valid(part) for part in parts)
        if allowed_fields is not None:
            return field in allowed_fields
        return field in SPLIT_FIELDS or bool(re.fullmatch(
            r'(?:parameters|properties|metadata/(?:cell|group|block)/properties)/(?:[A-Za-z0-9_.~/-]|%[0-9A-F]{2})+', field))
    if len(fields) > 8 or len(fields) != len(set(fields)) or any(not valid(f) for f in fields):
        raise ValueError("Choose up to 8 distinct recorded fields from the tree field catalog")
    return fields


def build_tree(rows, split_text, field_values=None, allowed_fields=None):
    """Group exact metadata membership; missing and typed values stay distinct."""
    from workspace_tree import value_key, field_value_order, joint_components, joint_value
    rows = list(rows)
    allowed = set(SPLIT_FIELDS) | set(allowed_fields or [])
    if field_values is not None:
        for values in field_values.values():
            allowed.update(values)
    fields = parse_splits(split_text, allowed)
    joints = [field for field in fields if field.startswith('joint/')]
    if joints:
        field_values = {row['epoch_uuid']: {**{field:row.get(path) for field,path in SPLIT_FIELDS.items()},
                        **(field_values or {}).get(row['epoch_uuid'], {})} for row in rows}
        for field in joints:
            components = joint_components(field, allowed)
            for current in field_values.values():
                current[field] = joint_value(current, components)
    ids = [r["epoch_uuid"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate epoch identity in tree input")

    def group(items, depth):
        durations = [row.get('duration_seconds') for row in items]
        node = {"count": len(items),
                "cell_count": len({row['cell_uuid'] for row in items if row.get('cell_uuid')}),
                "duration_seconds": sum(durations) if all(value is not None for value in durations) else None}
        if depth == len(fields):
            return {**node, "epoch_uuids": sorted(r["epoch_uuid"] for r in items)}
        field = fields[depth]
        bins = {}
        for row in items:
            value = (field_values or {}).get(row['epoch_uuid'], {}).get(field) if field not in SPLIT_FIELDS else row.get(SPLIT_FIELDS[field])
            if field == "date":
                raw = str(row.get("start_time") or "")[:10]
                value = None
                if raw:
                    for format in ("%Y-%m-%d", "%m/%d/%Y"):
                        try:
                            value = dt.datetime.strptime(raw, format).date().isoformat()
                            break
                        except ValueError:
                            pass
                    if value is None:
                        raise ValueError("Unrecognized recording date in tree metadata")
            missing = (field not in (field_values or {}).get(row['epoch_uuid'], {})) if field not in SPLIT_FIELDS else value is None
            key = '__missing__' if missing else value_key(value)
            if key not in bins:
                bins[key] = (value, missing, [])
            bins[key][2].append(row)
        node.update(field=field, children=[{"key": field + ":" + ("missing" if missing else value_key(value)), "value": value, "missing": missing, **group(items, depth + 1)}
                    for value, missing, items in sorted(bins.values(), key=lambda pair: (pair[1], field_value_order(field,pair[0])))])
        return node

    return group(rows, 0)
