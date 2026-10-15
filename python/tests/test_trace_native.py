"""Actual native inflate checks on owned H5 fixtures; no user recordings."""
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

import h5py
import numpy as np
import workspace_trace_native as native


class NativeTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
        if compiler is None or sys.platform not in ('darwin', 'linux'):
            raise unittest.SkipTest('Native C fixture requires macOS/Linux C compiler')
        cls.build = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build.cleanup)
        library = Path(cls.build.name) / 'owned-inflate.so'
        source = Path(__file__).resolve().parents[2] / 'desktop/native/trace_inflate.c'
        sdk = ['-isysroot', subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()] if sys.platform == 'darwin' else []
        subprocess.run([compiler, *sdk, '-O2', '-fno-fast-math', '-ffp-contract=off', '-dynamiclib' if sys.platform == 'darwin' else '-shared',
                        '-fPIC', str(source), '-o', str(library), '-lz', '-pthread'], check=True,
                       capture_output=True)
        cls.helper = ctypes.CDLL(str(library))
        cls.helper.disco_trace_inflate_abi.restype = ctypes.c_uint
        cls.helper.disco_trace_inflate_v1.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint]
        cls.helper.disco_trace_inflate_v1.restype = ctypes.c_int
        cls.helper.disco_trace_normalize_units_v1.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        cls.helper.disco_trace_normalize_units_v1.restype = ctypes.c_int
        cls.helper.disco_trace_extract_v1.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_uint]
        cls.helper.disco_trace_extract_v1.restype = ctypes.c_int
        cls.helper.disco_trace_m4_v1.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        cls.helper.disco_trace_m4_v1.restype = ctypes.c_int
        assert cls.helper.disco_trace_inflate_abi() == 4

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'source.h5'
        # Small adversarial layouts exercise the same admitted reader without
        # making every malformed-fixture case allocate a million records.
        threshold = patch.object(native, 'MIN_NATIVE_SAMPLES', 1)
        threshold.start()
        self.addCleanup(threshold.stop)
        self.loader = patch.object(native, '_load_helper', return_value=self.helper)
        self.loader.start()
        self.addCleanup(self.loader.stop)

    def values(self, n=1025, dtype=None):
        values = np.zeros(n, dtype=dtype or [('quantity', '<f8'), ('units', 'S10')])
        values['quantity'] = np.arange(n) / 7
        values['quantity'][:5] = [-0., 0., np.finfo('f8').max, 5e-324, -1e-300]
        values['units'] = b'pA'
        return values

    def signature(self):
        s = self.path.stat()
        return (str(self.path), s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

    def create(self, values=None, **options):
        values = self.values() if values is None else values
        with h5py.File(self.path, 'w') as h5:
            h5.create_dataset('data', data=values, **({'chunks': (64,), 'compression': 'gzip'} | options))
        return values

    def read(self, begin=0, end=None):
        with h5py.File(self.path, 'r') as h5:
            d = h5['data']
            return native.read_native_samples(d, self.signature(), begin, len(d) if end is None else end)

    def test_native_exact_full_tail_unaligned_and_four_byte_signature(self):
        values = self.create()
        for begin, end in ((0, len(values)), (13, 1000), (1024, 1025), (0, 64)):
            with self.subTest(begin=begin, end=end):
                self.assertEqual(self.read(begin, end).tobytes(), values[begin:end].tobytes())
        sig = self.signature()
        with h5py.File(self.path, 'r') as h5:
            result = native.read_native_samples(h5['data'], (sig[0], *sig[3:]), 0, len(values))
        self.assertEqual(result.tobytes(), values.tobytes())

    def test_small_requested_range_keeps_generic_h5_and_large_real_threshold_works(self):
        values = self.create(self.values(100003))
        with patch.object(native, 'MIN_NATIVE_SAMPLES', 100000):
            with patch.object(native.os, 'pread', side_effect=AssertionError('No raw I/O')):
                self.assertIsNone(self.read(0, 1000))
            self.assertEqual(self.read().tobytes(), values.tobytes())

    def test_integrated_service_rejects_mixed_units_and_nonfinite_after_native_read(self):
        from workspace_service import _response_window_reader
        import uuid
        epoch, stream_id = str(uuid.uuid4()), str(uuid.uuid4())
        for field, bad in (('units', b'mV'), ('quantity', float('nan'))):
            values = self.values(100003)
            values[field][-1] = bad
            with h5py.File(self.path, 'w') as h5:
                h5.create_group('epoch').attrs['uuid'] = epoch
                g = h5.create_group('epoch/responses/stream')
                g.attrs['uuid'], g.attrs['sampleRate'] = stream_id, 10000.
                g.create_dataset('data', data=values, chunks=(64,), compression='gzip')
            row = dict(epoch_uuid=epoch, source_sha256='verified-by-caller')
            stream = dict(uuid=stream_id, h5_path='/epoch/responses/stream',
                          sample_rate=10000., sample_count=len(values), units='pA')
            with patch.object(native, 'read_native_values', wraps=native.read_native_values) as used:
                with self.assertRaisesRegex(ValueError, 'units are inconsistent|nonfinite'):
                    with _response_window_reader(self.path, self.signature(), row, stream,
                                                 native_range=(0,len(values))) as read:
                        read(0, 100000, array_values=True)
                        read(100000, 3, array_values=True)
                self.assertEqual(used.call_count, 1)

    def test_fragmented_physical_chunks_are_coalesced_with_caps(self):
        values = self.values(2048)
        with h5py.File(self.path, 'w') as h5:
            d = h5.create_dataset('data', shape=(len(values),), dtype=values.dtype,
                                  chunks=(64,), compression='gzip')
            for index in reversed(range(len(values) // 64)):
                d.id.write_direct_chunk((index * 64,), zlib.compress(values[index*64:(index+1)*64].tobytes()))
                h5.create_dataset(f'unrelated-{index}', data=np.zeros(80000, dtype='u1'))
        original = os.pread
        lengths = []
        def observed(fd, length, offset):
            lengths.append(length)
            return original(fd, length, offset)
        with patch.object(native.os, 'pread', side_effect=observed):
            result = self.read()
        self.assertEqual(result.tobytes(), values.tobytes())
        self.assertGreater(len(lengths), 1)
        self.assertLessEqual(max(lengths), native.MAX_SPAN_BYTES)
        self.assertLessEqual(sum(lengths), native.MAX_INPUT_BYTES)
        self.assertLess(sum(lengths), self.path.stat().st_size // 2)

    def test_unsupported_endian_padding_filters_and_layout_fall_back_before_raw_io(self):
        cases = [dict(values=self.values(dtype=[('quantity','>f8'),('units','S10')])),
                 dict(values=self.values(dtype=np.dtype({'names':['quantity','units'],
                     'formats':['<f8','S10'], 'offsets':[0,16], 'itemsize':32}))),
                 dict(shuffle=True), dict(fletcher32=True), dict(compression=None), dict(chunks=(128,))]
        for options in cases:
            with self.subTest(options=options):
                self.create(**options)
                with patch.object(native.os, 'pread', side_effect=AssertionError('No raw I/O')):
                    self.assertIsNone(self.read())

    def test_same_numpy_dtype_with_different_h5_string_encoding_falls_back(self):
        values = self.values(64)
        with h5py.File(self.path, 'w') as h5:
            compound = h5py.h5t.create(h5py.h5t.COMPOUND, 18)
            compound.insert(b'quantity', 0, h5py.h5t.IEEE_F64LE)
            string = h5py.h5t.C_S1.copy()
            string.set_size(10)
            string.set_cset(h5py.h5t.CSET_UTF8)
            string.set_strpad(h5py.h5t.STR_NULLPAD)
            compound.insert(b'units', 8, string)
            props = h5py.h5p.create(h5py.h5p.DATASET_CREATE)
            props.set_chunk((64,))
            props.set_deflate(4)
            dataset = h5py.h5d.create(h5.id, b'data', compound,
                                     h5py.h5s.create_simple((64,)), dcpl=props)
            dataset.write_direct_chunk((0,), zlib.compress(values.tobytes()))
        with h5py.File(self.path, 'r') as h5:
            self.assertEqual(h5['data'].dtype, values.dtype)
        with patch.object(native.os, 'pread', side_effect=AssertionError('No raw I/O')):
            self.assertIsNone(self.read())

    def test_nullterm_units_match_h5_conversion_including_embedded_null_and_full_width(self):
        values = self.values(64)
        values['units'][:6] = [b'pA\0garbage', b'abcdefghij', b'\0garbage', b'pA', b'\xffA', b'pA\0\xff']
        with h5py.File(self.path, 'w') as h5:
            compound = h5py.h5t.create(h5py.h5t.COMPOUND, 18)
            compound.insert(b'quantity', 0, h5py.h5t.IEEE_F64LE)
            string = h5py.h5t.C_S1.copy()
            string.set_size(10)
            string.set_strpad(h5py.h5t.STR_NULLTERM)
            compound.insert(b'units', 8, string)
            props = h5py.h5p.create(h5py.h5p.DATASET_CREATE)
            props.set_chunk((64,))
            props.set_deflate(4)
            dataset = h5py.h5d.create(h5.id, b'data', compound,
                                     h5py.h5s.create_simple((64,)), dcpl=props)
            dataset.write_direct_chunk((0,), zlib.compress(values.tobytes()))
        with h5py.File(self.path, 'r') as h5:
            expected = h5['data'][:]
        actual = self.read()
        self.assertIsNotNone(actual)
        self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_unallocated_or_skipped_filter_chunks_use_generic_h5(self):
        values = self.values(128)
        for mask, data in ((0, zlib.compress(values[:64].tobytes())), (1, values[:64].tobytes())):
            with self.subTest(mask=mask):
                with h5py.File(self.path, 'w') as h5:
                    d = h5.create_dataset('data', shape=(128,), dtype=values.dtype, chunks=(64,), compression='gzip')
                    d.id.write_direct_chunk((0,), data, filter_mask=mask)
                    if mask: d.id.write_direct_chunk((64,), values[64:].tobytes(), filter_mask=mask)
                with patch.object(native.os, 'pread', side_effect=AssertionError('No raw I/O')):
                    self.assertIsNone(self.read())
                with h5py.File(self.path, 'r') as h5:
                    expected = h5['data'][:]
                    self.assertEqual(expected[:64].tobytes(), values[:64].tobytes())

    def test_reused_decoder_keeps_independent_streams_and_refuses_late_corruption(self):
        # More chunks than workers forces reset/reuse within every worker.
        values = self.values(64 * 33)
        chunks = [zlib.compress(values[i:i + 64].tobytes(), level=(i // 64) % 10)
                  for i in range(0, len(values), 64)]
        offsets = np.array([sum(map(len, chunks[:i])) for i in range(len(chunks))], dtype='u8')
        sizes = np.array(list(map(len, chunks)), dtype='u8')
        for workers in (1, 4, 8):
            for corrupt in (False, True):
                with self.subTest(workers=workers, corrupt=corrupt):
                    parts = list(chunks)
                    if corrupt:
                        parts[-1] = parts[-1][:-1] + bytes([parts[-1][-1] ^ 1])
                    compressed = b''.join(parts)
                    output = np.empty(values.nbytes, dtype='u1')
                    status = self.helper.disco_trace_inflate_v1(compressed, len(compressed),
                        offsets.ctypes.data, sizes.ctypes.data, len(parts), output.ctypes.data,
                        output.nbytes, native.CHUNK_BYTES, workers)
                    if corrupt:
                        self.assertEqual(status, -2)
                    else:
                        self.assertEqual(status, 0)
                        self.assertEqual(output.tobytes(), values.tobytes())

    def test_corrupt_truncated_or_trailing_zlib_bytes_are_hard_errors(self):
        values = self.values(64)
        original = zlib.compress(values.tobytes())
        for chunk in (b'invalid zlib', original[:-1], original + b'extra', zlib.compress(b'wrong size')):
            with self.subTest(length=len(chunk)):
                with h5py.File(self.path, 'w') as h5:
                    d = h5.create_dataset('data', shape=(64,), dtype=values.dtype, chunks=(64,), compression='gzip')
                    d.id.write_direct_chunk((0,), chunk)
                with self.assertRaisesRegex(ValueError, 'decompression'):
                    self.read()

    def test_short_physical_read_and_source_change_refuse(self):
        self.create()
        original = os.pread
        with patch.object(native.os, 'pread', side_effect=lambda fd,n,offset:original(fd,n,offset)[:-1]):
            with self.assertRaisesRegex(ValueError, 'Truncated'):
                self.read()
        with h5py.File(self.path, 'r') as h5:
            sig = self.signature()
            os.utime(self.path, ns=(self.path.stat().st_atime_ns, sig[-2] + 1000000))
            with self.assertRaisesRegex(ValueError, 'changed before'):
                native.read_native_samples(h5['data'], sig, 0, len(h5['data']))

    def test_source_timestamp_mutation_during_raw_read_refuses_publication(self):
        self.create()
        original = os.pread
        changed = []
        def mutation(fd, length, offset):
            result = original(fd, length, offset)
            if not changed:
                stat = self.path.stat()
                os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
                changed.append(True)
            return result
        with patch.object(native.os, 'pread', side_effect=mutation):
            with self.assertRaisesRegex(ValueError, 'changed while'):
                self.read()
        self.assertEqual(changed, [True])

    def test_native_thread_creation_failure_joins_started_worker_and_returns_no_samples(self):
        import json
        compiler = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
        source = Path(__file__).resolve().parents[2] / 'desktop/native/trace_inflate.c'
        wrapper = Path(self.folder.name) / 'failing-create.c'
        wrapper.write_text(
            '#include <pthread.h>\n#include <errno.h>\n'
            'static int attempts=0, joined=0;\n'
            'static int test_create(pthread_t*,const pthread_attr_t*,void*(*)(void*),void*);\n'
            'static int test_join(pthread_t,void**);\n'
            '#define pthread_create test_create\n#define pthread_join test_join\n'
            '#include ' + json.dumps(str(source)) + '\n'
            '#undef pthread_create\n#undef pthread_join\n'
            'static int test_create(pthread_t*t,const pthread_attr_t*a,void*(*f)(void*),void*p)'
            '{if(++attempts==2)return EAGAIN;return pthread_create(t,a,f,p);}\n'
            'static int test_join(pthread_t t,void**p){int r=pthread_join(t,p);if(!r)joined++;return r;}\n'
            'int test_joined(void){return joined;}\n')
        library = Path(self.folder.name) / 'failing-create.so'
        sdk = ['-isysroot', subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()] if sys.platform == 'darwin' else []
        subprocess.run([compiler,*sdk,'-O2','-dynamiclib' if sys.platform == 'darwin' else '-shared',
                        '-fPIC',str(wrapper),'-o',str(library),'-lz','-pthread'],check=True,capture_output=True)
        helper = ctypes.CDLL(str(library))
        helper.disco_trace_extract_v1.argtypes = self.helper.disco_trace_extract_v1.argtypes
        helper.disco_trace_extract_v1.restype = ctypes.c_int
        original_inflate = helper.disco_trace_extract_v1
        statuses = []
        def observed(*args):
            status = original_inflate(*args)
            statuses.append(status)
            return status
        helper.disco_trace_extract_v1 = observed
        self.create()
        with patch.object(native, '_load_helper', return_value=helper):
            with self.assertRaisesRegex(ValueError, 'failed exact decompression'):
                self.read_values()
        self.assertEqual(statuses, [-3])
        self.assertEqual(helper.test_joined(), 1)
        self.assertTrue(native._NATIVE_SLOT.acquire(blocking=False))
        native._NATIVE_SLOT.release()

    def test_decoder_reset_failure_releases_all_workers_and_native_slot(self):
        import json
        compiler = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
        source = Path(__file__).resolve().parents[2] / 'desktop/native/trace_inflate.c'
        wrapper = Path(self.folder.name) / 'failing-reset.c'
        wrapper.write_text(
            '#include <pthread.h>\n#include <zlib.h>\n#include <stdatomic.h>\n'
            'static atomic_int resets=0, initialized=0, ended=0, joined=0;\n'
            'static int test_init(z_streamp,const char*,int);\n'
            'static int test_reset(z_streamp);\nstatic int test_end(z_streamp);\n'
            'static int test_join(pthread_t,void**);\n'
            '#define inflateInit_ test_init\n#define inflateReset test_reset\n'
            '#define inflateEnd test_end\n#define pthread_join test_join\n'
            '#include ' + json.dumps(str(source)) + '\n'
            '#undef inflateInit_\n#undef inflateReset\n#undef inflateEnd\n#undef pthread_join\n'
            'static int test_init(z_streamp s,const char*v,int n){int r=inflateInit_(s,v,n);'
            'if(r==Z_OK)atomic_fetch_add(&initialized,1);return r;}\n'
            'static int test_reset(z_streamp s){if(atomic_fetch_add(&resets,1)==0)return Z_STREAM_ERROR;'
            'return inflateReset(s);}\n'
            'static int test_end(z_streamp s){atomic_fetch_add(&ended,1);return inflateEnd(s);}\n'
            'static int test_join(pthread_t t,void**p){int r=pthread_join(t,p);'
            'if(!r)atomic_fetch_add(&joined,1);return r;}\n'
            'int test_initialized(void){return initialized;}\nint test_ended(void){return ended;}\n'
            'int test_joined(void){return joined;}\n')
        library = Path(self.folder.name) / 'failing-reset.so'
        sdk = ['-isysroot', subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()] if sys.platform == 'darwin' else []
        subprocess.run([compiler,*sdk,'-std=c11','-O2','-dynamiclib' if sys.platform == 'darwin' else '-shared',
                        '-fPIC',str(wrapper),'-o',str(library),'-lz','-pthread'],check=True,capture_output=True)
        helper = ctypes.CDLL(str(library))
        helper.disco_trace_extract_v1.argtypes = self.helper.disco_trace_extract_v1.argtypes
        helper.disco_trace_extract_v1.restype = ctypes.c_int
        self.create()
        with patch.object(native, '_load_helper', return_value=helper), patch.object(native, '_NATIVE_WORKERS', 4):
            with self.assertRaisesRegex(ValueError, 'failed exact decompression'):
                self.read_values()
        self.assertEqual(helper.test_initialized(), 4)
        self.assertEqual(helper.test_ended(), 4)
        self.assertEqual(helper.test_joined(), 4)
        self.assertTrue(native._NATIVE_SLOT.acquire(blocking=False))
        native._NATIVE_SLOT.release()

    def test_old_abi_falls_back_before_raw_io_or_decoder_resolution(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        self.create()
        self.loader.stop()
        native._load_helper.cache_clear()
        try:
            old = SimpleNamespace(disco_trace_inflate_abi=Mock(return_value=3))
            with patch.object(native.ctypes, 'CDLL', return_value=old), \
                 patch.object(native.os, 'pread', side_effect=AssertionError('No raw I/O')):
                self.assertIsNone(self.read())
                old.disco_trace_inflate_abi.assert_called_once_with()
        finally:
            native._load_helper.cache_clear()

    def test_helper_absence_and_busy_slot_fall_back(self):
        self.create()
        with patch.object(native, '_load_helper', return_value=None):
            self.assertIsNone(self.read())
        native._NATIVE_SLOT.acquire()
        try:
            self.assertIsNone(self.read())
        finally:
            native._NATIVE_SLOT.release()

    def test_physical_overlap_and_caps_are_checked_before_read(self):
        from types import SimpleNamespace as Chunk
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            native._chunk_spans([Chunk(byte_offset=100,size=20),Chunk(byte_offset=110,size=20)], 1000)
        self.assertIsNone(native._chunk_spans([Chunk(byte_offset=0,size=native.MAX_SPAN_BYTES+1)], 10000000))
        infos = [Chunk(byte_offset=i*6000000,size=native.MAX_SPAN_BYTES) for i in range(9)]
        self.assertIsNone(native._chunk_spans(infos,100000000))

    def test_native_abi_refuses_invalid_bounds_and_does_not_publish_partial_output(self):
        compressed = zlib.compress(self.values(64).tobytes())
        offsets = np.array([0], dtype='u8'); sizes = np.array([len(compressed)], dtype='u8')
        out = np.empty(1152, dtype='u1')
        def call(**kw):
            args = dict(input_size=len(compressed), count=1, output_size=1152, chunk_size=1152, workers=4)
            args.update(kw)
            return self.helper.disco_trace_inflate_v1(compressed,args['input_size'],offsets.ctypes.data,
                sizes.ctypes.data,args['count'],out.ctypes.data,args['output_size'],args['chunk_size'],args['workers'])
        self.assertEqual(call(), 0)
        for kwargs in (dict(count=0),dict(count=15626),dict(output_size=1151),dict(chunk_size=18),
                       dict(workers=0),dict(workers=9),dict(input_size=33*1024*1024)):
            self.assertEqual(call(**kwargs), -1)
        offsets[0] = len(compressed)+1
        self.assertEqual(call(), -1)


    def read_values(self, begin=0, end=None, units='pA'):
        with h5py.File(self.path, 'r') as h5:
            data = h5['data']
            return native.read_native_values(data, self.signature(), begin,
                len(data) if end is None else end, units)

    def test_fused_values_preserve_bits_partial_chunks_and_only_requested_validation(self):
        values = self.create()
        for workers in (1, 2, 4, 8):
            for begin, end in ((0, len(values)), (1, 1024), (63, 129), (1024, 1025)):
                with self.subTest(workers=workers, begin=begin, end=end), patch.object(native, '_NATIVE_WORKERS', workers):
                    actual = self.read_values(begin, end)
                    self.assertEqual(actual.dtype, np.dtype('<f8'))
                    self.assertTrue(actual.flags.owndata)
                    self.assertEqual(actual.tobytes(), values['quantity'][begin:end].tobytes())
        values['units'][70] = b'mV'
        values['quantity'][80] = float('nan')
        self.create(values)
        self.assertEqual(self.read_values(0, 64).tobytes(), values['quantity'][:64].tobytes())
        with self.assertRaisesRegex(ValueError, 'units are inconsistent'):
            self.read_values(64, 80)
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            self.read_values(80, 81)

    def test_fused_units_never_truncate_and_match_h5_nullterm(self):
        self.create()
        with patch.object(native.os, 'pread', side_effect=AssertionError('No raw I/O')):
            self.assertIsNone(self.read_values(units='pA' + 'x' * 10))
        # Reuse the adversarial NULLTERM fixture: only the requested record is validated.
        self.test_nullterm_units_match_h5_conversion_including_embedded_null_and_full_width()
        self.assertEqual(self.read_values(0, 1).tobytes(), self.values(64)['quantity'][:1].tobytes())
        self.assertEqual(len(self.read_values(1, 2, 'abcdefghij')), 1)
        self.assertEqual(len(self.read_values(2, 3, '')), 1)
        with self.assertRaisesRegex(ValueError, 'units are inconsistent'):
            self.read_values(4, 5)
        self.assertEqual(len(self.read_values(5, 6)), 1)
        values = self.values(64)
        values['units'][0] = b'pA\0garbage'
        self.create(values)
        with self.assertRaisesRegex(ValueError, 'units are inconsistent'):
            self.read_values(0, 1)

    def test_fused_corrupt_streams_source_changes_and_busy_slot_do_not_publish(self):
        values = self.values(64)
        original = zlib.compress(values.tobytes())
        for chunk in (b'invalid zlib', original[:-1], original + b'extra', zlib.compress(b'wrong size')):
            with self.subTest(length=len(chunk)):
                with h5py.File(self.path, 'w') as h5:
                    d = h5.create_dataset('data', shape=(64,), dtype=values.dtype, chunks=(64,), compression='gzip')
                    d.id.write_direct_chunk((0,), chunk)
                with self.assertRaisesRegex(ValueError, 'decompression'):
                    self.read_values()
        self.create()
        original_read = os.pread
        def mutate(fd, length, offset):
            block = original_read(fd, length, offset)
            stat = self.path.stat()
            os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
            return block
        with patch.object(native.os, 'pread', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed while'):
                self.read_values()
        native._NATIVE_SLOT.acquire()
        try:
            self.assertIsNone(self.read_values())
        finally:
            native._NATIVE_SLOT.release()

    def test_exact_m4_fractional_bins_point_bits_and_signed_zero_statistics(self):
        raw = np.zeros(64, dtype='<f8')
        raw[[13, 39, 60]] = -2
        raw[[14, 40, 61]] = 3
        raw[0] = -0.
        expected = np.array([0, 13, 14, 27, 28, 39, 40, 55, 56, 60, 61, 63], dtype='<u4')
        indices, selected, low, high = native.reduce_native_display(raw, 2.25)
        self.assertEqual(indices.tobytes(), expected.tobytes())
        self.assertEqual(selected.tobytes(), raw[expected].tobytes())
        self.assertEqual((low, high), (-2., 3.))
        for raw in (np.array([0., -0.]), np.array([-0., 0.]), np.array([-0.])):
            indices, selected, low, high = native.reduce_native_display(raw, 1.)
            self.assertEqual(indices.tolist(), list(range(len(raw))))
            self.assertEqual(selected.tobytes(), raw.tobytes())
            self.assertTrue(np.signbit(low))
            self.assertEqual(bool(np.signbit(high)), len(raw) == 1)
        # Constant/tied bins retain first and last, never duplicate candidates.
        indices, _, _, _ = native.reduce_native_display(np.ones(64), 2.25)
        self.assertEqual(indices.tolist(), [0, 27, 28, 55, 56, 63])

    def test_m4_input_bounds_missing_helper_and_native_failure_are_distinct(self):
        raw = np.arange(16, dtype='<f8')
        for invalid in (0, -1, float('nan'), float('inf'), 16385, True):
            with self.subTest(width=invalid), self.assertRaises(ValueError):
                native.reduce_native_display(raw, invalid)
        for invalid in (np.array([],dtype='<f8'), raw[::2], raw.astype('<f4'), raw.reshape(4,4)):
            with self.assertRaises(ValueError):
                native.reduce_native_display(invalid, 10.)
        with patch.object(native, '_load_helper', return_value=None):
            self.assertIsNone(native.reduce_native_display(raw, 10.))
        raw[4] = float('nan')
        with self.assertRaisesRegex(ValueError, 'geometry failed'):
            native.reduce_native_display(raw, 10.)

    def test_fused_native_abi_rejects_bounds_before_output(self):
        compressed = zlib.compress(self.values(64).tobytes())
        offsets = np.array([0], dtype='u8'); sizes = np.array([len(compressed)], dtype='u8')
        output = np.empty(64, dtype='<f8')
        def call(**kw):
            args = dict(count=1, begin=0, end=64, size=512, nullterm=0, workers=4)
            args.update(kw)
            return self.helper.disco_trace_extract_v1(compressed, len(compressed), offsets.ctypes.data,
                sizes.ctypes.data, args['count'], output.ctypes.data, args['size'], args['begin'],
                args['end'], b'pA' + b'\0' * 8, args['nullterm'], args['workers'])
        self.assertEqual(call(), 0)
        for kwargs in (dict(count=0), dict(count=15626), dict(begin=64), dict(end=65),
                       dict(size=511), dict(nullterm=2), dict(workers=0), dict(workers=9)):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(call(**kwargs), -1)
