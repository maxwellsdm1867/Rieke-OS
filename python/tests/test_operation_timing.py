"""Module-local tic/toc is opt-in and does not change operation behavior."""
import concurrent.futures
import threading
import unittest
from unittest.mock import patch

import disco.operation_timing as operation_timing
from disco.operation_timing import capture_timings, elapsed


class OperationTimingTests(unittest.TestCase):
    def test_nested_elapsed_uses_two_clock_reads_per_operation(self):
        with patch.object(operation_timing, 'perf_counter_ns', side_effect=[1_000_000, 2_000_000, 5_000_000, 9_000_000]) as clock:
            with capture_timings() as records:
                with elapsed('workbench', 'prepare'):
                    with elapsed('metadata', 'read'):
                        pass
        self.assertEqual(clock.call_count, 4)
        self.assertEqual(records, [
            {'module': 'metadata', 'operation': 'read', 'elapsed_ms': 3, 'outcome': 'ok'},
            {'module': 'workbench', 'operation': 'prepare', 'elapsed_ms': 8, 'outcome': 'ok'},
        ])

    def test_disabled_does_not_read_clock(self):
        value = object()
        def operation():
            with elapsed('metadata', 'read'):
                return value
        with patch.object(operation_timing, 'perf_counter_ns', side_effect=AssertionError('disabled clock')):
            self.assertIs(operation(), value)

    def test_error_identity_and_capture_cleanup(self):
        error = ValueError('private error details')
        with self.assertRaises(ValueError) as caught:
            with capture_timings() as records:
                with elapsed('metadata', 'read'):
                    raise error
        self.assertIs(caught.exception, error)
        self.assertEqual(records[0]['outcome'], 'error')
        self.assertNotIn('private', str(records))
        with patch.object(operation_timing, 'perf_counter_ns', side_effect=AssertionError('capture leaked')):
            with elapsed('metadata', 'read'):
                pass

    def test_concurrent_and_nested_captures_are_isolated(self):
        barrier = threading.Barrier(2)
        def worker(label):
            with capture_timings() as records:
                with elapsed(label, 'wait'):
                    barrier.wait(timeout=5)
            return records
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(worker, ['one', 'two']))
        self.assertEqual([item['module'] for item in first], ['one'])
        self.assertEqual([item['module'] for item in second], ['two'])
        with capture_timings() as outer:
            with elapsed('outer', 'first'): pass
            with capture_timings() as inner:
                with elapsed('inner', 'only'): pass
            with elapsed('outer', 'last'): pass
        self.assertEqual([item['operation'] for item in outer], ['first', 'last'])
        self.assertEqual([item['operation'] for item in inner], ['only'])


if __name__ == '__main__': unittest.main()
