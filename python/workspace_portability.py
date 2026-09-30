"""Complete, offline project transfer using logical MySQL backups.

A prepared package is immutable interchange, not a live project. Restore always
creates a new folder/runtime; it never adopts or overwrites an existing database.
Run with the managed Python environment. Close project sessions before preparing.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import datetime as dt
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import subprocess
import tempfile
import uuid

FORMAT = 'rieke-project-transfer'
MANIFEST = 'transfer.json'
PENDING = '.portable-restore.pending'
DIRECTORIES = ('imports', 'protocols', 'query-snapshots', 'exports', 'raw-uploads',
               'logs/imports', 'logs/app-jobs', 'logs/errors', 'logs/storage')
DATABASES = ('schema', 'recording_workspace')


def _database_inventory(connection):
    """Fingerprint every logical table, including historical user-state versions.

    Inspect before rebasing current locators. JSON is canonicalized because MySQL
    may normalize its whitespace. Hashes are sorted per table so row ordering and
    tables without primary keys cannot change the result of a logical restore.
    Only row digests are retained, never complete recording metadata in memory.
    """
    from pymysql.cursors import SSCursor

    def encode(value):
        if isinstance(value, (dt.datetime, dt.date, dt.time)):
            return {'datetime': value.isoformat()}
        if isinstance(value, dt.timedelta):
            return {'timedelta': str(value)}
        if isinstance(value, Decimal):
            return {'decimal': str(value)}
        if isinstance(value, bytes):
            return {'bytes': value.hex()}
        raise TypeError(type(value).__name__)

    inventory = {}
    with connection.cursor() as cursor:
        cursor.execute('SELECT table_schema, table_name FROM information_schema.tables '
                       'WHERE table_schema IN (%s,%s) AND table_type=%s ORDER BY table_schema, table_name',
                       (*DATABASES, 'BASE TABLE'))
        tables = cursor.fetchall()
        for database, table in tables:
            # Names come from the actual server, but still quote identifiers.
            reference = '.'.join('`' + name.replace('`', '``') + '`' for name in (database, table))
            cursor.execute('SHOW COLUMNS FROM ' + reference)
            columns = cursor.fetchall()
            json_columns = [index for index, column in enumerate(columns) if column[1] == 'json']
            digests = []
            with connection.cursor(SSCursor) as data_cursor:
                data_cursor.execute('SELECT * FROM ' + reference)
                while rows := data_cursor.fetchmany(1000):
                    for row in rows:
                        row = list(row)
                        for index in json_columns:
                            if isinstance(row[index], (str, bytes)):
                                row[index] = json.loads(row[index])
                        data = json.dumps(row, default=encode, sort_keys=True,
                                          separators=(',', ':'), allow_nan=False).encode()
                        digests.append(hashlib.sha256(data).digest())
            checksum = hashlib.sha256()
            checksum.update(json.dumps([[column[0], column[1]] for column in columns],
                                       separators=(',', ':')).encode())
            digests.sort()
            for digest in digests:
                checksum.update(digest)
            inventory[database + '.' + table] = {'rows': len(digests), 'sha256': checksum.hexdigest()}
    return inventory


def _validate_database_inventory(inventory):
    if not isinstance(inventory, dict):
        raise ValueError('Prepared project database inventory is invalid')
    for table, expected in inventory.items():
        if (not isinstance(table, str) or not any(table.startswith(database + '.') and
                len(table) > len(database) + 1 for database in DATABASES)
                or not isinstance(expected, dict) or set(expected) != {'rows', 'sha256'}
                or type(expected['rows']) is not int or expected['rows'] < 0
                or not isinstance(expected['sha256'], str)
                or not re.fullmatch('[0-9a-f]{64}', expected['sha256'])):
            raise ValueError('Prepared project database inventory is invalid')


def register_empty_project(project_dir, connection=None):
    """Register a genuinely new native project's SQL identity before its first import.

    Missing identity in a populated project is corruption, never permission to
    replace its database. Check scientific files and every existing logical table
    before adding the four initial workspace tables to a still-empty database.
    """
    root = Path(project_dir).resolve()
    project = _json(root / 'project.json')
    identity = project['project_uuid']
    provider = _json(root / 'catalog.json')['connection']['credential_provider']
    if provider.get('kind') != 'native-project':
        return False
    owned = connection is None
    connection = connection or _connection(root)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT table_schema, table_name FROM information_schema.tables '
                           'WHERE table_schema IN (%s,%s) AND table_type=%s', (*DATABASES, 'BASE TABLE'))
            tables = cursor.fetchall()
            if ('recording_workspace', 'project') in tables:
                cursor.execute('SELECT project_uuid FROM recording_workspace.project')
                identities = {row[0] for row in cursor.fetchall()}
                if identities == {identity}:
                    return False
                if identities:
                    raise ValueError('Database must contain exactly the declared project identity')
            for directory in ('imports', 'protocols', 'query-snapshots', 'exports', 'raw-uploads'):
                folder = _inside(root, directory)
                files = _files(folder, skip_marker=False) if folder.exists() else {}
                if directory == 'protocols':
                    from workspace_project_preferences import ProjectPreferences, REFERENCE
                    if REFERENCE.removeprefix('protocols/') in files:
                        ProjectPreferences(root, identity).read()
                        files.pop(REFERENCE.removeprefix('protocols/'))
                if directory == 'exports' and 'README.md' in files:
                    from workspace_export_folder import GUIDE
                    if (folder / 'README.md').read_text() == GUIDE:
                        files.pop('README.md')  # Created by API startup before the read model.
                if files:
                    raise ValueError('Project database identity is missing from a populated project; restore its complete database before opening or sharing')
            for database, table in tables:
                if table == '~log':
                    continue  # DataJoint infrastructure log records table declarations.
                reference = '.'.join('`' + name.replace('`', '``') + '`' for name in (database, table))
                if database == 'recording_workspace' and table == 'annotation_profile':
                    # Older empty projects create a default author on first open,
                    # before the first import writes the Project row.
                    cursor.execute('SELECT 1 FROM ' + reference + ' WHERE project_uuid<>%s LIMIT 1', (identity,))
                else:
                    cursor.execute('SELECT 1 FROM ' + reference + ' LIMIT 1')
                if cursor.fetchone() is not None:
                    raise ValueError('Project database identity is missing from a populated project; restore its complete database before opening or sharing')
            # Same initial definitions as recording_workspace.workspace_tables.
            cursor.execute('CREATE DATABASE IF NOT EXISTS `schema`')
            cursor.execute('CREATE DATABASE IF NOT EXISTS recording_workspace')
            cursor.execute('CREATE TABLE IF NOT EXISTS recording_workspace.project '
                           '(project_uuid varchar(36) PRIMARY KEY, name varchar(255) NOT NULL, directory varchar(1024) NOT NULL)')
            cursor.execute('CREATE TABLE IF NOT EXISTS recording_workspace.source '
                           '(source_sha256 char(64) PRIMARY KEY, project_uuid varchar(36) NOT NULL, '
                           'experiment_uuid varchar(36) NOT NULL, experiment_id int NOT NULL, manifest json NOT NULL)')
            cursor.execute('CREATE TABLE IF NOT EXISTS recording_workspace.event '
                           '(event_uuid varchar(36) PRIMARY KEY, project_uuid varchar(36) NOT NULL, '
                           'occurred_at datetime NOT NULL, actor varchar(255) NOT NULL, action varchar(63) NOT NULL, payload json NOT NULL)')
            cursor.execute('CREATE TABLE IF NOT EXISTS recording_workspace.protocol_workspace '
                           '(protocol_uuid varchar(36) PRIMARY KEY, project_uuid varchar(36) NOT NULL, definition json NOT NULL)')
            cursor.execute('INSERT INTO recording_workspace.project (project_uuid,name,directory) VALUES (%s,%s,%s)',
                           (identity, project['name'], str(root)))
        return True
    finally:
        if owned:
            connection.close()


def _json(path):
    with Path(path).open(encoding='utf-8') as handle:
        return json.load(handle)


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')


def _hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def _verify_recording_dependencies(path):
    """A complete transfer must not depend on other H5 files or raw datasets."""
    import h5py
    from recording_workspace import validate_self_contained_h5
    try:
        with h5py.File(path, 'r') as handle:
            validate_self_contained_h5(handle)
    except OSError as error:
        raise ValueError('Registered recording is not a readable self-contained H5 file: ' + str(path)) from error


def _inside(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('Transfer file reference is invalid')
    value = PurePosixPath(relative)
    if value.is_absolute() or '..' in value.parts or str(value) != relative:
        raise ValueError('Transfer file reference must be a normalized relative path')
    path = root
    for part in value.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Transfer files cannot be symbolic links')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Transfer file reference leaves the package')
    return path


def _destination(value, source):
    path = Path(value).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise ValueError('Choose an absolute, new destination folder')
    from workspace_desktop_paths import require_external_data_path
    path = require_external_data_path(path)
    if path.exists():
        raise ValueError('Destination already exists; nothing was overwritten')
    if path.is_relative_to(source) or source.is_relative_to(path):
        raise ValueError('Transfer destination must be separate from the source folder')
    if not path.parent.is_dir():
        raise ValueError('Destination parent folder must already exist')
    return path


def _files(root, *, skip_marker=True):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Transfer files cannot be symbolic links')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('Transfer contains a nonregular file')
        relative = path.relative_to(root).as_posix()
        if skip_marker and relative == MANIFEST:
            continue
        result[relative] = {'sha256': _hash(path), 'size': path.stat().st_size}
    return result


@contextmanager
def _offline(root):
    path = root / '.app-state-session.lock'
    if path.is_symlink():
        raise ValueError('Project session lock cannot be a symbolic link')
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Close all project sessions and stop import tools before preparing a transfer; use the launcher to prepare it offline') from None
        yield


def _connection(project_dir):
    """Connect to the project's declared runtime; never infer a donor's backend."""
    import pymysql
    catalog = _json(Path(project_dir) / 'catalog.json')
    provider = catalog['connection']['credential_provider']
    if provider['kind'] == 'native-project':
        from workspace_native_mysql import connection_parameters
        return pymysql.connect(**connection_parameters(project_dir), autocommit=True,
                               connect_timeout=10, read_timeout=600, write_timeout=600)
    if provider['kind'] != 'docker-container-env':
        raise ValueError('Project transfer requires an explicitly configured local MySQL runtime')
    container = provider['container']
    from workspace_project_database import _run
    result = _run(['inspect', container])
    if result.returncode:
        raise ValueError('Transfer database is unavailable')
    info = json.loads(result.stdout)[0]
    bindings = info.get('NetworkSettings', {}).get('Ports', {}).get('3306/tcp') or []
    if len(bindings) != 1 or bindings[0].get('HostIp') != '127.0.0.1':
        raise ValueError('Transfer requires a private localhost database')
    environment = dict(item.split('=', 1) for item in info['Config']['Env'] if '=' in item)
    return pymysql.connect(host='127.0.0.1', port=int(bindings[0]['HostPort']), user='root',
        password=environment['MYSQL_ROOT_PASSWORD'], autocommit=True,
        connect_timeout=10, read_timeout=600, write_timeout=600)


def _sources(connection, identity):
    with connection.cursor() as cursor:
        cursor.execute('SELECT project_uuid FROM recording_workspace.project')
        identities = {row[0] for row in cursor.fetchall()}
        if identities != {identity}:
            raise ValueError('Database must contain exactly the declared project identity')
        cursor.execute('SELECT source_sha256, project_uuid, manifest FROM recording_workspace.source')
        sources = []
        for sha, project_uuid, manifest in cursor.fetchall():
            manifest = json.loads(manifest) if isinstance(manifest, (str, bytes)) else manifest
            if project_uuid != identity or manifest.get('source_sha256') != sha or not re.fullmatch(r'[0-9a-f]{64}', sha):
                raise ValueError('Database source identity disagrees with project')
            sources.append({'source_sha256': sha, 'manifest': manifest})
        return sorted(sources, key=lambda source: source['source_sha256'])


def _dump(project_dir, path):
    from workspace_state_generation import verify_export_triggers

    connection = _connection(project_dir)
    class QueryAdapter:
        def query(self, sql, args=(), *, as_dict=False, **_):
            with connection.cursor() as cursor:
                cursor.execute(sql, args)
                values = cursor.fetchall()
                names = [column[0] for column in cursor.description] if as_dict else []
                result = [dict(zip(names, row)) for row in values] if as_dict else values
            class Result:
                def fetchall(self):
                    return result
            return Result()
    try:
        adapter = QueryAdapter()
        before = verify_export_triggers(adapter, DATABASES)
        if before['managed_present'] and not before['safe_to_omit']:
            raise ValueError(before['reason'])
        _dump_logical(project_dir, path, omit_derived_triggers=before['managed_present'])
        after = verify_export_triggers(adapter, DATABASES)
        if before['contract_fingerprint'] != after['contract_fingerprint']:
            raise ValueError('Database trigger coverage changed during backup; no transfer was published')
    finally:
        connection.close()


def _dump_logical(project_dir, path, *, omit_derived_triggers=False):
    provider = _json(Path(project_dir) / 'catalog.json')['connection']['credential_provider']
    if provider['kind'] == 'native-project':
        from workspace_native_mysql import connection_parameters, native_binary
        settings = connection_parameters(project_dir)
        arguments = [str(native_binary('mysqldump')), '--no-defaults', '--protocol=TCP',
            '--host=127.0.0.1', '--port=' + str(settings['port']), '--user=' + settings['user'],
            '--single-transaction', '--skip-lock-tables', '--no-tablespaces',
            '--set-gtid-purged=OFF', '--hex-blob', '--skip-comments',
            *(['--skip-triggers'] if omit_derived_triggers else []),
            '--databases', *DATABASES]
        with path.open('wb') as handle:
            result = subprocess.run(arguments, stdout=handle, stderr=subprocess.PIPE, timeout=600,
                                    env={**os.environ, 'MYSQL_PWD': settings['password']})
        if result.returncode or not path.stat().st_size:
            raise ValueError('Logical database backup failed; no transfer was published')
        return
    if provider['kind'] != 'docker-container-env':
        raise ValueError('Unsupported project database runtime')
    container = provider['container']
    # Legacy donors remain in their explicitly configured Docker runtime.
    # Password remains inside Docker's environment, never an argv or artifact.
    trigger_option = ' --skip-triggers' if omit_derived_triggers else ''
    command = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF --hex-blob --skip-comments' + trigger_option + ' --databases schema recording_workspace'
    with path.open('wb') as handle:
        result = subprocess.run(['docker', 'exec', container, 'sh', '-c', command], stdout=handle,
                                stderr=subprocess.PIPE, timeout=600)
    if result.returncode or not path.stat().st_size:
        raise ValueError('Logical database backup failed; no transfer was published')


def _import(project_dir, path):
    # Treat received SQL as data from another user: it gets no system-schema,
    # account, FILE, SUPER, or GRANT privileges, and client commands are disabled.
    account = 'rieke_transfer_restore'
    password = secrets.token_urlsafe(36)
    provider = _json(Path(project_dir) / 'catalog.json')['connection']['credential_provider']
    account_host = '127.0.0.1' if provider['kind'] == 'native-project' else 'localhost'
    connection = _connection(project_dir)
    try:
        with connection.cursor() as cursor:
            cursor.execute("CREATE USER %s@%s IDENTIFIED BY %s", (account, account_host, password))
            for database in DATABASES:
                cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{database}`')
                cursor.execute(f"GRANT ALL PRIVILEGES ON `{database}`.* TO %s@%s", (account, account_host))
        provider = _json(Path(project_dir) / 'catalog.json')['connection']['credential_provider']
        if provider['kind'] == 'native-project':
            from workspace_native_mysql import connection_parameters, native_binary
            settings = connection_parameters(project_dir)
            arguments = [str(native_binary('mysql')), '--no-defaults', '--protocol=TCP',
                '--host=127.0.0.1', '--port=' + str(settings['port']), '--user=' + account,
                '--binary-mode', '--local-infile=0']
        elif provider['kind'] == 'docker-container-env':
            arguments = ['docker', 'exec', '-i', '--env', 'MYSQL_PWD', provider['container'],
                         'mysql', '-u' + account, '--binary-mode', '--local-infile=0']
        else:
            raise ValueError('Unsupported project database runtime')
        with path.open('rb') as handle:
            result = subprocess.run(arguments, stdin=handle,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=600,
                env={**os.environ, 'MYSQL_PWD': password})
        if result.returncode:
            raise ValueError('Logical database restore failed; source package is preserved')
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute("DROP USER IF EXISTS %s@%s", (account, account_host))
        finally:
            connection.close()


def _catalog(identity, instance):
    """A received logical backup always becomes a private native MySQL project."""
    from workspace_native_mysql import native_catalog
    return native_catalog(identity, instance)


def inspect_package(package_dir):
    """Validate complete inventory before starting MySQL or writing any files."""
    raw = Path(package_dir).expanduser()
    if raw.is_symlink() or not raw.is_dir():
        raise ValueError('Choose a regular prepared project folder')
    root = raw.resolve()
    marker = _inside(root, MANIFEST)
    if not marker.is_file() or marker.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Prepared project is incomplete or its transfer manifest is invalid')
    value = _json(marker)
    if not isinstance(value, dict) or value.get('format') != FORMAT or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('Unsupported prepared project format')
    if value.get('database_format') != 'mysql8-logical-v1' or value.get('mode') != 'complete':
        raise ValueError('Unsupported prepared project database format or transfer mode')
    files = value.get('files')
    if not isinstance(files, dict) or not {'project.json', 'database.sql'} <= files.keys():
        raise ValueError('Prepared project is missing required files')
    for relative, expected in files.items():
        _inside(root, relative)
        if not isinstance(expected, dict) or set(expected) != {'size', 'sha256'} or type(expected['size']) is not int or expected['size'] < 0 or not isinstance(expected['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', expected['sha256']):
            raise ValueError('Prepared project file checksum record is invalid')
        if relative not in {'project.json', 'database.sql'} and not any(
                relative.startswith(directory + '/') for directory in DIRECTORIES):
            raise ValueError('Prepared project contains unsupported runtime files')
    if _files(root) != files:
        raise ValueError('Prepared project checksum or file inventory mismatch')
    from workspace_projects import _identity
    project = _json(root / 'project.json')
    if not isinstance(project, dict) or project.get('format') != 'recording-project' or type(project.get('version')) is not int or project['version'] != 1 or _identity(project.get('project_uuid')) != _identity(value.get('project_uuid')):
        raise ValueError('Prepared project identity or format is invalid')
    if not isinstance(project.get('name'), str) or not project['name'].strip() or project.get('catalog_ref', 'catalog.json') != 'catalog.json':
        raise ValueError('Prepared project manifest is invalid')
    from workspace_project_preferences import ProjectPreferences
    ProjectPreferences(root, project['project_uuid']).read()
    if 'database_inventory' in value:
        _validate_database_inventory(value['database_inventory'])
    sources = value.get('sources')
    if not isinstance(sources, list):
        raise ValueError('Prepared project source inventory is invalid')
    seen = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {'source_sha256', 'recording_ref', 'metadata_ref', 'metadata_sha256'}:
            raise ValueError('Prepared project source record is invalid')
        sha = source['source_sha256']
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha) or sha in seen:
            raise ValueError('Prepared project source identities are invalid or duplicated')
        metadata_sha = source['metadata_sha256']
        if not isinstance(metadata_sha, str) or not re.fullmatch('[0-9a-f]{64}', metadata_sha):
            raise ValueError('Prepared project metadata checksum is invalid')
        seen.add(sha)
        for key in ('recording_ref', 'metadata_ref'):
            _inside(root, source[key])
        if not source['recording_ref'].startswith('raw-uploads/') or not source['metadata_ref'].startswith('imports/'):
            raise ValueError('Prepared source references use unsupported directories')
        if source['recording_ref'] not in files or source['metadata_ref'] not in files:
            raise ValueError('Prepared project is missing a registered source dependency')
        if files[source['recording_ref']]['sha256'] != sha or files[source['metadata_ref']]['sha256'] != metadata_sha:
            raise ValueError('Prepared project source checksums disagree')
        _verify_recording_dependencies(_inside(root, source['recording_ref']))
    return value


def _remove_runtime(project_dir):
    provider = _json(Path(project_dir) / 'catalog.json')['connection']['credential_provider']
    if provider['kind'] == 'native-project':
        from workspace_native_mysql import stop_native_database
        stop_native_database(project_dir)
        return
    if provider['kind'] != 'docker-container-env':
        raise ValueError('Unsupported project database runtime')
    container = provider['container']
    result = subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, timeout=60)
    if result.returncode:
        raise ValueError('Could not remove temporary transfer database; preserve its folder for recovery')


@contextmanager
def _desktop_database_session(project_dir):
    """Own transfer SQL durably and close it before acknowledging completion."""
    if os.environ.get('RIEKE_DESKTOP_MODE') != '1':
        yield
        return
    from workspace_desktop import desktop_database_operation
    identity = desktop_database_operation(project_dir)
    try:
        yield
    finally:
        try:
            _remove_runtime(project_dir)
            desktop_database_operation(project_dir, identity)
        except BaseException:
            try:
                desktop_database_operation(project_dir, identity, failed=True)
            except Exception:
                pass  # Persistent registration remains a recovery/update blocker.
            raise


def _artifact_relocations(connection, identity, root, previous=None):
    """Verify current exported-artifact locators without rewriting frozen exports."""
    root = Path(root)
    with connection.cursor() as cursor:
        try:
            cursor.execute('SELECT project_uuid, dataset_uuid, artifact_path, artifact_sha256 FROM recording_workspace.dataset_revision')
            records = cursor.fetchall()
        except Exception as error:
            if getattr(error, 'args', [None])[0] == 1146:
                return []  # Projects with no exports may not have this table yet.
            raise
        if not records:
            return []
        if previous is None:
            cursor.execute('SELECT project_uuid, directory FROM recording_workspace.project')
            projects = cursor.fetchall()
            if len(projects) != 1 or projects[0][0] != identity:
                raise ValueError('Export database does not match the project identity')
            previous = Path(projects[0][1])
    previous = Path(previous)
    if not previous.is_absolute():
        raise ValueError('Recorded project folder is not an absolute path')
    changes = []
    for project_uuid, dataset_uuid, location, checksum in records:
        if project_uuid != identity or not isinstance(location, str) or not Path(location).is_absolute():
            raise ValueError('Export artifact identity or locator is invalid')
        path = Path(location)
        if path.is_relative_to(previous / 'exports'):
            path = _inside(root, path.relative_to(previous).as_posix())
        elif path.is_relative_to(root / 'exports'):
            path = _inside(root, path.relative_to(root).as_posix())
        else:
            raise ValueError('Export artifact must live in this project exports folder')
        if not path.is_file():
            raise ValueError('Project relocation is missing a saved export artifact: ' + str(path))
        if not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum) or _hash(path) != checksum:
            raise ValueError('Project relocation export checksum mismatch: ' + str(path))
        changes.append((str(path), dataset_uuid, identity))
    return changes


def _update_artifact_locations(cursor, changes):
    for values in changes:
        cursor.execute('UPDATE recording_workspace.dataset_revision SET artifact_path=%s WHERE dataset_uuid=%s AND project_uuid=%s', values)


def restore_project(package_dir, destination):
    """Restore into a new local instance, publishing it only after verification."""
    package = Path(package_dir).expanduser().resolve()
    manifest = inspect_package(package_dir)
    target = _destination(destination, package)
    instance = str(uuid.uuid4())
    identity = manifest['project_uuid']
    catalog = _catalog(identity, instance)
    # Reserve destination exclusively. The marker hides all partial restorations.
    target.mkdir(mode=0o700)
    _write(target / PENDING, {'version': 1, 'runtime': 'native-mysql', 'instance_uuid': instance, 'project_uuid': identity})
    runtime_attempted = False
    desktop_services = ExitStack()
    try:
        for relative in manifest['files']:
            if relative == 'database.sql':
                continue
            output = _inside(target, relative)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_inside(package, relative), output)
            if _hash(output) != manifest['files'][relative]['sha256']:
                raise ValueError('Prepared project changed during restore')
        _write(target / 'catalog.json', catalog)
        _write(target / 'database/service.json', catalog['managed_database'])
        from workspace_storage import initialize_layout
        initialize_layout(target, identity, Path(__file__).resolve().parents[1])
        # Seal our own dump copy so a package change cannot alter SQL mid-import.
        dump = target / 'database' / 'transfer.sql'
        shutil.copyfile(package / 'database.sql', dump)
        if _hash(dump) != manifest['files']['database.sql']['sha256']:
            raise ValueError('Prepared database changed during restore')
        from workspace_project_database import ensure_project_database
        runtime_attempted = True
        desktop_services.enter_context(_desktop_database_session(target))
        ensure_project_database(target, _restoring=True)
        _import(target, dump)
        connection = _connection(target)
        try:
            if ('database_inventory' in manifest
                    and _database_inventory(connection) != manifest['database_inventory']):
                raise ValueError('Restored database content disagrees with the prepared project inventory')
            sources = _sources(connection, identity)
            artifacts = _artifact_relocations(connection, identity, target)
            mappings = {source['source_sha256']: source for source in manifest['sources']}
            if set(mappings) != {source['source_sha256'] for source in sources}:
                raise ValueError('Restored database sources disagree with the transfer inventory')
            with connection.cursor() as cursor:
                for source in sources:
                    record = source['manifest']
                    mapping = mappings[source['source_sha256']]
                    if record.get('metadata_sha256') != mapping['metadata_sha256']:
                        raise ValueError('Restored metadata checksum disagrees with database')
                    record['source_path'] = str(target / mapping['recording_ref'])
                    record['metadata_path'] = str(target / mapping['metadata_ref'])
                    cursor.execute('UPDATE recording_workspace.source SET manifest=%s WHERE source_sha256=%s AND project_uuid=%s',
                                   (json.dumps(record), source['source_sha256'], identity))
                    # Current import pointers move; historical event payloads stay intact.
                    local_manifest = (target / mapping['metadata_ref']).parent / 'import-manifest.json'
                    if local_manifest.is_file():
                        current = _json(local_manifest)
                        if current.get('source_sha256') != source['source_sha256']:
                            raise ValueError('Imported source file identity disagrees with database')
                        current.update(source_path=record['source_path'], metadata_path=record['metadata_path'])
                        _write(local_manifest, current)
                _update_artifact_locations(cursor, artifacts)
                cursor.execute('UPDATE recording_workspace.project SET directory=%s WHERE project_uuid=%s', (str(target), identity))
                cursor.execute('SHOW DATABASES')
                if {row[0] for row in cursor.fetchall()} - set(DATABASES) - {'mysql', 'information_schema', 'performance_schema', 'sys'}:
                    raise ValueError('Restored backup contains unexpected databases')
        finally:
            connection.close()
        dump.unlink()
        _write(target / 'database/transfer-receipt.json', {'format': FORMAT, 'version': 1,
            'project_uuid': identity, 'instance_uuid': instance, 'verified': True,
            'package_manifest_sha256': _hash(package / MANIFEST)})
        desktop_services.close()
        (target / PENDING).unlink()
        return {'project_uuid': identity, 'instance_uuid': instance, 'directory': str(target),
                'files': len(manifest['files']), 'source_count': len(manifest['sources']), 'verified': True}
    except BaseException:
        desktop_services.close()
        if runtime_attempted:
            _remove_runtime(target)
        shutil.rmtree(target)
        raise


def prepare_project(project_dir, destination):
    """Capture a complete offline package and prove its logical backup restores."""
    from workspace_projects import _project_record
    from workspace_project_database import ensure_project_database
    raw = Path(project_dir).expanduser()
    if raw.is_symlink() or not raw.is_dir():
        raise ValueError('Choose an existing regular project folder')
    root = raw.resolve()
    record = _project_record(root)
    target = _destination(destination, root)
    identity = record['uuid']
    with _offline(root), _desktop_database_session(root):
        from workspace_project_preferences import ProjectPreferences
        ProjectPreferences(root, identity).read()
        ensure_project_database(root)
        connection = _connection(root)
        staging = Path(tempfile.mkdtemp(prefix='.rieke-transfer-', dir=target.parent))
        try:
            register_empty_project(root, connection)
            with connection.cursor() as cursor:
                cursor.execute('SET SESSION lock_wait_timeout=15')
                cursor.execute('FLUSH TABLES WITH READ LOCK')
            sources = _sources(connection, identity)
            database_inventory = _database_inventory(connection)
            source_project = _json(root / 'project.json')
            # Only portable identity/display fields enter the transfer manifest.
            project = {key: source_project[key] for key in ('format', 'version', 'project_uuid', 'name', 'display_name', 'created_at') if key in source_project}
            project['name'] = source_project.get('name') or record['name']
            project['catalog_ref'] = 'catalog.json'
            _write(staging / 'project.json', project)
            before = {}
            for directory in DIRECTORIES:
                source_dir = root / directory
                if source_dir.exists():
                    if source_dir.is_symlink():
                        raise ValueError('Managed transfer directories cannot be symbolic links')
                    # Reject symlinked parents too, including the logs root.
                    _inside(root, directory)
                    before[directory] = _files(source_dir, skip_marker=False)
                    output_dir = staging / directory
                    output_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source_dir, output_dir)
            inventory = []
            for source in sources:
                manifest = source['manifest']
                metadata = Path(manifest['metadata_path']).resolve(strict=True)
                if not metadata.is_relative_to(root / 'imports'):
                    raise ValueError('Source metadata must live in project imports')
                reference = metadata.relative_to(root).as_posix()
                if _hash(_inside(staging, reference)) != manifest['metadata_sha256']:
                    raise ValueError('Source metadata checksum changed')
                recording = Path(manifest['source_path']).resolve()
                recording_ref = (recording.relative_to(root).as_posix() if recording.is_relative_to(root / 'raw-uploads')
                                 else 'raw-uploads/' + source['source_sha256'] + '.h5')
                output = _inside(staging, recording_ref)
                output.parent.mkdir(exist_ok=True)
                if not output.exists():
                    try:
                        shutil.copyfile(recording, output)
                    except FileNotFoundError:
                        raise ValueError('A registered recording is missing; locate it before preparing a complete transfer') from None
                if _hash(output) != source['source_sha256']:
                    raise ValueError('Recording checksum changed or a recording is missing')
                _verify_recording_dependencies(output)
                inventory.append({'source_sha256': source['source_sha256'], 'recording_ref': recording_ref,
                                  'metadata_ref': reference, 'metadata_sha256': manifest['metadata_sha256']})
            _dump(root, staging / 'database.sql')
            for directory, prior in before.items():
                staged_files = _files(staging / directory, skip_marker=False)
                if _files(root / directory, skip_marker=False) != prior or any(staged_files.get(key) != value for key, value in prior.items()):
                    raise ValueError('Project files changed while preparing transfer; stop all writers and retry')
            with connection.cursor() as cursor:
                cursor.execute('UNLOCK TABLES')
            connection.close()
            connection = None
            _write(staging / MANIFEST, {'format': FORMAT, 'version': 1, 'mode': 'complete',
                'database_format': 'mysql8-logical-v1', 'project_uuid': identity,
                'sources': inventory, 'database_inventory': database_inventory, 'files': _files(staging)})
            # Real restore verification, including identities and current source locators.
            verify_parent = Path(tempfile.mkdtemp(prefix='.rieke-verify-', dir=target.parent))
            try:
                verified = restore_project(staging, str(verify_parent / 'project'))
                _remove_runtime(Path(verified['directory']))
            except BaseException:
                # A failed runtime shutdown leaves evidence for manual recovery.
                # Failed restores remove their own partial project already.
                if not (verify_parent / 'project').exists():
                    shutil.rmtree(verify_parent)
                raise
            else:
                shutil.rmtree(verify_parent)
            # Claim the final path exclusively before replacing our own empty
            # reservation with the fully verified package.
            try:
                target.mkdir(mode=0o700)
            except FileExistsError:
                raise ValueError('Destination appeared during preparation; nothing was overwritten') from None
            staging.rename(target)
            return {'project_uuid': identity, 'directory': str(target),
                    'files': len(_json(target / MANIFEST)['files']), 'source_count': len(inventory), 'verified': True}
        finally:
            if connection is not None:
                connection.close()  # Releases the database-wide read lock on every failure.
            if staging.exists():
                shutil.rmtree(staging)


def _replace_json(path, value):
    """Replace current local metadata atomically during retryable relocation."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Current project manifests cannot be symbolic links')
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        _write(temporary, value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _rename_project_exclusive(source, destination):
    """Atomic directory rename that cannot replace even an empty destination."""
    import ctypes
    import errno
    library = ctypes.CDLL(None, use_errno=True)
    if os.uname().sysname == 'Darwin':
        rename = library.renamex_np
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(source), os.fsencode(destination), 0x00000004)  # RENAME_EXCL
    elif os.uname().sysname == 'Linux' and hasattr(library, 'renameat2'):
        rename = library.renameat2
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)  # AT_FDCWD, RENAME_NOREPLACE
    else:
        raise ValueError('Safe project moves are unsupported on this platform; close the project and copy its folder manually')
    if result:
        error = ctypes.get_errno()
        if error == errno.EXDEV:
            raise ValueError('Moving between volumes is not supported here. Close the project, copy its folder to the other volume, and open the copy before removing the original')
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise ValueError('Destination already exists; no project files were replaced')
        raise OSError(error, os.strerror(error), str(source))


