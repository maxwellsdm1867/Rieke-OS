"""Explicit read-only source snapshot -> separate project-owned desktop copy.

Legacy Docker is inspected through its existing local Unix socket. No Docker
command, container start/stop/exec, source SQL write or source-file rewrite occurs.
Only the bundled mysqldump client and a new destination MySQL runtime execute.
"""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import tempfile
from urllib.parse import quote

from workspace_portability import (DATABASES, DIRECTORIES, FORMAT, MANIFEST,
    _artifact_relocations, _database_inventory, _destination, _files, _hash, _inside,
    _json, _sources, _verify_recording_dependencies, _write, restore_project)

MAX_INSPECT_BYTES = 1024 * 1024


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=5)
        self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def inspect_source_container(container):
    """GET one declared container's inspect record, never execute Docker APIs."""
    if not isinstance(container, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', container):
        raise ValueError('Legacy source container identity is invalid')
    candidates = (Path.home() / '.docker/run/docker.sock', Path('/var/run/docker.sock'))
    for candidate in candidates:
        try:
            physical = candidate.resolve(strict=True)
            info = physical.stat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid not in {os.getuid(), 0}:
                continue
            connection = _UnixHTTPConnection(physical)
            try:
                connection.request('GET', '/containers/' + quote(container, safe='') + '/json',
                                   headers={'Accept': 'application/json'})
                response = connection.getresponse()
                payload = response.read(MAX_INSPECT_BYTES + 1)
                if response.status != 200 or len(payload) > MAX_INSPECT_BYTES:
                    raise ValueError('Source Docker inspect did not return a bounded success response')
                value = json.loads(payload)
                if not isinstance(value, dict) or not value.get('Id'):
                    raise ValueError('Source Docker inspect identity is invalid')
                if value.get('State', {}).get('Running') is not True:
                    raise ValueError('The existing source database is stopped. Open it through the source installation before creating a desktop copy.')
                return value
            finally:
                connection.close()
        except (OSError, http.client.HTTPException, json.JSONDecodeError):
            continue
    raise ValueError('The source Docker service is unavailable. Start the existing source database or prepare a transfer in the source installation, then restore that copy here.')


def source_connection(root):
    """Resolve ephemeral credentials from the declared existing source only."""
    import pymysql
    catalog = _json(Path(root) / 'catalog.json')
    declared = catalog.get('connection', {})
    provider = declared.get('credential_provider', {})
    if provider.get('kind') != 'docker-container-env' or declared.get('host') not in {'127.0.0.1', 'localhost'}:
        raise ValueError('Source migration currently supports declared localhost Docker databases only')
    port = declared.get('port')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('The source project must declare its existing database port')
    info = inspect_source_container(provider.get('container'))
    bindings = info.get('NetworkSettings', {}).get('Ports', {}).get('3306/tcp') or []
    selected = [item for item in bindings if item.get('HostPort') == str(port)
                and item.get('HostIp') in {'127.0.0.1', '0.0.0.0', '::', ''}]
    if not selected:
        raise ValueError('The declared source port differs from the existing Docker database; refresh the source configuration before copying')
    entries = info.get('Config', {}).get('Env')
    if not isinstance(entries, list) or len(entries) > 1000 or any(not isinstance(item, str) or len(item) > 65536 for item in entries):
        raise ValueError('Source credential environment is invalid')
    environment = dict(item.split('=', 1) for item in entries if '=' in item)
    password = environment.get('MYSQL_ROOT_PASSWORD')
    if not isinstance(password, str) or not password:
        raise ValueError('The declared source database does not expose its existing credential provider')
    settings = {'host': '127.0.0.1', 'port': port, 'user': 'root', 'password': password}
    connection = pymysql.connect(**settings, autocommit=True, connect_timeout=10, read_timeout=600, write_timeout=600)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT @@hostname, VERSION()')
            hostname, version = cursor.fetchone()
        if hostname != info.get('Config', {}).get('Hostname') or not re.match(r'^8\.', version):
            raise ValueError('Source server identity or MySQL logical format differs from its declared container')
        return connection, settings, version
    except BaseException:
        connection.close()
        raise


@contextmanager
def readonly_project_session(root):
    """Use an existing session lease without creating or modifying source files."""
    path = Path(root) / '.app-state-session.lock'
    if path.is_symlink():
        raise ValueError('Source session lock cannot be a symbolic link')
    if not path.exists():
        # Old source projects may predate leases. Consistent SQL and filesystem
        # inventories before/after below still reject concurrent source changes.
        yield
        return
    with path.open('r') as lease:
        try:
            fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('A source project session or import is still active. Finish its work and close that source session before creating a desktop copy.') from None
        yield


def _source_trigger_contract(connection):
    from workspace_state_generation import verify_export_triggers
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
    return verify_export_triggers(QueryAdapter(), DATABASES)


def _source_dump(settings, path, *, omit_derived_triggers=False):
    from workspace_native_mysql import native_binary
    arguments = [str(native_binary('mysqldump')), '--no-defaults', '--protocol=TCP', '--host=127.0.0.1',
        '--port=' + str(settings['port']), '--user=' + settings['user'], '--single-transaction',
        '--skip-lock-tables', '--no-tablespaces', '--set-gtid-purged=OFF', '--hex-blob', '--skip-comments',
        *(['--skip-triggers'] if omit_derived_triggers else []),
        '--databases', *DATABASES]
    with path.open('wb') as output:
        result = subprocess.run(arguments, stdout=output, stderr=subprocess.PIPE, timeout=600,
                                env={**os.environ, 'MYSQL_PWD': settings['password']})
    if result.returncode or not path.stat().st_size:
        raise ValueError('Read-only source backup failed; the source was not changed')


def snapshot_source_project(project_dir, destination):
    """Build the existing transfer format without writing the source or its SQL."""
    from workspace_projects import _project_record
    raw = Path(project_dir).expanduser()
    if raw.is_symlink() or not raw.is_dir():
        raise ValueError('Choose an existing regular source project folder')
    root = raw.resolve()
    record = _project_record(root)
    catalog = _json(root / 'catalog.json')
    if catalog.get('connection', {}).get('credential_provider', {}).get('kind') != 'docker-container-env':
        raise ValueError('Choose a legacy source project; native projects use project transfer')
    target = _destination(destination, root)
    with readonly_project_session(root):
        identity_files = {name: _hash(root / name) for name in ('project.json', 'catalog.json')}
        connection, settings, server_version = source_connection(root)
        staging = Path(tempfile.mkdtemp(prefix='.rieke-source-snapshot-', dir=target.parent))
        try:
            sources = _sources(connection, record['uuid'])
            source_inventory = _database_inventory(connection)
            project = _json(root / 'project.json')
            _write(staging / 'project.json', {key: project[key] for key in
                ('format', 'version', 'project_uuid', 'name', 'display_name', 'created_at') if key in project})
            before = {}
            for directory in DIRECTORIES:
                source = root / directory
                if source.exists():
                    before[directory] = _files(source, skip_marker=False)
                    _inside(root, directory)
                    output = staging / directory
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source, output)
            inventory = []
            for source in sources:
                manifest = source['manifest']
                metadata = Path(manifest['metadata_path']).resolve(strict=True)
                metadata_ref = (metadata.relative_to(root).as_posix() if metadata.is_relative_to(root / 'imports')
                                else 'imports/' + source['source_sha256'] + '/metadata.normalized.json')
                output_metadata = _inside(staging, metadata_ref)
                output_metadata.parent.mkdir(parents=True, exist_ok=True)
                if not output_metadata.exists():
                    shutil.copyfile(metadata, output_metadata)
                if _hash(output_metadata) != manifest['metadata_sha256']:
                    raise ValueError('Source metadata changed; no desktop copy was published')
                recording = Path(manifest['source_path']).resolve(strict=True)
                recording_ref = (recording.relative_to(root).as_posix() if recording.is_relative_to(root / 'raw-uploads')
                                 else 'raw-uploads/' + source['source_sha256'] + '.h5')
                output_recording = _inside(staging, recording_ref)
                output_recording.parent.mkdir(parents=True, exist_ok=True)
                if not output_recording.exists():
                    shutil.copyfile(recording, output_recording)
                if _hash(output_recording) != source['source_sha256']:
                    raise ValueError('Original recording changed; no desktop copy was published')
                _verify_recording_dependencies(output_recording)
                inventory.append({'source_sha256': source['source_sha256'], 'recording_ref': recording_ref,
                    'metadata_ref': metadata_ref, 'metadata_sha256': manifest['metadata_sha256']})
            # The verified cache-authority triggers are regenerated locally.
            # Their source-root DEFINER is neither portable nor an authority the
            # restricted restore account can impersonate. Unknown trigger
            # definitions are never silently removed from a migration.
            triggers = _source_trigger_contract(connection)
            if triggers['managed_present'] and not triggers['safe_to_omit']:
                raise ValueError(triggers['reason'])
            _source_dump(settings, staging / 'database.sql',
                         omit_derived_triggers=triggers['managed_present'])
            if _source_trigger_contract(connection)['contract_fingerprint'] != triggers['contract_fingerprint']:
                raise ValueError('Source trigger coverage changed during backup; no desktop copy was published')
            if _database_inventory(connection) != source_inventory:
                raise ValueError('Source database changed during backup; finish its writes before creating a copy')
            for directory, saved in before.items():
                if _files(root / directory, skip_marker=False) != saved:
                    raise ValueError('Source files changed during backup; no desktop copy was published')
            if any(_hash(root / name) != digest for name, digest in identity_files.items()):
                raise ValueError('Source identity or configuration changed during backup; no desktop copy was published')
            _write(staging / MANIFEST, {'format': FORMAT, 'version': 1, 'mode': 'complete',
                'database_format': 'mysql8-logical-v1', 'project_uuid': record['uuid'],
                'sources': inventory, 'database_inventory': source_inventory, 'files': _files(staging)})
            target.mkdir(mode=0o700)
            staging.rename(target)
            return {'directory': str(target), 'project_uuid': record['uuid'], 'source_count': len(sources),
                    'source_server_version': server_version, 'source_unchanged': True}
        finally:
            connection.close()
            if staging.exists():
                shutil.rmtree(staging)


def migrate_source_project(project_dir, destination):
    """Restore a read-only legacy snapshot to the user's new, exclusive folder."""
    root = Path(project_dir).expanduser().resolve(strict=True)
    target = _destination(destination, root)
    parent = Path(tempfile.mkdtemp(prefix='.rieke-migration-', dir=target.parent))
    try:
        snapshot = snapshot_source_project(root, parent / 'source-snapshot')
        result = restore_project(snapshot['directory'], target)
        from workspace_startup_registry import remember_project_result
        result = remember_project_result(result['directory'], result)
        result.update(migrated=True, source_unchanged=True, source_server_version=snapshot['source_server_version'])
        return result
    finally:
        shutil.rmtree(parent)
