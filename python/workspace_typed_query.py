"""Typed native predicate compilation shared by the disposable read index.

Adapted from the October 1 real-data experiment. Native validation and exact
JSON/number equality remain authoritative; no application source is imported
from an absolute path. Public integration is in workspace_typed_index.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import workspace_predicates as predicates
from workspace_metadata_objects import Decoder

ORIGINAL_TABLES = ('meta', 'epochs', 'fields', 'field_values', 'epoch_values', 'sources', 'metadata_objects')
CORE_COLUMNS = ('epoch_uuid', 'source_sha256', 'cell_uuid', 'block_uuid', 'group_uuid',
                'protocol_name', 'date', 'start_time', 'block_start_time', 'epoch_number',
                'duration_seconds', 'cell_label', 'cell_type', 'group_label')
CORE_FIELDS = {'epoch': 'epoch_uuid', 'cell': 'cell_uuid', 'block': 'block_uuid',
               'group': 'group_uuid', 'protocol': 'protocol_name', 'date': 'date',
               'cell type': 'cell_type', 'group label': 'group_label', 'block time': 'block_start_time'}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def file_sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def equality_json(value):
    """Canonical equal() identity, including nested int/float merges.

    Ratios preserve exact Python numeric equality; boolean has its own type.
    Original JSON is retained separately and is always used for returned values.
    """
    kind = predicates.kind(value)
    if kind == 'number':
        numerator, denominator = (value, 1) if type(value) is int else value.as_integer_ratio()
        return canonical(['number', str(numerator), str(denominator)])
    if kind == 'array':
        return canonical(['array', [equality_json(item) for item in value]])
    if kind == 'object':
        return canonical(['object', [[key, equality_json(value[key])] for key in sorted(value)]])
    return canonical([kind, value])



class _TypedQueries:
    def _leaf(self, node):
        field, op = node['field'], node['operator']
        number = self.fields[field]
        column = CORE_FIELDS.get(field)
        if column and self.core_safe.get(field) and op in {'eq', 'exists', 'missing', 'is_null'}:
            if op == 'exists':
                return '1', []
            if op in {'missing', 'is_null'}:
                return '0', []
            if predicates.kind(node['value']) == 'string':
                return f'c.{column}=?', [node['value']]
        if op == 'missing':
            return 'c.epoch_id NOT IN (SELECT epoch_id FROM epoch_values WHERE field_no=?)', [number]
        if op == 'exists':
            return 'c.epoch_id IN (SELECT epoch_id FROM epoch_values WHERE field_no=?)', [number]
        selector, arguments = '', [number]
        if op == 'is_null':
            selector = "v.kind='null'"
        elif op in {'eq','ne','in','not_in'}:
            choices = node['value'] if op in {'in','not_in'} else [node['value']]
            selector = 'v.equality_json IN (' + ','.join('?' for _ in choices) + ')' if choices else '0'
            arguments.extend(equality_json(value) for value in choices)
            if op in {'ne','not_in'}:
                selector = 'NOT (' + selector + ')'
        elif op in {'gt','gte','lt','lte'} and number not in self.wide_fields:
            selector = "v.kind='number' AND v.numeric_value " + {'gt':'>','gte':'>=','lt':'<','lte':'<='}[op] + ' ?'
            arguments.append(node['value'])
        else:
            # Contains and wide-int range comparisons are evaluated only on the
            # small native dictionary, never by materializing per-epoch DTOs.
            # Dictionary cardinality may itself reach millions. Stream exact
            # native comparisons into a disk-backed TEMP relation rather than
            # building a Python list or exceeding SQLite's parameter limit.
            match_no = self._dictionary_match_no
            self._dictionary_match_no += 1
            rows = ((match_no, value_id) for value_id, raw in self.connection.execute(
                'SELECT value_id,value_json FROM typed_values WHERE field_no=?', [number])
                if predicates.matches(node, {field: json.loads(raw)}))
            self.connection.executemany('INSERT INTO dictionary_matches VALUES (?,?)', rows)
            selector = 'v.value_id IN (SELECT value_id FROM dictionary_matches WHERE match_no=?)'
            arguments.append(match_no)
        return ('c.epoch_id IN (SELECT ev.epoch_id FROM typed_values v JOIN epoch_values ev '
                'ON ev.field_no=v.field_no AND ev.value_id=v.value_id WHERE v.field_no=? AND (' + selector + '))'), arguments


    def _compile(self, node):
        for group, operator, empty in [('all',' AND ','1'),('any',' OR ','0')]:
            if group in node:
                compiled = [self._compile(child) for child in node[group]]
                return '(' + operator.join(sql for sql, _ in compiled) + ')' if compiled else empty, [a for _, args in compiled for a in args]
        if 'not' in node:
            sql, arguments = self._compile(node['not'])
            return 'NOT (' + sql + ')', arguments
        return self._leaf(node)


    def predicate_sql(self, predicate):
        return ('1', []) if predicate is None else self._compile(self._validate(predicate))


    def _where(self, predicate=None, scope=None):
        self.connection.execute('DELETE FROM dictionary_matches')
        self._dictionary_match_no = 0
        sql, arguments = self.predicate_sql(predicate)
        if isinstance(scope, dict):
            allowed = {'protocol','cell','block','group','sources','epoch_ids'}
            if set(scope) - allowed:
                raise ValueError('Unknown direct scope field')
            for field, value in scope.items():
                if field == 'sources':
                    self.connection.execute('DELETE FROM supplied_sources')
                    self.connection.executemany('INSERT OR IGNORE INTO supplied_sources VALUES (?)',
                                                self._scope_values(value))
                    sql += ' AND c.epoch_id IN (SELECT e.epoch_id FROM native.epochs e JOIN supplied_sources s ON s.source_sha=e.source_sha)'
                    continue
                if field == 'epoch_ids':
                    self._supply_identities(value)
                    sql += ' AND c.epoch_id IN (SELECT epoch_id FROM supplied_scope)'
                    continue
                part, params = self.predicate_sql({'field':field,'operator':'eq','value':value})
                sql += ' AND (' + part + ')'
                arguments.extend(params)
        elif scope is not None:
            self._supply_identities(scope)
            sql += ' AND c.epoch_id IN (SELECT epoch_id FROM supplied_scope)'
        return sql, arguments

    def _scope_values(self, values):
        if isinstance(values, (str, bytes, dict)):
            raise ValueError('Scope identities must be an iterable of strings')
        try:
            iterator = iter(values)
        except TypeError:
            raise ValueError('Scope identities must be an iterable of strings') from None
        for number, value in enumerate(iterator):
            if number % 2000 == 0:
                self._check()
            if not isinstance(value, str):
                raise ValueError('Scope identities must be strings')
            yield (value,)

    def _supply_identities(self, identities):
        self.connection.execute('DELETE FROM supplied_scope')
        self.connection.executemany(
            'INSERT OR IGNORE INTO supplied_scope SELECT epoch_id FROM epochs WHERE epoch_uuid=?',
            self._scope_values(identities))


    def membership(self, predicate=None, scope=None):
        where, arguments = self._where(predicate, scope)
        return [identity for identity, in self.connection.execute('SELECT c.epoch_uuid FROM typed_core c WHERE ' + where + ' ORDER BY c.sort_rank', arguments)]


    def page(self, predicate=None, scope=None, cursor=None, limit=60):
        where, arguments = self._where(predicate, scope)
        return self._page(where, arguments, cursor, limit)


    def detail(self, epoch_uuid):
        record = self.connection.execute('SELECT row_json,detail_blob FROM epochs WHERE epoch_uuid=?', [epoch_uuid]).fetchone()
        if record is None:
            raise KeyError(epoch_uuid)
        return self.decoder.decode(self.connection, json.loads(record[0]), record[1])


    def groups(self, kind='cell', predicate=None, scope=None, cursor=None, limit=60):
        if kind not in {'cell','block'} or type(limit) is not int or not 1<=limit<=100:
            raise ValueError('Unsupported bounded group query')
        column = kind + '_uuid'
        where, arguments = self._where(predicate, scope)
        if kind == 'cell':
            if cursor is not None:
                if not isinstance(cursor,str):
                    raise ValueError('Cell group cursor must be a UUID')
                where += f' AND c.{column}>?'
                arguments.append(cursor)
            result = self.connection.execute(f'SELECT c.{column},COUNT(*) FROM typed_core c WHERE ' + where + f' GROUP BY c.{column} ORDER BY c.{column} LIMIT ?', arguments+[limit+1]).fetchall()
            page = result[:limit]
            return dict(groups=[dict(uuid=identity,count=n) for identity,n in page],cursor=page[-1][0] if len(result)>limit else None)
        # Previous typed prototype orders blocks by their recorded start time,
        # then UUID, and applies the cursor after grouping all matched members.
        grouped = ("SELECT c.block_uuid AS uuid,COUNT(*) AS n,MIN(COALESCE(c.block_start_time,'')) AS start_time "
                   'FROM typed_core c WHERE ' + where + ' GROUP BY c.block_uuid')
        post_where = ''
        if cursor is not None:
            if (not isinstance(cursor,dict) or set(cursor)!={'start_time','key'}
                    or not all(isinstance(value,str) for value in cursor.values())):
                raise ValueError('Block cursor requires start_time and key strings')
            post_where = ' WHERE (start_time,uuid)>(?,?)'
            arguments.extend([cursor['start_time'],cursor['key']])
        result = self.connection.execute('SELECT uuid,n,start_time FROM (' + grouped + ')' + post_where + ' ORDER BY start_time,uuid LIMIT ?', arguments+[limit+1]).fetchall()
        page = result[:limit]
        next_cursor = {'start_time':page[-1][2],'key':page[-1][0]} if len(result)>limit else None
        return dict(groups=[dict(uuid=identity,count=n) for identity,n,_ in page],cursor=next_cursor)


    def explain(self, predicate=None, scope=None):
        where, arguments = self._where(predicate, scope)
        return [list(row) for row in self.connection.execute('EXPLAIN QUERY PLAN SELECT c.epoch_uuid FROM typed_core c WHERE ' + where + ' ORDER BY c.sort_rank LIMIT 60', arguments)]
