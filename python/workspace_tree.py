"""Discover grouping fields from validated metadata, without reading waveforms.

Field IDs are opaque, case-sensitive, escaped paths into known metadata only.
Neither expressions nor SQL are evaluated. Grouping never selects membership.
"""
from __future__ import annotations

import json
import re
import math
from functools import lru_cache
from urllib.parse import quote, unquote
import copy
from collections.abc import Mapping


class StreamingValueView(Mapping):
    """Project or derive fields without retaining an epoch-by-field matrix."""
    def __init__(self, values, allowed=None, combinations=None):
        self.base, self.allowed, self.combinations = values, allowed, combinations or {}

    def _row(self, value):
        result = dict(value) if self.allowed is None else {key: item for key, item in value.items() if key in self.allowed}
        for key, components in self.combinations.items():
            result[key] = joint_value(value, components)
        return result

    def __getitem__(self, key):
        return self._row(self.base[key])

    def __iter__(self):
        return iter(self.base)

    def __len__(self):
        return len(self.base)

    def items(self):
        return ((key, self._row(value)) for key, value in self.base.items())

    def values(self):
        return (self._row(value) for value in self.base.values())

BASE_FIELDS = {
    'epoch': ('Epoch UUID', 'Recording', 'epoch_uuid'),
    'date': ('Recording date', 'Recording', 'date'),
    'cell': ('Cell', 'Recording', 'cell_uuid'),
    'block': ('Epoch block', 'Recording', 'block_uuid'),
    'block time': ('Block start time', 'Recording', 'block_start_time'),
    'cell type': ('Cell type', 'Conditions', 'cell_type'),
    'group label': ('Recorded group label', 'Conditions', 'group_label'),
    'group': ('Epoch group', 'Recording', 'group_uuid'),
    'protocol': ('Acquisition protocol', 'Recording', 'protocol_name'),
}


def humanize(value):
    words = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', value).replace('_', ' ').split()
    label = ' '.join(word if word.isupper() else word.lower() for word in words)
    return label[:1].upper() + label[1:]


def field_id(path):
    # JSON Pointer escaping keeps literal slash/tilde keys distinct. Percent
    # escaping keeps commas and arrows out of the legacy split-list separator.
    return '/'.join(quote(str(key).replace('~', '~0').replace('/', '~1'), safe='~') for key in path)


def joint_id(components):
    if (not isinstance(components, (list, tuple)) or not 2 <= len(components) <= 6
            or any(not isinstance(field, str) or not field or len(field) > 2048 or field.startswith('joint/') for field in components)
            or len(set(components)) != len(components)):
        raise ValueError('A joint grouping needs 2–6 distinct non-composite recorded fields')
    identity = 'joint/' + '+'.join(quote(field, safe="~()*!.'-") for field in components)
    if len(identity) > 8192:
        raise ValueError('Joint grouping identifier is too long')
    return identity


def joint_components(identity, allowed_fields=None):
    if not isinstance(identity, str) or not identity.startswith('joint/') or len(identity) > 8192:
        raise ValueError('Invalid joint grouping identifier')
    try:
        parts = [unquote(part, errors='strict') for part in identity[6:].split('+')]
        if joint_id(parts) != identity:
            raise ValueError('Joint grouping identifier must use canonical encoded fields')
    except UnicodeError as error:
        raise ValueError('Malformed joint grouping encoding') from error
    if allowed_fields is not None and any(field not in allowed_fields for field in parts):
        raise ValueError('Joint grouping contains an unknown recorded field')
    return parts


HISTORY_COMPONENTS = ['parameters/history1', 'parameters/history2', 'parameters/target']
HISTORY_JOINT = joint_id(HISTORY_COMPONENTS)


def joint_value(current, components):
    return [{'present': True, 'value': current[field]} if field in current else {'present': False}
            for field in components]


def field_value_order(field, value):
    if field.startswith('joint/'):
        def component_order(current):
            if isinstance(current,list):
                return (3,tuple(component_order(item) for item in current))
            if isinstance(current,dict):
                return (5,value_key(current))
            return value_order(current)
        return tuple((0, component_order(part['value'])) if part['present'] else (1,) for part in value)
    return value_order(value)


def component_display(field, value, missing=False):
    if missing:
        return 'Not recorded'
    if value is None:
        return 'null (recorded)'
    if field in HISTORY_COMPONENTS and isinstance(value, list) and len(value) == 2 and all(type(part) in (int,float) for part in value):
        return f'Mean {value_label(value[0])} · SD {value_label(value[1])}'
    return value_label(value)


