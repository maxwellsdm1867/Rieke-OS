"""Snapshot restore retains exact JSON and caller-owned rollback boundaries."""
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import workspace_state_snapshot as snapshots

VALUE = 5.5511151231257815e-17


class Connection:
    def __init__(self, row, *, corrupt=False):
        self.row = copy.deepcopy(row)
        self.corrupt = corrupt
        self.calls = []
        self.rollbacks = 0

    @property
    @contextmanager
    def transaction(self):
        original = copy.deepcopy(self.row)
        try:
            yield
        except BaseException:
            self.row = original
            self.rollbacks += 1
            raise

    def query(self, sql, args=(), **kwargs):
        self.calls.append((sql, args))
        result = []
        if 'information_schema.tables' in sql:
            result = [('search_preset',)]
        elif sql.startswith('SHOW COLUMNS'):
            result = [('project_uuid', 'varchar(36)', 'NO', 'PRI', None, ''),
                      ('preset_uuid', 'varchar(36)', 'NO', 'PRI', None, ''),
                      ('predicate', 'json', 'NO', '', None, ''),
                      ('version', 'int', 'NO', '', None, '')]
        elif sql.startswith('DELETE'):
            self.row = None
        elif sql.startswith('INSERT'):
            self.row = {'project_uuid': args[0], 'preset_uuid': args[1],
                        'predicate': json.loads(args[2]), 'version': args[-1]}
            if self.corrupt:
                self.row['predicate']['value'] = 5.551115123125782e-17
        elif sql.startswith('SELECT `predicate`'):
            result = [(json.dumps(self.row['predicate']),)] if self.row else []
        else:
            raise AssertionError(sql)
        return SimpleNamespace(fetchall=lambda: result)


class SnapshotJSONTests(unittest.TestCase):
    def fixture(self, root):
        original = {'project_uuid': 'project', 'preset_uuid': 'preset',
                    'predicate': {'field': 'parameters/x', 'op': 'eq', 'value': 0.5}, 'version': 1}
        wanted = {**original, 'predicate': {'field': 'parameters/x', 'op': 'eq',
                    'value': VALUE, 'integer': 2**63 + 1, 'flag': True, 'null': None}, 'version': 2}
        project = {'project_uuid': 'project', 'name': 'Before'}
        (root / 'project.json').write_text(json.dumps(project))
        (root / 'protocols').mkdir()
        (root / 'backups/app-state').mkdir(parents=True)
        state = {'format': snapshots.FORMAT, 'version': 1, 'project': project,
                 'source_sha256s': [], 'source_references': [], 'protocols': {},
                 'tables': {name: [] for name in snapshots.TABLES}}
        state['tables']['search_preset'] = [original]
        target = copy.deepcopy(state)
        target['tables']['search_preset'] = [wanted]
        target['project']['name'] = 'After'
        return original, wanted, state, target

    def test_restore_builds_typed_insert_and_verifies_before_committing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original, wanted, state, target = self.fixture(root)
            connection = Connection(original)
            with patch.object(snapshots, 'load', return_value=target), \
                    patch.object(snapshots, 'capture', return_value=state), \
                    patch.object(snapshots, 'save', return_value={'saved': True}):
                self.assertEqual(snapshots.restore(root, connection, root / 'snapshot.json'), {'saved': True})
            self.assertEqual(connection.row, wanted)
            insert = next(sql for sql, args in connection.calls if sql.startswith('INSERT'))
            self.assertIn('JSON_SET(CAST(%s AS JSON),%s,CAST(%s AS DOUBLE))', insert)
            self.assertEqual(json.loads((root / 'project.json').read_text())['name'], 'After')
            self.assertEqual(connection.rollbacks, 0)
            self.assertFalse((root / '.app-state-restore.pending').exists())

    def test_readback_failure_rolls_back_sql_and_preserves_project_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original, wanted, state, target = self.fixture(root)
            before = (root / 'project.json').read_bytes()
            connection = Connection(original, corrupt=True)
            with patch.object(snapshots, 'load', return_value=target), \
                    patch.object(snapshots, 'capture', return_value=state), \
                    patch.object(snapshots, 'save', return_value={'saved': True}), \
                    self.assertRaisesRegex(ValueError, 'authoritative value'):
                snapshots.restore(root, connection, root / 'snapshot.json')
            self.assertEqual(connection.row, original)
            self.assertEqual(connection.rollbacks, 1)
            self.assertEqual((root / 'project.json').read_bytes(), before)
            self.assertFalse((root / '.app-state-restore.pending').exists())
            self.assertEqual(len(list((root / 'backups/app-state').glob('before-restore-*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
