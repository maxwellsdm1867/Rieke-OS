"""Bounded catalog-only controls, never full Flask filter-preview timings."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import statistics
import threading
import time
import traceback

import psutil
from workspace_disk_index import DiskMetadataIndex
from eav_duck import DuckCatalogIndex, derive_from_typed, digest, import_sqlite
from projection import identity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, choices=(100000, 1000000), required=True)
    parser.add_argument('--source-sqlite', type=Path, required=True)
    parser.add_argument('--duck-path', type=Path, required=True)
    parser.add_argument('--typed-path', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse', action='store_true')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.epochs == 1000000 and args.typed_path is None:
        parser.error('Million-epoch mode requires --typed-path')
    report = {'epochs': args.epochs, 'status': 'running', 'phases': {}, 'operations': [],
              'resources': [], 'scope': 'Exact current production DiskMetadataIndex.catalog algorithm plus canonical JSON serialization on the contrast=.3 subset. Catalog-only: excludes complete Flask filter-preview, native curation/revisions, frozen membership payload, browser paint and details. The 100k import arm isolates EAV engine; derived1m SQL EAV is synthetic metadata only.'}
    process = psutil.Process()
    start, phase_start = time.monotonic(), time.monotonic()
    phase, done = 'initialization', False
    lock = threading.RLock()

    def save():
        with lock:
            temporary = args.output.with_suffix('.tmp')
            temporary.write_text(json.dumps(report, indent=2))
            temporary.replace(args.output)

    def enter(name):
        nonlocal phase, phase_start
        phase, phase_start = name, time.monotonic()
        report['phase'] = name
        save()
        print(json.dumps({'phase': name, 'epochs': args.epochs}), flush=True)

    def watch():
        while not done:
            sample = {'elapsed_seconds': time.monotonic() - start,
                      'rss_mib': process.memory_info().rss / 1024**2,
                      'available_mib': psutil.virtual_memory().available / 1024**2,
                      'free_disk_gib': shutil.disk_usage(args.output.parent).free / 1024**3}
            report['resources'].append(sample)
            reason = None
            if sample['rss_mib'] > 1536:
                reason = 'Owned catalog worker RSS exceeds 1.5 GiB'
            elif sample['available_mib'] < 600:
                reason = 'System available memory below 600 MiB'
            elif sample['free_disk_gib'] < 4:
                reason = 'Free disk below 4 GiB'
            elif time.monotonic() - phase_start > 180:
                reason = 'Owned phase exceeds 180 seconds'
            if reason:
                report.update(status='guard_stopped', reason=reason, seconds=time.monotonic() - start)
                save()
                os._exit(75)
            save()
            time.sleep(1)

    threading.Thread(target=watch, daemon=True).start()
    sqlite_index, duck_index = None, None
    try:
        enter('known_fields_before_timing')
        raw = sqlite3.connect(f'file:{args.source_sqlite}?mode=ro&immutable=1', uri=True)
        metadata = {key: json.loads(value) for key, value in raw.execute('SELECT key,value FROM meta')}
        raw.close()
        sqlite_index = DiskMetadataIndex.open(args.source_sqlite, metadata['generation'], metadata['project_uuid'])
        known_fields = sqlite_index.catalog()['fields']
        report['known_field_ids'] = [field['id'] for field in known_fields]
        report['source_generation'] = metadata['generation']
        enter('eav_build')
        if not args.reuse:
            if args.duck_path.exists():
                raise ValueError('Destination exists; use explicit --reuse only for this immutable fixture')
            if args.epochs == 100000:
                report['phases']['build'] = import_sqlite(args.source_sqlite, args.duck_path)
            else:
                report['phases']['build'] = derive_from_typed(args.typed_path, args.source_sqlite, args.duck_path)
        else:
            report['phases']['build'] = {'reused': True, 'not_a_fresh_build_measurement': True}
        enter('persisted_reopen_and_scope')
        before = time.perf_counter()
        duck_index = DuckCatalogIndex(args.duck_path)
        report['phases']['reopen_seconds'] = time.perf_counter() - before
        if duck_index._epoch_count != args.epochs:
            raise ValueError('Epoch count does not match requested fixture')
        scope = [row[0] for row in duck_index.connection.execute('''SELECT e.epoch_uuid FROM epochs e
            JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no)
            JOIN field_values v USING(value_id) WHERE f.field_id='parameters/contrast'
            AND v.value_json='0.3' ORDER BY e.epoch_id''').fetchall()]
        actual_hash, expected_hash = hashlib.sha256(), hashlib.sha256()
        for value in scope:
            actual_hash.update((value + '\n').encode())
        for index in range(3, args.epochs, 5):
            expected_hash.update((identity(index) + '\n').encode())
        if actual_hash.digest() != expected_hash.digest():
            raise ValueError('Independent arithmetic membership/order oracle failed')
        report['scope_count'] = len(scope)
        report['scope_sha256'] = actual_hash.hexdigest()

        expected_distinct = {'epoch': len(scope), 'date': 1, 'cell': args.epochs // 100,
                             'block': args.epochs // 20, 'block time': len(scope),
                             'cell type': 2, 'group label': 1, 'group': 1, 'protocol': 1,
                             'parameters/contrast': 1, 'parameters/currentMean': 3,
                             'parameters/seed': len(scope), 'parameters/stimTime': 1,
                             'metadata/cell/properties/type': 2,
                             'metadata/cell/label': args.epochs // 100,
                             'metadata/block/parameters/amp': 1}

        def oracle(catalog):
            if catalog['total'] != len(scope) or len(catalog['fields']) != 16:
                raise ValueError('Total or registered field count differs')
            for field in catalog['fields']:
                if (field['distinct_count'] != expected_distinct[field['id']]
                    or field['missing_count'] != 0 or field['null_count'] != 0
                    or field['count'] != len(scope)):
                    raise ValueError('Independent field statistics oracle failed: ' + field['id'])

        # JSON numeric kinds are part of the dictionary semantics. They cannot
        # be checked by Python equality, where integers and floats compare equal.
        for field, kind in [('parameters/contrast', float), ('parameters/seed', int),
                            ('parameters/currentMean', int), ('parameters/stimTime', int)]:
            values = duck_index.connection.execute('''SELECT value_json FROM field_values v JOIN fields f USING(field_no)
                WHERE f.field_id=? LIMIT 10''', [field]).fetchall()
            if any(type(json.loads(value)) is not kind for value, in values):
                raise ValueError('Parameter JSON type oracle failed: ' + field)
        report['independent_membership_and_types_passed'] = True

        control_hash = None
        arms = [('sqlite_eav', sqlite_index), ('duckdb_eav', duck_index)] if args.epochs == 100000 else [('duckdb_derived_eav', duck_index)]
        for name, engine in arms:
            enter('measure_' + name)
            samples, hashes, byte_sizes = [], [], []
            for repeat in range(10):
                before = time.perf_counter()
                result = engine.catalog(scope, known_fields)
                encoded = json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
                samples.append(time.perf_counter() - before)
                oracle(result)
                hashes.append(hashlib.sha256(encoded).hexdigest())
                byte_sizes.append(len(encoded))
                report['active_samples_seconds'] = samples
                save()
            if len(set(hashes)) != 1:
                raise ValueError('Repeated full catalog changed')
            if name == 'sqlite_eav':
                control_hash = hashes[0]
            elif control_hash is not None and hashes[0] != control_hash:
                raise ValueError('Exact SQLite/DuckDB full catalog hash differs')
            operation = {'name': name, 'samples_seconds': samples,
                         'first_seconds': samples[0], 'median_seconds': statistics.median(samples),
                         'warm_median_seconds': statistics.median(samples[1:]),
                         'maximum_seconds': max(samples), 'catalog_sha256': hashes[0],
                         'response_json_bytes': byte_sizes[-1], 'independent_oracle_passed': True,
                         'exact_sqlite_control_hash_passed': hashes[0] == control_hash if control_hash else None}
            report['operations'].append(operation)
            (args.output.parent / (args.output.stem + '-' + name + '-catalog.json')).write_text(json.dumps(result, indent=2))
            save()
        report.update(status='passed', seconds=time.monotonic() - start,
                      peak_sampled_rss_mib=max(sample['rss_mib'] for sample in report['resources']))
    except BaseException as error:
        report.update(status='failed', error=str(error), traceback=traceback.format_exc(), seconds=time.monotonic() - start)
        raise
    finally:
        done = True
        if duck_index is not None:
            duck_index.close()
        if sqlite_index is not None:
            sqlite_index.close()
        save()


if __name__ == '__main__':
    main()
