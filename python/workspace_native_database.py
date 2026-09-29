"""Private native MySQL per project. Never initialize or adopt existing SQL files."""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

from workspace_mysql_profile import local_mysql_options

ROOT = Path(__file__).resolve().parents[1]


def server_binary():
    binary = ROOT / '.rieke-runtime/native/bin/mysqld'
    if not binary.is_file():
        raise ValueError('Native MySQL is missing. Run ./install.sh first.')
    return binary


def descriptor(project_dir):
    from workspace_projects import _read_manifest
    root = Path(project_dir).resolve()
    project = _read_manifest(root / 'project.json')
    catalog = _read_manifest(root / 'catalog.json')
    expected = {'version': 1, 'kind': 'native-mysql', 'project_uuid': project['project_uuid'],
                'storage_ref': 'database/mysql'}
    if (catalog['project_uuid'] != project['project_uuid'] or
            catalog.get('managed_database') != expected or
            catalog['connection']['credential_provider'] != {'kind': 'native-mysql'} or
            _read_manifest(root / 'database/service.json') != expected):
        raise ValueError('Native database ownership records disagree')
    for name in ('database', 'database/mysql', 'database/native.json', 'database/native.lock'):
        if (root / name).is_symlink():
            raise ValueError('Native database storage cannot be a symbolic link')
    return root, expected


def read_state(root, expected):
    from workspace_projects import _read_manifest
    state = _read_manifest(root / 'database/native.json')
    if (state.get('project_uuid') != expected['project_uuid'] or state.get('version') != 1 or
            not isinstance(state.get('password'), str) or len(state['password']) < 32 or
            type(state.get('port')) is not int or not 1024 <= state['port'] <= 65535):
        raise ValueError('Invalid native database identity/credentials; recover this project before opening')
    return state


def sql_connection(state):
    import pymysql
    return pymysql.connect(host='127.0.0.1', port=state['port'], user='root',
        password=state['password'], connect_timeout=2, read_timeout=5, autocommit=True)


def running(state, expected_data_dir=None):
    import pymysql
    try:
        with sql_connection(state) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT @@server_uuid, @@datadir')
                identity, data_dir = cursor.fetchone()
                if identity != state.get('server_uuid'):
                    return False
                if expected_data_dir is not None and Path(data_dir).resolve() != Path(expected_data_dir).resolve():
                    raise ValueError('This project points to a running database in a different project folder. '
                                     'Do not open a copied or moved project while the original database is running. '
                                     'Stop the original project and use an explicitly validated migration; no database was attached.')
                return True
    except (OSError, pymysql.Error):
        return False



def validate_catalog_location(root, state):
    """Reject stale managed paths without rebasing scientific provenance or exports.

    Empty, newly initialized databases have no Source table yet. Imported
    metadata is always project-owned even when the raw recording is external.
    """
    import pymysql
    try:
        with sql_connection(state) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT manifest FROM recording_workspace.source WHERE project_uuid=%s',
                               (state['project_uuid'],))
                rows = cursor.fetchall()
    except pymysql.Error as error:
        if error.args and error.args[0] in (1049, 1146):
            return  # No catalog has been created or populated yet.
        raise
    imports = (root / 'imports').resolve()
    for (serialized,) in rows:
        manifest = json.loads(serialized) if isinstance(serialized, (str, bytes)) else serialized
        metadata = manifest.get('metadata_path') if isinstance(manifest, dict) else None
        if not isinstance(metadata, str) or not Path(metadata).is_absolute() or not Path(metadata).resolve().is_relative_to(imports):
            raise ValueError('This project was moved or copied, or its managed metadata paths no longer match its folder. '
                             'Restore the original project location or use an explicitly validated migration. '
                             'Choosing another workspace does not relocate recordings, metadata or saved exports; '
                             'no scientific paths were rewritten.')


