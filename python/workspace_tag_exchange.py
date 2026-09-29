"""Explicit, additive authored-tag interchange. Never imports selection masks."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from collections import defaultdict

FORMAT = 'rieke-tag-exchange'
MAX_BYTES = 8 * 1024 * 1024
MAX_OPERATIONS = 2000


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError('Tag exchange must contain bounded, finite JSON values') from error


def identity(value):
    if not isinstance(value, str):
        raise ValueError('Tag targets and authors require exact UUIDs')
    try:
        result = str(uuid.UUID(value))
    except (ValueError, AttributeError) as error:
        raise ValueError('Tag targets and authors require exact UUIDs') from error
    if result != value:
        raise ValueError('Tag UUIDs must use canonical lowercase form')
    return result


def _text(value, label, limit):
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(f'Invalid {label}')
    return value


def normalize_document(document, service):
    """Resolve portable or Samarjit nested JSON by exact registered identity."""
    if len(canonical(document).encode()) > MAX_BYTES:
        raise ValueError('Tag exchange exceeds 8 MiB')
    registry = {'epoch': set(service.rows), 'cell': set(service.cells)}
    warnings = []
    cell_sources = defaultdict(set)
    for row in service.rows.values():
        cell_sources[row['cell_uuid']].add(row['source_sha256'])
    if not isinstance(document, dict):
        raise ValueError('Tag exchange must be a JSON object')
    if document.get('format') == FORMAT:
        if type(document.get('version')) is not int or document.get('version') != 1 or not isinstance(document.get('entries'), list):
            raise ValueError('Unsupported tag exchange version or entries')
        entries = document['entries']
        origin = document.get('project_uuid')
        if origin is not None:
            identity(origin)
            if origin != service.project['project_uuid']:
                warnings.append('Origin project differs; only exact registered acquisition UUIDs are matched.')
    elif 'format' in document:
        raise ValueError('Unsupported tag exchange format; UGM is a selection mask, not authored tags')
    else:
        entries = []
        visited = set()
        def walk(nodes, depth=0):
            if depth > 16 or not isinstance(nodes, dict):
                raise ValueError('Malformed Samarjit tag hierarchy')
            for key, node in nodes.items():
                if key == 'tags':
                    if depth == 0 and node:
                        raise ValueError('Root-level legacy tags have no target UUID')
                    continue
                target = identity(key)
                if target in visited or not isinstance(node, dict):
                    raise ValueError('Duplicate identity or malformed Samarjit tag node')
                visited.add(target)
                pairs = node.get('tags', [])
                if not isinstance(pairs, list):
                    raise ValueError('Samarjit tags must be [author, tag] pairs')
                if pairs:
                    kinds = [kind for kind, ids in registry.items() if target in ids]
                    if len(kinds) != 1:
                        raise ValueError('Tagged Samarjit UUID is not a registered cell or epoch; unsupported levels are not discarded')
                    tags = []
                    for pair in pairs:
                        if not isinstance(pair, list) or len(pair) != 2:
                            raise ValueError('Samarjit tags must be [author, tag] pairs')
                        author = _text(pair[0], 'claimed author name', 120)
                        tags.append({'tag': pair[1], 'author_name': author,
                                     'profile_uuid': str(uuid.uuid5(uuid.NAMESPACE_URL, 'rieke:samarjit:claimed-author:' + author))})
                    entries.append({'target_kind': kinds[0], 'target_uuid': target, 'tags': tags})
                walk(node, depth + 1)
        walk(document)
        warnings.append('Samarjit author names are imported claims, not verified identities. Existing tags are retained.')
    normalized, seen, profiles = [], set(), {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('target_kind'), str) or entry['target_kind'] not in registry:
            raise ValueError('Tag target kind must be cell or epoch')
        kind, target = entry['target_kind'], identity(entry.get('target_uuid'))
        if target not in registry[kind] or (kind, target) in seen:
            raise ValueError('Unknown or duplicate tag target UUID')
        seen.add((kind, target))
        expected_sources = {service.rows[target]['source_sha256']} if kind == 'epoch' else cell_sources[target]
        if entry.get('source_sha256') is not None and (not isinstance(entry['source_sha256'], str) or entry['source_sha256'] not in expected_sources):
            raise ValueError('Tag target source SHA256 differs from the registered acquisition')
        if not isinstance(entry.get('tags'), list):
            raise ValueError('Target tags must be a list')
        tags, tag_keys = [], set()
        for chip in entry['tags']:
            if not isinstance(chip, dict):
                raise ValueError('Each tag requires text and an explicit author')
            profile = identity(chip.get('profile_uuid'))
            author = _text(chip.get('author_name'), 'author name', 120)
            tag = _text(chip.get('tag'), 'tag', 255)
            if profile in profiles and profiles[profile] != author:
                raise ValueError('One author UUID has conflicting names')
            profiles[profile] = author
            if (profile, tag) in tag_keys:
                raise ValueError('Duplicate authored tag')
            tag_keys.add((profile, tag))
            tags.append({'tag': tag, 'profile_uuid': profile, 'author_name': author})
        normalized.append({'target_kind': kind, 'target_uuid': target,
                           'tags': sorted(tags, key=lambda tag: (tag['profile_uuid'], tag['tag']))})
    normalized.sort(key=lambda entry: (entry['target_kind'], entry['target_uuid']))
    if len({(entry['target_kind'], entry['target_uuid'], tag['profile_uuid'])
            for entry in normalized for tag in entry['tags']}) > MAX_OPERATIONS:
        raise ValueError('Tag exchange exceeds 2000 author-target operations; split the package')
    if len(profiles) > 100:
        raise ValueError('Tag exchange exceeds 100 author profiles')
    for entry in normalized:
        counts = defaultdict(int)
        for tag in entry['tags']:
            counts[tag['profile_uuid']] += 1
        if any(count > 100 for count in counts.values()):
            raise ValueError('Each target/author may have at most 100 tags')
    return {'format': FORMAT, 'version': 1, 'project_uuid': service.project['project_uuid'], 'entries': normalized}, profiles, warnings


def _read_targets(store, kind, ids):
    result = {}
    for start in range(0, len(ids), 1000):
        result.update(store.read_targets(kind, ids[start:start+1000]))
    return result


def preview_import(document, service, store):
    normalized, profiles, warnings = normalize_document(document, service)
    existing = {kind: _read_targets(store, kind, [entry['target_uuid'] for entry in normalized['entries'] if entry['target_kind'] == kind])
                for kind in ('cell', 'epoch')}
    known_profiles = {p['profile_uuid']: p['display_name'] for p in store.list_profiles()['profiles']}
    if any(key in known_profiles and known_profiles[key] != name for key, name in profiles.items()):
        raise ValueError('Author UUID has another registered name; explicitly reconcile the author before import')
    operations, additions, unchanged = [], 0, 0
    evidence = []
    for entry in normalized['entries']:
        target, kind = entry['target_uuid'], entry['target_kind']
        current = existing[kind].get(target, {})
        present = {(tag['profile_uuid'], tag['tag']) for tag in current.get('tags', [])}
        grouped = defaultdict(list)
        for tag in entry['tags']:
            grouped[tag['profile_uuid']].append(tag['tag'])
        for profile, tags in sorted(grouped.items()):
            delta = [tag for tag in tags if (profile, tag) not in present]
            if len({tag for author, tag in present if author == profile} | set(tags)) > 100:
                raise ValueError('Import would exceed 100 tags for a target/author')
            additions += len(delta)
            unchanged += len(tags) - len(delta)
            revision = current.get('revisions', {}).get(profile, 0)
            evidence.append([kind, target, profile, revision, sorted(tag for author, tag in present if author == profile)])
            if delta:
                operations.append({'target_kind': kind, 'target_uuid': target, 'profile_uuid': profile,
                                   'tags_add': delta, 'tags_remove': [], 'expected_revision': revision})
    rows = service.rows
    cell_sources = defaultdict(set)
    for row in rows.values():
        cell_sources[row['cell_uuid']].add(row['source_sha256'])
    source_evidence = sorted((entry['target_kind'], entry['target_uuid'],
        rows[entry['target_uuid']]['source_sha256'] if entry['target_kind'] == 'epoch' else
        sorted(cell_sources[entry['target_uuid']]))
        for entry in normalized['entries'])
    token = hashlib.sha256(canonical([normalized, evidence, source_evidence]).encode()).hexdigest()
    return {'preview_token': token, 'entries': normalized['entries'], 'operations': operations,
            'addition_count': additions, 'unchanged_count': unchanged, 'target_count': len(normalized['entries']),
            'profiles': [{'profile_uuid': key, 'display_name': value} for key, value in sorted(profiles.items())],
            'warnings': warnings, 'mode': 'additive', 'project_uuid': service.project['project_uuid']}


def export_document(service, store, *, target_kind=None, target_uuid=None):
    if target_kind not in (None, 'cell', 'epoch') or target_uuid and target_kind is None:
        raise ValueError('Choose cell or epoch for a filtered tag export')
    entries = []
    for kind, registry in (('cell', service.cells), ('epoch', service.rows)):
        if target_kind and kind != target_kind:
            continue
        ids = [identity(target_uuid)] if target_uuid else sorted(registry)
        if set(ids) - registry.keys():
            raise ValueError('Tag export target is not registered in this project')
        for target, value in sorted(_read_targets(store, kind, ids).items()):
            tags = [{key: tag[key] for key in ('tag', 'profile_uuid', 'author_name')} for tag in value.get('tags', [])]
            # Empty entries authorize exact UUID targets for MATLAB edits.
            entries.append({'target_kind': kind, 'target_uuid': target,
                                'tags': sorted(tags, key=lambda tag: (tag['profile_uuid'], tag['tag']))})
    cell_sources = {}
    for row in service.rows.values():
        old = cell_sources.setdefault(row['cell_uuid'], row['source_sha256'])
        if old != row['source_sha256']:
            raise ValueError('Cell UUID occurs in multiple sources')
    for entry in entries:
        entry['source_sha256'] = service.rows[entry['target_uuid']]['source_sha256'] if entry['target_kind'] == 'epoch' else cell_sources[entry['target_uuid']]
    return {'format': FORMAT, 'version': 1, 'project_uuid': service.project['project_uuid'], 'entries': entries}


def register_tag_exchange_routes(app, service, annotations, db_lock):
    from flask import jsonify, request, Response
    def body():
        raw = request.stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Tag exchange exceeds 8 MiB')
        try:
            result = json.loads(raw)
        except (ValueError, RecursionError) as error:
            raise ValueError('Invalid tag exchange JSON') from error
        if not isinstance(result, dict) or 'document' not in result:
            raise ValueError('Expected a document object')
        return result

    @app.post('/api/annotations/import/preview')
    def tag_import_preview():
        content = body()
        with db_lock, annotations.lock():
            return jsonify(preview_import(content['document'], service, annotations))

    @app.post('/api/annotations/import/apply')
    def tag_import_apply():
        content = body()
        with db_lock, annotations.lock():
            preview = preview_import(content['document'], service, annotations)
            if content.get('preview_token') != preview['preview_token']:
                return jsonify(error='Tags or source scope changed; preview the import again'), 409
            selected_profile = content.get('profile_uuid')
            importer = next((p for p in annotations.list_profiles()['profiles'] if p['profile_uuid'] == selected_profile), None)
            if importer is None:
                raise ValueError('Select a registered importer profile')
            result = annotations.apply_batch(preview['operations'], actor=importer['display_name'], profiles=preview['profiles'],
                audit_context={'operation': 'tag_exchange_import', 'preview_sha256': preview['preview_token'],
                               'mode': 'additive', 'imported_author_identity': 'file_claim',
                               'importer_profile_uuid': importer['profile_uuid']}) if preview['operations'] else None
            return jsonify(applied=True, addition_count=preview['addition_count'], unchanged_count=preview['unchanged_count'], result=result)

    @app.get('/api/annotations/export')
    def tag_export():
        output_format = request.args.get('format', 'rieke')
        if output_format not in ('rieke', 'samarjit'):
            raise ValueError('Choose rieke or samarjit tag export')
        with db_lock, annotations.lock():
            document = export_document(service, annotations, target_kind=request.args.get('target_kind'), target_uuid=request.args.get('target_uuid'))
            if output_format == 'samarjit':
                document = samarjit_document(document, service)
        raw = canonical(document)
        if len(raw.encode()) > MAX_BYTES:
            return jsonify(error='Tag export exceeds 8 MiB; choose a specific target or smaller scope'), 413
        filename = 'samarjit-tags.json' if output_format == 'samarjit' else 'rieke-tags.json'
        return Response(raw, mimetype='application/json', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def samarjit_document(document, service):
    """Emit the actual experiment→animal→preparation→cell→group→block→epoch shape.

    Legacy JSON has author labels only. Refuse ambiguous duplicate labels rather
    than silently merge two independent profiles into a single legacy author.
    """
    requested = {(entry['target_kind'], entry['target_uuid']): entry for entry in document['entries']}
    names = {}
    for entry in document['entries']:
        for tag in entry['tags']:
            old = names.setdefault(tag['author_name'], tag['profile_uuid'])
            if old != tag['profile_uuid']:
                raise ValueError('Samarjit cannot distinguish profiles with identical author names; use portable Rieke JSON')
    output, found = {}, set()
    def traverse(node, level):
        levels = ('experiment', 'animal', 'preparation', 'cell', 'group', 'block', 'epoch')
        children = ('animals', 'preparations', 'cells', 'epoch_groups', 'epoch_blocks', 'epochs')
        key = identity(node['uuid']); target = (levels[level], key)
        entry = requested.get(target)
        result = {'tags': [[tag['author_name'], tag['tag']] for tag in entry['tags']] if entry else []}
        if entry is not None:
            found.add(target)
        if level < 6:
            for child in node.get(children[level], []):
                child_key, child_result = traverse(child, level + 1)
                if child_result is not None:
                    result[child_key] = child_result
        return key, result if entry is not None or len(result) > 1 else None
    required_sources = {row['source_sha256'] for row in service.rows.values()
                        if ('epoch', row['epoch_uuid']) in requested or ('cell', row['cell_uuid']) in requested}
    for source in sorted(required_sources):
        manifest = service.manifests.get(source)
        if not manifest or not manifest.get('metadata_path'):
            raise ValueError('Verified acquisition ancestry is unavailable; use portable Rieke JSON')
        path = Path(manifest['metadata_path']).resolve()
        if not path.is_relative_to(Path(service.project_dir).resolve() / 'imports'):
            raise ValueError('Source metadata path escapes registered imports')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest.get('metadata_sha256'):
            raise ValueError('Source metadata changed; refusing legacy tag export')
        key, result = traverse(json.loads(raw), 0)
        if result is not None:
            output[key] = result
    if found != set(requested):
        raise ValueError('Some tag targets do not match verified acquisition ancestry')
    return output


def frozen_annotation_entries(records):
    """Validate a frozen per-epoch annotation snapshot; deduplicate inherited cells.

    Old exports have no annotations key. Their protocol tags remain separate.
    """
    entries = {}
    for record in records:
        snapshot = record.get('annotations')
        if snapshot is None:
            continue
        if snapshot.get('epoch_uuid') != record['epoch_uuid'] or snapshot.get('cell_uuid') != record['cell_uuid']:
            raise ValueError('Frozen shared annotations have a different target identity')
        for kind, key, field in (('cell', record['cell_uuid'], 'cell_tags'), ('epoch', record['epoch_uuid'], 'epoch_tags')):
            chips = snapshot.get(field)
            revisions = snapshot.get('revisions', {}).get(kind)
            if not isinstance(chips, list) or not isinstance(revisions, dict):
                raise ValueError('Incomplete frozen annotation snapshot')
            seen = set()
            for chip in chips:
                if chip.get('target_kind') != kind or chip.get('target_uuid') != key:
                    raise ValueError('Frozen annotation target kind or UUID differs')
                author = identity(chip.get('profile_uuid'))
                _text(chip.get('author_name'), 'author name', 120)
                tag = _text(chip.get('tag'), 'tag', 255)
                revision = chip.get('revision')
                if type(revision) is not int or revision < 1 or revisions.get(author) != revision:
                    raise ValueError('Frozen annotation revision differs')
                if (author, tag) in seen:
                    raise ValueError('Duplicate frozen authored tag')
                seen.add((author, tag))
            for author, revision in revisions.items():
                identity(author)
                if type(revision) is not int or revision < 1:
                    raise ValueError('Invalid annotation revision')
            entry = {'target_kind': kind, 'target_uuid': identity(key), 'tags': chips, 'revisions': revisions}
            old = entries.setdefault((kind, key), entry)
            if canonical(old) != canonical(entry):
                raise ValueError('Conflicting cell annotation snapshots across exported epochs')
        if canonical(snapshot.get('effective_tags')) != canonical(snapshot['cell_tags'] + snapshot['epoch_tags']):
            raise ValueError('Effective annotations differ from exact cell and epoch tags')
    return list(entries.values())


def frozen_document(records, project_uuid):
    entries = {(entry['target_kind'], entry['target_uuid']): entry for entry in frozen_annotation_entries(records)}
    # Include every exact exported identity, even old/untagged records.
    for record in records:
        for kind in ('cell', 'epoch'):
            key = record[kind + '_uuid']
            entries.setdefault((kind, key), {'target_kind': kind, 'target_uuid': key, 'tags': []})
    source_ids = {(kind, record[kind + '_uuid']): record['source_sha256'] for record in records for kind in ('cell','epoch')}
    return {'format': FORMAT, 'version': 1, 'project_uuid': project_uuid,
            'entries': [{'target_kind': entry['target_kind'], 'target_uuid': entry['target_uuid'],
                         'source_sha256': source_ids[(entry['target_kind'], entry['target_uuid'])],
                         'tags': [{key: tag[key] for key in ('tag','profile_uuid','author_name')} for tag in entry['tags']]}
                        for _, entry in sorted(entries.items())]}
