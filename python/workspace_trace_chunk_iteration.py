"""Optional metadata callback for one explicitly qualified h5py/HDF5 build.

Python owns HDF5 calls under phil; the existing helper only collects scalar chunk
metadata. Unsupported means no iteration began. An invoked iteration never retries.
No source, map or sample data is cached; cached bindings retain library handles.
"""
from __future__ import annotations

import ctypes
from functools import lru_cache
import os
from pathlib import Path
import platform
import sys

UNSUPPORTED = object()


class _Unavailable(Exception):
    pass


class _DlInfo(ctypes.Structure):
    _fields_ = [('name', ctypes.c_char_p), ('base', ctypes.c_void_p),
                ('symbol', ctypes.c_char_p), ('address', ctypes.c_void_p)]


class _Context(ctypes.Structure):
    _fields_ = [
        ('version', ctypes.c_uint64), ('capacity', ctypes.c_uint64),
        ('total', ctypes.c_uint64), ('count', ctypes.c_uint64),
        ('physical', ctypes.c_void_p), ('lengths', ctypes.c_void_p),
        ('order', ctypes.c_void_p), ('seen', ctypes.c_void_p),
        ('invalid_logical', ctypes.c_uint32), ('masked', ctypes.c_uint32),
        ('invalid_context', ctypes.c_uint32), ('reserved', ctypes.c_uint32),
    ]


def _pointer(function):
    return ctypes.cast(function, ctypes.c_void_p).value


def _qualified_private_image(root, image):
    private = (root / '.dylibs').resolve(strict=True)
    if not private.is_relative_to(root):
        raise _Unavailable('Private HDF5 directory escaped the real package')
    if (not image.is_relative_to(private) or not image.name.startswith('libhdf5')
            or 'hdf5_hl' in image.name):
        raise _Unavailable('Symbol is not from the bundled private HDF5 image')


def _qualify_hdf5():
    import h5py
    from h5py._objects import phil

    # Different builds retain h5py's ordinary callback. This is not a generic
    # declaration of HDF5 binary compatibility, including on other platforms.
    if (sys.platform != 'darwin' or platform.machine() != 'arm64' or
            not all(hasattr(os, key) for key in ('RTLD_NOLOAD', 'RTLD_LOCAL', 'RTLD_NOW'))):
        raise _Unavailable('No qualified platform/NOLOAD interface')
    if h5py.__version__ != '3.16.0' or tuple(h5py.version.hdf5_version_tuple) != (2, 0, 0):
        raise _Unavailable('Unqualified h5py/HDF5 version')
    if tuple(ctypes.sizeof(t) for t in (ctypes.c_int, ctypes.c_uint,
            ctypes.c_int64, ctypes.c_uint64, ctypes.c_void_p)) != (4, 4, 8, 8, 8):
        raise _Unavailable('Unsupported scalar ABI')
    root = Path(h5py.__file__).resolve(strict=True).parent
    dpath = Path(h5py.h5d.__file__).resolve(strict=True)
    ipath = Path(h5py.h5i.__file__).resolve(strict=True)
    if dpath.parent != root or ipath.parent != root:
        raise _Unavailable('Extension escaped the real h5py package')
    mode = os.RTLD_NOLOAD | os.RTLD_LOCAL | os.RTLD_NOW
    hd, hi = ctypes.CDLL(str(dpath), mode=mode), ctypes.CDLL(str(ipath), mode=mode)
    iterate = hd.H5Dchunk_iter
    if _pointer(iterate) != _pointer(hi.H5Dchunk_iter):
        raise _Unavailable('Dependency symbol identities differ')
    # Only OS introspection uses the process handle. Never search globally for
    # HDF5 or load a library discovered by name/path outside this extension.
    system = ctypes.CDLL(None)
    dladdr = system.dladdr
    dladdr.argtypes = [ctypes.c_void_p, ctypes.POINTER(_DlInfo)]
    dladdr.restype = ctypes.c_int

    def origin(function):
        info = _DlInfo()
        if not dladdr(_pointer(function), ctypes.byref(info)) or not info.name:
            raise _Unavailable('Unknown symbol image')
        return Path(os.fsdecode(info.name)).resolve(strict=True)

    image = origin(iterate)
    _qualified_private_image(root, image)
    for symbol in ('H5Iis_valid', 'H5get_libversion'):
        if (_pointer(getattr(hd, symbol)) != _pointer(getattr(hi, symbol)) or
                origin(getattr(hd, symbol)) != image):
            raise _Unavailable('HDF5 dependency identity disagreement')
    version = hd.H5get_libversion
    version.argtypes = [ctypes.POINTER(ctypes.c_uint)] * 3
    version.restype = ctypes.c_int
    major, minor, release = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
    with phil:
        if version(ctypes.byref(major), ctypes.byref(minor), ctypes.byref(release)) != 0:
            raise _Unavailable('Unable to identify loaded HDF5')
    if (major.value, minor.value, release.value) != tuple(h5py.version.hdf5_version_tuple):
        raise _Unavailable('Loaded HDF5 version mismatch')
    iterate.argtypes = [ctypes.c_int64, ctypes.c_int64, ctypes.c_void_p, ctypes.c_void_p]
    iterate.restype = ctypes.c_int
    valid = hd.H5Iis_valid
    valid.argtypes = [ctypes.c_int64]
    valid.restype = ctypes.c_int
    return hd, hi, phil, iterate, valid


