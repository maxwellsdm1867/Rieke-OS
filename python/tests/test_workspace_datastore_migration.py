"""Crash recovery for the registration-only eligibility migration; no SQL server."""
import contextlib
import copy
import types
import unittest
from unittest.mock import patch

from workspace_datastores import migrate_query_eligibility
if __package__:
    from .test_workspace_curation import Table
else:
    from test_workspace_curation import Table


class MigrationConnection:
    def __init__(self, rows, events, column=None):
        self.rows, self.events, self.column = rows, events, column
        self.queries, self.result = [], []

    def query(self, sql, args=(), **kwargs):
        self.queries.append((sql, args))
        self.result = []
        if 'GET_LOCK' in sql:
            self.result = [(1,)]
        elif sql.startswith('SHOW COLUMNS'):
            self.result = [] if self.column is None else [{'Null': self.column}]
        elif 'ADD COLUMN' in sql:
            self.column = 'YES'
            for row in self.rows:
                row['query_excluded'] = None
        elif sql.startswith('SELECT project_uuid'):
            self.result = copy.deepcopy([row for row in self.rows if row.get('query_excluded') is None])
        elif sql.startswith('UPDATE'):
            excluded, version, project, source = args
            for row in self.rows:
                if row['project_uuid'] == project and row['source_sha256'] == source and row.get('query_excluded') is None:
                    row.update(query_excluded=excluded, version=version)
        elif 'MODIFY COLUMN' in sql:
            if any(row.get('query_excluded') is None for row in self.rows):
                raise ValueError('Unfinished migration')
            self.column = 'NO'
        elif 'RELEASE_LOCK' not in sql:
            raise AssertionError(sql)
        return self

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0]

    @property
    @contextlib.contextmanager
    def transaction(self):
        before = copy.deepcopy((self.rows, self.events.rows))
        try:
            yield
        except Exception:
            self.rows[:], self.events.rows[:] = before
            raise


class EligibilityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.events = Table(('event_uuid',))
        self.rows = [{'project_uuid': 'project-a', 'source_sha256': 'a' * 64, 'archived': 1, 'version': 4},
                     {'project_uuid': 'project-b', 'source_sha256': 'b' * 64, 'archived': 0, 'version': 2}]
        self.connection = MigrationConnection(self.rows, self.events)
        self.dj = types.SimpleNamespace(conn=lambda: self.connection)

    def test_backfill_preserves_legacy_exclusion_and_is_idempotent(self):
        migrate_query_eligibility(self.dj, self.events)
        self.assertEqual([row['query_excluded'] for row in self.rows], [1, 0])
        self.assertEqual([row['version'] for row in self.rows], [5, 3])
        self.assertEqual(self.connection.column, 'NO')
        self.assertEqual(len(self.events.rows), 2)
        self.assertEqual({row['project_uuid'] for row in self.events.rows}, {'project-a', 'project-b'})
        self.assertFalse(self.events.rows[0]['payload']['new_query_eligibility_changed'])
        before = copy.deepcopy((self.rows, self.events.rows))
        migrate_query_eligibility(self.dj, self.events)
        self.assertEqual((self.rows, self.events.rows), before)
        self.assertEqual(sum('ADD COLUMN' in sql for sql, _ in self.connection.queries), 1)

    def test_failed_audit_rolls_back_backfill_then_resumes_nullable_schema(self):
        with patch.object(self.events, 'insert1', side_effect=RuntimeError('audit failure')):
            with self.assertRaisesRegex(RuntimeError, 'audit failure'):
                migrate_query_eligibility(self.dj, self.events)
        self.assertEqual(self.connection.column, 'YES')
        self.assertTrue(all(row['query_excluded'] is None for row in self.rows))
        self.assertEqual([row['version'] for row in self.rows], [4, 2])
        self.assertFalse(self.events.rows)
        self.assertIn('RELEASE_LOCK', self.connection.queries[-1][0])
        migrate_query_eligibility(self.dj, self.events)
        self.assertEqual([row['query_excluded'] for row in self.rows], [1, 0])
        self.assertEqual(self.connection.column, 'NO')

    def test_partial_upgrade_never_overwrites_explicit_reincluded_state(self):
        self.connection.column = 'YES'
        self.rows[0]['query_excluded'] = False  # Deliberately included despite archived visibility.
        self.rows[1]['query_excluded'] = None
        migrate_query_eligibility(self.dj, self.events)
        self.assertFalse(self.rows[0]['query_excluded'])
        self.assertEqual(self.rows[0]['version'], 4)
        self.assertEqual(len(self.events.rows), 1)
        self.assertEqual(self.events.rows[0]['project_uuid'], 'project-b')
