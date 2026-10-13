"""Derive a two-response H5 solely from the owned donor-free fixture."""
import contextlib
import copy
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import uuid

import h5py
import numpy as np

folder = Path(sys.argv[1]).absolute()
parser = Path(sys.argv[2]).resolve(strict=True)
assert folder.name == 'synthetic' and folder.parent.name == 'home'
assert folder.parent.parent.name.startswith('disco-retention-native-')
assert folder.parent.resolve(strict=True) == folder.parent
assert not folder.exists() and not folder.is_symlink()
folder.mkdir(mode=0o700)
sha = lambda file: hashlib.sha256(Path(file).read_bytes()).hexdigest()
common_path = Path(__file__).resolve().parents[2] / 'tools/organization_e2e_fixture.py'
common_spec = importlib.util.spec_from_file_location('owned_common_fixture', common_path)
common = importlib.util.module_from_spec(common_spec)
common_spec.loader.exec_module(common)
assert sha(parser) == common.PARSER_SHA256
oracle = common.specification(str(uuid.uuid4()))
common.write_new(folder / 'oracle.json', oracle)
base = folder / 'synthetic.h5'
common.generate(base, oracle, np, h5py)
# PATCH parser records this metadata string but does not open a .bin file.
# Keep the reviewed generator unchanged; finish the derived fixture metadata
# before running its unchanged strict raw and parser preflight oracles.
block_metadata = []
with h5py.File(base, 'r+') as h5:
    for index, cell in enumerate(oracle['cells']):
        value = 'synthetic\\embedded-' + str(index) + '.bin'
        h5[cell['block_path'] + '/properties'].attrs['dataFileName'] = np.bytes_(value)
        block_metadata.append({'block_uuid': cell['block_uuid'], 'dataFileName': value})
common.verify_raw(base, oracle, np, h5py)
def declared_parser_projection(canonical, recording):
    projected = copy.deepcopy(canonical)
    root = canonical['root_path']
    def alias(target):
        assert target.startswith(root + '/')
        return canonical['animal_path'] + '/experiment' + target[len(root):]
    with h5py.File(recording, 'r') as h5:
        for row in projected['epochs']:
            targets = [row] + ([row['amp2']] if 'amp2' in row else [])
            for target in targets:
                original = target['stream_path']
                expected_alias = alias(original)
                assert h5[original].id == h5[expected_alias].id
                assert h5[original + '/data'].id == h5[expected_alias + '/data'].id
                target['stream_path'] = expected_alias
    return projected
base_parser_oracle = declared_parser_projection(oracle, base)
common.write_new(folder / 'parser-oracle.json', base_parser_oracle)
preflight = common.parse_preflight(base, folder / 'parsed.json', parser, base_parser_oracle)
receipt = {'status': 'passed', 'format': 'disco-owned-completed-base-fixture-v1',
           'h5_sha256': sha(base), 'oracle_sha256': sha(folder / 'oracle.json'),
           'parser_preflight': preflight, 'common_generator_sha256': sha(common_path),
           'parser_oracle_sha256': sha(folder / 'parser-oracle.json'),
           'alias_identity': 'Every stream group and data dataset has identical H5 object ID at canonical and predeclared animal/experiment alias.',
           'block_metadata': block_metadata, 'external_binary_reads': False}
common.write_new(folder / 'fixture-receipt.json', receipt)
base.chmod(0o400)
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
oracle['counts']['responses'] = 126
oracle_path = folder / 'dual-oracle.json'
common.write_new(oracle_path, oracle)
parser_oracle = declared_parser_projection(oracle, output)
parser_oracle_path = folder / 'dual-parser-oracle.json'
common.write_new(parser_oracle_path, parser_oracle)
module_spec = importlib.util.spec_from_file_location('owned_dual_parser', parser)
module = importlib.util.module_from_spec(module_spec)
parsed = folder / 'parsed-dual.json'
log = io.StringIO()
try:
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        module_spec.loader.exec_module(module)
        with module.Symphony2Reader(str(output), str(parsed)) as reader:
            reader.read_write(datajoint=True)
finally:
    (folder / 'parser-dual.log').write_text(log.getvalue())
assert not any(token in log.getvalue().lower() for token in ('warning:', 'error:', 'traceback')), 'Dual parser warning/error'
raw = json.loads(parsed.read_text())
rows = [epoch for animal in raw['animals'] for prep in animal['preparations']
        for cell in prep['cells'] for group in cell['epoch_groups']
        for block in group['epoch_blocks'] for epoch in block['epochs']]
expected = {row['uuid']: row for row in parser_oracle['epochs']}
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
output.chmod(0o400)
result = {'status': 'passed', 'format': 'disco-owned-dual-response-fixture-v1',
          'base_h5_sha256': receipt['h5_sha256'], 'h5_sha256': sha(output),
          'oracle_sha256': sha(oracle_path), 'parser_oracle_sha256': sha(parser_oracle_path),
          'base_oracle_sha256': receipt['oracle_sha256'], 'base_parser_oracle_sha256': receipt['parser_oracle_sha256'],
          'alias_identity': receipt['alias_identity'], 'generator_sha256': sha(__file__),
          'parser_sha256': sha(parser), 'parser_preflight': {'status': 'passed'},
          'epochs': 63, 'cells': 2, 'responses': 126, 'samples_per_response': 256,
          'base_common_generator_sha256': receipt['common_generator_sha256'],
          'completed_base_block_metadata': block_metadata, 'external_binary_reads': False}
(folder / 'dual-fixture-receipt.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
