#!/usr/bin/env python3
"""Private serial worker for the million-epoch backend route track.

Invoke through ``tools/benchmark_routes.py``. One process measures one source
checkout at one project/protocol size. It reuses the owned workflow fixture
(benchmarks/workflow/server.py: production Flask routes, WorkspaceService,
ProtocolStateReader, CurationStore, SharedAnnotations, Workbench and the
pending-import pool over transactional SQL doubles), then replaces its synthetic
metadata index with a real sealed ``DiskMetadataIndex`` built from the same rows
and installs the production ``StateGenerationAuthority`` with its two SQL leaf
reads replaced (as tools/benchmark_slow_reads.py does): schema attestation is a
counted constant and scope generations are in-memory counters that the SQL
doubles advance on every curation/shared-annotation write, standing in for the
native triggers.

Every case is timed without instrumentation (one cold/first request, then
``--samples`` warm requests) and then repeated once under cProfile in a separate
counting pass. Counts come from that pass only and never touch timed samples.
No class method is replaced, so identity-checked fast paths stay eligible.
H5 access after fixture construction fails the run: traces are out of scope.
"""
import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import pstats
import statistics
import sys
import tempfile
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
FORMAT = 'disco-route-million-worker-v1'

parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--epochs', type=int, required=True)
parser.add_argument('--protocol-epochs', type=int, required=True)
parser.add_argument('--samples', type=int, default=3)
parser.add_argument('--cases', default='', help='Comma-separated case-name prefixes (diagnostic subset)')
args = parser.parse_args()
if not __debug__:
    raise RuntimeError('Oracles require Python without -O')
if os.environ.get('RIEKE_TEST_DOM_MODULE') is not None:
    raise RuntimeError('RIEKE_TEST_DOM_MODULE must be unset')

result = {'format': FORMAT, 'status': 'running', 'epochs': args.epochs, 'protocol_epochs': args.protocol_epochs,
          'samples': args.samples, 'cases': {}, 'skipped': {}, 'h5_open_attempts': [], 'notes': []}
started = time.perf_counter()


def report(event, **values):
    print(json.dumps({'event': event, **values}), flush=True)


def write():
    args.output.write_text(json.dumps(result, indent=2, default=str) + '\n')


# Headline call counts; every other source-tree function is kept in the raw list.
HEADLINE = {
    'marshal.dumps': lambda f: f[2] == '<built-in method marshal.dumps>',
    'copy.deepcopy': lambda f: f[0].endswith('/copy.py') and f[2] == 'deepcopy',
    'sqlite.execute': lambda f: f[0] == '~' and 'sqlite3' in f[2] and ('execute' in f[2]),
    'predicate.matches': lambda f: f[0].endswith('navigation/predicates.py') and f[2] == 'matches',
    'protocol_state.input_witness': lambda f: f[0].endswith('workspace_protocol_state.py') and f[2] == '_input_witness',
    'protocol_state.metadata': lambda f: f[0].endswith('workspace_protocol_state.py') and f[2] == '_metadata',
    'protocol_state.materialized_state': lambda f: f[0].endswith('workspace_protocol_state.py') and f[2] == 'materialized_state',
    'service.refresh': lambda f: f[0].endswith('workspace_service.py') and f[2] == 'refresh',
    'service.query_result': lambda f: f[0].endswith('workspace_service.py') and f[2] == 'query_result',
    'tree_pages.build_scope': lambda f: f[0].endswith('tree_pages.py') and f[2] == '_build_scope',
    'disk_index.catalog': lambda f: f[0].endswith('disk_index.py') and f[2] == 'catalog',
    'generation.scope_read': lambda f: f[0].endswith('workspace_state_generation.py') and f[2] == '_scope',
    'sql_double.read': lambda f: f[0].endswith('test_workspace_curation.py') and f[2] == 'to_dicts',
    'sql_double.write': lambda f: f[0].endswith('test_workspace_curation.py') and f[2] in ('insert1', 'update1'),
    'sql_double.transaction': lambda f: f[0].endswith('test_workspace_curation.py') and f[2] == 'transaction',
}


