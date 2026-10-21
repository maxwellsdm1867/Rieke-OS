"""Bounded project metadata lookup. No waveform reads, SQL text, or mutations."""
from __future__ import annotations

from bisect import bisect_left
import json
from pathlib import Path
import re
from urllib.parse import unquote

from disco.navigation.predicates import equal, literal


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _cell_rows(service):
    """First registered row per cell, reused while the published rows are unchanged.

    Refresh replaces the row mapping and publication. Each hit still checks every
    cached row's live cell link; any mismatch rebuilds from all rows.
    """
    key = (id(service.rows), len(service.rows), getattr(service, '_explore_publication', None))
    cached = getattr(service, '_search_cell_rows', None)
    if (cached is None or cached[0] != key
            or any(service.rows.get(row['epoch_uuid']) is not row or row['cell_uuid'] != identity
                   for identity, row in cached[1])):
        cells = {}
        for row in service.rows.values():
            cells.setdefault(row['cell_uuid'], row)
        cached = service._search_cell_rows = (key, sorted(cells.items()))
    return cached[1]


def _cell_prefix_hits(service, prefix, limit):
    """Bounded UUID range in the prepared immutable registered-cell publication."""
    from disco.navigation.tag_predicates import prepare_publication
    publication = prepare_publication(service)
    if publication is None or not publication.lowercase_cells:
        return None
    identities = publication.cell_identities
    first = bisect_left(identities, prefix)
    last = bisect_left(identities, prefix + '\uffff')
    rows = [(identity, publication.rows[publication.cell_epochs(identity)[0]])
            for identity in identities[first:min(last, first + limit)]]
    return rows, last - first


def _epoch_prefix_hits(service, prefix, limit):
    """First ``limit`` epochs by UUID with this lowercase prefix plus the exact total.

    Native generations answer with one range probe on the sealed index's unique
    epoch_uuid index, not a sort of every row. Rows still come from the published
    mapping; a missing method, a mismatched row count, non-lowercase identities
    or an identity the mapping lacks returns None and the caller scans instead.
    """
    index = getattr(service, 'disk_index', None)
    probe = getattr(index, 'epoch_prefix', None)
    if probe is None or getattr(index, '_epoch_count', None) != len(service.rows):
        return None
    found = probe(prefix, limit)
    if found is None:
        return None
    identities, total = found
    rows = [(identity, service.rows.get(identity)) for identity in identities]
    if any(row is None or row.get('epoch_uuid') != identity for identity, row in rows):
        return None
    return rows, total


