"""Protocol publication must preserve exactly the predicate-selected working set.

Uses the isolated HTTP fixture and in-memory transactional relations only.
"""
import copy
import json
import uuid
from unittest.mock import patch

if __package__:
    from . import test_workspace_api as api_tests
else:
    import test_workspace_api as api_tests


class ProtocolBindingTests(api_tests.WorkspaceAPITests):
    # Reuse setup/helpers, not the base class's test methods (installed below).
    def save_candidate(self, predicate, name='Candidate', splits='cell'):
        response = self.client.post('/api/explore/revisions', json={
            'predicate': predicate, 'splits': splits, 'name': name}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def comparison(self, candidate):
        response = self.client.post('/api/explore/revisions/' + candidate['revision_uuid'] + '/compare-to-protocol',
            json={'protocol_uuid': self.service.protocol_id}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def apply_candidate(self, candidate, comparison=None):
        proposed = comparison or self.comparison(candidate)
        return self.client.post('/api/explore/revisions/' + candidate['revision_uuid'] + '/apply-to-protocol',
            json={'protocol_uuid': self.service.protocol_id,
                  'expected_binding_version': proposed['expected_binding_version'],
                  'expected_query_revision': proposed['expected_query_revision']}, headers=self.headers)

    def narrow(self):
        return self.save_candidate({'all': [
            {'field': 'protocol', 'operator': 'eq', 'value': 'example'},
            {'field': 'parameters/example', 'operator': 'eq', 'value': 0}]})

    def test_binding_controls_protocol_tree_masks_and_exports_without_changing_source(self):
        original_rows = copy.deepcopy(self.service.rows)
        original_definition = copy.deepcopy(self.service.protocols[self.service.protocol_id]['definition'])
        candidate = self.narrow()
        comparison = self.comparison(candidate)
        self.assertEqual(self.client.get(self.base).get_json()['counts']['epochs'], 2)
        applied = self.apply_candidate(candidate, comparison)
        self.assertEqual(applied.status_code, 200, applied.get_json())
        protocol = self.client.get(self.base).get_json()
        self.assertEqual(protocol['counts']['epochs'], 1)
        epochs = self.client.get(self.base + '/epochs').get_json()
        self.assertEqual([row['epoch_uuid'] for row in epochs['epochs']], self.service.ids[:1])
        self.assertEqual(self.client.get(self.base + '/tree?splits=cell').get_json()['count'], 1)
        mask = self.client.get(self.base + '/masks/export').get_json()
        self.assertEqual([row['epoch_uuid'] for row in mask['epochs']], self.service.ids[:1])
        response = self.client.post(self.base + '/exports', json={
            'name': 'Bound selection', 'review_policy': 'include_unreviewed',
            'filters': {}, 'query_revision': protocol['query_revision'], 'split_order': 'cell'}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        package = self.client.get(response.get_json()['download_url']).get_json()
        self.assertEqual([row['epoch_uuid'] for row in package['epochs']], self.service.ids[:1])
        self.assertEqual(package['recipe']['query']['kind'], 'source_predicate')
        self.assertEqual(package['recipe']['query']['predicate'], candidate['recipe']['predicate'])
        self.assertEqual(self.service.rows, original_rows)
        self.assertEqual(self.service.protocols[self.service.protocol_id]['definition'], original_definition)
        self.assertEqual(self.client.get('/api/overview').get_json()['counts']['epochs'], 2)

    def test_updated_protocol_preserves_annotations_and_previous_export(self):
        first = self.narrow()
        applied = self.apply_candidate(first)
        self.assertEqual(applied.status_code, 200, applied.get_json())
        edit = self.client.post(self.base + '/curation', json=self.curation_body(
            {'tags_add': ['kept-cell']}, ids=self.service.ids[:1]), headers=self.headers)
        self.assertEqual(edit.status_code, 200, edit.get_json())
        exported = self.client.post(self.base + '/exports', json={
            'name': 'First working version', 'review_policy': 'include_unreviewed',
            'filters': {}, 'query_revision': self.revision(), 'split_order': 'cell'}, headers=self.headers)
        self.assertEqual(exported.status_code, 201, exported.get_json())
        url = exported.get_json()['download_url']
        old_bytes = self.client.get(url).data
        candidate = self.save_candidate({'all': []}, name='Updated working set')
        result = self.apply_candidate(candidate)
        self.assertEqual(result.status_code, 200, result.get_json())
        current = self.client.get(self.base + '/epochs').get_json()['epochs']
        self.assertEqual({row['epoch_uuid'] for row in current}, set(self.service.ids))
        by_id = {row['epoch_uuid']: row for row in current}
        self.assertEqual(by_id[self.service.ids[0]]['curation']['tags'], ['kept-cell'])
        self.assertEqual(by_id[self.service.ids[1]]['curation']['tags'], [])
        self.assertFalse(by_id[self.service.ids[1]]['curation']['reviewed'])
        self.assertEqual(self.client.get(url).data, old_bytes)
        self.assertEqual(len(self.client.get('/api/explore/revisions').get_json()['revisions']), 2)

    def test_new_source_refresh_proposes_diff_without_switching_working_dataset(self):
        first = self.save_candidate({'all': []})
        self.assertEqual(self.apply_candidate(first).status_code, 200)
        new_id = str(uuid.uuid4())
        self.service.rows[new_id] = {**self.service.rows[self.service.ids[0]],
            'epoch_uuid': new_id, 'source_sha256': 'd' * 64}
        self.service.details[new_id] = copy.deepcopy(self.service.details[self.service.ids[0]])
        self.service._fingerprints[new_id] = 'e' * 64
        self.service.sources.append({'source_sha256': 'd' * 64, 'filename': 'new-fixture.h5'})
        self.service._tree_catalog_cache = {}
        self.service._predicate_catalog_cache = None
        response = self.client.post(self.base + '/refresh', json={}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        self.assertEqual(result['diff']['added'], [new_id])
        self.assertEqual(result['diff']['removed'], [])
        self.assertEqual(self.client.get(self.base).get_json()['counts']['epochs'], 2)
        candidate = self.client.get('/api/explore/revisions/' + result['candidate_revision_uuid']).get_json()
        self.assertEqual(self.apply_candidate(candidate).status_code, 200)
        self.assertEqual(self.client.get(self.base).get_json()['counts']['epochs'], 3)
        self.assertEqual(self.client.get('/api/explore/revisions/' + first['revision_uuid']).get_json()['recipe']['matched_count'], 2)

    def test_stale_target_apply_cannot_overwrite_newer_binding(self):
        first = self.narrow()
        old_comparison = self.comparison(first)
        second = self.save_candidate({'all': []}, name='Full candidate')
        applied = self.apply_candidate(second)
        self.assertEqual(applied.status_code, 200, applied.get_json())
        rejected = self.apply_candidate(first, old_comparison)
        self.assertEqual(rejected.status_code, 409, rejected.get_json())
        self.assertEqual(self.client.get(self.base).get_json()['counts']['epochs'], 2)

    def test_source_change_after_candidate_save_requires_rerun(self):
        candidate = self.narrow()
        proposed = self.comparison(candidate)
        self.service.change_on_refresh = True
        response = self.apply_candidate(candidate, proposed)
        self.assertIn(response.status_code, (400, 409), response.get_json())
        self.assertEqual(self.client.get(self.base).get_json()['counts']['epochs'], 2)

    def test_apply_event_failure_rolls_back_protocol_binding(self):
        candidate = self.narrow()
        proposed = self.comparison(candidate)
        before_events = copy.deepcopy(self.events.rows)
        with patch.object(self.events, 'insert1', side_effect=RuntimeError('Fixture audit write failed')):
            response = self.apply_candidate(candidate, proposed)
        self.assertEqual(response.status_code, 500, response.get_json())
        self.assertEqual(self.events.rows, before_events)
        self.assertEqual(self.client.get(self.base).get_json()['counts']['epochs'], 2)


    def test_exact_acquisition_identity_blocks_wrong_and_mixed_destinations(self):
        self.service.rows[self.service.ids[1]]['protocol_name'] = 'other.example'
        self.service._predicate_catalog_cache = None
        self.service._tree_catalog_cache = {}
        for predicate in ({'all': []}, {'all': [{'field':'protocol','operator':'eq','value':'other.example'}]}):
            candidate = self.save_candidate(predicate)
            comparison = self.comparison(candidate)
            self.assertFalse(comparison['compatibility']['compatible'])
            self.assertEqual(comparison['compatibility']['expected_protocol_id'], 'example')
            self.assertEqual(comparison['compatibility']['incompatible_epoch_count'], 1)
            before = copy.deepcopy(self.protocol_bindings.rows)
            response = self.apply_candidate(candidate, comparison)
            self.assertEqual(response.status_code, 400, response.get_json())
            self.assertIn('Protocol mismatch', response.get_json()['error'])
            self.assertEqual(self.protocol_bindings.rows, before)

    def test_reduced_same_protocol_selection_remains_valid(self):
        candidate = self.narrow(); comparison = self.comparison(candidate)
        self.assertTrue(comparison['compatibility']['compatible'])
        self.assertEqual(comparison['diff_counts']['removed'], 1)
        self.assertEqual(self.apply_candidate(candidate, comparison).status_code, 200)

    def test_protocol_export_rechecks_identity_even_for_legacy_bad_binding(self):
        self.service.rows[self.service.ids[1]]['protocol_name'] = 'other.example'
        candidate = self.save_candidate({'all': []})
        self.explorer_history.bind(candidate['revision_uuid'],self.service.protocol_id,0,'fixture',{},2)
        response = self.client.post(self.base + '/exports',json={
            'name':'wrong export','query_revision':self.revision(),'review_policy':'include_unreviewed'},headers=self.headers)
        self.assertEqual(response.status_code,400,response.get_json())
        self.assertIn('Protocol mismatch',response.get_json()['error'])
        self.assertEqual(self.datasets.rows,[])

    def create_protocol(self,candidate,**overrides):
        body={'name':'Narrow example','protocol_id':'example',
              'expected_recipe_sha256':candidate['recipe']['content_sha256'],**overrides}
        return self.client.post('/api/explore/revisions/'+candidate['revision_uuid']+'/create-protocol',json=body,headers=self.headers)

    def test_create_pinned_protocol_is_persistent_exact_and_retry_safe(self):
        candidate=self.narrow(); old=copy.deepcopy(self.service.protocols[self.service.protocol_id])
        result=self.create_protocol(candidate)
        self.assertEqual(result.status_code,201,result.get_json())
        identity=result.get_json()['protocol_uuid'];base='/api/protocols/'+identity
        self.assertEqual(result.get_json()['epoch_count'],1)
        definition=json.loads(self.service.protocol_file(identity).read_text())
        self.assertEqual(definition['query']['all'][0]['value'],'example')
        self.assertEqual(definition['initial_revision_uuid'],candidate['revision_uuid'])
        self.assertEqual(self.service.protocols[self.service.protocol_id],old)
        protocol=self.client.get(base).get_json()
        self.assertEqual(protocol['counts']['epochs'],1)
        self.assertEqual(self.client.get(base+'/epochs').get_json()['epochs'][0]['epoch_uuid'],self.service.ids[0])
        events=len(self.events.rows)
        retry=self.create_protocol(candidate)
        self.assertEqual(retry.status_code,200,retry.get_json())
        self.assertEqual(retry.get_json()['protocol_uuid'],identity)
        self.assertEqual(len(self.events.rows),events)
        exported=self.client.post(base+'/exports',json={'name':'New selection',
            'review_policy':'include_unreviewed','query_revision':protocol['query_revision'],'split_order':'cell'},headers=self.headers)
        self.assertEqual(exported.status_code,201,exported.get_json())
        package=self.client.get(exported.get_json()['download_url']).get_json()
        self.assertEqual([row['epoch_uuid'] for row in package['epochs']],self.service.ids[:1])

    def test_creation_rejects_mixed_empty_mismatched_identity_and_stale_preview(self):
        self.service.rows[self.service.ids[1]]['protocol_name']='other.example'
        for predicate,override in [({'all': []},{}),
                ({'all':[{'field':'protocol','operator':'eq','value':'absent'}]},{}),
                ({'all':[{'field':'protocol','operator':'eq','value':'example'}]},{'protocol_id':'other.example'}),
                ({'all':[{'field':'protocol','operator':'eq','value':'example'}]},{'expected_recipe_sha256':'0'*64})]:
            candidate=self.save_candidate(predicate)
            response=self.create_protocol(candidate,**override)
            self.assertIn(response.status_code,(400,409),response.get_json())
            self.assertEqual(len(self.service.protocols),1)
            self.assertFalse(list((self.service.project_dir/'protocols').glob('*.protocol.json')))
            self.assertEqual(self.protocol_bindings.rows,[])

    def test_create_audit_failure_leaves_no_manifest_or_binding(self):
        candidate=self.narrow(); before=copy.deepcopy(self.events.rows)
        with patch.object(self.events,'insert1',side_effect=RuntimeError('Audit unavailable')):
            result=self.create_protocol(candidate)
        self.assertEqual(result.status_code,500)
        self.assertEqual(self.events.rows,before)
        self.assertEqual(self.protocol_bindings.rows,[])
        self.assertFalse(list((self.service.project_dir/'protocols').glob('*.protocol.json')))

    def test_manifest_publication_failure_rolls_back_new_binding(self):
        candidate=self.narrow();before=copy.deepcopy(self.events.rows)
        with patch('json.dump',side_effect=OSError('Disk full')):
            result=self.create_protocol(candidate)
        self.assertEqual(result.status_code,500,result.get_json())
        self.assertEqual(self.protocol_bindings.rows,[])
        self.assertEqual(self.events.rows,before)
        self.assertEqual(len(self.service.protocols),1)
        self.assertFalse(list((self.service.project_dir/'protocols').glob('*.protocol.json')))

    def test_missing_initial_binding_never_falls_back_to_base_query(self):
        candidate=self.narrow();created=self.create_protocol(candidate).get_json()
        identity=created['protocol_uuid']
        self.protocol_bindings.rows.clear()
        with self.assertRaisesRegex(ValueError,'interrupted'):
            self.service.query_result(identity)
        repaired=self.create_protocol(candidate)
        self.assertEqual(repaired.status_code,201,repaired.get_json())
        self.assertEqual(repaired.get_json()['protocol_uuid'],identity)
        self.assertEqual(len(self.service.query_result(identity)['epochs']),1)

    def test_options_report_real_ids_and_counts(self):
        candidate=self.narrow()
        result=self.client.get('/api/explore/revisions/'+candidate['revision_uuid']+'/protocol-options')
        self.assertEqual(result.status_code,200,result.get_json())
        self.assertEqual(result.get_json()['protocols'],[{'protocol_id':'example','epoch_count':1}])
        self.assertEqual(result.get_json()['cell_count'],1)


# Only this module's new tests should run; inherited regression cases are already
# discovered from test_workspace_api.py. Keep setup and helper reuse explicit.
for _name in dir(api_tests.WorkspaceAPITests):
    if _name.startswith('test_') and _name not in ProtocolBindingTests.__dict__:
        setattr(ProtocolBindingTests, _name, None)
