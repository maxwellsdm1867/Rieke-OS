#!/usr/bin/env python3
"""Read-only synthetic export oracle. No app imports, SQL server or mutations."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def check(args):
    import numpy as np
    import scipy.io
    import h5py
    oracle = json.loads(args.oracle.read_text())
    assert oracle['format'] == 'disco-organization-oracle' and oracle['version'] == 1
    expected = {e['uuid']: e for e in oracle['epochs']}
    assert len(expected) == 63
    root = args.project_root.resolve(strict=True)
    checked = set()

    def root_check(meta):
        assert meta['uuid']==oracle['experiment_uuid'] and meta['label']==oracle['root_label']
        assert meta['properties']==oracle['root_properties'] and meta['rig_type']=='PATCH'

    def detail_check(detail,row):
        assert detail['parameters']==row['parameters']
        meta=detail['metadata']
        for level in ('cell','group','block'):
            assert meta[level]['uuid']==row[level+'_uuid']
        assert meta['epoch']['uuid']==row['uuid']
        assert meta['epoch']['start_time']==row['start_time'] and meta['epoch']['end_time']==row['end_time']
        assert meta['epoch']['attributes']['startTimeDotNetDateTimeOffsetTicks']==row['start_ticks']
        assert meta['epoch']['attributes']['endTimeDotNetDateTimeOffsetTicks']==row['end_ticks']

    def stream_check(source, pointer, rate, units, row):
        source = Path(source).resolve(strict=True)
        assert source.is_relative_to(root), 'Export H5 pointer escaped owned project'
        assert pointer == row['stream_path'] and float(rate) == oracle['sample_rate'] and units == oracle['units']
        if source not in checked:
            assert digest(source) == args.source_sha256, 'Managed source differs from sealed input'
            checked.add(source)
        with h5py.File(source, 'r') as h5:
            values = h5[pointer + '/data'][:]
            assert len(values) == 256 and np.array_equal(values['quantity'], row['ordinal'] + np.arange(256)/256)
            assert all(item == b'pA' for item in values['units'])

    with sqlite3.connect(args.sqlite.resolve(strict=True).as_uri() + '?mode=ro', uri=True) as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        ids = [r[0] for r in db.execute('SELECT epoch_uuid FROM epochs')]
        assert len(ids) == 63 and set(ids) == set(expected)
        assert db.execute('SELECT source_sha256 FROM sources').fetchall()==[(args.source_sha256,)]
        cells={c['uuid']:c for c in oracle['cells']}
        assert set(db.execute('SELECT cell_uuid,source_sha256,cell_label FROM cells'))=={(c['uuid'],args.source_sha256,c['label']) for c in cells.values()}
        assert set(db.execute('SELECT group_uuid,cell_uuid FROM epoch_groups'))=={(c['group_uuid'],c['uuid']) for c in cells.values()}
        assert set(db.execute('SELECT block_uuid,group_uuid,acquisition_protocol FROM epoch_blocks'))=={(c['block_uuid'],c['group_uuid'],oracle['protocol']) for c in cells.values()}
        epoch_rows=db.execute('SELECT epoch_uuid,block_uuid,source_sha256,start_time,end_time,metadata_json FROM epochs').fetchall()
        for identity,block,source_sha,start,end,metadata_json in epoch_rows:
            row=expected[identity]
            assert block==row['block_uuid'] and source_sha==args.source_sha256
            assert start==row['start_time'] and end==row['end_time']
            detail_check(json.loads(metadata_json),row)
        records = db.execute('SELECT st.epoch_uuid,st.stream_uuid,s.source_path,st.h5_path,st.sample_rate,st.units,st.sample_rate_units,st.sample_count,e.source_sha256 '
                             'FROM streams st JOIN epochs e USING(epoch_uuid) JOIN sources s USING(source_sha256) '
                             "WHERE st.kind='responses'").fetchall()
        assert len(records) == 63
        assert {record[1] for record in records}=={row['stream_uuid'] for row in expected.values()}
        for identity, stream, source, pointer, rate, units, rate_units, sample_count, source_sha in records:
            row = expected[identity]
            assert stream == row['stream_uuid'] and rate_units=='Hz' and sample_count==256 and source_sha==args.source_sha256
            stream_check(source, pointer, rate, units, row)
        assert db.execute("SELECT count(*) FROM streams WHERE kind='stimuli'").fetchone()[0] == 0
        for identity, row in expected.items():
            parameters = {key: json.loads(value) for key,value in db.execute(
                'SELECT field_id,value_json FROM epoch_parameters WHERE epoch_uuid=?', (identity,))}
            for key, value in row['parameters'].items():
                assert parameters['parameters/' + key] == value
        tags = db.execute('SELECT target_uuid,profile_uuid FROM shared_annotations WHERE target_kind=? AND tag=?',
                          ('epoch', args.tag)).fetchall()
        assert len(tags) == 2 and set(tags) == {(identity,args.profile_uuid) for identity in oracle['tag_ids']}

    assert not zipfile.is_zipfile(args.mat), 'Expected plain MAT, not a legacy archive'
    mat = scipy.io.loadmat(args.mat, simplify_cells=True)
    assert json.loads(mat['metadata']['epoch_sequence_json']) == [e['uuid'] for e in oracle['epochs']]
    annotations = json.loads(mat['metadata']['workspace_tags_json'])['entries']
    tagged = [(entry['target_uuid'], tag['profile_uuid']) for entry in annotations
              if entry['target_kind'] == 'epoch' for tag in entry['tags'] if tag['tag'] == args.tag]
    assert len(tagged) == 2 and set(tagged) == {(identity, args.profile_uuid) for identity in oracle['tag_ids']}
    def structs(value):
        values=[value] if isinstance(value,dict) else list(np.asarray(value,dtype=object).reshape(-1))
        assert all(isinstance(item,dict) for item in values), 'Malformed MAT structure list'
        return values
    # Enumerate the actual declared hierarchy before comparing any expected IDs.
    # Unknown and duplicate members must fail, not disappear through an oracle filter.
    experiments=structs(mat['experiments'])
    assert len(experiments)==1
    experiment=experiments[0]
    assert experiment['h5_uuid']==oracle['experiment_uuid'] and experiment['label']==oracle['root_label']
    assert experiment['source_sha256']==args.source_sha256
    root_check(json.loads(experiment['source_metadata_json']))
    observed={kind:[] for kind in ('cells','groups','blocks','epochs','responses')}
    for cell in structs(experiment['cells']):
        cell_id=cell['h5_uuid'];observed['cells'].append(cell_id)
        assert cell_id in cells and cell['label']==cells[cell_id]['label']
        for group in structs(cell['epoch_groups']):
            group_id=group['h5_uuid'];observed['groups'].append(group_id)
            assert group_id==cells[cell_id]['group_uuid']
            for block in structs(group['epoch_blocks']):
                block_id=block['h5_uuid'];observed['blocks'].append(block_id)
                assert block_id==cells[cell_id]['block_uuid'] and block['protocol_id']==oracle['protocol']
                for epoch in structs(block['epochs']):
                    identity=epoch['h5_uuid'];observed['epochs'].append(identity)
                    assert identity in expected, 'Foreign exported MAT epoch'
                    row=expected[identity]
                    assert (cell_id,group_id,block_id)==(row['cell_uuid'],row['group_uuid'],row['block_uuid'])
                    assert epoch['source_sha256']==args.source_sha256
                    assert epoch['start_time']==row['start_time'] and epoch['end_time']==row['end_time']
                    assert Path(epoch['h5_file']).resolve()==Path(experiment['h5_file']).resolve()
                    detail_check(json.loads(epoch['source_metadata_json']),row)
                    assert structs(epoch['stimuli'])==[], 'Unexpected MAT stimuli'
                    responses=structs(epoch['responses']);assert len(responses)==1
                    response=responses[0];observed['responses'].append(response['h5_uuid'])
                    assert response['h5_uuid']==row['stream_uuid']
                    assert response['sample_rate_units']=='Hz' and response['sample_count']==256
                    assert response['source_sha256']==args.source_sha256
                    stream_check(response['h5_file'],response['h5_path'],response['sample_rate'],response['units'],row)
    expected_sets={'cells':set(cells),'groups':{c['group_uuid'] for c in cells.values()},
        'blocks':{c['block_uuid'] for c in cells.values()},'epochs':set(expected),
        'responses':{row['stream_uuid'] for row in expected.values()}}
    for kind,ids in observed.items():
        assert len(ids)==len(expected_sets[kind]) and set(ids)==expected_sets[kind], 'MAT hierarchy membership differs: '+kind
    return {'status':'passed','epochs':63,'all_samples_exact':True,'sqlite_integrity':True,
            'sqlite_group_tag_membership':True,'mat_group_tag_membership':True,
            'mat_plain_file':True,'exported_identity_time_units_count_source_and_parameters_exact':True,
            'complete_mat_hierarchy_exact':True,'zero_stimuli':True,'mat_chronological_sequence_exact':True,
            'managed_sources_checked':len(checked), 'sqlite_sha256':digest(args.sqlite), 'mat_sha256':digest(args.mat)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('oracle','sqlite','mat','project-root','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    for name in ('source-sha256','tag','profile-uuid'):
        parser.add_argument('--'+name,required=True)
    args = parser.parse_args()
    assert not args.output.exists() and not args.output.is_symlink(), 'Refuse receipt overwrite'
    result = {'status':'unrun'}
    try: result = check(args)
    except BaseException as error:
        result = {'status':'failed','error_type':type(error).__name__,'message':str(error)}
        raise
    finally:
        with args.output.open('x') as handle: json.dump(result,handle,indent=2); handle.write('\n')


if __name__ == '__main__':
    main()
