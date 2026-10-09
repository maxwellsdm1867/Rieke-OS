"""Exact JSON numeric transport for authored state and logical database copies.

Import admission has its own representation policy. These helpers instead retain
the already-authoritative value: a saved predicate or a donor database document.
They never change a source server or relax the exact restore inventory.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
import json
import math

FLOATS_PER_STATEMENT = 64
MAX_EXPRESSION_FLOATS = 1024
MAX_EXPRESSION_PARAMETER_BYTES = 4 * 1024 * 1024
MAX_CORRECTION_SQL_BYTES = 1024 * 1024


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False)


def _identifier(value):
    return '`' + value.replace('`', '``') + '`'


def _reference(database, table):
    return _identifier(database) + '.' + _identifier(table)


def float_leaves(value, path='$'):
    """Yield JSON paths and finite binary64 decimal representations."""
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('Nonfinite JSON cannot be transported exactly')
        yield path, repr(value)
    elif isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError('JSON object keys must be strings')
            yield from float_leaves(child, path + '.' + json.dumps(key, ensure_ascii=False))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from float_leaves(child, f'{path}[{index}]')


def mysql_json_expression(value):
    """Return a parameterized INSERT/UPDATE expression preserving finite floats.

    JSON text establishes structure and nonfloating types. Typed DOUBLE operands
    establish the existing binary64 leaves without the JSON text numeric parser.
    Callers must read the result with verify_json_fields before committing. The
    typed path supports at most 1024 float leaves and 4 MiB of added UTF-8 path /
    number parameters: at most 16 nested JSON_SET calls. Larger typed expressions
    fail explicitly. The original JSON keeps the existing database packet limit;
    large float-free membership lists do not acquire a new size limit. No SQL is executed and no
    user value is interpolated here. Python None means JSON null, not SQL NULL.
    """
    encoded = json.dumps(value, allow_nan=False)
    sql, args = 'CAST(%s AS JSON)', [encoded]
    batch = []
    count, extra_bytes = 0, 0
    for leaf in float_leaves(value):
        count += 1
        extra_bytes += sum(len(item.encode('utf-8')) for item in leaf)
        if count > MAX_EXPRESSION_FLOATS or extra_bytes > MAX_EXPRESSION_PARAMETER_BYTES:
            raise ValueError('Exact JSON expression exceeds supported size; original value was not written')
        batch.append(leaf)
        if len(batch) == FLOATS_PER_STATEMENT:
            sql = 'JSON_SET(' + sql + ',' + ','.join('%s,CAST(%s AS DOUBLE)' for _ in batch) + ')'
            args.extend(item for leaf in batch for item in leaf)
            batch = []
    if batch:
        sql = 'JSON_SET(' + sql + ',' + ','.join('%s,CAST(%s AS DOUBLE)' for _ in batch) + ')'
        args.extend(item for leaf in batch for item in leaf)
    return sql, tuple(args)


def verify_json_fields(query, database, table, row, fields, key_fields, *, sql_null_fields=()):
    """Require exact JSON readback for an owned row before the caller commits.

    query is a DB-API/DataJoint-style callable returning a result with fetchall.
    Identifiers must originate from the caller's admitted schema. Key fields must
    be the complete live primary key; this helper never chooses row identity.
    Root None means JSON null unless explicitly named in sql_null_fields.
    """
    fields, key_fields = tuple(fields), tuple(key_fields)
    if not fields:
        return
    if not key_fields or any(key not in row or row[key] is None for key in key_fields):
        raise ValueError('Exact JSON verification requires the complete primary key')
    sql = ('SELECT ' + ','.join(_identifier(field) for field in fields) +
           ' FROM ' + _reference(database, table) + ' WHERE ' +
           ' AND '.join(_identifier(key) + '=%s' for key in key_fields))
    rows = query(sql, tuple(row[key] for key in key_fields)).fetchall()
    if len(rows) != 1 or len(rows[0]) != len(fields):
        raise ValueError('Exact JSON verification did not find one complete row')
    for field, actual in zip(fields, rows[0]):
        if field in sql_null_fields:
            if actual is not None or row[field] is not None:
                raise ValueError('Stored SQL NULL differs from authoritative value: ' + table + '.' + field)
            continue
        if actual is None:
            raise ValueError('Stored SQL NULL differs from authoritative JSON value: ' + table + '.' + field)
        if isinstance(actual, (str, bytes)):
            actual = json.loads(actual)
        if _canonical(actual) != _canonical(row[field]):
            raise ValueError('Stored JSON differs from authoritative value: ' + table + '.' + field)


def _literal(value):
    """SQL literals independent of sql_mode and backslash/string delimiters."""
    if value is None:
        return 'NULL'
    if type(value) is bool:
        return '1' if value else '0'
    if type(value) is int:
        return str(value)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('Nonfinite database key cannot be transported')
        return 'CAST(' + _literal(repr(value)) + ' AS DOUBLE)'
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('Nonfinite database key cannot be transported')
        return format(value, 'f')
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    if isinstance(value, dt.datetime):
        value = value.isoformat(sep=' ')
    elif isinstance(value, (dt.date, dt.time)):
        value = value.isoformat()
    elif isinstance(value, dt.timedelta):
        negative = value < dt.timedelta(0)
        value = -value if negative else value
        seconds = value.days * 86400 + value.seconds
        value = ('-' if negative else '') + f'{seconds // 3600:02}:{seconds % 3600 // 60:02}:{seconds % 60:02}.{value.microseconds:06}'
    if isinstance(value, str):
        return "CONVERT(X'" + value.encode('utf-8').hex() + "' USING utf8mb4)"
    raise ValueError('Unsupported database key type: ' + type(value).__name__)


def _changed_float_leaves(source, decoded, path='$'):
    """Locate only float changes; every other source value/type stays exact."""
    if type(source) is not type(decoded):
        raise ValueError('JSON reparse changed a nonfloating type')
    if type(source) is float:
        if not math.isfinite(source) or not math.isfinite(decoded):
            raise ValueError('Nonfinite JSON cannot be transported exactly')
        if repr(source) != repr(decoded):
            yield path, repr(source)
    elif isinstance(source, dict):
        if source.keys() != decoded.keys():
            raise ValueError('JSON reparse changed object keys')
        for key, value in source.items():
            yield from _changed_float_leaves(value, decoded[key], path + '.' + json.dumps(key, ensure_ascii=False))
    elif isinstance(source, list):
        if len(source) != len(decoded):
            raise ValueError('JSON reparse changed array length')
        for index, (value, actual) in enumerate(zip(source, decoded)):
            yield from _changed_float_leaves(value, actual, f'{path}[{index}]')
    elif source != decoded:
        raise ValueError('JSON reparse changed a nonfloating value')


def append_json_float_corrections(connection, path, databases, *, omitted_triggers=False):
    """Complete a trusted mysqldump using its quiescent donor connection.

    Caller owns a global read lock across donor inventory, dump and this scan;
    before/after fingerprints alone do not protect against concurrent ABA writes.
    The appended SQL is sealed with the dump and runs with the same
    restricted restore privileges. Server JSON is reparsed through its *text*
    representation, matching logical dump transport. Only changed float leaves
    generate updates, at most 64 paths per statement. Rows are streamed; no full
    project JSON or SQL parser is held here. The unchanged exact inventory is the
    final authority after restore. Initial qualification is MySQL 8.4.2 donor and
    recipient only; a different parser can change additional leaves, in which
    case exact inventory verification refuses publication. An affected table
    with update triggers (unless safely omitted), automatic updates or generated
    columns is refused. A CHECK constraint may refuse the original dump insertion;
    it is never bypassed. Foreign keys are untouched: JSON columns cannot be
    primary/foreign keys without generated columns, which are refused here.
    """
    from pymysql.cursors import SSCursor

    stats = {'documents': 0, 'float_leaves': 0, 'statements': 0}
    with connection.cursor() as cursor:
        cursor.execute('SELECT TRIGGER_SCHEMA, EVENT_OBJECT_TABLE FROM information_schema.triggers '
                       'WHERE TRIGGER_SCHEMA IN (' + ','.join('%s' for _ in databases) +
                       ") AND EVENT_MANIPULATION='UPDATE'", tuple(databases))
        triggered_tables = set(cursor.fetchall())
        cursor.execute('SELECT table_schema, table_name FROM information_schema.tables '
                       'WHERE table_schema IN (' + ','.join('%s' for _ in databases) +
                       ') AND table_type=%s ORDER BY table_schema, table_name',
                       (*databases, 'BASE TABLE'))
        tables = cursor.fetchall()
        with path.open('ab') as output:
            for database, table in tables:
                reference = _reference(database, table)
                cursor.execute('SHOW COLUMNS FROM ' + reference)
                columns = cursor.fetchall()
                fields = [column[0] for column in columns if column[1] == 'json']
                if not fields:
                    continue
                keys = [column[0] for column in columns if column[3] == 'PRI']
                selected = [_identifier(key) for key in keys]
                for field in fields:
                    name = _identifier(field)
                    selected.extend((name, 'CAST(CAST(' + name + ' AS CHAR CHARACTER SET utf8mb4) AS JSON)'))
                with connection.cursor(SSCursor) as data:
                    data.execute('SELECT ' + ','.join(selected) + ' FROM ' + reference)
                    while rows := data.fetchmany(128):
                        for row in rows:
                            key_values = row[:len(keys)]
                            for index, field in enumerate(fields):
                                original, reparsed = row[len(keys) + 2 * index:len(keys) + 2 * index + 2]
                                if original is None:
                                    continue
                                source, decoded = json.loads(original), json.loads(reparsed)
                                if _canonical(source) == _canonical(decoded):
                                    continue
                                # Validate the complete document before emitting any of its updates.
                                leaves = list(_changed_float_leaves(source, decoded))
                                if not keys or any(value is None for value in key_values):
                                    raise ValueError('Changing JSON requires a complete primary key for exact transfer: ' + reference)
                                if ((database, table) in triggered_tables and not omitted_triggers
                                        or any('on update' in str(column[5]).lower()
                                               or 'virtual generated' in str(column[5]).lower()
                                               or 'stored generated' in str(column[5]).lower() for column in columns)):
                                    raise ValueError('Exact JSON transfer refuses automatic update side effects: ' + reference)
                                stats['documents'] += 1
                                stats['float_leaves'] += len(leaves)
                                for start in range(0, len(leaves), FLOATS_PER_STATEMENT):
                                    batch = leaves[start:start + FLOATS_PER_STATEMENT]
                                    sql = ('UPDATE ' + reference + ' SET ' + _identifier(field) +
                                           '=JSON_SET(' + _identifier(field) + ',' +
                                           ','.join(_literal(key) + ',CAST(' + _literal(value) + ' AS DOUBLE)' for key, value in batch) +
                                           ') WHERE ' + ' AND '.join(_identifier(key) + '=' + _literal(value)
                                                                     for key, value in zip(keys, key_values)) + ';\n')
                                    if len(sql.encode('utf-8')) > MAX_CORRECTION_SQL_BYTES:
                                        raise ValueError('Exact JSON correction exceeds supported statement size')
                                    if stats['statements'] == 0:
                                        output.write(b'\n-- Exact finite JSON values from the logical backup donor.\n')
                                    output.write(sql.encode('utf-8'))
                                    stats['statements'] += 1
    return stats
