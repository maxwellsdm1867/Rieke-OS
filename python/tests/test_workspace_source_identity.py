"""Physical H5 identity and dependency closure, using only disposable recordings."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid

import h5py
import numpy as np

import recording_workspace as workspace
from workspace_service import WorkspaceService, read_response_window


def uid(number):
    return str(uuid.UUID(int=number))


def fixture(path, *, soft=False):
    """Two identically labelled cells, with one streamless epoch and empty block."""
    doc = {'uuid': uid(1), 'rig_type': 'PATCH', 'animals': []}
    with h5py.File(path, 'w') as h5:
        root = h5.create_group('experiment-' + uid(1))
        root.attrs.update(uuid=uid(1).encode(), label=b'Experiment')
        root.create_group('properties')
        animal = root.create_group('sources/animal-' + uid(2))
        animal.attrs['uuid'] = uid(2)
        animal['experiment'] = h5py.SoftLink(root.name) if soft else root
        prep = animal.create_group('sources/preparation-' + uid(3))
        prep.attrs['uuid'] = uid(3)
        parsed_prep = {'uuid': uid(3), 'cells': []}
        doc['animals'] = [{'uuid': uid(2), 'preparations': [parsed_prep]}]
        for index in (0, 1):
            offset = 10 + index * 10
            cell = prep.create_group('sources/cell-' + uid(offset))
            cell.attrs['uuid'] = uid(offset)
            group = root.create_group('epochGroups/group-' + uid(offset+1))
            group.attrs['uuid'] = uid(offset+1)
            group['source'] = h5py.SoftLink(cell.name) if soft else cell
            block = group.create_group('epochBlocks/block-' + uid(offset+2))
            block.attrs.update(uuid=uid(offset+2), protocolID='example.Protocol')
            block.create_group('protocolParameters')
            epoch = block.create_group('epochs/epoch-' + uid(offset+3))
            epoch.attrs['uuid'] = uid(offset+3)
            epoch.create_group('protocolParameters')
            parsed_epoch = {'uuid': uid(offset+3), 'start_time': '09/29/2026 12:00:00:000000',
                            'parameters': {}, 'properties': {}, 'attributes': {}, 'responses': {}, 'stimuli': {}}
            if not index:
                stream = epoch.create_group('responses/Amp1-' + uid(offset+4))
                stream.attrs.update(uuid=uid(offset+4), sampleRate=10000.)
                data = np.zeros(4, dtype=[('quantity', 'f8'), ('units', 'S8')])
                data['quantity'], data['units'] = np.arange(4), b'pA'
                stream.create_dataset('data', data=data)
                parsed_epoch['responses']['Amp1'] = {'uuid': uid(offset+4), 'h5path': stream.name,
                                                      'sampleRate': 10000., 'sampleRateUnits': 'Hz'}
            parsed_group = {'uuid': uid(offset+1), 'epoch_blocks': [
                {'uuid': uid(offset+2), 'protocolID': 'example.Protocol', 'epochs': [parsed_epoch]}]}
            parsed_prep['cells'].append({'uuid': uid(offset), 'label': 'Same label',
                'start_time': '09/29/2026 11:00:00:000000', 'epoch_groups': [parsed_group]})
        # The pinned parser intentionally omits empty blocks. They still need duplicate checks.
        empty = group.create_group('epochBlocks/empty-' + uid(30))
        empty.attrs.update(uuid=uid(30), protocolID='example.Protocol')
        empty.create_group('epochs')
    return doc


class SourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'source.h5'
        self.doc = fixture(self.path)

    def validate(self):
        with h5py.File(self.path, 'r') as h5:
            workspace.validate_source_identity(h5, self.doc)

    def cells(self):
        return self.doc['animals'][0]['preparations'][0]['cells']

    def test_control_distinct_cells_same_label_and_streamless_epoch(self):
        self.validate()
        self.doc = fixture(self.path, soft=True)
        self.validate()

    def test_wrong_group_owner_among_real_cells(self):
        cells = self.cells()
        cells[0]['epoch_groups'], cells[1]['epoch_groups'] = cells[1]['epoch_groups'], cells[0]['epoch_groups']
        with self.assertRaisesRegex(ValueError, 'group.*source cell|cell.*ownership'):
            self.validate()

    def test_wrong_preparation_ownership(self):
        self.doc['animals'][0]['preparations'][0]['uuid'] = uid(900)
        with self.assertRaisesRegex(ValueError, 'preparation.*(identity|membership|source)'):
            self.validate()

    def test_duplicate_raw_streamless_epoch_is_not_collapsed(self):
        with h5py.File(self.path, 'r+') as h5:
            group = h5['/experiment-' + uid(1) + '/epochGroups/group-' + uid(21) + '/epochBlocks/block-' + uid(22) + '/epochs']
            group.create_group('omitted').attrs['uuid'] = uid(23)
        with self.assertRaisesRegex(ValueError, 'Duplicate.*epoch.*UUID'):
            self.validate()

    def test_empty_block_duplicate_uuid_rejected(self):
        with h5py.File(self.path, 'r+') as h5:
            h5['/experiment-' + uid(1) + '/epochGroups/group-' + uid(21) + '/epochBlocks/empty-' + uid(30)].attrs['uuid'] = uid(12)
        with self.assertRaisesRegex(ValueError, 'Duplicate.*block.*UUID'):
            self.validate()

    def test_stream_membership_kind_and_device(self):
        for mutation in ('omit', 'kind', 'device'):
            with self.subTest(mutation=mutation):
                self.doc = fixture(self.path)
                epoch = self.cells()[0]['epoch_groups'][0]['epoch_blocks'][0]['epochs'][0]
                stream = epoch['responses'].pop('Amp1')
                if mutation == 'kind':
                    epoch['stimuli']['Amp1'] = stream
                if mutation == 'device':
                    epoch['responses']['Amp2'] = stream
                with self.assertRaisesRegex(ValueError, 'stream.*(membership|identity|device|kind)'):
                    self.validate()

    def test_read_model_independently_rejects_wrong_ownership(self):
        self.cells()[0]['epoch_groups'][0]['uuid'] = uid(900)
        stat = self.path.stat()
        signature = (str(self.path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        source = {'source_sha256': workspace.digest(self.path), 'manifest': {
            'counts': {'cells': 2, 'epochs': 2}, 'validated_at': '2026-09-29'}}
        with self.assertRaisesRegex(ValueError, 'group.*(identity|membership|source)'):
            WorkspaceService.__new__(WorkspaceService)._read_source_metadata(source, self.doc, self.path, signature)

    def signature(self):
        stat = self.path.stat()
        return (str(self.path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    def trace(self):
        epoch = next(workspace.epochs(self.doc))[3]
        stream = epoch['responses']['Amp1']
        return read_response_window(self.path, self.signature(),
            {'epoch_uuid': epoch['uuid'], 'source_sha256': workspace.digest(self.path)},
            {'uuid': stream['uuid'], 'h5_path': stream['h5path'], 'sample_rate': 10000.,
             'sample_count': 4, 'units': 'pA'}, count=4)

    def test_trace_rejects_external_links_in_any_path_component(self):
        for placement in ('data', 'stream', 'epoch', 'soft_chain'):
            with self.subTest(placement=placement):
                self.doc = fixture(self.path)
                stream_path = next(workspace.epochs(self.doc))[3]['responses']['Amp1']['h5path']
                with h5py.File(self.path, 'r+') as h5:
                    if placement == 'data':
                        target = stream_path + '/data'
                    elif placement == 'epoch':
                        target = stream_path.rsplit('/', 2)[0]
                    elif placement == 'soft_chain':
                        h5['unsealed'] = h5py.ExternalLink('missing.h5', '/samples')
                        target = stream_path + '/data'
                    else:
                        target = stream_path
                    del h5[target]
                    h5[target] = (h5py.SoftLink('/unsealed') if placement == 'soft_chain'
                                  else h5py.ExternalLink('missing.h5', '/samples'))
                with self.assertRaisesRegex(ValueError, 'External H5 links are unsupported'):
                    self.trace()

    def test_trace_rejects_virtual_and_external_storage(self):
        for virtual in (True, False):
            with self.subTest(virtual=virtual):
                self.doc = fixture(self.path)
                stream_path = next(workspace.epochs(self.doc))[3]['responses']['Amp1']['h5path']
                with h5py.File(self.path, 'r+') as h5:
                    group = h5[stream_path]
                    del group['data']
                    if virtual:
                        layout = h5py.VirtualLayout((4,), dtype='f8')
                        layout[:] = h5py.VirtualSource('missing.h5', 'values', shape=(4,))
                        group.create_virtual_dataset('data', layout)
                    else:
                        group.create_dataset('data', (4,), dtype='f8', external=[('missing.raw', 0, 32)])
                with self.assertRaisesRegex(ValueError, '(External|Virtual).*unsupported'):
                    self.trace()

    def test_trace_allows_internal_soft_data_link_and_rejects_cycles(self):
        stream_path = next(workspace.epochs(self.doc))[3]['responses']['Amp1']['h5path']
        with h5py.File(self.path, 'r+') as h5:
            h5['samples'] = h5[stream_path + '/data']
            del h5[stream_path + '/data']
            h5[stream_path + '/data'] = h5py.SoftLink('/samples')
        self.assertEqual(self.trace()['values'], [0., 1., 2., 3.])
        with h5py.File(self.path, 'r+') as h5:
            del h5['samples']
            h5['samples'] = h5py.SoftLink('/samples')
        with self.assertRaisesRegex(ValueError, 'cyclic H5 soft link'):
            self.trace()

    def prepare(self):
        repository = Path(__file__).resolve().parents[2] / '.rieke-runtime/retinanalysis'
        if not (repository / 'src/retinanalysis/utils/parse_data.py').exists():
            self.skipTest('Pinned RetinAnalysis parser is not installed')
        _, parser_path = workspace.load_parser(repository)
        sha = workspace.digest(self.path)
        project = self.path.parent / 'project'
        cache = project / 'imports' / (self.path.stem + '-' + sha[:12])
        cache.mkdir(parents=True, exist_ok=True)
        raw = cache / 'metadata.raw.json'
        workspace.write_json(raw, self.doc)
        workspace.write_json(cache / 'parse-manifest.json', {'status': 'parsed', 'sha256': sha,
            'metadata_sha256': workspace.digest(raw), 'parser_sha256': workspace.digest(parser_path)})
        return workspace.prepare(self.path, project, repository)

    def test_prepare_and_projection_retain_empty_cells_and_same_label_ownership(self):
        with h5py.File(self.path, 'r+') as h5:
            sources = h5['/experiment-' + uid(1) + '/sources/animal-' + uid(2) +
                         '/sources/preparation-' + uid(3) + '/sources']
            sources.create_group('empty-cell-' + uid(40)).attrs['uuid'] = uid(40)
        empty = copy.deepcopy(self.cells()[0])
        empty.update(uuid=uid(40), epoch_groups=[])
        self.cells().append(empty)
        doc, rows, manifest, _ = self.prepare()
        self.assertEqual(manifest['counts']['cells'], 3)
        self.assertEqual(manifest['cell_count_semantics'], 'all-source-cells-v1')
        self.assertEqual({r['cell_uuid'] for r in rows}, {uid(10), uid(20)})
        projection = WorkspaceService.__new__(WorkspaceService)._read_source_metadata(
            {'source_sha256': manifest['source_sha256'], 'manifest': manifest}, doc, self.path, self.signature())
        self.assertEqual(set(projection['cells']), {uid(10), uid(20), uid(40)})
        self.assertEqual(projection['rows'][uid(23)]['cell_uuid'], uid(20))

        # Legacy manifests counted only cells encountered while iterating epochs.
        legacy = copy.deepcopy(manifest)
        legacy.pop('cell_count_semantics')
        legacy['counts']['cells'] = 2
        reopened = WorkspaceService.__new__(WorkspaceService)._read_source_metadata(
            {'source_sha256': legacy['source_sha256'], 'manifest': legacy}, doc, self.path, self.signature())
        self.assertEqual(set(reopened['cells']), {uid(10), uid(20), uid(40)})
        self.assertEqual(reopened['rows'], projection['rows'])
        # A convention mismatch must still fail, never guess either count.
        for bad in (dict(legacy, cell_count_semantics='all-source-cells-v1'),
                    dict(manifest, cell_count_semantics='future-unknown'),
                    {key: value for key, value in manifest.items() if key != 'cell_count_semantics'}):
            with self.subTest(bad=bad.get('cell_count_semantics')):
                with self.assertRaisesRegex(ValueError, 'count|semantics'):
                    WorkspaceService.__new__(WorkspaceService)._read_source_metadata(
                        {'source_sha256': bad['source_sha256'], 'manifest': bad}, doc, self.path, self.signature())

    def test_prepare_validates_parameters_on_streamless_epochs(self):
        with h5py.File(self.path, 'r+') as h5:
            params = h5['/experiment-' + uid(1) + '/epochGroups/group-' + uid(21) +
                        '/epochBlocks/block-' + uid(22) + '/epochs/epoch-' + uid(23) + '/protocolParameters']
            params.attrs['amplitude'] = 17.
        with self.assertRaisesRegex(ValueError, 'Source parameter mismatch'):
            self.prepare()

    def test_prepare_retains_empty_block_protocol_parameters_and_verified_metadata(self):
        with h5py.File(self.path, 'r+') as h5:
            block = h5['/experiment-' + uid(1) + '/epochGroups/group-' + uid(21) + '/epochBlocks/empty-' + uid(30)]
            block.attrs['protocolID'] = 'example.EmptyProtocol'
            block.create_group('protocolParameters').attrs['sampleRate'] = 10000.
        original = workspace.digest(self.path)
        doc, rows, manifest, folder = self.prepare()
        blocks = doc['animals'][0]['preparations'][0]['cells'][1]['epoch_groups'][0]['epoch_blocks']
        empty = next(block for block in blocks if block['uuid'] == uid(30))
        self.assertEqual(empty['protocolID'], 'example.EmptyProtocol')
        self.assertEqual(empty['parameters'], {'sampleRate': 10000.})
        self.assertEqual(empty['epochs'], [])
        self.assertEqual(len(rows), 2)
        self.assertEqual(workspace.digest(self.path), original)
        self.assertEqual(workspace.digest(folder / 'metadata.catalog.json'), manifest['metadata_sha256'])
        self.assertTrue(any(warning['code'] == 'empty_epoch_block_restored' for warning in manifest['warnings']))
        again = self.prepare()
        self.assertEqual(again[0], doc)

    def test_changed_group_source_link_to_other_existing_cell_rejected(self):
        with h5py.File(self.path, 'r+') as h5:
            groups = h5['/experiment-' + uid(1) + '/epochGroups']
            first, second = groups['group-' + uid(11)], groups['group-' + uid(21)]
            del first['source']
            first['source'] = second['source']
        with self.assertRaisesRegex(ValueError, 'group ownership.*source cell'):
            self.validate()

    def test_dependencies_rejected_before_reading_data(self):
        for kind in ('external_link', 'external_storage', 'virtual', 'external_group'):
            with self.subTest(kind=kind):
                self.doc = fixture(self.path)
                stream = next(workspace.epochs(self.doc))[3]['responses']['Amp1']
                with h5py.File(self.path, 'r+') as h5:
                    obj = h5[stream['h5path']]
                    del obj['data']
                    if kind == 'external_link':
                        obj['data'] = h5py.ExternalLink('nonexistent.h5', '/values')
                    elif kind == 'external_group':
                        h5['unparsed_dependency'] = h5py.ExternalLink('nonexistent.h5', '/')
                    elif kind == 'external_storage':
                        obj.create_dataset('data', (4,), dtype='f8', external=[('nonexistent.raw', 0, 32)])
                    else:
                        layout = h5py.VirtualLayout((4,), dtype='f8')
                        layout[:] = h5py.VirtualSource('nonexistent.h5', 'values', shape=(4,))
                        obj.create_virtual_dataset('data', layout)
                with self.assertRaisesRegex(ValueError, '(External|Virtual).*unsupported'):
                    self.validate()


if __name__ == '__main__':
    unittest.main()
