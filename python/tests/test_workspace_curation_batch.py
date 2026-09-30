"""Compact curation reads and atomic saves against disposable transaction doubles."""
import copy
import unittest
from unittest.mock import Mock, patch
import uuid

import test_workspace_api as api_fixture
from workspace_api import create_app


class CurationBatchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = api_fixture.WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = self.fixture.service
        self.client = self.fixture.client

    def body(self, ids=None, scope=None):
        return {'epoch_uuids': list(self.service.ids if ids is None else ids),
            'query_revision': self.fixture.revision(), 'expected_binding_version': 0,
            'selection_scope': {'filters': {}, 'cell_uuid': None} if scope is None else scope}

    def read(self, body):
        return self.client.post(self.fixture.base+'/curation/read', json=body, headers=self.fixture.headers)

    def save(self, body, receipt, **changes):
        return self.client.post(self.fixture.base+'/curation', json={**body, 'changes':changes,
            'expected_revisions': {row['epoch_uuid']:row['curation_revision'] for row in receipt['epochs']}},
            headers=self.fixture.headers)

    def test_thousand_selected_epochs_use_one_compact_read_and_one_atomic_save(self):
        first = self.service.ids[0]
        for _ in range(998):
            key = str(uuid.uuid4())
            self.service.ids.append(key)
            self.service.rows[key] = {**self.service.rows[first], 'epoch_uuid':key}
            self.service._fingerprints[key] = 'b'*64
        self.service.protocols[self.service.protocol_id]['result']['epochs'] = [
            {'uuid':key,'metadata_hash':'b'*64} for key in self.service.ids]
        body = self.body(list(reversed(self.service.ids)))
        before = copy.deepcopy((self.fixture.curation.rows, self.fixture.events.rows, self.service.rows))
        with patch.object(self.service, 'epoch', side_effect=AssertionError('No full epoch reads')), \
             patch.object(self.fixture.store, 'read', wraps=self.fixture.store.read) as read:
            response = self.read(body)
        self.assertEqual(response.status_code, 200, response.get_json())
        read.assert_called_once()  # One global pinned revision, not 1,000 recomputations.
        receipt = response.get_json()
        self.assertEqual(receipt['query_revision'],body['query_revision'])
        self.assertEqual([row['epoch_uuid'] for row in receipt['epochs']],body['epoch_uuids'])
        for row in receipt['epochs']:
            self.assertEqual(set(row), {'epoch_uuid','cell_uuid','curation_revision'})
            self.assertEqual(row['cell_uuid'],self.service.rows[row['epoch_uuid']]['cell_uuid'])
            self.assertEqual(row['curation_revision'],0)
        self.assertLess(len(response.data),180000)
        self.assertEqual((self.fixture.curation.rows, self.fixture.events.rows, self.service.rows),before)
        with patch.object(self.fixture.store, 'update', wraps=self.fixture.store.update) as update:
            saved = self.save(body,receipt,tags_add=['verified'],included=False)
        self.assertEqual(saved.status_code,200,saved.get_json())
        update.assert_called_once()
        self.assertEqual(set(saved.get_json()['curation']),set(body['epoch_uuids']))
        self.assertTrue(all(row['tags']==['verified'] and not row['included'] and row['revision']==1
            for row in self.fixture.curation.rows))

    def test_malformed_or_unbounded_read_fails_before_accessing_state(self):
        valid = self.body()
        invalid = [[],[self.service.ids[0]]*2,[None],[{}],list(range(1001))]
        for ids in invalid:
            with self.subTest(ids=str(ids)[:50]), patch.object(self.fixture.store,'read',side_effect=AssertionError('No state scan')):
                response=self.read({**valid,'epoch_uuids':ids})
                self.assertEqual(response.status_code,400,response.get_json())
        self.assertEqual(self.read({**valid,'changes':{'included':False}}).status_code,400)
        self.assertEqual(self.read({**valid,'expected_binding_version':True}).status_code,400)
        self.assertFalse(self.fixture.curation.rows)

    def test_read_and_write_reject_mixed_cell_and_filtered_out_selection(self):
        for scope in ({'filters':{},'cell_uuid':self.service.cell_ids[0]},
                      {'filters':{'cell_uuid':self.service.cell_ids[0]}},
                      {'filters':{'cell_type':'other-type'}}):
            body=self.body(scope=scope)
            with self.subTest(scope=scope):
                response=self.read(body)
                self.assertEqual(response.status_code,400,response.get_json())
                self.assertIn('outside',response.get_json()['error'])
                forged={'epochs':[{'epoch_uuid':key,'curation_revision':0} for key in self.service.ids]}
                write=self.save(body,forged,included=False)
                self.assertEqual(write.status_code,400,write.get_json())
                self.assertFalse(self.fixture.curation.rows)
        allowed=self.read(self.body([self.service.ids[0]],{'filters':{},'cell_uuid':self.service.cell_ids[0]}))
        self.assertEqual(allowed.status_code,200,allowed.get_json())
        outside=self.read(self.body([str(uuid.uuid4())]))
        self.assertEqual(outside.status_code,400)
        self.assertIn('outside this protocol',outside.get_json()['error'])

    def test_query_or_binding_changes_reject_read_and_stale_atomic_write(self):
        body=self.body()
        receipt=self.read(body).get_json()
        self.assertEqual(self.read({**body,'expected_binding_version':1}).status_code,409)
        self.service._fingerprints[self.service.ids[0]]='c'*64
        self.assertEqual(self.read(body).status_code,409)
        self.assertEqual(self.save(body,receipt,tags_add=['never']).status_code,409)
        self.assertFalse(self.fixture.curation.rows)

    def test_selected_epoch_optimistic_conflict_has_no_partial_write(self):
        body=self.body()
        receipt=self.read(body).get_json()
        first=self.service.ids[0]
        one={**body,'epoch_uuids':[first]}
        one_receipt={**receipt,'epochs':[row for row in receipt['epochs'] if row['epoch_uuid']==first]}
        self.assertEqual(self.save(one,one_receipt,tags_add=['concurrent']).status_code,200)
        before=copy.deepcopy(self.fixture.curation.rows)
        # Even refreshing the global token cannot bypass each epoch's revision.
        body['query_revision']=self.fixture.revision()
        conflict=self.save(body,receipt,tags_add=['never'],included=False)
        self.assertEqual(conflict.status_code,409,conflict.get_json())
        self.assertEqual(self.fixture.curation.rows,before)

    def test_batch_read_skips_snapshot_but_successful_mutation_keeps_recovery(self):
        self.service.dj.Schema=object()
        checkpoint=Mock()
        with patch('workspace_annotations.SharedAnnotations',return_value=None), \
             patch('workspace_state_snapshot.save',checkpoint):
            app=create_app(self.fixture.temp.name,self.fixture.temp.name,service=self.service,
                store=self.fixture.store,explorer_history=self.fixture.explorer_history,
                data_stores=self.fixture.data_stores,protocol_suggestions=self.fixture.protocol_suggestions)
        self.addCleanup(app.extensions['app_state_session_lock'].close)
        self.client=app.test_client()
        checkpoint.reset_mock()
        body=self.body();receipt=self.read(body)
        self.assertEqual(receipt.status_code,200,receipt.get_json())
        checkpoint.assert_not_called()
        saved=self.save(body,receipt.get_json(),included=False)
        self.assertEqual(saved.status_code,200,saved.get_json())
        checkpoint.assert_called_once()


if __name__=='__main__':
    unittest.main()