def joint_definition(identity, definitions):
    components = joint_components(identity, definitions)
    return {'id': identity, 'label': 'History 1 + History 2 + Target' if components == HISTORY_COMPONENTS else
            ' + '.join(definitions[field]['label'] for field in components),
            'path': identity, 'category': 'Combinations', 'components': components}


def _joint_summary(definition, values):
    key, components = definition['id'], definition['components']
    distinct = {value_key(current[key]): current[key] for current in values.values()}
    missing = sum(any(not item['present'] for item in current[key]) for current in values.values())
    recorded = sum(all(item['present'] for item in value) for value in distinct.values())
    samples = sorted(distinct.values(), key=lambda value: field_value_order(key,value))
    examples = ['; '.join(component_display(field,part.get('value'),not part['present']) for field,part in zip(components,value))[:160]
                for value in samples[:5]]
    return {**definition, 'distinct_count': len(distinct), 'recorded_distinct_count': recorded,
            'missing_count': missing, 'null_count': 0, 'count': len(values), 'varying': len(distinct)>1,
            'examples': examples, 'grouping_role': 'primary' if key==HISTORY_JOINT else 'other',
            'grouping_priority': 1 if key==HISTORY_JOINT else 100,
            'grouping_hint': 'One level: epochs share a branch only when every component matches exactly.',
            'suggested_rank': None, 'suggestion_reason': '', 'high_cardinality': len(distinct)>24}


def materialize_combinations(field_catalog, values, requested):
    """Add only explicitly requested joint fields; do not mutate cached catalogs."""
    definitions = {field['id']: field for field in field_catalog['fields']}
    extra = [key for key in requested if key.startswith('joint/') and key not in definitions]
    if not extra:
        return field_catalog, values
    result = copy.deepcopy(field_catalog)
    data = ({key: dict(current) for key,current in values.items()} if isinstance(values, dict)
            else StreamingValueView(values, combinations={key: joint_components(key, definitions) for key in extra}))
    for identity in extra:
        definition = joint_definition(identity, definitions)
        if isinstance(data, dict):
            for current in data.values():
                current[identity] = joint_value(current,definition['components'])
        result['fields'].append(_joint_summary(definition,data))
        definitions[identity] = definition
    return result,data


def predicate_scope(field_catalog, values):
    """Combinations organize trees; they are never source predicate fields."""
    fields = [field for field in field_catalog['fields'] if not field['id'].startswith('joint/')]
    allowed = {field['id'] for field in fields}
    layout = field_catalog.get('suggested_layout')
    scoped_values = ({identity: {key:value for key,value in current.items() if key in allowed}
                      for identity,current in values.items()} if isinstance(values, dict)
                     else StreamingValueView(values, allowed=allowed))
    return {**field_catalog, 'fields': fields, 'suggestions': [key for key in field_catalog.get('suggestions',[]) if key in allowed],
        'presets': [preset for preset in field_catalog.get('presets',[]) if set(preset['fields']) <= allowed],
        'suggested_layout': layout if layout and set(layout['fields']) <= allowed else None}, scoped_values


@lru_cache(maxsize=4096, typed=True)
def _scalar_value_key(value, negative_zero):
    # negative_zero distinguishes -0.0 from 0.0 despite Python numeric equality.
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def value_key(value):
    if (value is None or type(value) in (bool, float)
            or type(value) is int and value.bit_length() <= 256
            or type(value) is str and len(value) <= 512):
        signed_zero = type(value) is float and value == 0 and math.copysign(1., value) < 0
        return _scalar_value_key(value, signed_zero)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def value_label(value):
    if value is None:
        return 'Not recorded'
    if value == '' and isinstance(value, str):
        return '"" (empty recorded value)'
    return value_key(value)


def value_order(value):
    if value is None:
        return (4, '')
    if type(value) in (int, float):
        return (0, value, value_key(value))
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, str):
        return (2, value)
    return (3, value_key(value))


def _leaves(value, path, depth=0):
    if isinstance(value, dict) and depth < 5:
        for key, child in sorted(value.items()):
            yield from _leaves(child, (*path, str(key)), depth + 1)
    elif value is None or isinstance(value, (str, int, float, bool, list)):
        # Large sampled vectors are not useful interactive grouping fields.
        if isinstance(value, list) and len(value) > 32:
            return
        if len(value_key(value)) <= 1024:
            yield path, value


