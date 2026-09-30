"""Native dense-tag API workload in a fresh disposable project.

Actual MySQL, triggers, SQLite indexes, Flask routes and save/checkpoint hooks.
Acquisition metadata is synthetic; no H5 parsing/waveform/NAS/browser claim.
"""
import argparse
import copy
import cProfile
import datetime as dt
import hashlib
import json
import math
import pstats
from pathlib import Path
import resource
import statistics
import tempfile
import time
import traceback
import uuid

from benchmark_service_scale import fixture, Details, uid
from recording_workspace import connect, workspace_tables
from workspace_projects import create_project
from workspace_native_mysql import ensure_native_database, stop_native_database
from workspace_disk_index import DiskMetadataIndex
from workspace_api import create_app

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FILES = ['workspace_api.py', 'workspace_service.py', 'workspace_curation.py',
         'workspace_protocol_state.py', 'workspace_state_generation.py',
         'workspace_annotations.py', 'workspace_shared_tag_index.py', 'workspace_state_snapshot.py',
         'workspace_recovery_store.py', 'workspace_recovery_generation.py', 'workspace_curation_vocabulary.py']


def hashes():
    return {name: hashlib.sha256((ROOT / 'python' / name).read_bytes()).hexdigest() for name in FILES}


def tags_for(ordinal, profile, size, *, cell=False):
    initial = (['inherited', f'cell-bucket:{ordinal % 13}', f'profile:{profile}', 'same', 'cell-tag'] if cell else
               ['all', f'bucket:{ordinal % 97}', 'ON' if ordinal % 2 == 0 else 'on',
                'é' if ordinal % 3 == 0 else 'e\u0301', f'profile:{profile}'])
    return initial[:size] + [f'extra:{profile}:{index}' for index in range(len(initial), size)]


def percentiles(values):
    ordered = sorted(values)
    return {'samples_seconds': values, 'p50_seconds': statistics.median(values),
            'p95_seconds': ordered[max(0, math.ceil(.95 * len(ordered)) - 1)],
            'max_seconds': max(values)}


def disk_bytes(path):
    files = [path] if path.is_file() else [p for p in path.rglob('*') if p.is_file() and not p.is_symlink()]
    return {'apparent_bytes': sum(p.stat().st_size for p in files),
            'allocated_bytes': sum(p.stat().st_blocks * 512 for p in files), 'files': len(files)}