def search_workspace(service, query, limit=20, *, field=None, operator='eq', value=None, membership_lookup=None):
    if not isinstance(query, str) or len(query) > 512:
        raise ValueError('Search text must contain at most 512 characters')
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('Search limit must be 1–50')
    query = query.strip()
    service._ready()
    scope = service.source_scope()
    active = set(scope['active_source_revisions'])
    sources = {source['source_sha256']: source for source in service.sources}
    results = []
    unlisted = 0  # Counted prefix matches beyond the materialized rows.
    normalized = query.casefold()
    uuid_query = bool(re.fullmatch(r'[0-9a-fA-F-]{8,36}', query))

    def context(row):
        source = sources.get(row['source_sha256'], {})
        return {'cell_uuid': row['cell_uuid'], 'date': row['date'],
                'source_sha256': row['source_sha256'],
                'source_filename': source.get('filename') or Path(source.get('source_path', '')).name,
                'acquisition_protocol': row['protocol_name'],
                'query_excluded': row['source_sha256'] not in active}

    if field is None and len(query) >= 2:
        cell_probe = _cell_prefix_hits(service, normalized, limit) if uuid_query else None
        if cell_probe is None:
            cell_rows = _cell_rows(service)
        else:
            cell_rows, cell_total = cell_probe
            unlisted += cell_total - len(cell_rows)
        for identity, row in cell_rows:
            identity_match = uuid_query and identity.lower().startswith(normalized)
            label_match = not uuid_query and normalized in f"{row['date']} {row['cell_label']} {row['cell_type']}".casefold()
            if identity_match or label_match:
                results.append({'kind': 'cell', 'id': identity, 'label': row['cell_label'],
                    'detail': f"{row['date']} · {row['cell_type']}", **context(row)})
        # Numeric ordinals are local to their recording/cell, never global IDs.
        if uuid_query:
            # Matches beyond the first ``limit`` are counted, never materialized.
            probed = _epoch_prefix_hits(service, normalized, limit)
            if probed is None:
                epoch_rows = [(identity, row) for identity, row in sorted(service.rows.items())
                              if identity.lower().startswith(normalized)]
            else:
                epoch_rows, epoch_total = probed
                unlisted += epoch_total - len(epoch_rows)
            for identity, row in epoch_rows:
                results.append({'kind': 'epoch', 'id': identity, 'epoch_uuid': identity,
                    'label': f"Epoch {row.get('epoch_number', '')} · {row['cell_label']}",
                    'detail': f"{row['date']} · {row['protocol_name'].rsplit('.', 1)[-1]}", **context(row)})
        # Exact UUID wins over prefixes; ambiguity is shown as separate rows.
        # An exact epoch UUID sorts first among its prefix matches.
        exact = [item for item in results if item['id'].lower() == normalized]
        if exact:
            results = exact
            unlisted = 0
        if uuid_query:
            memberships = {}
            shown = [item for item in results[:limit] if item['kind'] == 'epoch']
            prepared = membership_lookup([item['epoch_uuid'] for item in shown]) if shown and membership_lookup else None
            if prepared is not None:
                memberships = {identity:[{'protocol_uuid':protocol,
                    'name':service.protocols[protocol]['definition']['name']} for protocol in protocols]
                    for identity,protocols in prepared.items()}
            # The service's shared read-only member set (one per publication and
            # binding revision/version); None keeps the query_result path.
            reader = getattr(service, 'query_members', None) if shown else None
            for protocol_id, workspace in (service.protocols.items() if shown and prepared is None else ()):
                members = reader(protocol_id) if reader is not None else None
                if members is None:
                    members = {item['uuid'] for item in service.query_result(protocol_id)['epochs']}
                for item in shown:
                    if item['epoch_uuid'] in members:
                        memberships.setdefault(item['epoch_uuid'], []).append({'protocol_uuid': protocol_id,
                            'name': workspace['definition']['name']})
            for item in results:
                if item['kind'] == 'epoch':
                    item['protocols'] = memberships.get(item['epoch_uuid'], [])
                    item['protocol_uuid'] = item['protocols'][0]['protocol_uuid'] if item['protocols'] else None
            if not query.isdigit():
                return {'query': query, 'results': results[:limit], 'total': len(results) + unlisted, 'limit': limit,
                        'identity_ambiguous': len(results) + unlisted > 1, 'scope': 'registered_project_sources',
                        'source_scope_revision': scope['revision']}
    if not query and field is None:
        return {'query': query, 'results': [], 'total': 0, 'limit': limit}
    catalog = service.predicate_fields()
    # Convenient exact syntax; JSON gives numbers/pairs/booleans their types.
    pair = re.fullmatch(r'(.+?)\s*(>=|<=|!=|=|>|<)\s*(.*)', query)
    if field is None and pair:
        field_text, symbol, value_text = pair.groups()
        requested = field_text.strip().casefold()
        aliases = [item for item in catalog['fields']
                   if requested in {item['id'].casefold(), item['label'].casefold(),
                       unquote(item['id'].rsplit('/', 1)[-1]).replace('~1','/').replace('~0','~').casefold()}]
        exact = [item for item in aliases if item['id'].casefold() == requested]
        canonical = [item for item in aliases if item['id'].startswith('parameters/') and item['id'].count('/') == 1]
        # A source parameter also appears in block/epoch provenance copies.
        # Unqualified names refer to the effective merged epoch parameters;
        # explicit full IDs always select exactly the requested provenance path.
        if len(exact) == 1:
            aliases = exact
        elif len(canonical) == 1:
            aliases = canonical
        if not aliases:
            raise ValueError('No recorded field matches that name. Search its name first, or use its exact field ID.')
        operator = {'=':'eq','!=':'ne','>':'gt','>=':'gte','<':'lt','<=':'lte'}[symbol]
        try:
            value = json.loads(value_text.strip())
        except json.JSONDecodeError:
            if value_text.strip().startswith(('[', '{', '"')):
                raise ValueError('Use valid JSON for arrays, objects, and quoted strings')
            value = value_text.strip()
        if len(aliases) > 1:
            choices = []
            for item in aliases:
                try:
                    response = search_workspace(service, '', limit, field=item['id'], operator=operator, value=value)
                except ValueError:
                    continue  # Different source levels may expose different recorded types.
                choices.extend(response['results'])
            if not choices:
                raise ValueError('Matching fields do not support that typed value; use an exact field ID and its recorded type.')
            return {'query': query, 'results': choices[:limit], 'total': len(choices), 'limit': limit,
                    'field_ambiguous': True, 'scope': 'active_source_queries',
                    'source_scope_revision': scope['revision']}
        field = aliases[0]['id']
    if field is not None:
        predicate = {'field': field, 'operator': operator}
        if operator not in {'exists', 'missing', 'is_null'}:
            predicate['value'] = value
        predicate, matched, _ = service.match_predicate(predicate)
        count = len(matched)
        definition = next(item for item in catalog['fields'] if item['id'] == field)
        result = {'kind': 'value', 'id': field + ':' + _json(predicate), 'label': definition['label'],
                  'detail': f'{operator} {_json(value)} · {count} matching epochs · {field}',
                  'field_id': field, 'predicate': predicate, 'count': count}
        return {'query': query, 'results': [result], 'total': 1, 'limit': limit,
                'scope': 'active_source_queries', 'source_scope_revision': scope['revision']}
    try:
        typed_value = json.loads(query)
        literal(typed_value)
        typed = True
    except (ValueError, TypeError):
        typed = False
        typed_value = None
    examples_only = False
    for definition in catalog['fields']:
        identity, label = definition['id'], definition['label']
        if normalized in f'{identity} {label}'.casefold():
            results.append({'kind': 'field', 'id': identity, 'label': label, 'detail': identity,
                            'field_id': identity, 'predicate': {'field': identity, 'operator': 'exists'}})
        examples_only |= bool(definition.get('choices_truncated'))
        for choice in definition.get('choices', []):
            current = choice['value']
            encoded = _json(current)
            match = equal(current, typed_value) if typed else normalized in encoded.casefold()
            if not match:
                continue
            try:
                literal(current)
            except ValueError:
                continue  # Do not round oversized integer identities for browser predicates.
            results.append({'kind': 'value', 'id': identity + ':' + encoded, 'label': f'{label} = {encoded}',
                'detail': f"{choice['count']} matching epochs · {identity}", 'field_id': identity,
                'predicate': {'field': identity, 'operator': 'eq', 'value': current}, 'count': choice['count']})
    return {'query': query, 'results': results[:limit], 'total': len(results) + unlisted, 'limit': limit,
            'value_examples_only': examples_only, 'scope': 'project_identities_and_active_metadata',
            'source_scope_revision': scope['revision']}


