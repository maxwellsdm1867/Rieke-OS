"""Read-only, independent Sep23+Sep24 History export validation.

python verify_sept23_handoffs.py --sqlite FILE --bundle EXTRACTED_DIR --output NEW_DIR
Reads original H5 headers plus bounded sample windows. Writes proof files only
under --output. Emits verify_native.m; MATLAB runs only with explicit --matlab.
No API, DataJoint connection, publication, or research-file modification.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess

import h5py
import numpy as np
from scipy.io import loadmat

from query_workspace_export import ExportReader
from recording_workspace import digest
from workspace_matlab_masks import read_ugm
from workspace_recipes import verify

PROTOCOL = 'edu.washington.riekelab.chris.protocols.VariableHistoryNoiseCurInject'
CELL_COUNTS = {'280a21fa-949b-46aa-92f5-8793a43e0246': 49,
               '61d7f553-d5e3-4cc9-9d21-aba305bdb2f3': 52,
               '4012ffd8-1fc3-4e90-9119-6dbdcc696044': 33,
               '4d032bcd-39e4-4615-b666-e82893be58dd': 39}
SEPT24_CELLS = {'280a21fa-949b-46aa-92f5-8793a43e0246', '61d7f553-d5e3-4cc9-9d21-aba305bdb2f3'}


def text(value):
    return value.decode() if isinstance(value, bytes) else str(value)


def sequence(value):
    return [value] if isinstance(value, dict) else list(value)


def matlab_literal(value):
    value = str(value)
    if any(char in value for char in '\r\n\x00'):
        raise ValueError('Paths must fit one MATLAB source line')
    return "'" + value.replace("'", "''") + "'"


def raw_members(sources):
    """Independent direct hierarchy walk; never use exporter metadata as oracle."""
    result = {}
    for source in sources:
        with h5py.File(source['source_path'], 'r') as h5:
            roots = [value for key, value in h5.items() if key.startswith('experiment-')]
            assert len(roots) == 1
            for group in roots[0]['epochGroups'].values():
                cell = group['source']
                for block in group['epochBlocks'].values():
                    if text(block.attrs['protocolID']) != PROTOCOL:
                        continue
                    for epoch in block['epochs'].values():
                        identity = text(epoch.attrs['uuid'])
                        assert identity not in result, 'Duplicate raw epoch UUID'
                        parameters = dict(block['protocolParameters'].attrs)
                        parameters.update(epoch['protocolParameters'].attrs)
                        responses = list(epoch['responses'].values())
                        assert len(responses) == 1, 'Expected one recorded response per History epoch'
                        response = responses[0]
                        result[identity] = {'epoch_uuid': identity,
                            'cell_uuid': text(cell.attrs['uuid']), 'cell_label': text(cell.attrs['label']),
                            'source_sha256': source['source_sha256'], 'source_path': source['source_path'],
                            'stream_uuid': text(response.attrs['uuid']), 'h5_path': response.name,
                            'sample_rate': float(response.attrs['sampleRate']),
                            'sample_count': len(response['data']), 'control': float(parameters['isControl'])}
    return result


def validate(sqlite_path, bundle, output):
    sqlite_path, bundle, output = map(lambda path: Path(path).resolve(), (sqlite_path, bundle, output))
    output.mkdir(parents=True, exist_ok=False)
    with ExportReader(sqlite_path) as reader:
        db = reader.connection
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        sources = [dict(row) for row in db.execute('SELECT * FROM sources')]
        assert len(sources) == 2
        source_digests = {row['source_path']: digest(row['source_path']) for row in sources}
        assert all(source_digests[row['source_path']] == row['source_sha256'] for row in sources)
        raw = raw_members(sources)
        assert len(raw) == 173
        assert Counter(row['cell_uuid'] for row in raw.values()) == CELL_COUNTS
        assert sorted(Counter(row['source_sha256'] for row in raw.values()).values()) == [72, 101]
        assert Counter(row['control'] for row in raw.values()) == {0: 166, 1: 7}
        assert Counter(row['sample_count'] for row in raw.values()) == {100000: 7, 200000: 165, 400000: 1}
        assert {row['sample_rate'] for row in raw.values()} == {10000}
        assert sum(row['sample_count'] for row in raw.values()) == 34100000
        sql_rows = {row['epoch_uuid']: dict(row) for row in db.execute('SELECT * FROM epoch_overview')}
        assert set(sql_rows) == set(raw)
        assert {row['recording_date'] for row in sql_rows.values()} == {'2026-09-23', '2026-09-24'}
        assert len(list(db.execute("SELECT * FROM streams WHERE kind='responses'"))) == 173
        assert {member['uuid'] for member in reader.recipe['epochs']} == set(raw)
        mat = loadmat(bundle / 'recordings.mat', simplify_cells=True)
        mat_epochs = [epoch for experiment in sequence(mat['experiments'])
                      for cell in sequence(experiment['cells']) for group in sequence(cell['epoch_groups'])
                      for block in sequence(group['epoch_blocks']) for epoch in sequence(block['epochs'])]
        assert len(mat_epochs) == 173
        mat_by_id = {epoch['h5_uuid']: epoch for epoch in mat_epochs}
        assert set(mat_by_id) == set(raw)
        for experiment in sequence(mat['experiments']):
            for cell in sequence(experiment['cells']):
                for group in sequence(cell['epoch_groups']):
                    for block in sequence(group['epoch_blocks']):
                        for epoch in sequence(block['epochs']):
                            assert raw[epoch['h5_uuid']]['cell_uuid'] == cell['h5_uuid']
        mat_recipe = verify(json.loads(mat['metadata']['recipe_json']))
        assert {member['uuid'] for member in mat_recipe['epochs']} == set(raw)
        assert {row['uuid']: row['metadata_hash'] for row in reader.recipe['epochs']} == {
            row['uuid']: row['metadata_hash'] for row in mat_recipe['epochs']}
        assert reader.recipe['protocol_uuid'] == mat_recipe['protocol_uuid']
        assert reader.recipe['query'] == mat_recipe['query']
        mask = read_ugm(bundle / 'selection.ugm', expected_epoch_uuids=list(raw))
        assert all(mask['mask']) and len(mask['mask']) == 173
        for identity, row in raw.items():
            assert sql_rows[identity]['cell_uuid'] == row['cell_uuid']
            assert sql_rows[identity]['source_sha256'] == row['source_sha256']
            expected_date = '2026-09-24' if row['cell_uuid'] in SEPT24_CELLS else '2026-09-23'
            assert sql_rows[identity]['recording_date'] == expected_date
            response = sequence(mat_by_id[identity]['responses'])
            assert len(response) == 1
            response = response[0]
            sql_stream = dict(db.execute("SELECT * FROM streams WHERE epoch_uuid=? AND kind='responses'", (identity,)).fetchone())
            assert sql_stream['stream_uuid'] == row['stream_uuid']
            assert sql_stream['sample_count'] == row['sample_count']
            assert sql_stream['sample_rate'] == row['sample_rate']
            assert sql_stream['units'] == 'mV'
            # Symphony exposes hard-link aliases. Compare export pointer strings
            # to each other, and their target UUIDs to the independent raw walk.
            with h5py.File(row['source_path'], 'r') as h5:
                target = h5[sql_stream['h5_path']]
                assert text(target.attrs['uuid']) == row['stream_uuid']
                assert text(target.parent.parent.attrs['uuid']) == identity
            for key, expected in [('h5_uuid', row['stream_uuid']), ('h5_path', sql_stream['h5_path']),
                                  ('source_sha256', row['source_sha256']), ('h5_file', row['source_path']),
                                  ('sample_rate', row['sample_rate'])]:
                assert response[key] == expected, (identity, key)
            assert np.size(response['data']) == 0, 'MAT export unexpectedly contains waveform arrays'
        chosen = {}
        for source in sources:
            candidates = [row for row in raw.values() if row['source_sha256'] == source['source_sha256']]
            for control in (0, 1):
                selected = sorted((row for row in candidates if row['control'] == control), key=lambda row: row['epoch_uuid'])[0]
                chosen[selected['epoch_uuid']] = selected
        longest = max(raw.values(), key=lambda row: row['sample_count'])
        chosen[longest['epoch_uuid']] = longest
        traces = []
        for row in chosen.values():
            windows = []
            with h5py.File(row['source_path'], 'r') as h5:
                dataset = h5[row['h5_path'] + '/data']
                for start in (0, row['sample_count'] // 2, row['sample_count'] - 31):
                    values = dataset[start:start + 31]
                    expected = values['quantity'].astype(float)
                    actual = reader.read_trace(row['epoch_uuid'], row['stream_uuid'], start=start, count=31)
                    assert np.array_equal(actual['values'], expected)
                    assert actual['units'] == text(values['units'][0]) == 'mV'
                    assert actual['sample_rate'] == row['sample_rate']
                    assert actual['source_sha256'] == row['source_sha256']
                    windows.append({'start': start, 'values': expected.tolist()})
            traces.append({**row, 'windows': windows})
        proof = {'status': 'python_passed_native_pending', 'sqlite_path': str(sqlite_path),
                 'sqlite_sha256': digest(sqlite_path), 'mat_path': str(bundle / 'recordings.mat'),
                 'mat_sha256': digest(bundle / 'recordings.mat'), 'epoch_count': 173,
                 'cell_counts': CELL_COUNTS, 'source_counts': dict(Counter(row['source_sha256'] for row in raw.values())),
                 'sample_distribution': dict(Counter(row['sample_count'] for row in raw.values())),
                 'total_response_samples': 34100000, 'epoch_uuids': sorted(raw), 'traces': traces,
                 'sqlite_export_uuid': reader.recipe['export_uuid'], 'mat_export_uuid': mat_recipe['export_uuid'],
                 'source_signatures': {row['source_path']: list(Path(row['source_path']).stat()[6:9]) for row in sources}}
    proof_path = output / 'handoff-proof.json'
    proof_path.write_text(json.dumps(proof, indent=2))
    repo = Path(__file__).resolve().parents[1]
    native = f"""% Disposable verification; original bundle/source files remain unchanged.
