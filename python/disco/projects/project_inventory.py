"""Bounded, cancellable project discovery in a read-only child process.

This child has no desktop capability, database, or mutation entry point. Only
this owner's subprocess handles may be terminated; scientific services never
pass through this owner.
"""
from __future__ import annotations

import json
import hashlib
import logging
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
import time

INVENTORY_LIMIT = 8 * 1024 * 1024
PROGRESS_LIMIT = 1024
UNAVAILABLE = 'Project folders could not be read. Check folder access or reconnect the drive, then retry.'
OPERATIONS = frozenset({'starting', 'load_reader', 'validate_folder', 'list_directory', 'inspect_project',
                        'read_registry', 'read_project_index', 'read_saved_project'})
SCOPES = frozenset({'managed_root', 'project_parent', 'current_project', 'candidate',
                    'registry', 'saved_project', 'discovery_support'})
logger = logging.getLogger(__name__)


class ProjectInventoryUnavailable(ValueError):
    """Discovery did not complete; this is not an empty project inventory."""
    def __init__(self, message=UNAVAILABLE, *, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics if diagnostics is not None else {}


def _collect(child, deadline, diagnostics):
    """Drain both pipes without retaining unbounded progress or worker output."""
    output, pending = bytearray(), bytearray()
    with selectors.DefaultSelector() as selector:
        for pipe, kind in ((child.stdout, 'inventory'), (child.stderr, 'progress')):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, kind)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(child.args, 0)
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == 'inventory':
                    if len(output) + len(chunk) > INVENTORY_LIMIT:
                        diagnostics['reason'] = 'output_limit'
                        raise ProjectInventoryUnavailable(diagnostics=diagnostics)
                    output.extend(chunk)
                    continue
                # Each trusted progress record is short, path-free JSON. A
                # malformed/oversized stream cannot consume unbounded memory or
                # put arbitrary child stderr into API responses or logs.
                pending.extend(chunk)
                while b'\n' in pending:
                    line, _, rest = pending.partition(b'\n')
                    pending = bytearray(rest)
                    if len(line) > PROGRESS_LIMIT:
                        continue
                    try:
                        value = json.loads(line)
                        operation, scope, path_id = (value.get(name) for name in ('operation', 'scope', 'path_id'))
                        if (operation in OPERATIONS and scope in SCOPES
                                and isinstance(path_id, str) and len(path_id) == 16
                                and all(char in '0123456789abcdef' for char in path_id)):
                            diagnostics.update(operation=operation, scope=scope, path_id=path_id)
                        if value.get('reason') in {'permission_denied', 'filesystem_error'}:
                            diagnostics['reason'] = value['reason']
                    except (ValueError, AttributeError, TypeError):
                        pass
                if len(pending) > PROGRESS_LIMIT:
                    pending.clear()
        child.wait(timeout=max(.001, deadline - time.monotonic()))
    return bytes(output)


