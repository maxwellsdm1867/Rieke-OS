"""Automatic import proposals use disposable SQL doubles, never research writes."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import test_workspace_import_api as import_tests
from workspace_suggestions import ProtocolSuggestions


class ImportSuggestionTests(unittest.TestCase):
    def setUp(self):
        self.preflight = import_tests.ImportPreflightAPITests()
        self.preflight.setUp()
        self.addCleanup(self.preflight.doCleanups)
        self.case = self.preflight.case
        self.source = Path(self.case.temp.name) / 'new-recording.h5'
        self.source.write_bytes(b'new isolated recording fixture')
        self.source_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.before_ids = list(self.case.service.ids)

    def add_recording(self, *, same_cell=False):
        service = self.case.service
        identity, cell = str(uuid.uuid4()), service.cell_ids[0] if same_cell else str(uuid.uuid4())
        row = copy.deepcopy(service.rows[self.before_ids[0]])
        row.update(epoch_uuid=identity, cell_uuid=cell, source_sha256=self.source_sha,
                   cell_label='Cell3' if not same_cell else row['cell_label'])
        service.rows[identity] = row
        service.details[identity] = copy.deepcopy(service.details[self.before_ids[0]])
        service._fingerprints[identity] = 'b' * 64
        service.cells[cell] = {**service.cells[service.cell_ids[0]], 'cell_uuid': cell, 'label': row['cell_label']}
        service.sources.append({'source_sha256': self.source_sha, 'source_path': str(self.source),
                                'filename': self.source.name, 'counts': {'cells': 1, 'epochs': 1}})
        service.manifests[self.source_sha] = {'source_path': str(self.source)}
        self.case.sources.insert1({'project_uuid': service.project['project_uuid'], 'source_sha256': self.source_sha})
        starter = service.protocols[service.protocol_id]['result']
        starter['epochs'].append({'uuid': identity, 'metadata_hash': 'b' * 64})
        starter['source_revisions'].append(self.source_sha)
        starter['cells'].append({'uuid': cell})
        service._tree_catalog_cache = {}
        service._registered_tree_cache = service._registered_predicate_cache = service._predicate_catalog_cache = None
        return identity

    def run_import(self, mutate=None):
        def parser(command, stdout, stderr):
            binding = self.case.explorer_history.protocol_binding(self.case.service.protocol_id)
            self.assertIsNotNone(binding, 'Baseline must be persistent before source insertion')
            self.assertEqual({r['uuid'] for r in binding['recipe']['epochs']}, set(self.before_ids))
            (mutate or self.add_recording)()
            return SimpleNamespace(returncode=0)
        with patch('workspace_api.subprocess.run', side_effect=parser):
            response = self.case.client.post('/api/imports', json={'source_path': str(self.source)}, headers=self.case.headers)
        self.assertEqual(response.status_code, 202)
        return self.preflight.latest_job()

    def suggestions(self):
        response = self.case.client.get('/api/protocol-suggestions')
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_import_preserves_old_working_set_and_persists_reviewable_new_cell(self):
        job = self.run_import()
        self.assertEqual(job['status'], 'complete')
        self.assertEqual(job['protocol_suggestions']['created_count'], 1)
        self.assertEqual(job['warnings'], [])
        protocol = self.case.client.get(self.case.base).get_json()
        self.assertEqual(protocol['counts']['epochs'], 2)
        self.assertEqual(len(self.case.service.rows), 3)
        suggestion = self.suggestions()['suggestions'][0]
        self.assertEqual(suggestion['status'], 'pending')
        self.assertEqual(suggestion['diff_counts'], {'added': 1, 'removed': 0, 'changed': 0})
        self.assertEqual(suggestion['diff_summary']['delta']['cells'], 1)
        self.assertEqual(suggestion['source_filename'], self.source.name)
        self.assertEqual((suggestion['previous_count'], suggestion['next_count']), (2, 3))
        freezes = [event for event in self.case.events.rows if event['action'] == 'protocol_dataset_bound']
        self.assertEqual(freezes[0]['payload']['reason'], 'pre_import_baseline_freeze')
        self.assertFalse(freezes[0]['payload']['working_dataset_membership_changed'])
        # SQL summaries survive a new manager instance, without evaluating predicates.
        reloaded = ProtocolSuggestions(self.case.service, self.case.explorer_history, table=self.case.suggestion_rows)
        with patch.object(self.case.service, 'explore_preview', side_effect=AssertionError('GET must not rerun')):
            self.assertEqual(reloaded.list()['counts']['pending'], 1)
            self.assertEqual(self.suggestions()['counts']['pending'], 1)
        self.assertEqual(len(self.case.protocol_bindings.rows), 1)
        self.assertFalse(self.case.datasets.rows)
        self.assertFalse(self.case.curation.rows)

    def test_existing_cell_addition_has_zero_cell_delta_and_explicit_apply(self):
        self.run_import(lambda: self.add_recording(same_cell=True))
        suggestion = self.suggestions()['suggestions'][0]
        self.assertEqual(suggestion['diff_summary']['delta']['cells'], 0)
        candidate = '/api/explore/revisions/' + suggestion['candidate_revision_uuid']
        body = {'protocol_uuid': self.case.service.protocol_id}
        comparison = self.case.client.post(candidate + '/compare-to-protocol', json=body, headers=self.case.headers)
        self.assertEqual(comparison.status_code, 200, comparison.get_json())
        state = comparison.get_json()
        self.assertEqual(state['diff_counts']['added'], 1)
        response = self.case.client.post(candidate + '/apply-to-protocol', json={**body,
            'expected_binding_version': state['expected_binding_version'],
            'expected_query_revision': state['expected_query_revision']}, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['protocol']['counts']['epochs'], 3)
        self.assertEqual(self.suggestions()['suggestions'][0]['status'], 'applied')

    def test_candidate_failure_does_not_relabel_committed_import_as_failed(self):
        with patch.object(self.case.service, 'explore_preview', side_effect=ValueError('Unsupported new metadata')):
            job = self.run_import()
        self.assertEqual(job['status'], 'complete_with_warnings')
        self.assertEqual(job['protocol_suggestions']['failed_count'], 1)
        self.assertIn('Unsupported new metadata', job['warnings'][0]['message'])
        self.assertEqual(job['warnings'][0]['stage'], 'protocol_query')
        self.assertEqual(len(self.case.service.rows), 3)
        self.assertEqual(self.case.client.get(self.case.base).get_json()['counts']['epochs'], 2)
        self.assertFalse(self.case.suggestion_rows.rows)

    def test_baseline_failure_stops_before_parser_and_rolls_back_freeze(self):
        with patch.object(self.case.explorer_history, 'bind', side_effect=ValueError('Cannot persist baseline')), \
             patch('workspace_api.subprocess.run', side_effect=AssertionError('Do not import without baseline')):
            self.case.client.post('/api/imports', json={'source_path': str(self.source)}, headers=self.case.headers)
        job = self.preflight.latest_job()
        self.assertEqual(job['status'], 'failed')
        self.assertIn('Cannot persist baseline', job['error'])
        self.assertFalse(self.case.protocol_bindings.rows)
        self.assertFalse(self.case.explorer_revisions.rows)
        self.assertEqual(len(self.case.service.rows), 2)

    def test_duplicate_does_not_create_any_baseline_or_suggestion(self):
        self.source.write_bytes(self.preflight.bytes)
        with patch('workspace_api.subprocess.run', side_effect=AssertionError('No duplicate parse')):
            self.case.client.post('/api/imports', json={'source_path': str(self.source)}, headers=self.case.headers)
        self.assertEqual(self.preflight.latest_job()['status'], 'duplicate')
        self.assertFalse(self.case.protocol_bindings.rows)
        self.assertFalse(self.case.explorer_revisions.rows)
        self.assertFalse(self.suggestions()['suggestions'])

    def test_same_source_baseline_rerun_deduplicated_and_foreign_project_hidden(self):
        self.run_import()
        suggestion = self.suggestions()['suggestions'][0]
        binding = self.case.explorer_history.protocol_binding(self.case.service.protocol_id)
        baseline = {'protocol_uuid': self.case.service.protocol_id, 'protocol_name': 'Fixture protocol',
                    'binding_version': binding['version'], 'revision_uuid': binding['revision_uuid'], 'recipe': binding['recipe']}
        before = len(self.case.events.rows), len(self.case.explorer_revisions.rows)
        result = self.case.protocol_suggestions.rerun([baseline], self.source_sha, self.source.name, 'fixture')
        self.assertEqual(result['counts']['deduplicated_count'], 1)
        self.assertEqual((len(self.case.events.rows), len(self.case.explorer_revisions.rows)), before)
        foreign = copy.deepcopy(self.case.suggestion_rows.rows[0])
        foreign['project_uuid'] = str(uuid.uuid4())
        foreign['suggestion_uuid'] = str(uuid.uuid4())
        foreign['summary']['protocol_uuid'] = str(uuid.uuid4())
        self.case.suggestion_rows.insert1(foreign)
        self.assertEqual(len(self.suggestions()['suggestions']), 1)
        self.assertEqual(self.suggestions()['suggestions'][0]['suggestion_uuid'], suggestion['suggestion_uuid'])

    def test_suggestion_audit_failure_rolls_back_candidate_only(self):
        insert = self.case.events.insert1
        def fail(row):
            if row['action'] == 'protocol_update_suggested':
                raise ValueError('Audit unavailable')
            insert(row)
        with patch.object(self.case.events, 'insert1', side_effect=fail):
            job = self.run_import()
        self.assertEqual(job['status'], 'complete_with_warnings')
        self.assertEqual(job['protocol_suggestions']['failed_count'], 1)
        self.assertFalse(self.case.suggestion_rows.rows)
        self.assertEqual(len(self.case.explorer_revisions.rows), 1)  # Baseline retained; candidate rolled back.
        self.assertEqual(len(self.case.service.rows), 3)
        self.assertEqual(len(self.case.service.query_result(self.case.service.protocol_id)['epochs']), 2)

    def test_post_import_refresh_failure_is_warning_and_baseline_stays_frozen(self):
        def commit_then_fail_refresh():
            self.add_recording()
            self.case.service.refresh = lambda: (_ for _ in ()).throw(ValueError('Read model validation failed'))
        job = self.run_import(commit_then_fail_refresh)
        self.assertEqual(job['status'], 'complete_with_warnings')
        self.assertEqual(job['warnings'][0]['stage'], 'post_import_refresh')
        self.assertEqual(len(self.case.service.query_result(self.case.service.protocol_id)['epochs']), 2)

    def test_bound_saved_predicate_reruns_without_widening_or_rebinding(self):
        service = self.case.service
        second = str(uuid.uuid4())
        workspace = copy.deepcopy(service.protocols[service.protocol_id])
        workspace['definition'].update(protocol_uuid=second, name='Existing saved subset')
        workspace['result']['protocol_uuid'] = second
        service.protocols[second] = workspace
        candidate = self.case.client.post('/api/explore/revisions', json={
            'predicate': {'field': 'parameters/example', 'operator': 'eq', 'value': 1},
            'splits': 'cell,block'}, headers=self.case.headers).get_json()
        root = '/api/explore/revisions/' + candidate['revision_uuid']
        comparison = self.case.client.post(root + '/compare-to-protocol', json={'protocol_uuid': second}, headers=self.case.headers).get_json()
        response = self.case.client.post(root + '/apply-to-protocol', json={'protocol_uuid': second,
            'expected_binding_version': comparison['expected_binding_version'],
            'expected_query_revision': comparison['expected_query_revision']}, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        old_binding = self.case.explorer_history.protocol_binding(second)
        job = self.run_import()
        self.assertEqual(job['protocol_suggestions']['created_count'], 1)
        self.assertEqual(job['protocol_suggestions']['unchanged_count'], 1)
        self.assertEqual(self.case.explorer_history.protocol_binding(second), old_binding)
        self.assertEqual([row['uuid'] for row in service.query_result(second)['epochs']], [self.before_ids[1]])

    def test_candidate_apply_rejects_stale_curation_then_preserves_tags_and_exclusion(self):
        self.run_import()
        suggestion = self.suggestions()['suggestions'][0]
        endpoint = '/api/explore/revisions/' + suggestion['candidate_revision_uuid']
        body = {'protocol_uuid': self.case.service.protocol_id}
        comparison = self.case.client.post(endpoint + '/compare-to-protocol', json=body, headers=self.case.headers).get_json()
        changed = self.case.client.post(self.case.base + '/curation', json=self.case.curation_body(
            {'tags_add': ['Keep source context'], 'included': False}, [self.before_ids[0]]), headers=self.case.headers)
        self.assertEqual(changed.status_code, 200, changed.get_json())
        request = {**body, 'expected_binding_version': comparison['expected_binding_version'],
                   'expected_query_revision': comparison['expected_query_revision']}
        stale = self.case.client.post(endpoint + '/apply-to-protocol', json=request, headers=self.case.headers)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.suggestions()['counts']['pending'], 1)
        comparison = self.case.client.post(endpoint + '/compare-to-protocol', json=body, headers=self.case.headers).get_json()
        request.update(expected_query_revision=comparison['expected_query_revision'])
        applied = self.case.client.post(endpoint + '/apply-to-protocol', json=request, headers=self.case.headers)
        self.assertEqual(applied.status_code, 200, applied.get_json())
        epochs = self.case.client.get(self.case.base + '/epochs').get_json()['epochs']
        original = next(row for row in epochs if row['epoch_uuid'] == self.before_ids[0])
        self.assertEqual(original['curation']['tags'], ['Keep source context'])
        self.assertFalse(original['curation']['included'])
        self.assertEqual(applied.get_json()['protocol']['counts']['approved'], 0)