addpath(genpath({matlab_literal(repo)}));
addpath({matlab_literal(bundle)}, '-begin');
proof=jsondecode(fileread({matlab_literal(proof_path)}));
[tree,~]=launchWorkspaceTree(proof.mat_path, 'ShowGUI', false);
ids=cellfun(@(epoch) epoch.h5_uuid,tree.allEpochs,'UniformOutput',false);
assert(numel(ids)==173 && isequal(sort(ids(:)),sort(proof.epoch_uuids(:))));
assert(all(cellfun(@(epoch) epoch.isSelected,tree.allEpochs)));
for ti=1:numel(proof.traces)
    expected=proof.traces(ti);
    index=find(strcmp(ids,expected.epoch_uuid));assert(isscalar(index));
    epoch=tree.allEpochs{{index}};
    response=epicTreeTools.getResponseByName(epoch,'Amp1');
    assert(strcmp(response.h5_uuid,expected.stream_uuid));
    assert(strcmp(response.source_sha256,expected.source_sha256));
    [values,rate]=epicTreeTools.getResponseFromEpoch(epoch,'Amp1');
    assert(numel(values)==expected.sample_count && rate==expected.sample_rate);
    for wi=1:numel(expected.windows)
        window=expected.windows(wi); indices=window.start+(1:numel(window.values));
        assert(isequal(double(values(indices(:))),double(reshape(window.values,size(values(indices(:)))))));
    end