def register_search_routes(app, service, db_lock, *, membership_lookup=None):
    from flask import jsonify, request

    @app.get('/api/search')
    def workspace_search():
        if set(request.args) - {'q', 'limit', 'field', 'operator', 'value'} or any(
                len(request.args.getlist(key)) != 1 for key in request.args):
            raise ValueError('Unknown or repeated search option')
        if 'field' in request.args and 'value' not in request.args and request.args.get('operator', 'eq') not in {'exists','missing','is_null'}:
            raise ValueError('Typed field searches require an explicit JSON value')
        value = json.loads(request.args['value']) if 'value' in request.args else None
        def respond():
            from disco.navigation.publication_changes import PreparationRequired
            try:
                return jsonify(search_workspace(service, request.args.get('q', ''), int(request.args.get('limit', 20)),
                    field=request.args.get('field'), operator=request.args.get('operator', 'eq'), value=value,
                    membership_lookup=membership_lookup))
            except PreparationRequired as error:
                return jsonify(error='Search metadata is being prepared. Retry search shortly.',code='metadata_preparing',
                    preparation={'status':'pending','resource':'overview','reason':str(error)}),503
        # One schema attestation per response; scope generations stay live.
        contract = app.extensions.get('read_contract')
        with db_lock:
            if contract is None:
                return respond()
            with contract():
                return respond()
