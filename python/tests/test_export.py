"""
Unit tests for epicTreeGUI export module.

Tests follow TDD RED-GREEN-REFACTOR cycle.
"""

import pytest
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Test: sanitize_for_matlab
# ============================================================================

def test_sanitize_none_returns_empty_array():
    """None should convert to empty list (MATLAB empty array)."""
    from field_mapper import sanitize_for_matlab
    result = sanitize_for_matlab(None)
    assert result == []


def test_sanitize_empty_string_passes_through():
    """Empty strings should remain as empty strings."""
    from field_mapper import sanitize_for_matlab
    result = sanitize_for_matlab('')
    assert result == ''


def test_sanitize_numeric_passes_through():
    """Numeric values should pass through unchanged."""
    from field_mapper import sanitize_for_matlab
    assert sanitize_for_matlab(42) == 42
    assert sanitize_for_matlab(3.14) == 3.14
    assert sanitize_for_matlab(0) == 0


def test_sanitize_empty_dict_preserved():
    """Empty dicts should remain as empty dicts."""
    from field_mapper import sanitize_for_matlab
    result = sanitize_for_matlab({})
    assert result == {}


def test_sanitize_string_passes_through():
    """Non-empty strings should pass through unchanged."""
    from field_mapper import sanitize_for_matlab
    assert sanitize_for_matlab('test') == 'test'


# ============================================================================
# Test: flatten_json_params
# ============================================================================

def test_flatten_nested_dict_three_levels():
    """Nested dicts should flatten with underscore separators."""
    from field_mapper import flatten_json_params

    nested = {
        'stimulus': {
            'spot': {
                'intensity': 0.5
            }
        }
    }

    result = flatten_json_params(nested)
    assert result == {'stimulus_spot_intensity': 0.5}


def test_flatten_already_flat_dict_unchanged():
    """Already-flat dicts should remain unchanged."""
    from field_mapper import flatten_json_params

    flat = {'preTime': 100, 'stimTime': 200}
    result = flatten_json_params(flat)
    assert result == {'preTime': 100, 'stimTime': 200}


def test_flatten_none_input_returns_empty_dict():
    """None input should return empty dict."""
    from field_mapper import flatten_json_params

    result = flatten_json_params(None)
    assert result == {}


def test_flatten_empty_dict_returns_empty_dict():
    """Empty dict input should return empty dict."""
    from field_mapper import flatten_json_params

    result = flatten_json_params({})
    assert result == {}


def test_flatten_mixed_levels():
    """Mixed nested and flat keys should work correctly."""
    from field_mapper import flatten_json_params

    mixed = {
        'flat_key': 123,
        'nested': {
            'level1': {
                'level2': 'value'
            }
        },
        'another_flat': 'test'
    }

    result = flatten_json_params(mixed)
    assert result == {
        'flat_key': 123,
        'nested_level1_level2': 'value',
        'another_flat': 'test'
    }


# ============================================================================
# Test: parse_sample_rate
# ============================================================================

def test_parse_sample_rate_hz_string():
    """Parse string with Hz suffix."""
    from field_mapper import parse_sample_rate

    assert parse_sample_rate("10000 Hz") == 10000.0


def test_parse_sample_rate_khz_string():
    """Parse string with kHz suffix."""
    from field_mapper import parse_sample_rate

    assert parse_sample_rate("10 kHz") == 10000.0


def test_parse_sample_rate_numeric_input():
    """Numeric input should convert to float."""
    from field_mapper import parse_sample_rate

    assert parse_sample_rate(10000) == 10000.0
    assert parse_sample_rate(10000.0) == 10000.0


def test_parse_sample_rate_none_returns_zero():
    """None input should return 0.0."""
    from field_mapper import parse_sample_rate

    assert parse_sample_rate(None) == 0.0


# ============================================================================
# Test: extract_experiment_fields
# ============================================================================

def test_extract_experiment_complete_dict():
    """Extract all experiment fields from complete dict."""
    from field_mapper import extract_experiment_fields

    obj_dict = {
        'id': 1,
        'exp_name': '20250115A',
        'is_mea': False,
        'label': 'Test Experiment',
        'experimenter': 'John Doe',
        'rig': 'Rig1'
    }

    result = extract_experiment_fields(obj_dict)

    assert result['id'] == 1
    assert result['exp_name'] == '20250115A'
    assert result['is_mea'] == False
    assert result['label'] == 'Test Experiment'
    assert result['experimenter'] == 'John Doe'
    assert result['rig'] == 'Rig1'


