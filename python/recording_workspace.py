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

from workspace_catalog_identity import CatalogIdentityConflict, validate_catalog_identity


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
    from workspace_state_snapshot import atomic_write

    path = Path(path)
    # Finish strict serialization before touching the destination. Atomic
    # replacement alone does not persist the file or its directory entry.
    data = (json.dumps(value, indent=2, allow_nan=False, default=json_scalar) + "\n").encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, data, preserve_permissions=True)


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


def assert_new_catalog_identities(experiment, catalog, batch_size=200, *, lookup=None):
    """Reject reused source hierarchy identities before a new file is populated.

    Call only in the new-SHA branch while holding the import advisory lock and
    transaction. RetinAnalysis's h5_uuid columns are not unique keys; a later
    read-model rejection would be too late to prevent ambiguous catalog rows.
    Matching scientific values or repeated trials are not duplicate identities.
    """
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError('Identity lookup batches must contain 1–500 identities')
    identities = {name: set() for name in ('Animal', 'Preparation', 'Cell', 'EpochGroup', 'EpochBlock', 'Epoch', 'Response', 'Stimulus')}

    def record(table, item):
        identity = item.get('uuid')
        if not isinstance(identity, str) or not identity or len(identity) > 255:
            raise ValueError(f'Missing or invalid {table} source UUID')
        if identity in identities[table]:
            raise ValueError(f'Repeated {table} source UUID within recording: {identity}; explicit reconciliation is required')
        identities[table].add(identity)

    for animal in experiment['animals']:
        record('Animal', animal)
        for preparation in animal['preparations']:
            record('Preparation', preparation)
            for cell in preparation['cells']:
                record('Cell', cell)
                for group in cell['epoch_groups']:
                    record('EpochGroup', group)
                    for block in group['epoch_blocks']:
                        record('EpochBlock', block)
                        for epoch in block['epochs']:
                            record('Epoch', epoch)
                            for kind, key in (('Response', 'responses'), ('Stimulus', 'stimuli')):
                                for stream in epoch.get(key, {}).values():
                                    record(kind, stream)
    for name, values in identities.items():
        ordered = sorted(values)
        table = getattr(catalog, name)
        collision = None
        if lookup is not None:
            collision = lookup.first_collision(name, ordered, batch_size)
        else:
            for start in range(0, len(ordered), batch_size):
                batch = [{'h5_uuid': identity} for identity in ordered[start:start + batch_size]]
                found = (table & batch).fetch('h5_uuid', limit=1)
                if len(found):
                    collision = found[0]
                    break
        if collision is not None:
            raise CatalogIdentityConflict('source_uuid_collision',
                f'Existing {name} source UUID {collision} belongs to the catalog; '
                'explicit source/version reconciliation is required before importing this different file',
                identity=collision)


def validate_self_contained_h5(h5):
    """Inspect links/layouts without reading samples or following external files.

    Walk physical hard-linked objects once: Symphony includes experiment/source
    backlinks. Inspect every hard-link alias's containing group, and resolve soft
    links only after external links everywhere in this file have been ruled out.
    """
    import h5py
    pending, seen, soft_links = ['/'], set(), []
    while pending:
        obj = h5[pending.pop()]
        address = h5py.h5o.get_info(obj.id).addr
        if address in seen:
            continue
        seen.add(address)
        if isinstance(obj, h5py.Dataset):
            if obj.is_virtual:
                raise ValueError(f'Virtual dataset dependencies are unsupported: {obj.name}')
            if obj.external:
                raise ValueError(f'External dataset storage is unsupported: {obj.name}')
        elif isinstance(obj, h5py.Group):
            for name in obj:
                link = obj.get(name, getlink=True)
                if isinstance(link, h5py.ExternalLink):
                    raise ValueError(f'External H5 links are unsupported: {obj.name}/{name}')
                if isinstance(link, h5py.SoftLink):
                    soft_links.append(obj.name.rstrip('/') + '/' + name)
                elif isinstance(link, h5py.HardLink):
                    pending.append(obj.name.rstrip('/') + '/' + name)
                else:
                    raise ValueError(f'Unsupported H5 link: {obj.name}/{name}')
    for path in soft_links:
        target = resolve_sealed_h5_path(h5, path)
        if h5py.h5o.get_info(target.id).addr not in seen:
            raise ValueError(f'H5 link target is outside the sealed source: {path}')


