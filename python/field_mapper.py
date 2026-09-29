"""
Field Mapper: DataJoint to EpicTreeGUI Field Extraction and Sanitization

This module provides utilities for converting DataJoint query results
into epicTreeGUI's .mat format structure.
"""

import re


def sanitize_for_matlab(value):
    """
    Convert Python values to MATLAB-compatible representations.

    Args:
        value: Any Python value

    Returns:
        MATLAB-compatible value:
        - None -> [] (empty array)
        - Empty dict -> {} (preserved)
        - Other values pass through unchanged
    """
    if value is None:
        return []
    if isinstance(value, dict) and not value:
        return {}
    return value


def flatten_json_params(params_dict, prefix=''):
    """
    Recursively flatten nested dict to single-level dict with underscore-separated keys.

    Args:
        params_dict: Nested dict to flatten
        prefix: Current key prefix (used in recursion)

    Returns:
        dict: Flattened dict with underscore-separated keys

    Example:
        {'stimulus': {'spot': {'intensity': 0.5}}}
        -> {'stimulus_spot_intensity': 0.5}
    """
    if params_dict is None:
        return {}

    # If params_dict is a JSON string, parse it first
    if isinstance(params_dict, str):
        import json
        try:
            params_dict = json.loads(params_dict)
        except (json.JSONDecodeError, TypeError):
            return {}

    if not isinstance(params_dict, dict):
        return {}

    result = {}

    for key, value in params_dict.items():
        # Build full key with prefix
        if prefix:
            full_key = f"{prefix}_{key}"
        else:
            full_key = key

        # Recursively flatten nested dicts
        if isinstance(value, dict):
            nested = flatten_json_params(value, full_key)
            result.update(nested)
        else:
            # Sanitize None values for MATLAB compatibility
            result[full_key] = sanitize_for_matlab(value)

    return result


def deep_sanitize(obj):
    """
    Recursively sanitize an entire nested structure for scipy.io.savemat.

    Converts all None values to empty strings or empty lists,
    and converts non-serializable types (datetime, etc.) to strings.

    Args:
        obj: Any Python object (dict, list, scalar)

    Returns:
        MATLAB-compatible version of the object
    """
    if obj is None:
        return ''
    if isinstance(obj, dict):
        return {k: deep_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_sanitize(item) for item in obj]
    # Convert datetime objects to strings
    if hasattr(obj, 'strftime'):
        return str(obj)
    # Convert any other non-standard types to string
    if not isinstance(obj, (int, float, str, bool, bytes)):
        return str(obj)
    return obj


def parse_sample_rate(rate_str):
    """
    Convert sample rate string to numeric Hz.

    Args:
        rate_str: String like "10000 Hz" or "10 kHz", or numeric value

    Returns:
        float: Sample rate in Hz, or 0.0 if None/invalid
    """
    if rate_str is None:
        return 0.0

    # Numeric passthrough
    if isinstance(rate_str, (int, float)):
        return float(rate_str)

    # Parse string formats
    match = re.search(r'(\d+(?:\.\d+)?)\s*(Hz|kHz|MHz)?', str(rate_str))
    if match:
        value = float(match.group(1))
        unit = match.group(2) or 'Hz'

        if unit == 'kHz':
            value *= 1000
        elif unit == 'MHz':
            value *= 1e6

        return value

    return 0.0


def extract_experiment_fields(obj_dict):
    """
    Extract experiment fields from DataJoint object dict.

    Args:
        obj_dict: DataJoint experiment row as dict

    Returns:
        dict: Extracted experiment fields with None converted to empty strings
    """
    return {
        'id': obj_dict.get('id'),
        'h5_uuid': obj_dict.get('h5_uuid') or '',
        'exp_name': obj_dict.get('exp_name', ''),
        'is_mea': obj_dict.get('is_mea', False),
        'label': obj_dict.get('label') or '',
        'experimenter': obj_dict.get('experimenter') or '',
        'rig': obj_dict.get('rig', ''),
        'institution': obj_dict.get('institution', '')
    }


def extract_animal_fields(obj_dict):
    """
    Extract animal fields from DataJoint object dict.

    Args:
        obj_dict: DataJoint animal row as dict

    Returns:
        dict: Extracted animal fields with None converted to empty strings
    """
    return {
        'id': obj_dict.get('id'),
        'h5_uuid': obj_dict.get('h5_uuid') or '',
        'species': obj_dict.get('species') or '',
        'age': obj_dict.get('age') or '',
        'sex': obj_dict.get('sex', '')
    }


