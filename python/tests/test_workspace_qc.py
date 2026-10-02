"""Read-only QC boundaries and numerical methods, using source/SQL doubles."""
import copy
import unittest
from unittest.mock import Mock
import uuid
from collections import Counter
from collections.abc import Mapping

import test_workspace_api as api_tests
from workspace_qc import CellQC


class CellQCTests(unittest.TestCase):
    def setUp(self):
        self.case = api_tests.WorkspaceAPITests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.service = self.case.service
        self.ids = self.service.ids
        self.cell = self.service.cell_ids[0]
        self.qc = CellQC(self.service)
        self.base = '/api/cells/' + self.cell + '/qc'
        self.streams = {}
        for identity in self.ids:
            row = self.service.rows[identity]
            stream = {'uuid': str(uuid.uuid4()), 'kind': 'responses', 'device': 'Amp1',
                      'units': 'mV', 'sample_count': 1000, 'sample_rate': 10000., 'sample_rate_units': 'Hz'}
            row['streams'] = [stream]
            row['protocol_name'] = 'edu.washington.riekelab.turner.protocols.ExpandingSpots'
            self.service.details[identity]['parameters'] = {'amp': 'Amp1', 'preTime': 10., 'stimTime': 20.,
                                                          'tailTime': 70., 'currentSpotSize': 40.}
            self.streams[identity] = stream
        def trace(epoch, stream_uuid, start, count):
            stream = self.streams[epoch]
            values = [-60.] * 100 + [-50.] * 200 + [-60.] * (stream['sample_count'] - 300)
            return {'epoch_uuid': epoch, 'stream_uuid': stream_uuid, 'start': start,
                'count': min(count, len(values)-start), 'values': values[start:start+count],
                'sample_rate': stream['sample_rate'], 'units': stream['units'],
                'total_samples': stream['sample_count'], 'source_sha256': 'a' * 64, 'decimated': False}
        self.service.trace = Mock(side_effect=trace)

    def same_cell(self):
        self.service.rows[self.ids[1]]['cell_uuid'] = self.cell
        self.service.rows[self.ids[1]]['cell_label'] = 'Cell1'

    def test_overview_reads_each_detail_once_and_rechecks_changes_on_next_request(self):
        self.same_cell()
        backing = self.service.details
        reads = Counter()

        class CountedDetails(Mapping):
            def __iter__(self): return iter(backing)
            def __len__(self): return len(backing)
            def __getitem__(self, key):
                reads[key] += 1
                return copy.deepcopy(backing[key])

        for index, identity in enumerate(self.ids):
            backing[identity]['properties'] = {'bathTemperature': {'quantity': 29. + index, 'units': 'degC'}}
            backing[identity]['metadata']['cell'] = {'uuid': self.cell, 'properties': {
                'inputResistance': {'quantity': 120., 'units': 'MOhm'},
                'seriesResistanceCompensation': 0}}
        self.service.details = CountedDetails()
        first = self.qc.overview(self.cell)
        self.assertEqual(reads, Counter({identity: 1 for identity in self.ids}))
        self.assertEqual(first['temperature']['range'], {'min': 29., 'max': 30.})
        self.assertEqual(len(first['resistance']['measurements']), 1, 'Shared cell metadata is deduplicated across epochs')
        self.assertEqual(first['resistance']['measurements'][0]['value'], 120.)
        self.assertEqual(first['resistance']['compensation_settings'][0]['value'], 0)

        # Metadata mutation between requests must be observed; this optimization
        # must not become a persistent summary or detail cache.
        for identity in self.ids:
            backing[identity]['properties']['bathTemperature'] = True
            backing[identity]['metadata']['cell']['properties']['inputResistance'] = None
            backing[identity]['metadata']['cell']['properties']['seriesResistanceCompensation'] = 50
        reads.clear()
        second = self.qc.overview(self.cell)
        self.assertEqual(reads, Counter({identity: 1 for identity in self.ids}))
        self.assertEqual(second['temperature']['status'], 'unavailable')
        self.assertIsNone(second['temperature']['range'])
        self.assertEqual(second['resistance']['status'], 'unavailable')
        self.assertIsNone(second['resistance']['measurements'][0]['value'])
        self.assertEqual(second['resistance']['compensation_settings'][0]['value'], 50)
        self.service.trace.assert_not_called()

    def test_metadata_and_cross_protocol_epochs_are_lazy_and_cell_uuid_scoped(self):
        self.same_cell()
        self.service.protocols[self.service.protocol_id]['result']['epochs'] = [{'uuid': self.ids[0], 'metadata_hash': 'b' * 64}]
        self.service.rows[self.ids[1]]['protocol_name'] = 'edu.washington.riekelab.turner.protocols.SplitFieldCentering'
        self.service.details[self.ids[0]]['properties'] = {'bathTemperature': 29.1}
        self.service.details[self.ids[1]]['properties'] = {'bathTemperature': 30.2}
        response = self.case.client.get(self.base)
        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()
        self.assertEqual(data['counts']['epochs'], 2)
        self.assertEqual(data['counts']['protocols'], 2)
        self.assertEqual(data['temperature']['range'], {'min': 29.1, 'max': 30.2})
        self.assertIsNone(data['temperature']['units'])
        self.assertEqual(data['resting_voltage']['status'], 'unavailable')
        epochs = self.case.client.get(self.base + '/epochs?family=split_field').get_json()
        self.assertEqual([r['epoch_uuid'] for r in epochs['epochs']], [self.ids[1]])
        self.service.trace.assert_not_called()
        self.assertFalse(self.case.events.rows)
        self.assertFalse(self.case.curation.rows)
        self.assertFalse(self.case.datasets.rows)

    def test_compensation_is_not_a_resistance_measurement(self):
        details = self.service.details[self.ids[0]]
        details['metadata']['group'] = {'uuid': 'group-id', 'properties': {'seriesResistanceCompensation': 0}}
        overview = self.qc.overview(self.cell)
        self.assertEqual(overview['resistance']['status'], 'unavailable')
        self.assertEqual(overview['resistance']['compensation_settings'][0]['value'], 0)
        details['metadata']['cell'] = {'uuid': self.cell, 'properties': {
            'inputResistance': {'quantity': 120., 'units': 'MOhm'}}}
        overview = self.qc.overview(self.cell)
        self.assertEqual(overview['resistance']['status'], 'recorded')
        measurement = overview['resistance']['measurements'][0]
        self.assertEqual((measurement['value'], measurement['units']), (120., 'MOhm'))
        self.assertEqual(measurement['field'], 'cell.properties.inputResistance')
        details['metadata']['cell']['properties']['inputResistance'] = None
        self.assertEqual(self.qc.overview(self.cell)['resistance']['status'], 'unavailable')

    def test_missing_nonnumeric_temperature_is_not_fabricated(self):
        self.service.details[self.ids[0]]['properties']['bathTemperature'] = True
        result = self.qc.overview(self.cell)['temperature']
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['range'])
        self.assertEqual(result['missing_count'], 1)
        self.assertEqual(next(f for f in self.qc.overview(self.cell)['families'] if f['id']=='current_step')['epoch_count'], 0)

    def test_temperature_observations_include_missing_units_and_later_pages(self):
        self.same_cell()
        self.service.details[self.ids[0]]['properties']['bathTemperature'] = {'quantity': 29.5, 'units': 'degC'}
        self.service.details[self.ids[1]]['properties']['bathTemperature'] = None
        template = self.service.rows[self.ids[0]]
        for index in range(501):
            identity = str(uuid.uuid4())
            self.service.rows[identity] = {**copy.deepcopy(template), 'epoch_uuid': identity,
                'start_time': f'09/24/2026 14:{index // 60:02d}:{index % 60:02d}:000000'}
            self.service.details[identity] = {'properties': {'bathTemperature': 30.}}
        first = self.case.client.get(self.base + '/temperature?limit=2').get_json()
        self.assertEqual(first['total'], 503)
        self.assertTrue(first['has_more'])
        self.assertEqual(first['observations'][0]['epoch_uuid'], self.ids[0])
        self.assertEqual(first['observations'][0]['units'], 'degC')
        self.assertEqual(first['observations'][1]['status'], 'missing')
        self.assertIsNone(first['observations'][1]['units'])
        last = self.case.client.get(self.base + '/temperature?offset=500&limit=100').get_json()
        self.assertEqual(len(last['observations']), 3)
        self.assertEqual(last['observations'][-1]['recording_order'], 503)
        self.assertFalse(last['has_more'])
        self.service.trace.assert_not_called()
        for suffix in ('?limit=101', '?offset=-1', '?limit=2&limit=3'):
            self.assertEqual(self.case.client.get(self.base + '/temperature' + suffix).status_code, 400)

    def test_temperature_units_are_never_assumed_or_pooled_across_units(self):
        properties = self.service.details[self.ids[0]]['properties']
        properties.update(bathTemperature=30., bathTemperatureUnits='degC')
        self.assertEqual(self.qc.overview(self.cell)['temperature']['units'], 'degC')
        self.same_cell()
        self.service.details[self.ids[1]]['properties'].update(bathTemperature=86., bathTemperatureUnits='degF')
        temperature = self.qc.overview(self.cell)['temperature']
        self.assertIsNone(temperature['units'])
        self.assertIsNone(temperature['range'])
        self.assertEqual({point['units'] for point in temperature['points']}, {'degC', 'degF'})

    def test_response_windows_match_recorded_timing_and_summary_omits_samples(self):
        result = self.qc.response(self.cell, self.ids[0])
        self.assertEqual(result['statistics']['pre'], {'mean': -60., 'std': 0., 'n': 100})
        self.assertEqual(result['statistics']['stim'], {'mean': -50., 'std': 0., 'n': 200})
        self.assertEqual(result['statistics']['delta_mean'], 10.)
        self.assertEqual(result['provenance']['metadata_fingerprint'], 'b' * 64)
        response = self.case.client.get(self.base + '/response', query_string={'epoch_uuid': self.ids[0], 'summary_only': 'true'})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertNotIn('values', response.get_json()['trace'])
        self.assertTrue(response.get_json()['trace']['values_omitted'])
        self.assertFalse(self.case.events.rows)

    def test_partial_stimulus_window_never_yields_partial_mean_or_resting_vm(self):
        self.streams[self.ids[0]]['sample_count'] = 120000
        self.service.details[self.ids[0]]['parameters']['stimTime'] = 12000.
        result = self.qc.response(self.cell, self.ids[0])
        self.assertTrue(result['partial_trace'])
        self.assertEqual(result['trace']['count'], 100000)
        self.assertEqual(result['statistics']['status'], 'unavailable')
        self.assertIsNone(result['statistics']['stim'])
        self.assertIsNone(result['statistics']['delta_mean'])
        self.assertIn('no spike detection', result['method']['interpretation'].lower())

    def test_foreign_cell_epoch_malformed_options_and_ambiguous_stream_fail_closed(self):
        for route in ['/response?epoch_uuid=' + self.ids[1], '/epochs?family=unknown',
                      '/epochs?limit=101', '/epochs?family=other&family=other', '?sql=1']:
            response = self.case.client.get(self.base + route)
            self.assertEqual(response.status_code, 400, response.get_json())
        self.service.rows[self.ids[0]]['streams'].append(copy.deepcopy(self.streams[self.ids[0]]))
        with self.assertRaisesRegex(ValueError, 'no channel was guessed'):
            self.qc.response(self.cell, self.ids[0])
        self.service.trace.assert_not_called()

    def test_baseline_only_uses_chronological_first_epoch_and_exposes_contamination_flags(self):
        self.same_cell()
        block = self.service.rows[self.ids[0]]['block_uuid']
        for identity in self.ids:
            self.service.rows[identity]['block_uuid'] = block
            self.service.rows[identity]['protocol_name'] = 'edu.washington.riekelab.chris.protocols.VariableMeanNoiseCurInject'
        self.service.rows[self.ids[0]]['start_time'] = '09/24/2026 13:00:00:000000'
        self.service.rows[self.ids[1]]['start_time'] = '09/24/2026 12:00:00:000000'
        def trace(epoch, stream, start, count):
            self.assertEqual(epoch, self.ids[1])
            self.assertEqual(count, 20)
            values = [-60.] * 20
            values[15] = 5.
            return {'values': values}
        self.service.trace.side_effect = trace
        result = self.qc.block_baselines(self.cell)
        self.assertEqual(len(result['anchors']), 1)
        anchor = result['anchors'][0]
        self.assertEqual(anchor['mean_mV'], -60.)
        self.assertEqual(anchor['sample_count'], 10)
        self.assertTrue(anchor['flags']['possible_spike_first_2ms'])
        self.assertFalse(anchor['flags']['first_sample_outside_reference_range'])
        self.assertEqual(result['interpolation']['status'], 'unavailable')
        self.service.trace.assert_called_once()

    def test_singleton_block_and_non_voltage_units_do_not_become_baseline(self):
        self.service.rows[self.ids[0]]['protocol_name'] = 'VariableHistoryNoiseCurInject'
        result = self.qc.block_baselines(self.cell)
        self.assertFalse(result['anchors'])
        self.assertIn('two epochs', result['excluded_blocks'][0]['reason'])
        self.same_cell()
        self.service.rows[self.ids[1]]['protocol_name'] = 'VariableHistoryNoiseCurInject'
        self.service.rows[self.ids[1]]['block_uuid'] = self.service.rows[self.ids[0]]['block_uuid']
        self.streams[self.ids[0]]['units'] = 'pA'
        self.assertFalse(self.qc.block_baselines(self.cell)['anchors'])
        self.service.trace.assert_not_called()

    def eligible_noise_block(self):
        self.same_cell()
        for identity in self.ids:
            self.service.rows[identity]['protocol_name'] = 'VariableMeanNoiseCurInject'
            self.service.rows[identity]['block_uuid'] = self.service.rows[self.ids[0]]['block_uuid']
        return self.service.rows[self.ids[0]]['block_uuid']

    def test_prepared_voltage_reuses_exact_source_data_without_reads_on_display_or_restart(self):
        self.eligible_noise_block()
        result = self.qc.prepare_cell_baselines(self.cell)
        self.assertEqual(result['status'], 'estimates_for_review')
        anchor = result['anchors'][0]
        self.assertEqual(anchor['epoch_uuid'], self.ids[0])
        self.assertEqual(anchor['stream_uuid'], self.streams[self.ids[0]]['uuid'])
        self.assertEqual(anchor['recording_time_seconds'], 0.)
        self.assertEqual(anchor['stream_units'], 'mV')
        self.assertEqual(result['recordings'][0]['epoch_uuids'], self.ids)
        self.assertEqual(result['interpolation']['status'], 'unavailable')
        self.service.trace.assert_called_once()
        self.service.trace.reset_mock()
        restarted = CellQC(self.service)
        self.assertEqual(restarted.prepare_cell_baselines(self.cell), result)
        self.assertEqual(restarted.prepared_baselines(self.cell), result)
        self.assertEqual(restarted.overview(self.cell)['resting_voltage']['supporting_measurements'], result)
        self.assertEqual(self.case.client.get(self.base+'/block-baselines').get_json(), result)
        self.service.trace.assert_not_called()
        self.assertEqual(restarted.overview(self.cell)['resting_voltage']['status'], 'unavailable')

    def test_changed_baseline_inputs_membership_and_file_signature_do_not_load_stale_data(self):
        self.eligible_noise_block()
        self.qc.prepare_cell_baselines(self.cell)
        self.service._fingerprints[self.ids[0]] = 'c' * 64
        self.assertEqual(self.qc.prepared_baselines(self.cell)['preparation_status'], 'not_prepared')
        self.qc.prepare_cell_baselines(self.cell)
        self.service.rows[self.ids[1]]['cell_uuid'] = self.service.cell_ids[1]
        self.assertEqual(self.qc.prepared_baselines(self.cell)['preparation_status'], 'not_prepared')
        self.same_cell()
        self.streams[self.ids[0]]['units'] = 'pA'
        self.assertEqual(self.qc.prepared_baselines(self.cell)['preparation_status'], 'not_prepared')
        self.streams[self.ids[0]]['units'] = 'mV'
        source = self.service.project_dir/'fixture.h5'
        source.write_bytes(b'original')
        self.qc.prepare_cell_baselines(self.cell)
        source.write_bytes(b'changed')
        self.assertEqual(self.qc.prepared_baselines(self.cell)['preparation_status'], 'not_prepared')

    def test_baseline_processing_failure_is_persisted_and_retry_is_explicit(self):
        self.eligible_noise_block()
        self.service.trace.side_effect = OSError('Waveform unreadable')
        result = self.qc.prepare_cell_baselines(self.cell)
        self.assertEqual(result['preparation_status'], 'failed')
        self.assertFalse(result['anchors'])
        restarted = CellQC(self.service)
        self.assertEqual(restarted.prepared_baselines(self.cell)['preparation_status'], 'failed')
        self.assertIn('Waveform unreadable', restarted.prepared_baselines(self.cell)['reason'])
        self.service.trace.side_effect = lambda *args: {'values': [-60.] * 20}
        response = self.case.client.post(self.base+'/prepare-baselines', json={}, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['preparation_status'], 'complete')
        self.assertEqual(len(response.get_json()['anchors']), 1)
        unknown = str(uuid.uuid4())
        self.assertEqual(self.case.client.get('/api/cells/'+unknown+'/qc/block-baselines').status_code, 400)

    def test_baseline_recordings_are_separate_and_every_block_is_prepared(self):
        self.eligible_noise_block()
        template = copy.deepcopy(self.service.rows[self.ids[0]])
        for index in range(501):
            block = str(uuid.uuid4())
            for trial in range(2):
                identity = str(uuid.uuid4())
                row = {**copy.deepcopy(template), 'epoch_uuid': identity, 'block_uuid': block,
                    'start_time': f'09/24/2026 14:{index // 60:02d}:{index % 60:02d}:00000{trial}'}
                self.service.rows[identity] = row
                self.service.details[identity] = copy.deepcopy(self.service.details[self.ids[0]])
                self.service._fingerprints[identity] = 'b' * 64
        self.service.trace.side_effect = lambda *args: {'values': [-60.] * 20}
        result = self.qc.prepare_cell_baselines(self.cell)
        self.assertEqual(len(result['anchors']), 502)
        self.assertFalse(result['truncated'])
        self.assertEqual(self.service.trace.call_count, 502)
        self.assertEqual(result['preparation_status'], 'complete')
        # A block copied across sources cannot gain eligibility by pooling.
        self.service.rows[self.ids[1]]['source_sha256'] = 'd' * 64
        self.service.manifests['d' * 64] = {'source_path': str(self.service.project_dir/'other.h5')}
        separate = self.qc.prepare_cell_baselines(self.cell)
        self.assertEqual(len(separate['recordings']), 2)
        self.assertEqual(len(separate['anchors']), 501)
        self.assertFalse(separate['recordings'][1]['anchor_epoch_uuids'])

    def test_condition_summary_keeps_block_group_and_contrast_separate(self):
        self.same_cell()
        self.service.details[self.ids[1]]['parameters']['contrast'] = -1
        self.service.details[self.ids[0]]['parameters']['contrast'] = 1
        self.service.rows[self.ids[1]]['group_label'] = 'Exact drug label'
        result = self.qc.response_summary(self.cell, 'expanding_spots')
        self.assertEqual(len(result['points']), 2)
        self.assertEqual({p['parameters']['contrast'] for p in result['points']}, {-1, 1})
        self.assertTrue(all(p['response_mean']==-50. and p['delta_mean']==10. for p in result['points']))
        self.assertEqual(result['samples_read'], 2000)
        self.assertEqual({p['group_label'] for p in result['points']}, {'Recorded group', 'Exact drug label'})

    def test_source_verification_failure_is_explicit_not_an_average(self):
        self.service.trace.side_effect = ValueError('Source SHA256 changed')
        response = self.case.client.get(self.base + '/response', query_string={'epoch_uuid': self.ids[0]})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Source SHA256 changed', response.get_json()['error'])
        result = self.qc.response_summary(self.cell, 'expanding_spots')
        self.assertEqual(result['points'][0]['status'], 'unavailable')
        self.assertIsNone(result['points'][0]['response_mean'])
        self.assertIn('Source SHA256 changed', result['skipped'][0]['reason'])

    def test_unknown_sample_rate_units_fail_before_io(self):
        self.streams[self.ids[0]]['sample_rate_units'] = 'kHz'
        with self.assertRaisesRegex(ValueError, 'recorded in Hz'):
            self.qc.response(self.cell, self.ids[0])
        self.service.trace.assert_not_called()

    def test_condition_summary_enforces_read_budget(self):
        template = self.service.rows[self.ids[0]]
        self.streams[self.ids[0]]['sample_count'] = 100000
        for n in range(8):
            identity = str(uuid.uuid4())
            self.service.rows[identity] = {**copy.deepcopy(template), 'epoch_uuid': identity}
            self.service.details[identity] = copy.deepcopy(self.service.details[self.ids[0]])
            self.service.details[identity]['parameters']['currentSpotSize'] = 80. + n
            self.service._fingerprints[identity] = 'b' * 64
            self.streams[identity] = self.service.rows[identity]['streams'][0]
        result = self.qc.response_summary(self.cell, 'expanding_spots')
        self.assertLessEqual(result['samples_read'], 500000)
        self.assertEqual(self.service.trace.call_count, 5)
        self.assertTrue(any('budget reached' in row['reason'] for row in result['skipped']))
        self.assertEqual(sum(p['status']=='available' for p in result['points']), 5)


    def test_current_response_units_are_preserved_without_voltage_claim(self):
        self.streams[self.ids[0]]['units'] = 'pA'
        result = self.qc.response(self.cell, self.ids[0])
        self.assertEqual(result['statistics']['units'], 'pA')
        self.assertEqual(result['statistics']['delta_mean'], 10.)
        self.assertNotIn('voltage', result['method']['id'])
        self.assertNotIn('including spikes', result['method']['interpretation'])
        summary = self.qc.response_summary(self.cell, 'expanding_spots')
        self.assertEqual(summary['points'][0]['units'], 'pA')
        self.assertEqual(summary['points'][0]['response_mean'], -50.)
        capability = next(item for item in self.qc.overview(self.cell)['analysis_capabilities'] if item['id']=='condition_response_summary')
        self.assertIn('recorded stream units', capability['reason'])