def count_profile(profile, source_python):
    stats = pstats.Stats(profile).stats
    headline = {name: 0 for name in HEADLINE}
    functions = []
    for key, (primitive, total, _, cumulative, _) in stats.items():
        for name, test in HEADLINE.items():
            if test(key):
                # Primitive (non-recursive) calls: deepcopy counts top-level copies.
                headline[name] += primitive
        if key[0].startswith(source_python):
            functions.append({'function': f'{Path(key[0]).relative_to(source_python)}:{key[2]}',
                              'calls': total, 'cumulative_ms': round(cumulative * 1000, 3)})
    functions.sort(key=lambda row: -row['calls'])
    return headline, functions[:60]


def main():
    source = args.source_root.resolve()
    source_python = str(source / 'python') + os.sep
    sys.path[:0] = [str(ROOT / 'benchmarks/workflow')]
    folder = tempfile.mkdtemp(prefix='disco-route-million-')
    import server as workflow_fixture  # Harness-owned fixture; imports app code from --source-root.
    build_started = time.perf_counter()
    fixture, app, meta = workflow_fixture.build(source, Path(folder), args.epochs, args.protocol_epochs)
    case = fixture.case
    service = case.service
    report('fixture_built', seconds=time.perf_counter() - build_started)
    import h5py

    def forbidden(*values, **kwargs):
        result['h5_open_attempts'].append(str(values[:1]))
        raise AssertionError('Route benchmark attempted H5 access')
    h5py.File = forbidden

    from disco.metadata.disk_index import DiskMetadataIndex
    from workspace_state_generation import StateGenerationAuthority
    from types import SimpleNamespace
    from collections.abc import Mapping
    project = service.project['project_uuid']
    protocol = service.protocol_id

    class Details(Mapping):
        """Deterministic recorded parameters, generated per epoch while sealing."""
        def __init__(self, rows): self.rows = rows
        def __len__(self): return len(self.rows)
        def __iter__(self): return iter(self.rows)
        def __getitem__(self, key):
            self.rows[key]
            i = int(key[-12:], 16)
            parameters = {'example': i % 10, 'contrast': (i % 5) / 4, 'spotSize': float(40 + 20 * (i % 6))}
            if i % 3:
                parameters['optional'] = i % 7  # A recorded field missing on one third of epochs.
            return {'parameters': parameters, 'properties': {}, 'attributes': {},
                    'metadata': {'epoch': {'uuid': key}}}
    # Workflow rows carry 'a'*64 and the imported fixture source; the sealed
    # index records every source a row names.
    sources = {row['source_sha256'] for row in service.rows.values()}
    known = {item['source_sha256']: item for item in service.sources}
    index_sources = [known.get(sha, {'source_sha256': sha, 'source_path': str(Path(folder) / 'never-open.h5'),
                                     'filename': 'never-open.h5'}) for sha in sorted(sources)]
    seal_started = time.perf_counter()
    index = DiskMetadataIndex.build(Path(folder) / 'index' / 'routes.sqlite', service.rows, Details(service.rows),
                                    index_sources, f'route-million-{args.epochs}-{args.protocol_epochs}', project)
    service.disk_index, service.details = index, index.details
    service._tree_catalog_cache = {}
    for name in ('_registered_tree_cache', '_registered_predicate_cache', '_predicate_catalog_cache'):
        if hasattr(service, name):
            setattr(service, name, None)
    report('index_sealed', seconds=time.perf_counter() - seal_started)

    counters = {'attest': 0, 'generation_sql': 0}
    generations = {}
    epochs_by_kind = {}
    depth = [0]
    # The SQL double tracks transaction depth so the tracker's transaction-bound
    # mutation checks and autocommit-only response leases behave as natively.
    sql = case.connection
    plain = type(sql)
    import contextlib

    class TrackedConnection(plain):
        @property
        def transaction(self):
            inner = plain.transaction.fget(self)

            @contextlib.contextmanager
            def tracked():
                depth[0] += 1
                try:
                    with inner:
                        yield
                finally:
                    depth[0] -= 1
            return tracked()
    sql.__class__ = TrackedConnection

    class GenerationRows:
        """Leaf SQL of StateGenerationAuthority: generation rows and lock probes only."""
        _conn = SimpleNamespace(_sock=object())

        @property
        def in_transaction(self):
            return depth[0] > 0

        def query(self, statement, arguments=(), as_dict=True, reconnect=False):
            counters['generation_sql'] += 1
            rows = []
            if 'scope_epoch,generation' in statement and 'SELECT' in statement:
                key = (arguments[1], arguments[2])
                rows = [{'scope_epoch': epochs_by_kind.setdefault(key, str(uuid.uuid4())),
                         'generation': generations.get(key, 0)}]
            return SimpleNamespace(fetchall=lambda: rows)
    tracker = StateGenerationAuthority(GenerationRows(), project)
    tracker.ready, tracker.reason = True, None

    def attest():
        counters['attest'] += 1
        return 'benchmark-authority'
    tracker._attest_contract = attest
    tracker.shared_changes = lambda token, limit=10000: None
    shared = app.extensions.get('shared_annotations')
    case.store.state_generation = tracker
    if shared is not None:
        shared.state_generation = tracker
    service._explore_state_generation = tracker
    app.extensions['state_generation'] = tracker

    # Native triggers advance generations inside each writing transaction.
    # Restricted views of a double share its row list, so dispatch on that list.
    # Only the SQL double class is wrapped, never a production class.
    shared = app.extensions.get('shared_annotations')
    watched = {id(case.curation.rows): lambda row: ('protocol_curation', row['protocol_uuid'])}
    if shared is not None:
        watched[id(shared.Annotation.rows)] = lambda row: ('shared_annotations', project)
        watched[id(shared.Profile.rows)] = lambda row: ('shared_annotations', project)
    table_class = type(case.curation)
    for method in ('insert1', 'update1'):
        original = getattr(table_class, method)

        def triggered_write(self, row, _original=original):
            value = _original(self, row)
            kind_of = watched.get(id(self.rows))
            if kind_of is not None:
                key = kind_of(row)
                generations[key] = generations.get(key, 0) + 1
            return value
        setattr(table_class, method, triggered_write)
    if shared is not None and hasattr(shared, '_index_records'):
        # The production full scan pages raw SQL; the double has no SQL text
        # (same seam as tools/benchmark_slow_reads.py). Keyed reads stay native.
        original_records = shared._index_records
        annotation_table = shared.Annotation

        def index_records(keys):
            if keys is not None:
                yield from original_records(keys)
                return
            for kind in ('cell', 'epoch'):
                yield from sorted((row for row in annotation_table.to_dicts() if row['project_uuid'] == project
                                   and row['target_kind'] == kind), key=lambda row: (row['target_uuid'], row['profile_uuid']))
        shared._index_records = index_records

    if os.environ.get('ROUTE_DEBUG_CONFLICT'):
        import disco.decisions.curation as curation_module
        original_init = curation_module.RevisionConflict.__init__
        def noisy(self, current):
            traceback.print_stack(limit=14)
            print('CONFLICT', str(current)[:400], flush=True)
            original_init(self, current)
        curation_module.RevisionConflict.__init__ = noisy

    client = app.test_client()
    headers = dict(getattr(case, 'headers', {}) or {'X-Workspace-Request': '1'})
    author = shared.default_profile['profile_uuid'] if shared is not None else None
    main_ids = list(service.ids)
    cells = sorted({service.rows[key]['cell_uuid'] for key in main_ids})

    # Sparse protocol tags (1 per 500 members) and shared tags with times, written
    # through production owners before timing so tag predicates have matches.
    seed_started = time.perf_counter()
    tagged = main_ids[::500][:2000]
    page = client.get(f'/api/protocols/{protocol}/epochs?limit=1', headers=headers).get_json()
    for start in range(0, len(tagged), 1000):
        chunk = tagged[start:start + 1000]
        read = client.post(f'/api/protocols/{protocol}/curation/read', headers=headers, json={
            'epoch_uuids': chunk, 'query_revision': page['query_revision'],
            'expected_binding_version': page['expected_binding_version'],
            'selection_scope': {'filters': {}, 'cell_uuid': None}})
        if read.status_code != 200:
            raise RuntimeError('seed curation read failed: ' + read.get_data(as_text=True)[:400])
        revisions = {row['epoch_uuid']: row['curation_revision'] for row in read.get_json()['epochs']}
        saved = client.post(f'/api/protocols/{protocol}/curation', headers=headers, json={
            'epoch_uuids': chunk, 'query_revision': page['query_revision'],
            'expected_binding_version': page['expected_binding_version'],
            'selection_scope': {'filters': {}, 'cell_uuid': None},
            'changes': {'tags_add': ['bench-protocol-tag']}, 'expected_revisions': revisions})
        if saved.status_code != 200:
            raise RuntimeError('seed curation write failed: ' + saved.get_data(as_text=True)[:400])
        page = client.get(f'/api/protocols/{protocol}/epochs?limit=1', headers=headers).get_json()
    shared_epochs = main_ids[::97][:200]
    if shared is not None:
        shared.update('cell', cells[:3], author, {'tags_add': ['good cell'], 'tags_remove': []},
                      {key: 0 for key in cells[:3]}, 'benchmark')
        shared.update('epoch', shared_epochs, author, {'tags_add': ['drift'], 'tags_remove': []},
                      {key: 0 for key in shared_epochs}, 'benchmark')
    result['seed'] = {'protocol_tagged_epochs': len(tagged), 'shared_tagged_epochs': 200 if shared else 0,
                      'shared_tagged_cells': 3 if shared else 0, 'seconds': time.perf_counter() - seed_started}

    def call(method, path, body=None, expected=(200,)):
        response = getattr(client, method)(path, headers=headers, **({'json': body} if body is not None else {}))
        if response.status_code not in expected:
            raise RuntimeError(f'{method.upper()} {path}: {response.status_code} {response.get_data(as_text=True)[:500]}')
        return response

    selected = [prefix for prefix in args.cases.split(',') if prefix]

    def wanted(name):
        return not selected or any(name.startswith(prefix) for prefix in selected)

    def measure(name, prepare, request, *, oracle=None, cold=True, writes=False):
        """prepare() returns per-sample state (untimed); request(state) issues the timed call(s)."""
        if not wanted(name):
            return None
        record = {'samples_ms': [], 'bytes': [], 'attestations': [], 'requests': None, 'writes': writes}
        try:
            phases = (['cold'] if cold else []) + ['warm'] * args.samples
            for phase in phases:
                state = prepare(phase)
                before = counters['attest']; before_sql = counters['generation_sql']
                begin = time.perf_counter()
                responses = request(state)
                elapsed = (time.perf_counter() - begin) * 1000
                responses = responses if isinstance(responses, list) else [responses]
                if oracle:
                    oracle(responses, state)
                size = sum(len(r.get_data()) for r in responses)
                if phase == 'cold':
                    record['cold_ms'], record['cold_bytes'] = round(elapsed, 3), size
                    record['cold_attestations'] = counters['attest'] - before
                else:
                    record['samples_ms'].append(round(elapsed, 3))
                    record['bytes'].append(size)
                    record['attestations'].append(counters['attest'] - before)
                    record.setdefault('generation_sql', []).append(counters['generation_sql'] - before_sql)
                record['requests'] = len(responses)
                record['response_sha256'] = hashlib.sha256(b''.join(r.get_data() for r in responses)).hexdigest()
            state = prepare('count')
            profile = cProfile.Profile()
            profile.enable()
            try:
                responses = request(state)
            finally:
                profile.disable()
            responses = responses if isinstance(responses, list) else [responses]
            if oracle:
                oracle(responses, state)
            record['counts'], record['functions'] = count_profile(profile, source_python)
            record['median_ms'] = round(statistics.median(record['samples_ms']), 3)
            record['status'] = 'passed'
        except Exception as error:
            record['status'] = 'failed'
            record['error'] = f'{type(error).__name__}: {error}'
            record['traceback'] = traceback.format_exc()[-3000:]
        result['cases'][name] = record
        report('case', name=name, status=record['status'], median_ms=record.get('median_ms'),
               cold_ms=record.get('cold_ms'), error=record.get('error'))
        write()
        return record

    def same(value):
        return lambda phase: value

    base = f'/api/protocols/{protocol}'
    focus = main_ids[len(main_ids) // 2]
    focus_next = main_ids[len(main_ids) // 2 + 1]
    outside = next((key for key, row in service.rows.items() if row.get('protocol_name') == 'ambient'), None)

    def current_page():
        return call('get', f'{base}/epochs?limit=1').get_json()

    def ok_status(responses, state):
        for response in responses:
            if response.status_code != 200:
                raise AssertionError(response.status_code)

    # ---- Epoch reads -------------------------------------------------------
    measure('epoch.detail_in_protocol', same(None), lambda s: call('get', f'/api/epochs/{focus}?protocol_uuid={protocol}'),
            oracle=lambda r, s: r[0].get_json()['epoch_uuid'] == focus or (_ for _ in ()).throw(AssertionError('wrong epoch')))
    measure('epoch.detail', same(None), lambda s: call('get', f'/api/epochs/{focus}'))
    measure('epoch.annotations', same(None), lambda s: call('get', f'/api/epochs/{focus}/annotations'))
    measure('protocol.epochs_first', same(None), lambda s: call('get', f'{base}/epochs?limit=60&include_cells=true'),
            oracle=lambda r, s: r[0].get_json()['total'] == len(main_ids) or (_ for _ in ()).throw(AssertionError('total')))
    measure('protocol.epochs_deep', same(None), lambda s: call('get', f'{base}/epochs?limit=60&offset={max(0, len(main_ids) - 120)}'))
    measure('protocol.browse', same(None), lambda s: call('get', f'{base}?projection=browse'))
    measure('protocol.overview', same(None), lambda s: call('get', f'{base}/overview'))
    measure('overview', same(None), lambda s: call('get', '/api/overview'))

    # ---- Tree pages --------------------------------------------------------
    tree_body = {'protocol_uuid': protocol, 'splits': 'date,cell,block'}

    def tree_root():
        return call('post', '/api/tree-pages', tree_body).get_json()
    root = tree_root()
    measure('tree.root', same(None), lambda s: call('post', '/api/tree-pages', tree_body))

    def tree_child_state(phase):
        current = tree_root()
        return {'path': current['branches'][0]['path'], 'revision': current['revision']}
    measure('tree.expand_date', tree_child_state, lambda s: call('post', '/api/tree-pages', {**tree_body, 'path': s['path'], 'revision': s['revision']}))

    def tree_cell_state(phase):
        date = tree_child_state(phase)
        level = call('post', '/api/tree-pages', {**tree_body, 'path': date['path'], 'revision': date['revision']}).get_json()
        return {'path': level['branches'][0]['path'], 'revision': level['revision'], 'date': date}
    measure('tree.expand_cell', tree_cell_state, lambda s: call('post', '/api/tree-pages', {**tree_body, 'path': s['path'], 'revision': s['revision']}))
    measure('tree.next_page_cells', tree_child_state,
            lambda s: call('post', '/api/tree-pages', {**tree_body, 'path': s['path'], 'revision': s['revision'], 'offset': 80, 'limit': 80}))
    measure('tree.column_batch', tree_cell_state,
            lambda s: call('post', '/api/tree-pages', {**tree_body, 'path': s['path'], 'revision': s['revision'], 'include_ancestors': True}))
    measure('tree.root_counts_only', same(None), lambda s: call('post', '/api/tree-pages', {**tree_body, 'counts_only': True}))
    pager = app.extensions.get('disco.navigation.tree_pages')

    class Reply:  # Adapter so in-process production calls share measure().
        status_code = 200
        def __init__(self, value): self.value = value
        def get_data(self): return json.dumps(self.value, sort_keys=True).encode()
        def get_json(self): return self.value
    if pager is not None:
        def selection_state(phase):
            cell = tree_cell_state(phase)
            page = call('post', '/api/tree-pages', {**tree_body, 'path': cell['path'], 'revision': cell['revision']}).get_json()
            return {'path': cell['path'], 'revision': cell['revision'], 'count': page['selection']['count']}
        measure('tree.select_cell', selection_state, lambda s: Reply(pager.selection(
            {**tree_body, 'path': s['path'], 'revision': s['revision']}, s['count'])),
            oracle=lambda r, s: len(r[0].value['epoch_uuids']) == s['count'] or (_ for _ in ()).throw(AssertionError('count')))
    # The tree 'tag' filter reads shared effective tags (cell chips inherit).
    tag_tree = {'protocol_uuid': protocol, 'splits': 'cell', 'filters': {'tag': 'drift'}}
    expected_tag_total = len(shared_epochs) if shared is not None else 0
    measure('tree.tag_filtered_root', same(None), lambda s: call('post', '/api/tree-pages', tag_tree),
            oracle=lambda r, s: r[0].get_json()['total_epochs'] == expected_tag_total or (_ for _ in ()).throw(AssertionError(f"tag total {r[0].get_json().get('total_epochs')} != {expected_tag_total}")))

    # ---- Search and predicates --------------------------------------------
    measure('search.text', same(None), lambda s: call('get', '/api/search?q=cell'))
    measure('search.uuid_prefix', same(None), lambda s: call('get', f'/api/search?q={focus[:13]}'))
    measure('explore.predicate_fields', same(None), lambda s: call('get', '/api/explore/predicate-fields'))
    predicates = {
        'eq_cell_type': {'field': 'cell type', 'operator': 'eq', 'value': service.rows[focus]['cell_type']},
        'ne_cell_type': {'field': 'cell type', 'operator': 'ne', 'value': 'not-a-cell-type'},
        'exists_cell_type': {'field': 'cell type', 'operator': 'exists'},
        'missing_cell_type': {'field': 'cell type', 'operator': 'missing'},
        'missing_recorded': {'field': 'parameters/optional', 'operator': 'missing'},
        'range_contrast': {'all': [{'field': 'parameters/contrast', 'operator': 'gte', 'value': 0.25},
                                   {'field': 'parameters/contrast', 'operator': 'lt', 'value': 0.75}]},
        'eq_cell': {'field': 'cell', 'operator': 'eq', 'value': service.rows[focus]['cell_uuid']},
        'protocol_tag': {'field': f'curation/{protocol}/tags', 'operator': 'contains', 'value': 'bench-protocol-tag'},
        'shared_tag': {'field': 'annotations/epoch/tags', 'operator': 'contains', 'value': 'drift'},
        'effective_tag': {'field': 'annotations/effective/tags', 'operator': 'contains', 'value': 'good cell'},
        'tag_time': {'field': 'annotations/effective/tag_times', 'operator': 'contains',
                     'value': {'tag': 'drift', 'after': '2000-01-01T00:00:00Z'}},
        'and_or': {'all': [{'field': 'parameters/spotSize', 'operator': 'gt', 'value': 60.0},
                           {'any': [{'field': 'parameters/example', 'operator': 'eq', 'value': 3},
                                    {'field': 'annotations/epoch/tags', 'operator': 'contains', 'value': 'drift'}]}]},
    }
    counts = {}

    def countable(body):
        found = {}
        for key, value in body.items():
            if ('count' in key or 'total' in key or key == 'matched') and isinstance(value, (int, float)) and not isinstance(value, bool):
                found[key] = value
        return found
    for label, predicate in predicates.items():
        def page_rows(responses, state, _label=label):
            body = responses[0].get_json()
            counts.setdefault(_label, {})['page_rows'] = len(body.get('rows', body.get('epochs', [])))
        measure(f'explore.page.{label}', same(None), lambda s, p=predicate: call('post', '/api/explore/page',
                {'predicate': p, 'protocol_uuid': protocol, 'limit': 60}), oracle=page_rows)

        def preview_counts(responses, state, _label=label):
            counts.setdefault(_label, {})['preview'] = countable(responses[0].get_json())
        measure(f'explore.preview.{label}', same(None), lambda s, p=predicate: call('post', '/api/explore/preview',
                {'predicate': p, 'splits': 'cell', 'summary_only': True}), oracle=preview_counts)
    for label in ('eq_cell_type', 'protocol_tag', 'and_or'):
        measure(f'explore.run.{label}', same(None), lambda s, p=predicates[label]: call('post', '/api/explore/run',
                {'predicate': p, 'splits': 'cell'}))

    def summaries(state):
        submitted = call('post', '/api/explore/summaries', {'predicate': predicates['range_contrast'],
                         'summary_fields': ['cell type', 'parameters/contrast'], 'protocol_uuid': protocol},
                         expected=(200, 202))
        identity = submitted.get_json().get('request_id')
        replies = [submitted]
        deadline = time.monotonic() + 600
        while identity:
            poll = call('get', f'/api/explore/summaries/{identity}')
            replies.append(poll)
            if poll.get_json().get('status') not in ('queued', 'running', 'pending'):
                break
            if time.monotonic() > deadline:
                raise TimeoutError('summary job did not finish')
            time.sleep(0.01)
        return replies
    polled = measure('explore.summaries_poll', same(None), summaries)
    if polled:
        polled['counts_variable'] = 'Poll count depends on job timing; counts are not compared.'
    result['predicate_counts'] = counts

    # ---- Decisions: curation, approval, tags --------------------------------
    def curation_state(phase, target=focus):
        current = current_page()
        read = call('post', f'{base}/curation/read', {'epoch_uuids': [target], 'query_revision': current['query_revision'],
                    'expected_binding_version': current['expected_binding_version'],
                    'selection_scope': {'filters': {}, 'cell_uuid': None}}).get_json()
        detail = call('get', f'/api/epochs/{target}?protocol_uuid={protocol}').get_json()
        included = (detail.get('curation') or {}).get('included', True)
        return {'page': current, 'revision': read['epochs'][0]['curation_revision'], 'included': included, 'target': target}

    def curation_body(state, changes):
        return {'epoch_uuids': [state['target']], 'query_revision': state['page']['query_revision'],
                'expected_binding_version': state['page']['expected_binding_version'],
                'selection_scope': {'filters': {}, 'cell_uuid': None}, 'changes': changes,
                'expected_revisions': {state['target']: state['revision']}}

    def toggle(state):
        return call('post', f'{base}/curation', curation_body(state, {'included': not state['included']}))
    measure('curation.toggle_include', curation_state, toggle, writes=True, cold=False)

    def read_then_toggle(state):
        read = call('post', f'{base}/curation/read', {'epoch_uuids': [state['target']], 'query_revision': state['page']['query_revision'],
                    'expected_binding_version': state['page']['expected_binding_version'],
                    'selection_scope': {'filters': {}, 'cell_uuid': None}})
        return [read, toggle(state)]
    measure('curation.read_and_toggle', curation_state, read_then_toggle, writes=True, cold=False)

    def after_toggle(phase):
        toggle(curation_state(phase))
        return None
    measure('curation.then_epoch_read', after_toggle, lambda s: call('get', f'/api/epochs/{focus_next}?protocol_uuid={protocol}'), cold=False)
    measure('curation.then_epochs_page', after_toggle, lambda s: call('get', f'{base}/epochs?limit=60'), cold=False)
    measure('curation.then_tree_root', after_toggle, lambda s: call('post', '/api/tree-pages', tree_body), cold=False)

    approvals = {'flip': False}

    def approve(state):
        approvals['flip'] = not approvals['flip']
        return call('post', f'{base}/curation', curation_body(state, {'review_state': 'approved' if approvals['flip'] else 'unreviewed'}))
    measure('curation.approve', curation_state, approve, writes=True, cold=False)

    def after_approve(phase):
        state = curation_state(phase)
        approvals['flip'] = not approvals['flip']
        call('post', f'{base}/curation', curation_body(state, {'review_state': 'approved'}))
        return None
    measure('approve.then_epoch_read', after_approve, lambda s: call('get', f'/api/epochs/{focus_next}?protocol_uuid={protocol}'), cold=False)
    measure('approve.then_tree_expand', lambda phase: (after_approve(phase), tree_child_state(phase))[1],
            lambda s: call('post', '/api/tree-pages', {**tree_body, 'path': s['path'], 'revision': s['revision']}), cold=False)

    if shared is not None:
        serial = {'n': 0}

        def tag_state(phase):
            serial['n'] += 1
            current = call('post', '/api/annotations/read', {'target_kind': 'epoch', 'target_uuids': [focus]}).get_json()
            return {'tag': f'bench-tag-{serial["n"]}', 'revision': current['targets'][focus]['revisions'].get(author, 0)}

        def add_tag(state):
            return call('post', '/api/annotations', {'target_kind': 'epoch', 'target_uuids': [focus], 'profile_uuid': author,
                        'tags_add': [state['tag']], 'tags_remove': [], 'expected_revisions': {focus: state['revision']}})
        measure('tag.add_epoch', tag_state, add_tag, writes=True, cold=False)

        def after_tag(phase):
            add_tag(tag_state(phase))
            return None
        measure('tag.then_epoch_read', after_tag, lambda s: call('get', f'/api/epochs/{focus_next}?protocol_uuid={protocol}'), cold=False)
        measure('tag.then_epochs_page', after_tag, lambda s: call('get', f'{base}/epochs?limit=60'), cold=False)
        measure('tag.then_overview', after_tag, lambda s: call('get', '/api/overview'), cold=False)
        measure('tag.then_tree_root', after_tag, lambda s: call('post', '/api/tree-pages', tree_body), cold=False)
    else:
        result['skipped']['tag.*'] = 'Source has no SharedAnnotations extension'

    # ---- Workbench: queue, merge-all, undo -----------------------------------
    root_path = f'{base}/workbench'
    measure('workbench.queue', same(None), lambda s: call('get', f'{root_path}?limit=20'),
            oracle=lambda r, s: r[0].get_json().get('pending_epoch_count', meta['incoming_count']) == meta['incoming_count']
            or (_ for _ in ()).throw(AssertionError('pending count')))
    measure('workbench.summary', same(None), lambda s: call('get', '/api/workbench/summary'))
    receipts = {}

    def merge_state(phase):
        queue = call('get', f'{root_path}?limit=20').get_json()
        return {'queue_revision': queue['queue_revision'], 'operation': str(uuid.uuid4())}

    def merge_all(state):
        reply = call('post', f'{root_path}/merge-all', {'expected_queue_revision': state['queue_revision'],
                     'operation_uuid': state['operation']})
        receipts['last'] = reply.get_json()
        return reply

    def undo_last(state=None):
        receipt = receipts.pop('last')
        return call('post', f'{root_path}/undo', {'operation_uuid': receipt['operation_uuid'],
                    'expected_binding_version': receipt['binding']['version']})

    def merge_then_undo_state(phase):
        state = merge_state(phase)
        return state

    def merge_oracle(responses, state):
        receipt = responses[0].get_json()
        if receipt.get('accepted_epoch_count') != meta['incoming_count']:
            raise AssertionError(f"merge-all accepted {receipt.get('accepted_epoch_count')}")
    # Each sample merges then undoes (outside the merge clock) to restore the pool.
    if wanted('workbench.merge_all'):
        record_merge = measure('workbench.merge_all', merge_then_undo_state,
                               lambda s: (merge_all(s), undo_last())[0], oracle=merge_oracle, writes=True, cold=False)
        if record_merge:
            record_merge['note'] = 'Timed span includes the paired undo; see workbench.undo for undo alone.'

    def undo_state(phase):
        merge_all(merge_state(phase))
        return None
    measure('workbench.undo', undo_state, lambda s: undo_last(), writes=True, cold=False)
    measure('workbench.queue_after_undo', undo_state and (lambda phase: (merge_all(merge_state(phase)), undo_last(), None)[2]),
            lambda s: call('get', f'{root_path}?limit=20'), cold=False)

    result['index_closed'] = True
    try:
        index.close()
    except Exception as error:
        result['index_closed'] = False
        result['notes'].append(f'index close failed: {error}')
    fixture.doCleanups()


try:
    main()
    failed = [name for name, case in result['cases'].items() if case['status'] != 'passed']
    result['failed_cases'] = failed
    result['status'] = 'passed' if not failed and not result['h5_open_attempts'] else 'failed'
except Exception as error:
    result['status'] = 'failed'
    result['error'] = f'{type(error).__name__}: {error}'
    result['traceback'] = traceback.format_exc()
finally:
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result['peak_rss_bytes'] = peak if sys.platform == 'darwin' else peak * 1024
    result['elapsed_seconds'] = time.perf_counter() - started
    write()
    report('done', status=result['status'])
sys.exit(0 if result['status'] == 'passed' else 1)