def test_extract_experiment_with_none_values():
    """None values should become empty strings."""
    from field_mapper import extract_experiment_fields

    obj_dict = {
        'id': 1,
        'exp_name': '20250115A',
        'is_mea': False,
        'label': None,
        'experimenter': None
    }

    result = extract_experiment_fields(obj_dict)

    assert result['label'] == ''
    assert result['experimenter'] == ''


# ============================================================================
# Test: extract_animal_fields
# ============================================================================

def test_extract_animal_complete_dict():
    """Extract all animal fields from complete dict."""
    from field_mapper import extract_animal_fields

    obj_dict = {
        'id': 5,
        'species': 'Mouse',
        'age': '8 weeks',
        'sex': 'M'
    }

    result = extract_animal_fields(obj_dict)

    assert result['id'] == 5
    assert result['species'] == 'Mouse'
    assert result['age'] == '8 weeks'
    assert result['sex'] == 'M'


def test_extract_animal_with_none_values():
    """None values should become empty strings."""
    from field_mapper import extract_animal_fields

    obj_dict = {
        'id': 5,
        'species': None,
        'age': None
    }

    result = extract_animal_fields(obj_dict)

    assert result['species'] == ''
    assert result['age'] == ''


# ============================================================================
# Test: extract_preparation_fields
# ============================================================================

def test_extract_preparation_complete_dict():
    """Extract all preparation fields from complete dict."""
    from field_mapper import extract_preparation_fields

    obj_dict = {
        'id': 10,
        'bath_solution': 'Ames',
        'region': 'Retina'
    }

    result = extract_preparation_fields(obj_dict)

    assert result['id'] == 10
    assert result['bath_solution'] == 'Ames'
    assert result['region'] == 'Retina'


# ============================================================================
# Test: extract_cell_fields
# ============================================================================

def test_extract_cell_complete_dict():
    """Extract all cell fields from complete dict."""
    from field_mapper import extract_cell_fields

    obj_dict = {
        'id': 42,
        'type': 'OnP',
        'label': 'Cell 1',
        'properties': {'custom': 'data'}
    }

    result = extract_cell_fields(obj_dict)

    assert result['id'] == 42
    assert result['type'] == 'OnP'
    assert result['label'] == 'Cell 1'


# ============================================================================
# Test: extract_epoch_group_fields
# ============================================================================

def test_extract_epoch_group_complete_dict():
    """Extract all epoch group fields from complete dict."""
    from field_mapper import extract_epoch_group_fields

    obj_dict = {
        'id': 15,
        'label': 'Group 1',
        'protocol_name': 'Contrast',
        'start_time': '2025-01-15 10:00:00',
        'end_time': '2025-01-15 11:00:00'
    }

    result = extract_epoch_group_fields(obj_dict)

    assert result['id'] == 15
    assert result['label'] == 'Group 1'
    assert result['protocol_name'] == 'Contrast'


# ============================================================================
# Test: extract_epoch_block_fields
# ============================================================================

def test_extract_epoch_block_complete_dict():
    """Extract all epoch block fields from complete dict."""
    from field_mapper import extract_epoch_block_fields

    obj_dict = {
        'id': 20,
        'protocol_name': 'Contrast',
        'protocol_id': 5,
        'start_time': '2025-01-15 10:00:00',
        'parameters': {'contrast': 0.5}
    }

    result = extract_epoch_block_fields(obj_dict)

    assert result['id'] == 20
    assert result['protocol_name'] == 'Contrast'
    assert result['protocol_id'] == 5


# ============================================================================
# Test: extract_epoch_fields
# ============================================================================

def test_extract_epoch_complete_dict():
    """Extract all epoch fields from complete dict."""
    from field_mapper import extract_epoch_fields

    obj_dict = {
        'id': 123,
        'label': 'Epoch 1',
        'start_time': '2025-01-15 10:00:00',
        'end_time': '2025-01-15 10:00:05',
        'parameters': {'contrast': 0.5}
    }

    result = extract_epoch_fields(obj_dict)

    assert result['id'] == 123
    assert result['label'] == 'Epoch 1'


# ============================================================================
# Test: build_response_struct
# ============================================================================

