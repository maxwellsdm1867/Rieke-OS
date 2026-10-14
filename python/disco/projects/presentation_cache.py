"""Disposable, bounded last-good display data. Never scientific authority.

The cache lives outside the project and carries only explicitly named overview
fields. Loading it opens neither the scientific database nor recordings. Every
consumer must keep it inert until the ordinary canonical overview succeeds.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import uuid

MAX_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 12 * 1024 * 1024
COUNTS = ('epochs', 'cells', 'exported', 'duration_seconds', 'reviewed', 'approved', 'unreviewed')


def _strings(value, keys):
    return {key: value[key] for key in keys
            if isinstance(value.get(key), str) and len(value[key]) <= 4096}


def _numbers(value, keys):
    return {key: value[key] for key in keys if type(value.get(key)) in (int, float)
            and 0 <= value[key] <= 2**53 - 1 and math.isfinite(value[key])}


def display_overview(value):
    """Positive field allowlist, also applied on reads of older cache bytes."""
    if not isinstance(value, dict):
        raise ValueError('Overview must be an object')
    result = {'project': _strings(value.get('project') or {}, ('project_uuid', 'name', 'display_name')),
              'catalog': _strings(value.get('catalog') or {}, ('database', 'adapter')),
              'counts': _numbers(value.get('counts') or {}, COUNTS)}
    specs = {
        'cells': (('cell_uuid', 'uuid', 'label', 'name', 'cell_type', 'type', 'date'),
                  ('epochs', 'epoch_count', 'duration_seconds'), 20000),
        'protocols': (('protocol_uuid', 'name', 'acquisition_protocol'), ('epoch_count', 'cell_count'), 5000),
        'sources': (('source_sha256', 'filename', 'imported_at'), (), 5000),
        'events': (('action', 'status', 'occurred_at', 'at'), (), 5),
    }
    for collection, (strings, numbers, limit) in specs.items():
        rows = value.get(collection) or []
        if not isinstance(rows, list) or (collection != 'events' and len(rows) > limit):
            raise ValueError('Overview exceeds display cache limits')
        result[collection] = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                raise ValueError('Invalid overview row')
            item = {**_strings(row, strings), **_numbers(row, numbers)}
            if collection == 'cells':
                rigs = row.get('recording_rigs')
                if isinstance(rigs, list) and len(rigs) <= 5000:
                    item['recording_rigs'] = [rig for rig in rigs if isinstance(rig, str) and len(rig) <= 4096]
                if type(row.get('recording_rig_missing')) is bool:
                    item['recording_rig_missing'] = row['recording_rig_missing']
                ids = row.get('protocol_uuids') or []
                if not isinstance(ids, list) or len(ids) > 5000:
                    raise ValueError('Invalid protocol identities')
                item['protocol_uuids'] = [key for key in ids if isinstance(key, str) and len(key) <= 128]
            if collection == 'protocols':
                item['counts'] = _numbers(row.get('counts') or {}, COUNTS)
                if isinstance(row.get('binding'), dict):
                    version = _numbers(row['binding'], ('version',))
                    if version:
                        item['binding'] = version
            result[collection].append(item)
    return result


def _identity(project_dir):
    root = Path(project_dir).resolve(strict=True)
    manifest = root / 'project.json'
    if manifest.is_symlink() or manifest.stat().st_size > 65536:
        raise ValueError('Invalid project identity')
    value = json.loads(manifest.read_text())
    if value.get('format') != 'recording-project' or value.get('version') != 1:
        raise ValueError('Invalid project identity')
    return str(root), str(uuid.UUID(value['project_uuid']))


def _path(identity, user_state):
    state = user_state or os.environ.get('RIEKE_DESKTOP_USER_STATE')
    if not state:
        return None  # Non-desktop API runs do not silently create a user cache.
    root = Path(state).resolve() / 'ui-presentation'
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return root / (key + '.sqlite')


def _connect(path, *, writing=False):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Cache links are not supported')
    if path.exists() and path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('Cache file exceeds limit')
    connection = sqlite3.connect(path.as_uri() + ('?mode=rwc' if writing else '?mode=ro'), uri=True, timeout=0.025)
    connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_BYTES + 65536)
    connection.execute('PRAGMA trusted_schema=OFF')
    return connection


def save_overview(project_dir, overview, *, user_state=None):
    """Best effort after a successful canonical read; failure never affects it."""
    try:
        identity = _identity(project_dir)
        path = _path(identity, user_state)
        if path is None:
            return False
        display = display_overview(overview)
        if display['project'].get('project_uuid') != identity[1]:
            return False
        envelope = dict(available=True, format='disco-project-presentation', version=1,
                        project_path=identity[0], project_uuid=identity[1], presentation_only=True,
                        observed_at=datetime.now(timezone.utc).isoformat(), overview=display)
        raw = json.dumps(envelope, separators=(',', ':'), allow_nan=False).encode()
        if len(raw) > MAX_BYTES:
            return False
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(_connect(path, writing=True)) as connection, connection:
            connection.execute('PRAGMA journal_mode=DELETE')
            page_size = connection.execute('PRAGMA page_size').fetchone()[0]
            connection.execute(f'PRAGMA max_page_count={MAX_FILE_BYTES // page_size}')
            connection.execute('CREATE TABLE IF NOT EXISTS overview (id INTEGER PRIMARY KEY CHECK(id=1), payload BLOB NOT NULL, checksum TEXT NOT NULL)')
            connection.execute('INSERT OR REPLACE INTO overview VALUES (1, ?, ?)', (raw, hashlib.sha256(raw).hexdigest()))
        return True
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, sqlite3.Error):
        return False


def load_overview(project_dir, *, user_state=None, expected_uuid=None):
    """Return display-only bytes or a miss, without creating any file."""
    try:
        identity = _identity(project_dir)
        if expected_uuid is not None and identity[1] != expected_uuid:
            return {'available': False}
        path = _path(identity, user_state)
        if path is None or not path.is_file():
            return {'available': False}
        with closing(_connect(path)) as connection:
            row = connection.execute('SELECT payload, checksum FROM overview WHERE id=1').fetchone()
        if row is None or not isinstance(row[0], bytes) or len(row[0]) > MAX_BYTES or hashlib.sha256(row[0]).hexdigest() != row[1]:
            return {'available': False}
        value = json.loads(row[0])
        if (value.get('format') != 'disco-project-presentation' or value.get('version') != 1
                or value.get('project_path') != identity[0] or value.get('project_uuid') != identity[1]
                or value.get('presentation_only') is not True):
            return {'available': False}
        display = display_overview(value['overview'])
        if display['project'].get('project_uuid') != identity[1]:
            return {'available': False}
        return dict(available=True, format='disco-project-presentation', version=1,
                    project_path=identity[0], project_uuid=identity[1], presentation_only=True,
                    observed_at=str(value.get('observed_at', ''))[:128], overview=display)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, sqlite3.Error):
        return {'available': False}
