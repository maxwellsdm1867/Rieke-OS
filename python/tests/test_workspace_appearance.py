import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from flask import Flask
from workspace_app_routes import register_app_routes
from workspace_author_preferences import appearance_preferences, remember_appearance

class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        environment = patch.dict(os.environ, RIEKE_PREFERENCES_DIR=self.root.name)
        environment.start()
        self.addCleanup(environment.stop)

    def test_default_and_reversible_preference_touch_only_machine_appearance(self):
        self.assertEqual(appearance_preferences(), {'icon': 'disco'})
        remember_appearance('rieke')
        self.assertEqual(appearance_preferences(), {'icon': 'rieke'})
        remember_appearance('disco')
        self.assertEqual(appearance_preferences(), {'icon': 'disco'})
        self.assertEqual({p.name for p in Path(self.root.name).iterdir()}, {'appearance.json', 'appearance.lock'})

    def test_unknown_values_and_symlinks_do_not_overwrite_saved_preference(self):
        remember_appearance('rieke')
        before = (Path(self.root.name)/'appearance.json').read_bytes()
        with self.assertRaises(ValueError): remember_appearance('unknown')
        self.assertEqual((Path(self.root.name)/'appearance.json').read_bytes(), before)
        (Path(self.root.name)/'appearance.json').unlink()
        (Path(self.root.name)/'appearance.json').symlink_to('/tmp/unrelated-appearance.json')
        with self.assertRaises(ValueError): remember_appearance('disco')

    def test_route_requires_same_origin_and_exact_enum_payload(self):
        app = Flask(__name__)
        register_app_routes(app)
        app.register_error_handler(ValueError, lambda error: ({'error': str(error)}, 400))
        client = app.test_client()
        self.assertEqual(client.get('/api/app/appearance').get_json(), {'icon':'disco'})
        self.assertEqual(client.post('/api/app/appearance', json={'icon':'rieke'}).status_code,403)
        headers={'X-Workspace-Request':'1'}
        self.assertEqual(client.post('/api/app/appearance', json={'icon':'rieke'},headers=headers).get_json(),{'icon':'rieke'})
        self.assertEqual(client.post('/api/app/appearance', json={'icon':'../bad'},headers=headers).status_code,400)