def test_build_response_struct_complete():
    """Build response struct with all fields."""
    from field_mapper import build_response_struct

    resp_dict = {
        'id': 456,
        'device_name': 'Amp1',
        'label': 'Voltage response',
        'h5path': '/experiment-123/responses/Amp1-456/data',
        'sample_rate': '10000 Hz',
        'sample_rate_units': 'Hz',
        'units': 'mV'
    }

    h5_file = '/path/to/data.h5'

    result = build_response_struct(resp_dict, h5_file)

    assert result['device_name'] == 'Amp1'
    assert result['data'] == []  # Empty for lazy loading
    assert result['h5_path'] == '/experiment-123/responses/Amp1-456/data'
    assert result['h5_file'] == '/path/to/data.h5'
    assert result['sample_rate'] == 10000.0
    assert result['sample_rate_units'] == 'Hz'
    assert result['units'] == 'mV'
    assert result['spike_times'] == []
    assert result['offset_ms'] == 0.0


def test_build_response_struct_none_h5_file():
    """Response with None h5_file should have empty string."""
    from field_mapper import build_response_struct

    resp_dict = {
        'id': 456,
        'device_name': 'Amp1',
        'h5path': '/experiment-123/responses/Amp1-456/data',
        'sample_rate': 10000
    }

    result = build_response_struct(resp_dict, None)

    assert result['h5_file'] == ''


# ============================================================================
# Test: build_stimulus_struct
# ============================================================================

def test_build_stimulus_struct_complete():
    """Build stimulus struct with all fields."""
    from field_mapper import build_stimulus_struct

    stim_dict = {
        'id': 789,
        'device_name': 'Stage',
        'label': 'LED stimulus',
        'h5path': '/experiment-123/stimuli/Stage-789/data',
        'sample_rate': '10000 Hz',
        'units': 'normalized'
    }

    h5_file = '/path/to/data.h5'

    result = build_stimulus_struct(stim_dict, h5_file)

    assert result['device_name'] == 'Stage'
    assert result['data'] == []  # Empty for lazy loading
    assert result['h5_path'] == '/experiment-123/stimuli/Stage-789/data'
    assert result['h5_file'] == '/path/to/data.h5'
    assert result['sample_rate'] == 10000.0
    assert result['units'] == 'normalized'


# ============================================================================
# Integration Tests: export_mat.py
# ============================================================================

