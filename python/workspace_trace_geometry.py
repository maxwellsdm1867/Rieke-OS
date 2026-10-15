"""Screen geometry from admitted exact samples; never raw samples or authority.

The whole-auto view uses the same first/min/max/last indices as Canvas. Source
admission and closing checks belong to the route; this module owns reduction
and the distinct bounded wire representation only.
"""
import json
import math
import re
import struct
import uuid

MAX_SAMPLES = 1000000
MAX_WIDTH = 16384
MAX_HEADER_BYTES = 65536
CONTENT_TYPE = 'application/vnd.disco.trace-m4le.v1'
MAGIC = b'DTM1'
ALGORITHM = 'first-last-extrema-v1'
_IDENTITY = ('epoch_uuid', 'stream_uuid', 'source_sha256', 'sample_rate', 'units', 'total_samples')
_CONTEXT = {'kind', 'token', 'project_uuid', 'publication_revision', 'view_kind',
            'protocol_uuid', 'candidate_revision_uuid', 'membership_sha256'}


class GeometryUnavailable(ValueError):
    pass


def _valid_width(width):
    return type(width) in (int, float) and math.isfinite(width) and 0 < width <= MAX_WIDTH


def _uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _fallback_reduce(values, width):
    """Portable finite-only oracle, used when the optional native helper is absent."""
    import numpy as np
    count, columns = len(values), math.ceil(width)
    if not np.isfinite(values).all():
        raise ValueError('Display geometry requires finite samples')
    # Preserve JavaScript's divide-then-multiply bin expression, including its
    # floating boundary behavior. Arrays are bounded by MAX_SAMPLES.
    bins = np.minimum(columns - 1, np.floor(np.arange(count, dtype='f8') / (count - 1) * width))
    starts = np.r_[0, np.flatnonzero(bins[1:] != bins[:-1]) + 1]
    ends = np.r_[starts[1:], count]
    chosen = []
    for begin, end in zip(starts, ends):
        part = values[begin:end]
        chosen.extend(sorted({int(begin), int(end - 1), int(begin + part.argmin()), int(begin + part.argmax())}))
    indices = np.array(chosen, dtype='<u4')
    low, high = float(values.min()), float(values.max())
    # np.min/max do not specify the signed-zero tie rule of Math.min/max.
    if low == 0 and np.any((values == 0) & np.signbit(values)):
        low = -0.0
    if high == 0 and np.any((values == 0) & ~np.signbit(values)):
        high = 0.0
    return indices, values[indices].copy(), low, high


def _complete_bin_shape(indices, count, width):
    """Prove known first/last coverage without inspecting any original samples."""
    import numpy as np
    columns = math.ceil(width)
    targets = np.arange(columns, dtype='i8')
    low, high = np.zeros(columns, dtype='i8'), np.full(columns, count, dtype='i8')
    # Vectorized monotone search uses the exact painter expression, not an
    # algebraically rearranged boundary that can round to another sample.
    while np.any(low < high):
        middle = (low + high) // 2
        bins = np.minimum(columns - 1, np.floor(middle / (count - 1) * width))
        before = bins < targets
        low = np.where(before, middle + 1, low)
        high = np.where(before, high, middle)
    ends = np.r_[low[1:] - 1, count - 1]
    bins = np.minimum(columns - 1, np.floor(indices.astype('f8') / (count - 1) * width))
    occupied, sizes = np.unique(bins, return_counts=True)
    return (np.array_equal(occupied, targets) and bool(np.all(sizes <= 4)) and
            bool(np.isin(np.r_[low, ends], indices).all()))


def prepare_display_geometry(batch, physical_width):
    """Reduce one complete exact stream, before the caller's closing witness."""
    import numpy as np
    if not _valid_width(physical_width):
        raise ValueError('Invalid display width')
    count = batch.get('count') if isinstance(batch, dict) else None
    windows = batch.get('windows') if isinstance(batch, dict) else None
    if (type(count) is not int or not 0 < count <= MAX_SAMPLES or batch.get('start') != 0 or
            batch.get('total_samples') != count or batch.get('decimated') is not False or
            not isinstance(windows, list) or not 1 <= len(windows) <= 10):
        raise ValueError('Display geometry requires one complete bounded exact stream')
    if count <= 4 * math.ceil(physical_width):
        raise GeometryUnavailable('This display does not need screen-column reduction')
    parts, start = [], 0
    for window in windows:
        values = window.get('values') if isinstance(window, dict) else None
        if (type(values) is not np.ndarray or values.ndim != 1 or values.dtype.kind != 'f' or
                values.dtype.itemsize != 8 or not 0 < len(values) <= 100000 or
                window.get('start') != start or window.get('count') != len(values) or
                window.get('decimated') is not False or
                any(window.get(key) != batch.get(key) for key in _IDENTITY)):
            raise ValueError('Display geometry received inconsistent sample windows')
        parts.append(values)
        start += len(values)
    if start != count:
        raise ValueError('Display geometry sample coverage is incomplete')
    values = np.concatenate(parts).astype('<f8', copy=False)
    from workspace_trace_native import reduce_native_display
    reduced = reduce_native_display(values, physical_width)
    indices, selected, low, high = reduced if reduced is not None else _fallback_reduce(values, physical_width)
    return {**{key: batch[key] for key in _IDENTITY},
            'representation': 'm4_geometry', 'algorithm': ALGORITHM,
            'raw_start': 0, 'raw_count': count, 'physical_width': physical_width,
            'point_count': len(indices), 'indices': indices, 'point_values': selected,
            'statistics': {'min': low, 'max': high, 'finiteCount': count, 'missingCount': 0}}


