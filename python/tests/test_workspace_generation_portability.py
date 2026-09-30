"""Derived generation triggers must not break or weaken portable SQL backups."""
import datetime as dt
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from workspace_state_generation import DDL_COUNTERS, MANIFEST, SCHEMA, verify_export_triggers
import workspace_portability as transfer


def trigger_rows():
    return [{'TRIGGER_SCHEMA': SCHEMA, 'TRIGGER_NAME': name,
             'EVENT_MANIPULATION': value['event'], 'EVENT_OBJECT_TABLE': value['table'],
             'ACTION_TIMING': value['timing'], 'ACTION_STATEMENT': value['body'],
             'CREATED': dt.datetime(2026, 9, 29)} for name, value in MANIFEST.items()]


class InventoryConnection:
    def __init__(self, rows, changing=False, counters=True):
        self.rows = rows; self.changing = changing; self.counter_reads = 0; self.counters = counters

    def query(self, sql, args=(), **options):
        if sql.startswith('SHOW GLOBAL STATUS'):
            self.counter_reads += 1
            value = self.counter_reads if self.changing else 9
            rows = [{'Variable_name': key, 'Value': str(value)} for key in DDL_COUNTERS] if self.counters else []
        else:
            rows = [row for row in self.rows if row['TRIGGER_SCHEMA'] == args[0]]
        return SimpleNamespace(fetchall=lambda: rows)


class GenerationPortabilityTests(unittest.TestCase):
    def test_only_verified_derived_triggers_are_omittable_including_partial_installation(self):
        for rows in ([], trigger_rows()[:2], trigger_rows()):
            with self.subTest(count=len(rows)):
                report = verify_export_triggers(InventoryConnection(rows), transfer.DATABASES)
                self.assertTrue(report['safe_to_omit'])
                self.assertEqual(report['managed_present'], bool(rows))
                again = verify_export_triggers(InventoryConnection(list(reversed(rows))), transfer.DATABASES)
                self.assertEqual(report['contract_fingerprint'], again['contract_fingerprint'])

    def test_foreign_and_modified_triggers_cannot_silently_disappear(self):
        foreign = {**trigger_rows()[0], 'TRIGGER_NAME': 'scientific_audit', 'ACTION_STATEMENT': 'SET @seen=1'}
        for rows, managed in (([foreign], False), ([foreign, *trigger_rows()], True),
                              ([{**trigger_rows()[0], 'ACTION_STATEMENT': 'SET @seen=1'}], True)):
            with self.subTest(managed=managed, count=len(rows)):
                report = verify_export_triggers(InventoryConnection(rows), transfer.DATABASES)
                self.assertFalse(report['safe_to_omit'])
                self.assertEqual(report['managed_present'], managed)

    def test_unobservable_or_changing_ddl_cannot_authorize_omission(self):
        report = verify_export_triggers(InventoryConnection(trigger_rows(), counters=False), transfer.DATABASES)
        self.assertFalse(report['safe_to_omit'])
        with self.assertRaisesRegex(ValueError, 'coverage changed'):
            verify_export_triggers(InventoryConnection(trigger_rows(), changing=True), transfer.DATABASES)

    def test_dump_fences_coverage_and_closes_owned_connection(self):
        safe = {'managed_present': True, 'safe_to_omit': True, 'reason': None, 'contract_fingerprint': 'a'}
        with tempfile.TemporaryDirectory() as folder:
            connection = MagicMock()
            with patch.object(transfer, '_connection', return_value=connection), \
                    patch.object(transfer, '_dump_logical') as dump, \
                    patch('workspace_state_generation.verify_export_triggers', side_effect=[safe, {**safe, 'contract_fingerprint': 'b'}]):
                with self.assertRaisesRegex(ValueError, 'coverage changed during backup'):
                    transfer._dump(Path(folder), Path(folder) / 'database.sql')
            dump.assert_called_once_with(Path(folder), Path(folder) / 'database.sql', omit_derived_triggers=True)
            connection.close.assert_called_once()

    def test_mixed_trigger_installation_stops_before_running_dump(self):
        connection = MagicMock()
        with patch.object(transfer, '_connection', return_value=connection), \
                patch.object(transfer, '_dump_logical') as dump, \
                patch('workspace_state_generation.verify_export_triggers', return_value={
                    'managed_present': True, 'safe_to_omit': False, 'reason': 'custom triggers'}):
            with self.assertRaisesRegex(ValueError, 'custom triggers'):
                transfer._dump(Path('/disposable'), Path('/disposable/database.sql'))
        dump.assert_not_called(); connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