end
% Save/reload a disposable mixed mask and check UUID decisions after sequencing.
chosen=sort(ids);excluded=chosen{{1}};
for ei=1:numel(ids),tree.allEpochs{{ei}}.isSelected=~strcmp(ids{{ei}},excluded);end
tree.propagateSelectionToLeaves();tree.refreshNodeSelectionState();
maskFile={matlab_literal(output / 'native-returned.ugm')};tree.saveUserMetadata(maskFile);
[data,~]=loadEpicTreeData(proof.mat_path);roundtrip=epicTreeTools(data,'LoadUserMetadata','none');
assert(roundtrip.loadUserMetadata(maskFile));
for ei=1:numel(roundtrip.allEpochs)
    epoch=roundtrip.allEpochs{{ei}};assert(epoch.isSelected==~strcmp(epoch.h5_uuid,excluded));
end
nativeProof=struct('status','passed','trace_cases',numel(proof.traces),'epochs',173, ...
 'both_sources_verified',true,'control_and_long_trace_verified',true,'mixed_mask_uuid_roundtrip',true);
handle=fopen({matlab_literal(output / 'native-proof.json')},'w');fprintf(handle,'%s\\n',jsonencode(nativeProof));fclose(handle);
disp('SEPT23_HANDOFF_NATIVE_PASS');
"""
    (output / 'verify_native.m').write_text(native)
    return proof_path, output / 'verify_native.m'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite', required=True)
    parser.add_argument('--bundle', required=True, help='Already extracted MATLAB export directory')
    parser.add_argument('--output', required=True, help='New disposable evidence directory')
    parser.add_argument('--matlab', help='Explicit MATLAB executable; otherwise only prepare native script')
    args = parser.parse_args()
    proof, native = validate(args.sqlite, args.bundle, args.output)
    print(f'Python checks passed: {proof}\nNative validation script: {native}', flush=True)
    if args.matlab:
        subprocess.run([args.matlab, '-batch', f'run({matlab_literal(native)})'], check=True)


if __name__ == '__main__':
    main()
