"""Exact acquisition identity checks for pinned working datasets.

A display name or a narrowing predicate must never redefine the acquisition
protocol recorded in the workspace's original definition.
"""
from collections import Counter
from recording_workspace import validate_protocol_definition


def selection_protocols(service, identities):
    counts = Counter()
    cells = set()
    for identity in identities:
        row = service.rows.get(identity)
        if row is None or not row.get('protocol_name'):
            raise ValueError('Selection contains an unavailable epoch or missing recorded Protocol ID')
        counts[row['protocol_name']] += 1
        cells.add(row['cell_uuid'])
    return {'epoch_count': sum(counts.values()), 'cell_count': len(cells),
            'protocols': [{'protocol_id': name, 'epoch_count': count} for name, count in sorted(counts.items())]}


def protocol_key(protocol_id):
    """Recorded Protocol IDs match by protocol name across labs: the
    .chris. and .arthur. variants of VariableHistoryNoiseCurInject agree."""
    return protocol_id.rsplit('.', 1)[-1] if isinstance(protocol_id, str) else None


def protocol_ids(service, protocol_uuid):
    """The protocol names an entry accepts; a pinned entry may list several."""
    expected = validate_protocol_definition(service.protocols[protocol_uuid]['definition'])
    return frozenset(protocol_key(value) for value in (expected if isinstance(expected, list) else [expected]))


def protocol_compatibility(service, protocol_uuid, identities):
    expected = validate_protocol_definition(service.protocols[protocol_uuid]['definition'])
    expected_ids = expected if isinstance(expected, list) else [expected]
    summary = selection_protocols(service, identities)
    accepted = {protocol_key(value) for value in expected_ids}
    incompatible = sum(row['epoch_count'] for row in summary['protocols'] if protocol_key(row['protocol_id']) not in accepted)
    return {**summary, 'expected_protocol_id': ' + '.join(expected_ids), 'expected_protocol_ids': expected_ids,
            'compatible': summary['epoch_count'] > 0 and incompatible == 0,
            'incompatible_epoch_count': incompatible}


def require_protocol_compatibility(service, protocol_uuid, identities):
    result = protocol_compatibility(service, protocol_uuid, identities)
    if not result['compatible']:
        if not result['epoch_count']:
            raise ValueError('An empty selection cannot update or export a pinned protocol')
        raise ValueError(f"Protocol mismatch: {result['incompatible_epoch_count']} epochs do not belong to "
                         f"{result['expected_protocol_id']}. Choose a matching pinned protocol or create a new one.")
    return result


def create_pinned_protocol(service, history, record, name, protocol_id, actor):
    """Create a manifest plus an audited binding, with retry-safe identity.

    A new manifest requires its initial binding, so a process interruption
    between filesystem publication and SQL commit fails closed on reload.
    """
    import copy
    import hashlib
    import json
    import uuid
    import contextlib
    from disco.workbench.diff import summarize_diff

    if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(char) < 32 for char in name):
        raise ValueError('Name the new pinned protocol using 1–120 characters')
    name = name.strip()
    recipe = record['recipe']
    identities = [row['uuid'] for row in recipe['epochs']]
    summary = selection_protocols(service, identities)
    protocol_ids = protocol_id if isinstance(protocol_id, list) else [protocol_id]
    if (not protocol_ids or any(not isinstance(value, str) or not value for value in protocol_ids)
            or len(protocol_ids) > 2000 or len(set(protocol_ids)) != len(protocol_ids)
            or set(protocol_ids) != {row['protocol_id'] for row in summary['protocols']}):
        raise ValueError('Review every exact recorded Protocol ID in this selection before creating a pinned protocol.')
    protocol_ids = sorted(protocol_ids)
    protocol_id = protocol_ids[0] if len(protocol_ids) == 1 else protocol_ids
    project_uuid = service.project['project_uuid']
    identity = str(uuid.uuid5(uuid.UUID(project_uuid), 'pinned:' + record['revision_uuid'] + ':' + name.casefold()))
    folder = service.project_dir / 'protocols'
    if folder.is_symlink():
        raise ValueError('Protocol storage must be a local managed directory')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (identity + '.protocol.json')
    definition = {'format': 'recording-protocol-workspace', 'version': 1,
        'project_uuid': project_uuid, 'protocol_uuid': identity, 'name': name,
        'catalog_ref': '../catalog.json', 'initial_revision_uuid': record['revision_uuid'],
        'query': {'version': 1, 'all': [{'field': 'EpochBlock.protocol_name', 'operator': 'eq' if len(protocol_ids) == 1 else 'in', 'value': protocol_id}]},
        'view': {'group_by': recipe['tree_view']['fields'], 'layout': 'landscape'}}
    connection = service.dj.conn()
    lock = hashlib.sha256((project_uuid + identity).encode()).hexdigest()
    if connection.query(f"SELECT GET_LOCK('{lock}', 10)").fetchone()[0] != 1:
        raise RuntimeError('Another pinned protocol creation is running')
    created_file = False
    try:
        if path.is_symlink():
            raise ValueError('Protocol manifest must be a regular local file')
        if path.exists():
            stored = json.loads(path.read_text())
            if {**stored, 'name': name} != definition:
                raise ValueError('A different protocol manifest already uses this identity')
            definition = stored
            name = stored['name']
        existing = history.protocol_binding(identity)
        if existing and existing['revision_uuid'] != record['revision_uuid']:
            raise ValueError('This pinned protocol was already created and updated. Open it instead of recreating it.')
        if not existing:
            with connection.transaction:
                history.bind(record['revision_uuid'], identity, 0, actor,
                    {'added': sorted(identities), 'removed': [], 'changed': []}, 0,
                    diff_summary=summarize_diff(service.rows, {}, {row['uuid']: row['metadata_hash'] for row in recipe['epochs']}),
                    _in_transaction=True, _lock_held=True)
                if not path.exists():
                    with path.open('x') as handle:
                        created_file = True
                        json.dump(definition, handle, indent=2)
                        handle.write('\n')
        elif not path.exists():
            raise ValueError('Pinned protocol manifest is missing; restore the project manifest before retrying')
    except Exception:
        if created_file:
            path.unlink(missing_ok=True)
        raise
    finally:
        with contextlib.suppress(Exception):
            connection.query(f"SELECT RELEASE_LOCK('{lock}')")
    # Make it visible in this server immediately. Refresh reconstructs this same
    # base query from the project catalog, while the binding retains the subset.
    protocol_id = protocol_ids[0] if len(protocol_ids) == 1 else protocol_ids
    base = [row for row in service.rows.values() if row['protocol_name'] in protocol_ids]
    cells = {row['cell_uuid'] for row in base}
    service.protocols[identity] = {'definition': copy.deepcopy(definition), 'file': path,
        'result': {'project_uuid': project_uuid, 'protocol_uuid': identity, 'protocol_name': ' + '.join(protocol_ids),
            'source_revisions': sorted({row['source_sha256'] for row in base}),
            'epochs': [{'uuid': row['epoch_uuid'], 'metadata_hash': row['metadata_hash']} for row in base],
            'cells': [{'uuid': cell, 'label': service.cells[cell]['label'], 'type': service.cells[cell]['cell_type']} for cell in sorted(cells)]}}
    return {'protocol_uuid': identity, 'name': name, 'protocol_id': protocol_id,
            'revision_uuid': record['revision_uuid'], 'created': existing is None, **summary}