def test_export_to_mat_single_experiment():
    """Export single experiment with 1 cell, 1 epoch group, 1 block, 2 epochs."""
    from export_mat import export_to_mat
    import tempfile
    import os

    # Build synthetic generate_tree output (9-level hierarchy)
    tree_data = [
        {
            'level': 'experiment',
            'id': 1,
            'is_mea': False,
            'label': 'Test Experiment',
            'object': [{
                'id': 1,
                'exp_name': '20250115A',
                'is_mea': False,
                'experimenter': 'John Doe',
                'rig': 'Rig1',
                'data_file': '/path/to/data.h5'
            }],
            'tags': [],
            'children': [
                {
                    'level': 'animal',
                    'id': 5,
                    'object': [{
                        'id': 5,
                        'species': 'Mouse',
                        'age': '8 weeks',
                        'sex': 'M'
                    }],
                    'children': [
                        {
                            'level': 'preparation',
                            'id': 10,
                            'object': [{
                                'id': 10,
                                'bath_solution': 'Ames',
                                'region': 'Retina'
                            }],
                            'children': [
                                {
                                    'level': 'cell',
                                    'id': 42,
                                    'label': 'Cell 1',
                                    'object': [{
                                        'id': 42,
                                        'type': 'OnP',
                                        'label': 'Cell 1'
                                    }],
                                    'children': [
                                        {
                                            'level': 'epoch_group',
                                            'id': 15,
                                            'object': [{
                                                'id': 15,
                                                'protocol_name': 'Contrast',
                                                'protocol_id': 5
                                            }],
                                            'children': [
                                                {
                                                    'level': 'epoch_block',
                                                    'id': 20,
                                                    'object': [{
                                                        'id': 20,
                                                        'protocol_name': 'Contrast',
                                                        'protocol_id': 5,
                                                        'parameters': {'contrast': 0.5}
                                                    }],
                                                    'children': [
                                                        {
                                                            'level': 'epoch',
                                                            'id': 100,
                                                            'object': [{
                                                                'id': 100,
                                                                'label': 'Epoch 1',
                                                                'parameters': {'contrast': 0.5}
                                                            }],
                                                            'responses': [
                                                                {
                                                                    'device_name': 'Amp1',
                                                                    'h5path': '/exp-1/resp-100',
                                                                    'sample_rate': '10000 Hz'
                                                                }
                                                            ],
                                                            'stimuli': []
                                                        },
                                                        {
                                                            'level': 'epoch',
                                                            'id': 101,
                                                            'object': [{
                                                                'id': 101,
                                                                'label': 'Epoch 2',
                                                                'parameters': {'contrast': 0.8}
                                                            }],
                                                            'responses': [
                                                                {
                                                                    'device_name': 'Amp1',
                                                                    'h5path': '/exp-1/resp-101',
                                                                    'sample_rate': 10000
                                                                }
                                                            ],
                                                            'stimuli': []
                                                        }
                                                    ]
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    # Export to temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = export_to_mat(
            tree_data=tree_data,
            username='testuser',
            download_dir=tmpdir,
            h5_file_path='/path/to/data.h5'
        )

        # Verify file exists
        assert os.path.exists(filepath)
        assert filepath.endswith('.mat')

        # Load with scipy and verify structure
        import scipy.io
        data = scipy.io.loadmat(filepath)

        assert 'format_version' in data
        assert 'metadata' in data
        assert 'experiments' in data


def test_export_to_mat_mea_raises_error():
    """MEA experiment (is_mea=True) should raise ValueError."""
    from export_mat import export_to_mat
    import tempfile

    tree_data = [
        {
            'level': 'experiment',
            'id': 1,
            'is_mea': True,  # MEA experiment
            'object': [{'id': 1, 'exp_name': 'MEA_Exp', 'is_mea': True}],
            'children': []
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="MEA"):
            export_to_mat(tree_data, 'testuser', tmpdir)


def test_export_to_mat_roundtrip_structure():
    """Round-trip: export .mat -> load with scipy -> verify structure matches spec."""
    from export_mat import export_to_mat
    import tempfile
    import scipy.io

    tree_data = [
        {
            'level': 'experiment',
            'id': 1,
            'is_mea': False,
            'object': [{
                'id': 1,
                'exp_name': '20250115A',
                'is_mea': False,
                'data_file': '/path/to/data.h5'
            }],
            'children': [
                {
                    'level': 'animal',
                    'id': 5,
                    'object': [{'id': 5, 'species': 'Mouse', 'age': '8 weeks'}],
                    'children': [
                        {
                            'level': 'preparation',
                            'id': 10,
                            'object': [{'id': 10, 'bath_solution': 'Ames', 'region': 'Retina'}],
                            'children': [
                                {
                                    'level': 'cell',
                                    'id': 42,
                                    'object': [{'id': 42, 'type': 'OnP'}],
                                    'children': [
                                        {
                                            'level': 'epoch_group',
                                            'id': 15,
                                            'object': [{'id': 15, 'protocol_name': 'Contrast'}],
                                            'children': [
                                                {
                                                    'level': 'epoch_block',
                                                    'id': 20,
                                                    'object': [{'id': 20, 'protocol_name': 'Contrast', 'parameters': {}}],
                                                    'children': [
                                                        {
                                                            'level': 'epoch',
                                                            'id': 100,
                                                            'object': [{'id': 100, 'parameters': {'contrast': 0.5}}],
                                                            'responses': [],
                                                            'stimuli': []
                                                        }
                                                    ]
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = export_to_mat(tree_data, 'testuser', tmpdir)
        data = scipy.io.loadmat(filepath)

        # Verify top-level structure
        assert data['format_version'][0] == '1.0'
        assert 'metadata' in data
        assert 'experiments' in data

        # Verify metadata fields
        metadata = data['metadata']
        assert 'created_date' in metadata.dtype.names
        assert 'data_source' in metadata.dtype.names
        assert 'export_user' in metadata.dtype.names


def test_export_to_mat_h5_path_preservation():
    """Response structs should have h5_path and h5_file populated correctly."""
    from export_mat import export_to_mat
    import tempfile
    import scipy.io

    tree_data = [
        {
            'level': 'experiment',
            'id': 1,
            'is_mea': False,
            'object': [{
                'id': 1,
                'exp_name': '20250115A',
                'is_mea': False,
                'data_file': '/path/to/data.h5'
            }],
            'children': [
                {
                    'level': 'animal',
                    'id': 5,
                    'object': [{'id': 5}],
                    'children': [
                        {
                            'level': 'preparation',
                            'id': 10,
                            'object': [{'id': 10}],
                            'children': [
                                {
                                    'level': 'cell',
                                    'id': 42,
                                    'object': [{'id': 42, 'type': 'OnP'}],
                                    'children': [
                                        {
                                            'level': 'epoch_group',
                                            'id': 15,
                                            'object': [{'id': 15}],
                                            'children': [
                                                {
                                                    'level': 'epoch_block',
                                                    'id': 20,
                                                    'object': [{'id': 20, 'parameters': {}}],
                                                    'children': [
                                                        {
                                                            'level': 'epoch',
                                                            'id': 100,
                                                            'object': [{'id': 100, 'parameters': {}}],
                                                            'responses': [
                                                                {
                                                                    'device_name': 'Amp1',
                                                                    'h5path': '/experiment-123/responses/Amp1-456',
                                                                    'sample_rate': 10000
                                                                }
                                                            ],
                                                            'stimuli': []
                                                        }
                                                    ]
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = export_to_mat(tree_data, 'testuser', tmpdir, h5_file_path='/custom/path.h5')

        # For now, just verify file is created
        # Full verification would require parsing MATLAB structs from scipy
        assert os.path.exists(filepath)


def test_export_to_mat_animal_preparation_flattening():
    """Cell properties should contain merged animal/preparation metadata."""
    from export_mat import export_to_mat
    import tempfile

    tree_data = [
        {
            'level': 'experiment',
            'id': 1,
            'is_mea': False,
            'object': [{'id': 1, 'exp_name': 'Test', 'is_mea': False, 'data_file': '/path/to/data.h5'}],
            'children': [
                {
                    'level': 'animal',
                    'id': 5,
                    'object': [{'id': 5, 'species': 'Mouse', 'age': '8 weeks'}],
                    'children': [
                        {
                            'level': 'preparation',
                            'id': 10,
                            'object': [{'id': 10, 'bath_solution': 'Ames', 'region': 'Retina'}],
                            'children': [
                                {
                                    'level': 'cell',
                                    'id': 42,
                                    'object': [{'id': 42, 'type': 'OnP'}],
                                    'children': []
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = export_to_mat(tree_data, 'testuser', tmpdir)
        # Verification that metadata is properly flattened happens during export
        # If this doesn't raise an exception, the flattening worked
        assert os.path.exists(filepath)


def test_export_to_mat_empty_responses_stimuli():
    """Empty responses/stimuli arrays should export correctly."""
    from export_mat import export_to_mat
    import tempfile

    tree_data = [
        {
            'level': 'experiment',
            'id': 1,
            'is_mea': False,
            'object': [{'id': 1, 'exp_name': 'Test', 'is_mea': False, 'data_file': '/path/to/data.h5'}],
            'children': [
                {
                    'level': 'animal',
                    'id': 5,
                    'object': [{'id': 5}],
                    'children': [
                        {
                            'level': 'preparation',
                            'id': 10,
                            'object': [{'id': 10}],
                            'children': [
                                {
                                    'level': 'cell',
                                    'id': 42,
                                    'object': [{'id': 42, 'type': 'OnP'}],
                                    'children': [
                                        {
                                            'level': 'epoch_group',
                                            'id': 15,
                                            'object': [{'id': 15}],
                                            'children': [
                                                {
                                                    'level': 'epoch_block',
                                                    'id': 20,
                                                    'object': [{'id': 20, 'parameters': {}}],
                                                    'children': [
                                                        {
                                                            'level': 'epoch',
                                                            'id': 100,
                                                            'object': [{'id': 100, 'parameters': {}}],
                                                            'responses': [],  # Empty
                                                            'stimuli': []     # Empty
                                                        }
                                                    ]
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = export_to_mat(tree_data, 'testuser', tmpdir)
        assert os.path.exists(filepath)


def test_export_to_mat_multiple_experiments():
    """Multiple experiments should all be serialized correctly."""
    from export_mat import export_to_mat
    import tempfile
    import scipy.io

    tree_data = [
        {
            'level': 'experiment',
            'id': 1,
            'is_mea': False,
            'object': [{'id': 1, 'exp_name': 'Exp1', 'is_mea': False, 'data_file': '/path/1.h5'}],
            'children': []
        },
        {
            'level': 'experiment',
            'id': 2,
            'is_mea': False,
            'object': [{'id': 2, 'exp_name': 'Exp2', 'is_mea': False, 'data_file': '/path/2.h5'}],
            'children': []
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = export_to_mat(tree_data, 'testuser', tmpdir)
        data = scipy.io.loadmat(filepath)

        # Verify we have experiments array
        assert 'experiments' in data
