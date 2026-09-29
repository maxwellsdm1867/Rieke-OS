"""Import Symphony recordings with RetinAnalysis and persist protocol workspaces.

Run with the RetinAnalysis environment. Raw waveforms stay in their source H5.
Connection secrets are read from the configured local container, never saved in
protocol files. This first importer supports single-cell Symphony recordings.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import traceback
import uuid


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path, progress=None, stage="source_hashing"):
    with Path(path).open("rb") as handle:
        if progress is None:
            return hashlib.file_digest(handle, "sha256").hexdigest()
        total, completed, hasher = Path(path).stat().st_size, 0, hashlib.sha256()
        progress(stage, completed=0, total=total, unit='bytes')
        while chunk := handle.read(1024*1024):
            hasher.update(chunk)
            completed += len(chunk)
            progress(stage, completed=completed, total=total, unit='bytes')
        return hasher.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + "." + str(uuid.uuid4()) + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False, default=json_scalar) + "\n")
    os.replace(temporary, path)


def json_scalar(value):
    import numpy as np
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Unsupported metadata type: {type(value).__name__}")


def load_parser(repository):
    path = Path(repository) / "src/retinanalysis/utils/parse_data.py"
    spec = importlib.util.spec_from_file_location("workspace_symphony_parser", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def epochs(metadata):
    for animal in metadata["animals"]:
        for preparation in animal["preparations"]:
            for cell in preparation["cells"]:
                for group in cell["epoch_groups"]:
                    for block in group["epoch_blocks"]:
                        for epoch in block["epochs"]:
                            yield cell, group, block, epoch


def assert_new_catalog_identities(experiment, catalog, batch_size=200):
    """Reject reused source hierarchy identities before a new file is populated.

    Call only in the new-SHA branch while holding the import advisory lock and
    transaction. RetinAnalysis's h5_uuid columns are not unique keys; a later
    read-model rejection would be too late to prevent ambiguous catalog rows.
    Animal/preparation and response/stimulus identities are outside this guard.
    Matching scientific values or repeated trials are not duplicate identities.
    """
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError('Identity lookup batches must contain 1–500 identities')
    identities = {name: set() for name in ('Cell', 'EpochGroup', 'EpochBlock', 'Epoch')}

    def record(table, item):
        identity = item.get('uuid')
        if not isinstance(identity, str) or not identity or len(identity) > 255:
            raise ValueError(f'Missing or invalid {table} source UUID')
        if identity in identities[table]:
            raise ValueError(f'Repeated {table} source UUID within recording: {identity}; explicit reconciliation is required')
        identities[table].add(identity)

    for animal in experiment['animals']:
        for preparation in animal['preparations']:
            for cell in preparation['cells']:
                record('Cell', cell)
                for group in cell['epoch_groups']:
                    record('EpochGroup', group)
                    for block in group['epoch_blocks']:
                        record('EpochBlock', block)
                        for epoch in block['epochs']:
                            record('Epoch', epoch)
    for name, values in identities.items():
        ordered = sorted(values)
        table = getattr(catalog, name)
        for start in range(0, len(ordered), batch_size):
            batch = [{'h5_uuid': identity} for identity in ordered[start:start + batch_size]]
            collision = (table & batch).fetch('h5_uuid', limit=1)
            if len(collision):
                raise ValueError(f'Existing {name} source UUID {collision[0]} belongs to the catalog; '
                                 'explicit source/version reconciliation is required before importing this different file')


def prepare(source, project, repository, progress=None, expected_sha256=None):
    import h5py

    stat = source.stat()
    source_hash = digest(source, progress)
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise ValueError('Source SHA256 differs from the preflight identity; no parse or catalog insertion was attempted')
    emit = progress or (lambda stage, **fields: None)
    folder = project / "imports" / (source.stem + "-" + source_hash[:12])
    folder.mkdir(parents=True, exist_ok=True)
    raw_path = folder / "metadata.raw.json"
    parser, parser_path = load_parser(repository)
    parse_manifest = folder / "parse-manifest.json"
    emit("parsing", message="Reading cached metadata" if raw_path.exists() else "RetinAnalysis parser is running; its internal completion fraction is unavailable.")
    if raw_path.exists():
        if not parse_manifest.exists():
            raise ValueError("Unverified parser cache: missing parse manifest")
        cached = json.loads(parse_manifest.read_text())
        if cached.get("status") != "parsed" or cached.get("sha256") != source_hash:
            raise ValueError("Parser cache source or completion state does not match")
        if cached.get("metadata_sha256") != digest(raw_path):
            raise ValueError("Parser output checksum changed; refusing cached output")
        if cached.get("parser_sha256") != digest(parser_path):
            raise ValueError("Parser version changed; an explicit new parse revision is required")
    else:
        with (folder / "parser.log").open("w") as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                with parser.Symphony2Reader(str(source), str(raw_path)) as reader:
                    reader.read_write(datajoint=True)
        write_json(parse_manifest, {"status": "parsed", "sha256": source_hash,
                                   "metadata_sha256": digest(raw_path),
                                   "parser_sha256": digest(parser_path), "at": now()})
    raw = json.loads(raw_path.read_text())
    total_epochs = sum(1 for _ in epochs(raw))
    emit("validating_metadata", completed=0, total=total_epochs, unit="epochs")
    rows, protocol_counts, cell_ids = [], {}, set()
    warnings = []
    with h5py.File(source, "r") as h5:
        roots = [v for k, v in h5.items() if k.startswith("experiment-")]
        if len(roots) != 1:
            raise ValueError("Expected exactly one Symphony experiment root")
        root = roots[0]
        # RetinAnalysis currently builds ExperimentObj from the first animal.
        # Reuse its conversion while restoring the real experiment-level facts.
        experiment = parser.ExperimentObj(
            d={"attributes": parser.parse_attributes(root),
               "properties": parser.parse_attributes(root["properties"])},
            rig_type=raw["rig_type"],
        ).__dict__
        experiment["label"] = experiment.get("label") or source.stem
        experiment["animals"] = raw["animals"]
        if raw["uuid"] != experiment["uuid"]:
            warnings.append({"code": "experiment_identity_restored",
                             "parser_uuid": raw["uuid"],
                             "source_uuid": experiment["uuid"]})
        if experiment["rig_type"] != "PATCH":
            raise ValueError("This importer currently supports PATCH recordings only")
        for cell, group, block, epoch in epochs(experiment):
            cell_ids.add(cell["uuid"])
            streams = []
            parameters_checked = False
            for kind in ("responses", "stimuli"):
                for device, stream in epoch[kind].items():
                    obj = h5[stream["h5path"]]
                    raw_uuid = parser.parse_value(obj.attrs["uuid"])
                    if raw_uuid != stream["uuid"]:
                        raise ValueError("Stream UUID and H5 locator disagree")
                    source_epoch = obj.parent.parent
                    if parser.parse_value(source_epoch.attrs["uuid"]) != epoch["uuid"]:
                        raise ValueError("Stream points to a different source epoch")
                    source_block = source_epoch.parent.parent
                    if parser.parse_value(source_block.attrs["uuid"]) != block["uuid"]:
                        raise ValueError("Epoch points to a different source block")
                    if parser.parse_value(source_block.attrs["protocolID"]) != block["protocolID"]:
                        raise ValueError("Parsed protocol differs from the H5 block")
                    if not parameters_checked:
                        source_parameters = dict(source_block["protocolParameters"].attrs)
                        source_parameters.update(dict(source_epoch["protocolParameters"].attrs))
                        source_parameters = json.loads(json.dumps(source_parameters, cls=parser.NpEncoder, allow_nan=False))
                        for parameter, value in source_parameters.items():
                            if parameter not in epoch["parameters"] or epoch["parameters"][parameter] != value:
                                raise ValueError(f"Source parameter mismatch for epoch {epoch['uuid']}: {parameter}")
                        parameters_checked = True
                    data = obj.get("data")
                    units = None
                    if kind == "responses":
                        rate = stream.get("sampleRate")
                        if data is None or not isinstance(data, h5py.Dataset):
                            raise ValueError("Response has no readable H5 data dataset")
                        if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
                            raise ValueError("Response has an invalid sample rate")
                        if stream.get("sampleRateUnits") != "Hz":
                            raise ValueError("Unsupported sample-rate units; explicit conversion required")
                        source_rate = float(obj.attrs["sampleRate"])
                        if source_rate != rate:
                            raise ValueError("Parsed sample rate differs from its H5 response")
                        if data.shape and len(data):
                            # Bounded reads prove the referenced dataset is readable.
                            samples = [data[0], data[len(data) // 2], data[-1]]
                            if not data.dtype.names or "quantity" not in data.dtype.names or "units" not in data.dtype.names:
                                raise ValueError("Unsupported response representation; expected quantity and units")
                            observed_units = {s["units"].decode("utf-8") for s in samples}
                            if len(observed_units) != 1 or not next(iter(observed_units)):
                                raise ValueError("Missing or inconsistent response units")
                            units = observed_units.pop()
                            import numpy as np
                            for start in range(0, len(data), 65536):
                                chunk_units = np.unique(data.fields("units")[start:start + 65536])
                                if any(u.decode("utf-8") != units for u in chunk_units):
                                    raise ValueError("Response units change within its recorded samples")
                        else:
                            warnings.append({"code": "empty_response", "uuid": stream["uuid"]})
                    streams.append({"kind": kind, "device": device,
                                    "uuid": stream["uuid"],
                                    "h5_path": stream["h5path"],
                                    "data_path": data.name if data is not None else None,
                                    "sample_count": len(data) if data is not None else None,
                                    "units": units,
                                    "sample_rate": stream.get("sampleRate"),
                                    "sample_rate_units": stream.get("sampleRateUnits")})
            name = block["protocolID"]
            protocol_counts[name] = protocol_counts.get(name, 0) + 1
            rows.append({"epoch_uuid": epoch["uuid"], "cell_uuid": cell["uuid"],
                         "cell_label": cell["label"], "cell_type": cell.get("type"),
                         "group_uuid": group["uuid"], "group_label": group.get("label"),
                         "block_uuid": block["uuid"], "protocol_name": name,
                         "start_time": epoch.get("start_time"),
                         "parameters": epoch.get("parameters", {}), "streams": streams})
            emit("validating_metadata", completed=len(rows), total=total_epochs, unit="epochs")
        raw_epoch_ids = set()
        def visit(name, obj):
            if isinstance(obj, h5py.Group) and name.split("/")[-2:-1] == ["epochs"]:
                raw_epoch_ids.add(parser.parse_value(obj.attrs["uuid"]))
        h5.visititems(visit)
        parsed_ids = [r["epoch_uuid"] for r in rows]
        if len(set(parsed_ids)) != len(parsed_ids) or set(parsed_ids) != raw_epoch_ids:
            raise ValueError("Parsed epoch membership differs from the H5 source")
    after = source.stat()
    if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during parsing/validation")
    if digest(source, progress, "verifying_source_hash") != source_hash:
        raise ValueError("Source checksum changed during validation")
    normalized_path = folder / "metadata.catalog.json"
    write_json(normalized_path, experiment)
    experiment = json.loads(normalized_path.read_text())
    write_json(folder / "epoch-index.json", rows)
    write_json(folder / "tags.json", {})
    manifest = {"format": "recording-import", "version": 1, "status": "validated",
                "review_status": "unreviewed", "scientific_approval": False,
                "source_path": str(source), "source_sha256": source_hash,
                "source_size": stat.st_size, "experiment_uuid": experiment["uuid"],
                "parser_path": str(parser_path), "parser_sha256": digest(parser_path),
                "adapter_version": 1, "adapter_sha256": digest(__file__),
                "validated_at": now(), "metadata_path": str(normalized_path),
                "metadata_sha256": digest(normalized_path),
                "counts": {"cells": len(cell_ids), "epochs": len(rows),
                           "responses": sum(len(e["responses"]) for *_, e in epochs(experiment)),
                           "stimuli": sum(len(e["stimuli"]) for *_, e in epochs(experiment))},
                "protocol_epoch_counts": protocol_counts, "warnings": warnings}
    write_json(folder / "import-manifest.json", manifest)
    return experiment, rows, manifest, folder


def connect(container):
    if isinstance(container, Path):
        from workspace_native_database import connect_native
        return connect_native(container)
    import datajoint as dj
    result = subprocess.run(["docker", "inspect", container], check=True,
                            capture_output=True, text=True)
    info = json.loads(result.stdout)[0]
    env = dict(v.split("=", 1) for v in info["Config"]["Env"] if "=" in v)
    bindings = info["NetworkSettings"]["Ports"].get("3306/tcp")
    if not bindings:
        raise ValueError("Configured MySQL container has no published port")
    dj.config["database.host"] = "127.0.0.1"
    dj.config["database.port"] = int(bindings[0]["HostPort"])
    dj.config["database.user"] = "root"
    dj.config["database.password"] = env["MYSQL_ROOT_PASSWORD"]
    return dj


def workspace_tables(dj):
    schema = dj.Schema("recording_workspace")

    @schema
    class Project(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        ---
        name: varchar(255)
        directory: varchar(1024)
        """

    @schema
    class Source(dj.Manual):
        definition = """
        source_sha256: char(64)
        ---
        project_uuid: varchar(36)
        experiment_uuid: varchar(36)
        experiment_id: int
        manifest: json
        """

    @schema
    class Event(dj.Manual):
        definition = """
        event_uuid: varchar(36)
        ---
        project_uuid: varchar(36)
        occurred_at: datetime
        actor: varchar(255)
        action: varchar(63)
        payload: json
        """

    @schema
    class ProtocolWorkspace(dj.Manual):
        definition = """
        protocol_uuid: varchar(36)
        ---
        project_uuid: varchar(36)
        definition: json
        """
    return Project, Source, Event, ProtocolWorkspace