def _descriptive_metadata(metadata):
    """Recorded descriptions only; exclude waveforms and precise clock ticks."""
    result = {key: metadata[key] for key in
              ('label', 'notes', 'comment', 'comments', 'keywords', 'purpose',
               'start_time', 'end_time', 'protocolID') if key in metadata}
    attributes = metadata.get('attributes', {})
    selected = {key: attributes[key] for key in ('purpose', 'comment', 'comments', 'keywords')
                if key in attributes}
    if selected:
        result['attributes'] = selected
    return result


def catalog(rows, details, known_fields=None, *, sources=()):
    """Return field summaries and per-epoch values for a fixed metadata scope."""
    definitions = {key: {'id': key, 'label': label, 'category': category, 'path': path}
                   for key, (label, category, path) in BASE_FIELDS.items()}
    for field in known_fields or []:
        definitions[field['id']] = {key: field[key] for key in ('id', 'label', 'category', 'path', 'components') if key in field}
    # Source metadata is already checksum-verified by the service. Keep it
    # separate from epoch details: adding discovery fields must not invalidate
    # existing scientific fingerprints or curation decisions.
    experiments = {source['source_sha256']: source.get('metadata', {}) for source in sources}
    # Recorded paths repeat across epochs. Resolve labels/escaped IDs once per
    # build; the first observed value still replaces any known-field template.
    path_ids = {}
    categories = {'experiment': 'Experiment', 'cell': 'Cell', 'group': 'Epoch group',
                  'block': 'Epoch block', 'epoch': 'Epoch'}
    values = {}
    for row in rows:
        identity = row['epoch_uuid']
        datum = details[identity]
        current = {key: row.get(path) for key, (_, _, path) in BASE_FIELDS.items()}
        metadata_sources = [('Parameters', ('parameters',), datum.get('parameters', {})),
                   ('Conditions', ('properties',), datum.get('properties', {}))]
        for level in ('cell', 'group', 'block'):
            ancestor = datum.get('metadata', {}).get(level, {})
            metadata_sources.append(('Conditions', ('metadata', level, 'properties'), ancestor.get('properties', {})))
        levels = {'experiment': experiments.get(row.get('source_sha256'), {}),
                  **{level: datum.get('metadata', {}).get(level, {}) for level in ('cell', 'group', 'block', 'epoch')}}
        for level, metadata in levels.items():
            metadata_sources.append((categories[level], ('metadata', level), _descriptive_metadata(metadata)))
        metadata_sources.append(('Experiment', ('metadata', 'experiment', 'properties'),
                                 levels['experiment'].get('properties', {})))
        metadata_sources.append(('Parameters', ('metadata', 'block', 'parameters'),
                                 levels['block'].get('parameters', {})))
        for category, root, content in metadata_sources:
            for path, value in _leaves(content, root):
                key = path_ids.get(path)
                if key is None:
                    key = path_ids[path] = field_id(path)
                    prefix = f'{categories[path[1]]} · ' if path[0] == 'metadata' else ('Epoch · ' if path[0] == 'properties' else '')
                    definitions[key] = {'id': key, 'label': prefix + humanize(path[-1]),
                                        'category': category, 'path': '.'.join(path)}
                current[key] = value
        values[identity] = current
    if all(field in definitions for field in HISTORY_COMPONENTS):
        definitions[HISTORY_JOINT] = joint_definition(HISTORY_JOINT, definitions)
    for key, definition in list(definitions.items()):
        if key.startswith('joint/'):
            definition.update(joint_definition(key,definitions))
            for current in values.values():
                current[key] = joint_value(current,definition['components'])
    fields = []
    for key, definition in definitions.items():
        if definition.get('components'):
            fields.append(_joint_summary(definition,values))
            continue
        distinct = {}
        missing = nulls = 0
        for current in values.values():
            value = current.get(key)
            missing += key not in current
            nulls += key in current and value is None
            if key in current:
                distinct.setdefault(value_key(value), value)
        samples = sorted(distinct.values(), key=value_order)
        examples = [('null (recorded)' if value is None else value_label(value))[:160] for value in samples[:5]]
        if key in {'cell', 'block', 'group'}:
            labels = {row.get(BASE_FIELDS[key][2]): (
                f"{row.get('date', '')} · {row.get('cell_label', 'Cell')}" if key == 'cell' else
                row.get('block_start_time') if key == 'block' else row.get('group_label')) for row in rows}
            examples = [str(labels.get(value) or value)[:160] for value in samples[:5]]
        recorded_distinct = sum(value is not None for value in distinct.values())
        fields.append({**definition, 'distinct_count': len(distinct), 'missing_count': missing,
                       'recorded_distinct_count': recorded_distinct, 'varying': recorded_distinct > 1,
                       'null_count': nulls, 'count': len(rows), 'examples': examples})
    field_ids = set(definitions)
    presets = [{'id': 'recording', 'label': 'Date → cell → block', 'fields': ['date', 'cell', 'block']},
               {'id': 'conditions', 'label': 'Date → cell type → group label',
                'fields': ['date', 'cell type', 'group label']}]
    if 'parameters/frequencyCutoff' in field_ids:
        presets.append({'id': 'frequency', 'label': 'Date → cutoff → cell',
                        'fields': ['date', 'parameters/frequencyCutoff', 'cell']})
    if 'parameters/currentMean' in field_ids:
        presets.append({'id': 'current', 'label': 'Cell → current mean → block',
                        'fields': ['cell', 'parameters/currentMean', 'block']})
    for name, label, sequence in (
        ('noise', 'Cell → cutoff → current SD → block', ['cell', 'parameters/frequencyCutoff', 'parameters/currentSD', 'block']),
        ('spots', 'Cell → spot size → block', ['cell', 'parameters/currentSpotSize', 'block']),
        ('history', 'Cell → history mean → history SD → target SD → block', ['cell', 'parameters/history1Mean', 'parameters/history1SD', 'parameters/targetSD', 'block']),
    ):
        if set(sequence) <= field_ids:
            presets.append({'id': name, 'label': label, 'fields': sequence})
    if HISTORY_JOINT in field_ids:
        presets.append({'id':'history-joint','label':'Cell → control → joint history settings → block',
            'fields':['cell', *(['parameters/isControl'] if 'parameters/isControl' in field_ids else []), HISTORY_JOINT, 'block']})
    family = protocol_family(rows)
    annotate_grouping_fields(fields, values, rows, family)
    suggestions = suggest_fields(fields, values, family)
    suggested_layout = protocol_layout(fields, suggestions, family)
    if suggested_layout:
        presets.insert(0, suggested_layout)
    return {'fields': fields, 'total': len(rows), 'presets': presets, 'suggestions': suggestions,
            'protocol_family': family, 'suggested_layout': suggested_layout,
            'suggestion_basis': 'Variation in recorded metadata; these suggestions do not infer scientific meaning.'}, values


