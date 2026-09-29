"""Lazy, source-verified cell inspection; no pass/fail classification or raw writes."""
from __future__ import annotations

import copy
import math
from pathlib import Path
import uuid

import numpy as np

from workspace_recipes import checksum

FAMILIES = {
    'expanding_spots': ('Expanding spots', {'ExpandingSpots'}),
    'split_field': ('Split-field centering', {'SplitFieldCentering'}),
    'single_spot': ('Single spot / light step', {'SingleSpot'}),
    'current_step': ('Current steps', {'CurrentStep', 'CurrentPulse', 'CurrentInjectionStep'}),
    'current_noise': ('Injected-current noise', {'VariableMeanNoiseCurInject', 'VariableHistoryNoiseCurInject'}),
    'other': ('Other recorded protocols', set()),
}
RESISTANCE_FIELDS = {'inputResistance', 'seriesResistance', 'accessResistance', 'membraneResistance'}
BASELINE_METHOD = {
    'id': 'block_onset_voltage_review_v1',
    'label': 'First-epoch block-onset voltage estimate (not validated resting Vm)',
    'window_ms': 1.0, 'sensitivity_windows_ms': [0.5, 2.0],
    'minimum_epochs_per_block': 2,
    'references': [
        'retinaSRM/compute_vrest_baseline_drift.m',
        'retinaSRM/compute_vmn_block_baseline.m',
        'retinaSRM/vbaseline_interp.m',
        'Wheeler F-447a4b02 / S-489e6b8b / S-464cfc16'],
    'flags': {'first_sample_outside_reference_range': 'V[0] < -75 mV or V[0] > -45 mV',
              'possible_spike_first_2ms': 'max(V[0:2 ms]) > -20 mV'},
    'interpretation': 'Reference-method contamination flags, not a cell-quality pass/fail. Without explicit preTime, the window begins at stimulus onset and is only an approximation to the pre-block state.',
}
RESTING_REASON = ('No validated cell-specific baseline interpolant is registered for this recording. '
    'Historical five-cell knots are not reused. Review new block-onset estimates before deriving a drift curve; never extrapolate beyond validated anchors.')


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def family(row):
    name = row['protocol_name'].rsplit('.', 1)[-1]
    return next((key for key, (_, names) in FAMILIES.items() if name in names), 'other')


def stats(values):
    return {'mean': float(np.mean(values)), 'std': float(np.std(values)), 'n': len(values)} if len(values) else None