def validate_protocol_definition(definition):
    if definition.get("format") != "recording-protocol-workspace" or definition.get("version") != 1:
        raise ValueError("Unsupported protocol workspace format/version")
    uuid.UUID(definition["protocol_uuid"])
    uuid.UUID(definition["project_uuid"])
    query = definition.get("query", {})
    clauses = query.get("all", [])
    if set(query) != {"version", "all"} or query.get("version") != 1 or len(clauses) != 1:
        raise ValueError("Unsupported query shape; no fallback to an unrestricted query")
    clause = clauses[0]
    if set(clause) != {"field", "operator", "value"} or clause.get("field") != "EpochBlock.protocol_name" or clause.get("operator") != "eq":
        raise ValueError("Unsupported query field/operator")
    if not isinstance(clause.get("value"), str) or not clause["value"]:
        raise ValueError("Protocol query requires a nonempty acquisition protocol name")
    return clause["value"]


def sync_job_history(project_dir, Event, project_id):
    """Recover terminal pre-connection job records into the database audit log."""
    paths = {p.resolve() for folder in (project_dir / 'logs/imports', project_dir / 'jobs')
             for p in folder.glob('*.json')}
    for path in sorted(paths):
        try:
            job = json.loads(path.read_text())
            if not isinstance(job, dict) or not isinstance(job.get('status'), str):
                raise ValueError('Saved import history must have an object and text status')
            if job.get("status") not in {"failed", "validated", "imported", "already_imported", "complete_with_warnings", "interrupted"}:
                continue
            occurred = dt.datetime.fromisoformat(job["finished_at"]).astimezone(dt.timezone.utc)
            identity = str(uuid.UUID(path.stem))
        except (OSError, ValueError, KeyError, TypeError) as error:
            # Preserve malformed history and surface a durable diagnostic;
            # unrelated old log damage must not break new workspace finalization.
            message = {'stage': 'legacy_job_history', 'job_file': str(path),
                       'error_type': type(error).__name__, 'error': str(error), 'at': now()}
            print('Import history warning: ' + json.dumps(message))
            with contextlib.suppress(OSError):
                write_json(project_dir / 'logs/errors' / ('history-' + hashlib.sha256(str(path).encode()).hexdigest()[:16] + '.json'), message)
            continue
        Event.insert1({"event_uuid": identity, "project_uuid": project_id,
                       "occurred_at": occurred.replace(tzinfo=None),
                       "actor": os.environ.get("USER", "local-user"),
                       "action": "job_" + job["status"],
                       "payload": {"operation_uuid": path.stem, "job_file": str(path), **job}},
                      skip_duplicates=True)