def resolve_sealed_h5_path(h5, path):
    """Resolve one locator without following unsealed links (bounded trace path).

    Inspect each soft-link expansion, including its intermediate components;
    inspecting only the final object's filename misses external links that lead
    back into this file, virtual mappings and external raw-storage datasets.
    """
    import h5py
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('H5 locator must be an absolute path within its source')
    parts, current, expansions = path.split('/')[1:], h5['/'], 0
    while parts:
        name, parts = parts[0], parts[1:]
        if not name or name == '.':
            continue
        if name == '..' or not isinstance(current, h5py.Group):
            raise ValueError(f'Invalid H5 source locator: {path}')
        link = current.get(name, getlink=True)
        if isinstance(link, h5py.ExternalLink):
            raise ValueError(f'External H5 links are unsupported: {path}')
        if isinstance(link, h5py.SoftLink):
            expansions += 1
            if expansions > 64:
                raise ValueError(f'Unresolvable or cyclic H5 soft link: {path}')
            target = link.path
            if not target.startswith('/'):
                target = current.name.rstrip('/') + '/' + target
            parts, current = target.split('/')[1:] + parts, h5['/']
            continue
        if not isinstance(link, h5py.HardLink):
            raise ValueError(f'Missing or unsupported H5 source link: {path}')
        current = current[name]
        if current.file.id != h5.id:
            raise ValueError(f'H5 link target is outside the sealed source: {path}')
    if isinstance(current, h5py.Dataset):
        if current.is_virtual:
            raise ValueError(f'Virtual dataset dependencies are unsupported: {path}')
        if current.external:
            raise ValueError(f'External dataset storage is unsupported: {path}')
    return current


def _source_text(value):
    return value.decode('utf-8') if isinstance(value, bytes) else str(value)


