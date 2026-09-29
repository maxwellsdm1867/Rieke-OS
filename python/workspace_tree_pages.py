"""Bounded, revision-checked metadata tree navigation; never reads waveforms.

Branch keys encode exact typed values through a digest, including a distinct
missing marker. They are navigation keys, never queries or scientific IDs.
"""
from __future__ import annotations

import re
import uuid

from workspace_recipes import checksum, parse_splits
from workspace_tree import (field_value_order, joint_definition, joint_value,
                            value_key, protocol_family)
from workspace_predicates import validate as validate_predicate, matches
from workspace_tree_code import matlab_tree_command
from workspace_service import validate_filters


class StaleTreePage(ValueError):
    pass


def _uuid(value):
    if not isinstance(value, str):
        raise ValueError('Expected an epoch or protocol UUID')
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError('Expected an epoch or protocol UUID') from error


def _summary(rows):
    durations = [row.get('duration_seconds') for row in rows]
    return {'count': len(rows), 'cells': len({row['cell_uuid'] for row in rows}),
            'duration_seconds': sum(durations) if all(value is not None for value in durations) else None}


def _epoch(row):
    return {key: row.get(key) for key in ('epoch_uuid', 'start_time', 'cell_uuid',
            'cell_label', 'date', 'block_uuid', 'epoch_number')} | {
            'label': f"Epoch {row['epoch_number']} · {row['start_time'][11:]}"}


def _chronology(row):
    return row['date'], row['start_time'][11:], row['epoch_uuid']


def selection_revision(service, protocol, predicate, filters, order, rows, binding=None, annotation_scope=None):
    """Shared explorer-summary/page identity, independent of page offset/path."""
    if protocol is not None and binding is None:
        binding = service.binding(protocol)
    return checksum({'version':1, 'project_uuid':service.project['project_uuid'],
        'protocol_uuid':protocol, 'binding':binding and {'version':binding['version'],
            'revision_uuid':binding.get('revision_uuid')},
        'predicate':predicate, 'filters':filters or {}, 'splits':order,
        **({'annotation_scope_revision':annotation_scope['revision']} if annotation_scope else {}),
        'source_scope_revision':service.source_scope()['revision'] if protocol is None else None,
        'members':[(row['epoch_uuid'],service._fingerprints[row['epoch_uuid']])
                   for row in sorted(rows,key=lambda row:row['epoch_uuid'])]})


