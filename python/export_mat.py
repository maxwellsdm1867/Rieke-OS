"""
Export Module: Convert DataJoint Tree to EpicTreeGUI .mat Format

This module provides the main export function that transforms DataJoint's
9-level hierarchy (Experiment → Animal → Preparation → Cell → EpochGroup →
EpochBlock → Epoch → Response/Stimulus) into epicTreeGUI's 5-level format
(Experiment → Cell → EpochGroup → EpochBlock → Epoch with nested responses/stimuli).
"""

import os
from datetime import datetime
import scipy.io

from field_mapper import (
    sanitize_for_matlab,
    flatten_json_params,
    deep_sanitize,
    extract_experiment_fields,
    extract_animal_fields,
    extract_preparation_fields,
    extract_cell_fields,
    extract_epoch_group_fields,
    extract_epoch_block_fields,
    extract_epoch_fields,
    build_response_struct,
    build_stimulus_struct
)


def extract_tags(node):
    """
    Extract tags from a generate_tree() node into a MATLAB-friendly format.

    Tags in generate_tree() output are: [{'user': 'alice', 'tag': 'important'}, ...]
    We convert to: [{'user': 'alice', 'tag': 'important'}, ...] (same structure,
    but strip extra fields like tag_id, table_name, table_id, experiment_id, h5_uuid).

    Args:
        node: A node dict from generate_tree() output

    Returns:
        list: List of {'user': str, 'tag': str} dicts, or empty list if no tags
    """
    raw_tags = node.get('tags', [])
    if not raw_tags:
        return []
    return [{'user': t.get('user', ''), 'tag': t.get('tag', '')} for t in raw_tags]


def export_to_mat(tree_data, username, download_dir, h5_file_path=None):
    """
    Export DataJoint tree structure to epicTreeGUI .mat format.

    Args:
        tree_data (list): Output from generate_object_tree(include_meta=True)
                         9-level hierarchy starting with experiment nodes
        username (str): Database username for metadata
        download_dir (str): Directory to write .mat file
        h5_file_path (str): Optional path to H5 file for lazy loading

    Returns:
        str: Path to generated .mat file

    Raises:
        ValueError: If tree_data contains MEA experiments (is_mea=True)
        IOError: If write fails
    """
    # Build hierarchical structure matching DATA_FORMAT_SPECIFICATION
    experiments = []

    for exp_node in tree_data:
        experiment = build_experiment(exp_node, h5_file_path)
        experiments.append(experiment)

    # Create export data structure
    export_data = {
        'format_version': '1.0',
        'metadata': {
            'created_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_source': 'DataJoint + H5 files',
            'export_user': username
        },
        'experiments': experiments
    }

    # Write to .mat file
    filename = f"epictree_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mat"
    filepath = os.path.join(download_dir, filename)

    # Deep sanitize entire structure to remove None values, convert datetimes, etc.
    export_data = deep_sanitize(export_data)

    scipy.io.savemat(
        filepath,
        export_data,
        do_compression=True,  # Reduce file size
        oned_as='row',        # MATLAB convention for 1-D arrays
        format='5'            # MATLAB v5 format (most compatible)
    )

    return filepath


def build_experiment(exp_node, h5_file_path):
    """
    Process experiment node and flatten Animal → Preparation → Cell hierarchy.

    Args:
        exp_node: Experiment node from generate_object_tree
        h5_file_path: Path to H5 file (or None)

    Returns:
        dict: Experiment dict with cells array (flattened from 9-level to 5-level)

    Raises:
        ValueError: If is_mea=True (MEA not supported in Phase 05)
    """
    exp_data = exp_node['object'][0]

    # Check for MEA experiment (reject per user constraint)
    if exp_data.get('is_mea', False):
        raise ValueError(
            f"MEA experiments are not supported. "
            f"Experiment {exp_data.get('exp_name', exp_data.get('id'))} has is_mea=True. "
            f"This phase only supports single-cell patch clamp data."
        )

    # Extract experiment fields
    experiment = extract_experiment_fields(exp_data)
    experiment['tags'] = extract_tags(exp_node)
    experiment['cells'] = []

    # Get H5 file path from experiment data_file if not provided
    if h5_file_path is None:
        h5_file_path = exp_data.get('data_file', '')

    # Navigate: Experiment → Animal → Preparation → Cell
    # Flatten to: Experiment → Cell with merged metadata
    for animal_node in exp_node.get('children', []):
        animal_data = animal_node['object'][0] if animal_node.get('object') else {}
        animal_fields = extract_animal_fields(animal_data)

        for prep_node in animal_node.get('children', []):
            prep_data = prep_node['object'][0] if prep_node.get('object') else {}
            prep_fields = extract_preparation_fields(prep_data)

            for cell_node in prep_node.get('children', []):
                cell = build_cell(cell_node, animal_fields, prep_fields, h5_file_path)
                experiment['cells'].append(cell)

    return experiment