def save_state(root, state):
    target = root / 'database/native.json'
    temporary = root / ('database/.native-' + secrets.token_hex(8))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(state, handle, indent=2)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_native_database(project_dir, *, timeout=120):
    import pymysql
    root, expected = descriptor(project_dir)
    with (root / 'database/native.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = root / 'database/mysql'
        state_path = root / 'database/native.json'
        state = read_state(root, expected) if state_path.exists() else None
        if state and running(state, data):
            validate_catalog_location(root, state)
            return
        binary = server_binary()
        log_path = root / 'logs/native-mysql.log'
        # Short private socket path avoids the OS's ~104-byte Unix socket limit.
        import tempfile
        socket_dir = Path(tempfile.mkdtemp(prefix='rieke-mysql-'))
        socket_path = socket_dir / 'mysql.sock'
        init_file = root / 'database/.initialize.sql'
        if init_file.exists() or init_file.is_symlink():
            raise ValueError('Interrupted database initialization; inspect database/.initialize.sql before recovery')
        fresh = state is None
        if fresh:
            if data.exists() and any(data.iterdir()):
                raise ValueError('Database files exist without native credentials. Recover them; they will not be reinitialized.')
            state = {'version': 1, 'project_uuid': expected['project_uuid'],
                     'password': secrets.token_hex(32)}
            data.mkdir(exist_ok=True)
            with log_path.open('ab') as log:
                result = subprocess.run([str(binary), '--no-defaults', '--initialize-insecure',
                    '--basedir=' + str(binary.parent.parent), '--datadir=' + str(data),
                    *local_mysql_options()],
                    stdout=log, stderr=log, timeout=timeout)
            if result.returncode:
                raise ValueError(f'Native MySQL initialization failed. See {log_path}')
            # MySQL runs this before accepting network connections. No password
            # appears in command arguments or public project manifests.
            fd = os.open(init_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as handle:
                handle.write("ALTER USER 'root'@'localhost' IDENTIFIED BY '" + state['password'] + "';\n")
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            state['port'] = listener.getsockname()[1]
        save_state(root, state)
        args = [str(binary), '--no-defaults', '--basedir=' + str(binary.parent.parent),
                '--datadir=' + str(data), '--bind-address=127.0.0.1', '--port=' + str(state['port']),
                '--socket=' + str(socket_path), '--pid-file=' + str(root / 'database/mysql.pid'),
                '--mysqlx=OFF', *local_mysql_options()]
        if fresh:
            args.append('--init-file=' + str(init_file))
        with log_path.open('ab') as log:
            process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise ValueError(f'Native MySQL stopped. See {log_path}')
                try:
                    with sql_connection(state) as connection:
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT @@server_uuid, @@datadir')
                            identity, actual_data_dir = cursor.fetchone()
                    if Path(actual_data_dir).resolve() != data.resolve():
                        raise ValueError('Native MySQL data directory differs from this project; refusing to attach')
                    if state.get('server_uuid') and state['server_uuid'] != identity:
                        raise ValueError('Native MySQL server identity changed; refusing to attach')
                    state.update(server_uuid=identity, pid=process.pid)
                    save_state(root, state)
                    validate_catalog_location(root, state)
                    return
                except (OSError, pymysql.Error):
                    time.sleep(.2)
            raise ValueError(f'Native MySQL startup timed out. See {log_path}')
        except BaseException:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=30)
            raise
        finally:
            if fresh:
                init_file.unlink(missing_ok=True)


def connect_native(project_dir):
    import datajoint as dj
    root, expected = descriptor(project_dir)
    state = read_state(root, expected)
    if not running(state, root / 'database/mysql'):
        raise ValueError('Native project database is not running. Open the project from Rieke OS.')
    validate_catalog_location(root, state)
    for key, value in {'host':'127.0.0.1', 'port':state['port'], 'user':'root', 'password':state['password']}.items():
        dj.config['database.' + key] = value
    return dj


def stop_native_database(project_dir):
    root, expected = descriptor(project_dir)
    if not (root / 'database/native.json').exists():
        return
    with (root / 'database/native.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read_state(root, expected)
        if running(state, root / 'database/mysql'):
            with sql_connection(state) as connection:
                with connection.cursor() as cursor:
                    cursor.execute('SHUTDOWN')
            deadline = time.monotonic() + 30
            def process_alive():
                pid = state.get('pid')
                if not isinstance(pid, int) or pid <= 0:
                    return False
                try:
                    if os.waitpid(pid, os.WNOHANG)[0] == pid:
                        return False
                except ChildProcessError:
                    pass
                try:
                    os.kill(pid, 0)
                    return True
                except ProcessLookupError:
                    return False
            while (running(state, root / 'database/mysql') or process_alive()) and time.monotonic() < deadline:
                time.sleep(.2)
            if running(state, root / 'database/mysql') or process_alive():
                raise ValueError('Database has not stopped yet; do not copy its files')
