"""Owned fixture adaptation: real source verification and sealed metadata index.
No canonical service/index/policy method is replaced. SQL remains an explicit double.
"""
import copy,hashlib,json,uuid
from pathlib import Path
import h5py,numpy as np


def owned_sources(fixture, service, tracefile, stream, incoming_start):
    i=np.arange(1000000,dtype=np.float64)
    values=np.sin(i*.013)*7+np.cos(i*.117)
    values[12345]=80.;values[987654]=-90.;values[100:110]=0.;values[105]=-0.
    expected=values.astype('<f8').tobytes()
    (tracefile.parent/'expected-f64le.bin').write_bytes(expected)
    with h5py.File(tracefile,'w') as h:
        for i,count in [(0,10000),(incoming_start,300000),(incoming_start+1,1000000)]:
            identity=f'00000000-0000-0000-0000-{i:012x}'
            group=h.create_group('/epochs/'+identity);group.attrs['uuid']=identity
            response=group.create_group('responses/'+stream);response.attrs['uuid']=stream;response.attrs['sampleRate']=10000.
            data=np.empty(count,dtype=[('quantity','<f8'),('units','S10')]);data['quantity']=values[:count];data['units']=b'pA'
            response.create_dataset('data',data=data,chunks=(64,),compression='gzip',compression_opts=4)
    mainfile=tracefile.with_name('main-source.h5')
    # Separate owned registration, with real bytes and digest; synthetic metadata
    # rows without streams remain declared synthetic metadata, not imported H5 epochs.
    with h5py.File(mainfile,'w') as h, h5py.File(tracefile,'r') as incoming:
        h.attrs['owned-diagnostic']='synthetic ambient metadata registration'
        epochs_group=h.create_group('epochs'); incoming.copy('/epochs/00000000-0000-0000-0000-000000000000',epochs_group)
    mainsha=hashlib.sha256(mainfile.read_bytes()).hexdigest()
    fixture.source=tracefile;fixture.source_sha=hashlib.sha256(tracefile.read_bytes()).hexdigest()
    service._source_signatures={}
    service.sources=[dict(source_sha256=mainsha,source_path=str(mainfile),filename=mainfile.name,counts={'epochs':incoming_start})]
    service.manifests={mainsha:dict(source_sha256=mainsha,source_path=str(mainfile),source_size=mainfile.stat().st_size)}
    return mainsha


def fingerprints(service, identities):
    return {identity:hashlib.sha256(json.dumps({'epoch':service.details[identity], 'source_sha256':service.rows[identity].get('source_sha256')},sort_keys=True,allow_nan=False).encode()).hexdigest() for identity in identities}


def canonicalize(fixture,service,output):
    from workspace_service import WorkspaceService
    from disco.metadata.disk_index import DiskMetadataIndex
    service.refresh=service.refresh;service.events=service.events
    service.__class__=WorkspaceService
    service._explore_publication=str(uuid.uuid4())
    for source in service.sources:
        path=Path(source['source_path'])
        service.manifests[source['source_sha256']]=dict(source_sha256=source['source_sha256'],source_path=str(path),source_size=path.stat().st_size)
        service._verified_source(service.manifests[source['source_sha256']])
    old=service.disk_index
    index=DiskMetadataIndex.build(output/'sealed-metadata.sqlite3',service.rows,service.details,service.sources,'owned-capability-v1',service.project['project_uuid'])
    assert type(index) is DiskMetadataIndex
    sealed=index.fingerprints()
    assert dict(sealed)==service._fingerprints,'Real sealed fingerprints differ from frozen recipe metadata'
    service.disk_index=index;old.close();fixture.addCleanup(index.close)
    # These are real canonical methods. No method/policy eligibility spoofing.
    from workspace_trace_views import TraceViews
    assert TraceViews(service)._canonical(),'Canonical source/index setup rejected'