def suggest_fields(fields, values, family=None):
    """Rank manageable, varying metadata fields; never invent treatment labels."""
    priority = {'protocol': 0, 'date': 1, 'cell type': 2, 'group label': 3,
                'parameters/frequencyCutoff': 4, 'parameters/currentSD': 5,
                'parameters/currentMean': 6, 'parameters/currentSpotSize': 7,
                'cell': 8, 'parameters/useRandomSeed': 9}
    if family:
        priority = {key: index for index, key in enumerate(PROTOCOL_AXES[family])}
    candidates = []
    for field in fields:
        field['suggested_rank'] = None
        field['suggestion_reason'] = ''
        count = field['recorded_distinct_count']
        # Timestamps, identity-like seeds and almost unique values remain
        # searchable but do not crowd the beginner's starting suggestions.
        high_cardinality = count > 24 or count > max(5, len(values) * .25)
        field['high_cardinality'] = high_cardinality
        if not field['varying'] or high_cardinality or field.get('grouping_role') == 'technical' or field['id'] in {'epoch', 'block', 'block time', 'group'}:
            continue
        if field['id'].rsplit('/', 1)[-1].lower() in {'seed', 'uuid', 'id'}:
            continue
        candidates.append(field)
    candidates.sort(key=lambda field: (priority.get(field['id'], 20 if field['category'] == 'Parameters' else 30),
                                        not field.get('varies_within_cell',False),
                                        field['missing_count'], field['recorded_distinct_count'], field['id']))
    seen, suggestions = set(), []
    for field in candidates:
        signature = tuple(value_key(current[field['id']]) if field['id'] in current else '__missing__'
                          for current in values.values())
        if signature in seen:
            continue
        # Prefer effective epoch parameters over a block-level alias. Distinct
        # named experimental axes may coincide; only generic suggestions dedupe them.
        if family and field['id'].startswith('metadata/block/parameters/') and 'parameters/'+field['id'].rsplit('/',1)[-1] in {f['id'] for f in candidates}:
            continue
        if not family or field['id'] not in priority:
            seen.add(signature)
        field['suggested_rank'] = len(suggestions)
        field['suggestion_reason'] = f"{field['recorded_distinct_count']} recorded values across {field['count']} epochs"
        if field.get('varies_within_cell'):
            field['suggestion_reason'] += '; varies within cells'
        if field['missing_count']:
            field['suggestion_reason'] += f"; {field['missing_count']} missing stay visible"
        suggestions.append(field['id'])
        if len(suggestions) == 6:
            break
    return suggestions