def build_cell(cell_node, animal_meta, prep_meta, h5_file):
    """
    Build cell dict with merged Animal/Preparation metadata into properties.

    Args:
        cell_node: Cell node from generate_object_tree
        animal_meta: Extracted animal fields dict
        prep_meta: Extracted preparation fields dict
        h5_file: Path to H5 file

    Returns:
        dict: Cell dict with flattened animal/preparation metadata in properties
    """
    cell_data = cell_node['object'][0] if cell_node.get('object') else {}
    cell_fields = extract_cell_fields(cell_data)

    # Merge Animal + Preparation into Cell properties
    cell = {
        'id': cell_fields['id'],
        'h5_uuid': cell_fields['h5_uuid'],
        'label': cell_fields['label'],
        'type': cell_fields['type'],
        'tags': extract_tags(cell_node),
        'properties': {
            # Animal metadata
            'species': animal_meta.get('species', ''),
            'age': animal_meta.get('age', ''),
            'sex': animal_meta.get('sex', ''),
            # Preparation metadata
            'bath_solution': prep_meta.get('bath_solution', ''),
            'region': prep_meta.get('region', '')
        },
        'epoch_groups': []
    }

    # Process epoch groups
    for eg_node in cell_node.get('children', []):
        epoch_group = build_epoch_group(eg_node, h5_file)
        cell['epoch_groups'].append(epoch_group)

    return cell


def build_epoch_group(eg_node, h5_file):
    """
    Build epoch group dict.

    Args:
        eg_node: EpochGroup node from generate_object_tree
        h5_file: Path to H5 file

    Returns:
        dict: Epoch group dict with epoch_blocks array
    """
    eg_data = eg_node['object'][0] if eg_node.get('object') else {}
    eg_fields = extract_epoch_group_fields(eg_data)

    epoch_group = {
        'id': eg_fields['id'],
        'h5_uuid': eg_fields['h5_uuid'],
        'label': eg_fields['label'],
        'protocol_name': eg_fields['protocol_name'],
        'protocol_id': eg_fields['protocol_id'],
        'start_time': eg_fields['start_time'],
        'end_time': eg_fields['end_time'],
        'tags': extract_tags(eg_node),
        'epoch_blocks': []
    }

    # Process epoch blocks
    for eb_node in eg_node.get('children', []):
        epoch_block = build_epoch_block(eb_node, h5_file)
        epoch_group['epoch_blocks'].append(epoch_block)

    return epoch_group


def build_epoch_block(eb_node, h5_file):
    """
    Build epoch block dict with flattened parameters.

    Args:
        eb_node: EpochBlock node from generate_object_tree
        h5_file: Path to H5 file

    Returns:
        dict: Epoch block dict with epochs array and flattened parameters
    """
    eb_data = eb_node['object'][0] if eb_node.get('object') else {}
    eb_fields = extract_epoch_block_fields(eb_data)

    # Flatten JSON parameters blob
    params = eb_data.get('parameters', {})
    flat_params = flatten_json_params(params)

    epoch_block = {
        'id': eb_fields['id'],
        'h5_uuid': eb_fields['h5_uuid'],
        'label': eb_fields['label'],
        'protocol_name': eb_fields['protocol_name'],
        'protocol_id': eb_fields['protocol_id'],
        'start_time': eb_fields['start_time'],
        'end_time': eb_fields['end_time'],
        'parameters': flat_params,
        'tags': extract_tags(eb_node),
        'epochs': []
    }

    # Process epochs
    for epoch_node in eb_node.get('children', []):
        epoch = build_epoch(epoch_node, h5_file)
        epoch_block['epochs'].append(epoch)

    return epoch_block


def build_epoch(epoch_node, h5_file):
    """
    Build epoch dict with responses/stimuli via field_mapper structs.

    Args:
        epoch_node: Epoch node from generate_object_tree
        h5_file: Path to H5 file

    Returns:
        dict: Epoch dict with flattened parameters and response/stimulus structs
    """
    epoch_data = epoch_node['object'][0] if epoch_node.get('object') else {}
    epoch_fields = extract_epoch_fields(epoch_data)

    # Flatten JSON parameters blob
    params = epoch_data.get('parameters', {})
    flat_params = flatten_json_params(params)

    epoch = {
        'id': epoch_fields['id'],
        'h5_uuid': epoch_fields['h5_uuid'],
        'label': epoch_fields['label'],
        'start_time': epoch_fields['start_time'],
        'end_time': epoch_fields['end_time'],
        'parameters': flat_params,
        'tags': extract_tags(epoch_node),
        'responses': [],
        'stimuli': []
    }

    # Build response structs
    for resp_dict in epoch_node.get('responses', []):
        response = build_response_struct(resp_dict, h5_file)
        epoch['responses'].append(response)

    # Build stimulus structs
    for stim_dict in epoch_node.get('stimuli', []):
        stimulus = build_stimulus_struct(stim_dict, h5_file)
        epoch['stimuli'].append(stimulus)

    return epoch
