"""EpicTree mask format/identity tests; only temporary MATLAB fixture files."""
import copy
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np
from scipy.io import savemat

from workspace_matlab_masks import read_ugm, write_ugm

IDS = ['8381b8dc-3d62-40b3-8fc9-9781e1e7c33c', 'e7c03f90-1ad3-4240-8d49-7074e437c534']
DATASET = 'a6bb15a2-1238-4f3c-9c84-2d8f467394bb'


class MatlabMaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'selection.ugm'

    def h5_fixture(self, ids=IDS, mask=(True, False), count=None, version='1.1', logical=True):
        with h5py.File(self.path, 'w') as file:
            group = file.create_group('ugm')
            group.attrs['MATLAB_class'] = np.bytes_('struct')
            for key, value in {'version': version, 'created': '2026-09-27 10:00:00', 'mat_file_basename': 'recordings'}.items():
                dataset = group.create_dataset(key, data=np.frombuffer(value.encode('utf-16-le'), dtype='<u2').reshape(-1, 1))
                dataset.attrs['MATLAB_class'] = np.bytes_('char')
            group.create_dataset('epoch_count', data=np.array([[len(ids) if count is None else count]], dtype=float))
            dataset = group.create_dataset('selection_mask', data=np.asarray(mask, dtype=np.uint8).reshape(1, -1))
            dataset.attrs['MATLAB_class'] = np.bytes_('logical' if logical else 'uint8')
            refs = file.create_group('#refs#')
            cells = group.create_dataset('epoch_h5_uuids', shape=(1, len(ids)), dtype=h5py.ref_dtype)
            cells.attrs['MATLAB_class'] = np.bytes_('cell')
            for index, identity in enumerate(ids):
                dataset = refs.create_dataset(str(index), data=np.frombuffer(identity.encode('utf-16-le'), dtype='<u2').reshape(-1, 1))
                dataset.attrs['MATLAB_class'] = np.bytes_('char')
                cells[0, index] = dataset.ref

    def test_matlab_hdf5_mask_is_uuid_keyed_and_false_excludes(self):
        self.h5_fixture(ids=IDS[::-1])
        result = read_ugm(self.path, expected_epoch_uuids=IDS)
        self.assertEqual(dict(zip(result['epoch_uuids'], result['mask'])), {IDS[1]: True, IDS[0]: False})
        self.assertEqual(result['metadata']['version'], '1.1')
        self.assertEqual(result['metadata']['created'], '2026-09-27 10:00:00')

    def test_writer_emits_matlab73_logical_cell_columns_legacy_reader_accepts(self):
        from import_ugm import read_ugm as legacy_read
        result = write_ugm(self.path, IDS, [True, False], {'mat_file_basename': 'recordings',
            'dataset_uuid': DATASET, 'source_scope_revision': 'a' * 64})
        self.assertTrue(h5py.is_hdf5(self.path))
        with h5py.File(self.path, 'r') as file:
            self.assertEqual(file['ugm/selection_mask'].attrs['MATLAB_class'], b'logical')
            self.assertEqual(file['ugm/epoch_h5_uuids'].attrs['MATLAB_class'], b'cell')
            self.assertEqual(file['ugm/selection_mask'].shape, (1, 2))
        loaded = read_ugm(self.path, expected_epoch_uuids=IDS[::-1],
                          expected_metadata={'dataset_uuid': DATASET, 'source_scope_sha256': 'a' * 64})
        self.assertEqual(loaded, result)
        legacy = legacy_read(self.path)
        self.assertEqual(legacy['excluded_uuids'], [IDS[1]])
        self.assertEqual(legacy['selected_uuids'], [IDS[0]])

    def test_mat5_logical_struct_compatibility(self):
        cells = np.empty((2, 1), dtype=object)
        cells[:, 0] = IDS
        savemat(self.path, {'ugm': {'version': '1.1', 'epoch_count': 2.0,
            'selection_mask': np.array([[True], [False]]), 'epoch_h5_uuids': cells,
            'created': 'not used to resolve identity', 'mat_file_basename': 'name is not identity'}}, appendmat=False)
        self.assertEqual(read_ugm(self.path)['mask'], [True, False])

    def test_single_epoch_and_empty_basename_roundtrip(self):
        expected = write_ugm(self.path, [IDS[0]], [False])
        self.assertEqual(read_ugm(self.path), expected)
        self.assertEqual(expected['metadata']['mat_file_basename'], '')

    def test_writer_refuses_source_file_extensions(self):
        source = self.path.with_suffix('.mat')
        source.write_bytes(b'original source fixture')
        with self.assertRaisesRegex(ValueError, 'separate from source'):
            write_ugm(source, IDS, [True, False])
        self.assertEqual(source.read_bytes(), b'original source fixture')

    def test_writer_rejects_numeric_truthiness(self):
        for mask in ([1, 0], [2, 0], [np.nan, 0]):
            with self.subTest(mask=mask), self.assertRaisesRegex(ValueError, 'logical/boolean'):
                write_ugm(self.path, IDS, mask)
        self.assertFalse(self.path.exists())

    def test_reader_rejects_nonlogical_and_invalid_logical_values(self):
        for logical, mask in [(False, [1, 0]), (True, [2, 0])]:
            with self.subTest(logical=logical):
                self.h5_fixture(mask=mask, logical=logical)
                with self.assertRaisesRegex(ValueError, 'logical'):
                    read_ugm(self.path)

    def test_rejects_duplicate_blank_foreign_or_missing_uuids(self):
        for ids in ([IDS[0], IDS[0]], [IDS[0], '']):
            with self.subTest(ids=ids):
                self.h5_fixture(ids=ids)
                with self.assertRaises(ValueError):
                    read_ugm(self.path)
        self.h5_fixture()
        with self.assertRaisesRegex(ValueError, 'foreign, 0 missing'):
            read_ugm(self.path, expected_epoch_uuids=[IDS[0]])
        with self.assertRaisesRegex(ValueError, '0 foreign, 1 missing'):
            read_ugm(self.path, expected_epoch_uuids=IDS + [DATASET])

    def test_rejects_length_count_and_version_mismatch(self):
        for options in ({'count': 1}, {'count': 2.5}, {'mask': [True]}, {'version': '1.0'}):
            with self.subTest(options=options):
                self.h5_fixture(**options)
                with self.assertRaises(ValueError):
                    read_ugm(self.path)

    def test_provenance_mismatch_rejected_but_legacy_absence_does_not_invent_identity(self):
        write_ugm(self.path, IDS, [True, False], {'dataset_uuid': DATASET, 'source_scope_sha256': 'a' * 64})
        with self.assertRaisesRegex(ValueError, 'dataset_uuid'):
            read_ugm(self.path, expected_metadata={'dataset_uuid': IDS[0]})
        with self.assertRaisesRegex(ValueError, 'source scope hash'):
            read_ugm(self.path, expected_metadata={'source_scope_revision': 'b' * 64})
        self.h5_fixture()
        result = read_ugm(self.path, expected_epoch_uuids=IDS, expected_metadata={'dataset_uuid': DATASET})
        self.assertNotIn('dataset_uuid', result['metadata'])

    def test_no_uuid_field_never_falls_back_to_position(self):
        self.h5_fixture()
        with h5py.File(self.path, 'a') as file:
            del file['ugm/epoch_h5_uuids']
        with self.assertRaisesRegex(ValueError, 'positional masks'):
            read_ugm(self.path)

    def test_uuid_map_updates_only_the_known_export_subset(self):
        self.h5_fixture(ids=IDS[::-1])
        parsed = read_ugm(self.path, expected_epoch_uuids=IDS)
        working = {IDS[0]: True, IDS[1]: False, DATASET: False}
        before = copy.deepcopy(working)
        working.update(zip(parsed['epoch_uuids'], parsed['mask']))
        self.assertFalse(working[IDS[0]])
        self.assertTrue(working[IDS[1]])
        self.assertEqual(working[DATASET], before[DATASET])

    def test_external_hdf5_links_are_rejected(self):
        external = Path(self.temp.name) / 'external.h5'
        with h5py.File(external, 'w') as file:
            file.create_group('ugm')
        with h5py.File(self.path, 'w') as file:
            file['ugm'] = h5py.ExternalLink(str(external), '/ugm')
        with self.assertRaisesRegex(ValueError, 'scalar ugm struct'):
            read_ugm(self.path)


if __name__ == '__main__':
    unittest.main()
