"""Bounded, cancellable project discovery in a read-only child process.

This child has no desktop capability, database, or mutation entry point. Only
this owner's subprocess handles may be terminated; scientific services never
pass through this owner.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

INVENTORY_LIMIT = 8 * 1024 * 1024
UNAVAILABLE = 'Project folders could not be read. Check folder access or reconnect the drive, then retry.'


class ProjectInventoryUnavailable(ValueError):
    """Discovery did not complete; this is not an empty project inventory."""


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
        deadline = time.monotonic() + self.timeout
        if not self._serial.acquire(timeout=self.timeout):
            raise ProjectInventoryUnavailable(UNAVAILABLE)
        child = None
        try:
            with self._state:
                if self._paused or (self._stopping is not None and self._stopping.poll() is None):
                    raise ProjectInventoryUnavailable(UNAVAILABLE)
                self._stopping = None
                environment = {key: value for key, value in os.environ.items() if key in {
                    'HOME', 'TMPDIR', 'TEMP', 'SYSTEMROOT', 'LANG', 'LC_ALL',
                    'RIEKE_PROJECT_INDEX', 'RIEKE_DESKTOP_USER_STATE', 'RIEKE_PREFERENCES_DIR'}}
                child = self.process_factory(
                    [sys.executable, '-I', '-B', str(Path(__file__).resolve()), mode, str(folder)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    env=environment)
                self._active = child
            try:
                output, _ = child.communicate(timeout=max(.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise ProjectInventoryUnavailable(UNAVAILABLE) from None
            with self._state:
                if self._paused:
                    raise ProjectInventoryUnavailable(UNAVAILABLE)
            if child.returncode or len(output) > INVENTORY_LIMIT:
                raise ProjectInventoryUnavailable(UNAVAILABLE)
            try:
                result = json.loads(output)
                if result.get('kind') == 'invalid':
                    raise ValueError(result['message'])
                if result.get('ok') is not True or not isinstance(result.get('inventory'), dict):
                    raise ProjectInventoryUnavailable(UNAVAILABLE)
                return result['inventory']
            except (json.JSONDecodeError, AttributeError, KeyError, UnicodeError):
                raise ProjectInventoryUnavailable(UNAVAILABLE) from None
        finally:
            if child is not None:
                if child.poll() is None:
                    child.kill()
                    try:
                        child.communicate(timeout=.5)
                    except subprocess.TimeoutExpired:
                        # Do not spawn more helpers behind an uninterruptible OS
                        # read. It has no write authority; retain the exact handle.
                        with self._state:
                            self._stopping = child
                with self._state:
                    if self._active is child:
                        self._active = None
            self._serial.release()


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
    from workspace_projects import list_managed_projects, list_projects
    try:
        inventory = (list_managed_projects if arguments[0] == 'managed' else list_projects)(arguments[1])
        result = {'ok': True, 'inventory': inventory}
    except ValueError as error:
        result = {'ok': False, 'kind': 'invalid', 'message': str(error)}
    except OSError:
        result = {'ok': False}
    output = json.dumps(result, ensure_ascii=True).encode('utf-8')
    if len(output) > INVENTORY_LIMIT:
        output = b'{"ok":false}'
    sys.stdout.buffer.write(output)


if __name__ == '__main__':
    main()
