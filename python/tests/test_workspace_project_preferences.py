import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import uuid

from flask import Flask
from workspace_project_preferences import ProjectPreferences, PreferenceConflict, REFERENCE, register_project_preference_routes


class PortablePreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'donor'
        self.root.mkdir()
        self.identity = str(uuid.uuid4())
        self.store = ProjectPreferences(self.root, self.identity)
        self.protocol = str(uuid.uuid4())
        self.pins = {self.protocol: {'section': 'pinned', 'rank': 0}}
        self.search = {'id': 'query', 'name': 'History noise', 'predicate':
                       {'field': 'protocol', 'operator': 'contains', 'value': 'History'},
                       'splits': 'date,cell', 'pinned': True, 'matched_count': 8, 'cell_count': 2,
                       'lastRunAt': '2026-09-29T20:00:00Z'}

    def test_copy_preserves_search_and_sidebar_without_browser_or_sql(self):
        self.store.save('recent_searches', [self.search], 0)
        saved = self.store.save('protocol_shortcuts', self.pins, 0)
        recipient = self.root.parent / 'recipient'
        shutil.copytree(self.root, recipient)
        shutil.rmtree(self.root)
        reopened = ProjectPreferences(recipient, self.identity)
        self.assertEqual(reopened.read(), saved)
        self.assertEqual(saved['state']['recent_searches'], [self.search])
        self.assertEqual(saved['state']['protocol_shortcuts'], self.pins)
        self.assertFalse(list((recipient / 'protocols').glob('*.json')))

    def test_disjoint_updates_do_not_conflict_and_stale_same_field_refused(self):
        saved = self.store.save('recent_searches', [self.search], 0)
        self.assertEqual(saved['revisions']['recent_searches'], 1)
        other = self.store.save('protocol_shortcuts', self.pins, 0)
        self.assertEqual(other['state']['recent_searches'], [self.search])
        before = (self.root / REFERENCE).read_bytes()
        with self.assertRaises(PreferenceConflict):
            self.store.save('recent_searches', [], 0)
        self.assertEqual((self.root / REFERENCE).read_bytes(), before)
        self.assertEqual(self.store.save('recent_searches', [self.search], 1)['revisions']['recent_searches'], 1)

    def test_bad_shapes_and_future_or_foreign_files_cannot_replace_state(self):
        self.store.save('recent_searches', [self.search], 0)
        path = self.root / REFERENCE
        before = path.read_bytes()
        for field, value in [('protocol_shortcuts', {self.protocol: {'section': 'unknown', 'rank': 0}}),
                             ('protocol_shortcuts', {'not-a-uuid': {'section': 'main', 'rank': 0}}),
                             ('protocol_shortcuts', {self.protocol: {'section': 'main', 'rank': True}}),
                             ('recent_searches', [dict(self.search, cell_count=True)]),
                             ('recent_searches', [dict(self.search, predicate={'field': 'protocol', 'operator': 'execute', 'value': 'x'})]),
                             ('recent_searches', [self.search, self.search]),
                             ('pane_width', 900)]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    self.store.save(field, value, 0)
                self.assertEqual(path.read_bytes(), before)
        for changes in ({'version': 2}, {'version': True}, {'project_uuid': str(uuid.uuid4())}):
            value = json.loads(before)
            value.update(changes)
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                self.store.save('protocol_shortcuts', self.pins, 0)
            self.assertEqual(json.loads(path.read_text()), value)

    def test_preference_symlinks_are_never_followed(self):
        target = self.root.parent / 'outside'
        target.mkdir()
        (self.root / 'protocols').symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symbolic'):
            self.store.save('recent_searches', [self.search], 0)
        self.assertEqual(list(target.iterdir()), [])

    def test_routes_expose_only_project_fields_with_conflict_status(self):
        app = Flask(__name__)
        register_project_preference_routes(app, self.root, self.identity, threading.RLock())
        client = app.test_client()
        self.assertEqual(client.get('/api/project-preferences').json['state'], {})
        body = dict(field='recent_searches', value=[self.search], expected_revision=0)
        self.assertEqual(client.put('/api/project-preferences', json=body).status_code, 200)
        self.assertEqual(client.put('/api/project-preferences', json=body).status_code, 409)
        self.assertEqual(client.put('/api/project-preferences', json={**body, 'field': 'port'}).status_code, 400)
        self.assertEqual(client.get('/api/project-preferences?directory=/other').status_code, 400)


if __name__ == '__main__':
    unittest.main()
