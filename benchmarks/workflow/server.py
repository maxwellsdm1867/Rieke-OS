#!/usr/bin/env python3
"""Owned HTTP fixture for browser workflow measurements; never a live project.

SQL transaction tables, source admission and metadata index admission/projection
are doubles. Production Flask, protocol, predicate evaluator, tree paging, frozen
recipe and Workbench authority algorithms run unchanged. Only two synthetic H5
waveforms exist. This cannot qualify native SQL/index/parser or installed apps.
"""
import argparse
from collections.abc import Mapping
import copy
import json
import os
from pathlib import Path
import signal
import sys
import threading


def uid(i):
    return f'00000000-0000-0000-0000-{i:012x}'


class Details(Mapping):
    def __init__(self, rows): self.rows = rows
    def __len__(self): return len(self.rows)
    def __iter__(self): return iter(self.rows)
    def __getitem__(self, key):
        self.rows[key]
        i = int(key[-12:], 16)
        return {'parameters': {'example': i % 10}, 'properties': {}, 'attributes': {},
                'metadata': {'epoch': {'uuid': key}}}


class Values(Mapping):
    def __init__(self, rows, ids=None, fields=None):
        self.rows, self.ids, self.fields = rows, rows if ids is None else ids, fields
    def __len__(self): return len(self.ids)
    def __iter__(self): return iter(self.ids)
    def __getitem__(self, key):
        from disco.navigation.tree import BASE_FIELDS
        row = self.rows[key]
        result = {name: row[column] for name, (_, _, column) in BASE_FIELDS.items() if column in row}
        result['parameters/example'] = int(key[-12:], 16) % 10
        return result if self.fields is None else {k: v for k, v in result.items() if k in self.fields}


def admitted_index(service):
    from disco.metadata.disk_index import DiskMetadataIndex
    from disco.navigation import predicates
    from disco.navigation.tree import BASE_FIELDS
    class Index(DiskMetadataIndex):
        def __init__(self): self.generation = 'workflow-owned-v1'
        def _check(self): pass
        def close(self): pass
        def catalog(self, ids=None, known_fields=None):
            fields = [{'id': name, 'label': label, 'category': category, 'types': ['string']}
                      for name, (label, category, _) in BASE_FIELDS.items()]
            fields.append({'id': 'parameters/example', 'label': 'Example', 'category': 'Parameters', 'types': ['number']})
            return {'fields': fields, 'total': len(service.rows) if ids is None else len(ids),
                    'summary_available': False}
        def values(self, ids=None, fields=None): return Values(service.rows, ids, fields)
        def predicate_catalog(self, ids=None):
            result = self.catalog(ids)
            for field in result['fields']:
                field.update(choices=[], choices_truncated=True)
            return {**result, 'operators': list(predicates.OPERATORS), 'predicate_version': 1,
                    'limits': {'max_depth': predicates.MAX_DEPTH, 'max_nodes': predicates.MAX_NODES, 'max_choices': predicates.MAX_CHOICES}}
        def match(self, predicate, ids=None):
            values = self.values(ids)
            # All generated fields have a single invariant type. Use one real
            # representative for validation, then the real evaluator per row.
            first = next(iter(service.rows), None)
            representatives = {first: values[first]} if first is not None else {}
            validated = predicates.validate(predicate, self.catalog(ids), representatives)
            return validated, [key for key in values if predicates.matches(validated, values[key])]
    return Index()


