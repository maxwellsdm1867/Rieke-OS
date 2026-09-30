"""Private project-owned MySQL. Never discovers or modifies a system MySQL server.

Runtime binaries come from the application bundle; durable data and credentials
belong to the project. Process ownership is checked before connection or shutdown.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
import secrets
import socket
import stat
import subprocess
import tempfile
import time
import uuid

from workspace_mysql_profile import local_mysql_options

ROOT = Path(__file__).resolve().parents[1]
_PROCESSES = {}  # Retain children until graceful shutdown; avoid orphaned Popen handles.


@lru_cache(maxsize=1)
def _machine_identity():
    """Stable local identity, stored only as a hash; unknown never means equal."""
    try:
        system = os.uname().sysname
        if system == 'Darwin':
            result = subprocess.run(['/usr/sbin/ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
                                    capture_output=True, text=True, timeout=5)
            match = re.search(r'"IOPlatformUUID"\s*=\s*"([0-9A-Fa-f-]+)"', result.stdout)
            if result.returncode or match is None:
                return None
            value = str(uuid.UUID(match.group(1)))
        elif system == 'Linux':
            value = Path('/etc/machine-id').read_text().strip().lower()
            if not re.fullmatch('[0-9a-f]{32}', value):
                return None
        else:
            return None
        return hashlib.sha256((system + ':' + value).encode()).hexdigest()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def native_catalog(identity, instance_uuid=None):
    identity = str(uuid.UUID(identity))
    instance = str(uuid.UUID(instance_uuid)) if instance_uuid else str(uuid.uuid4())
    descriptor = {'version': 1, 'kind': 'native-mysql', 'project_uuid': identity,
        'instance_uuid': instance, 'storage_ref': 'database/mysql',
        'runtime_ref': 'database/native-runtime.json', 'credentials_ref': 'database/native-credentials.json'}
    return {'format': 'recording-catalog-reference', 'version': 1, 'project_uuid': identity,
        'catalog_id': 'retinanalysis-local', 'adapter': 'datajoint', 'database': 'schema',
        'workspace_database': 'recording_workspace', 'managed_database': descriptor,
        'connection': {'host': '127.0.0.1', 'port': None,
                       'credential_provider': {'kind': 'native-project', 'credentials_ref': descriptor['credentials_ref']}}}


def native_binary(name='mysqld'):
    if name not in {'mysqld', 'mysql', 'mysqldump'}:
        raise ValueError('Unsupported private MySQL binary')
    try:
        from workspace_mysql_runtime import mysql_runtime
    except ImportError:
        # Development installations predate the dedicated runtime prefix.
        for prefix in (ROOT / '.rieke-runtime/mysql', ROOT / '.rieke-runtime/native'):
            binary = prefix / 'bin' / name
            if binary.is_file() and os.access(binary, os.X_OK):
                return binary.resolve()
        raise ValueError('Private MySQL runtime is missing; run Rieke OS setup') from None
    runtime = mysql_runtime(root=ROOT)
    binary = Path(runtime.get(name) or Path(runtime['root']) / 'bin' / name)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError('Private MySQL client is missing; run Rieke OS setup')
    return binary.resolve()


def _read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('Native database configuration must be a small regular file')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Native database configuration must be an object')
    return value


def _write(path, value):
    if path.is_symlink():
        raise ValueError('Native database configuration cannot be a symbolic link')
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(value, handle)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _configuration(project_dir):
    candidate = Path(project_dir).expanduser()
    if candidate.is_symlink():
        raise ValueError('Native project folder cannot be a symbolic link')
    root = candidate.resolve()
    project = _read(root / 'project.json')
    catalog = _read(root / 'catalog.json')
    database = root / 'database'
    if database.is_symlink():
        raise ValueError('Native database directory cannot be a symbolic link')
    descriptor_file = database / 'service.json'
    descriptor = _read(descriptor_file) if descriptor_file.exists() else catalog.get('managed_database')
    identity = str(uuid.UUID(project['project_uuid']))
    if not isinstance(descriptor, dict):
        raise ValueError('Native database ownership record is missing')
    instance = str(uuid.UUID(descriptor['instance_uuid']))
    expected = native_catalog(identity, instance)['managed_database']
    if descriptor != expected or catalog.get('project_uuid') != identity:
        raise ValueError('Native database ownership does not match this project')
    if catalog.get('managed_database') and catalog['managed_database'] != descriptor:
        raise ValueError('Native database ownership records disagree')
    provider = catalog.get('connection', {}).get('credential_provider', {})
    if provider != {'kind': 'native-project', 'credentials_ref': expected['credentials_ref']}:
        raise ValueError('Native database credentials must use the project-owned credential file')
    for name in ('mysql', 'native-runtime.json', 'native-credentials.json', 'native-owner.json', 'native.lock', 'mysql-error.log'):
        if (database / name).is_symlink():
            raise ValueError('Native database files cannot be symbolic links')
    return root, descriptor


@contextmanager
def _locked(root):
    lock_path = root / 'database/native.lock'
    if lock_path.is_symlink():
        raise ValueError('Native database lock cannot be a symbolic link')
    with lock_path.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _credentials(root, descriptor):
    path = root / descriptor['credentials_ref']
    if path.is_symlink():
        raise ValueError('Native database credentials cannot be a symbolic link')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError('Native database credentials must be a readable regular local file') from error
    with os.fdopen(fd, 'r') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536 or info.st_uid != os.getuid():
            raise ValueError('Native database credentials must be a small regular file owned by this user')
        # Ordinary folder copies/ZIP extraction may reset modes. Tighten only a
        # verified current-user-owned descriptor, never chown another user's file.
        if stat.S_IMODE(info.st_mode) != 0o600:
            os.fchmod(handle.fileno(), 0o600)
        if stat.S_IMODE(os.fstat(handle.fileno()).st_mode) != 0o600:
            raise ValueError('This filesystem cannot protect native database credentials with permission 0600')
        value = json.load(handle)
    if not isinstance(value, dict) or value.get('project_uuid') != descriptor['project_uuid'] or value.get('instance_uuid') != descriptor['instance_uuid'] or not isinstance(value.get('password'), str) or len(value['password']) < 32:
        raise ValueError('Native database credentials do not match this project instance')
    return value


def _owned_process(runtime):
    import psutil
    if type(runtime.get('pid')) is not int or runtime['pid'] <= 1:
        raise ValueError('Native database process record is invalid')
    try:
        process = psutil.Process(runtime['pid'])
        if process.status() == psutil.STATUS_ZOMBIE:
            return None
        if abs(process.create_time() - runtime['process_created']) > 0.001:
            return None  # PID was recycled; this is not the recorded server, never signal it.
        if process.uids().real != os.getuid() or str(Path(process.exe()).resolve()) != runtime['executable'] or process.cmdline() != runtime['argv']:
            raise ValueError('Native database process ownership changed; refusing to attach or stop it')
        return process
    except psutil.NoSuchProcess:
        return None
    except (psutil.AccessDenied, KeyError, TypeError) as error:
        raise ValueError('Cannot verify native database process ownership') from error


def _runtime(root, descriptor):
    path = root / descriptor['runtime_ref']
    if not path.exists():
        return None
    value = _read(path)
    if value.get('project_uuid') != descriptor['project_uuid'] or value.get('instance_uuid') != descriptor['instance_uuid']:
        raise ValueError('Native database runtime belongs to a different project')
    owner_path = root / 'database/native-owner.json'
    owner = _read(owner_path) if owner_path.exists() else {}
    if (owner.get('clean_shutdown') is True and owner.get('project_uuid') == descriptor['project_uuid']
            and owner.get('instance_uuid') == descriptor['instance_uuid']):
        return None  # A completed shutdown is authoritative; stale foreign PIDs are irrelevant.
    machine = _machine_identity()
    if value.get('machine_id') is not None and value['machine_id'] != machine:
        return None  # Never inspect a sender's PID on the recipient's computer.
    if value.get('project_path') != str(root):
        if _owned_process(value):
            raise ValueError('This copied project still refers to an active source database; close it cleanly before copying')
        return None
    if value.get('executable') != str(native_binary()):
        raise ValueError('Native database runtime executable changed; stop the old runtime before updating')
    argv = value.get('argv')
    required = {f'--datadir={root / "database/mysql"}', '--no-defaults', '--bind-address=127.0.0.1', '--mysqlx=OFF'}
    if not isinstance(argv, list) or not required.issubset(argv) or not argv or argv[0] != value['executable']:
        raise ValueError('Native database process arguments do not match its project')
    if type(value.get('port')) is not int or not 1024 <= value['port'] <= 65535:
        raise ValueError('Native database port is invalid')
    return value


def _verify_server(connection, root, runtime):
    with connection.cursor() as cursor:
        cursor.execute('SELECT @@datadir, @@port, @@socket')
        datadir, port, unix_socket = cursor.fetchone()
        if Path(datadir).resolve() != root / 'database/mysql' or int(port) != runtime['port'] or unix_socket != runtime['socket']:
            raise ValueError('Connected MySQL server does not belong to this project')


def connection_parameters(project_dir):
    """Private credentials for DataJoint/PyMySQL; never return this in an API."""
    root, descriptor = _configuration(project_dir)
    runtime = _runtime(root, descriptor)
    if not runtime or not _owned_process(runtime) or runtime.get('bootstrap'):
        raise ValueError('Native project database is not ready; open the project first')
    credentials = _credentials(root, descriptor)
    import pymysql
    parameters = {'host': '127.0.0.1', 'port': runtime['port'], 'user': 'root', 'password': credentials['password']}
    connection = pymysql.connect(**parameters, connect_timeout=3)
    try:
        _verify_server(connection, root, runtime)
    finally:
        connection.close()
    return parameters


connection_settings = connection_parameters


def _socket_directory(root, descriptor):
    # macOS Unix sockets have a short path limit; the private parent prevents
    # other local users from replacing the socket or its lock file.
    token = hashlib.sha256((str(root) + descriptor['instance_uuid']).encode()).hexdigest()[:24]
    path = Path('/tmp') / ('rieke-mysql-' + str(os.getuid()) + '-' + token)
    if path.is_symlink():
        raise ValueError('Private MySQL socket directory cannot be a symbolic link')
    path.mkdir(mode=0o700, exist_ok=True)
    if path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise ValueError('Private MySQL socket directory ownership or permissions changed')
    return path


def _unix_connection(unix_socket, password, *, autocommit=False):
    import pymysql
    # Explicitly own failed socket attempts: PyMySQL's Unix-socket retry path
    # otherwise leaves sockets allocated when connect() fails before handoff.
    transport = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    transport.settimeout(3)
    try:
        transport.connect(unix_socket)
        connection = pymysql.connect(unix_socket=unix_socket, user='root', password=password,
                                     autocommit=autocommit, defer_connect=True)
        connection.connect(sock=transport)
        return connection
    except BaseException:
        transport.close()
        raise


def _launch(root, descriptor, *, bootstrap, timeout):
    import psutil
    import pymysql
    executable = native_binary()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    socket_dir = _socket_directory(root, descriptor)
    unix_socket = str(socket_dir / 'mysql.sock')
    argv = [str(executable), '--no-defaults', f'--basedir={executable.parent.parent}',
            f'--datadir={root / "database/mysql"}', f'--socket={unix_socket}',
            f'--pid-file={socket_dir / "mysql.pid"}', f'--log-error={root / "database/mysql-error.log"}',
            '--bind-address=127.0.0.1', f'--port={port}', '--mysqlx=OFF', '--skip-name-resolve',
            '--mysql-native-password=ON', '--local-infile=OFF', '--secure-file-priv=NULL',
            *local_mysql_options()]
    if bootstrap:
        argv.append('--skip-networking')
    owner_path = root / 'database/native-owner.json'
    if owner_path.exists():
        owner = _read(owner_path)
        owner.update(clean_shutdown=False, last_project_path=str(root), machine_id=_machine_identity())
        _write(owner_path, owner)
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True, env={**os.environ, 'MYSQL_HOME': str(socket_dir)})
    _PROCESSES[process.pid] = process
    owned = psutil.Process(process.pid)
    runtime = {'version': 1, 'project_uuid': descriptor['project_uuid'], 'instance_uuid': descriptor['instance_uuid'],
        'project_path': str(root), 'pid': process.pid, 'process_created': owned.create_time(),
        'executable': str(executable), 'argv': argv, 'port': port, 'socket': unix_socket, 'bootstrap': bootstrap,
        'machine_id': _machine_identity()}
    _write(root / descriptor['runtime_ref'], runtime)
    password = '' if bootstrap else _credentials(root, descriptor)['password']
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ValueError('Private MySQL could not start; inspect database/mysql-error.log. Existing data was preserved')
        try:
            connection = _unix_connection(unix_socket, password)
            try:
                if not bootstrap:
                    _verify_server(connection, root, runtime)
            finally:
                connection.close()
            return runtime
        except (pymysql.Error, OSError):
            time.sleep(0.2)
    raise ValueError('Private MySQL startup timed out; its owned process and data are preserved for retry')


def _shutdown(root, descriptor, runtime, password):
    import pymysql
    process = _owned_process(runtime)
    if process is None:
        return False
    connection = _unix_connection(runtime['socket'], password)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT @@datadir, @@socket')
            datadir, unix_socket = cursor.fetchone()
            if Path(datadir).resolve() != root / 'database/mysql' or unix_socket != runtime['socket']:
                raise ValueError('Refusing to stop a MySQL server outside this project')
            cursor.execute('SHUTDOWN')
            runtime = {**runtime, 'shutdown_requested': True}
            _write(root / descriptor['runtime_ref'], runtime)
    finally:
        connection.close()
    return _await_shutdown(root, descriptor, runtime, process)


def _await_shutdown(root, descriptor, runtime, process):
    import psutil
    # The chooser may own this child while a separate project API closes it.
    # A non-parent cannot reap a zombie: psutil.wait() would wait until the
    # chooser happened to reap it despite MySQL already having exited cleanly.
    deadline = time.monotonic() + 30
    while True:
        try:
            exited = process is None or not process.is_running() or process.status() == psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            exited = True
        if exited:
            break
        if time.monotonic() >= deadline:
            raise ValueError('Private MySQL is still shutting down; no process was forcibly killed')
        time.sleep(0.1)
    child = _PROCESSES.pop(runtime['pid'], None)
    if child is not None:
        child.wait(timeout=1)
    owner_path = root / 'database/native-owner.json'
    if owner_path.exists():
        owner = _read(owner_path)
        owner.update(clean_shutdown=True, last_project_path=str(root), machine_id=_machine_identity())
        _write(owner_path, owner)
    (root / descriptor['runtime_ref']).unlink(missing_ok=True)
    return True


def stop_native_database(project_dir):
    """Graceful authenticated shutdown only after exact ownership verification."""
    root, descriptor = _configuration(project_dir)
    with _locked(root):
        runtime = _runtime(root, descriptor)
        if runtime is None:
            return False
        process = _owned_process(runtime)
        machine = _machine_identity()
        if runtime.get('shutdown_requested') is True and machine is not None and runtime.get('machine_id') == machine:
            return _await_shutdown(root, descriptor, runtime, process)
        if process is None:
            (root / descriptor['runtime_ref']).unlink(missing_ok=True)
            return False  # An arbitrary crashed/missing process is never called clean.
        credentials = _credentials(root, descriptor)
        return _shutdown(root, descriptor, runtime, credentials['password'])


def ensure_native_database(project_dir, *, timeout=120):
    for pid, child in list(_PROCESSES.items()):
        if child.poll() is not None:
            _PROCESSES.pop(pid, None)
    root, descriptor = _configuration(project_dir)
    native_binary()  # Resolve the app runtime before creating credentials or data.
    database = root / 'database'
    database.mkdir(exist_ok=True)
    with _locked(root):
        runtime = _runtime(root, descriptor)
        if runtime and _owned_process(runtime):
            connection_parameters(root)
            return runtime
        if runtime:
            (root / descriptor['runtime_ref']).unlink()
        data = root / descriptor['storage_ref']
        owner_path = database / 'native-owner.json'
        credential_path = root / descriptor['credentials_ref']
        if not owner_path.exists():
            if data.exists() and any(data.iterdir()):
                raise ValueError('Existing MySQL files have no native ownership record; explicit recovery is required')
            if credential_path.exists():
                raise ValueError('Native database initialization was interrupted; preserve its files for explicit recovery')
            data.mkdir(mode=0o700, exist_ok=True)
            credentials = {'version': 1, 'project_uuid': descriptor['project_uuid'],
                'instance_uuid': descriptor['instance_uuid'], 'password': secrets.token_urlsafe(36)}
            _write(credential_path, credentials)
            executable = native_binary()
            result = subprocess.run([str(executable), '--no-defaults', '--initialize-insecure',
                f'--basedir={executable.parent.parent}', f'--datadir={data}', '--mysqlx=OFF',
                '--skip-log-bin', '--lower-case-table-names=2' if os.uname().sysname == 'Darwin' else '--lower-case-table-names=0'],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout)
            if result.returncode:
                raise ValueError('Private MySQL initialization failed; existing files were preserved for recovery')
            runtime = _launch(root, descriptor, bootstrap=True, timeout=timeout)
            import pymysql
            connection = _unix_connection(runtime['socket'], '', autocommit=True)
            try:
                with connection.cursor() as cursor:
                    cursor.execute("CREATE USER 'root'@'127.0.0.1' IDENTIFIED BY %s", (credentials['password'],))
                    cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION")
                    cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (credentials['password'],))
            finally:
                connection.close()
            _shutdown(root, descriptor, runtime, credentials['password'])
            _write(owner_path, {'version': 1, 'project_uuid': descriptor['project_uuid'],
                'instance_uuid': descriptor['instance_uuid'], 'mysql_series': '8.4',
                'clean_shutdown': True, 'last_project_path': str(root), 'machine_id': _machine_identity()})
        else:
            owner = _read(owner_path)
            expected = {'version': 1, 'project_uuid': descriptor['project_uuid'],
                        'instance_uuid': descriptor['instance_uuid'], 'mysql_series': '8.4'}
            if any(owner.get(key) != value for key, value in expected.items()) or not data.is_dir():
                raise ValueError('Native database data ownership does not match this project')
            machine = _machine_identity()
            same_origin = (machine is not None and owner.get('machine_id') == machine
                           and owner.get('last_project_path') == str(root))
            if owner.get('clean_shutdown') is not True and not same_origin:
                raise ValueError('This copied or moved database was not closed cleanly; close the original project before copying its folder')
            _credentials(root, descriptor)
        return _launch(root, descriptor, bootstrap=False, timeout=timeout)