def evaluate_protocol_file(file):
    """Execute a saved protocol query against its project-scoped main catalog."""
    file = Path(file).resolve()
    definition = json.loads(file.read_text())
    name = validate_protocol_definition(definition)
    catalog_path = (file.parent / definition["catalog_ref"]).resolve()
    config = json.loads(catalog_path.read_text())
    if config.get("adapter") != "datajoint" or config.get("database") != "schema":
        raise ValueError("Unsupported catalog adapter/schema")
    if config["project_uuid"] != definition["project_uuid"]:
        raise ValueError("Protocol and catalog project identities differ")
    provider = config["connection"]["credential_provider"]
    dj = connect(configured_container(catalog_path.parent))
    from retinanalysis.config import schema as catalog
    _, Source, _, _ = workspace_tables(dj)
    sources = (Source & {"project_uuid": definition["project_uuid"]}).to_dicts()
    if not sources:
        return {"protocol_uuid": definition["protocol_uuid"], "epochs": [], "cells": []}
    experiment_ids = [{"experiment_id": s["experiment_id"]} for s in sources]
    protocol_rows = (catalog.Protocol & {"name": name}).to_dicts()
    if not protocol_rows:
        return {"protocol_uuid": definition["protocol_uuid"], "epochs": [], "cells": []}
    blocks = (catalog.EpochBlock & experiment_ids &
              [{"protocol_id": r["protocol_id"]} for r in protocol_rows]).to_dicts()
    if not blocks:
        return {"protocol_uuid": definition["protocol_uuid"], "epochs": [], "cells": []}
    epoch_rows = (catalog.Epoch & experiment_ids &
                  [{"parent_id": b["id"]} for b in blocks]).to_dicts()
    group_rows = (catalog.EpochGroup & [{"id": b["parent_id"]} for b in blocks]).to_dicts()
    cell_rows = (catalog.Cell & [{"id": g["parent_id"]} for g in group_rows]).to_dicts()
    return {"protocol_uuid": definition["protocol_uuid"], "protocol_name": name,
            "project_uuid": definition["project_uuid"],
            "epochs": [{"uuid": e["h5_uuid"], "row_id": e["id"],
                        "metadata_hash": hashlib.sha256(json.dumps(
                            {k: e[k] for k in ["parameters", "properties", "attributes"]},
                            sort_keys=True, allow_nan=False).encode()).hexdigest()} for e in epoch_rows],
            "cells": [{"uuid": c["h5_uuid"], "label": c["label"], "type": c["type"]} for c in cell_rows],
            "source_revisions": [s["source_sha256"] for s in sources]}


