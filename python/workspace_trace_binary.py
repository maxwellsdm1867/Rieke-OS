"""Lossless foreground trace-batch transport after scientific read admission.

This codec neither reads source files nor grants scope authority. Callers supply
fully detached batches only after their existing closing guards have succeeded.
"""
from array import array
import json
import math
import struct
import sys
import time

from workspace_http_boundary import browser_safe_metadata

BINARY_CONTENT_TYPE = 'application/vnd.disco.trace-f64le.v1'
MAGIC = b'DTF1'
MAX_HEADER_BYTES = 65536
MAX_SAMPLES = 1000000
_IDENTITY = ('epoch_uuid', 'stream_uuid', 'source_sha256', 'sample_rate', 'units', 'total_samples', 'decimated')


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def encode_trace_batch(batch, *, dumps=json.dumps):
    """Encode the admitted finite float64 samples without decimal conversion.

    Wire format: DTF1, uint32-LE JSON length, UTF-8 JSON, zero padding to an
    eight-byte boundary, then contiguous little-endian IEEE754 binary64 samples.
    Per-window byte offsets are relative to the sample payload, not the body.
    """
    windows = batch.get('windows') if isinstance(batch, dict) else None
    if (not isinstance(windows, list) or not 1 <= len(windows) <= 10 or
            not _integer(batch.get('start')) or not _integer(batch.get('count'), 1) or
            batch['count'] > MAX_SAMPLES or not _integer(batch.get('total_samples'), 1) or
            batch['start'] + batch['count'] > batch['total_samples'] or
            batch.get('decimated') is not False or
            type(batch.get('sample_rate')) not in (int, float) or
            not math.isfinite(batch['sample_rate']) or batch['sample_rate'] <= 0 or
            any(not isinstance(batch.get(key), str) for key in ('epoch_uuid', 'stream_uuid', 'source_sha256', 'units')) or
            'values' in batch):
        raise ValueError('Malformed exact trace batch')
    header_windows, payloads = [], []
    offset, sample_start = 0, batch['start']
    for window in windows:
        values = window.get('values') if isinstance(window, dict) else None
        import numpy as np
        is_array = type(values) is np.ndarray
        valid_values = (values.ndim == 1 and values.dtype.kind == 'f' and values.dtype.itemsize == 8
                        and bool(np.isfinite(values).all())) if is_array else (
                            isinstance(values, list) and all(type(value) is float and math.isfinite(value) for value in values))
        if (not valid_values or not _integer(window.get('count'), 1) or
                window['count'] > 100000 or len(values) != window['count'] or
                window.get('start') != sample_start or type(window.get('start')) is not int or
                not _integer(window.get('total_samples'), 1) or window.get('decimated') is not False or
                any(window.get(key) != batch[key] for key in _IDENTITY)):
            raise ValueError('Malformed exact trace batch window')
        if is_array:
            payload = values.astype('<f8', copy=False).tobytes(order='C')
        else:
            samples = array('d', values)
            if samples.itemsize != 8:
                raise ValueError('Binary64 trace transport is unavailable on this platform')
            if sys.byteorder != 'little':
                samples.byteswap()
            payload = samples.tobytes()
        header_windows.append({**{key: value for key, value in window.items() if key != 'values'},
                               'byte_offset': offset, 'byte_length': len(payload)})
        payloads.append(payload)
        offset += len(payload)
        sample_start += len(values)
    if sample_start != batch['start'] + batch['count'] or offset != batch['count'] * 8:
        raise ValueError('Trace batch windows do not cover the admitted range')
    header = {**batch, 'windows': header_windows}
    encoded = dumps(browser_safe_metadata(header), ensure_ascii=True, sort_keys=True,
                    separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(encoded) > MAX_HEADER_BYTES:
        raise ValueError('Trace binary metadata exceeds its bounded header')
    prefix = struct.pack('<4sI', MAGIC, len(encoded))
    padding = bytes(-(len(prefix) + len(encoded)) % 8)
    return b''.join((prefix, encoded, padding, *payloads))


def begin_trace_timing():
    """Opt-in elapsed wall-clock diagnostics; no clock reads on ordinary requests."""
    from flask import request
    return {'_last': time.perf_counter()} if request.headers.get('X-Disco-Trace-Timing') == '1' else None


def mark_trace_timing(timing, stage):
    if timing is not None:
        now = time.perf_counter()
        timing[stage] = (now - timing['_last']) * 1000
        timing['_last'] = now


def wants_binary_trace():
    from flask import request
    return any(media == BINARY_CONTENT_TYPE and quality > 0
               for media, quality in request.accept_mimetypes)


def read_trace_batch(service, epoch, stream, start, count, chunks, *, binary, timing=None):
    """Pass the internal array option only to the unchanged canonical method."""
    from workspace_service import _CANONICAL_TRACE_BATCH
    if getattr(service.trace_batch, '__func__', None) is _CANONICAL_TRACE_BATCH:
        return service.trace_batch(epoch, stream, start, count, chunks, array_windows=binary, timing=timing)
    if type(chunks) is not int or not 1 <= chunks <= 5:
        raise ValueError('Trace batch requires 1–5 chunks')
    return service.trace_batch(epoch, stream, start, count, chunks)


def trace_batch_response(app, batch, timing=None, *, binary=None):
    """Negotiate only explicit binary opt-in; legacy and error JSON stay intact."""
    from flask import jsonify, request
    started = time.perf_counter() if timing is not None else None
    explicit = wants_binary_trace() if binary is None else binary
    if explicit and batch.get('count', 0) > 0:
        response = app.response_class(encode_trace_batch(batch, dumps=app.json.dumps),
                                      mimetype=BINARY_CONTENT_TYPE)
    else:
        response = jsonify(batch)
    if timing is not None:
        timing['encode'] = (time.perf_counter() - started) * 1000
        response.headers['Server-Timing'] = ', '.join(
            f'trace_{stage};dur={timing[stage]:.3f}' for stage in ('open', 'capture', 'samples', 'validate', 'read', 'close', 'encode')
            if stage in timing)
    response.vary.add('Accept')
    return response
