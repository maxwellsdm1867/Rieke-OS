"""HTTP integration tests using an isolated project and transactional DB doubles.

No test here connects to or writes the research catalog. The Flask routes, recipe
files, curation validation, revision checks, and download checks are real.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import workspace_curation
from workspace_api import create_app
from workspace_explorer import ExplorerHistory
from workspace_datastores import DataStores
from workspace_service import WorkspaceService
if __package__:
    from .test_workspace_curation import Connection, Table
else:
    from test_workspace_curation import Connection, Table


class FixtureService(WorkspaceService):
    def __init__(self, folder):
        self.project_dir = Path(folder)
        self.project = {'project_uuid': str(uuid.uuid4()), 'name': 'HTTP fixture'}
        self.config = {'adapter': 'datajoint', 'catalog_id': 'fixture', 'database': 'schema'}
        self.curation_provider = None
        self._loaded = True
        self.protocol_id = str(uuid.uuid4())
        self.ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        self.cell_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        self.change_on_refresh = False
        self.refresh_count = 0
        self.rows, self.details, self.cells = {}, {}, {}
        self._fingerprints = {key: 'b' * 64 for key in self.ids}
        self.sources = [{'source_sha256': 'a' * 64,
                         'source_path': str(self.project_dir / 'fixture.h5'),
                         'filename': 'fixture.h5', 'counts': {'cells': 2, 'epochs': 2}}]
        self.manifests = {'a' * 64: {'source_path': self.sources[0]['source_path']}}
        for index, (key, cell) in enumerate(zip(self.ids, self.cell_ids)):
            self.rows[key] = {'epoch_uuid': key, 'cell_uuid': cell,
                'cell_label': f'Cell{index + 1}', 'cell_type': 'fixture-type',
                'date': '2026-09-24', 'start_time': f'09/24/2026 12:00:0{index}:000000',
                'group_uuid': str(uuid.uuid4()), 'group_label': 'Recorded group',
                'block_uuid': str(uuid.uuid4()), 'protocol_name': 'example',
                'duration_seconds': 1, 'streams': [], 'source_sha256': 'a' * 64,
                'metadata_hash': 'b' * 64, 'epoch_number': 1,
                'block_start_time': f'09/24/2026 12:00:0{index}:000000'}
            self.details[key] = {'parameters': {'example': index}, 'properties': {},
                                 'attributes': {}, 'metadata': {'epoch': {'uuid': key}}}
            self.cells[cell] = {'cell_uuid': cell, 'label': f'Cell{index + 1}',
                'cell_type': 'fixture-type', 'date': '2026-09-24',
                'start_time': self.rows[key]['start_time']}
        definition = {'format': 'recording-protocol-workspace', 'version': 1,
            'project_uuid': self.project['project_uuid'], 'protocol_uuid': self.protocol_id,
            'name': 'Fixture protocol', 'catalog_ref': '../catalog.json',
            'query': {'version': 1, 'all': [{'field': 'EpochBlock.protocol_name',
                                          'operator': 'eq', 'value': 'example'}]},
            'view': {'group_by': ['date', 'cell'], 'layout': 'landscape'}}
        self.protocols = {self.protocol_id: {'definition': definition,
            'file': self.project_dir / 'protocol.json',
            'result': {'project_uuid': self.project['project_uuid'],
                       'protocol_uuid': self.protocol_id, 'protocol_name': 'example',
                       'source_revisions': ['a' * 64],
                       'epochs': [{'uuid': key, 'metadata_hash': 'b' * 64} for key in self.ids],
                       'cells': [{'uuid': key} for key in self.cell_ids]}}}

    def refresh(self):
        self.refresh_count += 1
        if self.change_on_refresh:
            self._fingerprints = {key: 'c' * 64 for key in self.ids}
            self.change_on_refresh = False
        return {'epochs': len(self.rows)}

    def events(self, limit=100):
        return []


class WorkspaceAPITests(unittest.TestCase):
    def test_event_history_is_paged_and_full_evidence_is_loaded_separately(self):
        from unittest.mock import Mock
        from workspace_audit import build_audit_payload
        identity = str(uuid.uuid4())
        row = {"event_uuid": identity, "project_uuid": self.service.project["project_uuid"],
               "occurred_at": "2026-09-27T12:00:00+00:00", "actor": "fixture", "action": "curation_updated",
               "payload": build_audit_payload("curation_updated", "fixture", {"after": {"example": {"tags": ["check"]}}})}
        self.service.event_page = Mock(return_value={"events": [row], "has_more": False, "limit": 50, "offset": 0})
        self.service.event_detail = Mock(return_value=row)
        response = self.client.get('/api/events?offset=0&limit=50')
        self.assertEqual(response.status_code, 200)
        entry = response.get_json()['events'][0]
        self.assertNotIn('payload', entry)
        self.assertTrue(entry['audit_summary']['versioned'])
        self.assertEqual(entry['audit_summary']['entity_count'], 1)
        self.service.event_page.assert_called_once_with(50, 0, None)
        detail = self.client.get('/api/events/' + identity).get_json()['event']
        self.assertEqual(detail['payload']['after']['example']['tags'], ['check'])
        self.assertEqual(detail['provenance']['contracts']['audit_payload'], 1)
        self.assertEqual(self.client.get('/api/events?unsupported=1').status_code, 400)

    def test_managed_file_routes_report_locations_and_reject_escape(self):
        storage = self.client.get('/api/storage').get_json()
        self.assertEqual(storage['root'], str(Path(self.temp.name).resolve()))
        self.assertNotEqual(storage['root'], storage['code_root'])
        files = self.client.get('/api/files?path=protocols').get_json()
        self.assertEqual(files['entries'], [])
        for path in ('../', '/etc', 'database/mysql'):
            with self.subTest(path=path):
                response = self.client.get('/api/files', query_string={'path': path})
                self.assertEqual(response.status_code, 400)

    def test_browser_metadata_preserves_exact_source_ticks(self):
        epoch = self.service.ids[0]
        ticks = 639258608779858225
        self.service.details[epoch]['attributes']['startTimeDotNetDateTimeOffsetTicks'] = ticks
        response = self.client.get('/api/epochs/' + epoch)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['attributes']['startTimeDotNetDateTimeOffsetTicks'], str(ticks))
        self.assertEqual(self.service.details[epoch]['attributes']['startTimeDotNetDateTimeOffsetTicks'], ticks)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        isolated_index = patch.dict(os.environ, {'RIEKE_PROJECT_INDEX': str(Path(self.temp.name) / 'user-state/project-index.json')})
        isolated_index.start()
        self.addCleanup(isolated_index.stop)
        self.service = FixtureService(self.temp.name)
        self.curation = Table(('project_uuid', 'protocol_uuid', 'epoch_uuid'))
        self.datasets = Table(('project_uuid', 'dataset_uuid'))
        self.events = Table(('event_uuid',))
        self.sources = Table(('source_sha256',))
        self.sources.insert1({'source_sha256': 'a' * 64,
                             'project_uuid': self.service.project['project_uuid']})
        self.connection = Connection([self.curation, self.datasets, self.events, self.sources])
        class DJ:
            pass
        self.service.dj = DJ()
        self.service.dj.conn = lambda: self.connection
        with patch.object(workspace_curation, 'workspace_tables',
                          return_value=(None, self.sources, self.events, None)), \
             patch.object(workspace_curation, 'curation_tables',
                          return_value=(self.curation, self.datasets)):
            self.store = workspace_curation.CurationStore(self.service.dj, self.service.project['project_uuid'])
        self.explorer_revisions = Table(('project_uuid', 'revision_uuid'))
        self.protocol_bindings = Table(('project_uuid', 'protocol_uuid'))
        self.connection.tables.extend([self.explorer_revisions, self.protocol_bindings])
        self.explorer_history = ExplorerHistory(self.service.dj, self.service.project['project_uuid'],
            event_table=self.events, revision_table=self.explorer_revisions, binding_table=self.protocol_bindings)
        self.data_store_states = Table(('project_uuid', 'source_sha256'))
        self.connection.tables.append(self.data_store_states)
        self.data_stores = DataStores(self.service, self.store, self.explorer_history,
            state_table=self.data_store_states, source_table=self.sources, event_table=self.events)
        from workspace_suggestions import ProtocolSuggestions
        self.suggestion_rows = Table(('project_uuid', 'suggestion_uuid'))
        self.connection.tables.append(self.suggestion_rows)
        self.protocol_suggestions = ProtocolSuggestions(self.service, self.explorer_history, table=self.suggestion_rows)
        self.app = create_app(self.temp.name, self.temp.name, service=self.service, store=self.store,
                             explorer_history=self.explorer_history, data_stores=self.data_stores, protocol_suggestions=self.protocol_suggestions)
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.base = '/api/protocols/' + self.service.protocol_id
        self.headers = {'X-Workspace-Request': '1', 'Origin': 'http://localhost:8766'}

    def revision(self):
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()['query_revision']

    def curation_body(self, changes, ids=None):
        ids = self.service.ids if ids is None else ids
        return {'epoch_uuids': ids, 'changes': changes,
                'expected_revisions': {key: 0 for key in ids},
                'query_revision': self.revision()}

    def test_mutation_requires_request_header_and_allowed_origin(self):
        body = self.curation_body({'tags_add': ['checked']})
        missing = self.client.post(self.base + '/curation', json=body)
        foreign = self.client.post(self.base + '/curation', json=body,
            headers={'X-Workspace-Request': '1', 'Origin': 'https://foreign.example'})
        host = self.client.get('/api/overview', base_url='http://foreign.example')
        self.assertEqual((missing.status_code, foreign.status_code, host.status_code), (403, 403, 403))
        self.assertFalse(self.curation.rows)
        self.assertFalse(self.events.rows)

    def test_unknown_filter_fails_closed_and_pages_remain_bounded(self):
        unknown = self.client.get(self.base + '/epochs?sql=1%3D1')
        oversized = self.client.get(self.base + '/epochs?limit=10000')
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(oversized.status_code, 400)
        self.assertIn('Unknown query filter', unknown.get_json()['error'])
        page = self.client.get(self.base + '/epochs?limit=1').get_json()
        self.assertEqual(page['total'], 2)
        self.assertEqual(len(page['epochs']), 1)
        self.assertEqual(page['epochs'][0]['curation']['review_state'], 'unreviewed')

    def test_tag_and_exclude_saves_state_without_approval(self):
        body = self.curation_body({'tags_add': ['noisy'], 'included': False})
        response = self.client.post(self.base + '/curation', json=body, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(len(self.events.rows), 0)
        for key, state in response.get_json()['curation'].items():
            self.assertEqual(state['review_state'], 'unreviewed')
            self.assertEqual(state['tags'], ['noisy'])
            self.assertFalse(state['included'])
            self.assertEqual(state['revision'], 1)
        counts = self.client.get(self.base).get_json()['counts']
        self.assertEqual((counts['approved'], counts['excluded'], counts['exportable']), (0, 2, 0))

    def test_changed_source_metadata_blocks_old_approval_request(self):
        body = self.curation_body({'review_state': 'approved'})
        self.service.change_on_refresh = True
        response = self.client.post(self.base + '/curation', json=body, headers=self.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(response.get_json()['code'], 'stale_workspace')
        self.assertEqual(self.service.refresh_count, 1)
        self.assertFalse(self.curation.rows)
        self.assertFalse(self.events.rows)

    def test_out_of_query_selection_rejected(self):
        outside = str(uuid.uuid4())
        response = self.client.post(self.base + '/curation',
            json=self.curation_body({'tags_add': ['noisy']}, [outside]), headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('outside', response.get_json()['error'])
        self.assertFalse(self.curation.rows)
        self.assertFalse(self.events.rows)

    def test_approved_only_export_rejects_unreviewed_without_output(self):
        existing_files = set((Path(self.temp.name) / 'exports').iterdir())
        response = self.client.post(self.base + '/exports', json={
            'query_revision': self.revision(), 'review_policy': 'approved_only'}, headers=self.headers)
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertIn('No epochs eligible', response.get_json()['error'])
        self.assertFalse(self.datasets.rows)
        self.assertFalse(self.events.rows)
        self.assertEqual(set((Path(self.temp.name) / 'exports').iterdir()), existing_files)

    def test_invalid_export_filter_shape_never_broadens_membership(self):
        for invalid in ([], False, ""):
            with self.subTest(filters=invalid):
                response = self.client.post(self.base + '/exports', json={
                    'query_revision': self.revision(), 'review_policy': 'include_unreviewed',
                    'filters': invalid}, headers=self.headers)
                self.assertEqual(response.status_code, 400, response.get_json())
        self.assertFalse(self.datasets.rows)

    def test_export_rejects_unknown_tree_fields(self):
        response = self.client.post(self.base + '/exports', json={
            'query_revision': self.revision(), 'review_policy': 'include_unreviewed',
            'split_order': 'date, accidental-field'}, headers=self.headers)
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertFalse(self.datasets.rows)

    def test_explicit_unreviewed_export_freezes_query_selection_and_checksum(self):
        filters = {'cell_uuid': self.service.cell_ids[0]}
        response = self.client.post(self.base + '/exports', json={
            'query_revision': self.revision(), 'review_policy': 'include_unreviewed',
            'filters': filters, 'name': 'Fixture handoff', 'split_order': 'date, cell'}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        result = response.get_json()
        self.assertEqual(result['epoch_count'], 1)
        record = self.store.get_dataset_revision(result['dataset_uuid'])
        self.assertEqual(record['recipe']['query'], self.service.protocols[self.service.protocol_id]['definition']['query'])
        self.assertEqual(record['recipe']['options']['filters'], filters)
        self.assertEqual(len(record['recipe']['query_snapshot']['epochs']), 2)
        self.assertEqual([row['uuid'] for row in record['recipe']['epochs']], self.service.ids[:1])
        self.assertEqual(record['recipe']['review']['policy'], 'include_unreviewed')
        self.assertEqual(self.events.rows[-1]['action'], 'dataset_revision_exported')
        downloaded = self.client.get(result['download_url'])
        self.assertEqual(downloaded.status_code, 200)
        raw = downloaded.data
        downloaded.close()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), record['artifact_sha256'])
        package = json.loads(raw)
        self.assertEqual(package['format'], 'recording-reference-package')
        self.assertEqual(package['epochs'][0]['curation']['review_state'], 'unreviewed')
        self.assertEqual(package['sources'][0]['source_sha256'], 'a' * 64)
        self.assertEqual(package['epochs'][0]['epoch_uuid'], self.service.ids[0])
        reused = self.client.get('/api/exports/' + result['dataset_uuid'] + '/reuse')
        self.assertEqual(reused.status_code, 200)
        self.assertEqual(reused.get_json()['filters'], filters)
        self.assertEqual(reused.get_json()['split_order'], 'date, cell')
        self.assertEqual(reused.get_json()['source_export_uuid'], result['dataset_uuid'])
        self.service.protocols[self.service.protocol_id]['definition']['query']['all'][0]['value'] = 'different.Protocol'
        blocked = self.client.get('/api/exports/' + result['dataset_uuid'] + '/reuse')
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(self.store.get_dataset_revision(result['dataset_uuid'])['recipe'], record['recipe'])
        Path(record['artifact_path']).write_text('{"changed": true}')
        tampered = self.client.get(result['download_url'])
        self.assertEqual(tampered.status_code, 400)
        self.assertIn('changed', tampered.get_json()['error'])

    def mask(self):
        response = self.client.get(self.base + '/masks/export')
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def import_mask(self, mask, revision=None):
        return self.client.post(self.base + '/masks/import', json={
            'mask': mask, 'query_revision': revision or self.revision()}, headers=self.headers)

    def test_mask_roundtrip_is_exact_and_preserves_tags_and_approvals(self):
        approved = self.client.post(self.base + '/curation', json=self.curation_body({
            'tags_add': ['inspected'], 'review_state': 'approved'}), headers=self.headers)
        self.assertEqual(approved.status_code, 200)
        mask = self.mask()
        self.assertEqual(set(mask), {'format', 'version', 'protocol_uuid', 'source_revisions', 'epochs'})
        self.assertEqual(mask['source_revisions'], ['a' * 64])
        self.assertEqual({row['epoch_uuid'] for row in mask['epochs']}, set(self.service.ids))
        mask['epochs'][0]['included'] = False
        response = self.import_mask(mask)
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        self.assertEqual((result['imported_count'], result['included_count']), (2, 1))
        self.assertEqual(result['query_revision'], self.revision())
        self.assertEqual(len(self.events.rows), 0)
        for key, state in result['curation'].items():
            self.assertEqual(state['tags'], ['inspected'])
            self.assertEqual(state['review_state'], 'approved')
            self.assertEqual(state['revision'], 2)
        self.assertEqual(sum(row['included'] for row in result['curation'].values()), 1)
        self.assertEqual(self.mask(), mask)

    def test_mask_rejects_malformed_duplicate_unknown_or_partial_membership(self):
        import copy
        base = self.mask()
        variants = []
        extra = copy.deepcopy(base); extra['unexpected'] = 1; variants.append(extra)
        wrong_protocol = copy.deepcopy(base); wrong_protocol['protocol_uuid'] = str(uuid.uuid4()); variants.append(wrong_protocol)
        wrong_version = copy.deepcopy(base); wrong_version['version'] = True; variants.append(wrong_version)
        duplicate = copy.deepcopy(base); duplicate['epochs'][1] = duplicate['epochs'][0]; variants.append(duplicate)
        unknown = copy.deepcopy(base); unknown['epochs'][0]['epoch_uuid'] = str(uuid.uuid4()); variants.append(unknown)
        partial = copy.deepcopy(base); partial['epochs'].pop(); variants.append(partial)
        source = copy.deepcopy(base); source['source_revisions'] = ['c' * 64]; variants.append(source)
        duplicate_source = copy.deepcopy(base); duplicate_source['source_revisions'] *= 2; variants.append(duplicate_source)
        extra_epoch = copy.deepcopy(base); extra_epoch['epochs'][0]['review_state'] = 'approved'; variants.append(extra_epoch)
        for invalid in (1, 'false', None):
            value = copy.deepcopy(base); value['epochs'][0]['included'] = invalid; variants.append(value)
        for index, mask in enumerate(variants):
            with self.subTest(case=index):
                response = self.import_mask(mask)
                self.assertEqual(response.status_code, 400, response.get_json())
        self.assertFalse(self.curation.rows)
        self.assertFalse(self.events.rows)
        self.assertEqual(self.client.get(self.base + '/masks/export?cell_type=x').status_code, 400)

    def test_mask_import_rejects_changed_metadata_and_stale_curation(self):
        mask, revision = self.mask(), self.revision()
        self.service.change_on_refresh = True
        stale_source = self.import_mask(mask, revision)
        self.assertEqual(stale_source.status_code, 409)
        self.assertFalse(self.curation.rows)
        old_revision = self.revision()
        update = self.client.post(self.base + '/curation', json=self.curation_body({
            'tags_add': ['another-reviewer']}), headers=self.headers)
        self.assertEqual(update.status_code, 200)
        stale_curation = self.import_mask(mask, old_revision)
        self.assertEqual(stale_curation.status_code, 409)
        self.assertEqual(len(self.events.rows), 0)
        self.assertTrue(all(row['included'] for row in self.curation.rows))

    def test_mask_write_failure_rolls_back_entire_mixed_selection(self):
        mask = self.mask()
        mask['epochs'][0]['included'] = False
        original_insert = self.curation.insert1
        calls = []
        def fail_second(row):
            calls.append(row)
            if len(calls) == 2:
                raise RuntimeError('simulated second row failure')
            original_insert(row)
        with patch.object(self.curation, 'insert1', side_effect=fail_second), \
             self.assertLogs(self.app.logger, level='ERROR'):
            response = self.import_mask(mask)
        self.assertEqual(response.status_code, 500)
        self.assertFalse(self.curation.rows)
        self.assertFalse(self.events.rows)

    def test_tree_fields_exposes_recorded_fields_and_keeps_filtered_missing_fields(self):
        self.service.details[self.service.ids[0]]['parameters']['frequencyCutoff'] = 414
        self.service.details[self.service.ids[0]]['metadata']['group'] = {
            'properties': {'externalSolutionAdditions': 'NBQX5um'}}
        fields = self.client.get(self.base + '/tree-fields').get_json()
        by_id = {field['id']: field for field in fields['fields']}
        self.assertEqual(by_id['parameters/frequencyCutoff']['missing_count'], 1)
        self.assertIn('metadata/group/properties/externalSolutionAdditions', by_id)
        self.assertIn('frequency', {preset['id'] for preset in fields['presets']})
        filtered = self.client.get(self.base + '/tree', query_string={
            'splits': 'parameters/frequencyCutoff', 'cell_uuid': self.service.cell_ids[1]})
        self.assertEqual(filtered.status_code, 200, filtered.get_json())
        tree = filtered.get_json()
        self.assertEqual(tree['count'], 1)
        self.assertTrue(tree['children'][0]['missing'])
        self.assertEqual(tree['children'][0]['epoch_uuids'], self.service.ids[1:])
        self.assertEqual(tree['levels'][0]['missing_epochs'], 1)

    def test_tree_unknown_or_wrong_case_field_fails_closed_in_tree_and_export(self):
        self.service.details[self.service.ids[0]]['parameters']['frequencyCutoff'] = 414
        for field in ('parameters/frequencycutoff', 'parameters/notRecorded', 'SELECT * FROM Epoch'):
            with self.subTest(field=field):
                result = self.client.get(self.base + '/tree', query_string={'splits': field})
                self.assertEqual(result.status_code, 400, result.get_json())
                export = self.client.post(self.base + '/exports', json={
                    'query_revision': self.revision(), 'review_policy': 'include_unreviewed',
                    'split_order': field}, headers=self.headers)
                self.assertEqual(export.status_code, 400, export.get_json())
        self.assertFalse(self.datasets.rows)
        self.assertFalse(self.events.rows)
        self.assertEqual(list((Path(self.temp.name) / 'exports').rglob('recordings.json')), [])

    def test_export_saves_verified_dynamic_tree_order(self):
        self.service.details[self.service.ids[0]]['parameters']['frequencyCutoff'] = 414
        response = self.client.post(self.base + '/exports', json={
            'query_revision': self.revision(), 'review_policy': 'include_unreviewed',
            'split_order': 'cell, parameters/frequencyCutoff, block'}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        saved = self.store.get_dataset_revision(response.get_json()['dataset_uuid'])
        self.assertEqual(saved['recipe']['options']['split_order'], 'cell, parameters/frequencyCutoff, block')
        self.assertEqual({row['uuid'] for row in saved['recipe']['epochs']}, set(self.service.ids))

    def test_focused_epoch_export_freezes_exact_uuid_with_repeated_numbers(self):
        key = self.service.ids[1]  # Both fixture rows are Epoch 1.
        response = self.client.post(self.base + '/exports', json={
            'query_revision': self.revision(), 'filters': {'epoch_uuid': key},
            'review_policy': 'include_unreviewed'}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        saved = self.store.get_dataset_revision(response.get_json()['dataset_uuid'])
        self.assertEqual([row['uuid'] for row in saved['recipe']['epochs']], [key])
        self.assertEqual(response.get_json()['epoch_count'], 1)

    def test_focused_export_rejects_excluded_and_out_of_view_without_artifacts(self):
        initial_exports = set((Path(self.temp.name) / 'exports').rglob('*'))
        key = self.service.ids[0]
        self.client.post(self.base + '/curation', json=self.curation_body({'included': False}, [key]), headers=self.headers)
        for filters in ({'epoch_uuid': key}, {'epoch_uuid': self.service.ids[1], 'cell_uuid': self.service.cell_ids[0]}):
            response = self.client.post(self.base + '/exports', json={
                'query_revision': self.revision(), 'filters': filters}, headers=self.headers)
            self.assertEqual(response.status_code, 400, response.get_json())
        self.assertFalse(self.datasets.rows)
        self.assertEqual(set((Path(self.temp.name) / 'exports').rglob('*')), initial_exports)

    def test_selection_export_defaults_to_optional_review_and_links_exact_members(self):
        counts = self.client.get(self.base).get_json()['counts']
        self.assertEqual((counts['exportable'], counts['approved_exportable']), (2, 0))
        response = self.client.post(self.base + '/exports', json={
            'query_revision': self.revision(), 'filters': {'cell_uuid': self.service.cell_ids[0]},
            'name': 'Selected sample'}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        identity = response.get_json()['dataset_uuid']
        saved = self.store.get_dataset_revision(identity)
        self.assertEqual(saved['recipe']['review']['policy'], 'include_unreviewed')
        self.assertFalse(self.curation.rows)  # Export never confers review approval.
        linked = self.client.get('/api/epochs/' + self.service.ids[0], query_string={
            'protocol_uuid': self.service.protocol_id}).get_json()
        self.assertEqual(linked['catalog_ref'], {'database': 'schema',
            'project_uuid': self.service.project['project_uuid'], 'protocol_uuid': self.service.protocol_id})
        self.assertEqual(len(linked['exports']), 1)
        link = linked['exports'][0]
        self.assertEqual(link['dataset_uuid'], identity)
        self.assertEqual(link['name'], 'Selected sample')
        self.assertEqual(link['download_url'], '/api/exports/' + identity + '/download')
        self.assertTrue(link['metadata_matches'])
        self.assertEqual(link['artifact_sha256'], saved['artifact_sha256'])
        unlinked = self.client.get('/api/epochs/' + self.service.ids[1]).get_json()
        self.assertEqual(unlinked['exports'], [])
        self.assertEqual(unlinked['catalog_ref']['protocol_uuid'], None)
        overview = self.client.get('/api/overview').get_json()
        self.assertEqual((overview['counts']['exported'], overview['counts']['reviewed']), (1, 0))
        self.assertEqual(overview['protocols'][0]['counts']['exported'], 1)
        cell_counts = {cell['cell_uuid']: cell['exported'] for cell in overview['cells']}
        self.assertEqual(cell_counts, {self.service.cell_ids[0]: 1, self.service.cell_ids[1]: 0})
        protocol = self.client.get(self.base).get_json()
        self.assertEqual(protocol['counts']['exported'], 1)
        page = self.client.get(self.base + '/epochs').get_json()
        self.assertEqual({row['epoch_uuid']: row['export_count'] for row in page['epochs']},
                         {self.service.ids[0]: 1, self.service.ids[1]: 0})
        self.service._fingerprints[self.service.ids[0]] = 'c' * 64
        changed = self.client.get('/api/epochs/' + self.service.ids[0]).get_json()
        self.assertFalse(changed['exports'][0]['metadata_matches'])
        self.assertEqual(self.store.get_dataset_revision(identity)['recipe'], saved['recipe'])

    def test_optional_review_policy_intersects_approval_with_inclusion(self):
        first, second = self.service.ids
        approved = self.client.post(self.base + '/curation', json=self.curation_body(
            {'review_state': 'approved'}, [first]), headers=self.headers)
        self.assertEqual(approved.status_code, 200)
        counts = self.client.get(self.base).get_json()['counts']
        self.assertEqual((counts['exportable'], counts['approved_exportable'], counts['approved']), (2, 1, 1))
        explicit = self.client.post(self.base + '/exports', json={
            'query_revision': self.revision(), 'review_policy': 'approved_only'}, headers=self.headers)
        self.assertEqual(explicit.status_code, 201, explicit.get_json())
        strict_recipe = self.store.get_dataset_revision(explicit.get_json()['dataset_uuid'])['recipe']
        self.assertEqual([row['uuid'] for row in strict_recipe['epochs']], [first])
        self.assertEqual(strict_recipe['selection']['held_by_review'], [second])
        excluded = self.client.post(self.base + '/curation', json={
            'epoch_uuids': [first], 'changes': {'included': False},
            'expected_revisions': {first: 1}, 'query_revision': self.revision()}, headers=self.headers)
        self.assertEqual(excluded.status_code, 200)
        counts = self.client.get(self.base).get_json()['counts']
        self.assertEqual((counts['exportable'], counts['approved_exportable'], counts['approved']), (1, 0, 1))
        rejected = self.client.post(self.base + '/exports', json={
            'query_revision': self.revision(), 'review_policy': 'approved_only'}, headers=self.headers)
        self.assertEqual(rejected.status_code, 400)
        selected = self.client.post(self.base + '/exports', json={
            'query_revision': self.revision()}, headers=self.headers)
        self.assertEqual(selected.status_code, 201, selected.get_json())
        selected_recipe = self.store.get_dataset_revision(selected.get_json()['dataset_uuid'])['recipe']
        self.assertEqual([row['uuid'] for row in selected_recipe['epochs']], [second])
        self.assertEqual(selected_recipe['selection']['excluded'], [first])
        self.assertEqual(self.client.get('/api/overview').get_json()['counts']['exported'], 2)

    def test_project_explorer_discovers_epochs_without_saved_protocol_membership(self):
        import copy
        outside = str(uuid.uuid4())
        self.service.rows[outside] = {**copy.deepcopy(self.service.rows[self.service.ids[0]]),
            'epoch_uuid': outside, 'protocol_name': 'NewRecordedProtocol', 'group_label': 'Unassigned'}
        self.service.details[outside] = {'parameters': {'unassignedSetting': 9}, 'properties': {}, 'metadata': {}}
        before = copy.deepcopy((self.service.rows, self.service.details, self.curation.rows))
        with patch.object(self.service, 'query_result', side_effect=AssertionError('No saved protocol lookup')), \
             patch.object(self.store, 'read', side_effect=AssertionError('No curation read needed')), \
             patch('h5py.File', side_effect=AssertionError('No waveform reads')):
            fields = self.client.get('/api/explore/tree-fields')
            self.assertEqual(fields.status_code, 200, fields.get_json())
            data = fields.get_json()
            self.assertEqual(data['total'], 3)
            self.assertIn('protocol', data['suggestions'])
            self.assertIn('parameters/unassignedSetting', {field['id'] for field in data['fields']})
            tree = self.client.get('/api/explore/tree', query_string={
                'group_label': 'Unassigned', 'splits': 'parameters/unassignedSetting'})
            self.assertEqual(tree.status_code, 200, tree.get_json())
            self.assertEqual(tree.get_json()['children'][0]['epoch_uuids'], [outside])
            self.assertEqual(tree.get_json()['children'][0]['value'], 9)
            filtered_fields = self.client.get('/api/explore/tree-fields', query_string={'group_label': 'Recorded group'})
            self.assertEqual(filtered_fields.status_code, 200)
            field = next(field for field in filtered_fields.get_json()['fields'] if field['id'] == 'parameters/unassignedSetting')
            self.assertEqual((field['count'], field['missing_count']), (2, 2))
        self.assertEqual((self.service.rows, self.service.details, self.curation.rows), before)
        self.assertFalse(self.events.rows)
        self.assertFalse(self.datasets.rows)

    def test_project_explorer_rejects_unknown_parameters_invalid_ids_and_unknown_splits(self):
        for endpoint, query in (('/api/explore/tree-fields', {'sql': '1=1'}),
                                ('/api/explore/tree-fields', {'cell_uuid': 'Cell1'}),
                                ('/api/explore/tree', {'query': 'all'}),
                                ('/api/explore/tree', {'splits': 'parameters/imaginedProtocol'}),
                                ('/api/explore/tree', {'splits': 'cell, cell'})):
            with self.subTest(endpoint=endpoint, query=query):
                response = self.client.get(endpoint, query_string=query)
                self.assertEqual(response.status_code, 400, response.get_json())
        self.assertFalse(self.curation.rows)
        self.assertFalse(self.datasets.rows)
        self.assertFalse(self.events.rows)

    def test_two_named_exports_share_main_catalog_but_keep_filter_tree_and_tagged_membership(self):
        """Exercise saved export recipes; this does not imply a named-analysis editor."""
        import copy
        first, second = self.service.ids
        excluded = str(uuid.uuid4())
        self.service.rows[first]['group_label'] = 'Recorded condition A'
        self.service.rows[second]['group_label'] = 'Recorded condition B'
        self.service.rows[excluded] = {**copy.deepcopy(self.service.rows[first]),
            'epoch_uuid': excluded, 'epoch_number': 2, 'start_time': '09/24/2026 12:00:02:000000'}
        self.service.details[excluded] = copy.deepcopy(self.service.details[first])
        self.service.details[excluded]['metadata']['epoch']['uuid'] = excluded
        self.service._fingerprints[excluded] = 'b' * 64
        self.service.protocols[self.service.protocol_id]['result']['epochs'].append(
            {'uuid': excluded, 'metadata_hash': 'b' * 64})
        self.service.ids.append(excluded)
        raw_before = copy.deepcopy((self.service.rows, self.service.details))
        tagged = self.client.post(self.base + '/curation', json=self.curation_body({
            'tags_add': ['candidate']}), headers=self.headers)
        self.assertEqual(tagged.status_code, 200, tagged.get_json())
        deselected = self.client.post(self.base + '/curation', json={
            'epoch_uuids': [excluded], 'changes': {'included': False},
            'expected_revisions': {excluded: 1}, 'query_revision': self.revision()}, headers=self.headers)
        self.assertEqual(deselected.status_code, 200, deselected.get_json())
        definitions = [
            ('Cell-selected response', {'cell_uuid': self.service.cell_ids[0]}, 'date, cell, block', first),
            ('Condition-selected response', {'group_label': 'Recorded condition B'}, 'group label, block, cell', second),
        ]
        saved = []
        for name, filters, split_order, expected_epoch in definitions:
            response = self.client.post(self.base + '/exports', json={
                'name': name, 'filters': filters, 'split_order': split_order,
                'query_revision': self.revision()}, headers=self.headers)
            self.assertEqual(response.status_code, 201, response.get_json())
            record = self.store.get_dataset_revision(response.get_json()['dataset_uuid'])
            saved.append(copy.deepcopy(record))
            recipe = record['recipe']
            self.assertEqual(recipe['options']['name'], name)
            self.assertEqual(recipe['options']['filters'], filters)
            self.assertEqual(recipe['options']['split_order'], split_order)
            self.assertEqual([field['id'] for field in recipe['options']['tree_view']['fields']],
                             [field.strip() for field in split_order.split(',')])
            self.assertEqual(recipe['review']['policy'], 'include_unreviewed')
            self.assertEqual([row['uuid'] for row in recipe['epochs']], [expected_epoch])
            self.assertEqual({row['uuid'] for row in recipe['query_snapshot']['epochs']}, set(self.service.ids))
            self.assertIn(excluded, recipe['selection']['excluded'])
            package = json.loads(Path(record['artifact_path']).read_text())
            self.assertEqual([epoch['epoch_uuid'] for epoch in package['epochs']], [expected_epoch])
            self.assertEqual(package['epochs'][0]['curation']['tags'], ['candidate'])
            self.assertEqual(package['epochs'][0]['curation']['review_state'], 'unreviewed')
            self.assertTrue(package['epochs'][0]['curation']['included'])
            self.assertEqual(package['sources'][0]['source_sha256'], 'a' * 64)
            reused = self.client.get('/api/exports/' + record['dataset_uuid'] + '/reuse')
            self.assertEqual(reused.status_code, 200, reused.get_json())
            self.assertEqual(reused.get_json()['filters'], filters)
            self.assertEqual(reused.get_json()['split_order'], split_order)
            self.assertEqual(reused.get_json()['protocol_uuid'], self.service.protocol_id)
        left, right = (record['recipe'] for record in saved)
        for field in ('project_uuid', 'protocol_uuid', 'catalog_ref', 'query', 'query_sha256', 'source_revisions'):
            self.assertEqual(left[field], right[field])
        self.assertEqual(left['catalog_ref'], str(Path(self.temp.name).resolve() / 'catalog.json'))
        self.assertEqual(left['source_revisions'], ['a' * 64])
        self.assertNotEqual(left['export_uuid'], right['export_uuid'])
        self.assertNotEqual(left['options']['filters'], right['options']['filters'])
        self.assertNotEqual(left['options']['split_order'], right['options']['split_order'])
        for record in saved:
            self.assertEqual(self.store.get_dataset_revision(record['dataset_uuid'])['recipe'], record['recipe'])
        current = self.store.read(self.service.protocol_id, self.service.ids, self.service._fingerprints)
        self.assertFalse(current[excluded]['included'])
        self.assertEqual(current[excluded]['tags'], ['candidate'])
        self.assertTrue(all(value['review_state'] == 'unreviewed' for value in current.values()))
        self.assertEqual((self.service.rows, self.service.details), raw_before)

    def test_source_predicate_preview_preserves_nested_groups_and_is_read_only(self):
        import copy
        fields = self.client.get('/api/explore/predicate-fields')
        self.assertEqual(fields.status_code, 200, fields.get_json())
        example = next(field for field in fields.get_json()['fields'] if field['id'] == 'parameters/example')
        self.assertEqual(example['types'], ['number'])
        self.assertEqual({choice['value'] for choice in example['choices']}, {0, 1})
        predicate = {'all': [{'field': 'protocol', 'operator': 'eq', 'value': 'example'},
            {'any': [{'field': 'parameters/example', 'operator': 'eq', 'value': 0},
                     {'not': {'field': 'parameters/example', 'operator': 'gte', 'value': 0}}]}]}
        before = copy.deepcopy((self.service.rows, self.service.details))
        with patch.object(self.store, 'read', side_effect=AssertionError('No curation predicate access')), \
             patch('h5py.File', side_effect=AssertionError('No waveform read')):
            response = self.client.post('/api/explore/preview', json={
                'predicate': predicate, 'splits': 'date, cell'}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        preview = response.get_json()
        self.assertEqual((preview['total_source'], preview['matched_count']), (2, 1))
        self.assertEqual(preview['predicate'], predicate)
        self.assertEqual([member['uuid'] for member in preview['membership']], self.service.ids[:1])
        self.assertEqual(preview['tree']['count'], 1)
        self.assertEqual(preview['catalog']['total'], 1)
        self.assertEqual((self.service.rows, self.service.details), before)
        self.assertFalse(self.explorer_revisions.rows)
        self.assertFalse(self.events.rows)
        self.assertFalse(self.curation.rows)
        self.assertEqual(self.service.refresh_count, 0)

    def test_applied_source_query_tree_history_is_exact_immutable_and_paged(self):
        import copy
        predicate = {'all': []}
        applied = self.client.post('/api/explore/revisions', json={
            'predicate': predicate, 'splits': 'cell, date', 'name': 'All recorded cells'}, headers=self.headers)
        self.assertEqual(applied.status_code, 201, applied.get_json())
        first = applied.get_json()
        frozen = copy.deepcopy(first['recipe'])
        self.assertEqual(first['recipe']['predicate'], predicate)
        self.assertEqual(first['recipe']['source_revisions'], ['a' * 64])
        self.assertEqual({member['uuid'] for member in first['recipe']['epochs']}, set(self.service.ids))
        self.assertEqual(first['preview']['membership'], first['recipe']['epochs'])
        self.assertEqual(first['recipe']['tree_view']['fields'], ['cell', 'date'])
        self.assertEqual(first['recipe']['provenance']['contracts']['source_predicate'], 1)
        self.assertEqual(first['recipe']['provenance']['code']['python/workspace_predicates.py']['status'], 'recorded')
        self.assertEqual(self.events.rows[0]['action'], 'explorer_revision_created')
        self.assertEqual(self.events.rows[0]['payload']['recipe_sha256'], first['recipe']['content_sha256'])
        self.assertEqual(self.events.rows[0]['event_uuid'], first['revision_uuid'])
        subset = {'field': 'parameters/example', 'operator': 'eq', 'value': 1}
        child = self.client.post('/api/explore/revisions', json={
            'predicate': subset, 'splits': 'date, cell', 'name': 'One cell',
            'parent_revision_uuid': first['revision_uuid']}, headers=self.headers)
        self.assertEqual(child.status_code, 201, child.get_json())
        second = child.get_json()
        self.assertEqual(second['recipe']['diff'], {'added': [], 'removed': self.service.ids[:1], 'changed': []})
        self.assertEqual(second['summary']['diff_counts'], {'added': 0, 'removed': 1, 'changed': 0})
        self.assertEqual(second['recipe']['parent_revision_uuid'], first['revision_uuid'])
        self.assertEqual([member['uuid'] for member in second['recipe']['epochs']], self.service.ids[1:])
        page = self.client.get('/api/explore/revisions?limit=1').get_json()
        self.assertEqual(len(page['revisions']), 1)
        self.assertTrue(page['has_more'])
        self.assertNotIn('recipe', page['revisions'][0])
        self.assertNotIn('recipe', self.explorer_revisions.read_log[-1]['projected'])
        last = self.client.get('/api/explore/revisions?limit=1&offset=1').get_json()
        self.assertFalse(last['has_more'])
        self.service._fingerprints[self.service.ids[0]] = 'c' * 64
        stored = self.client.get('/api/explore/revisions/' + first['revision_uuid'])
        self.assertEqual(stored.get_json()['recipe'], frozen)
        rerun = self.client.post('/api/explore/preview', json={
            'predicate': frozen['predicate'], 'splits': frozen['splits']}, headers=self.headers).get_json()
        self.assertEqual(next(row['metadata_hash'] for row in rerun['membership'] if row['uuid'] == self.service.ids[0]), 'c' * 64)
        self.assertEqual(len(self.events.rows), 2)
        self.assertFalse(self.datasets.rows)
        self.assertFalse(self.curation.rows)
        self.assertEqual(self.service.refresh_count, 2)

    def test_explorer_history_rejects_cross_project_parent_and_record_access(self):
        import copy
        created = self.client.post('/api/explore/revisions', json={
            'predicate': {'all': []}, 'splits': 'date'}, headers=self.headers).get_json()
        foreign = copy.deepcopy(self.explorer_revisions.rows[0])
        foreign['project_uuid'] = str(uuid.uuid4())
        foreign['revision_uuid'] = str(uuid.uuid4())
        self.explorer_revisions.insert1(foreign)
        blocked = self.client.get('/api/explore/revisions/' + foreign['revision_uuid'])
        self.assertEqual(blocked.status_code, 400)
        self.assertIn('not found in this project', blocked.get_json()['error'])
        parent = self.client.post('/api/explore/revisions', json={
            'predicate': {'all': []}, 'splits': 'date', 'parent_revision_uuid': foreign['revision_uuid']}, headers=self.headers)
        self.assertEqual(parent.status_code, 400)
        self.assertEqual(len(self.events.rows), 1)
        page = self.client.get('/api/explore/revisions').get_json()
        self.assertEqual([row['revision_uuid'] for row in page['revisions']], [created['revision_uuid']])
        for method in ('put', 'delete', 'patch'):
            response = getattr(self.client, method)('/api/explore/revisions/' + created['revision_uuid'], headers=self.headers)
            self.assertEqual(response.status_code, 405)

    def test_explorer_revision_and_audit_commit_or_rollback_together(self):
        with patch.object(self.events, 'insert1', side_effect=RuntimeError('audit unavailable')), \
             self.assertLogs(self.app.logger, level='ERROR'):
            response = self.client.post('/api/explore/revisions', json={
                'predicate': {'all': []}, 'splits': 'date'}, headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertFalse(self.explorer_revisions.rows)
        self.assertFalse(self.events.rows)

    def test_explorer_predicate_bad_types_unknown_fields_and_input_limits_fail_closed(self):
        invalid = [None, {}, {'not': []}, {'field': 'parameters/example', 'operator': 'eq', 'value': '1'},
                   {'field': 'parameters/unknown', 'operator': 'eq', 'value': 1},
                   {'field': 'parameters/example', 'operator': 'eq', 'value': 10 ** 400},
                   {'field': 'parameters/example', 'operator': 'eq', 'value': 2**53 + 1}]
        for predicate in invalid:
            for endpoint in ('preview', 'revisions'):
                with self.subTest(endpoint=endpoint, predicate=str(predicate)[:100]):
                    response = self.client.post('/api/explore/' + endpoint, json={
                        'predicate': predicate, 'splits': 'date'}, headers=self.headers)
                    self.assertEqual(response.status_code, 400, response.get_json())
        oversized = self.client.post('/api/explore/preview', json={
            'predicate': {'all': []}, 'splits': ' ' * 70000}, headers=self.headers)
        self.assertEqual(oversized.status_code, 400)
        self.assertEqual(self.client.get('/api/explore/revisions?limit=1000').status_code, 400)
        self.assertEqual(self.client.get('/api/explore/revisions?offset=-1').status_code, 400)
        self.assertEqual(self.client.get('/api/explore/predicate-fields?cell_uuid=x').status_code, 400)
        self.assertFalse(self.events.rows)
        self.assertFalse(self.explorer_revisions.rows)

    def test_protocol_comparison_reports_exact_counts_but_rejects_mixed_acquisition_ids(self):
        import copy
        extra = str(uuid.uuid4())
        self.service.rows[extra] = {**copy.deepcopy(self.service.rows[self.service.ids[0]]),
            'epoch_uuid': extra, 'protocol_name': 'AnotherRecordedProtocol',
            'epoch_number': 2, 'duration_seconds': 2.5}
        self.service.details[extra] = copy.deepcopy(self.service.details[self.service.ids[0]])
        self.service.details[extra]['metadata']['epoch']['uuid'] = extra
        self.service._fingerprints[extra] = 'b' * 64
        candidate = self.client.post('/api/explore/revisions', json={
            'predicate': {'all': []}, 'splits': 'cell, protocol'}, headers=self.headers)
        self.assertEqual(candidate.status_code, 201, candidate.get_json())
        identity = candidate.get_json()['revision_uuid']
        comparison = self.client.post('/api/explore/revisions/' + identity + '/compare-to-protocol',
            json={'protocol_uuid': self.service.protocol_id}, headers=self.headers)
        self.assertEqual(comparison.status_code, 200, comparison.get_json())
        result = comparison.get_json()
        summary = result['diff_summary']
        self.assertEqual(summary['current']['cells'], 2)
        self.assertEqual(summary['proposed']['cells'], 2)
        self.assertEqual(summary['delta']['cells'], 0)
        self.assertEqual(summary['delta']['epochs'], 1)
        self.assertEqual(summary['delta']['acquisition_protocols'], 1)
        self.assertEqual(summary['delta']['duration_seconds'], 2.5)
        self.assertEqual(summary['cell_changes']['counts'], {'added': 0, 'removed': 0, 'updated': 1})
        self.assertEqual(summary['cell_changes']['updated'][0]['epochs_added'], 1)
        applied = self.client.post('/api/explore/revisions/' + identity + '/apply-to-protocol', json={
            'protocol_uuid': self.service.protocol_id,
            'expected_binding_version': result['expected_binding_version'],
            'expected_query_revision': result['expected_query_revision']}, headers=self.headers)
        self.assertFalse(result['compatibility']['compatible'])
        self.assertEqual(applied.status_code, 400, applied.get_json())
        self.assertIn('Protocol mismatch', applied.get_json()['error'])
        self.assertFalse(any(event['action']=='protocol_dataset_bound' for event in self.events.rows))
        self.assertEqual(len(self.service.query_result(self.service.protocol_id)['epochs']),2)



if __name__ == '__main__':
    unittest.main()