def import_catalog(project_dir, experiment, manifest, folder, container, progress=None):
    emit = progress or (lambda stage, **fields: None)
    dj = connect(container)
    from retinanalysis.config import schema as catalog
    from retinanalysis.utils import database_pop as population

    Project, Source, Event, ProtocolWorkspace = workspace_tables(dj)
    project_file = project_dir / "project.json"
    project = json.loads(project_file.read_text()) if project_file.exists() else {
        "format": "recording-project", "version": 1, "project_uuid": str(uuid.uuid4()),
        "name": "RetinaSRM", "catalog_ref": "catalog.json"}
    write_json(project_file, project)
    project_id = project["project_uuid"]
    connection = catalog.schema.connection
    lock = connection.query("SELECT GET_LOCK('recording_workspace_import', 30)").fetchone()[0]
    if lock != 1:
        raise RuntimeError("Another workspace import is running")
    def event(action, payload):
        from workspace_audit import build_audit_payload
        actor = os.environ.get("USER", "local-user")
        Event.insert1({"event_uuid": str(uuid.uuid4()), "project_uuid": project_id,
                       "occurred_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                       "actor": actor, "action": action,
                       "payload": build_audit_payload(action, actor,
                           {"operation_uuid": manifest.get("operation_uuid"), **payload},
                           parser_manifest=manifest,
                           outcome="failed" if action.endswith("failed") else "completed",
                           inputs={"source_path": manifest["source_path"], "source_sha256": manifest["source_sha256"]},
                           context={"project_uuid": project_id})})
    stage = "database_transaction"
    emit("writing_catalog", commit_state="unknown", catalog_committed=None)
    try:
        with connection.transaction:
            Project.insert1({"project_uuid": project_id, "name": project["name"],
                             "directory": str(project_dir)}, skip_duplicates=True)
            existing = Source & {"source_sha256": manifest["source_sha256"]}
            if existing:
                old = existing.fetch1()
                if old["project_uuid"] != project_id:
                    raise ValueError("Source belongs to another project; explicit linking is required")
                experiment_id = old["experiment_id"]
                outcome = "already_imported"
            else:
                if catalog.Experiment & [{"h5_uuid": experiment["uuid"]},
                                         {"exp_name": Path(manifest["source_path"]).stem}]:
                    raise ValueError("Existing experiment needs source/version reconciliation")
                assert_new_catalog_identities(experiment, catalog)
                population.configure_tables(catalog)
                population.append_experiment(str(folder / "metadata.catalog.json"),
                    manifest["source_path"], str(folder / "tags.json"), experiment,
                    os.environ.get("USER", "local-user"), {})
                experiment_id = (catalog.Experiment & {"h5_uuid": experiment["uuid"]}).fetch1("id")
                outcome = "imported"
                Source.insert1({"source_sha256": manifest["source_sha256"],
                                "project_uuid": project_id, "experiment_uuid": experiment["uuid"],
                                "experiment_id": experiment_id, "manifest": manifest})
            actual_ids = {str(r["h5_uuid"]) for r in (catalog.Epoch & {"experiment_id": experiment_id}).to_dicts()}
            expected_ids = {e["uuid"] for *_, e in epochs(experiment)}
            if actual_ids != expected_ids:
                raise ValueError("Catalog epoch membership differs from parsed source")
            if len(catalog.Cell & {"experiment_id": experiment_id}) != manifest["counts"]["cells"]:
                raise ValueError("Catalog cell count differs from source")
            db_epochs = (catalog.Epoch & {"experiment_id": experiment_id}).to_dicts()
            expected = {e["uuid"]: e for *_, e in epochs(experiment)}
            response_count = stimulus_count = 0
            emit("verifying_catalog", completed=0, total=len(db_epochs), unit="epochs")
            for epoch_index, row in enumerate(db_epochs, 1):
                epoch = expected[row["h5_uuid"]]
                if row["parameters"] != epoch["parameters"] or row["attributes"] != epoch["attributes"]:
                    raise ValueError("Catalog epoch parameters/attributes changed during insertion")
                for table, key in [(catalog.Response, "responses"), (catalog.Stimulus, "stimuli")]:
                    actual_streams = (table & {"parent_id": row["id"]}).to_dicts()
                    actual = {(r["h5_uuid"], r["device_name"], r["h5path"]) for r in actual_streams}
                    wanted = {(s["uuid"], device, s["h5path"]) for device, s in epoch[key].items()}
                    if actual != wanted:
                        raise ValueError("Catalog stream identity/device/path differs from source")
                    if key == "responses":
                        response_count += len(actual)
                    else:
                        stimulus_count += len(actual)
                emit("verifying_catalog", completed=epoch_index, total=len(db_epochs), unit="epochs")
            if (response_count, stimulus_count) != (manifest["counts"]["responses"], manifest["counts"]["stimuli"]):
                raise ValueError("Catalog stream counts differ from source")
            event(outcome, {"source_sha256": manifest["source_sha256"],
                            "experiment_uuid": experiment["uuid"],
                            "counts": manifest["counts"], "warnings": manifest["warnings"]})
        stage = "workspace_files"
        emit("catalog_committed", commit_state="committed", catalog_committed=True, counts=manifest["counts"])
        sync_job_history(project_dir, Event, project_id)
        catalog_file = {"format": "recording-catalog-reference", "version": 1,
                        "catalog_id": "retinanalysis-local", "adapter": "datajoint",
                        "database": "schema", "workspace_database": "recording_workspace",
                        "connection": {"host": "127.0.0.1", "port": int(dj.config["database.port"]),
                                       "credential_provider": {"kind": "docker-container-env",
                                                               "container": str(container)}},
                        "project_uuid": project_id}
        existing_catalog = project_dir / 'catalog.json'
        if existing_catalog.exists():
            catalog_file = json.loads(existing_catalog.read_text())
        write_json(existing_catalog, catalog_file)
        definitions = []
        emit("finalizing_files", completed=0, total=len(manifest["protocol_epoch_counts"]), unit="protocols")
        for name in sorted(manifest["protocol_epoch_counts"]):
            protocol_id = str(uuid.uuid5(uuid.UUID(project_id), name))
            slug = re.sub(r"(?<!^)(?=[A-Z])", "-", name.rsplit(".", 1)[-1]).lower()
            file = project_dir / "protocols" / (slug + "-" + protocol_id[:8] + ".protocol.json")
            if file.exists():
                definition = json.loads(file.read_text())
            else:
                definition = {"format": "recording-protocol-workspace", "version": 1,
                    "protocol_uuid": protocol_id, "project_uuid": project_id,
                    "name": name.rsplit(".", 1)[-1], "catalog_ref": "../catalog.json",
                    "query": {"version": 1, "all": [{"field": "EpochBlock.protocol_name",
                               "operator": "eq", "value": name}]},
                    "view": {"group_by": ["cell.type", "cell.start_time"],
                             "layout": "landscape", "sidebar_visible": True},
                    "datasets": [], "exports": [], "figures": []}
            definition.pop("last_import", None)
            definition["last_import_check"] = {"source_sha256": manifest["source_sha256"],
                                               "epochs": manifest["protocol_epoch_counts"][name],
                                               "outcome": outcome, "at": now()}
            validate_protocol_definition(definition)
            write_json(file, definition)
            ProtocolWorkspace.insert1({"protocol_uuid": protocol_id,
                "project_uuid": project_id, "definition": definition}, replace=True)
            definitions.append(str(file))
            emit("finalizing_files", completed=len(definitions), total=len(manifest["protocol_epoch_counts"]), unit="protocols")
        manifest = dict(manifest, status=outcome, experiment_id=experiment_id,
                        project_uuid=project_id, imported_at=now(), protocol_files=definitions)
        write_json(folder / "import-manifest.json", manifest)
        event("protocol_files_saved", {"files": definitions, "source_sha256": manifest["source_sha256"]})
        return manifest
    except Exception as error:
        error.catalog_committed = True if stage == "workspace_files" else None
        error.workflow_stage = stage
        failure = {"source_sha256": manifest["source_sha256"],
                   "stage": stage, "catalog_committed": error.catalog_committed,
                   "error_type": type(error).__name__, "error": str(error)}
        try:
            event("workspace_finalize_failed" if error.catalog_committed else "import_failed", failure)
        except Exception as audit_error:
            failure["audit_write_error"] = str(audit_error)
            write_json(folder / ("failure-" + str(uuid.uuid4()) + ".json"), failure)
        raise
    finally:
        # A lost connection releases its advisory lock server-side. Do not mask
        # the original import error with a secondary unlock error.
        with contextlib.suppress(Exception):
            connection.query("SELECT RELEASE_LOCK('recording_workspace_import')")


