#!/usr/bin/env python3
"""Owned, donor-free H5 generator. Execution requires the parent-reviewed gate.

This module deliberately has no scientific imports until main is invoked.
It never creates a project, catalog, account or database.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import uuid

PARSER_SHA256 = '0d63fa4df6e087cda60fd85305ea3c4a7d287949abab325b9f1dd2e5f12779d2'
PROTOCOL = 'org.disco.synthetic.OrganizationAcceptance'


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def ticks(value):
    delta = value - dt.datetime(1, 1, 1)
    return delta.days * 864000000000 + delta.seconds * 10000000 + delta.microseconds * 10


def specification(namespace):
    namespace = uuid.UUID(namespace)
    ident = lambda key: str(uuid.uuid5(namespace, key))
    origin = dt.datetime(2026, 1, 1)
    root = '/experiment-' + ident('experiment')
    animal = root + '/sources/animal-' + ident('animal')
    prep = animal + '/sources/preparation-' + ident('preparation')
    value = {'format': 'disco-organization-oracle', 'version': 1,
             'namespace': str(namespace), 'experiment_uuid': ident('experiment'),
             'animal_uuid': ident('animal'), 'preparation_uuid': ident('preparation'),
             'root_label': 'Synthetic organization acceptance',
             'root_properties': {key: 'Synthetic ' + key for key in ('experimenter','institution','lab','project','rig')},
             'root_path': root, 'animal_path': animal, 'preparation_path': prep,
             'protocol': PROTOCOL, 'formula': 'global_epoch_ordinal + sample_index / 256',
             'sample_count': 256, 'sample_rate': 10000.0, 'units': 'pA',
             'counts': {'experiments': 1, 'cells': 2, 'epochs': 63, 'responses': 63, 'stimuli': 0},
             'origin_ticks': ticks(origin), 'cells': [], 'epochs': []}
    for cell_index, count in enumerate((61, 2)):
        key = f'cell/{cell_index}'
        group = root + '/epochGroups/group-' + ident(key + '/group')
        block = group + '/epochBlocks/block-' + ident(key + '/block')
        cell = {'uuid': ident(key), 'path': prep + '/sources/cell-' + ident(key),
                'label': 'Synthetic cell ' + ('A' if cell_index == 0 else 'B'),
                'group_uuid': ident(key + '/group'), 'group_path': group,
                'block_uuid': ident(key + '/block'), 'block_path': block, 'epoch_ids': []}
        for local in range(count):
            ordinal = len(value['epochs'])
            epoch_id = ident(f'{key}/epoch/{local}')
            stream_id = ident(f'{key}/epoch/{local}/response')
            epoch_path = block + '/epochs/epoch-' + epoch_id
            start = origin + dt.timedelta(seconds=ordinal)
            value['epochs'].append({'uuid': epoch_id, 'cell_uuid': cell['uuid'],
                'group_uuid': cell['group_uuid'], 'block_uuid': cell['block_uuid'],
                'ordinal': ordinal, 'path': epoch_path, 'stream_uuid': stream_id,
                'stream_path': epoch_path + '/responses/Amp1-' + stream_id,
                'start_ticks': ticks(start), 'end_ticks': ticks(start + dt.timedelta(microseconds=25600)),
                'start_time': start.strftime('%m/%d/%Y %H:%M:%S:%f'),
                'end_time': (start+dt.timedelta(microseconds=25600)).strftime('%m/%d/%Y %H:%M:%S:%f'),
                'parameters': {'sampleRate': 10000.0, 'preTime': 0.0, 'stimTime': 25.6,
                               'tailTime': 0.0, 'fixtureOrdinal': ordinal, 'fixtureOverride': ordinal}})
            cell['epoch_ids'].append(epoch_id)
        value['cells'].append(cell)
    value['selection_ids'] = [row['uuid'] for row in value['epochs'][59:61]]
    value['tag_ids'] = value['cells'][1]['epoch_ids']
    value['windows'] = [{'epoch_uuid': value['epochs'][n]['uuid'], 'start': 17, 'count': 127}
                        for n in (59, 60, 61, 62)]
    return value


def generate(path, oracle, np, h5py):
    def attrs(obj, **values):
        for key, value in values.items():
            obj.attrs[key] = np.bytes_(value) if isinstance(value, str) else value
    def source(h5, name, identity, label, start):
        obj = h5.create_group(name)
        attrs(obj, uuid=identity, label=label, startTimeDotNetDateTimeOffsetTicks=np.int64(start))
        obj.create_group('properties')
        obj.create_group('sources')
        return obj
    with h5py.File(path, 'x') as h5:
        root = source(h5, oracle['root_path'], oracle['experiment_uuid'], oracle['root_label'], oracle['origin_ticks'] - 30000000)
        attrs(root['properties'], **oracle['root_properties'])
        root.create_group('epochGroups')
        animal = source(h5, oracle['animal_path'], oracle['animal_uuid'], 'Synthetic animal', oracle['origin_ticks'] - 20000000)
        animal['experiment'] = root
        source(h5, oracle['preparation_path'], oracle['preparation_uuid'], 'Synthetic preparation', oracle['origin_ticks'] - 10000000)
        for cell in oracle['cells']:
            rows = [r for r in oracle['epochs'] if r['cell_uuid'] == cell['uuid']]
            cell_obj = source(h5, cell['path'], cell['uuid'], cell['label'], rows[0]['start_ticks'])
            group = h5.create_group(cell['group_path'])
            attrs(group, uuid=cell['group_uuid'], label='Synthetic group ' + cell['label'][-1],
                  startTimeDotNetDateTimeOffsetTicks=np.int64(rows[0]['start_ticks']),
                  endTimeDotNetDateTimeOffsetTicks=np.int64(rows[-1]['end_ticks']))
            group.create_group('properties')
            group['source'] = cell_obj
            block = h5.create_group(cell['block_path'])
            attrs(block, uuid=cell['block_uuid'], label='Synthetic block', protocolID=oracle['protocol'],
                  startTimeDotNetDateTimeOffsetTicks=np.int64(rows[0]['start_ticks']),
                  endTimeDotNetDateTimeOffsetTicks=np.int64(rows[-1]['end_ticks']))
            block.create_group('properties')
            params = block.create_group('protocolParameters')
            attrs(params, **({k: v for k, v in rows[0]['parameters'].items() if k not in ('fixtureOrdinal','fixtureOverride')} | {'fixtureOverride':-1}))
            for row in rows:
                epoch = h5.create_group(row['path'])
                attrs(epoch, uuid=row['uuid'], label='Synthetic epoch',
                      startTimeDotNetDateTimeOffsetTicks=np.int64(row['start_ticks']),
                      endTimeDotNetDateTimeOffsetTicks=np.int64(row['end_ticks']))
                for name in ('properties', 'backgrounds', 'stimuli'):
                    epoch.create_group(name)
                attrs(epoch.create_group('protocolParameters'), fixtureOrdinal=row['ordinal'],fixtureOverride=row['ordinal'])
                stream = h5.create_group(row['stream_path'])
                attrs(stream, uuid=row['stream_uuid'], label='Amp1', sampleRate=10000.0,
                      sampleRateUnits='Hz', inputTimeDotNetDateTimeOffsetOffsetHours=0,
                      inputTimeDotNetDateTimeOffsetTicks=np.int64(row['start_ticks']))
                data = np.zeros(256, dtype=[('quantity', '<f8'), ('units', 'S8')])
                data['quantity'] = row['ordinal'] + np.arange(256, dtype=np.float64) / 256
                data['units'] = b'pA'
                stream.create_dataset('data', data=data)


def verify_raw(path, oracle, np, h5py):
    with h5py.File(path, 'r') as h5:
        assert list(h5) == [oracle['root_path'].lstrip('/')]
        root=h5[oracle['root_path']]
        assert root.attrs['uuid'].decode()==oracle['experiment_uuid'] and root.attrs['label'].decode()==oracle['root_label']
        assert {key:value.decode() for key,value in root['properties'].attrs.items()}==oracle['root_properties']
        for row in oracle['epochs']:
            stream = h5[row['stream_path']]
            assert stream.attrs['uuid'].decode() == row['stream_uuid']
            assert float(stream.attrs['sampleRate']) == oracle['sample_rate']
            data = stream['data'][:]
            assert len(data) == oracle['sample_count']
            assert np.array_equal(data['quantity'], row['ordinal'] + np.arange(256) / 256)
            assert all(item == b'pA' for item in data['units'])


def parse_preflight(source, target, parser_file, oracle):
    assert sha(parser_file) == PARSER_SHA256, 'Unreviewed parser bytes'
    spec = importlib.util.spec_from_file_location('organization_reviewed_parser', parser_file)
    module = importlib.util.module_from_spec(spec)
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            spec.loader.exec_module(module)
            with module.Symphony2Reader(str(source), str(target)) as reader:
                reader.read_write(datajoint=True)
    finally:
        (target.parent / 'parser.log').write_text(log.getvalue())
    output = log.getvalue()
    assert not any(token in output.lower() for token in ('warning:', 'error:', 'traceback')), 'Raw parser warning/error'
    raw = json.loads(target.read_text())
    assert raw['rig_type'] == 'PATCH'
    assert raw['uuid'] == oracle['animal_uuid'], 'Expected first-animal raw projection'
    assert len(raw['animals']) == 1 and raw['animals'][0]['uuid'] == oracle['animal_uuid']
    preparations = raw['animals'][0]['preparations']
    assert len(preparations) == 1 and preparations[0]['uuid'] == oracle['preparation_uuid']
    cells = preparations[0]['cells']
    assert {c['uuid'] for c in cells} == {c['uuid'] for c in oracle['cells']}
    expected = {e['uuid']: e for e in oracle['epochs']}
    seen = []
    for cell in cells:
        assert len(cell['epoch_groups']) == 1
        group = cell['epoch_groups'][0]
        assert len(group['epoch_blocks']) == 1
        block = group['epoch_blocks'][0]
        assert block['protocolID'] == oracle['protocol']
        ids = []
        for epoch in block['epochs']:
            row = expected[epoch['uuid']]
            assert row['cell_uuid'] == cell['uuid'] and row['group_uuid'] == group['uuid'] and row['block_uuid'] == block['uuid']
            assert epoch['start_time'] == row['start_time'] and epoch['end_time']==row['end_time'] and epoch['parameters'] == row['parameters']
            assert epoch['stimuli'] == {} and set(epoch['responses']) == {'Amp1'}
            stream = epoch['responses']['Amp1']
            assert stream['uuid'] == row['stream_uuid'] and stream['h5path'] == row['stream_path']
            assert stream['sampleRate'] == 10000 and stream['sampleRateUnits'] == 'Hz'
            ids.append(epoch['uuid'])
        assert ids == next(c['epoch_ids'] for c in oracle['cells'] if c['uuid'] == cell['uuid'])
        seen.extend(ids)
    assert len(seen) == 63 and set(seen) == set(expected)
    return {'status': 'passed', 'parser_sha256': PARSER_SHA256,
            'raw_experiment_projection': 'animal', 'expected_import_warning': {
                'code': 'experiment_identity_restored', 'parser_uuid': oracle['animal_uuid'],
                'source_uuid': oracle['experiment_uuid']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--parser-source', type=Path, required=True)
    args = parser.parse_args()
    destination = args.output_dir.absolute()
    assert destination.parent.resolve(strict=True) == destination.parent, 'Canonical parent required'
    assert not destination.exists() and not destination.is_symlink(), 'Fresh output directory required'
    assert sha(args.parser_source) == PARSER_SHA256
    oracle = specification(args.namespace)
    destination.mkdir(mode=0o700)
    receipt = {'format': 'disco-organization-fixture', 'version': 1, 'status': 'unrun',
               'generator_sha256': sha(__file__), 'namespace': args.namespace}
    try:
        # Expectations exist before any scientific generation or parser execution.
        write_new(destination / 'oracle.json', oracle)
        import numpy as np
        import h5py
        source = destination / 'synthetic.h5'
        generate(source, oracle, np, h5py)
        verify_raw(source, oracle, np, h5py)
        receipt['parser_preflight'] = parse_preflight(source, destination / 'parsed.json', args.parser_source, oracle)
        source.chmod(0o400)
        receipt.update(status='passed', h5_sha256=sha(source), oracle_sha256=sha(destination / 'oracle.json'),
                       python_version=__import__('sys').version, numpy_version=np.__version__, h5py_version=h5py.__version__)
    except BaseException as error:
        receipt.update(status='failed', error_type=type(error).__name__, message=str(error))
        raise
    finally:
        write_new(destination / 'fixture-receipt.json', receipt)


if __name__ == '__main__':
    main()