def extract_preparation_fields(obj_dict):
    """
    Extract preparation fields from DataJoint object dict.

    Args:
        obj_dict: DataJoint preparation row as dict

    Returns:
        dict: Extracted preparation fields with None converted to empty strings
    """
    return {
        'id': obj_dict.get('id'),
        'h5_uuid': obj_dict.get('h5_uuid') or '',
        'bath_solution': obj_dict.get('bath_solution') or '',
        'region': obj_dict.get('region') or ''
    }


def extract_cell_fields(obj_dict):
    """
    Extract cell fields from DataJoint object dict.

    Args:
        obj_dict: DataJoint cell row as dict

    Returns:
        dict: Extracted cell fields with None converted to empty strings
    """
    return {
        'id': obj_dict.get('id'),
        'h5_uuid': obj_dict.get('h5_uuid') or '',
        'type': obj_dict.get('type') or '',
        'label': obj_dict.get('label') or ''
    }


def extract_epoch_group_fields(obj_dict):
    """
    Extract epoch group fields from DataJoint object dict.

    Args:
        obj_dict: DataJoint epoch_group row as dict

    Returns:
        dict: Extracted epoch_group fields with None converted to empty strings
    """
    return {
        'id': obj_dict.get('id'),
        'h5_uuid': obj_dict.get('h5_uuid') or '',
        'label': obj_dict.get('label') or '',
        'protocol_name': obj_dict.get('protocol_name') or '',
        'protocol_id': obj_dict.get('protocol_id', 0),
        'start_time': obj_dict.get('start_time', ''),
        'end_time': obj_dict.get('end_time', '')
    }


def extract_epoch_block_fields(obj_dict):
    """
    Extract epoch block fields from DataJoint object dict.

    Args:
        obj_dict: DataJoint epoch_block row as dict

    Returns:
        dict: Extracted epoch_block fields with None converted to empty strings
    """
    return {
        'id': obj_dict.get('id'),
        'h5_uuid': obj_dict.get('h5_uuid') or '',
        'label': obj_dict.get('label') or '',
        'protocol_name': obj_dict.get('protocol_name') or '',
        'protocol_id': obj_dict.get('protocol_id', 0),
        'start_time': obj_dict.get('start_time', ''),
        'end_time': obj_dict.get('end_time', '')
    }


def extract_epoch_fields(obj_dict):
    """
    Extract epoch fields from DataJoint object dict.

    Args:
        obj_dict: DataJoint epoch row as dict

    Returns:
        dict: Extracted epoch fields with None converted to empty strings
    """
    return {
        'id': obj_dict.get('id'),
        'h5_uuid': obj_dict.get('h5_uuid') or '',
        'label': obj_dict.get('label') or '',
        'start_time': obj_dict.get('start_time', ''),
        'end_time': obj_dict.get('end_time', '')
    }


def build_response_struct(resp_dict, h5_file):
    """
    Build response struct with h5_path for lazy loading.

    Args:
        resp_dict: DataJoint response row as dict
        h5_file: Path to H5 file (or None)

    Returns:
        dict: Response struct with empty data field and h5_path populated
    """
    return {
        'device_name': resp_dict.get('device_name', ''),
        'data': [],  # Empty for lazy loading
        'h5_path': resp_dict.get('h5path', ''),
        'h5_file': h5_file if h5_file else '',
        'sample_rate': parse_sample_rate(resp_dict.get('sample_rate')),
        'sample_rate_units': resp_dict.get('sample_rate_units', 'Hz'),
        'units': resp_dict.get('units', 'mV'),
        'spike_times': [],  # Empty for now (computed on-demand)
        'offset_ms': 0.0
    }


def build_stimulus_struct(stim_dict, h5_file):
    """
    Build stimulus struct with h5_path for lazy loading.

    Args:
        stim_dict: DataJoint stimulus row as dict
        h5_file: Path to H5 file (or None)

    Returns:
        dict: Stimulus struct with empty data field, h5_path,
              stimulus_id (generator class), and stimulus_parameters
    """
    # Extract stimulus parameters and flatten for MATLAB compatibility
    stim_params = stim_dict.get('stimulus_parameters', {})
    if stim_params and isinstance(stim_params, dict):
        stim_params = flatten_json_params(stim_params)
    elif stim_params and isinstance(stim_params, str):
        stim_params = flatten_json_params(stim_params)
    else:
        stim_params = {}

    return {
        'device_name': stim_dict.get('device_name', ''),
        'stimulus_id': stim_dict.get('stimulus_id', ''),
        'data': [],  # Empty for lazy loading / reconstruction
        'h5_path': stim_dict.get('h5path', ''),
        'h5_file': h5_file if h5_file else '',
        'sample_rate': parse_sample_rate(stim_dict.get('sample_rate')),
        'units': stim_dict.get('units', 'normalized'),
        'stimulus_parameters': stim_params
    }
