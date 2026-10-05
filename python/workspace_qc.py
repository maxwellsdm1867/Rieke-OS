"""Lazy, source-verified cell inspection; no pass/fail classification or raw writes."""
from __future__ import annotations

import copy
import datetime as dt
import json
import time
import math
from pathlib import Path
import uuid

import numpy as np

from disco.workbench.recipes import checksum

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
    'id': 'block_onset_voltage_review_v2',
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
        self._preparation_failures = {}

    def rows(self, cell_uuid):
        self.service._ready()
        identity = str(uuid.UUID(cell_uuid))
        if identity not in self.service.cells:
            raise KeyError('Cell is not in the main project catalog')
        return sorted((row for row in self.service.rows.values() if row['cell_uuid'] == identity),
                      key=lambda row: (row['date'], row['start_time'][11:], row['epoch_uuid']))

    def _params(self, row):
        return self.service.details[row['epoch_uuid']].get('parameters', {})

    def _metadata_values(self, row, detail, fields, seen):
        measurements = []
        metadata = detail.get('metadata', {})
        for scope in ('cell', 'group', 'block', 'epoch'):
            source = metadata.get(scope, {})
            entity = source.get('uuid') or row.get(scope + '_uuid') or row['epoch_uuid']
            for category in ('properties', 'parameters', 'attributes'):
                values = detail.get(category, {}) if scope == 'epoch' else source.get(category, {})
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
        observations, measured, compensation = [], [], []
        seen_resistance, seen_compensation = set(), set()
        for index, row in enumerate(rows):
            # The disk-backed mapping validates and deep-copies each lookup.
            # Read once per epoch in this request, then discard the detail;
            # no summary or metadata survives to a subsequent request.
            detail = self.service.details[row['epoch_uuid']]
            observations.append(self._temperature(row, index + 1, detail=detail))
            measured.extend(self._metadata_values(row, detail, RESISTANCE_FIELDS, seen_resistance))
            compensation.extend(self._metadata_values(row, detail, {'seriesResistanceCompensation'}, seen_compensation))
        points = [item for item in observations if item['status'] == 'recorded']
        recorded_units = {item['units'] for item in points}
        same_units = len(recorded_units) == 1
        has_resistance = any(item['numeric'] for item in measured)
        baseline = self.prepared_baselines(cell_uuid, rows=rows)
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
                'field': 'epoch.properties.bathTemperature',
                'units': next(iter(recorded_units)) if same_units else None,
                'unit_basis': 'recorded' if same_units and None not in recorded_units else 'mixed_or_not_recorded',
                'range': {'min': min(p['value'] for p in points), 'max': max(p['value'] for p in points)} if points and same_units else None,
                'recorded_count': len(points), 'missing_count': len(rows) - len(points),
                'points': points[:500], 'truncated': len(points) > 500},
            'resistance': {'status': 'recorded' if has_resistance else 'unavailable', 'measurements': measured,
                'compensation_settings': compensation,
                'reason': None if has_resistance else 'No numeric measured input, access, series or membrane resistance was recorded. Series-resistance compensation is an amplifier setting, not a resistance measurement.'},
            'resting_voltage': {'status': 'unavailable', 'label': 'Resting membrane voltage',
                'reason': baseline.get('reason') or RESTING_REASON, 'method': copy.deepcopy(BASELINE_METHOD),
                'candidate_blocks': block_count, 'supporting_measurements': baseline},
            'families': families,
            'characteristics': {'recorded_cell_type': cell.get('cell_type'),
                'group_labels': sorted({r.get('group_label') for r in rows}, key=str),
                'source_revisions': sorted({r['source_sha256'] for r in rows})},
            'analysis_capabilities': [
                {'id': 'recorded_response', 'status': 'available', 'reason': 'Lazy full-rate response windows with source UUID, SHA256, units and sample-count checks.'},
                {'id': 'condition_response_summary', 'label': 'Recorded response summary', 'status': 'available', 'reason': 'Raw signal window means in the recorded stream units, grouped within acquisition block and exact parameters; no event classification, firing-rate or receptive-field interpretation.'},
                {'id': 'spike_rate_receptive_field', 'status': 'unvalidated_adapter', 'reason': 'RetinAnalysis ExpandingSpotsPipeline.get_stim_nspikes/plot_rf exists, but spike detector and acquisition/clamp configuration need validation before automatic QC use.'},
                {'id': 'baseline_drift_interpolant', 'status': 'unavailable', 'reason': RESTING_REASON}]}

    def _temperature(self, row, order, *, detail=None):
        properties = (self.service.details[row['epoch_uuid']] if detail is None else detail).get('properties', {})
        raw = properties.get('bathTemperature')
        value = raw.get('quantity') if isinstance(raw, dict) else raw
        units = raw.get('units') if isinstance(raw, dict) else properties.get('bathTemperatureUnits')
        units = units if isinstance(units, str) and units.strip() else None
        return {'epoch_uuid': row['epoch_uuid'], 'cell_uuid': row['cell_uuid'],
            'epoch_number': row.get('epoch_number'), 'recording_order': order,
            'start_time': row['start_time'], 'block_uuid': row['block_uuid'],
            'group_label': row.get('group_label'), 'source_sha256': row['source_sha256'],
            'value': value if number(value) else None, 'units': units,
            'status': 'recorded' if number(value) else 'missing',
            'reason': None if number(value) else 'Temperature value is missing or nonnumeric.'}

    def temperature_observations(self, cell_uuid, offset=0, limit=50):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Temperature page requires nonnegative offset and limit 1–100')
        rows = self.rows(cell_uuid)
        return {'cell_uuid': str(uuid.UUID(cell_uuid)),
            'observations': [self._temperature(row, index + 1)
                for index, row in enumerate(rows[offset:offset + limit], offset)],
            'total': len(rows), 'offset': offset, 'limit': limit,
            'has_more': offset + limit < len(rows)}

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

    def block_baselines(self, cell_uuid, rows=None):
        rows = self.rows(cell_uuid) if rows is None else rows
        blocks = {}
        for row in rows:
            if family(row) == 'current_noise':
                blocks.setdefault((row['source_sha256'], row['block_uuid']), []).append(row)
        anchors, excluded = [], []
        for (source_sha, block_uuid), members in blocks.items():
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
                values = np.asarray(trace['values'], dtype=float)
                if len(values) != count or not np.isfinite(values).all():
                    raise ValueError('The complete finite 2 ms voltage window is required.')
                n = max(1, math.floor(rate * 0.001 + 0.5))
                parameters = self._params(row)
                flags = {'first_sample_outside_reference_range': bool(values[0] < -75 or values[0] > -45),
                         'possible_spike_first_2ms': bool(values.max() > -20),
                         'pre_time_not_recorded': not number(parameters.get('preTime'))}
                anchors.append({'epoch_uuid': row['epoch_uuid'], 'block_uuid': block_uuid,
                    'group_uuid': row['group_uuid'], 'group_label': row.get('group_label'),
                    'start_time': row['start_time'], 'mean_mV': float(values[:n].mean()),
                    'median_mV': float(np.median(values[:n])), 'first_mV': float(values[0]),
                    'max_2ms_mV': float(values.max()), 'flags': flags, 'sample_count': n,
                    'sensitivity': [{'window_ms': ms, 'mean_mV': float(values[:max(1, math.floor(rate*ms/1000+0.5))].mean())} for ms in (0.5, 2.0)],
                    'metadata_fingerprint': self.service._fingerprints[row['epoch_uuid']], 'source_sha256': row['source_sha256'],
                    'stream_uuid': stream['uuid'], 'sample_rate': rate, 'sample_rate_units': stream['sample_rate_units'],
                    'pre_time_ms': self._params(row).get('preTime'), 'epochs_in_block': len(members)})
            except (KeyError, ValueError, OSError) as error:
                excluded.append({'block_uuid': block_uuid, 'epoch_uuid': row['epoch_uuid'], 'reason': str(error), 'processing_error': True})
        return {'status': 'estimates_for_review' if anchors else 'unavailable', 'cell_uuid': str(uuid.UUID(cell_uuid)),
                'method': copy.deepcopy(BASELINE_METHOD), 'anchors': anchors, 'excluded_blocks': excluded,
                'total_blocks': len(blocks), 'truncated': False,
                'interpolation': {'status': 'unavailable', 'reason': RESTING_REASON}}

    @staticmethod
    def _recorded_time(row):
        text = row.get('start_time')
        if not isinstance(text, str):
            return None
        for pattern in ('%m/%d/%Y %H:%M:%S:%f', '%m/%d/%Y %H:%M:%S',
                        '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
            try:
                return dt.datetime.strptime(text, pattern)
            except ValueError:
                pass
        return None

    def _baseline_key(self, cell_uuid, rows):
        sources = {}
        for source_sha in {row['source_sha256'] for row in rows}:
            manifest = self.service.manifests.get(source_sha, {})
            path = Path(manifest.get('source_path', ''))
            # Only stat on interaction; checksums are verified by trace reads
            # during preparation and by normal source validation on app startup.
            sources[source_sha] = list(self.service._input_signature(path)) if path.is_file() else None
        return checksum({'method': BASELINE_METHOD, 'implementation_version': 1,
            'project_uuid': self.service.project['project_uuid'], 'cell_uuid': str(uuid.UUID(cell_uuid)),
            'sources': sources, 'epochs': [{key: row.get(key) for key in
                ('epoch_uuid', 'source_sha256', 'block_uuid', 'group_uuid', 'date', 'start_time', 'protocol_name', 'streams')}
                | {'metadata_fingerprint': self.service._fingerprints[row['epoch_uuid']]} for row in rows]})

    def _baseline_path(self, cell_uuid):
        from disco.projects.storage import managed_directory
        path = managed_directory(self.service.project_dir, 'cache/block-onset-voltage') / (str(uuid.UUID(cell_uuid)) + '.json')
        if path.is_symlink():
            raise ValueError('Prepared voltage result cannot be a symbolic link')
        return path

    def prepared_baselines(self, cell_uuid, rows=None):
        rows = self.rows(cell_uuid) if rows is None else rows
        identity = str(uuid.UUID(cell_uuid))
        unavailable = {'status': 'unavailable', 'preparation_status': 'not_prepared', 'cell_uuid': identity,
            'anchors': [], 'recordings': [], 'excluded_blocks': [],
            'reason': 'Supporting block-onset data needs preparation for the current recording version.',
            'interpolation': {'status': 'unavailable', 'reason': RESTING_REASON}}
        try:
            key = self._baseline_key(identity, rows)
            failure = self._preparation_failures.get(identity)
            if failure and failure['key'] == key:
                return {**unavailable, 'preparation_status': 'failed', 'reason': failure['reason']}
            path = self._baseline_path(identity)
            if not path.exists():
                return unavailable
            document = json.loads(path.read_text())
            if document.get('key') != key:
                return unavailable
            result = document['result']
            if (result.get('cell_uuid') != identity or document.get('result_sha256') != checksum(result)
                    or document.get('format') != 'block-onset-voltage-v1'):
                raise ValueError('Prepared supporting voltage data failed its integrity check.')
            return result
        except (OSError, KeyError, TypeError, ValueError) as error:
            return {**unavailable, 'preparation_status': 'failed', 'reason': str(error)}

    def prepare_cell_baselines(self, cell_uuid, *, force=False):
        started = time.perf_counter()
        rows = self.rows(cell_uuid)
        identity = str(uuid.UUID(cell_uuid))
        prior = self.prepared_baselines(identity, rows=rows)
        try:
            key = self._baseline_key(identity, rows)
        except (OSError, KeyError, ValueError, TypeError) as error:
            return {**prior, 'status': 'unavailable', 'preparation_status': 'failed',
                'anchors': [], 'recordings': [], 'reason': str(error)}
        if not force and prior.get('preparation_status') == 'complete':
            return prior
        try:
            from recording_workspace import write_json
            pending = {**prior, 'status': 'unavailable', 'preparation_status': 'preparing',
                'anchors': [], 'recordings': [], 'reason': 'Supporting voltage data is preparing; retry if preparation was interrupted.'}
            write_json(self._baseline_path(identity), {'format': 'block-onset-voltage-v1', 'key': key,
                'result': pending, 'result_sha256': checksum(pending)})
            result = self.block_baselines(identity, rows=rows)
            errors = [item['reason'] for item in result['excluded_blocks'] if item.get('processing_error')]
            if errors:
                raise ValueError('Supporting voltage preparation failed: ' + '; '.join(errors))
            recordings = []
            for source_sha in sorted({row['source_sha256'] for row in rows}):
                members = [row for row in rows if row['source_sha256'] == source_sha]
                times = [self._recorded_time(row) for row in members]
                known = [value for value in times if value is not None]
                onset = min(known) if known else None
                anchors = [anchor for anchor in result['anchors'] if anchor['source_sha256'] == source_sha]
                for anchor in anchors:
                    anchor_time = self._recorded_time(anchor)
                    anchor['recording_time_seconds'] = (anchor_time-onset).total_seconds() if anchor_time and onset else None
                    anchor['stream_units'] = 'mV'
                recordings.append({'source_sha256': source_sha, 'cell_uuid': identity,
                    'start_time': min(members, key=lambda row: (row['date'], row['start_time'][11:]))['start_time'],
                    'duration_seconds': (max(known)-onset).total_seconds() if known else None,
                    'time_basis': 'Seconds from first recorded epoch in this cell/source; anchors are not pooled across recordings.',
                    'epoch_uuids': [row['epoch_uuid'] for row in members],
                    'anchor_epoch_uuids': [anchor['epoch_uuid'] for anchor in anchors],
                    'estimate_range_mV': {'min': min(anchor['mean_mV'] for anchor in anchors),
                        'max': max(anchor['mean_mV'] for anchor in anchors)} if anchors else None})
            result.update(recordings=recordings, preparation_status='complete',
                prepared_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                preparation_ms=(time.perf_counter()-started)*1000,
                reason=None if result['anchors'] else (result['excluded_blocks'][0]['reason'] if result['excluded_blocks']
                    else 'No eligible injected-current-noise blocks were recorded.'))
            from recording_workspace import write_json
            write_json(self._baseline_path(identity), {'format': 'block-onset-voltage-v1', 'key': key,
                'result': result, 'result_sha256': checksum(result)})
            self._preparation_failures.pop(identity, None)
            return result
        except (OSError, KeyError, ValueError, TypeError) as error:
            self._preparation_failures[identity] = {'key': key, 'reason': str(error)}
            failed = {**prior, 'status': 'unavailable', 'preparation_status': 'failed',
                'anchors': [], 'recordings': [], 'reason': str(error)}
            try:
                from recording_workspace import write_json
                write_json(self._baseline_path(identity), {'format': 'block-onset-voltage-v1', 'key': key,
                    'result': failed, 'result_sha256': checksum(failed)})
            except (OSError, ValueError):
                pass
            return failed

    def prepare_baselines(self, source_sha256=None):
        """Import preparation / startup backfill; display routes never read samples."""
        cells = {row['cell_uuid'] for row in self.service.rows.values()
            if source_sha256 is None or row['source_sha256'] == source_sha256}
        results = [self.prepare_cell_baselines(identity) for identity in sorted(cells)]
        failures = [{'cell_uuid': item['cell_uuid'], 'reason': item.get('reason')}
            for item in results if item['preparation_status'] == 'failed']
        return {'status': 'failed' if failures else 'complete', 'cell_count': len(cells), 'failures': failures,
            'method': BASELINE_METHOD['id'], 'preparation_ms': sum(item.get('preparation_ms', 0) for item in results)}

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

    @app.get('/api/cells/<cell_uuid>/qc/temperature')
    def cell_qc_temperature(cell_uuid):
        options({'offset', 'limit'})
        with db_lock:
            return jsonify(qc.temperature_observations(cell_uuid,
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
            return jsonify(qc.prepared_baselines(cell_uuid))

    @app.post('/api/cells/<cell_uuid>/qc/prepare-baselines')
    def cell_qc_prepare_baselines(cell_uuid):
        options({})
        if request.get_json(silent=True) != {}:
            raise ValueError('Supporting voltage preparation accepts an empty JSON object')
        with db_lock:
            return jsonify(qc.prepare_cell_baselines(cell_uuid, force=True))

    @app.get('/api/cells/<cell_uuid>/qc/response-summary')
    def cell_qc_summary(cell_uuid):
        options({'family', 'block_uuid'})
        with db_lock:
            return jsonify(qc.response_summary(cell_uuid, request.args.get('family'), request.args.get('block_uuid')))
