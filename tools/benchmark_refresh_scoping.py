#!/usr/bin/env python3
"""Pre-write refresh cost and read-model identity at growing project sizes.

Owned disposable fixture only; never a user project or live port. A real
WorkspaceService refresh runs against generated imported-metadata JSON and
minimal H5 sources (epochs carry no streams, so no per-epoch H5 reads); the
DataJoint catalog connection, Source table and protocol SQL evaluation are the
python/tests doubles. Measured per size, warm (after the first open):

- ``refresh``: a full ``WorkspaceService.refresh()`` with unchanged inputs.
- ``approve_preflight``: what the approve / explorer-save / mask / export routes
  run before their write: ``verify_sources()`` when the source tree has it,
  otherwise ``refresh()`` (the route behaviour of older trees).

Load-independent counts: source projections decoded, protocol SQL evaluations,
whether ``service.rows`` kept its identity and whether the published read model
(publication serial / explore publication token) changed. Run against any tree
with ``--source-root`` for identical harness bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import uuid


def build(source_root, folder, epochs, sources):
    sys.path[:0] = [str(source_root / 'python'), str(source_root / 'python/tests')]
    import h5py
    from unittest.mock import patch
    import workspace_service as module
    from test_workspace_curation import Table
    folder = Path(folder)
    (folder / 'imports').mkdir()
    (folder / 'protocols').mkdir()
    project, protocol = str(uuid.uuid4()), str(uuid.uuid4())
    (folder / 'project.json').write_text(json.dumps({'project_uuid': project, 'name': 'Benchmark'}))
    (folder / 'catalog.json').write_text(json.dumps({'project_uuid': project, 'adapter': 'datajoint', 'database': 'schema',
        'connection': {'credential_provider': {'kind': 'docker-container-env', 'container': 'unused-fixture'}}}))
    (folder / 'protocols/example.protocol.json').write_text(json.dumps({'format': 'recording-protocol-workspace',
        'version': 1, 'project_uuid': project, 'protocol_uuid': protocol, 'name': 'Example',
        'catalog_ref': '../catalog.json',
        'query': {'version': 1, 'all': [{'field': 'EpochBlock.protocol_name', 'operator': 'eq', 'value': 'example'}]}}))
    table = Table(('source_sha256',))
    per_source = epochs // sources
    for s in range(sources):
        identity = str(uuid.uuid4())
        path = folder / f'source{s}.h5'
        animal_id, prep_id = str(uuid.uuid4()), str(uuid.uuid4())
        cells = []
        with h5py.File(path, 'w') as h5:
            experiment = h5.create_group('/experiment-' + identity)
            experiment.attrs['uuid'] = identity
            animal = experiment.create_group('sources/animal-' + animal_id)
            animal.attrs['uuid'] = animal_id
            animal['experiment'] = experiment
            prep = animal.create_group('sources/preparation-' + prep_id)
            prep.attrs['uuid'] = prep_id
            for c in range(max(1, per_source // 300)):
                cell_id, group_id = str(uuid.uuid4()), str(uuid.uuid4())
                cell_obj = prep.create_group('sources/cell-' + cell_id)
                cell_obj.attrs['uuid'] = cell_id
                group = experiment.create_group('epochGroups/group-' + group_id)
                group.attrs['uuid'] = group_id
                group['source'] = cell_obj
                blocks = []
                for b in range(15):
                    block_id = str(uuid.uuid4())
                    block_obj = group.create_group('epochBlocks/block-' + block_id)
                    block_obj.attrs.update(uuid=block_id, protocolID='example')
                    block_epochs = []
                    for e in range(20):
                        epoch_id = str(uuid.uuid4())
                        block_obj.create_group('epochs/epoch-' + epoch_id).attrs['uuid'] = epoch_id
                        block_epochs.append({'uuid': epoch_id, 'start_time': f'09/24/2026 12:{b:02d}:{e % 60:02d}:000000',
                            'parameters': {'contrast': e % 5 / 4}, 'properties': {}, 'attributes': {},
                            'responses': {}, 'stimuli': {}})
                    blocks.append({'uuid': block_id, 'protocolID': 'example', 'parameters': {},
                                   'start_time': '09/24/2026 12:00:00:000000', 'epochs': block_epochs})
                cells.append({'uuid': cell_id, 'label': f'c{c}', 'type': 'ON parasol',
                              'start_time': '09/24/2026 12:00:00:000000',
                              'epoch_groups': [{'uuid': group_id, 'label': 'Control', 'epoch_blocks': blocks}]})
        document = {'uuid': identity, 'animals': [{'uuid': animal_id, 'preparations': [
            {'uuid': prep_id, 'cells': cells}]}]}
        metadata = folder / 'imports' / f'source{s}.json'
        metadata.write_text(json.dumps(document))
        count = sum(len(block['epochs']) for cell in cells for block in cell['epoch_groups'][0]['epoch_blocks'])
        table.insert1({'project_uuid': project, 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'experiment_uuid': identity, 'experiment_id': s + 1,
            'manifest': {'source_path': str(path), 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'source_size': path.stat().st_size, 'metadata_path': str(metadata),
                'metadata_sha256': hashlib.sha256(metadata.read_bytes()).hexdigest(),
                'counts': {'epochs': count, 'cells': len(cells)}, 'validated_at': '2026-09-24T12:00:00+00:00'}})
    counters = {'sql': 0, 'projections': 0}
    memo = {}

    def evaluate(path, *, catalog_connection, verified_source_metadata=None):
        counters['sql'] += 1
        rows = verified_source_metadata[0]
        key = id(rows), len(rows)
        if key not in memo:
            memo.clear()
            memo[key] = {'epochs': [{'uuid': k, 'metadata_hash': r['metadata_hash']} for k, r in rows.items()],
                         'cells': [{'uuid': c} for c in sorted({r['cell_uuid'] for r in rows.values()})]}
        return json.loads(json.dumps(memo[key]))
    patches = [patch.object(module, 'connect', return_value=object()),
               patch.object(module, 'workspace_tables', return_value=(None, table, None, None)),
               patch.object(module, 'evaluate_protocol_file', evaluate)]
    for item in patches:
        item.start()
    from disco.metadata.disk_index import DiskMetadataIndex
    original = DiskMetadataIndex.source_projection

    def projection(self, *args, **kwargs):
        counters['projections'] += 1
        return original(self, *args, **kwargs)
    DiskMetadataIndex.source_projection = projection
    service = module.WorkspaceService(folder)
    if getattr(service, 'manager_error', None):
        raise RuntimeError('fixture refresh failed: ' + service.manager_error)
    return service, counters, patches, protocol


def published(service):
    return (id(service.rows), getattr(service, '_explore_publication', None), getattr(service, '_publication_serial', None))


def measure(service, counters, call, repeats):
    samples, observations = [], []
    for _ in range(repeats):
        before = dict(counters), published(service)
        begin = time.perf_counter()
        call()
        samples.append((time.perf_counter() - begin) * 1000)
        after = published(service)
        observations.append({'projections_decoded': counters['projections'] - before[0]['projections'],
                             'protocol_sql_evaluations': counters['sql'] - before[0]['sql'],
                             'rows_identity_kept': after[0] == before[1][0],
                             'publication_kept': after[1:] == before[1][1:]})
    return {'median_ms': round(statistics.median(samples), 2), 'min_ms': round(min(samples), 2),
            'samples_ms': [round(v, 2) for v in samples],
            'per_call': {key: statistics.median(o[key] for o in observations) for key in observations[0]}}


def run(source_root, epochs, sources, repeats):
    with tempfile.TemporaryDirectory(prefix='disco-refresh-scoping-benchmark-') as folder:
        started = time.perf_counter()
        service, counters, patches, protocol = build(source_root, folder, epochs, sources)
        setup = time.perf_counter() - started
        try:
            preflight = getattr(service, 'verify_sources', None) or service.refresh
            return {'epochs': len(service.rows), 'sources': sources, 'setup_seconds': round(setup, 1),
                    'approve_preflight_uses': 'verify_sources' if hasattr(service, 'verify_sources') else 'refresh',
                    'refresh': measure(service, counters, service.refresh, repeats),
                    'approve_preflight': measure(service, counters, preflight, repeats)}
        finally:
            for item in patches:
                item.stop()
            index = getattr(service, 'disk_index', None)
            if index is not None:
                index.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--epochs', type=int, nargs='+', default=[5000, 50000])
    parser.add_argument('--sources', type=int, default=5)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = args.source_root.resolve()
    results = [run(source, n, args.sources, args.repeats) for n in args.epochs]
    text = json.dumps({'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       'source_root': str(source), 'python': sys.version.split()[0], 'results': results}, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    for item in results:
        print(item['epochs'], item['approve_preflight_uses'], 'refresh', item['refresh']['median_ms'], item['refresh']['per_call'],
              'preflight', item['approve_preflight']['median_ms'], item['approve_preflight']['per_call'])