def encode_display_geometry(geometry, *, dumps=json.dumps):
    """DTM1 + JSON length/header/pad8 + u32 indices/pad8 + exact f64 values."""
    import numpy as np
    g = geometry
    expected = set(_IDENTITY) | {'representation', 'algorithm', 'raw_start', 'raw_count',
        'physical_width', 'point_count', 'indices', 'point_values', 'statistics', 'read_context'}
    if not isinstance(g, dict) or set(g) != expected:
        raise ValueError('Malformed display geometry')
    indices, values, stats, context = (g.get(key) for key in ('indices', 'point_values', 'statistics', 'read_context'))
    count, points, width = (g.get(key) for key in ('raw_count', 'point_count', 'physical_width'))
    if (g.get('representation') != 'm4_geometry' or g.get('algorithm') != ALGORITHM or
            type(count) is not int or not 0 < count <= MAX_SAMPLES or type(g.get('raw_start')) is not int or g['raw_start'] != 0 or
            type(g.get('total_samples')) is not int or g['total_samples'] != count or not _valid_width(width) or
            count <= 4 * math.ceil(width) or
            type(points) is not int or not 2 <= points <= min(count, 4 * math.ceil(width)) or
            type(indices) is not np.ndarray or indices.ndim != 1 or indices.dtype.kind != 'u' or indices.dtype.itemsize != 4 or
            type(values) is not np.ndarray or values.ndim != 1 or values.dtype.kind != 'f' or values.dtype.itemsize != 8 or
            len(indices) != points or len(values) != points or indices[0] != 0 or indices[-1] != count - 1 or
            not np.all(indices[1:] > indices[:-1]) or not np.isfinite(values).all() or
            not isinstance(stats, dict) or set(stats) != {'min', 'max', 'finiteCount', 'missingCount'} or
            type(stats['finiteCount']) is not int or stats['finiteCount'] != count or
            type(stats['missingCount']) is not int or stats['missingCount'] != 0 or
            any(type(stats[k]) not in (int, float) or not math.isfinite(stats[k]) for k in ('min', 'max')) or
            stats['min'] != float(values.min()) or stats['max'] != float(values.max()) or
            not _uuid(g.get('epoch_uuid')) or not _uuid(g.get('stream_uuid')) or not _sha(g.get('source_sha256')) or
            type(g.get('sample_rate')) not in (int, float) or not math.isfinite(g['sample_rate']) or g['sample_rate'] <= 0 or
            not isinstance(g.get('units'), str) or not isinstance(context, dict) or set(context) != _CONTEXT or
            context['kind'] != 'prepared_display' or context['view_kind'] not in ('workbench_pending', 'workbench_selected') or
            not all(_uuid(context[key]) for key in ('token', 'project_uuid', 'publication_revision', 'protocol_uuid', 'candidate_revision_uuid')) or
            not _sha(context['membership_sha256']) or 'decimated' in g or 'values' in g):
        raise ValueError('Malformed display geometry')
    if not _complete_bin_shape(indices, count, width):
        raise ValueError('Display geometry omits required screen-column endpoints')
    header = {key: value for key, value in g.items() if key not in ('indices', 'point_values')}
    encoded = dumps(header, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(encoded) > MAX_HEADER_BYTES:
        raise ValueError('Display geometry metadata exceeds its bounded header')
    index_bytes = indices.astype('<u4', copy=False).tobytes()
    return b''.join((struct.pack('<4sI', MAGIC, len(encoded)), encoded,
                     bytes(-(8 + len(encoded)) % 8), index_bytes, bytes(-len(index_bytes) % 8),
                     values.astype('<f8', copy=False).tobytes()))