def validate_source_identity(h5, document):
    """Compare parser hierarchy to physical Symphony objects, including empties.

    UUID dictionaries are built only after checking physical multiplicity. The
    source hierarchy is experiment/sources/animal/sources/preparation/sources/cell;
    epoch groups reference cells by an in-file source link, not by display label.
    The pinned parser deliberately drops blocks without epochs, so those may be
    absent from metadata, but still participate in duplicate-identity checks.
    """
    import h5py
    validate_self_contained_h5(h5)
    roots = [h5[name] for name in h5 if name.startswith('experiment-')]
    if len(roots) != 1 or not isinstance(roots[0], h5py.Group):
        raise ValueError('Expected exactly one Symphony experiment root')
    root = roots[0]

    def identity(obj):
        if not isinstance(obj, h5py.Group) or 'uuid' not in obj.attrs:
            raise ValueError(f'Missing source object UUID: {obj.name}')
        value = _source_text(obj.attrs['uuid'])
        if not value or len(value) > 255:
            raise ValueError(f'Invalid source object UUID: {obj.name}')
        return value

    if identity(root) != document['uuid']:
        raise ValueError('Experiment identity differs from H5 source')
    inventory = {kind: {} for kind in ('animal', 'preparation', 'cell', 'group', 'block', 'epoch', 'stream')}
    parsed = {kind: set() for kind in inventory}

    def children(obj, collection):
        if collection not in obj:
            return []
        container = obj[collection]
        if not isinstance(container, h5py.Group):
            raise ValueError(f'Invalid source {collection} collection: {container.name}')
        return container.items()

    def record(category, obj, parent, **fields):
        kind = category
        value = identity(obj)
        if value in inventory[kind]:
            raise ValueError(f'Duplicate source {kind} UUID: {value}')
        inventory[kind][value] = dict(path=obj.name, address=h5py.h5o.get_info(obj.id).addr, parent=parent, **fields)
        return value

    for _, animal in children(root, 'sources'):
        animal_id = record('animal', animal, document['uuid'])
        for _, prep in children(animal, 'sources'):
            prep_id = record('preparation', prep, animal_id)
            for _, cell in children(prep, 'sources'):
                record('cell', cell, prep_id)
    for _, group in children(root, 'epochGroups'):
        if 'source' not in group:
            raise ValueError('Epoch group has no source cell identity')
        cell_obj = group['source']
        cell_id = identity(cell_obj)
        if cell_id not in inventory['cell'] or inventory['cell'][cell_id]['address'] != h5py.h5o.get_info(cell_obj.id).addr:
            raise ValueError('Epoch group source cell identity differs from the experiment sources')
        group_id = record('group', group, cell_id)
        for _, block in children(group, 'epochBlocks'):
            raw_epochs = children(block, 'epochs')
            block_id = record('block', block, group_id, empty=not raw_epochs)
            for _, epoch in raw_epochs:
                epoch_id = record('epoch', epoch, block_id)
                for kind in ('responses', 'stimuli'):
                    for key, stream in children(epoch, kind):
                        # This is Symphony's device-UUID naming convention and the
                        # pinned parser's strip_uuid operation, independently checked.
                        device = '-'.join(key.split('-')[:-5])
                        if not device:
                            raise ValueError('Source stream device identity is missing')
                        record('stream', stream, epoch_id, kind=kind, device=device)

    def check(kind, item, parent):
        value = item.get('uuid')
        source = inventory[kind].get(value)
        if source is None or value in parsed[kind]:
            if kind == 'block':
                raise ValueError('Epoch points to a different source block')
            raise ValueError(f'Parsed {kind} identity or membership differs from H5 source')
        parsed[kind].add(value)
        if source['parent'] != parent:
            if kind == 'group':
                raise ValueError('Parsed group ownership differs from its source cell')
            raise ValueError(f'Parsed {kind} parent ownership differs from H5 source')
        return source

    for animal in document['animals']:
        check('animal', animal, document['uuid'])
        for prep in animal['preparations']:
            check('preparation', prep, animal['uuid'])
            for cell in prep['cells']:
                check('cell', cell, prep['uuid'])
                for group in cell['epoch_groups']:
                    check('group', group, cell['uuid'])
                    for block in group['epoch_blocks']:
                        source_block = h5[check('block', block, group['uuid'])['path']]
                        if _source_text(source_block.attrs.get('protocolID', '')) != block['protocolID']:
                            raise ValueError('Parsed protocol differs from the H5 block')
                        for epoch in block['epochs']:
                            check('epoch', epoch, block['uuid'])
                            for kind in ('responses', 'stimuli'):
                                for device, stream in epoch.get(kind, {}).items():
                                    source = check('stream', stream, epoch['uuid'])
                                    try:
                                        target = h5[stream['h5path']]
                                    except (KeyError, TypeError) as error:
                                        raise ValueError('Parsed stream locator differs from H5 source') from error
                                    if source['address'] != h5py.h5o.get_info(target.id).addr or source['kind'] != kind or source['device'] != device:
                                        raise ValueError('Parsed stream identity, kind or device differs from H5 source')
                                    # Readers use ancestry of the locator, so aliases must
                                    # retain its authoritative epoch/collection context.
                                    if (target.parent.name.rsplit('/', 1)[-1] != kind or
                                            identity(target.parent.parent) != epoch['uuid']):
                                        raise ValueError('Parsed stream locator ownership differs from H5 source')
    for kind, objects in inventory.items():
        required = {key for key, value in objects.items() if kind != 'block' or not value['empty']}
        if not required <= parsed[kind]:
            raise ValueError(f'Parsed {kind} membership differs from the H5 source')
    return inventory


def restore_empty_blocks(h5, experiment, parser):
    """Preserve canonical acquisition blocks the pinned parser omits as empty.

    Production callers first validate physical hierarchy and identity. Walk only
    canonical experiment/epochGroups paths so hard-linked backlinks cannot hide
    blocks. Never reconstruct a missing populated block or guess its parent.
    """
    import h5py
    validate_self_contained_h5(h5)
    groups = {}
    for animal in experiment['animals']:
        for preparation in animal['preparations']:
            for cell in preparation['cells']:
                for group in cell['epoch_groups']:
                    if group['uuid'] in groups:
                        raise ValueError('Duplicate parsed epoch group identity')
                    groups[group['uuid']] = group
    roots = [h5[name] for name in h5 if name.startswith('experiment-')]
    if len(roots) != 1 or not isinstance(roots[0], h5py.Group):
        raise ValueError('Expected exactly one Symphony experiment root')
    additions, seen = [], set()
    for source_group in roots[0].get('epochGroups', {}).values():
        group_uuid = _source_text(source_group.attrs['uuid'])
        if group_uuid not in groups:
            raise ValueError('Source epoch group is missing from parsed metadata')
        group = groups[group_uuid]
        existing = {block['uuid'] for block in group['epoch_blocks']}
        for source_block in source_group.get('epochBlocks', {}).values():
            identity = _source_text(source_block.attrs['uuid'])
            if identity in seen:
                raise ValueError('Duplicate source block UUID')
            seen.add(identity)
            if identity in existing:
                continue
            if len(source_block.get('epochs', {})):
                raise ValueError('Missing populated block cannot be reconstructed')
            block = dict(parser.EpochBlockObj(source_block).__dict__)
            if block.get('uuid') != identity or block.get('epochs') != []:
                raise ValueError('Empty block parser identity or membership differs from source')
            # Use the same pinned conversions as ordinary blocks, retaining
            # protocol parameters, source attributes and acquisition timestamps.
            block = json.loads(json.dumps(block, cls=getattr(parser, 'NpEncoder', None),
                                          default=None if hasattr(parser, 'NpEncoder') else json_scalar,
                                          allow_nan=False))
            additions.append((group, block, group_uuid))
    for group, block, _ in additions:
        group['epoch_blocks'].append(block)
    return [{'code': 'empty_epoch_block_restored', 'uuid': block['uuid'], 'group_uuid': group_uuid}
            for _, block, group_uuid in additions]