import os, sys, threading
from benchmarks.workflow.server import uid, Details, admitted_index

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
    tracefile = (output / 'trace-fixture.h5').resolve()
    stream = uid(5_000_000)
    mainsha = owned_sources(fixture, service, tracefile, stream, incoming_start)
    def add(start, stop, sha):
        for i in range(start, stop):
            cell, block = service.cell_ids[i // 100], uid(3_000_000 + i // 20)
            row = {**original, 'epoch_uuid': uid(i), 'cell_uuid': cell, 'block_uuid': block,
                   'cell_label': f'Cell {i // 100}', 'epoch_number': i % 20 + 1,
                   'source_sha256': sha, 'streams': [], 'group_uuid': uid(4_000_000),
                   'protocol_name': 'ambient' if main_count <= i < incoming_start else 'example'}
            if i in (0, incoming_start, incoming_start + 1):
                row['streams'] = [{'uuid': stream, 'kind': 'responses', 'sample_count': 10000 if i == 0 else 300000 if i == incoming_start else 1000000,
                    'sample_rate': 10000.0, 'units': 'pA',
                    'h5_path': '/epochs/' + uid(i) + '/responses/' + stream}]
            service.rows[uid(i)] = row
            service.cells.setdefault(cell, {'cell_uuid': cell, 'label': row['cell_label'],
                'cell_type': row['cell_type'], 'date': row['date'], 'start_time': row['start_time']})
    add(0, incoming_start, mainsha)
    service.details = Details(service.rows)
    service._fingerprints = fingerprints(service, service.rows)
    result = service.protocols[service.protocol_id]['result']
    result['epochs'] = [{'uuid': key, 'metadata_hash': service._fingerprints[key]} for key in service.ids]
    result['source_revisions'] = [mainsha]
    result['cells'] = [{'uuid': uid(2_000_000 + i)} for i in range((main_count + 99) // 100)]
    fixture.before_ids = list(service.ids)
    service.disk_index = admitted_index(service)
    author = patch('disco.decisions.author_preferences.selected_author', return_value={'profile_uuid': 'actor-one'})
    author.start(); fixture.addCleanup(author.stop)
    verified = patch.object(service, '_verified_source', return_value=(fixture.source, None))
    verified_mock = verified.start(); fixture.addCleanup(verified.stop)
    def mutate():
        add(incoming_start, epochs, fixture.source_sha)
        service._fingerprints.update(fingerprints(service, [uid(i) for i in range(incoming_start, epochs)]))
        result['epochs'].extend({'uuid': uid(i), 'metadata_hash': service._fingerprints[uid(i)]} for i in range(incoming_start, epochs))
        result['source_revisions'].append(fixture.source_sha)
        service.sources.append({'source_sha256': fixture.source_sha, 'source_path': str(fixture.source), 'filename': fixture.source.name, 'counts': {'epochs': incoming}})
        service.manifests[fixture.source_sha] = {'source_path': str(fixture.source)}
        case.sources.insert1({'project_uuid': service.project['project_uuid'], 'source_sha256': fixture.source_sha})
        service._tree_catalog_cache = {}
        service._registered_tree_cache = service._registered_predicate_cache = service._predicate_catalog_cache = None
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
    case.sources.insert1({'project_uuid': service.project['project_uuid'], 'source_sha256': mainsha})
    verified.stop()
    canonicalize(fixture, service, output)
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
            'date_label': original['date'], 'cell_label': 'Cell 0', 'incoming_cell_label': f'Cell {incoming_start // 100}',
            'trace_expected': {'epoch_uuid': uid(0), 'stream_uuid': stream, 'start': 0, 'count': 10000, 'sample_rate': 10000, 'units': 'pA', 'values_first': 0, 'values_last': 9999},
            'incoming_trace_expected': {'epoch_uuid': uid(incoming_start), 'stream_uuid': stream, 'start': 0, 'count': 300000, 'sample_rate': 10000, 'units': 'pA', 'values_first': 0, 'values_last': 299999, 'ramp': True, 'source_sha256': fixture.source_sha},
            'million_trace_expected': {'epoch_uuid': uid(incoming_start + 1), 'stream_uuid': stream, 'start': 0, 'count': 1000000, 'sample_rate': 10000, 'units': 'pA', 'values_first': 0, 'values_last': 999999, 'ramp': True, 'source_sha256': fixture.source_sha},
            'trace_streams': copy.deepcopy(service.rows[uid(0)]['streams']),
            'trace_stream': stream, 'trace_samples': 10000, 'trace_rate_hz': 10000,
            'qualifying_scale': epochs == 1_000_000, 'fixture': 'workflow-owned-v4',
            'admissions': ['transactional SQL doubles', 'synthetic metadata rows; real sealed DiskMetadataIndex', 'real owned gzip64 H5 and SHA verification'],
            'trace': 'three owned synthetic gzip64 H5 waveforms; real canonical reads',
            'owned_h5_path': str(tracefile.resolve()), 'native_qualification': False}
    return fixture, case.app, meta

