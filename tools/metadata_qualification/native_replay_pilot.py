"""Bounded APFS clone pilot; native H5/RetinAnalysis validation, no SQL writes.

This creates a NEW sealed native-source replay. Experimental SQLite source
hashes are never treated as native authority. Keep receipts and inputs private.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
NAMESPACE = uuid.UUID('d2c5d5ce-6736-4d52-a6ba-033693103d12')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def transform(value, mapping):
    """Independent immutable metadata oracle: only declared UUID values change."""
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [transform(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: transform(item, mapping) for key, item in value.items()}
    return value


def run(source, document, destination, repository, replica, floor_bytes):
    import h5py
    import numpy as np
    from recording_workspace import prepare, validate_source_identity, load_parser
    destination = destination.resolve()
    if not destination.is_relative_to(Path('/tmp').resolve()):
        raise ValueError('Replay pilot output must be below /tmp')
    destination.mkdir(parents=True, exist_ok=False)
    source_signature = source.stat()
    before_sha = sha(source)
    truth = json.loads(document.read_bytes())
    # Historical parser caches omitted physical empty acquisition blocks. Read
    # those original objects through the pinned native parser, before replay.
    # No optimized projection/query/catalog implementation supplies the oracle.
    parser, _ = load_parser(repository)
    groups = {group['uuid']: group for animal in truth['animals']
              for prep in animal['preparations'] for cell in prep['cells']
              for group in cell['epoch_groups']}
    restored_empty = 0
    with h5py.File(source, 'r') as original:
        root = original[next(name for name in original if name.startswith('experiment-'))]
        for group in root.get('epochGroups', {}).values():
            owner = groups[group.attrs['uuid'].decode('UTF-8')]
            known = {block['uuid'] for block in owner['epoch_blocks']}
            for block in group.get('epochBlocks', {}).values():
                identity = block.attrs['uuid'].decode('UTF-8')
                if identity in known:
                    continue
                if len(block.get('epochs', {})):
                    raise AssertionError('Immutable source oracle omitted a populated block')
                datum = json.loads(json.dumps(parser.EpochBlockObj(block).__dict__, cls=parser.NpEncoder))
                if datum['uuid'] != identity or datum['epochs']:
                    raise AssertionError('Independent original empty block identity changed')
                owner['epoch_blocks'].append(datum)
                restored_empty += 1
    free_before = shutil.disk_usage(destination).free
    if free_before < floor_bytes + source.stat().st_size:
        raise ValueError('Insufficient conservative space for bounded pilot')
    target = destination / source.name
    # No full-copy fallback: APFS clone availability is part of this gate.
    subprocess.run(['/bin/cp', '-c', str(source), str(target)], check=True, timeout=30)
    free_after_clone = shutil.disk_usage(destination).free
    mapping = {}
    with h5py.File(target, 'r+') as h5:
        objects = []
        def capture(name, obj):
            if 'uuid' in obj.attrs:
                old = obj.attrs['uuid']
                old = old.decode() if isinstance(old, bytes) else str(old)
                mapped = str(uuid.uuid5(NAMESPACE, f'{replica}/{old}'))
                mapping[old] = mapped
                objects.append((name, mapped))
        h5.visititems(capture)
        for name, mapped in objects:
            obj = h5[name]
            # Some Symphony fixed-width strings reserve their final byte for a
            # terminator. modify() silently truncates a 36-byte replacement.
            # The pinned parser also requires bytes (not variable UTF-8 text).
            # Recreate with NumPy's explicit fixed-width, NULLPAD representation.
            del obj.attrs['uuid']
            obj.attrs.create('uuid', np.bytes_(mapped), dtype='S36')
            if obj.attrs['uuid'].decode('UTF-8') != mapped:
                raise AssertionError('Replayed UUID was truncated in H5 storage')
        expected = transform(truth, mapping)
        inventory = validate_source_identity(h5, expected)
    free_after_identity_remap = shutil.disk_usage(destination).free
    experiment, rows, manifest, folder = prepare(target, destination, repository)
    expected_bytes = json.dumps(expected, sort_keys=True, separators=(',', ':'), allow_nan=False)
    observed_bytes = json.dumps(experiment, sort_keys=True, separators=(',', ':'), allow_nan=False)
    full_metadata_equal = expected_bytes == observed_bytes
    # Every stream is structurally checked by prepare. Independently compare
    # actual retained samples at first/middle/last epoch of this real recording.
    windows = []
    with h5py.File(source, 'r') as old, h5py.File(target, 'r') as new:
        for row in [rows[0], rows[len(rows)//2], rows[-1]]:
            for stream in row['streams']:
                if stream['kind'] != 'responses':
                    continue
                path = stream['h5_path'].rstrip('/') + '/data'
                a, b = old[path], new[path]
                starts = sorted({0, max(0, len(a)//2-16), max(0, len(a)-32)})
                for start in starts:
                    left, right = a[start:start+32], b[start:start+32]
                    if left.dtype != right.dtype or left.shape != right.shape or left.tobytes() != right.tobytes():
                        raise AssertionError('Native retained waveform bytes changed')
                    windows.append({'samples': len(left), 'equal': True})
    after = source.stat()
    signature_unchanged = all(getattr(source_signature, key) == getattr(after, key)
                              for key in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))
    source_unchanged = signature_unchanged and before_sha == sha(source)
    free_after = shutil.disk_usage(destination).free
    allocated = sum(p.stat().st_blocks*512 for p in destination.rglob('*') if p.is_file())
    result = dict(status='pilot_passed' if full_metadata_equal and source_unchanged else 'pilot_failed',
                  replica=replica,epochs=len(rows),native_identity_counts={k:len(v) for k,v in inventory.items()},
                  full_metadata_equal=full_metadata_equal,source_unchanged=source_unchanged,
                  original_physical_empty_blocks_restored=restored_empty,
                  retained_waveform_windows=windows,new_source_sha256=manifest['source_sha256'],
                  immutable_source_sha256=before_sha,clone_logical_bytes=target.stat().st_size,
                  directory_reported_allocated_bytes=allocated,free_bytes_before=free_before,
                  free_bytes_after_clone=free_after_clone,free_bytes_after_identity_remap=free_after_identity_remap,
                  free_bytes_after=free_after,volume_free_delta_bytes=free_before-free_after,
                  metadata_outputs_bytes=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()),
                  disk_floor_bytes=floor_bytes,sql_writes=False,
                  million_status='not_constructed_or_qualified',
                  storage_limit='Volume delta includes background filesystem activity; st_blocks may count shared extents more than once')
    if not full_metadata_equal:
        (destination/'expected-metadata.private.json').write_text(expected_bytes)
        (destination/'observed-metadata.private.json').write_text(observed_bytes)
    (destination/'pilot.private.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser()
    for field in ('source','document','destination','repository'):
        parser.add_argument('--'+field,required=True,type=Path)
    parser.add_argument('--replica',type=int,default=1)
    parser.add_argument('--cap-seconds',type=int,default=180)
    parser.add_argument('--disk-floor-gib',type=int,default=4)
    args=parser.parse_args()
    os.environ.setdefault('MPLCONFIGDIR', str(args.destination.parent / 'matplotlib-cache'))
    os.environ.setdefault('XDG_CACHE_HOME', str(args.destination.parent / 'xdg-cache'))
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('Native pilot time cap')))
    signal.alarm(args.cap_seconds)
    start=time.perf_counter()
    try:
        result=run(args.source,args.document,args.destination,args.repository,args.replica,args.disk_floor_gib*1024**3)
        result['setup_seconds']=time.perf_counter()-start
        print(json.dumps(result))
        if result['status']!='pilot_passed':raise SystemExit(1)
    finally:signal.alarm(0)


if __name__=='__main__':main()