class CellQC:
    def __init__(self, service):
        self.service = service

    def rows(self, cell_uuid):
        self.service._ready()
        identity = str(uuid.UUID(cell_uuid))
        if identity not in self.service.cells:
            raise KeyError('Cell is not in the main project catalog')
        return sorted((row for row in self.service.rows.values() if row['cell_uuid'] == identity),
                      key=lambda row: (row['date'], row['start_time'][11:], row['epoch_uuid']))

    def _params(self, row):
        return self.service.details[row['epoch_uuid']].get('parameters', {})

    def _metadata_values(self, rows, fields):
        measurements, seen = [], set()
        for row in rows:
            metadata = self.service.details[row['epoch_uuid']].get('metadata', {})
            for scope in ('cell', 'group', 'block', 'epoch'):
                source = metadata.get(scope, {})
                entity = source.get('uuid') or row.get(scope + '_uuid') or row['epoch_uuid']
                for category in ('properties', 'parameters', 'attributes'):
                    values = (self.service.details[row['epoch_uuid']].get(category, {}) if scope == 'epoch'
                              else source.get(category, {}))
                    for name in fields & values.keys():
                        raw = values[name]
                        value = raw.get('quantity') if isinstance(raw, dict) else raw
                        units = raw.get('units') if isinstance(raw, dict) else values.get(name + 'Units')
                        key = (scope, entity, category, name, checksum(raw))
                        if key in seen:
                            continue
                        seen.add(key)
                        measurements.append({'field': f'{scope}.{category}.{name}', 'scope': scope,
                            'entity_uuid': entity, 'epoch_uuid': row['epoch_uuid'],
                            'value': value, 'units': units, 'numeric': number(value),
                            'source_sha256': row['source_sha256']})
        return measurements

    def overview(self, cell_uuid):
        rows = self.rows(cell_uuid)
        cell = self.service.cells[str(uuid.UUID(cell_uuid))]
        points = []
        for row in rows:
            value = self.service.details[row['epoch_uuid']].get('properties', {}).get('bathTemperature')
            if number(value):
                points.append({'epoch_uuid': row['epoch_uuid'], 'start_time': row['start_time'],
                    'value': value, 'group_label': row.get('group_label'), 'source_sha256': row['source_sha256']})
        measured = self._metadata_values(rows, RESISTANCE_FIELDS)
        compensation = self._metadata_values(rows, {'seriesResistanceCompensation'})
        has_resistance = any(item['numeric'] for item in measured)
        block_count = len({r['block_uuid'] for r in rows if family(r) == 'current_noise'})
        families = []
        for key, (label, _) in FAMILIES.items():
            members = [r for r in rows if family(r) == key]
            families.append({'id': key, 'label': label, 'epoch_count': len(members),
                'blocks': len({r['block_uuid'] for r in members}),
                'protocol_names': sorted({r['protocol_name'] for r in members})})
        return {'cell': copy.deepcopy(cell), 'scope': 'main_catalog_same_cell_uuid',
            'scope_note': 'All recorded epochs for this cell UUID, including epochs outside protocol working sets and local inclusion masks.',
            'counts': {'epochs': len(rows), 'blocks': len({r['block_uuid'] for r in rows}),
                'groups': len({r['group_uuid'] for r in rows}), 'protocols': len({r['protocol_name'] for r in rows})},
            'temperature': {'status': 'recorded' if points else 'unavailable',
                'field': 'epoch.properties.bathTemperature', 'units': None, 'unit_basis': 'not_recorded',
                'range': {'min': min(p['value'] for p in points), 'max': max(p['value'] for p in points)} if points else None,
                'recorded_count': len(points), 'missing_count': len(rows) - len(points),
                'points': points[:500], 'truncated': len(points) > 500},
            'resistance': {'status': 'recorded' if has_resistance else 'unavailable', 'measurements': measured,
                'compensation_settings': compensation,
                'reason': None if has_resistance else 'No numeric measured input, access, series or membrane resistance was recorded. Series-resistance compensation is an amplifier setting, not a resistance measurement.'},
            'resting_voltage': {'status': 'unavailable', 'label': 'Resting membrane voltage',
                'reason': RESTING_REASON, 'method': copy.deepcopy(BASELINE_METHOD), 'candidate_blocks': block_count},
            'families': families,
            'characteristics': {'recorded_cell_type': cell.get('cell_type'),
                'group_labels': sorted({r.get('group_label') for r in rows}, key=str),
                'source_revisions': sorted({r['source_sha256'] for r in rows})},
            'analysis_capabilities': [
                {'id': 'recorded_response', 'status': 'available', 'reason': 'Lazy full-rate response windows with source UUID, SHA256, units and sample-count checks.'},
                {'id': 'condition_response_summary', 'label': 'Recorded response summary', 'status': 'available', 'reason': 'Raw signal window means in the recorded stream units, grouped within acquisition block and exact parameters; no event classification, firing-rate or receptive-field interpretation.'},
                {'id': 'spike_rate_receptive_field', 'status': 'unvalidated_adapter', 'reason': 'RetinAnalysis ExpandingSpotsPipeline.get_stim_nspikes/plot_rf exists, but spike detector and acquisition/clamp configuration need validation before automatic QC use.'},
                {'id': 'baseline_drift_interpolant', 'status': 'unavailable', 'reason': RESTING_REASON}]}

    def epochs(self, cell_uuid, family_id=None, offset=0, limit=50):
        if family_id is not None and family_id not in FAMILIES:
            raise ValueError('Unknown QC protocol family')
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('QC epoch page requires nonnegative offset and limit 1–100')
        rows = [r for r in self.rows(cell_uuid) if family_id is None or family(r) == family_id]
        values = [{**copy.deepcopy(row), 'parameters': copy.deepcopy(self._params(row)),
            'source_filename': Path(self.service.manifests[row['source_sha256']]['source_path']).name}
            for row in rows[offset:offset+limit]]
        return {'epochs': values, 'total': len(rows), 'offset': offset, 'limit': limit,
                'has_more': offset + limit < len(rows)}

    def _response_stream(self, row, stream_uuid=None):
        streams = [s for s in row.get('streams', []) if s['kind'] == 'responses']
        if stream_uuid is not None:
            streams = [s for s in streams if s['uuid'] == str(uuid.UUID(stream_uuid))]
        else:
            amp = self._params(row).get('amp', 'Amp1')
            streams = [s for s in streams if s.get('device') == amp]
        if len(streams) != 1:
            raise ValueError('Choose one recorded response stream for this epoch; no channel was guessed')
        stream = streams[0]
        if (not number(stream.get('sample_rate')) or stream['sample_rate'] <= 0
                or type(stream.get('sample_count')) is not int or stream['sample_count'] < 1
                or stream.get('sample_rate_units') != 'Hz'):
            raise ValueError('QC requires a nonempty response with a positive sample rate explicitly recorded in Hz')
        return stream

    def response(self, cell_uuid, epoch_uuid, stream_uuid=None):
        identity = str(uuid.UUID(epoch_uuid))
        row = next((r for r in self.rows(cell_uuid) if r['epoch_uuid'] == identity), None)
        if row is None:
            raise ValueError('Epoch does not belong to this cell UUID')
        stream = self._response_stream(row, stream_uuid)
        trace = self.service.trace(identity, stream['uuid'], 0, min(stream['sample_count'], 100000))
        parameters = self._params(row)
        timing = {name + '_ms': parameters.get(field) for name, field in
                  [('pre', 'preTime'), ('stim', 'stimTime'), ('tail', 'tailTime')]}
        pre, duration = timing['pre_ms'], timing['stim_ms']
        statistics = {'status': 'unavailable', 'reason': 'Complete nonnegative preTime and positive stimTime are required.',
                      'units': trace['units'], 'pre': None, 'stim': None, 'delta_mean': None}
        if number(pre) and pre >= 0 and number(duration) and duration > 0:
            rate = trace['sample_rate']
            a, b = math.floor(pre * rate / 1000 + 0.5), math.floor((pre + duration) * rate / 1000 + 0.5)
            if b <= trace['count'] and b > a:
                before, active = stats(trace['values'][:a]), stats(trace['values'][a:b])
                statistics.update(status='available', reason=None, pre=before, stim=active,
                    delta_mean=active['mean'] - before['mean'] if before else None)
            else:
                statistics['reason'] = 'The full stimulus window exceeds the bounded response preview; no partial-window mean is reported.'
        return {'epoch_uuid': identity, 'cell_uuid': row['cell_uuid'], 'trace': trace,
            'parameters': copy.deepcopy(parameters), 'timing': timing, 'statistics': statistics,
            'partial_trace': trace['count'] < trace['total_samples'],
            'method': {'id': 'recorded_window_response_v1',
                'label': 'Recorded response window mean and population SD',
                'interpretation': 'Raw signal samples in the recorded response units; no spike detection, stimulus reconstruction, baseline correction or resting-Vm claim.',
                'timing_source': 'Recorded epoch preTime/stimTime in ms; nearest-sample boundaries.'},
            'provenance': {'metadata_fingerprint': self.service._fingerprints[identity], 'source_sha256': row['source_sha256']}}

    def block_baselines(self, cell_uuid):
        rows = self.rows(cell_uuid)
        blocks = {}
        for row in rows:
            if family(row) == 'current_noise':
                blocks.setdefault(row['block_uuid'], []).append(row)
        anchors, excluded = [], []
        for block_uuid, members in list(blocks.items())[:500]:
            row = members[0]  # rows are chronological; never use later trials as independent anchors.
            reason = None
            if len(members) < 2:
                reason = 'Reference method requires at least two epochs in the acquisition block.'
            try:
                stream = self._response_stream(row)
                if stream.get('units') != 'mV':
                    reason = 'Reference method requires a recorded membrane-voltage response in mV.'
                rate = stream.get('sample_rate')
                if not number(rate) or rate <= 0:
                    reason = 'Invalid recorded sample rate.'
                if reason:
                    excluded.append({'block_uuid': block_uuid, 'epoch_uuid': row['epoch_uuid'], 'reason': reason})
                    continue
                count = math.ceil(rate * 0.002)
                if count < 2 or count > 2000 or stream['sample_count'] < count:
                    excluded.append({'block_uuid': block_uuid, 'epoch_uuid': row['epoch_uuid'], 'reason': 'Insufficient samples or unsupported rate for bounded 2 ms window.'})
                    continue
                trace = self.service.trace(row['epoch_uuid'], stream['uuid'], 0, count)
                values = np.asarray(trace['values'])
                n = max(1, math.floor(rate * 0.001 + 0.5))
                flags = {'first_sample_outside_reference_range': bool(values[0] < -75 or values[0] > -45),
                         'possible_spike_first_2ms': bool(values.max() > -20)}
                anchors.append({'epoch_uuid': row['epoch_uuid'], 'block_uuid': block_uuid,
                    'group_uuid': row['group_uuid'], 'group_label': row.get('group_label'),
                    'start_time': row['start_time'], 'mean_mV': float(values[:n].mean()),
                    'median_mV': float(np.median(values[:n])), 'first_mV': float(values[0]),
                    'max_2ms_mV': float(values.max()), 'flags': flags, 'sample_count': n,
                    'sensitivity': [{'window_ms': ms, 'mean_mV': float(values[:max(1, math.floor(rate*ms/1000+0.5))].mean())} for ms in (0.5, 2.0)],
                    'metadata_fingerprint': self.service._fingerprints[row['epoch_uuid']], 'source_sha256': row['source_sha256'],
                    'pre_time_ms': self._params(row).get('preTime'), 'epochs_in_block': len(members)})
            except (KeyError, ValueError, OSError) as error:
                excluded.append({'block_uuid': block_uuid, 'epoch_uuid': row['epoch_uuid'], 'reason': str(error)})
        return {'status': 'estimates_for_review' if anchors else 'unavailable', 'cell_uuid': str(uuid.UUID(cell_uuid)),
                'method': copy.deepcopy(BASELINE_METHOD), 'anchors': anchors, 'excluded_blocks': excluded,
                'total_blocks': len(blocks), 'truncated': len(blocks) > 500,
                'interpolation': {'status': 'unavailable', 'reason': RESTING_REASON}}

    def response_summary(self, cell_uuid, family_id, block_uuid=None):
        if family_id not in {'expanding_spots', 'split_field', 'single_spot', 'current_step'}:
            raise ValueError('Select a spot, split-field or current-step family for a condition response summary')
        rows = [r for r in self.rows(cell_uuid) if family(r) == family_id]
        if block_uuid is not None:
            block_uuid = str(uuid.UUID(block_uuid))
            rows = [r for r in rows if r['block_uuid'] == block_uuid]
            if not rows:
                raise ValueError('Block is outside this cell and QC family')
        conditions = {}
        for row in rows:
            key = checksum({'block_uuid': row['block_uuid'], 'parameters': self._params(row)})
            conditions.setdefault(key, []).append(row)
        points, skipped = [], []
        samples_used = 0
        for key, members in list(conditions.items())[:50]:
            measurements = []
            for row in members[:3]:
                try:
                    stream = self._response_stream(row)
                    cost = min(stream['sample_count'], 100000)
                    if samples_used + cost > 500000:
                        skipped.append({'epoch_uuid': row['epoch_uuid'], 'reason': '500,000-sample request budget reached.'})
                        continue
                    samples_used += cost
                    result = self.response(cell_uuid, row['epoch_uuid'], stream['uuid'])
                    if result['statistics']['status'] != 'available':
                        skipped.append({'epoch_uuid': row['epoch_uuid'], 'reason': result['statistics']['reason']})
                        continue
                    measurements.append({'epoch_uuid': row['epoch_uuid'], **result['statistics'],
                        'source_sha256': row['source_sha256'], 'metadata_fingerprint': self.service._fingerprints[row['epoch_uuid']]})
                except (KeyError, ValueError, OSError) as error:
                    skipped.append({'epoch_uuid': row['epoch_uuid'], 'reason': str(error)})
            units = {r['units'] for r in measurements}
            usable = bool(measurements) and len(units) == 1
            points.append({'condition_id': key, 'block_uuid': members[0]['block_uuid'],
                'group_uuid': members[0]['group_uuid'], 'group_label': members[0].get('group_label'),
                'parameters': copy.deepcopy(self._params(members[0])), 'epoch_count': len(members),
                'used_epoch_count': len(measurements), 'units': next(iter(units)) if usable else None,
                'response_mean': float(np.mean([r['stim']['mean'] for r in measurements])) if usable else None,
                'pre_mean': float(np.mean([r['pre']['mean'] for r in measurements])) if usable and all(r['pre'] for r in measurements) else None,
                'delta_mean': float(np.mean([r['delta_mean'] for r in measurements])) if usable and all(r['delta_mean'] is not None for r in measurements) else None,
                'status': 'available' if usable else 'unavailable', 'measurements': measurements})
        return {'cell_uuid': str(uuid.UUID(cell_uuid)), 'family': family_id, 'points': points, 'skipped': skipped,
                'total_conditions': len(conditions), 'truncated': len(conditions) > 50,
                'samples_read': samples_used, 'sample_budget': 500000,
                'method': {'id': 'bounded_condition_response_v1', 'label': 'Raw stimulus-window response mean',
                    'interpretation': 'First up to three chronological epochs per exact parameter set and acquisition block. Conditions, raw groups and units are never pooled across blocks. Uses unprocessed signals in recorded stream units; this is not firing rate or a fitted receptive field.',
                    'maximum_epochs_per_condition': 3}}


