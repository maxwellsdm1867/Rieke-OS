"""New-only export and receipt-driven retries on disposable SQL/file fixtures."""
import copy
import json
import unittest
import uuid
from unittest.mock import patch

from test_workspace_workbench import WorkbenchTests


class IncomingExportTests(unittest.TestCase):
    setUp = WorkbenchTests.setUp
    get_context = WorkbenchTests.get_context
    save = WorkbenchTests.save
    accepted_request = WorkbenchTests.accepted_request
    accept = WorkbenchTests.accept

    def standalone_request(self, format='reference-json'):
        return dict(**self.accepted_request(), format=format, name='Incoming only')

    def receipt_export_request(self, acceptance, format='reference-json'):
        root = self.case.base + '/workbench/receipts/' + acceptance['operation_uuid']
        context = self.case.client.get(root + '/export-context')
        self.assertEqual(context.status_code, 200, context.get_json())
        self.assertEqual(set(context.get_json()['formats']), {'reference-json', 'wheeler-sqlite', 'matlab-mat'})
        return root, dict(expected_export_scope_revision=context.get_json()['export_scope_revision'],
            operation_uuid=str(uuid.uuid4()), format=format, name='Accepted additions')

    def artifact(self, receipt):
        response = self.case.client.get(receipt['download_url'])
        self.assertEqual(response.status_code, 200)
        try:
            return json.loads(response.data)
        finally:
            response.close()

    def test_export_new_reviewed_selection_does_not_accept_and_preserves_source_metadata(self):
        body = self.standalone_request()
        before = copy.deepcopy(self.case.protocol_bindings.rows)
        exported = self.case.client.post(self.root + '/exports', json=body, headers=self.case.headers)
        self.assertEqual(exported.status_code, 201, exported.get_json())
        receipt = exported.get_json()
        self.assertEqual(receipt['epoch_count'], 1)
        self.assertEqual(self.case.protocol_bindings.rows, before)
        self.assertFalse(self.case.curation.rows)
        package = self.artifact(receipt)
        self.assertEqual([row['epoch_uuid'] for row in package['epochs']], [self.added])
        row = package['epochs'][0]
        self.assertEqual(row['cell_uuid'], self.case.service.rows[self.added]['cell_uuid'])
        self.assertEqual(row['protocol_name'], 'example')
        self.assertEqual(row['parameters'], self.case.service.details[self.added]['parameters'])
        self.assertEqual(row['source_reference']['sha256'], self.case.service.rows[self.added]['source_sha256'])
        self.assertFalse(row['curation']['reviewed'])
        self.assertEqual(receipt['export_scope']['kind'], 'workbench_incoming')
        self.assertEqual(receipt['export_scope']['selection_authority'], 'frozen_review_preview')
        self.assertEqual(self.case.client.get(self.case.base + '/workbench').get_json()['pending_epoch_count'], 1)
        with patch.object(self.case.service, 'refresh', side_effect=ValueError('Unavailable source')), \
             patch.object(self.manager, 'proposal', side_effect=ValueError('Unavailable candidate')):
            repeated = self.case.client.post(self.root + '/exports', json=body, headers=self.case.headers)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.get_json(), receipt)
        self.assertEqual(len(self.case.datasets.rows), 1)
        changed = self.case.client.post(self.root + '/exports', json={**body, 'name': 'Different request'}, headers=self.case.headers)
        self.assertEqual(changed.status_code, 409)

    def test_accept_then_export_failure_keeps_receipt_and_export_retry_never_rebinds(self):
        acceptance = self.accept(self.accepted_request()).get_json()
        root, body = self.receipt_export_request(acceptance)
        before = copy.deepcopy(self.case.protocol_bindings.rows)
        self.case.app.config['TESTING'] = False
        with patch('workspace_workbench_exports.write_json', side_effect=OSError('Artifact staging failed')):
            failed = self.case.client.post(root + '/exports', json=body, headers=self.case.headers)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(self.case.protocol_bindings.rows, before)
        self.assertEqual(self.case.client.get(root).get_json(), acceptance)
        self.assertFalse(self.case.datasets.rows)
        exported = self.case.client.post(root + '/exports', json=body, headers=self.case.headers)
        self.assertEqual(exported.status_code, 201, exported.get_json())
        receipt = exported.get_json()
        self.assertEqual(receipt['accept_operation_uuid'], acceptance['operation_uuid'])
        self.assertEqual(receipt['epoch_count'], 1)
        self.assertEqual([row['epoch_uuid'] for row in self.artifact(receipt)['epochs']], [self.added])
        self.assertEqual(self.case.protocol_bindings.rows, before)
        with patch.object(self.case.service, 'refresh', side_effect=ValueError('Source gone')), \
             patch.object(self.manager, 'proposal', side_effect=ValueError('Candidate gone')):
            retry = self.case.client.post(root + '/exports', json=body, headers=self.case.headers)
        self.assertEqual(retry.get_json(), receipt)
        self.assertEqual(len(self.case.datasets.rows), 1)
        self.assertEqual(self.case.protocol_bindings.rows, before)

    def test_export_audit_or_receipt_failure_rolls_back_dataset_publication_only(self):
        acceptance = self.accept(self.accepted_request()).get_json()
        root, body = self.receipt_export_request(acceptance)
        before = copy.deepcopy([table.rows for table in self.case.connection.tables])
        insert = self.case.events.insert1
        def fail(row):
            if row['action'] == 'workbench_incoming_exported':
                raise RuntimeError('Export audit unavailable')
            insert(row)
        self.case.app.config['TESTING'] = False
        with patch.object(self.case.events, 'insert1', side_effect=fail):
            failed = self.case.client.post(root + '/exports', json=body, headers=self.case.headers)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual([table.rows for table in self.case.connection.tables], before)
        self.assertEqual(self.case.client.get(root).get_json(), acceptance)
        self.assertEqual(self.case.client.post(root + '/exports', json=body, headers=self.case.headers).status_code, 201)

    def test_export_receipt_insert_failure_is_atomic_with_dataset_and_keeps_acceptance(self):
        acceptance = self.accept(self.accepted_request()).get_json()
        root, body = self.receipt_export_request(acceptance)
        before = copy.deepcopy([table.rows for table in self.case.connection.tables])
        self.case.app.config['TESTING'] = False
        with patch.object(self.tables[2], 'insert1', side_effect=RuntimeError('Export receipt unavailable')):
            failed = self.case.client.post(root + '/exports', json=body, headers=self.case.headers)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual([table.rows for table in self.case.connection.tables], before)
        self.assertEqual(self.case.client.get(root).get_json(), acceptance)
        self.assertEqual(self.case.client.post(root + '/exports', json=body, headers=self.case.headers).status_code, 201)

    def test_matlab_annotation_grouping_is_explicitly_unsupported_before_staging(self):
        from workspace_workbench_exports import formats_for_candidate, publish_incoming_export
        context = self.manager.context(self.protocol, self.revision, 'actor-one')
        context['candidate'] = copy.deepcopy(context['candidate'])
        context['candidate']['tree_view']['fields'] = ['annotations/effective/tags']
        context['candidate']['splits'] = 'annotations/effective/tags'
        self.assertNotIn('matlab-mat', formats_for_candidate(context['candidate']))
        with patch('workspace_workbench_exports.managed_directory', side_effect=AssertionError('Never stage unsupported format')):
            with self.assertRaisesRegex(ValueError, 'MATLAB export cannot preserve'):
                publish_incoming_export(self.manager, self.case.store, context, context['incoming'], 'actor-one',
                    dict(format='matlab-mat', operation_uuid=str(uuid.uuid4())))

    def test_acceptance_export_rejects_changed_fingerprint_or_source_eligibility_without_rebinding(self):
        acceptance = self.accept(self.accepted_request()).get_json()
        root, body = self.receipt_export_request(acceptance)
        before = copy.deepcopy(self.case.protocol_bindings.rows)
        self.case.service._fingerprints[self.added] = 'c' * 64
        changed = self.case.client.post(root + '/exports', json=body, headers=self.case.headers)
        self.assertEqual(changed.status_code, 409)
        self.assertFalse(self.case.datasets.rows)
        self.assertEqual(self.case.protocol_bindings.rows, before)
        self.assertEqual(self.case.client.get(root).get_json(), acceptance)

    def test_selected_export_does_not_silently_omit_a_selected_source_that_became_ineligible(self):
        context = self.get_context()
        context = self.save(context, [dict(epoch_uuid=self.added, selected=True, reviewed=True)]).get_json()
        source = self.case.service.rows[self.added]['source_sha256']
        self.case.data_store_states.insert1(dict(project_uuid=self.case.service.project['project_uuid'], source_sha256=source,
            query_excluded=True, archived=False, frozen=False, version=1, updated_at=None,
            actor='actor-one', server_actor='actor-one', reason='test'))
        fresh = self.get_context()
        preview = self.case.client.post(self.root + '/preview', json=dict(expected_candidate_scope_revision=fresh['candidate_scope_revision'],
            expected_draft_version=fresh['draft']['draft_version'], mode='selected'), headers=self.case.headers)
        self.assertEqual(preview.status_code, 409)
        self.assertFalse(self.case.datasets.rows)

    def test_sqlite_export_uses_the_same_exact_new_only_selection(self):
        # SQLite deliberately recomputes scientific fingerprints. Give this
        # adapter a proper metadata/hierarchy oracle rather than 'b'*64 doubles.
        import hashlib
        for key, row in self.case.service.rows.items():
            self.case.service.details[key]['metadata'].update(cell={'uuid': row['cell_uuid'], 'start_time': row['start_time']},
                group={'uuid': row['group_uuid']}, block={'uuid': row['block_uuid']},
                epoch={'uuid': key, 'responses': {}, 'stimuli': {}})
            value = hashlib.sha256(json.dumps({'epoch': self.case.service.details[key],
                'source_sha256': row['source_sha256']}, sort_keys=True, allow_nan=False).encode()).hexdigest()
            self.case.service._fingerprints[key] = value
            row['metadata_hash'] = value
        self.case.service._tree_catalog_cache = {}
        self.case.service._registered_tree_cache = self.case.service._registered_predicate_cache = self.case.service._predicate_catalog_cache = None
        preview = self.case.service.explore_preview({'field': 'protocol', 'operator': 'eq', 'value': 'example'}, 'cell')
        preview['membership'] = [row for row in preview['membership'] if row['uuid'] in self.fixture.before_ids]
        preview['matched_count'] = 2
        baseline = self.case.explorer_history.create(preview, self.case.service.sources,
            self.case.service.project_dir / 'catalog.json', 'fixture', name='Verified baseline')
        self.case.explorer_history.bind(baseline['revision_uuid'], self.protocol, 1, 'fixture', {}, 2)
        binding = self.case.explorer_history.protocol_binding(self.protocol)
        result = self.case.protocol_suggestions.rerun([dict(protocol_uuid=self.protocol, protocol_name='Fixture',
            binding_version=binding['version'], revision_uuid=binding['revision_uuid'], recipe=binding['recipe'])],
            self.fixture.source_sha, 'verified.h5', 'actor-one')
        self.revision = result['suggestions'][0]['candidate_revision_uuid']
        self.root = self.case.base + '/workbench/candidates/' + self.revision
        body = self.standalone_request('wheeler-sqlite')
        exported = self.case.client.post(self.root + '/exports', json=body, headers=self.case.headers)
        self.assertEqual(exported.status_code, 201, exported.get_json())
        import sqlite3
        with sqlite3.connect(exported.get_json()['artifact_path']) as connection:
            ids = [row[0] for row in connection.execute('SELECT epoch_uuid FROM epochs')]
        self.assertEqual(ids, [self.added])

        reuse = self.case.client.get('/api/exports/' + exported.get_json()['dataset_uuid'] + '/reuse')
        self.assertEqual(reuse.status_code, 200, reuse.get_json())
        self.assertEqual(reuse.get_json()['kind'], 'workbench_incoming')


if __name__ == '__main__':
    unittest.main()
