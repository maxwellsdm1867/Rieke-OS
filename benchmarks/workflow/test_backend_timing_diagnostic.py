"""Lightweight passive-GC attribution checks; no collections or benchmark jobs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('diagnostic_backend_timing', Path(__file__).with_name('backend_timing.py'))
owner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(owner)


class GcDiagnosticTests(unittest.TestCase):
    def test_generation_interval_and_request_cpu_are_separate(self):
        clocks = iter([(1., 2., 3.), (1.01, 2.002, 3.003), (1.16, 2.102, 3.113), (1.2, 2.12, 3.14)])
        d = owner._GcDiagnostics(lambda: next(clocks)); m = d.start('request')
        d.callback('start', {'generation': 2}); d.callback('stop', {'generation': 2, 'collected': 4, 'uncollectable': 0})
        result = d.finish(m)
        self.assertAlmostEqual(result['request_wall_ms'], 200)
        self.assertAlmostEqual(result['request_thread_cpu_ms'], 120)
        self.assertAlmostEqual(result['gc_generations']['2']['wall_ms'], 150)
        self.assertAlmostEqual(result['gc_records'][0]['collector_thread_cpu_ms'], 100)
        self.assertAlmostEqual(result['gc_records'][0]['process_cpu_ms'], 110)
        self.assertTrue(result['gc_records'][0]['request_thread'])
        self.assertEqual(result['callback_errors'], 0); self.assertFalse(d.active)

    def test_other_thread_collection_is_named_and_not_request_thread_cpu(self):
        clocks = iter([(1., 1., 1.), (2., 20., 2.), (2.1, 20.05, 2.06), (3., 1.2, 3.)])
        d = owner._GcDiagnostics(lambda: next(clocks))
        with patch.object(owner.threading, 'get_ident', return_value=101): m = d.start('request')
        with patch.object(owner.threading, 'get_ident', return_value=202):
            d.callback('start', {'generation': 1}); d.callback('stop', {'generation': 1})
        result = d.finish(m); record = result['gc_records'][0]
        self.assertEqual(record['collector_thread_id'], 202); self.assertFalse(record['request_thread'])
        self.assertAlmostEqual(record['collector_thread_cpu_ms'], 50)
        self.assertAlmostEqual(result['request_thread_cpu_ms'], 200)

    def test_records_capped_but_totals_keep_every_collection(self):
        value = [0.]
        def clock(): value[0] += .001; return (value[0], value[0], value[0])
        d = owner._GcDiagnostics(clock); m = d.start('request')
        for _ in range(owner.GC_RECORD_LIMIT + 9):
            d.callback('start', {'generation': 0}); d.callback('stop', {'generation': 0})
        result = d.finish(m)
        self.assertEqual(len(result['gc_records']), owner.GC_RECORD_LIMIT)
        self.assertEqual(result['gc_records_dropped'], 9)
        self.assertEqual(result['gc_generations']['0']['collections'], owner.GC_RECORD_LIMIT + 9)

    def test_unfinished_collection_and_callback_error_are_explicit(self):
        d = owner._GcDiagnostics(); m = d.start('request')
        d.callback('start', {})
        d.callback('start', {'generation': 2})
        result = d.finish(m)
        self.assertEqual(result['callback_errors'], 1)
        self.assertEqual(result['gc_inflight_at_finish'][0]['generation'], 2)
        self.assertEqual(result['gc_generations']['2']['collections'], 0)
        d.callback('stop', {'generation': 2})
        self.assertEqual(result['gc_generations']['2']['collections'], 0, 'saved snapshot cannot mutate later')
        d.close(); self.assertFalse(d.pending)

    def test_discard_and_close_retire_request_ownership(self):
        d = owner._GcDiagnostics(); m = d.start('request'); d.discard(m)
        d.callback('start', {'generation': 0}); self.assertFalse(d.pending)
        d.start('next'); d.close(); self.assertFalse(d.active)

    def test_install_and_restore_preserve_callbacks_and_gc_policy(self):
        from flask import Flask
        import h5py  # Import before asserting no policy calls during instrumentation.
        app = Flask(__name__); app.add_url_rule('/value', view_func=lambda: {'ok': True})
        original = list(owner.gc.callbacks)
        forbidden = ['collect', 'disable', 'enable', 'freeze', 'unfreeze', 'set_threshold', 'get_objects']
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            for name in forbidden: stack.enter_context(patch.object(owner.gc, name, side_effect=AssertionError(name)))
            restore = owner.install(app, directory, Path(__file__).resolve().parents[2])
            try:
                self.assertEqual(len(owner.gc.callbacks), len(original) + 1)
                response = app.test_client().get('/value'); self.assertEqual(response.status_code, 200)
                row = json.loads((Path(directory) / 'requests.jsonl').read_text())
                self.assertTrue(row['gc_diagnostic']['diagnostic_only'])
                self.assertGreaterEqual(row['gc_diagnostic']['request_thread_cpu_ms'], 0)
                self.assertEqual(row['gc_diagnostic']['callback_errors'], 0)
            finally: restore()
            self.assertEqual(owner.gc.callbacks, original)
            restore(); self.assertEqual(owner.gc.callbacks, original)


if __name__ == '__main__': unittest.main()