def build(source, output, epochs, protocol_epochs=None):
    protocol_epochs = epochs if protocol_epochs is None else protocol_epochs
    if not 200 <= protocol_epochs <= epochs:
        raise ValueError("protocol_epochs must be 200..epochs")
    sys.path[:0] = [str(source / 'python'), str(source / 'python/tests')]
    os.environ['RIEKE_PREFERENCES_DIR'] = str(output / 'preferences')
    from unittest.mock import patch
    from test_workspace_suggestions import ImportSuggestionTests
    import h5py
    import numpy as np
    fixture = ImportSuggestionTests(); fixture.setUp()
    case, service = fixture.case, fixture.case.service
    # Register actual annotation and saved-search owners against owned SQL doubles.
    # create_app captures these dependencies when declaring routes.
    from test_workspace_curation import Table
    from test_workspace_search_presets import PresetTable
    from disco.decisions.annotations import SharedAnnotations
    from disco.navigation.search_presets import SearchPresets
    from workspace_api import create_app
    profiles = Table(('project_uuid', 'profile_uuid'))
    annotations = Table(('project_uuid', 'target_kind', 'target_uuid', 'profile_uuid'))
    presets = PresetTable(('project_uuid', 'preset_uuid'))
    versions = Table(('project_uuid', 'preset_uuid', 'version'))
    runs = Table(('project_uuid', 'query_sha256'))
    case.connection.tables.extend([profiles, annotations, presets, versions, runs])
    shared = SharedAnnotations(service, (profiles, annotations, case.events))
    case.app = create_app(case.temp.name, case.temp.name, service=service, store=case.store,
        explorer_history=case.explorer_history, data_stores=case.data_stores,
        protocol_suggestions=case.protocol_suggestions, shared_annotations=shared)
    case.app.config['TESTING'] = True
    case.app.extensions['search_presets'] = SearchPresets(case.store, (presets, versions), runs=runs)
    case.client = case.app.test_client()
    incoming = min(100, max(1, protocol_epochs // 10))
    main_count = protocol_epochs - incoming
    incoming_start = epochs - incoming
    original = copy.deepcopy(next(iter(service.rows.values())))
    service.rows.clear(); service.cells.clear()
    service.ids = [uid(i) for i in range(main_count)]
    service.cell_ids = [uid(2_000_000 + i) for i in range((epochs + 99) // 100)]
    tracefile = output / 'trace-fixture.h5'
    stream = uid(5_000_000)
    def add(start, stop, sha):
        for i in range(start, stop):
            cell, block = service.cell_ids[i // 100], uid(3_000_000 + i // 20)
            row = {**original, 'epoch_uuid': uid(i), 'cell_uuid': cell, 'block_uuid': block,
                   'cell_label': f'Cell {i // 100}', 'epoch_number': i % 20 + 1,
                   'source_sha256': sha, 'streams': [], 'group_uuid': uid(4_000_000),
                   'protocol_name': 'ambient' if main_count <= i < incoming_start else 'example'}
            if i in (0, incoming_start):
                row['streams'] = [{'uuid': stream, 'kind': 'responses', 'sample_count': 10000,
                    'sample_rate': 10000.0, 'units': 'pA',
                    'h5_path': '/epochs/' + uid(i) + '/responses/' + stream}]
            service.rows[uid(i)] = row
            service.cells.setdefault(cell, {'cell_uuid': cell, 'label': row['cell_label'],
                'cell_type': row['cell_type'], 'date': row['date'], 'start_time': row['start_time']})
    add(0, incoming_start, 'a' * 64)
    service.details = Details(service.rows)
    service._fingerprints = dict.fromkeys(service.rows, 'b' * 64)
    result = service.protocols[service.protocol_id]['result']
    result['epochs'] = [{'uuid': key, 'metadata_hash': 'b' * 64} for key in service.ids]
    result['cells'] = [{'uuid': uid(2_000_000 + i)} for i in range((main_count + 99) // 100)]
    fixture.before_ids = list(service.ids)
    service.disk_index = admitted_index(service)
    author = patch('disco.decisions.author_preferences.selected_author', return_value={'profile_uuid': 'actor-one'})
    author.start(); fixture.addCleanup(author.stop)
    verified = patch.object(service, '_verified_source', return_value=(fixture.source, None))
    verified_mock = verified.start(); fixture.addCleanup(verified.stop)
    def mutate():
        add(incoming_start, epochs, fixture.source_sha)
        service._fingerprints.update(dict.fromkeys((uid(i) for i in range(incoming_start, epochs)), 'b' * 64))
        result['epochs'].extend({'uuid': uid(i), 'metadata_hash': 'b' * 64} for i in range(incoming_start, epochs))
        result['source_revisions'].append(fixture.source_sha)
        service.sources.append({'source_sha256': fixture.source_sha, 'source_path': str(fixture.source), 'filename': fixture.source.name, 'counts': {'epochs': incoming}})
        service.manifests[fixture.source_sha] = {'source_path': str(fixture.source)}
        case.sources.insert1({'project_uuid': service.project['project_uuid'], 'source_sha256': fixture.source_sha})
        service._tree_catalog_cache = {}
        service._registered_tree_cache = service._registered_predicate_cache = service._predicate_catalog_cache = None
    with h5py.File(tracefile, 'w') as h:
        for i in (0, incoming_start):
            group = h.create_group('/epochs/' + uid(i)); group.attrs['uuid'] = uid(i)
            response = group.create_group('responses/' + stream)
            response.attrs['uuid'] = stream; response.attrs['sampleRate'] = 10000.0
            data = np.zeros(10000, dtype=[('quantity', 'f8'), ('units', 'S2')])
            data['quantity'] = np.arange(10000); data['units'] = b'pA'
            response.create_dataset('data', data=data)
    st = tracefile.stat()
    verified_mock.return_value = (tracefile, (str(tracefile), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
    from flask import request, jsonify, g, abort
    reset_state = {}
    request_guard = threading.Lock()
    active = {'count': 0, 'resetting': False}

    @case.app.post('/__benchmark__/reset-preparation')
    def reset_preparation():
        # Only the owned fixture exposes this control. The browser invokes it
        # while idle, outside action timings. Never restore over scientific edits.
        if request.headers.get('X-Workspace-Request') != '1':
            abort(403)
        with request_guard:
            if active['count'] or active['resetting']:
                abort(409, 'Other owned fixture requests are still active')
            active['resetting'] = True
        try:
            for table, expected in reset_state['protected']:
                if table.rows != expected:
                    abort(409, 'Main/source/annotation authority changed; refusing reset')
            if service.sources != reset_state['sources'] or service._fingerprints != reset_state['fingerprints']:
                abort(409, 'Source metadata changed; refusing reset')
            # Actual production algorithms run again against the exact immutable
            # post-import SQL fixture. This control grants no recipe authority.
            for table, rows in reset_state['tables']:
                table.rows[:] = copy.deepcopy(rows)
            retained_revisions = {row['revision_uuid'] for row in case.explorer_revisions.rows}
            case.explorer_history._recipe_cache = {key: value for key, value in case.explorer_history._recipe_cache.items() if key in retained_revisions}
            return jsonify(reset=True, ready=True, main_count=main_count, incoming_count=incoming,
                           protocol_epochs=protocol_epochs, epochs=epochs,
                           scope='owned post-import SQL fixture; outside measurement',
                           metadata_cache='retained warm; prepared cohort and operation receipts reset')
        finally:
            with request_guard:
                active['resetting'] = False

    fixture.run_import(mutate)
    for item in fixture.preflight.patches: item.stop()
    case.sources.insert1({'project_uuid': service.project['project_uuid'], 'source_sha256': 'a' * 64})
    reset_state['tables'] = [(table, copy.deepcopy(table.rows)) for table in case.connection.tables]
    protected = [case.protocol_bindings, case.curation, case.sources, case.data_store_states, annotations]
    reset_state['protected'] = [(table, rows) for table, rows in reset_state['tables'] if any(table is protected_table for protected_table in protected)]
    reset_state['sources'] = copy.deepcopy(service.sources)
    reset_state['fingerprints'] = dict(service._fingerprints)

    def track_request():
        g.workflow_counted = False
        if request.path == '/__benchmark__/reset-preparation':
            return
        with request_guard:
            if active['resetting']:
                abort(409, 'Owned fixture restoration in progress')
            active['count'] += 1
            g.workflow_counted = True

    def finish_request(error):
        if getattr(g, 'workflow_counted', False):
            with request_guard:
                active['count'] -= 1
            g.workflow_counted = False

    case.app.before_request_funcs.setdefault(None, []).insert(0, track_request)
    case.app.teardown_request_funcs.setdefault(None, []).append(finish_request)
    def profiles():
        if request.path == '/api/annotation-profiles':
            return jsonify({'profiles': [{'profile_uuid': 'actor-one', 'display_name': 'Owned fixture'}], 'selected_profile_uuid': 'actor-one'})
    case.app.before_request_funcs.setdefault(None, []).insert(0, profiles)
    meta = {'project': service.project['project_uuid'], 'protocol': service.protocol_id,
            'candidate': case.suggestion_rows.rows[0]['summary']['candidate_revision_uuid'],
            'epochs': epochs, 'protocol_epochs': protocol_epochs, 'ambient_count': epochs - protocol_epochs,
            'main_count': main_count, 'main_cell_count': (main_count + 99) // 100, 'incoming_count': incoming,
            'first_epoch': uid(0), 'first_cell': service.cell_ids[0], 'first_incoming': uid(incoming_start),
            'first_cell_epochs': [uid(i) for i in range(min(100, main_count))],
            'incoming_epochs': [uid(i) for i in range(incoming_start, epochs)],
            'date_label': original['date'], 'cell_label': 'Cell 0',
            'trace_expected': {'epoch_uuid': uid(0), 'stream_uuid': stream, 'start': 0, 'count': 10000, 'sample_rate': 10000, 'units': 'pA', 'values_first': 0, 'values_last': 9999},
            'trace_stream': stream, 'trace_samples': 10000, 'trace_rate_hz': 10000,
            'qualifying_scale': epochs == 1_000_000, 'fixture': 'workflow-owned-v2',
            'admissions': ['transactional SQL doubles', 'synthetic metadata index catalog/projection; production predicate evaluator', 'source verification double'],
            'trace': 'two owned synthetic H5 ramps; real lazy reads',
            'owned_h5_path': str(tracefile.resolve()), 'native_qualification': False}
    return fixture, case.app, meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=1_000_000)
    parser.add_argument('--protocol-epochs', type=int, help='Active protocol scope including incoming; default is entire project')
    args = parser.parse_args()
    if args.epochs < 200 or args.epochs > 1_000_000: parser.error('epochs must be 200..1000000')
    if args.protocol_epochs is not None and not 200 <= args.protocol_epochs <= args.epochs:
        parser.error('protocol-epochs must be 200..epochs')
    args.output.mkdir(parents=True, exist_ok=False)
    fixture = server = restore = None
    cleanup = {'server_closed': False, 'fixture_closed': False, 'instrumentation_restored': False}
    try:
        fixture, app, meta = build(args.source_root.resolve(), args.output.resolve(), args.epochs, args.protocol_epochs)
        from backend_timing import install
        from werkzeug.serving import make_server
        restore = install(app, args.output, args.source_root)
        server = make_server('127.0.0.1', 0, app, threaded=True)
        meta['port'] = server.server_port
        (args.output / 'server.json').write_text(json.dumps(meta, indent=2))
        print(json.dumps(meta), flush=True)
        def stop(*_): threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
        server.serve_forever()
    finally:
        failures = []
        for key, operation in (
            ('server_closed', server.server_close if server else None),
            ('instrumentation_restored', restore),
            ('fixture_closed', fixture.doCleanups if fixture else None),
        ):
            if operation:
                try:
                    operation()
                    cleanup[key] = True
                except Exception as error:
                    failures.append({'stage': key, 'error': str(error)})
        cleanup['errors'] = failures
        (args.output / 'cleanup.json').write_text(json.dumps(cleanup, indent=2))
        if failures:
            raise RuntimeError('Owned fixture cleanup failed: ' + json.dumps(failures))

if __name__ == '__main__': main()
