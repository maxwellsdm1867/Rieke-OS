"""Exact optional parallel geometry and shared worker-budget failure semantics."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import workspace_trace_native as native


class ParallelM4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('cc')
        if compiler is None or sys.platform not in ('darwin', 'linux'):
            raise unittest.SkipTest('Native fixture requires a macOS/Linux compiler')
        cls.build = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build.cleanup)
        folder = Path(cls.build.name)
        source = Path(__file__).resolve().parents[2] / 'desktop/native/trace_inflate.c'
        fault = folder / 'fault.c'
        fault.write_text('''#include <stdlib.h>
#include <pthread.h>
#include <errno.h>
static int fail_thread=-1, started=0, joined=0, fail_allocation=-1, allocations=0;
void fixture_failures(int t,int a) {fail_thread=t;started=joined=0;fail_allocation=a;allocations=0;}
int fixture_started(void) {return started;}
int fixture_joined(void) {return joined;}
static void *fixture_malloc(size_t size) {
 if(allocations++==fail_allocation)return NULL;
 return malloc(size);
}
static int fixture_create(pthread_t *t,const pthread_attr_t *a,void *(*fn)(void *),void *arg) {
 if(started==fail_thread)return EAGAIN;
 int rc=pthread_create(t,a,fn,arg);if(!rc)++started;return rc;
}
static int fixture_join(pthread_t t,void **result) {
 int rc=pthread_join(t,result);if(!rc)++joined;return rc;
}
#define malloc fixture_malloc
#define pthread_create fixture_create
#define pthread_join fixture_join
''' + '#include "' + str(source).replace('\\', '\\\\').replace('"', '\\"') + '"\n')
        def build(path, name):
            library = folder / name
            subprocess.run([compiler, '-O3', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fno-fast-math', '-ffp-contract=off', '-fPIC',
                '-dynamiclib' if sys.platform == 'darwin' else '-shared',
                str(path), '-o', str(library), '-lz', '-lm', '-pthread'], check=True)
            helper = ctypes.CDLL(str(library))
            helper.disco_trace_m4_v1.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double,
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            helper.disco_trace_m4_v1.restype = ctypes.c_int
            if native._parallel_m4(helper) is None:
                raise AssertionError('Parallel feature missing from fixture build')
            return helper
        cls.helper = build(source, 'helper.so')
        cls.fault = build(fault, 'fault.so')
        cls.fault.fixture_failures.argtypes = [ctypes.c_int, ctypes.c_int]

    def setUp(self):
        native._parallel_m4.cache_clear()
        self.addCleanup(native._parallel_m4.cache_clear)

    @staticmethod
    def oracle(raw, width):
        count, columns = len(raw), int(np.ceil(width))
        if count <= 4 * columns:
            indices = np.arange(count, dtype='<u4')
        else:
            bins = np.minimum(columns - 1, np.floor(np.arange(count, dtype='f8') / (count - 1) * width))
            starts = np.r_[0, np.flatnonzero(bins[1:] != bins[:-1]) + 1]
            ends = np.r_[starts[1:], count]
            chosen = []
            for begin, end in zip(starts, ends):
                part = raw[begin:end]
                chosen.extend(sorted({int(begin), int(end - 1),
                    int(begin + part.argmin()), int(begin + part.argmax())}))
            indices = np.array(chosen, dtype='<u4')
        low, high = float(raw.min()), float(raw.max())
        if low == 0 and np.any((raw == 0) & np.signbit(raw)): low = -0.
        if high == 0 and np.any((raw == 0) & ~np.signbit(raw)): high = 0.
        return indices.tobytes(), raw[indices].tobytes(), np.array([low, high], dtype='<f8').tobytes()

    def call(self, raw, width, workers, helper=None, capacity=None, count=None):
        helper = helper or self.helper
        expected_capacity = min(len(raw), 4 * int(np.ceil(width)))
        capacity = expected_capacity if capacity is None else capacity
        indices = np.full(expected_capacity + 8, 0xDEADBEEF, dtype='<u4')
        values = np.full(expected_capacity + 8, 123.25, dtype='<f8')
        written, low, high = ctypes.c_size_t(1234), ctypes.c_double(123), ctypes.c_double(456)
        before = raw.tobytes()
        status = native._parallel_m4(helper)(raw.ctypes.data, len(raw) if count is None else count,
            width, indices.ctypes.data, values.ctypes.data, capacity,
            ctypes.byref(written), ctypes.byref(low), ctypes.byref(high), workers)
        self.assertEqual(raw.tobytes(), before)
        if status:
            self.assertEqual((written.value, low.value, high.value), (1234, 123, 456))
            self.assertTrue(np.all(indices == 0xDEADBEEF) and np.all(values == 123.25))
            return status, None
        self.assertLessEqual(written.value, expected_capacity)
        self.assertTrue(np.all(indices[expected_capacity:] == 0xDEADBEEF) and
                        np.all(values[expected_capacity:] == 123.25))
        return status, (indices[:written.value].tobytes(), values[:written.value].tobytes(),
                        np.array([low.value, high.value], dtype='<f8').tobytes())

    def test_exact_raw_mode_bins_ties_signed_zero_and_fractional_boundaries(self):
        for count in (1, 64, 65, 513, 4097, 65537):
            tied = np.resize(np.array([-0., 0., -3., -3., 5., 5., 5e-324, -5e-324]), count)
            for raw in (tied, np.zeros(count), np.full(count, -0.)):
                for width in (.125, 1., 2.25, float(np.nextafter(7., 0.)), 7.,
                              float(np.nextafter(7., np.inf)), 751., 16384.):
                    expected = self.oracle(raw, width)
                    for workers in (1, 2, 4, 8):
                        with self.subTest(count=count, width=width, workers=workers):
                            self.assertEqual(self.call(raw, width, workers), (0, expected))

    def test_nonfinite_and_bounds_leave_all_outputs_unpublished(self):
        for count, width in ((1, 1.), (64, 32.), (4097, 31.)):
            for position in {0, count // 2, count - 1}:
                for value in (float('nan'), float('inf'), -float('inf')):
                    raw = np.zeros(count)
                    raw[position] = value
                    self.assertEqual(self.call(raw, width, 8)[0], -5)
        raw = np.zeros(4097)
        for workers in (0, 9): self.assertEqual(self.call(raw, 31., workers)[0], -1)
        for count in (0, 1000001): self.assertEqual(self.call(raw, 31., 8, count=count)[0], -1)
        self.assertEqual(self.call(raw, 31., 8, capacity=123)[0], -1)

    def test_allocation_and_partial_thread_creation_failures_join_before_return(self):
        raw = np.zeros(4097)
        for started in (0, 1, 3, 7):
            self.fault.fixture_failures(started, -1)
            self.assertEqual(self.call(raw, 31., 8, self.fault)[0], -3)
            self.assertEqual((self.fault.fixture_started(), self.fault.fixture_joined()), (started, started))
        for allocation in (0, 1, 2):
            self.fault.fixture_failures(-1, allocation)
            self.assertEqual(self.call(raw, 31., 8, self.fault)[0], -3)
            self.assertEqual(self.fault.fixture_started(), 0)

    def test_python_threshold_worker_caps_and_shared_busy_slot(self):
        parallel = native._parallel_m4(self.helper)
        calls = []
        def observed(*arguments):
            calls.append(arguments[-1])
            acquired = native._NATIVE_SLOT.acquire(blocking=False)
            if acquired: native._NATIVE_SLOT.release()
            self.assertFalse(acquired)
            return parallel(*arguments)
        with patch.object(native, '_load_helper', return_value=self.helper), \
                patch.object(native, '_parallel_m4', return_value=observed), \
                patch.object(native, '_NATIVE_WORKERS', 8):
            for count, expected_workers in ((299999, None), (300000, 4), (499999, 4), (500000, 8)):
                raw = np.resize(np.array([-0., 0., -3., 5., 5.]), count)
                before = len(calls)
                indices, values, low, high = native.reduce_native_display(raw, 751.)
                self.assertEqual((indices.tobytes(), values.tobytes(),
                    np.array([low, high], dtype='<f8').tobytes()), self.oracle(raw, 751.))
                self.assertEqual(calls[before:], [] if expected_workers is None else [expected_workers])
            raw = np.zeros(300000)
            native._NATIVE_SLOT.acquire()
            try:
                before = len(calls)
                native.reduce_native_display(raw, 751.)
                self.assertEqual(len(calls), before)
            finally:
                native._NATIVE_SLOT.release()
            for workers, width, expected in ((2, 751., [2]), (1, 751., []), (8, 1., [])):
                before = len(calls)
                with patch.object(native, '_NATIVE_WORKERS', workers):
                    native.reduce_native_display(raw, width)
                self.assertEqual(calls[before:], expected)
        self.assertTrue(native._NATIVE_SLOT.acquire(blocking=False))
        native._NATIVE_SLOT.release()

    def test_missing_optional_feature_uses_serial_and_invoked_errors_release_slot(self):
        helper = self.helper
        class OldHelper:
            def __getattr__(self, name):
                if name.startswith('disco_trace_m4_parallel_'): raise AttributeError(name)
                return getattr(helper, name)
        raw = np.zeros(300000)
        old = OldHelper()
        self.assertIsNone(native._parallel_m4(old))
        with patch.object(native, '_load_helper', return_value=old):
            result = native.reduce_native_display(raw, 751.)
            self.assertEqual(result[0].tobytes(), self.oracle(raw, 751.)[0])
        for failure in (-3, RuntimeError('Injected native-call exception')):
            def failed(*arguments):
                if isinstance(failure, Exception): raise failure
                return failure
            class NoSerial:
                def disco_trace_m4_v1(self, *arguments):
                    raise AssertionError('No serial retry after invocation')
            with patch.object(native, '_load_helper', return_value=NoSerial()), \
                    patch.object(native, '_parallel_m4', return_value=failed), \
                    patch.object(native, '_NATIVE_WORKERS', 8):
                with self.assertRaises((ValueError, RuntimeError)):
                    native.reduce_native_display(raw, 751.)
            self.assertTrue(native._NATIVE_SLOT.acquire(blocking=False))
            native._NATIVE_SLOT.release()
