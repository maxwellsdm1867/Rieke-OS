"""Recoverable current app state; no waveforms or action replay.

Verified changes update a compact SQLite mirror before save acknowledgment; a
small JSON pointer locates it. Full capture remains the fallback and old JSON /
SQLite snapshots remain readable. Restore is an explicit offline tool; sources
remain separate and must match. Frozen selections keep their explicit members.
"""
from __future__ import annotations
import argparse
from contextlib import closing
import fcntl
import datetime as dt
import hashlib
import json
import logging
import os
import secrets
import stat
from pathlib import Path
import sqlite3
import tempfile

TABLES = ('annotation_profile', 'shared_annotation', 'curation', 'protocol_workspace',
          'data_store_state', 'protocol_tree_layout', 'search_preset', 'search_preset_version',
          'protocol_binding', 'explorer_revision', 'dataset_revision', 'search_query_last_run')
FORMAT = 'rieke-app-state'


def encode(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def serialized(value):
    return json.dumps(value, default=encode, sort_keys=True, separators=(',', ':'), allow_nan=False)


def capture(project_dir, connection, *, include_tables=True, ordered=True):
    root = Path(project_dir).resolve()
    project = json.loads((root/'project.json').read_text())
    identity = project['project_uuid']
    protocols = {}
    for path in sorted((root/'protocols').glob('*.json')):
        if path.is_symlink():
            raise ValueError('Protocol snapshot cannot follow symbolic links')
        protocols[path.name] = json.loads(path.read_text())
    existing = {row[0] for row in connection.query(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='recording_workspace'").fetchall()}
    tables = {table: [] for table in TABLES}
    for table in TABLES if include_tables else ():
        if table not in existing:
            continue
        restriction, arguments = '', (identity,)
        if table == 'search_preset_version':
            if 'search_preset' not in existing:
                continue
            restriction = (' AND EXISTS (SELECT 1 FROM recording_workspace.search_preset AS current '
                'WHERE current.project_uuid=search_preset_version.project_uuid '
                'AND current.preset_uuid=search_preset_version.preset_uuid '
                'AND current.version=search_preset_version.version)')
        elif table == 'explorer_revision':
            revisions = {row['revision_uuid'] for row in tables.get('protocol_binding', [])}
            revisions.update(value.get('initial_revision_uuid') for value in protocols.values() if isinstance(value, dict))
            revisions.discard(None)
            if not revisions:
                continue
            revision_ids = sorted(revisions)
            restriction = ' AND revision_uuid IN (' + ','.join(['%s'] * len(revision_ids)) + ')'
            arguments += tuple(revision_ids)
        rows = connection.query(f'SELECT * FROM recording_workspace.`{table}` WHERE project_uuid=%s' + restriction,
                                args=arguments, as_dict=True).fetchall()
        json_fields = {row[0] for row in connection.query(
            f'SHOW COLUMNS FROM recording_workspace.`{table}`').fetchall() if row[1] == 'json'}
        tables[table] = [{key:_column_value(value, key in json_fields)
                          for key,value in dict(row).items()} for row in rows]
    # Only saved current query versions and active membership snapshots belong
    # in recovery state. Historical recipes/exports stay immutable in live SQL.
    versions = {row['preset_uuid']:row['version'] for row in tables.get('search_preset', [])}
    if 'search_preset_version' in tables:
        tables['search_preset_version'] = [row for row in tables['search_preset_version']
            if versions.get(row['preset_uuid']) == row['version']]
    revisions = {row['revision_uuid'] for row in tables.get('protocol_binding', [])}
    revisions.update(value.get('initial_revision_uuid') for value in protocols.values() if isinstance(value, dict))
    if 'explorer_revision' in tables:
        tables['explorer_revision'] = [row for row in tables['explorer_revision'] if row['revision_uuid'] in revisions]
    if ordered:
        for table, rows in tables.items():
            tables[table] = sorted(rows, key=serialized)
    sources = []
    source_references = []
    if 'source' in existing:
        registered = connection.query('SELECT source_sha256,manifest FROM recording_workspace.source WHERE project_uuid=%s', args=(identity,)).fetchall()
        sources = sorted(row[0] for row in registered)
        for sha, manifest in registered:
            manifest=json.loads(manifest) if isinstance(manifest,(str,bytes)) else manifest
            source_references.append({'source_sha256':sha, **{key:manifest[key] for key in
                ('source_path','metadata_path','metadata_sha256','parser_sha256','adapter_version') if key in manifest}})
        source_references.sort(key=lambda row:row['source_sha256'])
    state = dict(format=FORMAT, version=1, project=project, source_sha256s=sources,
                 source_references=source_references, protocols=protocols, tables=tables)
    return state


def _column_value(value, json_column=False):
    if json_column and isinstance(value, (str, bytes)):
        return json.loads(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return value



def query_members(service, recipe):
    eligible = [key for key,row in service.rows.items() if row['source_sha256'] in recipe['source_revisions']]
    _, identities, _ = service.match_predicate(recipe['predicate'], eligible)
    return [{'uuid':key, 'metadata_hash':service._fingerprints[key]} for key in sorted(identities)]


def query_service(root):
    from workspace_service import WorkspaceService
    from workspace_annotations import SharedAnnotations
    service = WorkspaceService(root)
    service.shared_annotations = SharedAnnotations(service)
    service._ready()
    return service


def compact_queries(state, service):
    """Use a reproducible query and digest instead of enumerating every epoch.

    Existing non-reproducible/frozen selections retain their explicit members;
    silently changing a pin during recovery would lose scientific intent.
    """
    for row in state['tables'].get('explorer_revision', []):
        recipe = row['recipe']
        try:
            members = query_members(service, recipe)
        except (KeyError, ValueError):
            continue
        if any(set(member)-{'uuid','metadata_hash','row_id'} for member in recipe['epochs']):
            continue
        expected = sorted(({'uuid':member['uuid'],'metadata_hash':member['metadata_hash']} for member in recipe['epochs']), key=lambda member:member['uuid'])
        if members != expected:
            continue
        recipe['requery'] = {'membership_sha256':hashlib.sha256(serialized(members).encode()).hexdigest(),
            'original_content_sha256':recipe['content_sha256']}
        for key in ('epochs', 'diff', 'content_sha256'):
            recipe.pop(key, None)
        # The configuration needs an app/contract version, not every source-file
        # fingerprint again. Frozen exports retain their full provenance.
        recipe['provenance'] = {key:value for key,value in recipe.get('provenance',{}).items() if key != 'code'}


def expand_queries(state, service):
    import uuid
    from workspace_recipes import checksum
    remap = {}
    for row in state['tables'].get('explorer_revision', []):
        recipe = row['recipe']; reference=recipe.pop('requery',None)
        if reference is None:continue
        members = query_members(service, recipe)
        if hashlib.sha256(serialized(members).encode()).hexdigest() != reference['membership_sha256']:
            raise ValueError('Saved query no longer reproduces the pinned selection; restore matching source metadata/app version')
        old=row['revision_uuid']
        identity=str(uuid.uuid5(uuid.UUID(row['project_uuid']), 'recovered-query:'+reference['original_content_sha256']))
        remap[old]=identity
        row.update(revision_uuid=identity,parent_revision_uuid=None)
        row['summary'].update(revision_uuid=identity,parent_revision_uuid=None)
        recipe.update(revision_uuid=identity,parent_revision_uuid=None,epochs=members,
                      diff={'added':[], 'removed':[], 'changed':[]}, recovered_from=reference)
        recipe['content_sha256']=checksum(recipe)
    for binding in state['tables'].get('protocol_binding',[]):
        binding['revision_uuid']=remap.get(binding['revision_uuid'],binding['revision_uuid'])
    for definition in state['protocols'].values():
        key=definition.get('initial_revision_uuid')
        if key in remap:definition['initial_revision_uuid']=remap[key]


def atomic_write(path, data, *, preserve_permissions=False):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('App state must use regular project files')
    mode = None
    if preserve_permissions:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError:
            pass
        # General project JSON keeps normal creation permissions. Let open()
        # apply the caller's umask atomically; never change the process umask in
        # a threaded server. Snapshot callers retain mkstemp's private 0600.
        for _ in range(100):
            temporary = path.parent / ('.app-state-' + secrets.token_hex(16))
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                             0o600 if mode is not None else 0o666)
                break
            except FileExistsError:
                continue
        else:
            raise FileExistsError('Could not allocate an exclusive project JSON temporary file')
    else:
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.app-state-')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data); handle.flush()
            if mode is not None:
                os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save(project_dir, connection, *, day=None, service=None):
    root=Path(project_dir).resolve()
    path=root/'.app-state-save.lock'
    if path.is_symlink():raise ValueError('Snapshot lock cannot be a symbolic link')
    with path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _save(root,connection,day=day,service=service)


def _save(project_dir, connection, *, day=None, service=None):
    # A verified native change feed makes ordinary tag saves proportional to
    # changed rows. The full capture remains the correctness fallback when the
    # authority cannot prove coverage, including unsupported SQL providers.
    from workspace_recovery_store import inspect as inspect_recovery, write as write_recovery
    root = Path(project_dir).resolve()
    if connection.in_transaction:
        raise ValueError('Snapshot must follow the completed app transaction')
    current = inspect_recovery(root)
    identity = json.loads((root / 'project.json').read_text())['project_uuid']
    tracker = getattr(service, '_recovery_tracker', None) if service is not None else None
    if (tracker is None or tracker.connection is not connection
            or tracker.project_uuid != identity):
        from workspace_recovery_generation import RecoveryTracker
        tracker = RecoveryTracker(connection, identity)
        if service is not None:
            service._recovery_tracker = tracker
    if tracker is not None:
        prior = current['header']['watermark'] if current is not None else None
        result = None
        with tracker.capture(prior) as plan:
            if plan is not None:
                state = capture(root, connection, include_tables=False)
                keys = {table: list(names) for table, names in plan.primary_keys.items() if table in TABLES}
                columns = {table: list(names) for table, names in plan.columns.items() if table in TABLES}
                # These tables change which immutable recipes/versions belong
                # in recovery. Reconcile them with a full pruned capture rather
                # than adding unreferenced history to the current-state mirror.
                full_tables = {'source', 'search_preset', 'search_preset_version',
                               'protocol_binding', 'explorer_revision', 'dataset_revision'}
                incremental = (current is not None and plan.complete
                    and bool(current['header'].get('table_seals'))
                    and keys == current['header']['keys'] and columns == current['header']['columns']
                    and state == current['header']['state']
                    and not any(plan.keys.get(table) for table in full_tables))
                changes = deleted = None
                if incremental:
                    changes, deleted = recovery_after_images(connection, identity, plan)
                else:
                    state = capture(root, connection, ordered=False)
                expected_header = {**state, 'tables': {table: [] for table in TABLES}}
                if capture(root, connection, include_tables=False) != expected_header:
                    raise ValueError('Project or protocol files changed during recovery capture; retry the save')
                plan.verify()
                result = write_recovery(root, state=state, keys=keys, columns=columns,
                    watermark=plan.watermark, changes=changes, deleted=deleted, day=day)
        if result is not None:
            try:
                tracker.prune(plan.watermark)
            except Exception:
                # A durable mirror is already committed. Retaining extra feed
                # rows is safe; losing them before that commit would not be.
                logging.getLogger(__name__).exception('Recovery is durable but change-feed cleanup failed')
                result['feed_cleanup_pending'] = True
            return result
    # Providers without a verified change authority still get compact current
    # state, but must read canonical rows to prove that backup is complete.
    with connection.transaction:
        state = capture(root, connection, ordered=False)
        keys, columns = recovery_schema(connection)
    return write_recovery(root, state=state, keys=keys, columns=columns, watermark=None, day=day)


def recovery_schema(connection):
    existing = {row[0] for row in connection.query(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='recording_workspace'").fetchall()}
    keys, columns = {}, {}
    for table in TABLES:
        if table not in existing:
            continue
        heading = connection.query(f'SHOW COLUMNS FROM recording_workspace.`{table}`').fetchall()
        columns[table] = [row[0] for row in heading]
        primary = connection.query(f'SHOW INDEX FROM recording_workspace.`{table}` WHERE Key_name=\'PRIMARY\'', as_dict=True).fetchall()
        keys[table] = [row['Column_name'] for row in sorted(primary, key=lambda row: row['Seq_in_index'])]
        if not keys[table]:
            raise ValueError('Recovery requires an exact primary key for ' + table)
    return keys, columns


def recovery_after_images(connection, identity, plan):
    """Fetch only changed complete keys within the authority's SQL snapshot."""
    changes, deleted = {}, {}
    for table, identities in plan.keys.items():
        if table not in TABLES or not identities:
            continue
        names = plan.primary_keys[table]
        deleted[table] = [list(key) for key in identities]
        changes[table] = []
        for offset in range(0, len(identities), 200):
            batch = identities[offset:offset+200]
            predicate = ' OR '.join('(' + ' AND '.join('`' + name + '`=%s' for name in names) + ')' for _ in batch)
            args = (identity, *(value for key in batch for value in key))
            rows = connection.query(f'SELECT * FROM recording_workspace.`{table}` '
                f'WHERE project_uuid=%s AND ({predicate})', args=args, as_dict=True).fetchall()
            for row in rows:
                changes[table].append({key: _column_value(value, key in plan.json_columns[table])
                    for key, value in dict(row).items()})
    return changes, deleted


def load(path):
    path = Path(path)
    if path.suffix == '.sqlite':
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as database:
            if database.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recovery_header'").fetchone():
                from workspace_recovery_store import load_database
                return load_database(path)
            rows = database.execute('SELECT format,version,sha256,document FROM snapshot').fetchall()
        if len(rows) != 1:
            raise ValueError('Expected one app state snapshot')
        form,version,digest,document = rows[0]
        if form != FORMAT or version != 1 or hashlib.sha256(document.encode()).hexdigest() != digest:
            raise ValueError('App state snapshot checksum or format differs')
        state = json.loads(document)
    else:
        state = json.loads(path.read_text())
        if state.get('format') == FORMAT and state.get('version') == 2:
            from workspace_recovery_store import load_database, pointer_path
            return load_database(pointer_path(path.parent, state), expected=state)
    if state.get('format') != FORMAT or state.get('version') != 1 or set(state.get('tables', {}))-set(TABLES):
        raise ValueError('Unsupported app state snapshot')
    return state


def restore(project_dir, connection, snapshot):
    root=Path(project_dir).resolve()
    path=root/'.app-state-session.lock'
    if path.is_symlink():raise ValueError('Recovery lock cannot be a symbolic link')
    with path.open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Stop the project app before restoring its saved state') from None
        return _restore(root,connection,snapshot)


def _restore(project_dir, connection, snapshot):
    """Explicit offline restore against the same imported sources and schema.

    Historical export/membership recipes are retained; current authored tables
    are replaced within one transaction. Source recordings are never modified.
    """
    root=Path(project_dir).resolve(); state=load(snapshot)
    current=capture(root,connection)
    if (state['project']['project_uuid'] != current['project']['project_uuid'] or
            state['source_sha256s'] != current['source_sha256s']):
        raise ValueError('Restore requires the same project and registered source recordings')
    if [(row['source_sha256'],row.get('metadata_sha256')) for row in state.get('source_references',[])] != [(row['source_sha256'],row.get('metadata_sha256')) for row in current.get('source_references',[])]:
        raise ValueError('Restore requires matching parsed source metadata versions')
    if set(state['tables']) != set(current['tables']):
        raise ValueError('Restore requires the same initialized app state tables')
    identity=current['project']['project_uuid']
    if any(row.get('project_uuid') != identity for rows in state['tables'].values() for row in rows):
        raise ValueError('Snapshot contains foreign project rows')
    for name in state['protocols']:
        if Path(name).name != name or not name.endswith('.json'):
            raise ValueError('Invalid protocol filename')
    # Validate all identifiers against live SQL before interpolating any columns.
    json_columns={}; columns={}
    existing = {row[0] for row in connection.query(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='recording_workspace'").fetchall()}
    for table, rows in state['tables'].items():
        if table not in existing:
            if rows:raise ValueError('Open the app to initialize its state tables before restore')
            continue
        heading=connection.query(f'SHOW COLUMNS FROM recording_workspace.`{table}`').fetchall()
        columns[table]=[row[0] for row in heading]
        json_columns[table]={row[0] for row in heading if row[1]=='json'}
        if any(set(row)!=set(columns[table]) for row in rows):
            raise ValueError('Snapshot columns differ from the app schema')
    save(root,connection)
    # Preserve the immediate pre-restore state even within the same UTC day.
    before=root/'backups/app-state'/('before-restore-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')
    atomic_write(before,serialized(current).encode());before.chmod(0o400)
    recovery_service = query_service(root) if any('requery' in row['recipe'] for row in state['tables'].get('explorer_revision',[])) else None
    files={root/'project.json':serialized(state['project']).encode()}
    files.update({root/'protocols'/name:serialized(value).encode() for name,value in state['protocols'].items()})
    for path in (root/'protocols').glob('*.json'):
        files.setdefault(path,None)
    if any(path.is_symlink() for path in files):
        raise ValueError('Restore cannot replace symbolic links')
    originals={path:path.read_bytes() if path.exists() else None for path in files}
    pending=root/'.app-state-restore.pending'
    interrupted=pending.exists()
    if not interrupted:
        atomic_write(pending,serialized({'before_restore':str(before),'requested_snapshot':str(snapshot)}).encode())
    try:
        with connection.transaction:
            order = [table for table in state['tables'] if table not in {'explorer_revision','protocol_binding'}] + ['explorer_revision','protocol_binding']
            for table in order:
                rows = state['tables'].get(table,[])
                if table not in columns:continue
                if table == 'explorer_revision' and recovery_service is not None:
                    expand_queries(state,recovery_service)
                    files.update({root/'protocols'/name:serialized(value).encode() for name,value in state['protocols'].items()})
                # Keep immutable export recipes and their historical dependencies.
                if table not in {'explorer_revision','dataset_revision','search_preset_version'}:
                    connection.query(f'DELETE FROM recording_workspace.`{table}` WHERE project_uuid=%s',args=(identity,))
                names=columns[table]
                quoted=','.join('`'+name+'`' for name in names)
                placeholders=','.join(['%s']*len(names))
                for row in rows:
                    values=tuple(serialized(row[name]) if name in json_columns[table] else row[name] for name in names)
                    connection.query(f'INSERT INTO recording_workspace.`{table}` ({quoted}) VALUES ({placeholders}) '
                        'ON DUPLICATE KEY UPDATE '+','.join('`'+name+'`=VALUES(`'+name+'`)' for name in names), args=values)
            for path,data in files.items():
                if data is None:path.unlink(missing_ok=True)
                else:atomic_write(path,data)
    except BaseException:
        for path,data in originals.items():
            if data is None:path.unlink(missing_ok=True)
            else:atomic_write(path,data)
        if not interrupted:pending.unlink(missing_ok=True)
        raise
    pending.unlink(missing_ok=True)
    return save(root,connection)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir',type=Path,required=True)
    parser.add_argument('--restore',type=Path,help='Offline only: restore saved current state; stop the app first')
    args=parser.parse_args()
    from recording_workspace import connect, configured_database
    provider=configured_database(args.project_dir)
    dj=connect(provider,project_dir=args.project_dir) if isinstance(provider,dict) else connect(provider)
    result=restore(args.project_dir,dj.conn(),args.restore) if args.restore else save(args.project_dir,dj.conn())
    print(json.dumps(result))


if __name__=='__main__':main()
