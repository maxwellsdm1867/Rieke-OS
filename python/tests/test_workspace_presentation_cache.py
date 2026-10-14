"""Cold display is bounded, project-specific, inert, and disposable."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from disco.projects import presentation_cache as cache


class PresentationCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.state = self.root / 'state'
        self.uuid = str(uuid.uuid4())
        self.manifest = {'format': 'recording-project', 'version': 1, 'project_uuid': self.uuid}
        (self.project / 'project.json').write_text(json.dumps(self.manifest))
        self.payload = {'project': {**self.manifest, 'name': 'SRM', 'secret': 'credential'},
                        'counts': {'epochs': 300, 'duration_seconds': 9.25},
                        'cells': [{'cell_uuid': 'cell', 'cell_type': 'ON parasol', 'epochs': 300,
                                   'protocol_uuids': ['protocol'], 'scope_lease': 'secret'}],
                        'protocols': [{'protocol_uuid': 'protocol', 'name': 'Noise',
                                       'query_revision': 'authority', 'binding': {'version': 3, 'revision_uuid': 'authority'}}],
                        'sources': [], 'capability': 'secret', 'events': []}

    def save(self):
        return cache.save_overview(self.project, self.payload, user_state=self.state)

    def load(self):
        return cache.load_overview(self.project, user_state=self.state, expected_uuid=self.uuid)

    def test_recording_rigs_survive_the_inert_display_allowlist(self):
        self.payload['cells'][0].update(recording_rigs=['EF', 'HT'], recording_rig_missing=True)
        self.assertTrue(self.save())
        row = self.load()['overview']['cells'][0]
        self.assertEqual(row['recording_rigs'], ['EF', 'HT'])
        self.assertTrue(row['recording_rig_missing'])
        self.assertNotIn('scope_lease', row)

    def test_missing_read_is_side_effect_free(self):
        self.assertEqual(self.load(), {'available': False})
        self.assertFalse(self.state.exists())
        self.assertEqual(list(self.project.iterdir()), [self.project / 'project.json'])

    def test_second_process_restore_has_no_authority_or_unknown_fields(self):
        self.assertTrue(self.save())
        script = 'import json,sys; from disco.projects.presentation_cache import load_overview; print(json.dumps(load_overview(sys.argv[1],user_state=sys.argv[2])))'
        restored = json.loads(subprocess.check_output([sys.executable, '-c', script, str(self.project), str(self.state)]))
        self.assertTrue(restored['presentation_only'])
        self.assertEqual(restored['overview']['protocols'][0]['binding'], {'version': 3})
        self.assertEqual(restored['overview']['counts']['epochs'], 300)
        self.assertNotIn('secret', json.dumps(restored))
        self.assertNotIn('authority', json.dumps(restored))
        self.assertNotIn('scope_lease', json.dumps(restored))
        self.assertEqual(list(self.project.iterdir()), [self.project / 'project.json'])

    def test_copied_uuid_at_another_physical_path_is_a_miss(self):
        self.assertTrue(self.save())
        other = self.root / 'other'
        other.mkdir()
        (other / 'project.json').write_text(json.dumps(self.manifest))
        self.assertEqual(cache.load_overview(other, user_state=self.state), {'available': False})
        self.assertEqual(cache.load_overview(self.project, user_state=self.state, expected_uuid='different'), {'available': False})
        self.manifest['project_uuid'] = str(uuid.uuid4())
        (self.project / 'project.json').write_text(json.dumps(self.manifest))
        self.assertEqual(self.load(), {'available': False})

    def test_corrupt_locked_and_oversized_caches_fail_open(self):
        self.assertTrue(self.save())
        path = next((self.state / 'ui-presentation').iterdir())
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE overview SET checksum='bad'")
        self.assertEqual(self.load(), {'available': False})
        self.assertTrue(self.save())
        connection = sqlite3.connect(path)
        try:
            connection.execute('BEGIN EXCLUSIVE')
            self.assertEqual(self.load(), {'available': False})
            self.assertFalse(self.save())
        finally:
            connection.close()
        path.write_bytes(b'not a database')
        self.assertEqual(self.load(), {'available': False})
        self.assertFalse(self.save())
        with path.open('wb') as handle:
            handle.truncate(cache.MAX_FILE_BYTES + 1)
        self.assertEqual(self.load(), {'available': False})

    def test_oversized_and_unserializable_input_does_not_replace_good_snapshot(self):
        self.assertTrue(self.save())
        self.payload['cells'] *= 20001
        self.assertFalse(self.save())
        self.assertEqual(self.load()['overview']['counts']['epochs'], 300)
        self.payload['cells'] = []
        self.payload['counts'] = {'epochs': float('nan')}
        self.assertTrue(self.save())
        self.assertEqual(self.load()['overview']['counts'], {})

    def test_same_path_database_replacement_remains_only_historical_display(self):
        self.assertTrue(self.save())
        (self.project / 'database').mkdir()
        (self.project / 'database' / 'replacement').write_text('different scientific state')
        result = self.load()
        self.assertTrue(result['presentation_only'])
        self.assertNotIn('ready', result)
        self.assertNotIn('revision', result)
        self.assertEqual((self.project / 'database' / 'replacement').read_text(), 'different scientific state')

    def test_no_desktop_state_and_unwritable_state_are_optional(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(cache.save_overview(self.project, self.payload))
        self.state.write_text('not a directory')
        self.assertFalse(self.save())
        self.assertEqual(self.load(), {'available': False})

    def test_alias_uses_canonical_identity_but_manifest_link_is_rejected(self):
        self.assertTrue(self.save())
        alias = self.root / 'alias'
        alias.symlink_to(self.project, target_is_directory=True)
        self.assertEqual(cache.load_overview(alias, user_state=self.state)['project_path'], str(self.project.resolve()))
        manifest = self.project / 'project.json'
        moved = self.root / 'manifest.json'
        manifest.rename(moved)
        manifest.symlink_to(moved)
        self.assertEqual(self.load(), {'available': False})
