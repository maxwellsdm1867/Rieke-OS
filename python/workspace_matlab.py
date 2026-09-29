"""Exact frozen workspace selection → existing EpicTreeGUI MAT v1 loader.

Waveforms stay in H5. Numeric `id` fields are display ordinals; `h5_uuid` is the
unchanged acquisition identity. Exact metadata/query JSON accompanies convenient
MATLAB fields, so unsupported MATLAB names never silently discard evidence.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import re
import uuid

import numpy as np
import scipy.io

from field_mapper import build_response_struct, build_stimulus_struct, flatten_json_params
from workspace_tag_exchange import frozen_annotation_entries, frozen_document
from workspace_recipes import verify, parse_splits, SPLIT_FIELDS
from workspace_tree import catalog, value_key, field_value_order, materialize_combinations
from workspace_tree_code import matlab_tree_command, matlab_split_fields


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _uuid(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError('Missing or malformed acquisition UUID in MATLAB export metadata') from error


def _structs(items):
    if not items:
        return np.empty((0, 0))
    fields = list(items[0])
    if any(set(item) != set(fields) for item in items):
        raise ValueError('Inconsistent MATLAB structure fields')
    result = np.empty((1, len(items)), dtype=[(key, object) for key in fields])
    for index, item in enumerate(items):
        for key, value in item.items():
            result[key][0, index] = value
    return result


def _params(parameters, warnings):
    """Reuse existing flattening, detecting collisions rather than overwriting."""
    names = []
    def walk(value, prefix=''):
        for key, child in value.items():
            name = prefix + '_' + key if prefix else key
            if isinstance(child, dict):
                walk(child, name)
            else:
                names.append(name)
    walk(parameters)
    if len(set(names)) != len(names):
        raise ValueError('Flattened MATLAB parameter names collide; use reference JSON')
    flat = flatten_json_params(parameters)
    result = {}
    for key, value in flat.items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,62}', key):
            warnings.add('Some source parameter names are represented only in source_metadata_json; MATLAB field names are restricted.')
            continue
        if isinstance(value, (dict, list)) and not all(isinstance(v, (int, float, bool, str)) for v in value):
            warnings.add('Nested parameter arrays remain exact in source_metadata_json.')
            continue
        result[key] = [] if value is None else value
    return result


def _grouping_value(values, field):
    missing = field not in values or (field in SPLIT_FIELDS and values[field] is None)
    return '<not recorded>' if missing else value_key(values[field])


def _grouping_order(rows, values, fields):
    # Match the web tree's typed value ordering without decoding values in MATLAB.
    result = []
    for field in fields:
        distinct = {}
        for row in rows:
            current = values[row['epoch_uuid']]
            encoded = _grouping_value(current, field)
            if field == 'block':
                stamp = str(row.get('block_start_time') or '')
                # Source block timestamps use validated MM/DD/YYYY or ISO dates.
                date = stamp[:10]
                if len(date)==10 and date[2]=='/' and date[5]=='/':
                    date = date[6:10]+'-'+date[:2]+'-'+date[3:5]
                rank = (date+stamp[11:] if stamp else '', str(current.get(field)))
            else:
                rank = (1,) if encoded == '<not recorded>' else (0, *field_value_order(field,current[field]))
            distinct[encoded] = rank
        result.append({'field':field,'values':sorted(distinct,key=distinct.get)})
    return result


def build_matlab_export(service, recipe, output_dir, *, epoch_records=None):
    """Write recordings.mat + launch_epictree.m for exact recipe['epochs'].

    Caller supplies frozen reference-package epoch_records to retain protocol
    tags. This function does not query live curation or mutate the database.
    """
    verify(recipe)
    if recipe.get('format') != 'recording-export-recipe' or recipe.get('version') != 1:
        raise ValueError('MATLAB export requires a sealed export recipe')
    if recipe['project_uuid'] != service.project['project_uuid']:
        raise ValueError('Export recipe belongs to another project')
    members = recipe['epochs']
    ids = [_uuid(item['uuid']) for item in members]
    if not ids or len(set(ids)) != len(ids) or set(ids) - service.rows.keys():
        raise ValueError('Export membership is empty, duplicated, or unavailable')
    for item in members:
        if item['metadata_hash'] != service._fingerprints[item['uuid']]:
            raise ValueError('Source metadata changed since this export recipe was frozen')
    warnings = set()
    records = {}
    if epoch_records is not None:
        records = {record['epoch_uuid']: record for record in epoch_records}
        if len(records) != len(epoch_records) or set(records) != set(ids):
            raise ValueError('Frozen epoch records must exactly match export membership')
    else:
        warnings.add('No frozen protocol tags supplied; live curation was not read.')
    frozen_tag_records = [{**service.rows[key], **records.get(key, {})} for key in ids]
    for record in frozen_tag_records:
        expected = service.rows[record['epoch_uuid']]
        if any(record.get(field) != expected.get(field) for field in ('cell_uuid', 'source_sha256')):
            raise ValueError('Frozen annotation record differs from exported acquisition identity')
    annotations = {(item['target_kind'], item['target_uuid']): item for item in frozen_annotation_entries(frozen_tag_records)}
    sources = {source['source_sha256']: source for source in service.sources}
    used_sources = {service.rows[key]['source_sha256'] for key in ids}
    if used_sources - sources.keys() or used_sources - set(recipe['source_revisions']):
        raise ValueError('Export membership has an unrecorded source revision')
    rows = [service.rows[key] for key in ids]
    registered, _ = catalog(list(service.rows.values()), service.details, sources=service.sources)
    fields, values = catalog(rows, service.details, registered['fields'], sources=service.sources)
    definitions = {field['id']: field for field in fields['fields']}
    order = parse_splits(recipe.get('options', {}).get('split_order', 'date,cell,block'), definitions)
    fields, values = materialize_combinations(fields, values, order)
    definitions = {field['id']: field for field in fields['fields']}
    mapping = [{'field': field, 'label': definitions[field]['label'], 'matlab_path': f'workspaceGrouping.g{index + 1:03}',
                'components': definitions[field].get('components', [])}
               for index, field in enumerate(order)]
    # Labels are presentation only; exact typed keys still determine membership.
    display_values = {field: {} for field in order}
    display_tree = service._render_tree(rows, fields, values, ','.join(order))
    def collect_labels(node):
        field = node.get('field')
        for child in node.get('children', []):
            encoded = '<not recorded>' if child.get('missing') else value_key(child['value'])
            display_values[field][encoded] = (' · '.join(
                'Not recorded' if part['missing'] else 'null (recorded)' if part['value'] is None else value_key(part['value'])
                for part in child['components']) if child.get('components') else child['label'])
            collect_labels(child)
    collect_labels(display_tree)
    display = [{'field': field, 'label': definitions[field]['label'],
                'values': [{'value': encoded, 'label': label} for encoded, label in display_values[field].items()]}
               for field in order]
    groups = {}
    for row in sorted(rows, key=lambda row: (row['source_sha256'], row['cell_uuid'], row['group_uuid'], row['block_uuid'], row['start_time'], row['epoch_uuid'])):
        groups.setdefault(row['source_sha256'], {}).setdefault(row['cell_uuid'], {}).setdefault(row['group_uuid'], {}).setdefault(row['block_uuid'], []).append(row)
    epoch_order, experiments = [], []
    for exp_index, (source_sha, cells) in enumerate(groups.items(), 1):
        source = sources[source_sha]
        source_meta = source.get('metadata', {})
        experiment_uuid = _uuid(source.get('experiment_uuid') or source_meta.get('uuid'))
        cell_items = []
        for cell_index, (cell_uuid, epoch_groups) in enumerate(cells.items(), 1):
            group_items = []
            representative = next(iter(next(iter(epoch_groups.values())).values()))[0]
            cell_meta = service.details[representative['epoch_uuid']]['metadata'].get('cell', {})
            for group_index, (group_uuid, blocks) in enumerate(epoch_groups.items(), 1):
                block_items = []
                first = next(iter(blocks.values()))[0]
                group_meta = service.details[first['epoch_uuid']]['metadata'].get('group', {})
                for block_index, (block_uuid, block_rows) in enumerate(blocks.items(), 1):
                    epoch_items = []
                    block_meta = service.details[block_rows[0]['epoch_uuid']]['metadata'].get('block', {})
                    for epoch_index, row in enumerate(block_rows, 1):
                        key = row['epoch_uuid']
                        detail = service.details[key]
                        epoch_meta = detail['metadata']['epoch']
                        for level, identity in (('cell', cell_uuid), ('group', group_uuid), ('block', block_uuid), ('epoch', key)):
                            recorded = detail['metadata'].get(level, {}).get('uuid')
                            if recorded is not None and _uuid(recorded) != identity:
                                raise ValueError('Recorded hierarchy UUID disagrees with catalog')
                        streams = {'responses': [], 'stimuli': []}
                        for stream in row['streams']:
                            kind, device = stream['kind'], stream['device']
                            if kind not in streams:
                                raise ValueError('Unsupported stream kind')
                            raw = epoch_meta.get(kind, {}).get(device, {})
                            if raw.get('uuid') is not None and raw['uuid'] != stream['uuid']:
                                raise ValueError('Stream identity disagrees with source metadata')
                            if not stream.get('h5_path'):
                                raise ValueError('Missing lazy H5 stream pointer')
                            args = {'device_name': device, 'h5path': stream['h5_path'],
                                    'sample_rate': stream.get('sample_rate'),
                                    'sample_rate_units': stream.get('sample_rate_units') or '',
                                    'units': stream.get('units') or raw.get('units') or '',
                                    'stimulus_id': raw.get('stimulusID', ''),
                                    'stimulus_parameters': {}}
                            result = (build_response_struct if kind == 'responses' else build_stimulus_struct)(args, source['source_path'])
                            result.update(h5_uuid=_uuid(stream['uuid']), source_sha256=source_sha, source_metadata_json=_json(raw),
                                          sample_count=stream.get('sample_count') if stream.get('sample_count') is not None else [],
                                          sample_rate_units=args['sample_rate_units'])
                            if kind == 'stimuli':
                                recorded_parameters = raw.get('parameters', {k: v for k, v in raw.items() if k not in {'uuid', 'h5path'}})
                                result['stimulus_parameters'] = _params(recorded_parameters, warnings)
                            if stream.get('sample_rate') is None:
                                result['sample_rate'] = []
                            streams[kind].append(result)
                        curation = records.get(key, {}).get('curation', {})
                        # Frozen tags have no per-tag author; do not invent one from the export actor.
                        tags = [{'user': '', 'tag': tag, 'profile_uuid': '', 'scope': 'protocol'} for tag in curation.get('tags', [])]
                        tags += [{'user': tag['author_name'], 'tag': tag['tag'], 'profile_uuid': tag['profile_uuid'], 'scope': 'epoch'}
                                 for tag in annotations.get(('epoch', key), {}).get('tags', [])]
                        grouping = {}
                        for index, field in enumerate(order, 1):
                            # Canonical JSON keeps bool/string/number/array/null
                            # distinct; a missing value gets its own sentinel.
                            grouping[f'g{index:03}'] = _grouping_value(values[key], field)
                        epoch_items.append({'id': epoch_index, 'h5_uuid': key, 'label': epoch_meta.get('label') or '',
                            'start_time': row['start_time'], 'end_time': epoch_meta.get('end_time') or '',
                            'parameters': _params(detail.get('parameters', {}), warnings),
                            'tags': _structs(tags), 'responses': _structs(streams['responses']), 'stimuli': _structs(streams['stimuli']),
                            'h5_file': source['source_path'], 'source_sha256': source_sha,
                            'source_metadata_json': _json(detail), 'curation_json': _json(curation),
                            'workspace_annotations_json': _json(records.get(key, {}).get('annotations')),
                            'workspaceGrouping': grouping})
                        epoch_order.append(key)
                    block_items.append({'id': block_index, 'h5_uuid': block_uuid, 'label': block_meta.get('label') or '',
                        'protocol_name': block_rows[0]['protocol_name'], 'protocol_id': block_meta.get('protocolID') or '',
                        'start_time': block_meta.get('start_time') or '', 'end_time': block_meta.get('end_time') or '',
                        'parameters': _params(block_meta.get('parameters', {}), warnings), 'tags': _structs([]),
                        'source_metadata_json': _json(block_meta), 'epochs': _structs(epoch_items)})
                group_items.append({'id': group_index, 'h5_uuid': group_uuid, 'label': first.get('group_label') or '',
                    'protocol_name': group_meta.get('protocolID') or '', 'protocol_id': group_meta.get('protocolID') or '',
                    'start_time': group_meta.get('start_time') or '', 'end_time': group_meta.get('end_time') or '',
                    'tags': _structs([]), 'source_metadata_json': _json(group_meta), 'epoch_blocks': _structs(block_items)})
            cell_items.append({'id': cell_index, 'h5_uuid': cell_uuid, 'label': representative['cell_label'],
                'type': representative.get('cell_type') or '', 'tags': _structs([
                    {'user': tag['author_name'], 'tag': tag['tag'], 'profile_uuid': tag['profile_uuid'], 'scope': 'cell'}
                    for tag in annotations.get(('cell', cell_uuid), {}).get('tags', [])]),
                'properties': _params(cell_meta.get('properties', {}), warnings),
                'source_metadata_json': _json(cell_meta), 'epoch_groups': _structs(group_items)})
        if source_meta.get('rig_type') == 'MEA':
            raise ValueError('MEA export is not supported by this adapter')
        experiments.append({'id': exp_index, 'h5_uuid': experiment_uuid, 'exp_name': source_meta.get('label') or source.get('filename', ''),
            'is_mea': False, 'label': source_meta.get('label') or '', 'experimenter': source_meta.get('experimenter') or '',
            'rig': source_meta.get('rig') or '', 'institution': source_meta.get('institution') or '',
            'h5_file': source['source_path'], 'source_sha256': source_sha, 'source_metadata_json': _json(source_meta),
            'tags': _structs([]), 'cells': _structs(cell_items)})
    # Source timestamps include microseconds in a format MATLAB's datenum does
    # not reliably parse. Freeze exact UI sequencing as UUIDs, independently of
    # MAT hierarchy order (which is also the UGM positional/index order).
    epoch_sequence = [row['epoch_uuid'] for row in sorted(rows, key=lambda row:
        (row['date'], row['start_time'][11:], row['epoch_uuid']))]
    metadata = {'created_date': recipe['created_at'], 'data_source': 'Recording workspace; lazy H5 references',
                'export_user': recipe['actor'], 'dataset_uuid': recipe['export_uuid'], 'recipe_json': _json(recipe),
                'split_mapping_json': _json(mapping), 'split_value_order_json': _json(_grouping_order(rows, values, order)), 'epoch_order': np.array(epoch_order, dtype=object),
                'epoch_sequence_json': _json(epoch_sequence),
                'workspace_tags_json': _json(frozen_document(frozen_tag_records, service.project['project_uuid'])),
                'split_display_json': _json(display),
                'id_semantics': 'Numeric IDs are display ordinals; h5_uuid preserves acquisition identity.'}
    buffer = io.BytesIO()
    scipy.io.savemat(buffer, {'format_version': '1.0', 'metadata': metadata, 'experiments': _structs(experiments)},
                     do_compression=True, long_field_names=True, oned_as='row')
    root = str(Path(__file__).resolve().parents[1]).replace("'", "''")
    command = matlab_tree_command(order)
    split_literal = matlab_split_fields(order)
    script = f"""% Generated frozen selection; edit EpicTreeGUI location if moving computers.
