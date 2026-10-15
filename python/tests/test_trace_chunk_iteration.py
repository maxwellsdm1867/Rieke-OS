"""Owned optional C metadata callback, library admission and locking checks."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib

import h5py
import numpy as np
import workspace_trace_chunk_iteration as bridge
import workspace_trace_native as native


class TraceChunkIterationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('cc')
        if compiler is None or sys.platform not in ('darwin', 'linux'):
            raise unittest.SkipTest('Native fixture requires a macOS/Linux compiler')
        cls.build = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build.cleanup)
        library = Path(cls.build.name) / 'helper.so'
        source = Path(__file__).resolve().parents[2] / 'desktop/native/trace_inflate.c'
        subprocess.run([compiler, '-O3', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fno-fast-math', '-ffp-contract=off', '-fPIC',
                        '-dynamiclib' if sys.platform == 'darwin' else '-shared',
                        str(source), '-o', str(library), '-lz', '-lm', '-pthread'],
                       check=True)
        cls.helper = ctypes.CDLL(str(library))
        cls.helper.disco_trace_chunk_collect_v1.argtypes = [ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_uint, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
        cls.helper.disco_trace_chunk_collect_v1.restype = ctypes.c_int

    def setUp(self):
        bridge._binding.cache_clear()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(bridge._binding.cache_clear)

    def bound(self):
        bound = bridge._binding(self.helper)
        if bound is None:
            self.skipTest('This HDF5 build/platform is not qualified for direct iteration')
        return bound

    def create(self, userblock=0, kind='dense'):
        path = Path(self.folder.name) / f'{userblock}-{kind}.h5'
        count = 1025 if kind == 'tail' else 1024
        values = np.zeros(count, dtype=[('quantity', '<f8'), ('units', 'S10')])
        values['quantity'], values['units'] = np.arange(count) / 7, b'pA'
        values['quantity'][3] = -0.
        with h5py.File(path, 'w', userblock_size=userblock or None) as h5:
            data = h5.create_dataset('data', shape=(count,), dtype=values.dtype,
                                     chunks=(64,), compression='gzip')
            order = list(range((count + 63) // 64))
            if kind == 'reverse': order.reverse()
            if kind == 'sparse': order = order[::2]
            for index in order:
                block = np.zeros(64, dtype=values.dtype)
                part = values[index * 64:(index + 1) * 64]
                block[:len(part)] = part
                mask = 1 if kind == 'masked' else 0
                data.id.write_direct_chunk((index * 64,),
                    block.tobytes() if mask else zlib.compress(block.tobytes()), filter_mask=mask)
                if kind == 'reverse':
                    h5.create_dataset(f'gap-{index}', data=np.zeros(70000, dtype='u1'))
        return path, values

    def assert_map_equal(self, left, right):
        self.assertEqual(left[0], right[0])
        if left[1] is None:
            self.assertIsNone(right[1])
        else:
            self.assertIsNotNone(right[1])
            for index in (0, 1, 3):
                self.assertEqual(left[1][index].tobytes(), right[1][index].tobytes())
            self.assertEqual(left[1][2], right[1][2])

    def test_userblocks_fragmentation_sparse_masks_and_tail_match_h5py(self):
        self.bound()
        for userblock in (0, 512, 4096):
            for kind in ('dense', 'reverse', 'sparse', 'masked', 'tail'):
                with self.subTest(userblock=userblock, kind=kind):
                    path, values = self.create(userblock, kind)
                    with h5py.File(path, 'r') as h5:
                        expected = native._enumerate_chunk_arrays(h5['data'])
                        actual = native._enumerate_chunk_arrays(h5['data'], self.helper)
                        self.assert_map_equal(expected, actual)
                        if actual[1] is None:
                            continue
                        physical, lengths, _, order = actual[1]
                        with path.open('rb') as source:
                            for logical in order:
                                source.seek(int(physical[logical]))
                                decoded = zlib.decompress(source.read(int(lengths[logical])))
                                start = int(logical) * 64
                                wanted = values[start:start + 64].tobytes()
                                self.assertEqual(decoded[:len(wanted)], wanted)

    def test_missing_optional_symbols_keep_old_helper_and_python_map_usable(self):
        class OldHelper:
            def __getattr__(self, name):
                if name.startswith('disco_trace_chunk_'):
                    raise AttributeError(name)
                return getattr(TraceChunkIterationTests.helper, name)
        old = OldHelper()
        self.assertEqual(old.disco_trace_inflate_abi(), 4)
        self.assertIsNone(bridge._binding(old))
        path, _ = self.create()
        with h5py.File(path, 'r') as h5:
            self.assertIs(bridge.try_enumerate_chunks(h5['data'], old), bridge.UNSUPPORTED)
            self.assert_map_equal(native._enumerate_chunk_arrays(h5['data']),
                                  native._enumerate_chunk_arrays(h5['data'], old))
        self.assertIs(bridge.try_enumerate_chunks(object(), self.helper), bridge.UNSUPPORTED)

    def test_public_value_read_uses_callback_and_old_helper_keeps_exact_fallback(self):
        bound = self.bound()
        helper = self.helper
        helper.disco_trace_extract_v1.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_uint]
        helper.disco_trace_extract_v1.restype = ctypes.c_int
        class OldHelper:
            def __getattr__(self, name):
                if name.startswith('disco_trace_chunk_'):
                    raise AttributeError(name)
                return getattr(helper, name)
        path, values = self.create(512, 'reverse')
        stat = path.stat()
        signature = (str(path), stat.st_dev, stat.st_ino, stat.st_size,
                     stat.st_mtime_ns, stat.st_ctime_ns)
        calls = []
        def observed(*args):
            calls.append(True)
            return bound[3](*args)
        live = (*bound[:3], observed, *bound[4:])
        with patch.object(native, 'MIN_NATIVE_SAMPLES', 1):
            with patch.object(native, '_load_helper', return_value=helper), \
                    patch.object(bridge, '_binding', return_value=live), h5py.File(path, 'r') as h5:
                actual = native.read_native_values(h5['data'], signature, 63, 897, 'pA')
            self.assertEqual(calls, [True])
            self.assertEqual(actual.tobytes(), values['quantity'][63:897].tobytes())
            with patch.object(native, '_load_helper', return_value=OldHelper()), h5py.File(path, 'r') as h5:
                fallback = native.read_native_values(h5['data'], signature, 63, 897, 'pA')
            self.assertEqual(fallback.tobytes(), actual.tobytes())
            self.assertEqual(calls, [True])

    def test_unqualified_hdf5_with_optional_symbols_uses_python_map_on_every_platform(self):
        path, _ = self.create()
        with patch.object(bridge, '_qualify_hdf5',
                side_effect=bridge._Unavailable('Unqualified runtime')) as qualify, \
                patch.object(self.helper, 'disco_trace_chunk_collect_v1',
                    side_effect=AssertionError('No native iteration may begin')) as callback:
            self.assertIsNone(bridge._binding(self.helper))
            with h5py.File(path, 'r') as h5:
                expected = native._enumerate_chunk_arrays(h5['data'])
                actual = native._enumerate_chunk_arrays(h5['data'], self.helper)
                self.assert_map_equal(expected, actual)
            qualify.assert_called_once_with()
            callback.assert_not_called()

    def test_optional_context_version_size_and_offsets_reject_before_hdf5(self):
        helper = self.helper
        faults = {'disco_trace_chunk_context_v1_version': lambda: 2,
                  'disco_trace_chunk_context_v1_size': lambda: ctypes.sizeof(bridge._Context) + 8,
                  'disco_trace_chunk_context_v1_offset': lambda index: 999}
        for name, replacement in faults.items():
            class Proxy:
                def __getattr__(self, key):
                    return replacement if key == name else getattr(helper, key)
            with self.subTest(name=name), patch.object(bridge, '_qualify_hdf5',
                    side_effect=AssertionError('HDF5 admission must not begin')):
                self.assertIsNone(bridge._binding(Proxy()))

    def test_qualification_rejects_versions_paths_and_private_symlink_escape(self):
        self.bound()
        for owner, key, value in ((h5py, '__version__', '3.15.0'),
                (h5py.version, 'hdf5_version_tuple', (1, 14, 3)),
                (h5py.h5d, '__file__', __file__)):
            with self.subTest(key=key), patch.object(owner, key, value):
                with self.assertRaises(bridge._Unavailable):
                    bridge._qualify_hdf5()
        root = Path(self.folder.name).resolve() / 'package'
        root.mkdir()
        outside = Path(self.folder.name).resolve() / 'outside'
        outside.mkdir()
        (root / '.dylibs').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(bridge._Unavailable, 'directory escaped'):
            bridge._qualified_private_image(root, outside / 'libhdf5.dylib')
        (root / '.dylibs').unlink()
        (root / '.dylibs').mkdir()
        with self.assertRaisesRegex(bridge._Unavailable, 'not from'):
            bridge._qualified_private_image(root, outside / 'libhdf5.dylib')
        with patch.object(bridge.sys, 'platform', 'linux'):
            with self.assertRaises(bridge._Unavailable):
                bridge._qualify_hdf5()

    def test_c_callback_bounds_flags_and_invalid_context_canaries(self):
        callback = self.helper.disco_trace_chunk_collect_v1
        def context():
            physical = np.full(6, 13, dtype='u8')
            lengths = np.full(6, 17, dtype='u8')
            order = np.full(6, -1, dtype='i8')
            seen = (ctypes.c_ubyte * 6)()
            ctx = bridge._Context(1, 2, 128, 0, physical.ctypes.data,
                lengths.ctypes.data, order.ctypes.data, ctypes.addressof(seen), 0, 0, 0, 0)
            return ctx, physical, lengths, order, seen
        for field, value in (('version', 2), ('reserved', 1), ('total', 0),
                ('total', 1000001), ('capacity', 3), ('physical', None),
                ('lengths', None), ('order', None), ('seen', None), ('coordinate', None)):
            with self.subTest(field=field, value=value):
                ctx, physical, lengths, order, seen = context()
                coordinate = ctypes.c_uint64(0)
                if field != 'coordinate': setattr(ctx, field, value)
                self.assertEqual(callback(None if field == 'coordinate' else ctypes.byref(coordinate),
                    0, 100, 20, ctypes.byref(ctx)), -1)
                self.assertEqual((ctx.count, ctx.invalid_context), (0, 1))
                self.assertTrue(np.all(physical == 13) and np.all(lengths == 17) and
                                np.all(order == -1) and not any(seen))
        for entries, invalid, masked in (
                (((64, 0), (0, 1)), 0, 1), (((1, 0),), 1, 0),
                (((0, 0), (0, 1)), 1, 0), (((1, 0), (64, 0), (128, 0)), 1, 0)):
            ctx, physical, lengths, order, seen = context()
            for index, mask in entries:
                coordinate = ctypes.c_uint64(index)
                self.assertEqual(callback(ctypes.byref(coordinate), mask, 2**64 - 1,
                    2**64 - 1, ctypes.byref(ctx)), 0)
            self.assertEqual((ctx.count, ctx.invalid_logical, ctx.masked), (len(entries), invalid, masked))
            self.assertTrue(np.all(physical[2:] == 13) and np.all(lengths[2:] == 17) and
                            np.all(order[2:] == -1) and not any(seen[2:]))

    def test_post_callback_error_or_early_stop_never_retries_and_closed_id_fails(self):
        bound = self.bound()
        path, _ = self.create()
        for result in (-1, 1):
            invoked = []
            def stopped(dataset, dxpl, callback, context):
                coordinate = ctypes.c_uint64(0)
                self.assertEqual(bound[6](ctypes.byref(coordinate), 0, 100, 20, context), 0)
                self.assertEqual(ctypes.cast(context, ctypes.POINTER(bridge._Context)).contents.count, 1)
                invoked.append(True)
                return result
            altered = (*bound[:3], stopped, *bound[4:])
            with h5py.File(path, 'r') as h5, patch.object(bridge, '_binding', return_value=altered):
                with self.assertRaisesRegex(ValueError, 'iteration failed'):
                    bridge.try_enumerate_chunks(h5['data'], self.helper)
            self.assertEqual(invoked, [True])
        with h5py.File(path, 'r') as h5:
            closed = h5['data']
        with self.assertRaisesRegex(ValueError, 'ID is invalid'):
            bridge.try_enumerate_chunks(closed, self.helper)

    def test_phil_serializes_other_hdf5_users_across_complete_iteration(self):
        bound = self.bound()
        path, _ = self.create()
        entered, release = threading.Event(), threading.Event()
        attempting, acquired = threading.Event(), threading.Event()
        results, errors = [], []
        def held(*args):
            entered.set()
            if not release.wait(5): raise AssertionError('Test release deadline')
            return bound[3](*args)
        altered = (*bound[:3], held, *bound[4:])
        with h5py.File(path, 'r') as h5:
            data = h5['data']
            def first():
                try: results.append(bridge.try_enumerate_chunks(data, self.helper))
                except BaseException as error: errors.append(error)
            def second():
                attempting.set()
                with bound[2]: acquired.set()
            with patch.object(bridge, '_binding', return_value=altered):
                worker = threading.Thread(target=first)
                other = threading.Thread(target=second)
                worker.start()
                try:
                    self.assertTrue(entered.wait(5))
                    other.start()
                    self.assertTrue(attempting.wait(5))
                    self.assertFalse(acquired.wait(.05))
                finally:
                    release.set()
                    worker.join(5)
                    if other.ident is not None: other.join(5)
                self.assertFalse(worker.is_alive() or other.is_alive())
            self.assertEqual(errors, [])
            self.assertTrue(acquired.is_set())
            self.assertEqual(len(results), 1)
            self.assert_map_equal(native._enumerate_chunk_arrays(data), results[0])
