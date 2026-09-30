"""Opt-in SIGKILL recovery using only a newly created private project database.

Tests native storage/ownership recovery with a synthetic acquisition hierarchy.
It does not claim to exercise full H5 import, API writes or machine power loss.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from workspace_projects import create_project
import workspace_native_mysql as native


@unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_MYSQL') == '1',
                     'opt-in disposable native MySQL SIGKILL recovery')
class NativeCrashTests(unittest.TestCase):
    def test_committed_hierarchy_survives_and_partial_transactions_roll_back(self):
        import pymysql
        with tempfile.TemporaryDirectory(prefix='rieke-private-crash-test-') as directory:
            root = Path(create_project(Path(directory) / 'projects', 'Disposable crash fixture')['path'])
            connection = None
            try:
                runtime = native.ensure_native_database(root)
                connection = pymysql.connect(**native.connection_parameters(root))
                with connection.cursor() as cursor:
                    cursor.execute('CREATE DATABASE crash_fixture')
                    cursor.execute('CREATE TABLE crash_fixture.acquisition (identity CHAR(36) PRIMARY KEY, parent CHAR(36) NULL, metadata JSON NOT NULL, sample_sha CHAR(64) NOT NULL, FOREIGN KEY(parent) REFERENCES crash_fixture.acquisition(identity)) ENGINE=InnoDB')
                    cells = [str(uuid.uuid4()), str(uuid.uuid4())]
                    records = [(cell, None, json.dumps({'label': 'Cell3', 'date': '2026-06-11', 'rig': rig}), '0' * 64)
                               for cell, rig in zip(cells, ('RigA', 'RigB'))]
                    cursor.executemany('INSERT INTO crash_fixture.acquisition VALUES (%s,%s,%s,%s)', records)
                    records = [(str(uuid.uuid5(uuid.NAMESPACE_URL, 'disposable-crash-epoch/' + str(i))), cells[i % 2],
                                json.dumps({'ordinal': i, 'included': True}), hashlib.sha256(str(i).encode()).hexdigest())
                               for i in range(1000)]
                    cursor.executemany('INSERT INTO crash_fixture.acquisition VALUES (%s,%s,%s,%s)', records)
                connection.commit()

                def inventory():
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT identity,parent,metadata,sample_sha FROM crash_fixture.acquisition ORDER BY identity')
                        return [(identity, parent, json.loads(metadata), sample_sha)
                                for identity, parent, metadata, sample_sha in cursor.fetchall()]

                expected = inventory()
                connection.commit()
                for stage in ('uncommitted_insert', 'uncommitted_metadata_change', 'acknowledged_commit'):
                    with self.subTest(stage=stage):
                        connection.begin()
                        with connection.cursor() as cursor:
                            if stage == 'uncommitted_insert':
                                cursor.execute('INSERT INTO crash_fixture.acquisition VALUES (%s,%s,%s,%s)',
                                               (str(uuid.uuid4()), cells[0], '{"partial":true}', '1' * 64))
                            else:
                                cursor.execute('UPDATE crash_fixture.acquisition SET metadata=%s WHERE identity=%s',
                                               (json.dumps({'label': 'Cell3', 'date': '2026-06-11', 'rig': 'ReviewedRig'}), cells[0]))
                        if stage == 'acknowledged_commit':
                            connection.commit()
                            expected = inventory()
                            connection.commit()
                        # Resolve and verify the exact process started for this
                        # temporary project; never signal a discovered server.
                        self.assertEqual(Path(runtime['project_path']), root.resolve())
                        owned = native._owned_process(runtime)
                        self.assertIsNotNone(owned)
                        self.assertIn(runtime['pid'], native._PROCESSES)
                        owned.kill()
                        native._PROCESSES[runtime['pid']].wait(timeout=15)
                        connection.close(); connection = None
                        self.assertFalse(native._read(root / 'database/native-owner.json')['clean_shutdown'])
                        previous_pid = runtime['pid']
                        runtime = native.ensure_native_database(root)
                        self.assertNotEqual(runtime['pid'], previous_pid)
                        connection = pymysql.connect(**native.connection_parameters(root))
                        # Python equality conflates True/1 and 1/1.0. Compare
                        # canonical JSON to retain scientific value types too.
                        self.assertEqual(json.dumps(inventory(), sort_keys=True, allow_nan=False),
                                         json.dumps(expected, sort_keys=True, allow_nan=False))
                        connection.commit()
                        self.assertEqual(len(expected), 1002)
            finally:
                if connection is not None:
                    connection.close()
                native.stop_native_database(root)


if __name__ == '__main__':
    unittest.main()