@contextmanager
def _move_lock(path, message):
    if path.is_symlink():
        raise ValueError('Project move locks cannot be symbolic links')
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(message) from None
        yield


def relocate_project(project_dir, destination):
    """Move a closed native project to an exact new folder without copying data.

    Its scientific UUID and all contents remain unchanged. Existing next-open
    relocation rebases current SQL/file locators after the private database starts.
    Cross-volume movement is deliberately not a copy/delete transaction.
    """
    from workspace_projects import _project_record
    import workspace_native_mysql as native
    source = Path(project_dir).expanduser()
    if not source.is_absolute() or source.is_symlink() or not source.is_dir():
        raise ValueError('Choose an absolute existing project folder, not a symbolic link')
    from workspace_desktop_paths import require_external_data_path
    source = require_external_data_path(source)
    project = _project_record(source)
    target = _destination(destination, source)
    code_root = Path(__file__).resolve().parents[1]
    if target.is_relative_to(code_root) or code_root.is_relative_to(target):
        raise ValueError('Project storage must remain separate from application code')
    catalog = _json(source / 'catalog.json')
    if catalog.get('connection', {}).get('credential_provider', {}).get('kind') != 'native-project':
        raise ValueError('In-app moves require a native MySQL project; legacy project folders need explicit migration')
    root, descriptor = native._configuration(source)
    logs = root / 'logs'
    if logs.is_symlink():
        raise ValueError('Project logs cannot be a symbolic link during a move')
    logs.mkdir(exist_ok=True)
    # Match opener lock ordering. Never move beneath a running API, startup,
    # shutdown, or other native database operation.
    with _move_lock(logs / 'workspace-server.lock', 'Project startup is active; wait and close the project before moving'), \
         _move_lock(root / '.app-state-session.lock', 'Close the project before moving its folder'), \
         _move_lock(root / 'database/native.lock', 'A database operation is active; wait before moving the project'):
        if (root / '.project-path-rebase.pending').exists():
            raise ValueError('Finish the interrupted project open before moving its folder again')
        owner_path = root / 'database/native-owner.json'
        data = root / descriptor['storage_ref']
        if owner_path.exists():
            owner = native._read(owner_path)
            if (owner.get('project_uuid') != descriptor['project_uuid']
                    or owner.get('instance_uuid') != descriptor['instance_uuid']
                    or owner.get('clean_shutdown') is not True):
                raise ValueError('Close the project cleanly before moving its database folder')
            native._credentials(root, descriptor)
            runtime_path = root / descriptor['runtime_ref']
            if runtime_path.exists():
                runtime = native._read(runtime_path)
                machine = native._machine_identity()
                if (machine is not None and runtime.get('project_path') == str(root)
                        and runtime.get('machine_id') == machine
                        and native._owned_process(runtime) is not None):
                    raise ValueError('The project database is still running; close it before moving')
        elif ((data.exists() and any(data.iterdir()))
              or (root / descriptor['credentials_ref']).exists()
              or (root / descriptor['runtime_ref']).exists()):
            raise ValueError('The database has no verified clean state; finish its recovery before moving')
        _rename_project_exclusive(root, target)
    return {'project_uuid': project['uuid'], 'previous_directory': str(root),
            'directory': str(target), 'moved': True}