PROTOCOL_AXES = {
    'history-noise': ['parameters/isControl',HISTORY_JOINT,'parameters/segmentTime','parameters/frequencyCutoff',
        'parameters/history1','parameters/history2','parameters/target',
        'parameters/history1Mean','parameters/history1SD','parameters/history2Mean',
        'parameters/history2SD','parameters/targetMean','parameters/targetSD','parameters/useRandomSeed'],
    'mean-noise': ['parameters/frequencyCutoff','parameters/currentMean','parameters/currentSD','parameters/useRandomSeed'],
}
TECHNICAL_PARAMETERS = {'amp','NDF','ndfs','gain','canvasSize','trueCanvasSize','centerOffset',
    'numberOfAverages','blockRepeatCount','numberOfTrials','numberOfTrialsInRun','repeatsPerTrial',
    'trialNumber','samplesPerBlock','samplesPerSegment','sampleRate','stimulusSampleRate',
    'stimulusGenerator','stimulusGeneratorVersion','historyNoiseVersion','firstHistoryID',
    'lightPath','microdisplayBrightness','microdisplayBrightnessValue','micronsPerPixel',
    'monitorRefreshRate','prerender','controlMode','stdv'}


def protocol_family(rows):
    names = {str(row.get('protocol_name','')).rsplit('.',1)[-1] for row in rows}
    return {'VariableHistoryNoiseCurInject':'history-noise',
            'VariableMeanNoiseCurInject':'mean-noise'}.get(next(iter(names))) if len(names)==1 else None


def annotate_grouping_fields(fields, values, rows, family):
    axes = PROTOCOL_AXES.get(family, [])
    row_cells = {row['epoch_uuid']: row.get('cell_uuid') for row in rows}
    for field in fields:
        key = field['id']; leaf = key.rsplit('/',1)[-1]
        technical = (key.startswith(('parameters/','metadata/block/parameters/')) and
                     (leaf in TECHNICAL_PARAMETERS or leaf.lower().endswith('seed')) and leaf!='useRandomSeed')
        role = 'technical' if technical else 'other'
        if key in axes:
            role = 'alternative' if family=='history-noise' and key not in {'parameters/isControl',HISTORY_JOINT,'parameters/segmentTime','parameters/frequencyCutoff'} else 'primary'
        if key in BASE_FIELDS: role = 'context'
        field['grouping_role'] = role
        field['grouping_priority'] = axes.index(key) if key in axes else 100
        per_cell = {}
        varies = False
        for identity, datum in values.items():
            if key in datum and datum[key] is not None:
                distinct = per_cell.setdefault(row_cells.get(identity), set())
                distinct.add(value_key(datum[key]))
                if len(distinct) > 1:
                    varies = True
                    break
        field['varies_within_cell'] = varies
        if family=='history-noise':
            labels = {'history1':'History 1 · mean / SD','history2':'History 2 · mean / SD',
                      'target':'Target · mean / SD','isControl':'Control epoch','segmentTime':'Segment duration'}
            if key.startswith('parameters/') and leaf in labels:
                field['label'] = labels[leaf]
            if key in {'parameters/history1','parameters/history2','parameters/target'}:
                field['grouping_hint'] = 'Recorded [mean, SD]; control epochs deliver target only.'
            elif key=='parameters/isControl':
                field['grouping_hint'] = 'Recorded protocol control flag; separate from drug or bath conditions.'


def protocol_layout(fields, suggestions, family):
    if not family:
        return None
    by_id = {field['id']:field for field in fields}
    if family=='history-noise' and HISTORY_JOINT in by_id:
        axes = [key for key in ('parameters/isControl',HISTORY_JOINT,'parameters/segmentTime') if key in by_id]
    else:
        axes = [key for key in suggestions if by_id[key]['grouping_role']=='primary'][:4]
    if not axes:
        return None
    sequence = ['date','cell type','cell',*axes,'block']
    return {'id':'protocol-suggested','label':'Date → Cell type → Cell → protocol settings → Block',
            'fields':sequence,'description':'Split by settings that vary in this selection; keep acquisition blocks separate.'}
