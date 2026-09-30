"""Disposable receiver tests exercising real annotation transactions and HTTP."""
import copy
import hashlib
import json
import sqlite3
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

import test_workspace_annotations as annotations_tests
from workspace_external_tags import ExternalTags, submit_tags
from workspace_tag_predicates import TagPredicates


class ExternalTagTests(unittest.TestCase):
    def setUp(self):
        self.case = annotations_tests.SharedAnnotationTests()
        self.case.setUp(); self.addCleanup(self.case.doCleanups)
        self.service = self.case.service
        self.client, self.headers = self.case.client, self.case.headers
        for key, row in self.service.rows.items():
            self.service._fingerprints[key] = hashlib.sha256(json.dumps({
                'epoch': self.service.details[key], 'source_sha256': row['source_sha256']},
                sort_keys=True, allow_nan=False).encode()).hexdigest()
        base = '/api/protocols/' + self.service.protocol_id
        revision = self.client.get(base).json['query_revision']
        result = self.client.post(base + '/exports', headers=self.headers,
                                  json={'query_revision': revision, 'format': 'wheeler-sqlite'})
        self.assertEqual(result.status_code, 201, result.json)
        self.export = result.json
        self.folder = Path(result.json['artifact_path']).parent
        self.profile = str(uuid.uuid4())
        self.artifact = Path(result.json['artifact_path']).read_bytes()
        with sqlite3.connect(result.json['artifact_path']) as db:
            instructions=db.execute("SELECT content FROM documentation WHERE name='external_tag_return'").fetchone()[0]
            self.assertIn('annotations/incoming',instructions)
        self.receiver = self.case.app.extensions['external_tags']

    def submit(self, kind='epoch', target=None, tag='publication:paper-1'):
        return Path(submit_tags(self.folder, [dict(target_kind=kind,
            target_uuid=target or self.case.first, tags=[tag])], author_name='Wheeler', profile_uuid=self.profile))

    def scan(self):
        response = self.client.post('/api/annotations/scan', headers=self.headers, json={})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def test_export_to_actor_to_live_query_and_restart_without_mutating_artifact(self):
        path = self.submit()
        state = self.scan()
        self.assertFalse(state['exports'][0]['errors'])
        self.assertEqual(state['receipts'][0]['addition_count'], 1)
        chips = self.client.get('/api/epochs/' + self.case.first + '/annotations').json['epoch_tags']
        self.assertEqual(chips[0]['author_name'], 'Wheeler')
        matches = TagPredicates(self.service).match(dict(field='annotations/effective/tags',
            operator='contains', value='publication:paper-1'), self.service.ids)[1]
        self.assertEqual(matches, [self.case.first])
        receipt = self.folder / 'annotations/receipts' / path.name
        receipt.unlink()  # Simulate a crash after SQL commit, before writing file receipt.
        restarted = ExternalTags(self.service, self.case.case.store, self.case.store)
        self.assertEqual(len(restarted.scan()['receipts']), 1)
        self.assertTrue(receipt.exists())
        self.assertEqual(Path(self.export['artifact_path']).read_bytes(), self.artifact)
        with self.client.get(self.export['download_url']) as download:
            self.assertEqual(download.status_code, 200)
        self.case.store.update('epoch', [self.case.first], self.profile,
            {'tags_remove':['publication:paper-1']}, {self.case.first:1}, 'Wheeler')
        restarted.scan()
        self.assertEqual(self.case.epoch(self.case.first)['epoch_tags'], [])

    def test_cell_inheritance_and_receipt_for_unchanged_message(self):
        self.submit('cell', self.case.cell)
        first = self.scan()
        self.assertEqual(len(self.case.epoch(self.case.first)['cell_tags']), 1)
        self.assertEqual(self.case.epoch(self.case.second)['effective_tags'], [])
        self.submit('cell', self.case.cell)
        second = self.scan()
        self.assertEqual(second['revision'], first['revision'])
        self.assertEqual(sorted(r['addition_count'] for r in second['receipts']), [0,1])

    def test_receipt_failure_rolls_back_additions_and_retry_succeeds(self):
        path = self.submit()
        original = self.case.store._event
        def fail(action, actor, payload):
            if action == 'external_annotation_received': raise RuntimeError('receipt write failed')
            return original(action, actor, payload)
        with patch.object(self.case.store, '_event', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'receipt write failed'): self.receiver.scan()
        self.assertEqual(self.case.epoch(self.case.first)['epoch_tags'], [])
        self.assertEqual(self.receiver.receipts(), {})
        self.assertFalse((self.folder / 'annotations/receipts' / path.name).exists())
        self.assertEqual(self.scan()['receipts'][0]['addition_count'], 1)

    def test_bad_messages_isolated_and_consumed_message_cannot_change(self):
        good = self.submit()
        bad = self.submit(target=self.case.second)
        message = json.loads(bad.read_text())
        message['document']['entries'][0]['source_sha256'] = 'f'*64
        bad.write_text(json.dumps(message))
        state = self.scan()
        self.assertEqual(len(state['receipts']), 1)
        self.assertEqual(len(state['exports'][0]['errors']), 1)
        self.assertEqual(self.case.epoch(self.case.second)['epoch_tags'], [])
        message = json.loads(good.read_text());message['document']['entries'][0]['tags'][0]['tag']='rewritten'
        good.write_text(json.dumps(message))
        errors = self.scan()['exports'][0]['errors']
        self.assertTrue(any('reused' in e['error'] for e in errors))

    def test_project_target_kind_and_export_membership_rejected(self):
        path = self.submit(); original=json.loads(path.read_text())
        variants=[]
        other=copy.deepcopy(original);other['document']['project_uuid']=str(uuid.uuid4());variants.append(other)
        wrong=copy.deepcopy(original);wrong['document']['entries'][0]['target_kind']='cell';variants.append(wrong)
        foreign=copy.deepcopy(original);foreign['document']['entries'][0]['target_uuid']=str(uuid.uuid4());variants.append(foreign)
        record=self.case.case.store.get_dataset_revision(self.export['dataset_uuid'])
        for value in variants:
            with self.assertRaises(ValueError):self.receiver.receive(value,record,{})
        self.assertEqual(self.case.epoch(self.case.first)['effective_tags'], [])
        self.assertEqual(self.client.post('/api/annotations/scan', json={}).status_code,403)

    def test_missing_folder_and_partial_files_are_visible_or_ignored(self):
        incoming=self.folder/'annotations/incoming'
        (incoming/'.pending-upload').write_text('{')
        self.assertFalse(self.scan()['exports'][0]['errors'])
        moved=self.folder.with_name(self.folder.name+'-moved');self.folder.rename(moved)
        self.assertEqual(self.scan()['exports'][0]['status'],'unavailable')

    def test_existing_sqlite_export_gets_return_folder_without_changing_database(self):
        (self.folder/'annotations/incoming').rmdir()
        (self.folder/'annotations').rmdir()
        (self.folder/'annotation-return.json').unlink()
        self.assertEqual(self.scan()['exports'][0]['status'],'watching')
        self.assertTrue((self.folder/'annotation-return.json').exists())
        self.assertEqual(Path(self.export['artifact_path']).read_bytes(),self.artifact)

    def test_redirected_annotation_parent_is_rejected_before_creating_files(self):
        parent=self.folder/'annotations';(parent/'incoming').rmdir();parent.rmdir()
        outside=self.folder/'elsewhere';outside.mkdir();parent.symlink_to(outside,target_is_directory=True)
        state=self.scan()
        self.assertEqual(state['exports'][0]['status'],'unavailable')
        self.assertEqual(list(outside.iterdir()),[])


if __name__ == '__main__': unittest.main()