def validate_manifest_cell_count(manifest, all_cell_ids, epoch_cell_ids):
    """Check the recorded count under its explicit or historical convention.

    Before all-source-cells-v1, prepare counted only cells reached by epochs.
    This affects the count check only: callers must still validate and retain
    every source cell, including cells with no epochs.
    """
    semantics = manifest.get('cell_count_semantics')
    if 'cell_count_semantics' not in manifest:
        expected = len(epoch_cell_ids)
    elif semantics == 'all-source-cells-v1':
        expected = len(all_cell_ids)
    else:
        raise ValueError(f'Unsupported source cell count semantics: {semantics!r}')
    if manifest['counts']['cells'] != expected:
        raise ValueError('Source cell count differs from validated manifest')


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
        # Reject unsealed dependencies before the parser can read their samples.
        with h5py.File(source, "r") as h5:
            validate_self_contained_h5(h5)
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
        roots = [k for k in h5 if k.startswith("experiment-")]
        if len(roots) != 1:
            raise ValueError("Expected exactly one Symphony experiment root")
        root = resolve_sealed_h5_path(h5, "/" + roots[0])
        properties = resolve_sealed_h5_path(h5, root.name + "/properties")
        # RetinAnalysis currently builds ExperimentObj from the first animal.
        # Reuse its conversion while restoring the real experiment-level facts.
        experiment = parser.ExperimentObj(
            d={"attributes": parser.parse_attributes(root),
               "properties": parser.parse_attributes(properties)},
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
        inventory = validate_source_identity(h5, experiment)
        warnings.extend(restore_empty_blocks(h5, experiment, parser))
        cell_ids.update(inventory["cell"])
        for cell, group, block, epoch in epochs(experiment):
            cell_ids.add(cell["uuid"])
            streams = []
            source_epoch = h5[inventory['epoch'][epoch['uuid']]['path']]
            source_block = h5[inventory['block'][block['uuid']]['path']]
            source_parameters = dict(source_block['protocolParameters'].attrs)
            source_parameters.update(dict(source_epoch['protocolParameters'].attrs))
            source_parameters = json.loads(json.dumps(source_parameters, cls=parser.NpEncoder, allow_nan=False))
            for parameter, value in source_parameters.items():
                if parameter not in epoch['parameters'] or epoch['parameters'][parameter] != value:
                    raise ValueError(f"Source parameter mismatch for epoch {epoch['uuid']}: {parameter}")
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
                "cell_count_semantics": "all-source-cells-v1",
                "counts": {"cells": len(cell_ids), "epochs": len(rows),
                           "responses": sum(len(e["responses"]) for *_, e in epochs(experiment)),
                           "stimuli": sum(len(e["stimuli"]) for *_, e in epochs(experiment))},
                "protocol_epoch_counts": protocol_counts, "warnings": warnings}
    write_json(folder / "import-manifest.json", manifest)
    return experiment, rows, manifest, folder


def connect(container, *, project_dir=None):
    import datajoint as dj
    if isinstance(container, dict):
        if container.get('kind') != 'native-project' or project_dir is None:
            raise ValueError('Native database connections require the owning project folder')
        from workspace_native_mysql import connection_parameters
        parameters = connection_parameters(project_dir)
        for key in ('host', 'port', 'user', 'password'):
            dj.config['database.' + key] = parameters[key]
        return dj
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
    if provider["kind"] not in {"docker-container-env", "native-project"}:
        raise ValueError("Unsupported credential provider")
    dj = (connect(provider, project_dir=catalog_path.parent) if provider['kind'] == 'native-project'
          else connect(provider['container']))
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