class TreePages:
    """Service adapter with no retained full trees or per-branch membership copies."""
    def __init__(self, service):
        self.service = service

    def _scope(self, body):
        service = self.service
        service._ready()
        protocol = body.get('protocol_uuid')
        if protocol is not None:
            protocol = _uuid(protocol)
            if 'predicate' in body:
                raise ValueError('Protocol tree membership cannot be replaced by a source predicate')
        filters = validate_filters(body.get('filters'))
        rows = service._tree_rows(protocol, filters)
        index = getattr(service, 'disk_index', None)
        if index is not None:
            # Registered definitions remain valid for empty or excluded scopes;
            # paged navigation needs no repeated per-field scope summaries.
            catalog = index.catalog()
            values = None
        else:
            catalog, values = service._tree_fields(protocol, filters)
        predicate = None
        annotation_scope = None
        if protocol is None:
            requested_predicate = body.get('predicate', {'all': []})
            if requested_predicate == {'all': []}:
                predicate = {'all': []}
            else:
                predicate, identities, annotation_scope = service.match_predicate(requested_predicate, ids=[row['epoch_uuid'] for row in rows])
                allowed = set(identities)
                rows = [row for row in rows if row['epoch_uuid'] in allowed]
        catalog = {**catalog, 'protocol_family':protocol_family(rows)}
        definitions = {field['id']: field for field in catalog['fields']}
        splits = body.get('splits', 'date,cell,block')
        order = parse_splits(splits, definitions)
        for field in order:
            if field not in definitions:
                definitions[field] = joint_definition(field, definitions)
        if index is not None:
            requested = order if body.get('anchor_uuid') else order[:len(body.get('path', []))+1]
            columns = set()
            for field in requested:
                columns.update(definitions[field].get('components') or [field])
            # One streaming read, not one SQL lookup per epoch. Retain only the
            # current navigation columns, never the full epoch×field matrix.
            values = dict(index.values(ids=[row['epoch_uuid'] for row in rows], fields=sorted(columns)).items()) if columns else {}
        binding = service.binding(protocol) if protocol else None
        revision = selection_revision(service, protocol, predicate, filters, order, rows, binding, annotation_scope=annotation_scope)
        return rows, catalog, values, definitions, order, revision

    def page(self, body):
        if not isinstance(body, dict) or set(body) - {'protocol_uuid','predicate','filters','splits','path','offset','limit','revision','anchor_uuid'}:
            raise ValueError('Malformed tree page request or unsupported fields')
        limit, offset = body.get('limit', 80), body.get('offset', 0)
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 10_000_000:
            raise ValueError('Tree pages require limit 1–100 and a nonnegative bounded offset')
        path = body.get('path', [])
        if not isinstance(path, list) or len(path) > 8 or any(not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key) for key in path):
            raise ValueError('Tree path must contain at most eight opaque branch keys')
        expected = body.get('revision')
        if expected is not None and (not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected)):
            raise ValueError('Malformed tree revision')
        if (path or offset) and expected is None:
            raise ValueError('A tree revision is required for continuation pages')
        anchor = _uuid(body['anchor_uuid']) if 'anchor_uuid' in body else None
        if anchor and (path or offset):
            raise ValueError('An epoch locator cannot also specify a path or offset')
        rows, catalog, values, definitions, order, revision = self._scope(body)
        if expected is not None and expected != revision:
            raise StaleTreePage('Tree metadata or membership changed; reload the root before continuing')
        if len(path) > len(order):
            raise ValueError('Tree path exceeds the selected grouping depth')
        root_summary = _summary(rows)
        total_epochs = len(rows)
        levels = [{'field':field,'label':definitions[field]['label'],
                   **({'components':definitions[field]['components']} if definitions[field].get('components') else {})}
                  for field in order]

        def datum(row, field):
            current = values[row['epoch_uuid']]
            parts = definitions[field].get('components')
            return (True, joint_value(current, parts)) if parts else (field in current, current.get(field))

        def key_for(row, field):
            present, value = datum(row, field)
            return checksum({'field':field, 'present':present, **({'value':value} if present else {})})

        def groups(current, depth):
            field = order[depth]
            buckets = {}
            for row in current:
                present, value = datum(row, field)
                canonical = value_key(value) if present else None
                bucket = buckets.setdefault((present, canonical), {'row':row, 'value':value,
                    'missing':not present, 'rows':[]})
                bucket['rows'].append(row)
            def sorting(bucket):
                if field == 'block' and not bucket['missing']:
                    row = bucket['row']; stamp = row.get('block_start_time')
                    # Same source chronology as the full-tree renderer.
                    from workspace_service import _date
                    return (0, (_date(stamp) + stamp[11:]) if stamp else '', str(bucket['value']))
                return (1,) if bucket['missing'] else (0, field_value_order(field,bucket['value']))
            return sorted(buckets.values(), key=sorting)

        def branch_records(buckets, depth, parent_path):
            if not buckets:
                return []
            field = order[depth]
            representatives = [bucket['row'] for bucket in buckets]
            # Reuse the established human labels, but render only one epoch per
            # requested branch, never all members or all descendant levels.
            scoped_values = {row['epoch_uuid']: dict(values[row['epoch_uuid']]) for row in representatives}
            if definitions[field].get('components'):
                for current in scoped_values.values():
                    current[field] = joint_value(current,definitions[field]['components'])
            rendered = self.service._render_tree(representatives,
                {**catalog, 'fields':list(definitions.values())}, scoped_values, field)
            labels = {checksum({'field':field,'present':not child.get('missing',False),
                      **({'value':child['value']} if not child.get('missing',False) else {})}):child
                      for child in rendered.get('children',[])}
            result = []
            for bucket in buckets:
                key = key_for(bucket['row'],field)
                child = labels[key]
                result.append({'key':key,'label':child['label'],'value':bucket['value'],
                    'missing':bucket['missing'], 'path':[*parent_path,key],
                    'has_children':depth + 1 < len(order), **_summary(bucket['rows']),
                    **{name:child[name] for name in ('components','has_missing_components','start_time') if name in child}})
            return result

        ancestors = []
        if anchor:
            candidate = next((row for row in rows if row['epoch_uuid'] == anchor), None)
            if candidate is None:
                raise KeyError('Epoch is outside this tree selection')
            path = [key_for(candidate,field) for field in order]
        selected = rows
        for depth, key in enumerate(path):
            buckets = groups(selected,depth)
            found = next(((index,bucket) for index,bucket in enumerate(buckets) if key_for(bucket['row'],order[depth]) == key),None)
            current = found[1] if found else None
            if current is None:
                raise KeyError('Tree branch is outside this selection')
            ancestors.extend([{**item,'parent_offset':found[0] // limit * limit} for item in branch_records([current],depth,path[:depth])])
            selected = current['rows']
        depth = len(path)
        payload = {'revision':revision,'split_order':order,'levels':levels,'total_epochs':total_epochs,
            'count':root_summary['count'],'cells':root_summary['cells'],'duration_seconds':root_summary['duration_seconds'],
            'matlab_command':matlab_tree_command(order),
            'path':path,'depth':depth,'offset':offset,'limit':limit,'branches':[],'epochs':[],
            'selection':_summary(selected), 'ancestors':ancestors,
            'source_scope_revision':self.service.source_scope()['revision'] if body.get('protocol_uuid') is None else None}
        if depth < len(order):
            buckets = groups(selected,depth)
            payload.update(kind='branches',total=len(buckets),
                branches=branch_records(buckets[offset:offset+limit],depth,path))
        else:
            selected = sorted(selected,key=_chronology)
            if anchor:
                index = next(index for index,row in enumerate(selected) if row['epoch_uuid']==anchor)
                offset = (index // limit) * limit
                payload['offset'] = offset
                payload['anchor'] = {'epoch_uuid':anchor,'path':path,'index':index,'offset':offset}
            shown=selected[offset:offset+limit]
            payload.update(kind='epochs',total=len(selected),epochs=[_epoch(row) for row in shown])
            shared=getattr(self.service,'shared_annotations',None)
            if shared:
                annotations=shared.for_epochs(shown)
                for row in payload['epochs']:row['annotations']=annotations[row['epoch_uuid']]
        payload['has_more'] = offset + limit < payload['total']
        return payload


def register_tree_page_routes(app, service, db_lock, registration_locks):
    from flask import jsonify, request
    pager = TreePages(service)
    app.extensions['workspace_tree_pages'] = pager

    @app.post('/api/tree-pages')
    def tree_page():
        if request.args or (request.content_length is not None and request.content_length > 65536):
            raise ValueError('Tree page requests require a JSON body of at most 64 KiB and no URL parameters')
        try:
            body = request.get_json()
        except (RecursionError, OverflowError) as error:
            raise ValueError('Tree page JSON nesting or numeric value exceeds limits') from error
        with db_lock, registration_locks():
            try:
                return jsonify(pager.page(body))
            except StaleTreePage as error:
                return jsonify(error=str(error),code='stale_tree_revision'),409