epicTreeRoot = '{root}';
addpath(genpath(epicTreeRoot));
exportFolder = fileparts(mfilename('fullpath'));
addpath(exportFolder);
% Resolve readable split IDs through this bundle's verified field mapping.
[tree, gui] = launchWorkspaceTree(fullfile(exportFolder, 'recordings.mat'), {split_literal});
"""
    helper = Path(__file__).resolve().parents[1] / 'src' / 'tree' / 'launchWorkspaceTree.m'
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {'recordings.mat': buffer.getvalue(), 'launch_epictree.m': script.encode(),
             'matlab_recipe.json': (_json(recipe) + '\n').encode(),
             'launchWorkspaceTree.m': helper.read_bytes(),
             'tree_layout.m': ('% Run from this extracted EpicTreeGUI bundle.\n'+command+'\n').encode()}
    files['annotations.json'] = (_json(frozen_document(frozen_tag_records, service.project['project_uuid'])) + '\n').encode()
    for helper_name in ('readWorkspaceTags', 'validateWorkspaceTags', 'workspaceTag', 'writeWorkspaceTags'):
        files[helper_name + '.m'] = (helper.parent / (helper_name + '.m')).read_bytes()
    if any((output / name).exists() for name in files):
        raise ValueError('MATLAB export files already exist; refusing overwrite')
    written = []
    try:
        for name, content in files.items():
            path = output / name
            with path.open('xb') as handle:
                handle.write(content)
            written.append(path)
    except Exception:
        for path in written:
            path.unlink()
        raise
    return {'mat_path': str(output / 'recordings.mat'), 'launch_script_path': str(output / 'launch_epictree.m'),
            'recipe_path': str(output / 'matlab_recipe.json'), 'epoch_count': len(ids), 'epoch_order': epoch_order,
            'source_revisions': sorted(used_sources), 'split_mapping': mapping, 'matlab_command': command, 'warnings': sorted(warnings)}