class ProjectInventory:
    def __init__(self, *, timeout=3.0, process_factory=subprocess.Popen):
        self.timeout = timeout
        self.process_factory = process_factory
        self._serial = threading.Lock()
        self._state = threading.Lock()
        self._paused = False
        self._active = None
        self._stopping = None

    def managed(self, root):
        return self._read('managed', root)

    def current(self, project):
        return self._read('current', project)

    def pause(self):
        with self._state:
            self._paused = True
            # Popen retains this exact child identity; never accept a caller PID.
            for child in (self._active, self._stopping):
                if child is not None and child.poll() is None:
                    child.kill()

    def resume(self):
        with self._state:
            self._paused = False

    def _read(self, mode, folder):
        started = time.monotonic()
        deadline = started + self.timeout
        diagnostics = {'reason': 'unavailable', 'operation': 'starting', 'mode': mode}
        if not self._serial.acquire(timeout=self.timeout):
            raise ProjectInventoryUnavailable(diagnostics={'reason': 'busy', 'mode': mode,
                'elapsed_ms': round((time.monotonic() - started) * 1000, 1)})
        child = None
        failed = False
        try:
            with self._state:
                if self._paused or (self._stopping is not None and self._stopping.poll() is None):
                    diagnostics['reason'] = 'paused' if self._paused else 'worker_still_stopping'
                    raise ProjectInventoryUnavailable(diagnostics=diagnostics)
                self._stopping = None
                environment = {key: value for key, value in os.environ.items() if key in {
                    'HOME', 'TMPDIR', 'TEMP', 'SYSTEMROOT', 'LANG', 'LC_ALL',
                    'RIEKE_PROJECT_INDEX', 'RIEKE_DESKTOP_USER_STATE', 'RIEKE_PREFERENCES_DIR'}}
                child = self.process_factory(
                    [sys.executable, '-I', '-B', str(Path(__file__).resolve()), mode, str(folder)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env=environment)
                self._active = child
            try:
                output = _collect(child, deadline, diagnostics)
            except subprocess.TimeoutExpired:
                diagnostics['reason'] = 'timeout'
                detail = ' Discovery timed out'
                if diagnostics['operation'] == 'list_directory':
                    detail += ' while listing a folder'
                elif diagnostics['operation'] != 'starting':
                    detail += ' while reading project information'
                raise ProjectInventoryUnavailable(UNAVAILABLE + detail + '.', diagnostics=diagnostics) from None
            with self._state:
                if self._paused:
                    diagnostics['reason'] = 'paused'
                    raise ProjectInventoryUnavailable(diagnostics=diagnostics)
            if child.returncode or len(output) > INVENTORY_LIMIT:
                diagnostics['reason'] = 'worker_failed'
                raise ProjectInventoryUnavailable(diagnostics=diagnostics)
            try:
                result = json.loads(output)
                if result.get('kind') == 'invalid':
                    raise ValueError(result['message'])
                if result.get('ok') is not True or not isinstance(result.get('inventory'), dict):
                    raise ProjectInventoryUnavailable(diagnostics=diagnostics)
                return result['inventory']
            except (json.JSONDecodeError, AttributeError, KeyError, UnicodeError):
                diagnostics['reason'] = 'invalid_response'
                raise ProjectInventoryUnavailable(diagnostics=diagnostics) from None
        except ProjectInventoryUnavailable:
            failed = True
            raise
        except OSError:
            failed = True
            diagnostics['reason'] = 'worker_io_error'
            raise ProjectInventoryUnavailable(diagnostics=diagnostics) from None
        finally:
            if child is not None:
                if child.poll() is None:
                    child.kill()
                    try:
                        child.wait(timeout=.5)
                    except subprocess.TimeoutExpired:
                        # Do not spawn more helpers behind an uninterruptible OS
                        # read. It has no write authority; retain the exact handle.
                        with self._state:
                            self._stopping = child
                diagnostics['worker_cleanup'] = 'reaped' if child.poll() is not None else 'pending'
                for pipe in (child.stdout, child.stderr):
                    if pipe is not None:
                        pipe.close()
                with self._state:
                    if self._active is child:
                        self._active = None
            self._serial.release()
            if failed:
                diagnostics['elapsed_ms'] = round((time.monotonic() - started) * 1000, 1)
                logger.warning('Project discovery unavailable: %s', json.dumps(diagnostics, sort_keys=True))


def project_inventory(app):
    """One bounded discovery owner per Flask application."""
    return app.extensions.setdefault('project_inventory', ProjectInventory())


def _read_only(event, args):
    if event == 'open':
        mode, flags = args[1], args[2]
        if ((isinstance(mode, str) and any(value in mode for value in 'wax+'))
                or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))):
            raise PermissionError('Project discovery cannot write files')
    if event in {'os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.link', 'os.symlink',
                 'os.truncate', 'os.chmod', 'os.chown', 'os.utime', 'os.system', 'os.posix_spawn',
                 'os.fork', 'os.forkpty', 'os.setxattr', 'os.removexattr', 'subprocess.Popen',
                 'socket.__new__', 'sqlite3.connect', 'ctypes.dlopen'}:
        raise PermissionError('Project discovery cannot mutate files, launch processes, or access a database/network')


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) != 2 or arguments[0] not in {'managed', 'current'}:
        raise ValueError('Project discovery requires a mode and exact folder')
    # -I ignores caller Python paths; admit only the packaged application root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.addaudithook(_read_only)

    def progress(event, args):
        if event == 'disco.project_inventory':
            operation, scope, path = args
        elif event in {'os.listdir', 'os.scandir'}:
            operation, path = 'list_directory', args[0]
            expected = Path(arguments[1]) if arguments[0] == 'managed' else Path(arguments[1]).parent
            scope = ('managed_root' if arguments[0] == 'managed' else 'project_parent') if str(path) == str(expected) else 'discovery_support'
        else:
            return
        emit({'operation': operation, 'scope': scope,
              'path_id': hashlib.sha256(os.fsencode(str(path))).hexdigest()[:16]})

    def emit(value):
        try:
            os.write(2, (json.dumps(value, separators=(',', ':')) + '\n').encode('ascii'))
        except OSError:
            pass  # Diagnostic delivery must never change discovery behavior.

    sys.addaudithook(progress)
    try:
        sys.audit('disco.project_inventory', 'load_reader', 'discovery_support',
                  str(Path(__file__).resolve().parents[2]))
        from workspace_projects import list_managed_projects, list_projects
        sys.audit('disco.project_inventory', 'validate_folder',
                  'managed_root' if arguments[0] == 'managed' else 'current_project', arguments[1])
        inventory = (list_managed_projects if arguments[0] == 'managed' else list_projects)(arguments[1])
        result = {'ok': True, 'inventory': inventory}
    except ValueError as error:
        result = {'ok': False, 'kind': 'invalid', 'message': str(error)}
    except OSError as error:
        emit({'reason': 'permission_denied' if isinstance(error, PermissionError) else 'filesystem_error'})
        result = {'ok': False}
    output = json.dumps(result, ensure_ascii=True).encode('utf-8')
    if len(output) > INVENTORY_LIMIT:
        output = b'{"ok":false}'
    sys.stdout.buffer.write(output)


if __name__ == '__main__':
    main()
