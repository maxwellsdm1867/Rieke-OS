"""Exact JSON transport contracts; opt-in native evidence is separate."""
import datetime as dt
from decimal import Decimal
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import workspace_json_transport as transport

VALUE = 5.5511151231257815e-17
REPARSED = 5.551115123125782e-17


class JSONExpressionTests(unittest.TestCase):
    def test_json_scalar_types_and_parameterization_are_preserved(self):
        value = {'quote"\\雪\n': [True, 2**63 + 1, None, '1.0', -0.0, 5e-324, VALUE]}
        sql, args = transport.mysql_json_expression(value)
        self.assertEqual(json.loads(args[0]), value)
        self.assertEqual(sql.count('AS DOUBLE'), 3)
        self.assertNotIn('雪', sql)
        self.assertEqual(args[1::2], ('$.' + json.dumps('quote"\\雪\n', ensure_ascii=False) + '[4]',
                                     '$.' + json.dumps('quote"\\雪\n', ensure_ascii=False) + '[5]',
                                     '$.' + json.dumps('quote"\\雪\n', ensure_ascii=False) + '[6]'))
        self.assertEqual(args[2::2], ('-0.0', '5e-324', repr(VALUE)))
        for value in (None, True, 1, 2**63 + 1, 'text', {}, []):
            sql, args = transport.mysql_json_expression(value)
            self.assertEqual(sql, 'CAST(%s AS JSON)')
            self.assertEqual(json.loads(args[0]), value)

    def test_total_expression_depth_and_added_parameter_bytes_are_bounded(self):
        sql, args = transport.mysql_json_expression([VALUE] * transport.MAX_EXPRESSION_FLOATS)
        self.assertEqual(sql.count('JSON_SET('), 16)
        with self.assertRaisesRegex(ValueError, 'supported size'):
            transport.mysql_json_expression([VALUE] * (transport.MAX_EXPRESSION_FLOATS + 1))
        with patch.object(transport, 'MAX_EXPRESSION_PARAMETER_BYTES', 32):
            with self.assertRaisesRegex(ValueError, 'supported size'):
                transport.mysql_json_expression({'a' * 33: VALUE})
            # Original membership/text bytes do not acquire the added-path limit.
            transport.mysql_json_expression({'members': ['x' * 1000], 'x': 0.5})

    def test_nonfinite_values_and_nonstring_keys_fail_before_sql(self):
        for value in (math.nan, math.inf, -math.inf, {1: VALUE}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                transport.mysql_json_expression(value)

    def test_exact_readback_rejects_types_nearby_float_and_missing_rows(self):
        source = {'project': 'owned', 'id': 7, 'payload': {'flag': True, 'x': VALUE}}
        for actual in ({'flag': True, 'x': REPARSED}, {'flag': 1, 'x': VALUE}):
            query = lambda *args: SimpleNamespace(fetchall=lambda: [(json.dumps(actual),)])
            with self.assertRaisesRegex(ValueError, 'authoritative value'):
                transport.verify_json_fields(query, 'recording_workspace', 'fixture', source,
                                             ['payload'], ['project', 'id'])
        calls = []
        def query(sql, args):
            calls.append((sql, args))
            return SimpleNamespace(fetchall=lambda: [(json.dumps(source['payload']),)])
        transport.verify_json_fields(query, 'recording_workspace', 'fixture', source,
                                     ['payload'], ['project', 'id'])
        self.assertEqual(calls[0][1], ('owned', 7))
        for rows in ([], [('{}',), ('{}',)]):
            with self.assertRaisesRegex(ValueError, 'one complete row'):
                transport.verify_json_fields(lambda *args: SimpleNamespace(fetchall=lambda: rows),
                                             'db', 't', source, ['payload'], ['id'])

    def test_readback_distinguishes_explicit_sql_null_from_json_null(self):
        row = {'id': 1, 'payload': None}
        sql_null = lambda *args: SimpleNamespace(fetchall=lambda: [(None,)])
        json_null = lambda *args: SimpleNamespace(fetchall=lambda: [('null',)])
        transport.verify_json_fields(json_null, 'db', 't', row, ['payload'], ['id'])
        transport.verify_json_fields(sql_null, 'db', 't', row, ['payload'], ['id'],
                                     sql_null_fields={'payload'})
        with self.assertRaisesRegex(ValueError, 'SQL NULL'):
            transport.verify_json_fields(sql_null, 'db', 't', row, ['payload'], ['id'])
        with self.assertRaisesRegex(ValueError, 'SQL NULL'):
            transport.verify_json_fields(json_null, 'db', 't', row, ['payload'], ['id'],
                                         sql_null_fields={'payload'})


class DumpCorrectionTests(unittest.TestCase):
    def connection(self, values, *, keys=True, extra='', triggers=()):
        from pymysql.cursors import SSCursor
        connection, metadata, data = MagicMock(), MagicMock(), MagicMock()
        metadata.__enter__.return_value = metadata
        data.__enter__.return_value = data
        metadata.fetchall.side_effect = [list(triggers), [('schema', 'table`quoted')],
            [('tenant', 'varchar(100)', 'NO', 'PRI' if keys else '', None, ''),
             ('id', 'int', 'NO', 'PRI' if keys else '', None, ''),
             ('payload', 'json', 'YES', '', None, extra)]]
        data.fetchmany.side_effect = [values, []]
        connection.cursor.side_effect = lambda kind=None: data if kind is SSCursor else metadata
        return connection, data

    def append(self, values, **kwargs):
        connection, data = self.connection(values, **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'database.sql'
            path.write_bytes(b'-- original dump\n')
            stats = transport.append_json_float_corrections(connection, path, ('schema', 'recording_workspace'))
            return path.read_text(), stats, data

    def test_only_reparse_changed_leaves_are_appended_with_hex_values(self):
        source = {'x': VALUE, 'unchanged': 0.5, 'integer': 2**63 + 1}
        decoded = {**source, 'x': REPARSED}
        sql, stats, data = self.append([("tenant'\\雪; DROP TABLE x", 7,
                                       json.dumps(source), json.dumps(decoded))])
        self.assertEqual(stats, {'documents': 1, 'float_leaves': 1, 'statements': 1})
        self.assertIn('UPDATE `schema`.`table``quoted`', sql)
        self.assertNotIn('DROP TABLE x', sql)
        self.assertIn('CAST(CAST(`payload` AS CHAR CHARACTER SET utf8mb4) AS JSON)', data.execute.call_args.args[0])
        self.assertIn('`tenant`=CONVERT(X', sql)
        self.assertIn('AND `id`=7;', sql)
        self.assertEqual(sql.count('AS DOUBLE'), 1)

    def test_sql_null_json_null_and_unchanged_documents_need_no_updates(self):
        values = [('a', 1, None, None), ('a', 2, 'null', 'null'),
                  ('a', 3, '{"value": 0.5}', '{"value":0.5}'),
                  ('a', 4, '[]', '[]'), ('a', 5, '{}', '{}')]
        sql, stats, _ = self.append(values)
        self.assertEqual(sql, '-- original dump\n')
        self.assertEqual(stats['statements'], 0)

    def test_changed_documents_require_primary_key_and_no_update_side_effects(self):
        doc, decoded = json.dumps({'x': VALUE}), json.dumps({'x': REPARSED})
        cases = [dict(keys=False), dict(extra='on update CURRENT_TIMESTAMP'),
                 dict(extra='STORED GENERATED'), dict(triggers=[('schema', 'table`quoted')])]
        for options in cases:
            values = [(doc, decoded)] if options.get('keys') is False else [('a', 1, doc, decoded)]
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.append(values, **options)

    def test_nonnumeric_change_cannot_be_hidden_by_float_correction(self):
        with self.assertRaisesRegex(ValueError, 'nonfloating'):
            self.append([('a', 1, json.dumps({'x': VALUE, 'id': 3}),
                          json.dumps({'x': REPARSED, 'id': 4}))])

    def test_correction_statements_have_path_and_total_byte_bounds(self):
        source, decoded = [VALUE] * 130, [REPARSED] * 130
        sql, stats, _ = self.append([('a', 1, json.dumps(source), json.dumps(decoded))])
        self.assertEqual(stats['statements'], 3)
        self.assertEqual([line.count('AS DOUBLE') for line in sql.splitlines() if line.startswith('UPDATE')], [64, 64, 2])
        with patch.object(transport, 'MAX_CORRECTION_SQL_BYTES', 10), self.assertRaisesRegex(ValueError, 'statement size'):
            self.append([('a', 1, json.dumps(source), json.dumps(decoded))])

    def test_primary_key_literals_do_not_depend_on_backslash_sql_mode(self):
        for value in ("'\\雪", b'\x00\xff', Decimal('2.50'), dt.date(2026, 10, 9),
                      dt.datetime(2026, 10, 9, 1, 2, 3), dt.timedelta(hours=-2), 3, 1.5):
            literal = transport._literal(value)
            self.assertNotIn('\\', literal)
            self.assertNotIn('雪', literal)


if __name__ == '__main__':
    unittest.main()