def register_qc_routes(app, service, db_lock):
    from flask import jsonify, request
    qc = CellQC(service)
    app.extensions['cell_qc'] = qc

    def options(allowed):
        if set(request.args) - set(allowed) or any(len(request.args.getlist(key)) != 1 for key in request.args):
            raise ValueError('Unsupported or repeated cell QC option')

    @app.get('/api/cells/<cell_uuid>/qc')
    def cell_qc(cell_uuid):
        options({})
        with db_lock:
            return jsonify(qc.overview(cell_uuid))

    @app.get('/api/cells/<cell_uuid>/qc/epochs')
    def cell_qc_epochs(cell_uuid):
        options({'family', 'offset', 'limit'})
        with db_lock:
            return jsonify(qc.epochs(cell_uuid, request.args.get('family'),
                int(request.args.get('offset', 0)), int(request.args.get('limit', 50))))

    @app.get('/api/cells/<cell_uuid>/qc/response')
    def cell_qc_response(cell_uuid):
        options({'epoch_uuid', 'stream_uuid', 'summary_only'})
        if request.args.get('summary_only', 'false') not in {'true', 'false'}:
            raise ValueError('summary_only must be true or false')
        if not request.args.get('epoch_uuid'):
            raise ValueError('Choose an epoch to inspect its recorded response')
        with db_lock:
            result = qc.response(cell_uuid, request.args['epoch_uuid'], request.args.get('stream_uuid'))
            if request.args.get('summary_only') == 'true':
                result['trace'].pop('values', None)
                result['trace']['values_omitted'] = True
            return jsonify(result)

    @app.get('/api/cells/<cell_uuid>/qc/block-baselines')
    def cell_qc_baselines(cell_uuid):
        options({})
        with db_lock:
            return jsonify(qc.block_baselines(cell_uuid))

    @app.get('/api/cells/<cell_uuid>/qc/response-summary')
    def cell_qc_summary(cell_uuid):
        options({'family', 'block_uuid'})
        with db_lock:
            return jsonify(qc.response_summary(cell_uuid, request.args.get('family'), request.args.get('block_uuid')))
