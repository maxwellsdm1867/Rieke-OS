import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from flask import Flask
from workspace_app_routes import register_app_routes
from disco.decisions.author_preferences import appearance_preferences, remember_appearance

class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        environment = patch.dict(os.environ, RIEKE_PREFERENCES_DIR=self.root.name)
        environment.start()
        self.addCleanup(environment.stop)

    def test_default_and_reversible_preference_touch_only_machine_appearance(self):
        self.assertEqual(appearance_preferences(), {'icon': 'disco', 'theme': 'light'})
        remember_appearance('rieke')
        self.assertEqual(appearance_preferences(), {'icon': 'rieke', 'theme': 'fred'})
        remember_appearance('disco')
        self.assertEqual(appearance_preferences(), {'icon': 'disco', 'theme': 'light'})
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
        self.assertEqual(client.get('/api/app/appearance').get_json(), {'icon':'disco','theme':'light'})
        self.assertEqual(client.post('/api/app/appearance', json={'icon':'rieke'}).status_code,403)
        headers={'X-Workspace-Request':'1'}
        self.assertEqual(client.post('/api/app/appearance', json={'icon':'rieke'},headers=headers).get_json(),{'icon':'rieke','theme':'fred'})
        self.assertEqual(client.post('/api/app/appearance', json={'icon':'../bad'},headers=headers).status_code,400)

    def test_legacy_icon_preference_migrates_without_rewriting_on_read(self):
        path = Path(self.root.name) / 'appearance.json'
        legacy = {'format': 'disco-appearance', 'version': 1, 'icon': 'rieke'}
        path.write_text(json.dumps(legacy))
        before = path.read_bytes()
        self.assertEqual(appearance_preferences(), {'icon': 'rieke', 'theme': 'fred'})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(remember_appearance(theme='dark'), {'icon': 'disco', 'theme': 'dark'})
        self.assertEqual(appearance_preferences(), {'icon': 'disco', 'theme': 'dark'})
        self.assertEqual(remember_appearance('disco'), {'icon': 'disco', 'theme': 'dark'})
        self.assertEqual(remember_appearance(theme='fred'), {'icon': 'rieke', 'theme': 'fred'})

    def test_theme_route_persists_and_rejects_invalid_or_conflicting_updates(self):
        app = Flask(__name__)
        register_app_routes(app)
        app.register_error_handler(ValueError, lambda error: ({'error': str(error)}, 400))
        client = app.test_client()
        headers = {'X-Workspace-Request': '1'}
        response = client.post('/api/app/appearance', json={'theme': 'dark'}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get('/api/app/appearance').get_json(), {'icon': 'disco', 'theme': 'dark'})
        path = Path(self.root.name) / 'appearance.json'
        before = path.read_bytes()
        for payload in ({}, {'theme': 'neon'}, {'theme': []}, {'theme': None},
                        {'theme': 'system', 'path': '/tmp'}, {'theme': 'dark', 'icon': 'rieke'}):
            with self.subTest(payload=payload):
                self.assertEqual(client.post('/api/app/appearance', json=payload, headers=headers).status_code, 400)
                self.assertEqual(path.read_bytes(), before)
        self.assertEqual(client.post('/api/app/appearance', json={'theme': 'fred'},
                                     headers={**headers, 'Origin': 'https://example.com'}).status_code, 403)
        self.assertEqual(path.read_bytes(), before)

    def test_system_light_and_legacy_bright_preferences(self):
        path = Path(self.root.name) / 'appearance.json'
        path.write_text(json.dumps({'format': 'disco-appearance', 'version': 1, 'icon': 'disco', 'theme': 'bright'}))
        self.assertEqual(appearance_preferences(), {'icon': 'disco', 'theme': 'light'})
        for theme in ('system', 'light', 'dark', 'fred'):
            expected = {'icon': 'rieke' if theme == 'fred' else 'disco', 'theme': theme}
            self.assertEqual(remember_appearance(theme=theme), expected)
            self.assertEqual(appearance_preferences(), expected)
        remember_appearance(theme='system')
        self.assertEqual(remember_appearance('disco'), {'icon': 'disco', 'theme': 'system'})
