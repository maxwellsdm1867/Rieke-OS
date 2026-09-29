"""Strict, explicit EpicTree .ugm interchange; no discovery or database writes.

EpicTree saveUserMetadata writes a MATLAB v7.3 scalar ``ugm`` struct with
version 1.1, logical selection_mask and epoch_h5_uuids cell strings. True means
included. MATLAB reconstructs this struct on save, dropping optional provenance
fields. Callers must therefore resolve a completed MAT export by its exact UUID
set when an explicit export identity is absent. Basenames/timestamps are hints,
never proof. Import only the returned UUID→boolean pairs; leave other epochs
unchanged. The historical MATLAB loader's unmatched→true behavior is NOT used.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
import uuid

import h5py
import numpy as np
from scipy.io import loadmat

MAX_EPOCHS = 1_000_000
MAX_TEXT = 4096
UUID_FIELDS = ('dataset_uuid', 'export_uuid', 'project_uuid', 'protocol_uuid')
HASH_FIELDS = ('source_scope_revision', 'source_scope_sha256', 'query_sha256', 'recipe_sha256')
TEXT_FIELDS = ('version', 'created', 'mat_file_basename', *UUID_FIELDS, *HASH_FIELDS)
REQUIRED = ('version', 'epoch_count', 'selection_mask', 'epoch_h5_uuids')


def _vector(value, label, limit=MAX_EPOCHS):
    value = np.asarray(value)
    if value.ndim > 2 or (value.ndim == 2 and min(value.shape) > 1) or not 1 <= value.size <= limit:
        raise ValueError(f'{label} must be a nonempty vector of at most {limit} entries')
    return value.reshape(-1)


def _text(value, label):
    if isinstance(value, np.ndarray):
        if value.size == 1:
            value = value.reshape(-1)[0]
        elif value.dtype.kind in 'US' and value.ndim <= 2 and min(value.shape) <= 1:
            parts = value.reshape(-1).tolist()
            if any(len(part) != 1 for part in parts):
                raise ValueError(f'{label} must be one text value')
            value = ''.join(part.decode('utf-8') if isinstance(part, bytes) else part for part in parts)
        elif value.size == 0 and value.dtype.kind in 'US':
            value = ''
    if isinstance(value, bytes):
        value = value.decode('utf-8')
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        raise ValueError(f'{label} must be text of at most {MAX_TEXT} characters')
    return value


def _uuid(value, label):
    value = _text(value, label)
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as error:
        raise ValueError(f'{label} is missing or is not a valid source UUID') from error


def _ids(values):
    result = [_uuid(value, 'epoch_h5_uuid') for value in _vector(values, 'epoch_h5_uuids')]
    if len(set(result)) != len(result):
        raise ValueError('Duplicate epoch UUIDs in selection mask')
    return result


def _metadata(fields):
    result = {key: _text(fields[key], key) for key in TEXT_FIELDS if key in fields}
    if result.get('version') != '1.1':
        raise ValueError('Only UUID-based EpicTree .ugm version 1.1 is supported')
    for key in UUID_FIELDS:
        if key in result:
            result[key] = _uuid(result[key], key)
    for key in HASH_FIELDS:
        if key in result and (len(result[key]) != 64 or any(c not in '0123456789abcdef' for c in result[key])):
            raise ValueError(f'{key} must be a lowercase SHA-256')
    if all(key in result for key in ('source_scope_revision', 'source_scope_sha256')) and result['source_scope_revision'] != result['source_scope_sha256']:
        raise ValueError('Conflicting source scope hashes')
    return result


def _normalise(fields, *, expected_epoch_uuids=None, expected_metadata=None):
    if any(key not in fields for key in REQUIRED):
        raise ValueError('UGM requires version, epoch_count, selection_mask and epoch_h5_uuids; positional masks are not accepted')
    identities = _ids(fields['epoch_h5_uuids'])
    mask = _vector(fields['selection_mask'], 'selection_mask')
    if mask.dtype.kind != 'b':
        raise ValueError('selection_mask must contain MATLAB logical/boolean values, not numeric truthiness')
    count = np.asarray(fields['epoch_count'])
    if count.size != 1 or count.dtype.kind not in 'iuf':
        raise ValueError('epoch_count must be one positive integer')
    count = count.reshape(-1)[0]
    if not np.isfinite(count) or count != int(count) or int(count) != len(identities) or len(mask) != len(identities):
        raise ValueError('epoch_count, UUID count and mask length must match exactly')
    metadata = {**_metadata(fields), 'epoch_count': int(count)}
    if expected_epoch_uuids is not None:
        expected = set(_ids(expected_epoch_uuids))
        actual = set(identities)
        if expected != actual:
            raise ValueError(f'Mask UUID set differs from the saved MAT export: {len(actual - expected)} foreign, {len(expected - actual)} missing')
    if expected_metadata is not None:
        if not isinstance(expected_metadata, dict) or set(expected_metadata) - set(UUID_FIELDS + HASH_FIELDS):
            raise ValueError('Expected provenance must contain supported UUID/hash fields')
        wanted = _metadata({'version': '1.1', **expected_metadata})
        for key, value in wanted.items():
            if key in metadata and metadata[key] != value:
                raise ValueError(f'Mask {key} differs from the saved export provenance')
        for key in ('source_scope_revision', 'source_scope_sha256'):
            alternate = 'source_scope_sha256' if key == 'source_scope_revision' else 'source_scope_revision'
            if key in wanted and alternate in metadata and wanted[key] != metadata[alternate]:
                raise ValueError('Mask source scope hash differs from the saved export provenance')
    return {'epoch_uuids': identities, 'mask': mask.tolist(), 'metadata': metadata}


def _dataset(value, label, limit):
    if not isinstance(value, h5py.Dataset) or value.size > limit or value.external or value.is_virtual:
        raise ValueError(f'Invalid or oversized {label} dataset')
    return value


def _h5_text(file, value, label):
    value = _dataset(value, label, MAX_TEXT)
    if h5py.check_dtype(ref=value.dtype) is not None:
        refs = _vector(value[()], label, 1)
        if not refs[0]:
            raise ValueError(f'Missing {label} text reference')
        value = _dataset(file[refs[0]], label, MAX_TEXT)
    if value.attrs.get('MATLAB_empty') == 1:
        # MATLAB encodes an empty character array as its dimensions, not text.
        return ''
    raw = value[()]
    if raw.size == 0:
        return ''
    if raw.dtype.kind in 'ui':
        codes = _vector(raw, label, MAX_TEXT)
        if np.any(codes > 65535):
            raise ValueError(f'Invalid UTF-16 in {label}')
        return codes.astype('<u2').tobytes().decode('utf-16-le')
    return _text(raw, label)


def _read_hdf5(path):
    with h5py.File(path, 'r') as file:
        if not isinstance(file.get('ugm', getlink=True), h5py.HardLink) or not isinstance(file['ugm'], h5py.Group):
            raise ValueError('File must contain a scalar ugm struct')
        group = file['ugm']
        fields = {}
        for key in dict.fromkeys((*REQUIRED, *TEXT_FIELDS)):
            if key not in group:
                continue
            if not isinstance(group.get(key, getlink=True), h5py.HardLink):
                raise ValueError('UGM fields cannot refer to external or symbolic links')
            if key in TEXT_FIELDS:
                fields[key] = _h5_text(file, group[key], key)
            elif key == 'epoch_count':
                fields[key] = _dataset(group[key], key, 1)[()]
            elif key == 'selection_mask':
                dataset = _dataset(group[key], key, MAX_EPOCHS)
                raw = _vector(dataset[()], key)
                logical = dataset.attrs.get('MATLAB_class')
                logical = logical.decode('ascii') if isinstance(logical, bytes) else logical
                if raw.dtype.kind != 'b' and not (logical == 'logical' and raw.dtype.kind in 'ui' and np.all((raw == 0) | (raw == 1))):
                    raise ValueError('selection_mask must be a logical vector with only true/false values')
                fields[key] = raw.astype(bool)
            else:
                dataset = _dataset(group[key], key, MAX_EPOCHS)
                if h5py.check_dtype(ref=dataset.dtype) is None:
                    raise ValueError('epoch_h5_uuids must be a MATLAB cell array of text')
                values = []
                for ref in _vector(dataset[()], key):
                    if not ref:
                        raise ValueError('Missing epoch UUID reference')
                    values.append(_h5_text(file, file[ref], 'epoch_h5_uuid'))
                fields[key] = values
        return fields


def read_ugm(path, *, expected_epoch_uuids=None, expected_metadata=None):
    """Read one explicitly supplied v7.3 or v5 mask; optionally check an export.

    Provenance fields are checked when present. Their absence is not permission
    to apply a mask: the caller must match its exact UUID set to a completed MAT
    export and check current protocol/query/curation versions before mutation.
    Returned ordering is the file's ordering; always join by epoch UUID.
    """
    path = Path(path)
    try:
        if h5py.is_hdf5(path):
            fields = _read_hdf5(path)
        else:
            data = loadmat(path, variable_names=['ugm'], struct_as_record=False,
                           squeeze_me=False, mat_dtype=True, chars_as_strings=True)
            value = data.get('ugm')
            if not isinstance(value, np.ndarray) or value.size != 1:
                raise ValueError('File must contain one scalar ugm struct')
            value = value.reshape(-1)[0]
            if not hasattr(value, '_fieldnames'):
                raise ValueError('File must contain a ugm struct')
            fields = {key: getattr(value, key) for key in set(REQUIRED + TEXT_FIELDS) if key in value._fieldnames}
            if 'epoch_h5_uuids' in fields and np.asarray(fields['epoch_h5_uuids']).dtype.kind != 'O':
                raise ValueError('epoch_h5_uuids must be a MATLAB cell array of text')
        return _normalise(fields, expected_epoch_uuids=expected_epoch_uuids, expected_metadata=expected_metadata)
    except (OSError, KeyError, TypeError, UnicodeError, NotImplementedError) as error:
        raise ValueError(f'Cannot read valid EpicTree UGM: {error}') from error


def write_ugm(path, epoch_uuids, mask, metadata=None):
    """Write an actual MATLAB v7.3 .ugm scalar struct without touching its MAT.

    Output UUIDs are a cell column and mask values a logical column. Optional
    flat provenance is useful on initial export but legacy MATLAB saves drop it.
    No timestamp, basename or UUID order is used as an identity fallback.
    """
    import hdf5storage

    if Path(path).suffix.lower() != '.ugm':
        raise ValueError('Write selection masks to a .ugm file, separate from source data')
    metadata = {} if metadata is None else dict(metadata)
    if set(metadata) - set(TEXT_FIELDS + ('epoch_count',)):
        raise ValueError('Unsupported UGM metadata field')
    identities = _ids(epoch_uuids)
    if 'epoch_count' in metadata and metadata['epoch_count'] != len(identities):
        raise ValueError('Supplied metadata epoch_count differs from mask identities')
    fields = {'version': '1.1', 'created': dt.datetime.now(dt.timezone.utc).isoformat(),
              'mat_file_basename': '', **metadata, 'epoch_count': len(identities),
              'epoch_h5_uuids': identities, 'selection_mask': np.asarray(mask)}
    validated = _normalise(fields)
    cells = np.empty((len(identities), 1), dtype=object)
    for index, identity in enumerate(identities):
        cells[index, 0] = identity
    ugm = {**validated['metadata'], 'epoch_count': float(len(identities)),
           'selection_mask': np.asarray(validated['mask'], dtype=bool).reshape(-1, 1),
           'epoch_h5_uuids': cells}
    hdf5storage.savemat(str(path), {'ugm': ugm}, appendmat=False, fmt='7.3',
                       store_python_metadata=False, oned_as='column', truncate_existing=True)
    return validated
