"""Lossless binary transport over already-admitted detached trace batches."""
import copy
import json
import math
import struct
import sys
import unittest
from unittest.mock import patch

from flask import Flask
from workspace_trace_binary import (BINARY_CONTENT_TYPE, MAGIC, MAX_HEADER_BYTES,
                                    encode_trace_batch, trace_batch_response, begin_trace_timing, mark_trace_timing)


def batch_fixture():
    common = dict(epoch_uuid='epoch', stream_uuid='stream', source_sha256='a' * 64,
                  sample_rate=10000.0, units='pA', total_samples=6, decimated=False)
    values = [[-0.0, 0.0, 1.2345678901234567], [sys.float_info.max, 5e-324, -1e-300]]
    windows = [dict(common, start=i * 3, count=3, values=items) for i, items in enumerate(values)]
    return dict(common, start=0, count=6, windows=windows,
                candidate_scope_revision='scope', query_revision='scope',
                expected_binding_version=7, generation={'source': 'fresh'}, tick=2**60)


def independent_decode(body):
    magic, length = struct.unpack('<4sI', body[:8])
    if magic != MAGIC or not 0 < length <= MAX_HEADER_BYTES:
        raise ValueError('Bad prefix')
    start = (8 + length + 7) // 8 * 8
    if any(body[8 + length:start]):
        raise ValueError('Nonzero padding')
    header = json.loads(body[8:8 + length])
    if len(body) != start + header['count'] * 8:
        raise ValueError('Wrong payload length')
    return header, struct.unpack('<' + 'd' * header['count'], body[start:])


class TraceBinaryTests(unittest.TestCase):
    def test_round_trip_preserves_every_float_bit_identity_scope_and_input(self):
        batch = batch_fixture()
        before = copy.deepcopy(batch)
        body = encode_trace_batch(batch)
        header, samples = independent_decode(body)
        expected = [value for window in batch['windows'] for value in window['values']]
        self.assertEqual(struct.pack('<6d', *samples), struct.pack('<6d', *expected))
        self.assertEqual(math.copysign(1.0, samples[0]), -1.0)
        self.assertEqual(header['tick'], str(2**60))
        for key in ('epoch_uuid', 'stream_uuid', 'source_sha256', 'candidate_scope_revision',
                    'query_revision', 'generation', 'expected_binding_version'):
            self.assertEqual(header[key], batch[key])
        self.assertEqual([window['byte_offset'] for window in header['windows']], [0, 24])
        self.assertEqual([window['byte_length'] for window in header['windows']], [24, 24])
        self.assertTrue(all('values' not in window for window in header['windows']))
        self.assertEqual(batch, before)

    def test_header_serializer_never_receives_sample_arrays(self):
        seen = []
        def dumps(header, **kwargs):
            seen.append(header)
            self.assertNotIn('values', header)
            self.assertTrue(all('values' not in window for window in header['windows']))
            return json.dumps(header, **kwargs)
        encode_trace_batch(batch_fixture(), dumps=dumps)
        self.assertEqual(len(seen), 1)

    def test_refuses_nonfinite_samples_and_malformed_batches(self):
        for value in (float('nan'), float('inf'), float('-inf'), 1, True):
            batch = batch_fixture()
            batch['windows'][0]['values'][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                encode_trace_batch(batch)
        mutations = [lambda b: b.update(count=500001), lambda b: b.update(count=5),
                     lambda b: b.update(sample_rate=float('nan')),
                     lambda b: b['windows'][1].update(start=4),
                     lambda b: b['windows'][1].update(source_sha256='different'),
                     lambda b: b['windows'][1].update(stream_uuid='other'),
                     lambda b: b['windows'][1].update(count=100001),
                     lambda b: b['windows'][1]['values'].pop(),
                     lambda b: b.update(windows=b['windows'] * 3),
                     lambda b: b.update(extra='x' * MAX_HEADER_BYTES)]
        for mutate in mutations:
            batch = batch_fixture(); mutate(batch)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                encode_trace_batch(batch)

    def test_binary_requires_nonempty_samples_but_json_eof_remains_valid(self):
        batch = batch_fixture()
        batch.update(start=6, count=0)
        batch['windows'] = [dict(batch['windows'][0], start=6, count=0, values=[])]
        with self.assertRaises(ValueError):
            encode_trace_batch(batch)
        app = Flask(__name__)
        with app.test_request_context():
            response = trace_batch_response(app, batch)
        self.assertEqual(response.get_json()['windows'][0]['values'], [])
        self.assertEqual(response.get_json()['count'], 0)

    def test_negotiation_requires_explicit_supported_accept_and_keeps_json(self):
        app = Flask(__name__)
        for accept in ('', '*/*', 'application/json', 'application/unknown', BINARY_CONTENT_TYPE + ';q=0'):
            with self.subTest(accept=accept), app.test_request_context(headers={'Accept': accept}):
                response = trace_batch_response(app, batch_fixture())
                self.assertEqual(response.mimetype, 'application/json')
                self.assertIn('values', response.get_json()['windows'][0])
                self.assertIn('Accept', response.vary)
        with app.test_request_context(headers={'Accept': BINARY_CONTENT_TYPE}):
            response = trace_batch_response(app, batch_fixture())
            self.assertEqual(response.mimetype, BINARY_CONTENT_TYPE)
            self.assertEqual(len(independent_decode(response.data)[1]), 6)
            self.assertIn('Accept', response.vary)

    def test_timing_is_opt_in_and_reports_only_fixed_elapsed_stages(self):
        app = Flask(__name__)
        with app.test_request_context(), patch('workspace_trace_binary.time.perf_counter', side_effect=AssertionError('No default clocks')):
            self.assertIsNone(begin_trace_timing())
            mark_trace_timing(None, 'open')
            response = trace_batch_response(app, batch_fixture())
            self.assertNotIn('Server-Timing', response.headers)
        with app.test_request_context(headers={'Accept': BINARY_CONTENT_TYPE, 'X-Disco-Trace-Timing': '1'}), \
                patch('workspace_trace_binary.time.perf_counter', side_effect=[1.0, 1.01, 1.03, 1.04, 1.05, 1.07]):
            timing = begin_trace_timing()
            for stage in ('open', 'read', 'close'):
                mark_trace_timing(timing, stage)
            response = trace_batch_response(app, batch_fixture(), timing)
        self.assertEqual(response.headers['Server-Timing'],
                         'trace_open;dur=10.000, trace_read;dur=20.000, trace_close;dur=10.000, trace_encode;dur=20.000')

    def test_non_binary64_platform_refuses(self):
        class WrongArray:
            itemsize = 4
        with patch('workspace_trace_binary.array', return_value=WrongArray()), self.assertRaises(ValueError):
            encode_trace_batch(batch_fixture())
