"""Portable search shortcuts and protocol organization; device geometry stays local."""
from __future__ import annotations

import copy
import fcntl
import json
import os
from pathlib import Path
import tempfile
import uuid

FORMAT = 'rieke-project-preferences'
REFERENCE = 'protocols/ui-state/project-preferences.json'
FIELDS = {'recent_searches', 'protocol_shortcuts'}
MAX_BYTES = 1024 * 1024


def _uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('Preference identities must be normalized UUID strings')
    return value


def _predicate(value):
    from workspace_predicates import MAX_DEPTH, MAX_NODES, validate
    fields, count = set(), 0
    def collect(node, depth=0):
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH or not isinstance(node, dict):
            raise ValueError('Saved search predicate exceeds its shape or size limits')
        if set(node) == {'not'}:
            collect(node['not'], depth + 1)
        elif set(node) in ({'all'}, {'any'}):
            children = node[next(iter(node))]
            if not isinstance(children, list):
                raise ValueError('Predicate groups require arrays')
            for child in children:
                collect(child, depth + 1)
        else:
            field = node.get('field')
            if not isinstance(field, str) or not field or len(field) > 2048:
                raise ValueError('Saved search field is invalid')
            fields.add(field)
    collect(value)
    # A previously valid field can disappear after archiving a source. Preserve
    # the recipe's structural validity here; running it still checks the catalog.
    return validate(value, {'fields': [{'id': field} for field in fields]}, {})


def validate_field(field, value):
    if field == 'protocol_shortcuts':
        if not isinstance(value, dict) or len(value) > 2000:
            raise ValueError('Use at most 2000 protocol shortcuts')
        for identity, preference in value.items():
            _uuid(identity)
            if (not isinstance(preference, dict) or set(preference) != {'section', 'rank'}
                    or not isinstance(preference['section'], str) or preference['section'] not in {'pinned', 'main', 'support'}
                    or type(preference['rank']) is not int or not 0 <= preference['rank'] <= 2000):
                raise ValueError('Protocol shortcuts require a known section and integer rank')
    elif field == 'recent_searches':
        if not isinstance(value, list) or len(value) > 100:
            raise ValueError('Use at most 100 recent search shortcuts')
        seen = set()
        for entry in value:
            if (not isinstance(entry, dict)
                    or set(entry) - {'id', 'name', 'predicate', 'splits', 'matched_count', 'cell_count', 'pinned', 'lastRunAt'}
                    or not {'id', 'predicate', 'splits', 'pinned'} <= set(entry)
                    or not isinstance(entry['id'], str) or not entry['id'] or len(entry['id']) > 65536
                    or entry['id'] in seen or type(entry['pinned']) is not bool
                    or not isinstance(entry['splits'], str) or len(entry['splits']) > 4096):
                raise ValueError('Saved search shortcut shape or identity is invalid')
            seen.add(entry['id'])
            _predicate(entry['predicate'])
            for key, maximum in (('name', 255), ('lastRunAt', 64)):
                if key in entry and entry[key] is not None and (not isinstance(entry[key], str) or len(entry[key]) > maximum):
                    raise ValueError('Saved search label or timestamp is invalid')
            for key in ('matched_count', 'cell_count'):
                if key in entry and entry[key] is not None and (type(entry[key]) is not int or entry[key] < 0):
                    raise ValueError('Saved search counts must be nonnegative integers')
    else:
        raise ValueError('Unknown project preference field')
    if len(json.dumps(value, allow_nan=False).encode()) > MAX_BYTES:
        raise ValueError('Project preference field exceeds 1 MiB')
    return copy.deepcopy(value)


class PreferenceConflict(ValueError):
    pass


class ProjectPreferences:
    def __init__(self, directory, project_uuid):
        self.root = Path(directory).resolve()
        self.identity = _uuid(project_uuid)

    def _path(self):
        current = self.root
        for part in Path(REFERENCE).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError('Project preference files cannot be symbolic links')
        return current

    def read(self):
        path = self._path()
        if not path.exists():
            return {'format': FORMAT, 'version': 1, 'project_uuid': self.identity,
                    'revisions': {field: 0 for field in FIELDS}, 'state': {}}
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError('Project preference file is invalid or exceeds 1 MiB')
        value = json.loads(path.read_text())
        if (not isinstance(value, dict) or set(value) != {'format', 'version', 'project_uuid', 'revisions', 'state'}
                or value['format'] != FORMAT or type(value['version']) is not int or value['version'] != 1
                or value['project_uuid'] != self.identity or not isinstance(value['state'], dict)
                or set(value['state']) - FIELDS or not isinstance(value['revisions'], dict)
                or set(value['revisions']) != FIELDS
                or any(type(revision) is not int or revision < 0 for revision in value['revisions'].values())):
            raise ValueError('Unsupported project preference file or identity')
        for field, state in value['state'].items():
            validate_field(field, state)
        return value

    def save(self, field, value, expected_revision):
        value = validate_field(field, value)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('Preference expected_revision must be a nonnegative integer')
        lock_path = self.root / '.project-preferences.lock'
        if lock_path.is_symlink():
            raise ValueError('Project preference lock cannot be a symbolic link')
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = self.read()
            if current['revisions'][field] != expected_revision:
                raise PreferenceConflict('Project preferences changed; reload before saving.')
            if current['state'].get(field) == value:
                return current
            current['state'][field] = value
            current['revisions'][field] += 1
            content = json.dumps(current, allow_nan=False, indent=2, sort_keys=True).encode() + b'\n'
            if len(content) > MAX_BYTES:
                raise ValueError('Project preference file exceeds 1 MiB')
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.preferences-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return current


def register_project_preference_routes(app, directory, project_uuid, db_lock):
    from flask import jsonify, request
    preferences = ProjectPreferences(directory, project_uuid)
    app.extensions['project_preferences'] = preferences

    @app.get('/api/project-preferences')
    def read_preferences():
        if request.args:
            return jsonify(error='Project preferences do not accept query parameters.'), 400
        try:
            with db_lock:
                return jsonify(preferences.read())
        except (ValueError, OSError) as error:
            return jsonify(error=str(error)), 400

    @app.put('/api/project-preferences')
    def save_preferences():
        if request.content_length is not None and request.content_length > MAX_BYTES:
            return jsonify(error='Project preference request exceeds 1 MiB.'), 400
        body = request.get_json(silent=True)
        if request.args or not isinstance(body, dict) or set(body) != {'field', 'value', 'expected_revision'}:
            return jsonify(error='Preference saves require field, value and expected_revision.'), 400
        try:
            with db_lock:
                return jsonify(preferences.save(body['field'], body['value'], body['expected_revision']))
        except PreferenceConflict as error:
            return jsonify(error=str(error)), 409
        except (ValueError, OSError, TypeError) as error:
            return jsonify(error=str(error)), 400
