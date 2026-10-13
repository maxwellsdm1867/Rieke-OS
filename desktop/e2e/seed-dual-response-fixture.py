"""Derive a two-response H5 solely from the owned donor-free fixture."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import uuid

import h5py
import numpy as np

folder, parser = map(lambda value: Path(value).resolve(strict=True), sys.argv[1:])
assert folder.name == 'synthetic' and folder.parent.name == 'home'
assert folder.parent.parent.name.startswith('disco-retention-native-')
base = folder / 'synthetic.h5'
receipt = json.loads((folder / 'fixture-receipt.json').read_text())
sha = lambda file: hashlib.sha256(Path(file).read_bytes()).hexdigest()
assert receipt['status'] == 'passed' and sha(base) == receipt['h5_sha256']
assert sha(parser) == receipt['parser_preflight']['parser_sha256']
oracle = json.loads((folder / 'oracle.json').read_text())
assert oracle['counts']['epochs'] == 63 and len(oracle['epochs']) == 63
output = folder / 'synthetic-dual.h5'
assert not output.exists()
shutil.copyfile(base, output)
output.chmod(0o600)
with h5py.File(output, 'r+') as h5:
    for row in oracle['epochs']:
        identity = str(uuid.uuid5(uuid.UUID(oracle['namespace']), row['uuid'] + '/response/Amp2'))
        target = row['path'] + '/responses/Amp2-' + identity
        h5.copy(row['stream_path'], target)
        stream = h5[target]
        stream.attrs['uuid'] = np.bytes_(identity)
        stream.attrs['label'] = np.bytes_('Amp2')
        values = stream['data'][:]
        values['quantity'] = 1000 + row['ordinal'] + np.arange(256) / 128
        stream['data'][:] = values
        row['amp2'] = {'stream_uuid': identity, 'stream_path': target,
                       'offset': 1000 + row['ordinal'], 'sample_coefficient': 1 / 128,
                       'sample_rate': 10000, 'units': 'pA'}
with h5py.File(output, 'r') as h5:
    for row in oracle['epochs']:
        assert len(h5[row['path'] + '/responses']) == 2
        for name, ident, target, offset, coefficient in (
            ('Amp1', row['stream_uuid'], row['stream_path'], row['ordinal'], 1 / 256),
            ('Amp2', row['amp2']['stream_uuid'], row['amp2']['stream_path'], row['amp2']['offset'], 1 / 128),
        ):
            stream = h5[target]
            assert stream.attrs['uuid'].decode() == ident and stream.attrs['label'].decode() == name
            assert float(stream.attrs['sampleRate']) == 10000
            values = stream['data'][:]
            assert np.array_equal(values['quantity'], offset + np.arange(256) * coefficient)
            assert all(value == b'pA' for value in values['units'])
module_spec = importlib.util.spec_from_file_location('owned_dual_parser', parser)
module = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(module)
parsed = folder / 'parsed-dual.json'
with module.Symphony2Reader(str(output), str(parsed)) as reader:
    reader.read_write(datajoint=True)
raw = json.loads(parsed.read_text())
rows = [epoch for animal in raw['animals'] for prep in animal['preparations']
        for cell in prep['cells'] for group in cell['epoch_groups']
        for block in group['epoch_blocks'] for epoch in block['epochs']]
expected = {row['uuid']: row for row in oracle['epochs']}
assert len(rows) == 63 and {row['uuid'] for row in rows} == set(expected)
for row in rows:
    expected_row = expected[row['uuid']]
    assert set(row['responses']) == {'Amp1', 'Amp2'}
    for name, identity, target in [('Amp1', expected_row['stream_uuid'], expected_row['stream_path']),
                                   ('Amp2', expected_row['amp2']['stream_uuid'], expected_row['amp2']['stream_path'])]:
        stream = row['responses'][name]
        assert stream['uuid'] == identity and stream['h5path'] == target
        assert stream['sampleRate'] == 10000 and stream['sampleRateUnits'] == 'Hz'
assert sha(base) == receipt['h5_sha256'], 'Original donor-free fixture changed'
oracle['counts']['responses'] = 126
oracle_path = folder / 'dual-oracle.json'
oracle_path.write_text(json.dumps(oracle, indent=2) + '\n')
output.chmod(0o400)
result = {'status': 'passed', 'format': 'disco-owned-dual-response-fixture-v1',
          'base_h5_sha256': receipt['h5_sha256'], 'h5_sha256': sha(output),
          'oracle_sha256': sha(oracle_path), 'generator_sha256': sha(__file__),
          'parser_sha256': sha(parser), 'parser_preflight': {'status': 'passed'},
          'epochs': 63, 'cells': 2, 'responses': 126, 'samples_per_response': 256}
(folder / 'dual-fixture-receipt.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