def run(args, report):
    app = None; dj = None
    with tempfile.TemporaryDirectory(prefix='rieke-native-dense-tags-') as directory:
        root = Path(create_project(Path(directory) / 'projects', 'Disposable dense tag benchmark')['path'])
        try:
            ensure_native_database(root)
            dj = connect({'kind': 'native-project'}, project_dir=root)
            service, protocol = fixture(args.epochs)
            service.project_dir = root
            service.project = json.loads((root / 'project.json').read_text())
            service.config = json.loads((root / 'catalog.json').read_text())
            service.dj = dj
            other = uid(-3)
            service.protocols[other] = copy.deepcopy(service.protocols[protocol])
            service.protocols[other]['definition']['protocol_uuid'] = other
            service.protocols[other]['result']['protocol_uuid'] = other
            for value in service.protocols.values():
                value['definition']['project_uuid'] = service.project['project_uuid']
                value['definition']['query'] = {'version': 1, 'all': [
                    {'field': 'EpochBlock.protocol_name', 'operator': 'eq', 'value': 'Synthetic'}]}
            index = DiskMetadataIndex.build(root / 'cache' / 'dense.sqlite', service.rows, Details(service.rows),
                service.sources, 'native-dense-synthetic-acquisition', service.project['project_uuid'])
            service.disk_index = index; service.details = index.details
            Project, _, _, _ = workspace_tables(dj)
            Project.insert1({'project_uuid': service.project['project_uuid'], 'name': service.project['name'], 'directory': str(root)})
            app = create_app(root, ROOT / '.rieke-runtime/retinanalysis', service=service)
            assert service._recovery_tracker.ready, service._recovery_tracker.reason
            tracker = app.extensions['state_generation']
            assert tracker.ready, tracker.reason
            assert tracker.token(protocol) is not None, tracker.reason
            report['mysql_version'] = dj.conn().query('SELECT VERSION()').fetchone()[0]
            store = app.extensions['curation_store']; shared = app.extensions['shared_annotations']
            authors = [uid(-100 - i) for i in range(args.profiles)]
            now = dt.datetime(2026, 6, 11, 12)
            project_id = service.project['project_uuid']
            started = time.perf_counter()
            with dj.conn().transaction:
                shared.Profile.insert([{'project_uuid': project_id, 'profile_uuid': author,
                    'display_name': f'Scientist {p}', 'created_at': now, 'created_by': 'native benchmark'}
                    for p, author in enumerate(authors)])
                batch = []
                for kind, identities in (('epoch', service.rows), ('cell', service.cells)):
                    for ordinal, identity in enumerate(identities):
                        for profile, author in enumerate(authors):
                            batch.append({'project_uuid': project_id, 'target_kind': kind, 'target_uuid': identity,
                                'profile_uuid': author, 'tags': tags_for(ordinal, profile, args.tags, cell=kind == 'cell'),
                                'author_name': f'Scientist {profile}', 'revision': 1, 'updated_at': now})
                            if len(batch) == 500:
                                shared.Annotation.insert(batch); batch.clear()
                    if batch: shared.Annotation.insert(batch); batch.clear()
                for position, current_protocol in enumerate((protocol, other)):
                    dataset_tags = [f'dataset:{position}'] + [f'dataset-tag:{i}' for i in range(1, args.tags)]
                    for identity in service.rows:
                        batch.append({'project_uuid': project_id, 'protocol_uuid': current_protocol,
                            'epoch_uuid': identity, 'included': True, 'tags': dataset_tags,
                            'review_state': 'unreviewed', 'revision': 1,
                            'metadata_fingerprint': service._fingerprints[identity]})
                        if len(batch) == 500: store.Curation.insert(batch); batch.clear()
                    if batch: store.Curation.insert(batch); batch.clear()
            report['seed_seconds'] = time.perf_counter() - started
            report['shared_rows'] = (len(service.rows) + len(service.cells)) * args.profiles
            report['dataset_curation_rows'] = 2 * args.epochs
            print('Native tags seeded', flush=True)
            from workspace_state_snapshot import save as save_recovery
            started = time.perf_counter()
            report['seed_checkpoint'] = save_recovery(root, dj.conn(), service=service)
            report['seed_checkpoint']['seconds'] = time.perf_counter() - started
            print('Seed recovery checkpoint durable', flush=True)
            client = app.test_client(); base = f'/api/protocols/{protocol}'
            headers = {'X-Workspace-Request': '1', 'Origin': 'http://localhost:8766'}
            report['operations'] = []

            def sql_status():
                return {key: int(value) for key, value in dj.conn().query(
                    "SHOW SESSION STATUS WHERE Variable_name IN ('Rows_sent','Bytes_sent','Questions')").fetchall()}

            def get(path, query=None):
                response = client.get(path, query_string=query)
                value = response.get_json()
                assert response.status_code == 200, (response.status_code, value)
                return value

            def measure(name, callback, repeat=None):
                durations = []; sql = []; result = None
                profile = cProfile.Profile() if args.profile and any(value in name for value in ('summary', 'overview', 'suggestions')) else None
                for _ in range(args.samples if repeat is None else repeat):
                    before = sql_status(); start = time.perf_counter()
                    if profile is not None: profile.enable()
                    result = callback()
                    if profile is not None: profile.disable()
                    durations.append(time.perf_counter() - start)
                    after = sql_status(); sql.append({key: after[key] - before[key] for key in before})
                record = {'name': name, **percentiles(durations), 'sql_session_deltas': sql}
                if profile is not None:
                    profile_path = args.output.with_name(args.output.stem + '.' + name + '.prof')
                    profile.dump_stats(str(profile_path))
                    stats = pstats.Stats(profile)
                    record['profile'] = [{'file': key[0], 'line': key[1], 'function': key[2],
                        'primitive_calls': value[0], 'calls': value[1], 'own_seconds': value[2],
                        'cumulative_seconds': value[3]} for key, value in
                        sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)[:60]]
                report['operations'].append(record)
                print(json.dumps({'operation': name, 'p50': record['p50_seconds'], 'p95': record['p95_seconds']}), flush=True)
                return result

            page = measure('page_cold', lambda: get(base + '/epochs', {'limit': 60}), 1)
            assert len(page['epochs']) == min(60, args.epochs) and page['total'] == args.epochs
            for row in page['epochs']:
                ordinal = service.rows[row['epoch_uuid']]['synthetic_index']
                expected = sorted((tag, authors[p]) for p in range(args.profiles) for tag in tags_for(ordinal, p, args.tags))
                actual = sorted((item['tag'], item['profile_uuid']) for item in row['annotations']['epoch_tags'])
                assert actual == expected
                assert len(row['curation']['tags']) == args.tags
            measure('page_warm', lambda: get(base + '/epochs', {'limit': 60}))
            for tag, check in [('ON', lambda i: i % 2 == 0), ('on', lambda i: i % 2 != 0),
                               ('bucket:7', lambda i: i % 97 == 7), ('inherited', lambda i: True)]:
                expected = [key for key, row in service.rows.items() if check(row['synthetic_index'])]
                result = measure('filter_cold_' + tag, lambda tag=tag: get(base + '/epochs', {'limit': 60, 'tag': tag}), 1)
                assert result['total'] == len(expected), (tag, result['total'], len(expected))
                assert [row['epoch_uuid'] for row in result['epochs']] == expected[:60]
                measure('filter_warm_' + tag, lambda tag=tag: get(base + '/epochs', {'limit': 60, 'tag': tag}))
            measure('protocol_summary_after_tagged_load', lambda: get(base), 1)
            measure('overview_after_tagged_load', lambda: get('/api/overview'), 1)
            measure('dataset_tag_suggestions_cold', lambda: get('/api/tags', {'q': 'dataset', 'limit': 30}), 1)
            measure('dataset_tag_suggestions_warm', lambda: get('/api/tags', {'q': 'dataset', 'limit': 30}), 3)
            identity = next(iter(service.rows)); revision = 1
            for iteration in range(args.edits):
                current = get(base + '/epochs', {'limit': 1})
                body = {'epoch_uuids': [identity], 'query_revision': current['query_revision'],
                    'expected_revisions': {identity: revision}, 'expected_binding_version': 0,
                    'changes': {'tags_add': [f'edited:{iteration}']}}
                def edit():
                    response = client.post(base + '/curation', json=body, headers=headers)
                    assert response.status_code == 200, (response.status_code, response.get_json())
                    return response.get_json()
                measure('edit_with_durable_backup_' + str(iteration), edit, 1)
                revision += 1
                result = measure('first_page_after_edit_' + str(iteration), lambda: get(base + '/epochs', {'limit': 60}), 1)
                assert result['epochs'][0]['curation']['revision'] == revision
                assert f'edited:{iteration}' in result['epochs'][0]['curation']['tags']
                measure('protocol_summary_after_edit_' + str(iteration), lambda: get(base), 1)
                measure('overview_after_edit_' + str(iteration), lambda: get('/api/overview'), 1)
                measure('dataset_tag_suggestions_after_edit_' + str(iteration),
                        lambda: get('/api/tags', {'q': 'dataset', 'limit': 30}), 1)
            for iteration in range(args.edits):
                body = {'target_kind': 'epoch', 'target_uuids': [identity], 'profile_uuid': authors[0],
                    'tags_add': [f'shared-edited:{iteration}'], 'expected_revisions': {identity: iteration + 1}}
                def shared_edit():
                    response = client.post('/api/annotations', json=body, headers=headers)
                    assert response.status_code == 200, (response.status_code, response.get_json())
                    return response.get_json()
                measure('shared_edit_with_durable_backup_' + str(iteration), shared_edit, 1)
                result = measure('shared_filter_after_edit_' + str(iteration), lambda: get(base + '/epochs',
                    {'limit': 60, 'tag': f'shared-edited:{iteration}'}), 1)
                assert result['total'] == 1 and result['epochs'][0]['epoch_uuid'] == identity
                measure('shared_summary_after_edit_' + str(iteration), lambda: get(base), 1)
            report['shared_index_stats'] = getattr(getattr(shared, '_shared_tag_index', None), 'stats', None)
            vocabulary = getattr(store, '_curation_vocabulary_index', None)
            report['curation_vocabulary_stats'] = getattr(vocabulary, 'stats', None)
            if vocabulary is not None:
                report['curation_vocabulary_storage'] = vocabulary.storage_stats()
            index = getattr(shared, '_shared_tag_index', None)
            index_path = getattr(index, 'path', None)
            report['storage'] = {'project': disk_bytes(root), 'native_database': disk_bytes(root / 'database'),
                'source_metadata_index': disk_bytes(root / 'cache'), 'recovery': disk_bytes(root / 'backups')}
            if index_path is not None:
                report['storage']['shared_tag_index'] = disk_bytes(Path(index_path))
            if index is not None:
                report['storage']['shared_tag_index_sqlite'] = index.storage_stats()
            report['storage']['sql_tables'] = dj.conn().query(
                "SELECT TABLE_NAME,TABLE_ROWS,DATA_LENGTH,INDEX_LENGTH,DATA_FREE FROM information_schema.tables "
                "WHERE TABLE_SCHEMA='recording_workspace' ORDER BY TABLE_NAME", as_dict=True).fetchall()
            report['storage']['note'] = 'SQL row/byte estimates may lag; filesystem apparent and allocated totals include native redo/preallocation. Synthetic acquisition has no real waveform-size denominator.'
            report['oracle_passed'] = True
        finally:
            if app is not None:
                shared = app.extensions.get('shared_annotations')
                index = getattr(shared, '_shared_tag_index', None)
                if index is not None: index.close()
                lock = app.extensions.get('app_state_session_lock')
                if lock is not None: lock.close()
            if dj is not None: dj.conn().close()
            stop_native_database(root)
            report['owned_runtime_stopped'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs', type=int, default=1000)
    parser.add_argument('--tags', type=int, choices=(5, 20), default=5)
    parser.add_argument('--profiles', type=int, default=3)
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--edits', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', action='store_true', help='Profile summary, overview and suggestion operations; timings include profiler overhead')
    parser.add_argument('--mysql-runtime-root', type=Path,
                        help='Verified external runtime for copied-source validation; no live database reuse')
    args = parser.parse_args()
    if args.output.exists(): parser.error('Choose a new receipt path')
    if args.mysql_runtime_root is not None:
        from workspace_mysql_runtime import _probe, runtime_spec
        import workspace_native_mysql as native
        runtime = _probe(args.mysql_runtime_root.resolve(strict=True), runtime_spec(ROOT)[0]['mysql_version'])
        def runtime_binary(name='mysqld'):
            if name not in {'mysqld', 'mysql', 'mysqldump'}:
                raise ValueError('Unsupported external native executable')
            return Path(runtime[name])
        native.native_binary = runtime_binary
    report = {'epochs': args.epochs, 'tags_per_record': args.tags, 'profiles': args.profiles,
              'protocols': 2, 'source_hashes_before': hashes(), 'release_ready': False,
              'external_mysql_runtime': str(args.mysql_runtime_root) if args.mysql_runtime_root else None,
              'scope': 'Actual native MySQL + production Flask/save hooks + sealed SQLite synthetic metadata; excludes physical H5 parsing, waveform/NAS I/O and browser rendering.'}
    try:
        run(args, report)
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
        print(traceback.format_exc(), flush=True)
    report['source_hashes_after'] = hashes()
    report['source_changed_during_run'] = [name for name, value in report['source_hashes_before'].items()
                                          if value != report['source_hashes_after'][name]]
    report['peak_rss_bytes_macos'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['passed'] = bool(report.get('oracle_passed')) and not report['source_changed_during_run']
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
