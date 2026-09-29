"""
Import Module: Read .ugm selection mask and map to DataJoint epoch h5_uuids.

Reads a .ugm file (saved by epicTreeTools.saveUserMetadata) and returns
the selection state keyed by h5_uuid for pushing back to DataJoint Tags.

Note: .ugm files are saved with MATLAB's -v7.3 flag (HDF5 format),
so we use h5py instead of scipy.io.loadmat.
"""

import h5py
import numpy as np


def read_ugm(filepath):
    """
    Read a .ugm file and return epoch selection state keyed by h5_uuid.

    Args:
        filepath (str): Path to .ugm file

    Returns:
        dict: {
            'version': str,
            'created': str,
            'epoch_count': int,
            'selected_count': int,
            'excluded_count': int,
            'excluded_uuids': list[str],  -- h5_uuids of deselected epochs
            'selected_uuids': list[str],  -- h5_uuids of selected epochs
        }

    Raises:
        FileNotFoundError: If filepath doesn't exist
        ValueError: If .ugm is missing epoch_h5_uuids (v1.0 format)
        ValueError: If .ugm has invalid structure
    """
    try:
        f = h5py.File(filepath, 'r')
    except Exception as e:
        raise ValueError(f"Failed to read .ugm file: {e}")

    try:
        if 'ugm' not in f:
            raise ValueError("File does not contain ugm struct")

        ugm = f['ugm']

        # Extract scalar fields
        version = _read_h5_string(f, ugm['version'])
        created = _read_h5_string(f, ugm['created'])
        epoch_count = int(np.array(ugm['epoch_count']).flatten()[0])
        selection_mask = np.array(ugm['selection_mask']).flatten().astype(bool)

        # Check for h5_uuids (required for DataJoint round-trip)
        if 'epoch_h5_uuids' not in ugm:
            raise ValueError(
                f"This .ugm file (version {version}) does not contain epoch_h5_uuids. "
                "Re-export from DataJoint and re-save the .ugm to include UUIDs. "
                "Only .ugm v1.1+ files support DataJoint round-trip."
            )

        # Read cell array of strings (HDF5 object references)
        epoch_h5_uuids = _read_h5_cell_strings(f, ugm['epoch_h5_uuids'])

        # Validate lengths match
        if len(selection_mask) != len(epoch_h5_uuids):
            raise ValueError(
                f"Mask length ({len(selection_mask)}) != UUID count ({len(epoch_h5_uuids)})"
            )

        # Check that UUIDs are not all empty (non-DataJoint data)
        non_empty_count = sum(1 for u in epoch_h5_uuids if u)
        if non_empty_count == 0:
            raise ValueError(
                "This .ugm file has no h5_uuids (all empty). "
                "It was saved from non-DataJoint data. "
                "Re-export from DataJoint first, then save a new .ugm."
            )

        # Build excluded/selected lists
        excluded_uuids = []
        selected_uuids = []
        for i, uuid in enumerate(epoch_h5_uuids):
            if uuid:  # Skip empty uuids
                if selection_mask[i]:
                    selected_uuids.append(uuid)
                else:
                    excluded_uuids.append(uuid)

        return {
            'version': version,
            'created': created,
            'epoch_count': epoch_count,
            'selected_count': len(selected_uuids),
            'excluded_count': len(excluded_uuids),
            'excluded_uuids': excluded_uuids,
            'selected_uuids': selected_uuids,
        }
    finally:
        f.close()


def _read_h5_string(f, dataset):
    """Read a MATLAB string from HDF5 dataset (handles object references)."""
    data = np.array(dataset).flatten()
    if data.dtype == np.object_ or data.dtype.kind == 'O':
        # Object reference - dereference it
        ref = data[0]
        return ''.join(chr(c) for c in np.array(f[ref]).flatten())
    elif data.dtype.kind == 'U' or data.dtype.kind == 'S':
        return str(data[0])
    else:
        # Numeric array of char codes
        return ''.join(chr(int(c)) for c in data)


def _read_h5_cell_strings(f, dataset):
    """Read a MATLAB cell array of strings from HDF5 dataset."""
    refs = np.array(dataset).flatten()
    strings = []
    for ref in refs:
        if isinstance(ref, h5py.h5r.Reference):
            chars = np.array(f[ref]).flatten()
            s = ''.join(chr(int(c)) for c in chars)
            strings.append(s)
        else:
            strings.append(str(ref))
    return strings
