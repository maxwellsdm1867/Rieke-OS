import json
from pathlib import Path
import tempfile
import unittest

from workspace_storage import ManagedStorage, initialize_layout, migrate_legacy_logs


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'managed'
        self.code = self.base / 'code'
        self.code.mkdir()
        self.storage = ManagedStorage(self.root, 'fixture-project', self.code)

    def test_inventory_is_paged_and_contains_real_files_only(self):
        for n in range(3):
            (self.root / 'protocols' / f'{n}.json').write_text('{}')
        page = self.storage.files('protocols', 1, 1)
        self.assertEqual(page['total'], 3)
        self.assertEqual(page['entries'][0]['name'], '1.json')
        self.assertEqual(page['entries'][0]['size_bytes'], 2)
        self.assertTrue(page['has_more'])
        self.assertEqual(page['parent'], '')

    def test_known_old_layout_adds_disposable_cache_without_remapping_sources(self):
        manifest = self.root / 'storage.json'
        old = json.loads(manifest.read_text())
        old['directories'].pop('cache')
        manifest.write_text(json.dumps(old))
        marker = self.root / 'imports' / 'unchanged.json'
        marker.write_text('{"raw":"kept"}')
        result = initialize_layout(self.root, 'fixture-project', self.code)
        self.assertEqual(result['directories']['cache'], 'cache')
        self.assertEqual(marker.read_text(), '{"raw":"kept"}')
        self.assertTrue((self.root / 'logs/storage/derived-cache-layout.json').exists())
        self.assertEqual(initialize_layout(self.root, 'fixture-project', self.code), result)

    def test_tree_cannot_escape_or_expose_mysql_internals(self):
        (self.root / 'database/mysql').mkdir()
        (self.root / 'database/mysql' / 'private-key.pem').write_text('not served')
        (self.root / 'outside').symlink_to(self.code, target_is_directory=True)
        for path in ('../code', str(self.code), 'outside', 'database/mysql', 'database/mysql/child'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.storage.files(path)
        mysql = next(e for e in self.storage.files('database')['entries'] if e['name'] == 'mysql')
        self.assertEqual(mysql['type'], 'restricted')
        self.assertFalse(mysql['browseable'])

    def test_scripts_cannot_share_managed_root(self):
        with self.assertRaises(ValueError):
            initialize_layout(self.code / 'data', 'fixture', self.code)
        with self.assertRaises(ValueError):
            initialize_layout(self.base, 'fixture', self.code)

    def test_legacy_logs_relocate_but_historical_paths_remain_readable(self):
        old = self.root / 'jobs'
        old.mkdir()
        (old / 'job.json').write_text('{"status":"imported"}')
        changes = migrate_legacy_logs(self.root)
        self.assertEqual(changes[0]['to'], 'logs/imports')
        self.assertTrue(old.is_symlink())
        self.assertEqual((self.root / 'logs/imports/job.json').read_text(), (old / 'job.json').read_text())
        self.assertEqual(migrate_legacy_logs(self.root), [])

    def test_unknown_layout_and_external_directory_symlinks_fail_closed(self):
        layout = self.root / 'storage.json'
        value = json.loads(layout.read_text())
        value['version'] = 9
        layout.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            ManagedStorage(self.root, 'fixture-project', self.code)
        fresh = self.base / 'fresh'
        fresh.mkdir()
        (fresh / 'logs').symlink_to(self.code, target_is_directory=True)
        with self.assertRaises(ValueError):
            ManagedStorage(fresh, 'fixture-project', self.code)
        self.assertFalse((self.code / 'imports').exists())
