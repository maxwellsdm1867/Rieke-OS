"""Request-local diagnostic ownership; no recordings or runtime mutation."""
from contextvars import copy_context
import math
import threading
import unittest
from unittest.mock import patch

import workspace_trace_native as native


class NativeTimingTests(unittest.TestCase):
    def test_disabled_capture_never_reads_clocks_or_registers_callback(self):
        before = list(native.gc.callbacks)
        with patch.object(native._NativeTiming, 'clock', side_effect=AssertionError('disabled clock')):
            with native.capture_native_timing(None) as result:
                self.assertIsNone(result)
                self.assertEqual(native.gc.callbacks, before)
        self.assertIsNone(native._NATIVE_TIMING.get())

    def test_stages_and_gc_are_bounded_and_numeric(self):
        timing = {}
        before = list(native.gc.callbacks)
        with native.capture_native_timing(timing) as capture:
            capture.mark('enumeration')
            for _ in range(100):
                capture.gc_event('start', {'generation': 1})
                capture.gc_event('stop', {'generation': 1})
                capture.mark('enumeration')
            capture.mark(None)
            with self.assertRaises(ValueError): capture.mark('untrusted label')
            with self.assertRaises(ValueError): capture.count('file_path', 1)
            with self.assertRaises(ValueError): capture.count('chunks', True)
        self.assertEqual(native.gc.callbacks, before)
        self.assertGreaterEqual(timing['_native_counts']['gc1'], 100)
        self.assertIn('native_enumeration_gc_wall', timing)
        self.assertLessEqual(set(timing) - {'_native_counts'}, set(native.NATIVE_TIMING_METRICS))
        self.assertTrue(all(type(value) is float and math.isfinite(value) and value >= 0
                            for key, value in timing.items() if key != '_native_counts'))

    def test_thread_context_and_nested_capture_do_not_steal_gc_attribution(self):
        outer, inner, worker = {}, {}, {}
        callbacks = list(native.gc.callbacks)
        errors = []
        with native.capture_native_timing(outer) as first:
            first.mark('map')
            prior = first.counts['gc2']
            with native.capture_native_timing(inner) as second:
                first.gc_event('start', {'generation': 2})
                first.gc_event('stop', {'generation': 2})
                second.gc_event('start', {'generation': 1})
                second.gc_event('stop', {'generation': 1})
            self.assertEqual(first.counts['gc2'], prior)
            self.assertIs(native._NATIVE_TIMING.get(), first)
            def run():
                try:
                    self.assertIsNone(native._NATIVE_TIMING.get())
                    with native.capture_native_timing(worker) as third:
                        first.gc_event('start', {'generation': 2})
                        first.gc_event('stop', {'generation': 2})
                        third.gc_event('start', {'generation': 0})
                        third.gc_event('stop', {'generation': 0})
                    self.assertIsNone(native._NATIVE_TIMING.get())
                except BaseException as error: errors.append(error)
            thread = threading.Thread(target=run); thread.start(); thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(first.counts['gc2'], prior)
        self.assertEqual(native.gc.callbacks, callbacks)
        self.assertGreaterEqual(inner['_native_counts']['gc1'], 1)
        self.assertGreaterEqual(worker['_native_counts']['gc0'], 1)
        self.assertIsNone(native._NATIVE_TIMING.get())

    def test_copied_context_cannot_transfer_thread_cpu_or_stage_ownership(self):
        import numpy as np
        timing, errors = {}, []
        values = np.ones(4, dtype='<f8')
        with native.capture_native_timing(timing):
            context = copy_context()
            def run():
                try:
                    self.assertIsNone(native._current_native_timing())
                    self.assertIsNone(native.reduce_native_display(values, 1.))
                except BaseException as error: errors.append(error)
            with patch.object(native, '_load_helper', return_value=None):
                thread = threading.Thread(target=lambda: context.run(run))
                thread.start(); thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
        self.assertNotIn('native_reduce_setup_wall', timing)
        self.assertIn('native_scope_wall', timing)

    def test_exception_retires_only_owned_callback_and_restores_context(self):
        callbacks = list(native.gc.callbacks)
        timing = {}
        with self.assertRaisesRegex(RuntimeError, 'original failure'):
            with native.capture_native_timing(timing) as capture:
                capture.mark('extract')
                native.gc.callbacks.remove(capture.callback)
                raise RuntimeError('original failure')
        self.assertEqual(native.gc.callbacks, callbacks)
        self.assertIsNone(native._NATIVE_TIMING.get())
        self.assertIn('native_extract_wall', timing)
        self.assertIn('native_scope_wall', timing)


if __name__ == '__main__': unittest.main()