def configured_container(project_dir, explicit=None):
    """Resolve the adjacent project catalog; never default to a lab container."""
    if explicit:
        return explicit
    path = Path(project_dir) / 'catalog.json'
    try:
        catalog = json.loads(path.read_text())
        provider = catalog['connection']['credential_provider']
        if provider['kind'] == 'native-mysql':
            return Path(project_dir).resolve()
        container = provider['container']
        if provider['kind'] != 'docker-container-env' or not isinstance(container, str) or not container.strip():
            raise ValueError('Unsupported project database credential provider')
        return container
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError('Choose/create a project with catalog.json, or pass --container explicitly; no default database is selected.') from error


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("--project-dir", type=Path, required=True)
    ap.add_argument("--retinanalysis", type=Path, required=True)
    ap.add_argument("--container", help="Override the adjacent project catalog container (never inferred from a lab default)")
    ap.add_argument("--parse-only", action="store_true")
    ap.add_argument("--progress-file", type=Path)
    ap.add_argument("--expected-sha256")
    args = ap.parse_args()
    from workspace_import_progress import ProgressReporter
    reporter = ProgressReporter(args.progress_file)
    source, project_dir = args.source.resolve(), args.project_dir.resolve()
    job_file = project_dir / "logs/imports" / (str(uuid.uuid4()) + ".json")
    job = {"source": str(source), "started_at": now(), "status": "validating"}
    write_json(job_file, job)
    try:
        if args.expected_sha256 is not None and not re.fullmatch('[0-9a-f]{64}', args.expected_sha256):
            raise ValueError('Expected SHA256 must be 64 lowercase hexadecimal characters')
        container = configured_container(project_dir, args.container) if not args.parse_only else None
        reporter.emit('source_hashing', child_job_file=str(job_file))
        experiment, rows, manifest, folder = prepare(source, project_dir, args.retinanalysis,
            reporter.emit, args.expected_sha256)
        manifest["operation_uuid"] = job_file.stem
        if not args.parse_only:
            job["status"] = "importing"
            write_json(job_file, job)
            manifest = import_catalog(project_dir, experiment, manifest, folder, container, reporter.emit)
        job.update(status=manifest["status"], finished_at=now(),
                   manifest=str(folder / "import-manifest.json"))
        write_json(job_file, job)
        reporter.emit('complete', outcome='completed', counts=manifest['counts'],
            catalog_committed=not args.parse_only, commit_state='not_started' if args.parse_only else 'committed',
            manifest=str(folder / 'import-manifest.json'))
        print(json.dumps({"status": manifest["status"], "counts": manifest["counts"],
                          "manifest": job["manifest"], "job": str(job_file)}, indent=2))
    except Exception as error:
        error_message = str(error) or f'{type(error).__name__} during {reporter.current.get("stage", "validation")} for {source.name}; inspect the parser log and traceback.'
        known_commit = (True if reporter.current.get('commit_state') == 'committed' else
                        None if reporter.current.get('commit_state') == 'unknown' else False)
        committed = True if known_commit is True else getattr(error, 'catalog_committed', known_commit)
        job.update(status='complete_with_warnings' if committed is True else 'interrupted' if committed is None else 'failed',
                   finished_at=now(), error_type=type(error).__name__, error=error_message,
                   stage=getattr(error, "workflow_stage", reporter.current.get('stage', 'validation')),
                   catalog_committed=committed)
        write_json(job_file, job)
        job_file.with_suffix(".traceback.txt").write_text(traceback.format_exc())
        reporter.emit('failed', outcome='failed', error_type=type(error).__name__, error=error_message,
            workflow_stage=job['stage'], catalog_committed=job['catalog_committed'],
            commit_state='committed' if job['catalog_committed'] is True else 'unknown' if job['catalog_committed'] is None else 'not_started',
            traceback_path=str(job_file.with_suffix('.traceback.txt')))
        raise SystemExit(f"Import stopped: {type(error).__name__}: {error_message}. Details: {job_file}")


if __name__ == "__main__":
    main()
