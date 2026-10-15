"""Optional exact reader for the bounded packed-f64/S10 gzip64 H5 family.

HDF5 alone resolves metadata; native threads only inflate already-read bytes.
None means unsupported/unavailable before raw I/O. Once admitted, corruption is
an error, never a successful retry through a different reader. No sample cache.
"""
from __future__ import annotations

import ctypes
from functools import lru_cache
import os
from pathlib import Path
import threading

MIN_NATIVE_SAMPLES = 100000
MAX_SAMPLES = 1000000
MAX_CHUNKS = 15625
CHUNK_BYTES = 1152
MAX_SPAN_BYTES = 4 * 1024 * 1024
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_GAP_BYTES = 64 * 1024
_NATIVE_SLOT = threading.BoundedSemaphore(1)


@lru_cache(maxsize=1)
def _load_helper():
    """Packaged helper or explicit development build; never compile on demand."""
    runtime = os.environ.get('RIEKE_DESKTOP_RUNTIME')
    root = Path(runtime) / 'native' if runtime else Path(__file__).resolve().parents[1] / '.rieke-runtime' / 'trace-native'
    path = root / 'libdisco_trace_inflate.dylib'
    try:
        library = ctypes.CDLL(str(path))
        library.disco_trace_inflate_abi.restype = ctypes.c_uint
        if library.disco_trace_inflate_abi() != 2:
            return None
        library.disco_trace_inflate_v1.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint]
        library.disco_trace_inflate_v1.restype = ctypes.c_int
        library.disco_trace_normalize_units_v1.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        library.disco_trace_normalize_units_v1.restype = ctypes.c_int
        return library
    except (OSError, AttributeError):
        return None


def _signature_matches(stat, signature):
    fields = ((stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
              if len(signature) == 6 else (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    return tuple(signature[1:]) == fields


def _chunk_spans(infos, file_size):
    """Bound coalescing independently of physical fragmentation or total file size."""
    ordered = sorted(infos, key=lambda item: item.byte_offset)
    spans = []
    last_end = 0
    for info in ordered:
        offset, size = info.byte_offset, info.size
        if (not isinstance(offset, int) or not isinstance(size, int) or offset < 0 or size <= 0 or
                offset > file_size or size > file_size - offset or offset < last_end):
            raise ValueError('Invalid or overlapping trace chunk storage')
        end = offset + size
        if size > MAX_SPAN_BYTES:
            return None
        if spans and offset - spans[-1][1] <= MAX_GAP_BYTES and end - spans[-1][0] <= MAX_SPAN_BYTES:
            spans[-1][1] = end
            spans[-1][2].append(info)
        else:
            spans.append([offset, end, [info]])
        last_end = end
    if sum(end - start for start, end, _ in spans) > MAX_INPUT_BYTES:
        return None
    return spans


def read_native_samples(data, signature, begin, end):
    """Return owned compound samples or None for a pre-admission fallback."""
    import h5py
    import numpy as np
    dtype = np.dtype([('quantity', '<f8'), ('units', 'S10')])
    if (data.file.driver != 'sec2' or data.ndim != 1 or not 0 < len(data) <= MAX_SAMPLES or
            not 0 <= begin < end <= len(data) or end - begin < MIN_NATIVE_SAMPLES or
            data.chunks != (64,) or data.dtype != dtype or
            data.is_virtual or data.external or not hasattr(data.id, 'chunk_iter')):
        return None
    # NumPy dtype equality alone does not attest HDF5 float/string encodings.
    source_type = data.id.get_type()
    padded_type = h5py.h5t.py_create(dtype)
    nullterm_type = h5py.h5t.create(h5py.h5t.COMPOUND, 18)
    nullterm_type.insert(b'quantity', 0, padded_type.get_member_type(0))
    string_type = padded_type.get_member_type(1)
    string_type.set_strpad(h5py.h5t.STR_NULLTERM)
    nullterm_type.insert(b'units', 8, string_type)
    normalize_units = source_type.equal(nullterm_type)
    if not source_type.equal(padded_type) and not normalize_units:
        return None
    creation = data.id.get_create_plist()
    if creation.get_nfilters() != 1 or creation.get_filter(0)[0] != h5py.h5z.FILTER_DEFLATE:
        return None
    helper = _load_helper()
    if helper is None or not _NATIVE_SLOT.acquire(blocking=False):
        return None
    try:
        return _read_admitted(data, signature, begin, end, helper, dtype, normalize_units)
    finally:
        _NATIVE_SLOT.release()


def _read_admitted(data, signature, begin, end, helper, dtype, normalize_units):
    import numpy as np
    infos = []
    data.id.chunk_iter(lambda item: infos.append(item))
    total = len(data)
    expected_count = (total + 63) // 64
    if len(infos) > expected_count:
        raise ValueError('Duplicate trace chunk locations')
    logical = {}
    for info in infos:
        coordinate = info.chunk_offset
        if (len(coordinate) != 1 or type(coordinate[0]) is not int or coordinate[0] < 0 or
                coordinate[0] % 64 or coordinate[0] >= total or coordinate[0] in logical):
            raise ValueError('Invalid or duplicate trace chunk locations')
        logical[coordinate[0]] = info
    # Sparse/fill chunks and skipped filters stay with HDF5's generic semantics.
    if len(infos) != expected_count or any(info.filter_mask != 0 for info in infos):
        return None
    first, stop = begin // 64, (end + 63) // 64
    selected = [logical[index * 64] for index in range(first, stop)]
    fd = os.dup(data.file.id.get_vfd_handle())
    try:
        before = os.fstat(fd)
        if not _signature_matches(before, signature):
            raise ValueError('Source recording changed before reading trace chunks')
        # Validate the complete bounded dataset's physical map, not just this slice.
        all_spans = _chunk_spans(infos, before.st_size)
        if all_spans is None:
            return None
        spans = all_spans if first == 0 and stop == expected_count else _chunk_spans(selected, before.st_size)
        if spans is None:
            return None
        offsets = np.empty(len(selected), dtype=np.uint64)
        sizes = np.empty(len(selected), dtype=np.uint64)
        pieces, input_size = [], 0
        for low, high, items in spans:
            block = os.pread(fd, high - low, low)
            if len(block) != high - low:
                raise ValueError('Truncated trace chunk storage')
            for item in items:
                index = item.chunk_offset[0] // 64 - first
                offsets[index], sizes[index] = input_size + item.byte_offset - low, item.size
            pieces.append(block)
            input_size += len(block)
        compressed = b''.join(pieces)
        output = np.empty(len(selected) * 64, dtype=dtype)
        status = helper.disco_trace_inflate_v1(compressed, len(compressed), offsets.ctypes.data,
            sizes.ctypes.data, len(selected), output.ctypes.data, output.nbytes, CHUNK_BYTES, 4)
        if status != 0:
            raise ValueError('Trace compressed chunks failed exact decompression')
        if normalize_units and helper.disco_trace_normalize_units_v1(output.ctypes.data, output.nbytes) != 0:
            raise ValueError('Trace units failed exact H5 string conversion')
        if not _signature_matches(os.fstat(fd), signature):
            raise ValueError('Source recording changed while reading trace chunks')
        # The final allocated chunk includes padding. Never expose that padding.
        return output[begin - first * 64:end - first * 64]
    finally:
        os.close(fd)