def rebase_project_paths(project_dir, connection=None):
    """Reopen a cold-copied native project at its new location without packaging.

    Run before starting app writers. Only current project/source locators change;
    historical event payloads and immutable exports keep their original evidence.
    All dependencies are verified before writing. A small journal makes interrupted
    local-file/SQL updates idempotently recoverable on the next open.
    """
    root = Path(project_dir).expanduser().resolve()
    identity = _json(root / 'project.json')['project_uuid']
    journal = root / '.project-path-rebase.pending'
    if journal.is_symlink():
        raise ValueError('Project relocation journal cannot be a symbolic link')
    owned_connection = connection is None
    connection = connection or _connection(root)
    try:
        with connection.cursor() as cursor:
            try:
                cursor.execute('SELECT project_uuid, directory FROM recording_workspace.project')
                projects = cursor.fetchall()
            except Exception as error:
                if getattr(error, 'args', [None])[0] in (1049, 1146):
                    return {'relocated': False, 'source_count': 0, 'directory': str(root)}
                raise
        if not projects:
            return {'relocated': False, 'source_count': 0, 'directory': str(root)}
        if len(projects) != 1 or projects[0][0] != identity:
            raise ValueError('Database must contain exactly the declared project identity before relocation')
        previous = Path(projects[0][1])
        if not previous.is_absolute():
            raise ValueError('Recorded project folder is not an absolute path')
        if journal.exists():
            recovery = _json(journal)
            if recovery.get('project_uuid') != identity or recovery.get('directory') != str(root):
                raise ValueError('An interrupted project relocation needs recovery at its recorded destination')
            previous = Path(recovery['previous_directory'])
            if not previous.is_absolute():
                raise ValueError('Project relocation journal is invalid')
        elif previous == root:
            return {'relocated': False, 'source_count': 0, 'directory': str(root)}

        def relocate(value, *, metadata=False):
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError('A recorded source locator is not an absolute path')
            path = Path(value)
            if path.is_relative_to(previous):
                path = _inside(root, path.relative_to(previous).as_posix())
            elif path.is_relative_to(root):
                path = _inside(root, path.relative_to(root).as_posix())
            elif metadata:
                raise ValueError('Source metadata must live in the project imports folder')
            if metadata and not path.is_relative_to(root / 'imports'):
                raise ValueError('Source metadata must live in the project imports folder')
            return path

        sources = _sources(connection, identity)
        changes = []
        missing = []
        for source in sources:
            record = dict(source['manifest'])
            recording = relocate(record['source_path'])
            metadata = relocate(record['metadata_path'], metadata=True)
            for path, expected in ((recording, source['source_sha256']),
                                   (metadata, record['metadata_sha256'])):
                if not path.is_file():
                    missing.append(str(path))
                elif _hash(path) != expected:
                    raise ValueError('Project relocation checksum mismatch: ' + str(path))
            record.update(source_path=str(recording), metadata_path=str(metadata))
            local = metadata.parent / 'import-manifest.json'
            local_record = None
            if local.exists():
                if local.is_symlink():
                    raise ValueError('Current import manifests cannot be symbolic links')
                local_record = _json(local)
                if local_record.get('source_sha256') != source['source_sha256']:
                    raise ValueError('Imported source file identity disagrees with database')
                local_record.update(source_path=str(recording), metadata_path=str(metadata))
            changes.append((source['source_sha256'], record, local, local_record))
        if missing:
            raise ValueError('This project depends on missing files. Copy managed recordings with the project, '
                             'or restore access to linked recordings before opening: ' + '; '.join(missing[:8]))
        artifacts = _artifact_relocations(connection, identity, root, previous)
        _replace_json(journal, {'version': 1, 'project_uuid': identity,
                               'previous_directory': str(previous), 'directory': str(root)})
        connection.begin()
        try:
            with connection.cursor() as cursor:
                for sha, record, local, local_record in changes:
                    if local_record is not None:
                        _replace_json(local, local_record)
                    cursor.execute('UPDATE recording_workspace.source SET manifest=%s WHERE source_sha256=%s AND project_uuid=%s',
                                   (json.dumps(record), sha, identity))
                _update_artifact_locations(cursor, artifacts)
                cursor.execute('UPDATE recording_workspace.project SET directory=%s WHERE project_uuid=%s', (str(root), identity))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        journal.unlink()
        return {'relocated': True, 'source_count': len(sources), 'directory': str(root)}
    finally:
        if owned_connection:
            connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'inspect', 'restore'))
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', nargs='?', type=Path)
    args = parser.parse_args()
    if args.operation == 'inspect':
        result = inspect_package(args.source)
    else:
        if args.destination is None:
            parser.error('prepare and restore require a new destination folder')
        result = (prepare_project if args.operation == 'prepare' else restore_project)(args.source, args.destination)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
