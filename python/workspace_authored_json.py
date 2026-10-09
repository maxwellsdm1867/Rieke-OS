"""Exact first writes for the app's saved queries and sealed explorer recipes.

Only the enumerated app-owned schemas qualify for native SQL expressions. Custom
writers retain their existing method and must pass the same exact JSON readback.
Callers own transactions, optimistic versions, locks, audit and publication.
"""
from __future__ import annotations

import datetime as dt
import json

from workspace_json_transport import mysql_json_expression, verify_json_fields

# This is deliberately not a generic DataJoint replacement. No blobs, binary
# UUIDs, defaults, generated fields, custom adapters, or omitted columns qualify.
SCHEMAS = {
    'search_preset': (('project_uuid', 'preset_uuid'), ('predicate',), {
        'project_uuid': 'varchar(36)', 'preset_uuid': 'varchar(36)', 'name': 'varchar(160)',
        'description': 'varchar(2000)', 'predicate': 'json', 'splits': 'varchar(4096)',
        'pinned': 'tinyint', 'version': 'int unsigned', 'updated_at': 'datetime', 'actor': 'varchar(255)'}),
    'search_preset_version': (('project_uuid', 'preset_uuid', 'version'), ('recipe',), {
        'project_uuid': 'varchar(36)', 'preset_uuid': 'varchar(36)', 'version': 'int unsigned', 'recipe': 'json'}),
    'search_query_last_run': (('project_uuid', 'query_sha256'), ('result',), {
        'project_uuid': 'varchar(36)', 'query_sha256': 'char(64)', 'result': 'json'}),
    'dataset_revision': (('project_uuid', 'dataset_uuid'), ('recipe',), {
        'project_uuid': 'varchar(36)', 'dataset_uuid': 'varchar(36)', 'protocol_uuid': 'varchar(36)',
        'created_at': 'datetime', 'actor': 'varchar(255)', 'recipe': 'json', 'artifact_path': 'varchar(2048)',
        'artifact_sha256': 'char(64)', 'epoch_count': 'int unsigned'}),
    'explorer_revision': (('project_uuid', 'revision_uuid'), ('summary', 'recipe'), {
        'project_uuid': 'varchar(36)', 'revision_uuid': 'varchar(36)', 'created_at': 'datetime',
        'name': 'varchar(255)', 'parent_revision_uuid': 'varchar(36)', 'summary': 'json', 'recipe': 'json'}),
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _native_owner(table, method):
    writer = getattr(table, method)
    owner = getattr(writer, '__self__', None)
    # Inert/custom adapters do not import the scientific dependency just to save.
    if owner is None or not hasattr(owner, 'full_table_name'):
        return None
    from datajoint.table import Table
    if not isinstance(owner, Table) or getattr(writer, '__func__', None) is not getattr(Table, method):
        return None
    if method == 'insert1' and getattr(owner.insert, '__func__', None) is not Table.insert:
        return None
    return owner


def write_row(table, row, *, schema, update=False):
    """Write one admitted row, then verify authoritative JSON before returning.

    A native write requires an existing caller transaction. Every supplied scalar
    maps directly to a plain declared SQL field. Root None uses SQL NULL, matching
    these nullable/default-null fields; nested None remains JSON null. No commit,
    repair of existing data, tolerant comparison or retry occurs here.
    """
    keys, fields, columns = SCHEMAS[schema]
    if set(row) != set(columns) or any(row[key] is None for key in keys):
        raise ValueError('Exact authored JSON requires the complete admitted row and primary key')
    for field, value in row.items():
        if field in fields:
            _canonical(value)
        elif value is not None and type(value) not in (str, int, bool, dt.datetime):
            raise ValueError('Unsupported authored scalar: ' + field)
    method = 'update1' if update else 'insert1'
    owner = _native_owner(table, method)
    if owner is None:
        getattr(table, method)(row)
        actual = (table & {key: row[key] for key in keys}).to_dicts()
        if len(actual) != 1 or any(_canonical(actual[0].get(field)) != _canonical(row[field]) for field in fields):
            raise ValueError('Custom authored writer did not preserve exact JSON')
        return
    if (owner.database != 'recording_workspace' or owner.table_name != schema or
            tuple(owner.primary_key) != keys or owner.restriction or
            set(owner.heading.names) != set(columns)):
        raise ValueError('Native authored JSON table does not match its admitted schema')
    for name, expected in columns.items():
        actual = owner.heading.attributes[name].type.lower()
        if actual != expected:
            raise ValueError('Native authored JSON column does not match its admitted schema: ' + name)
    if not owner.connection.in_transaction:
        raise ValueError('Exact authored JSON requires a caller-owned transaction')
    scope = {key: row[key] for key in keys}
    if update and len(owner & scope) != 1:
        raise ValueError('Authored update requires exactly one existing row')
    names = [name for name in row if not update or name not in keys]
    expressions, args = [], []
    for name in names:
        value = row[name]
        if name in fields and value is not None:
            expression, values = mysql_json_expression(value)
        else:
            expression, values = '%s', (value,)
        expressions.append(expression)
        args.extend(values)
    if update:
        sql = 'UPDATE ' + owner.full_table_name + ' SET ' + ','.join(
            '`' + name + '`=' + expression for name, expression in zip(names, expressions))
        sql += ' WHERE ' + ' AND '.join('`' + key + '`=%s' for key in keys)
        args.extend(row[key] for key in keys)
    else:
        sql = ('INSERT INTO ' + owner.full_table_name + ' (' + ','.join('`' + name + '`' for name in names) +
               ') VALUES (' + ','.join(expressions) + ')')
    owner.connection.query(sql, tuple(args))
    verify_json_fields(owner.connection.query, owner.database, owner.table_name, row, fields, keys,
                       sql_null_fields=tuple(field for field in fields if row[field] is None))