@lru_cache(maxsize=1)
def _binding(helper):
    try:
        # Old ABI 4 helpers remain useful for extraction without this optional
        # feature. Configure these functions here even for injected helpers.
        size = helper.disco_trace_chunk_context_v1_size
        version = helper.disco_trace_chunk_context_v1_version
        offset = helper.disco_trace_chunk_context_v1_offset
        callback = helper.disco_trace_chunk_collect_v1
        size.argtypes, size.restype = [], ctypes.c_uint64
        version.argtypes, version.restype = [], ctypes.c_uint64
        offset.argtypes, offset.restype = [ctypes.c_uint], ctypes.c_uint64
        if size() != ctypes.sizeof(_Context) or version() != 1:
            raise _Unavailable('Context ABI mismatch')
        for index, (name, _) in enumerate(_Context._fields_):
            if offset(index) != getattr(_Context, name).offset:
                raise _Unavailable('Context field offset mismatch')
        callback.argtypes = [ctypes.POINTER(ctypes.c_uint64), ctypes.c_uint,
                             ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
        callback.restype = ctypes.c_int
        hd, hi, phil, iterate, valid = _qualify_hdf5()
        return hd, hi, phil, iterate, valid, helper, callback
    except (_Unavailable, OSError, AttributeError, ImportError):
        return None


def try_enumerate_chunks(data, already_loaded_helper):
    """Return the ordinary map shape or UNSUPPORTED before iteration starts."""
    import h5py
    import numpy as np

    if type(data) is not h5py.Dataset:
        return UNSUPPORTED
    bound = _binding(already_loaded_helper)
    if bound is None:
        return UNSUPPORTED
    hd, hi, phil, iterate, valid, helper, callback = bound
    with phil:
        dataset_id = data.id
        if type(dataset_id) is not h5py.h5d.DatasetID:
            return UNSUPPORTED
        if not dataset_id.valid or valid(dataset_id.id) <= 0:
            raise ValueError('Native chunk iteration dataset ID is invalid')
        if data.ndim != 1 or data.chunks != (64,):
            return UNSUPPORTED
        total = len(data)
        if not 0 < total <= 1000000:
            return UNSUPPORTED
        count = (total + 63) // 64
        physical = np.zeros(count, dtype=np.uint64)
        lengths = np.zeros(count, dtype=np.uint64)
        order = np.empty(count, dtype=np.int64)
        seen = (ctypes.c_ubyte * count)()
        context = _Context(1, count, total, 0, physical.ctypes.data,
            lengths.ctypes.data, order.ctypes.data, ctypes.addressof(seen), 0, 0, 0, 0)
        # This is an exported C function address, not a Python callback thunk.
        # All dataset/array/context/library references survive the entire call.
        result = iterate(dataset_id.id, 0, _pointer(callback), ctypes.byref(context))
        if result != 0 or context.invalid_context:
            raise ValueError('Native HDF5 chunk iteration failed')
        if context.count > count:
            raise ValueError('Duplicate trace chunk locations')
        if context.invalid_logical:
            raise ValueError('Invalid or duplicate trace chunk locations')
        if context.count != count or context.masked:
            return int(context.count), None
        return int(context.count), (physical, lengths, {}, order)
