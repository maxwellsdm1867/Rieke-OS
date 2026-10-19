#!/usr/bin/env python3
"""Slow read endpoints at two project sizes: search, predicate fields, overview,
epoch detail inside a protocol and the protocol browse descriptor.

Owned disposable fixture only; never a user project or live port. Production
Flask routes, WorkspaceService, ProtocolStateReader, CurationStore,
SharedAnnotations and a real sealed DiskMetadataIndex run unchanged. SQL tables
are the in-memory transactional doubles from python/tests. The native
generation authority is the production StateGenerationAuthority class with its
two SQL leaf reads replaced: schema attestation (``_attest_contract``, about 20
MySQL status/information_schema queries in production) returns a constant and
is counted, and scope generations come from in-memory counters. Attestation
counts per request are reported; their SQL latency is not timed here.

Run against any source tree with ``--source-root`` to compare revisions with
identical harness bytes. When the source tree publishes deep-frozen read-model
maps (``workspace_service.publish_frozen``), the fixture publishes them the same
way production ``refresh`` does; older trees keep plain dictionaries.

Load-independent counts are reported per request: schema attestations, proof
rebuilds (``ProtocolStateReader._metadata``), ``query_result`` copies and
marshalled witness bytes. ``--witness-check`` times ``native_context`` alone on
one protocol holding every epoch (the per-call freshness proof).
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

SOURCE = 'a' * 64


def uid(namespace, i):
    return str(uuid.UUID(int=(namespace << 64) | i))


def build(source_root, folder, epochs, protocols):
    sys.path[:0] = [str(source_root / 'python'), str(source_root / 'python/tests')]
    import os
    os.environ['RIEKE_PREFERENCES_DIR'] = str(Path(folder) / 'preferences')
    import test_workspace_api as api_fixture
    from test_workspace_curation import Table
    from types import SimpleNamespace
    from unittest.mock import patch
    from disco.metadata.disk_index import DiskMetadataIndex
    from disco.decisions.annotations import SharedAnnotations
    from workspace_service import WorkspaceService
    from workspace_state_generation import StateGenerationAuthority
    from workspace_api import create_app

    case = api_fixture.WorkspaceAPITests()
    case.setUp()
    service = case.service
    project = service.project['project_uuid']
    service.rows, details, service.cells, service._fingerprints = {}, {}, {}, {}
    names = [f'edu.washington.riekelab.protocols.Protocol{p}' for p in range(protocols)]
    for i in range(epochs):
        c, block = i // 300, i // 20
        identity, cell = uid(1, i), uid(2, c)
        protocol = names[block % protocols]
        service.rows[identity] = {'epoch_uuid': identity, 'cell_uuid': cell, 'cell_label': f'Cell{c}',
            'cell_type': ('ON parasol', 'OFF midget', 'ON-OFF DS')[c % 3], 'date': f'2026-09-{1 + c % 28:02d}',
            'start_time': f'09/24/2026 12:{(i // 60) % 60:02d}:{i % 60:02d}:000000',
            'group_uuid': uid(3, c), 'group_label': 'control', 'block_uuid': uid(4, block),
            'protocol_name': protocol, 'duration_seconds': 10, 'streams': [], 'source_sha256': SOURCE,
            'metadata_hash': hashlib.sha256(identity.encode()).hexdigest(), 'epoch_number': i % 20 + 1,
            'block_start_time': '09/24/2026 12:00:00:000000'}
        details[identity] = {'parameters': {'preTime': 500., 'stimTime': 1000., 'contrast': (i % 5) / 4,
                                            'spotSize': float(40 + 20 * (i % 6))},
            'properties': {}, 'attributes': {}, 'metadata': {'epoch': {'uuid': identity}}}
        service._fingerprints[identity] = service.rows[identity]['metadata_hash']
        service.cells.setdefault(cell, {'cell_uuid': cell, 'label': f'Cell{c}',
            'cell_type': service.rows[identity]['cell_type'], 'date': service.rows[identity]['date'],
            'start_time': service.rows[identity]['start_time']})
    service.sources = [{'source_sha256': SOURCE, 'source_path': str(Path(folder) / 'never-open.h5'),
                        'filename': 'never-open.h5', 'counts': {'cells': len(service.cells), 'epochs': epochs}}]
    service.manifests = {SOURCE: {'source_path': service.sources[0]['source_path']}}
    index = DiskMetadataIndex.build(Path(folder) / 'slow-reads.sqlite', service.rows, details, service.sources,
                                    f'slow-reads-{epochs}', project)
    service.disk_index, service.details = index, index.details
    template = service.protocols[service.protocol_id]
    service.protocols = {}
    protocol_ids = [uid(6, p) for p in range(protocols)]
    for p, (identity, name) in enumerate(zip(protocol_ids, names)):
        members = [key for key, row in service.rows.items() if row['protocol_name'] == name]
        definition = {**template['definition'], 'protocol_uuid': identity, 'name': f'Protocol {p}',
                      'query': {'version': 1, 'all': [{'field': 'EpochBlock.protocol_name', 'operator': 'eq', 'value': name}]}}
        service.protocols[identity] = {'definition': definition, 'file': template['file'],
            'result': {'project_uuid': project, 'protocol_uuid': identity, 'protocol_name': name,
                       'source_revisions': [SOURCE],
                       'epochs': [{'uuid': key, 'metadata_hash': service._fingerprints[key]} for key in members],
                       'cells': [{'uuid': key} for key in sorted({service.rows[k]['cell_uuid'] for k in members})]}}
    service.protocol_id = protocol_ids[0]
    service.ids = [member['uuid'] for member in service.protocols[protocol_ids[0]]['result']['epochs']]
    service.__class__ = WorkspaceService
    service.Event = case.events
    # Sparse saved protocol tags (about 2% of each protocol) and shared tags.
    for identity, entry in service.protocols.items():
        for n, member in enumerate(entry['result']['epochs'][::50]):
            case.curation.rows.append({'project_uuid': project, 'protocol_uuid': identity, 'epoch_uuid': member['uuid'],
                'included': n % 7 != 0, 'tags': [f'tag{n % 4}'], 'review_state': 'approved' if n % 3 == 0 else 'unreviewed',
                'revision': 1, 'metadata_fingerprint': member['metadata_hash']})
    profiles = Table(('project_uuid', 'profile_uuid'))
    records = Table(('project_uuid', 'target_kind', 'target_uuid', 'profile_uuid'))
    case.connection.tables.extend([profiles, records])
    shared = SharedAnnotations(service, (profiles, records, case.events))
    app = create_app(case.temp.name, case.temp.name, service=service, store=case.store,
                     explorer_history=case.explorer_history, data_stores=case.data_stores,
                     protocol_suggestions=case.protocol_suggestions, shared_annotations=shared)
    app.config['TESTING'] = True
    author = shared.default_profile['profile_uuid']
    cells = sorted(service.cells)
    shared.update('cell', cells[:3], author, {'tags_add': ['good cell'], 'tags_remove': []},
                  {key: 0 for key in cells[:3]}, 'benchmark')
    tagged = list(service.rows)[::97][:200]
    shared.update('epoch', tagged, author, {'tags_add': ['drift'], 'tags_remove': []},
                  {key: 0 for key in tagged}, 'benchmark')

    counters = {'attest': 0, 'scope': 0}
    generations = {}
    tracker = StateGenerationAuthority(SimpleNamespace(_conn=object(), in_transaction=False), project)
    tracker.ready = True
    tracker.reason = None

    def attest():
        counters['attest'] += 1
        return 'benchmark-authority'

    def scope(kind, identity):
        counters['scope'] += 1
        return ('benchmark-epoch', generations.get((kind, identity), 0))
    tracker._attest_contract = attest
    tracker._scope = scope
    tracker.shared_changes = lambda token, limit=10000: None
    original_records = shared._index_records

    def index_records(keys):
        # The production full scan pages raw SQL; the double has no SQL text.
        if keys is not None:
            yield from original_records(keys)
            return
        for kind in ('cell', 'epoch'):
            yield from sorted((row for row in records.to_dicts() if row['project_uuid'] == project
                               and row['target_kind'] == kind), key=lambda row: (row['target_uuid'], row['profile_uuid']))
    shared._index_records = index_records
    case.store.state_generation = tracker
    shared.state_generation = tracker
    service._explore_state_generation = tracker
    app.extensions['state_generation'] = tracker

    def bump(kind, identity):
        generations[(kind, identity)] = generations.get((kind, identity), 0) + 1
    import workspace_service as service_module
    if hasattr(service_module, 'publish_frozen'):
        service.rows = service_module.publish_frozen(service.rows, rows=True)
        service.cells = service_module.publish_frozen(service.cells)
        service.protocols = service_module.publish_frozen(service.protocols)
        service._fingerprints = service_module.publish_frozen(service._fingerprints)
    install_counters(counters)
    return SimpleNamespace(case=case, service=service, app=app, client=app.test_client(), index=index,
                           protocols=protocol_ids, counters=counters, bump=bump, project=project,
                           epoch=service.ids[len(service.ids) // 2])


def install_counters(counters):
    """Count proof rebuilds, query copies and marshalled witness bytes."""
    import workspace_protocol_state as state
    counters.update(metadata=0, query_result=0, marshal_bytes=0)
    original_metadata = state.ProtocolStateReader._metadata

    def metadata(self, *args, **kwargs):
        counters['metadata'] += 1
        return original_metadata(self, *args, **kwargs)
    state.ProtocolStateReader._metadata = metadata
    module_marshal = getattr(state, 'marshal', None)
    if module_marshal is not None:
        dumps = module_marshal.dumps

        class CountingMarshal:
            def __getattr__(self, name):
                return getattr(module_marshal, name)

            @staticmethod
            def dumps(*args):
                value = dumps(*args)
                counters['marshal_bytes'] += len(value)
                return value
        state.marshal = CountingMarshal()


def counted(fx, call):
    # query_result copies are counted through its existing elapsed() timer,
    # leaving every captured method identity (native contracts) untouched.
    from disco.operation_timing import capture_timings
    before = {key: fx.counters[key] for key in ('attest', 'metadata', 'marshal_bytes')}
    with capture_timings() as timings:
        begin = time.perf_counter()
        value = call()
        elapsed = (time.perf_counter() - begin) * 1000
    delta = {key: fx.counters[key] - before[key] for key in before}
    delta['query_result'] = sum(item['operation'] == 'query_result' for item in timings)
    return value, elapsed, delta


def witness_check(source_root, epochs, repeats):
    """ms per native_context on one protocol of ``epochs`` members (warm)."""
    with tempfile.TemporaryDirectory(prefix='disco-witness-benchmark-') as folder:
        fx = build(source_root, folder, epochs, 1)
        reader = fx.app.extensions['protocol_state_reader']
        protocol = fx.protocols[0]
        # None means the native proof was not admitted (for example above the
        # proof byte budget): every call then rebuilds it and the caller falls
        # back to the legacy full-state oracle. Its per-call cost is reported.
        cold = counted(fx, lambda: reader.native_context(protocol))
        samples, counts = [], []
        for _ in range(repeats):
            value, elapsed, delta = counted(fx, lambda: reader.native_context(protocol, [fx.epoch]))
            if (value is None) != (cold[0] is None) or (value is not None and value['query_revision'] != cold[0]['query_revision']):
                raise RuntimeError('revision changed between identical warm calls')
            samples.append(elapsed)
            counts.append(delta)
        fx.index.close()
        fx.case.doCleanups()
        return {'epochs': epochs, 'protocol_members': epochs, 'native_proof_admitted': cold[0] is not None,
                'cold_ms': round(cold[1], 2), 'cold_counts': cold[2],
                'median_ms': round(statistics.median(samples), 3), 'min_ms': round(min(samples), 3),
                'per_call_counts': {key: statistics.median(item[key] for item in counts) for key in counts[0]},
                'samples_ms': [round(value, 3) for value in samples]}


def run(source_root, epochs, protocols, repeats):
    with tempfile.TemporaryDirectory(prefix='disco-slow-reads-benchmark-') as folder:
        started = time.perf_counter()
        fx = build(source_root, folder, epochs, protocols)
        setup_seconds = time.perf_counter() - started
        main = fx.protocols[0]
        endpoints = {
            'search.keystroke': '/api/search?q=con',
            # UUID lookups: exact, a narrow prefix (<=256 epochs) and a prefix
            # every epoch shares (exact total over the whole project).
            'search.uuid_exact': f'/api/search?q={fx.epoch}',
            'search.uuid_prefix': f'/api/search?q={fx.epoch[:-2]}',
            'search.uuid_prefix_all': f'/api/search?q={fx.epoch[:18]}',
            'explore.predicate_fields': '/api/explore/predicate-fields',
            'overview': '/api/overview',
            'epoch.detail': f'/api/epochs/{fx.epoch}',
            'epoch.detail_in_protocol': f'/api/epochs/{fx.epoch}?protocol_uuid={main}',
            'protocol.browse': f'/api/protocols/{main}?projection=browse',
        }
        results = {}
        bodies = {}
        for name, path in endpoints.items():
            def call():
                response = fx.client.get(path)
                if response.status_code != 200:
                    raise RuntimeError(f'{name}: {response.status_code} {response.get_data(as_text=True)[:400]}')
                return response
            # Cold: first request after a curation write to the main protocol
            # and a shared-tag write (both generations advance).
            fx.bump('protocol_curation', main)
            fx.bump('shared_annotations', fx.project)
            begin = time.perf_counter(); call(); cold = (time.perf_counter() - begin) * 1000
            samples, attest, counts = [], [], []
            for _ in range(repeats):
                response, elapsed, delta = counted(fx, call)
                samples.append(elapsed)
                attest.append(delta['attest'])
                counts.append(delta)
            bodies[name] = hashlib.sha256(response.get_data()).hexdigest()
            results[name] = {'cold_after_write_ms': round(cold, 2), 'median_ms': round(statistics.median(samples), 2),
                             'min_ms': round(min(samples), 2), 'attestations_per_request': statistics.median(attest),
                             'per_request_counts': {key: statistics.median(item[key] for item in counts) for key in counts[0]},
                             'samples_ms': [round(value, 2) for value in samples]}
        fx.index.close()
        fx.case.doCleanups()
        return {'epochs': epochs, 'protocols': protocols, 'protocol_epochs': epochs // protocols,
                'setup_seconds': round(setup_seconds, 1), 'endpoints': results, 'response_sha256': bodies}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--epochs', type=int, nargs='+', default=[5000, 50000])
    parser.add_argument('--protocols', type=int, default=7)
    parser.add_argument('--repeats', type=int, default=9)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--witness-check', action='store_true', help='time native_context alone (one protocol)')
    args = parser.parse_args()
    source = args.source_root.resolve()
    if args.witness_check:
        results = [witness_check(source, n, args.repeats) for n in args.epochs]
        text = json.dumps({'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           'source_root': str(source), 'python': sys.version.split()[0], 'witness_check': results}, indent=2)
        if args.output:
            args.output.write_text(text + '\n')
        for item in results:
            print(item['epochs'], 'admitted' if item['native_proof_admitted'] else 'NOT admitted', item['median_ms'],
                  item['per_call_counts'], 'cold', item['cold_ms'], item['cold_counts'])
        raise SystemExit(0)
    results = [run(source, n, args.protocols, args.repeats) for n in args.epochs]
    text = json.dumps({'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       'source_root': str(source), 'python': sys.version.split()[0], 'results': results}, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    for item in results:
        print(item['epochs'], {k: (v['median_ms'], v['cold_after_write_ms'], v['per_request_counts'])
                               for k, v in item['endpoints'].items()})