def new_project_protocol_types(catalog, Source, project_id, incoming_names):
    """Find new acquisition names with a project-scoped SQL semi-join.

    Only names in this import are returned from SQL; epochs and catalog metadata
    are never loaded to count protocol types. Saved/pinned queries are unrelated.
    """
    incoming = set(incoming_names)
    if not incoming:
        return set()
    # Source.experiment_id is a plain integer rather than a DataJoint FK.
    # Materialize only these small registration keys to avoid an invalid
    # relational restriction across incompatible attribute lineages.
    experiment_ids = (Source & {'project_uuid': project_id}).fetch('experiment_id')
    if not len(experiment_ids):
        return incoming
    blocks = (catalog.EpochBlock & [{'experiment_id': int(key)} for key in experiment_ids]).proj('protocol_id')
    existing = (catalog.Protocol & [{'name': name} for name in sorted(incoming)] & blocks).fetch('name')
    return incoming - set(existing)


def import_catalog(project_dir, experiment, manifest, folder, container, progress=None):
    emit = progress or (lambda stage, **fields: None)
    dj = connect(container, project_dir=project_dir) if isinstance(container, dict) else connect(container)
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
    from workspace_catalog_collision import CatalogCollisionLookup
    identity_lookup = CatalogCollisionLookup(catalog)
    try:
        # Temporary candidate indexes belong to this locked connection and are
        # created before the transaction: no DDL may commit acquisition writes.
        identity_lookup.prepare()
        with connection.transaction:
            Project.insert1({"project_uuid": project_id, "name": project["name"],
                             "directory": str(project_dir)}, skip_duplicates=True)
            existing = Source & {"source_sha256": manifest["source_sha256"]}
            if existing:
                old = existing.fetch1()
                if old["project_uuid"] != project_id:
                    raise ValueError("Source belongs to another project; explicit linking is required")
                if old['experiment_uuid'] != experiment['uuid']:
                    raise CatalogIdentityConflict('source_registration',
                        'Registered source experiment UUID differs from these same source bytes',identity=experiment['uuid'])
                experiment_id = old["experiment_id"]
                outcome = "already_imported"
                protocol_types_added = 0
            else:
                if catalog.Experiment & {"h5_uuid": experiment["uuid"]}:
                    raise CatalogIdentityConflict('source_revision_conflict',
                        'This experiment acquisition UUID is already associated with different source bytes',identity=experiment['uuid'])
                if catalog.Experiment & {"exp_name": Path(manifest["source_path"]).stem}:
                    # RetinAnalysis consumers still select experiments by name.
                    # Do not silently rename scientific identifiers or permit
                    # ambiguous downstream selection while that contract exists.
                    raise CatalogIdentityConflict('experiment_name_collision',
                        'A different acquisition uses this experiment filename. Matching names do not establish duplicate data; choose an explicitly qualified import filename before retrying',identity=experiment['uuid'])
                assert_new_catalog_identities(experiment, catalog, lookup=identity_lookup)
                protocol_types_added = len(new_project_protocol_types(
                    catalog, Source, project_id, manifest['protocol_epoch_counts']))
                population.configure_tables(catalog)
                population.append_experiment(str(folder / "metadata.catalog.json"),
                    manifest["source_path"], str(folder / "tags.json"), experiment,
                    os.environ.get("USER", "local-user"), {})
                experiment_id = (catalog.Experiment & {"h5_uuid": experiment["uuid"]}).fetch1("id")
                outcome = "imported"
                Source.insert1({"source_sha256": manifest["source_sha256"],
                                "project_uuid": project_id, "experiment_uuid": experiment["uuid"],
                                "experiment_id": experiment_id, "manifest": manifest})
            all_cell_ids = {cell['uuid'] for animal in experiment['animals']
                            for preparation in animal['preparations'] for cell in preparation['cells']}
            epoch_cell_ids = {cell['uuid'] for cell, *_ in epochs(experiment)}
            validate_manifest_cell_count(manifest, all_cell_ids, epoch_cell_ids)
            # Catalog population retains all cells under either manifest convention.
            # Same-SHA rechecks must not compare this total to a legacy active count.
            counts = validate_catalog_identity(experiment, catalog, experiment_id, emit)
            if counts['Cell'] != len(all_cell_ids):
                raise ValueError("Catalog cell count differs from source")
            if counts['Epoch'] != manifest['counts']['epochs']:
                raise ValueError('Catalog epoch count differs from source')
            if (counts['Response'], counts['Stimulus']) != (manifest["counts"]["responses"], manifest["counts"]["stimuli"]):
                raise ValueError("Catalog stream counts differ from source")
            event(outcome, {"source_sha256": manifest["source_sha256"],
                            "experiment_uuid": experiment["uuid"],
                            "counts": manifest["counts"], "warnings": manifest["warnings"]})
        # A cleanup failure after commit must report persisted catalog state,
        # never suggest that the completed acquisition transaction rolled back.
        stage = "workspace_files"
        identity_lookup.close()
        # Every new Cell/Epoch UUID was checked absent under the import lock,
        # then inserted membership and stream counts were verified in the
        # transaction above. These are actual additions, not source totals.
        manifest['catalog_delta'] = {
            'sources_added': int(outcome == 'imported'),
            'protocol_types_added': protocol_types_added,
            **{key + '_added': manifest['counts'][key] if outcome == 'imported' else 0
               for key in ('cells', 'epochs', 'responses', 'stimuli')}}
        stage = "workspace_files"
        emit("catalog_committed", commit_state="committed", catalog_committed=True,
             counts=manifest["counts"], catalog_delta=manifest['catalog_delta'])
        sync_job_history(project_dir, Event, project_id)
        existing_catalog = json.loads((project_dir / 'catalog.json').read_text()) if (project_dir / 'catalog.json').exists() else {}
        catalog_file = {**existing_catalog, "format": "recording-catalog-reference", "version": 1,
                        "catalog_id": "retinanalysis-local", "adapter": "datajoint",
                        "database": "schema", "workspace_database": "recording_workspace",
                        "connection": {"host": "127.0.0.1", "port": int(dj.config["database.port"]),
                                       "credential_provider": container if isinstance(container, dict) else
                                           {"kind": "docker-container-env", "container": container}},
                        "project_uuid": project_id}
        write_json(project_dir / "catalog.json", catalog_file)
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
                    "view": {"group_by": ["cell type", "metadata/cell/start_time"],
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
        if isinstance(error, CatalogIdentityConflict):
            failure['identity_conflict'] = error.conflict
        try:
            event("workspace_finalize_failed" if error.catalog_committed else "import_failed", failure)
        except Exception as audit_error:
            failure["audit_write_error"] = str(audit_error)
            write_json(folder / ("failure-" + str(uuid.uuid4()) + ".json"), failure)
        raise
    finally:
        # Rollback has already ended before scratch cleanup. Its own fallback
        # closes the owning connection if temporary-table removal fails.
        with contextlib.suppress(Exception):
            identity_lookup.close()
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
        container = provider['container']
        if provider['kind'] != 'docker-container-env' or not isinstance(container, str) or not container.strip():
            raise ValueError('Unsupported project database credential provider')
        return container
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError('Choose/create a project with catalog.json, or pass --container explicitly; no default database is selected.') from error


def configured_database(project_dir, explicit=None):
    """Choose the project's private native runtime; retain explicit legacy access."""
    if explicit:
        return explicit
    try:
        catalog = json.loads((Path(project_dir) / 'catalog.json').read_text())
        provider = catalog['connection']['credential_provider']
        if provider.get('kind') == 'native-project':
            if provider.get('credentials_ref') != 'database/native-credentials.json':
                raise ValueError('Unsupported native credential reference')
            return provider
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError('Choose a valid project catalog before connecting to its database') from error
    return configured_container(project_dir)


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
        container = configured_database(project_dir, args.container) if not args.parse_only else None
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
        if isinstance(error, CatalogIdentityConflict):
            job['identity_conflict'] = error.conflict
        write_json(job_file, job)
        job_file.with_suffix(".traceback.txt").write_text(traceback.format_exc())
        reporter.emit('failed', outcome='failed', error_type=type(error).__name__, error=error_message,
            workflow_stage=job['stage'], catalog_committed=job['catalog_committed'],
            commit_state='committed' if job['catalog_committed'] is True else 'unknown' if job['catalog_committed'] is None else 'not_started',
            traceback_path=str(job_file.with_suffix('.traceback.txt')))
        raise SystemExit(f"Import stopped: {type(error).__name__}: {error_message}. Details: {job_file}")


if __name__ == "__main__":
    main()
