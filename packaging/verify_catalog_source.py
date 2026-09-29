"""Read-only native catalog audit against original Symphony H5 files.

Run with the installed runtime Python. No application parser is used as an oracle.
The database must already be running. All SQL executes in a read-only transaction.
Example: python packaging/verify_catalog_source.py --project PATH --inventory JSON
         --base-url http://127.0.0.1:PORT --output receipt.json
Inventory is a JSON list of paths or objects with a path member. Only original .h5
recordings are accepted; .auisql.h5 and .asqul.h5 companions are rejected.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen

import h5py
import numpy as np
import pymysql

TABLES = ('animal', 'preparation', 'cell', 'epoch_group', 'epoch_block', 'epoch', 'response', 'stimulus')


def value(v):
    if isinstance(v, h5py.Empty):
        return None
    if isinstance(v, bytes):
        return v.decode('utf-8')
    if isinstance(v, np.ndarray):
        return value(v.tolist())
    if isinstance(v, np.generic):
        return value(v.item())
    if isinstance(v, list):
        return [value(x) for x in v]
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def attrs(group):
    return {k: value(v) for k, v in group.attrs.items()}


def members(group, name):
    return group[name].values() if name in group else ()


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def equal(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


class Audit:
    def __init__(self):
        self.failures = []
        self.failure_count = 0
        self.failure_categories = Counter()
        self.checks = Counter()

    def check(self, condition, category, context):
        self.checks[category] += 1
        if not condition:
            self.failure_count += 1
            self.failure_categories[category] += 1
            if len(self.failures) < 200:
                self.failures.append({'check': category, 'context': context})

    def metadata(self, expected, actual, category, context):
        actual = json.loads(actual) if isinstance(actual, str) else actual
        for key, v in expected.items():
            self.check(isinstance(actual, dict) and key in actual and equal(v, actual[key]),
                       category, f'{context}: {key}')


def audit_source(path, source, connection, audit, base_url):
    before = sha(path)
    result = {'name': path.name, 'bytes': path.stat().st_size, 'sha256': before}
    audit.check(before == source['source_sha256'], 'source_sha256', path.name)
    with connection.cursor() as cur:
        cur.execute('SELECT * FROM `schema`.`experiment` WHERE id=%s', (source['experiment_id'],))
        experiment_row = cur.fetchone()
        rows = {}
        for table in TABLES:
            if table in ('response', 'stimulus'):
                cur.execute(f'SELECT s.* FROM `schema`.`{table}` s JOIN `schema`.`epoch` e ON e.id=s.parent_id WHERE e.experiment_id=%s', (source['experiment_id'],))
            else:
                cur.execute(f'SELECT * FROM `schema`.`{table}` WHERE experiment_id=%s', (source['experiment_id'],))
            fetched = cur.fetchall()
            rows[table] = {r['h5_uuid']: r for r in fetched}
            audit.check(len(rows[table]) == len(fetched), 'unique_db_uuid', f'{path.name}/{table}')
        cur.execute('SELECT protocol_id,name FROM `schema`.`protocol`')
        protocols = {r['protocol_id']: r['name'] for r in cur.fetchall()}
    expected = {t: {} for t in TABLES}
    samples = []
    with h5py.File(path, 'r') as h5:
        experiments = [h5[k] for k in h5 if k.startswith('experiment-')]
        audit.check(len(experiments) == 1, 'one_experiment', path.name)
        exp = experiments[0]
        audit.check(value(exp.attrs['uuid']) == source['experiment_uuid'] == experiment_row['h5_uuid'], 'experiment_uuid', path.name)
        audit.metadata(attrs(exp), experiment_row['attributes'], 'attributes', path.name)
        if 'properties' in exp:
            audit.metadata(attrs(exp['properties']), experiment_row['properties'], 'properties', path.name)

        def record(table, obj, parent=None, parameters=None):
            uid = value(obj.attrs['uuid'])
            audit.check(uid not in expected[table], 'unique_source_uuid', f'{table}/{uid}')
            expected[table][uid] = obj.name
            row = rows[table].get(uid)
            if row is None:
                return
            ctx = f'{path.name}/{table}/{uid}'
            if parent:
                parent_table, parent_uuid = parent
                parent_row = rows[parent_table].get(parent_uuid)
                audit.check(parent_row is not None and row['parent_id'] == parent_row['id'], 'parent_link', ctx)
            if 'attributes' in row:
                audit.metadata(attrs(obj), row['attributes'], 'attributes', ctx)
            if 'properties' in obj and 'properties' in row:
                audit.metadata(attrs(obj['properties']), row['properties'], 'properties', ctx)
            if parameters is not None:
                audit.metadata(parameters, row['parameters'], 'parameters', ctx)
            if 'label' in obj.attrs and 'label' in row:
                audit.check(value(obj.attrs['label']) == row['label'], 'label', ctx)
            return row

        def sources(obj, depth=0, parent=None):
            for child in members(obj, 'sources'):
                if depth > 2:
                    audit.check(False, 'unsupported_source_depth', child.name)
                    continue
                table = ('animal', 'preparation', 'cell')[depth]
                record(table, child, parent)
                sources(child, depth + 1, (table, value(child.attrs['uuid'])))
        sources(exp)

        def groups(container):
            for group in members(container, 'epochGroups'):
                gu = value(group.attrs['uuid'])
                if gu in expected['epoch_group']:
                    continue  # HDF5 aliases to the same group
                record('epoch_group', group, ('cell', value(group['source'].attrs['uuid'])))
                for block in members(group, 'epochBlocks'):
                    bu = value(block.attrs['uuid'])
                    bp = attrs(block['protocolParameters']) if 'protocolParameters' in block else {}
                    br = record('epoch_block', block, ('epoch_group', gu), bp)
                    if br:
                        audit.check(protocols.get(br['protocol_id']) == value(block.attrs['protocolID']), 'protocol_identity', bu)
                    for ep in members(block, 'epochs'):
                        eu = value(ep.attrs['uuid'])
                        params = dict(bp)
                        params.update(attrs(ep['protocolParameters']) if 'protocolParameters' in ep else {})
                        er = record('epoch', ep, ('epoch_block', bu), params)
                        # Background device configuration also contributes persisted parameters.
                        if er:
                            extra = {}
                            for bg in members(ep, 'backgrounds'):
                                spans = list(members(bg, 'dataConfigurationSpans'))
                                device = bg.name.rsplit('/', 1)[1][:-37]
                                if spans and device in spans[0]:
                                    extra.update(attrs(spans[0][device]))
                            raw_props = attrs(ep['properties']) if 'properties' in ep else {}
                            extra = {k: v for k, v in extra.items() if k not in params and k not in raw_props}
                            audit.metadata(extra, er['parameters'], 'background_parameters', eu)
                        for kind, table in [('responses', 'response'), ('stimuli', 'stimulus')]:
                            for stream in members(ep, kind):
                                sr = record(table, stream, ('epoch', eu))
                                if not sr:
                                    continue
                                su = value(stream.attrs['uuid'])
                                audit.check(sr['device_name'] == value(stream['device'].attrs['name']), 'device', su)
                                locator = sr['h5path']
                                valid = locator in h5 and value(h5[locator].attrs.get('uuid')) == su
                                audit.check(valid, 'stream_locator_uuid', su)
                                if table == 'response':
                                    for column, key in [('sample_rate', 'sampleRate'), ('offset_hours', 'inputTimeDotNetDateTimeOffsetOffsetHours'), ('offset_ticks', 'inputTimeDotNetDateTimeOffsetTicks')]:
                                        # Avoid float precision loss for 64-bit .NET ticks.
                                        wanted = value(stream.attrs[key])
                                        got = int(sr[column]) if isinstance(wanted, int) else float(sr[column])
                                        audit.check(got == wanted, column, su)
                                    audit.check(sr['sample_rate_units'] == value(stream.attrs['sampleRateUnits']), 'sample_rate_units', su)
                                    audit.check('data' in stream and valid and 'data' in h5[locator], 'waveform_locator', su)
                                    samples.append((eu, su, stream.name, sr['device_name']))
                groups(group)
        groups(exp)
        for table in TABLES:
            wanted, actual = set(expected[table]), set(rows[table])
            audit.check(wanted == actual, 'exact_uuid_membership', {'source': path.name, 'table': table, 'missing': sorted(wanted - actual)[:20], 'extra': sorted(actual - wanted)[:20]})
        result['source_counts'] = {t: len(expected[t]) for t in TABLES}
        result['database_counts'] = {t: len(rows[t]) for t in TABLES}
        # Bound actual waveform reads, covering first/middle/last and every device.
        chosen = {i for i in (0, len(samples)//2, len(samples)-1) if 0 <= i < len(samples)}
        seen = set()
        for i, item in enumerate(samples):
            if item[3] not in seen:
                chosen.add(i)
                seen.add(item[3])
        result['waveform_samples'] = []
        for i in sorted(chosen):
            eu, su, locator, device = samples[i]
            dataset = h5[locator + '/data']
            for start in sorted({0, max(0, len(dataset)//2-16), max(0, len(dataset)-32)}):
                raw = dataset[start:start+32]
                values = raw['quantity'].astype(float).tolist()
                units = sorted({value(x) for x in raw['units']}) if 'units' in (raw.dtype.names or ()) else []
                evidence = {'epoch_uuid': eu, 'stream_uuid': su, 'device': device, 'start': start, 'count': len(values), 'units': units, 'values_sha256': hashlib.sha256(json.dumps(values).encode()).hexdigest()}
                if base_url:
                    query = urlencode({'stream_uuid': su, 'start': start, 'count': len(values)})
                    with urlopen(f'{base_url.rstrip("/")}/api/epochs/{eu}/trace?{query}', timeout=60) as response:
                        trace = json.load(response)
                    audit.check(equal(values, trace.get('values')), 'http_waveform_values', evidence)
                    audit.check(trace.get('decimated') is False, 'http_waveform_not_decimated', su)
                    audit.check(trace.get('sample_rate') == value(h5[locator].attrs['sampleRate']), 'http_waveform_rate', su)
                    audit.check(units == [trace.get('units')], 'http_waveform_units', su)
                    audit.check(trace.get('start') == start and trace.get('count') == len(values) and trace.get('total_samples') == len(dataset), 'http_waveform_window', su)
                    audit.check(trace.get('source_sha256') == before, 'http_waveform_source', su)
                    evidence['http_compared'] = True
                result['waveform_samples'].append(evidence)
    audit.check(sha(path) == before, 'source_unchanged', path.name)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--base-url')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = [Path(x['path'] if isinstance(x, dict) else x).resolve(strict=True) for x in json.loads(args.inventory.read_text())]
    for path in paths:
        if path.suffix.lower() != '.h5' or path.name.lower().endswith(('.auisql.h5', '.asqul.h5')):
            parser.error('Only original Symphony .h5 sources are permitted')
    state = json.loads((args.project / 'database/native.json').read_text())
    connection = pymysql.connect(host='127.0.0.1', port=state['port'], user='root', password=state['password'], cursorclass=pymysql.cursors.DictCursor, read_timeout=120)
    audit = Audit()
    receipt = {'status': 'running', 'sources': [], 'limitations': ['Raw waveform arrays remain in original read-only H5 files; SQL stores metadata and locators.', 'Waveform values are sampled at bounded first/middle/last windows, not exhaustively scanned.', 'Derived frame times and protocol-specific stimulus reconstruction are not validated by this audit.']}
    if not args.base_url:
        receipt['limitations'].append('No HTTP endpoint supplied: waveform windows recorded but application trace values not compared.')
    start = time.monotonic()
    try:
        with connection.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
            cur.execute('SELECT * FROM recording_workspace.source')
            sources = cur.fetchall()
        with connection.cursor() as cur:
            cur.execute('SELECT id FROM `schema`.`experiment`')
            experiment_ids = {r['id'] for r in cur.fetchall()}
        audit.check(experiment_ids == {s['experiment_id'] for s in sources}, 'no_unregistered_experiments', {'catalog_count': len(experiment_ids), 'source_count': len(sources)})
        by_sha = {s['source_sha256']: s for s in sources}
        wanted_shas = {sha(p) for p in paths}
        audit.check(set(by_sha) == wanted_shas, 'exact_source_membership', {'expected': len(paths), 'actual': len(sources)})
        for path in paths:
            source = by_sha.get(sha(path))
            audit.check(source is not None, 'source_present', path.name)
            if source:
                receipt['sources'].append(audit_source(path, source, connection, audit, args.base_url))
                print('Audited', path.name, receipt['sources'][-1]['source_counts'], flush=True)
        if len(receipt['sources']) == len(sources):
            with connection.cursor() as cur:
                for table in TABLES:
                    cur.execute(f'SELECT COUNT(*) AS n FROM `schema`.`{table}`')
                    total = cur.fetchone()['n']
                    accounted = sum(item['database_counts'][table] for item in receipt['sources'])
                    audit.check(total == accounted, 'no_orphan_rows', {'table': table, 'total': total, 'accounted': accounted})
        receipt['status'] = 'passed' if audit.failure_count == 0 else 'failed'
    finally:
        connection.rollback()
        connection.close()
        receipt.update(checks=dict(audit.checks), failure_count=audit.failure_count, failure_categories=dict(audit.failure_categories), failures=audit.failures, duration_seconds=round(time.monotonic()-start, 3))
        args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': receipt['status'], 'failure_count': audit.failure_count, 'receipt': str(args.output)}))
    return 0 if receipt['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
