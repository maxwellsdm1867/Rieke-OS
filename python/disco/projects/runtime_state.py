"""One answer to "is this project's private database running, and is it ours?"

Callers (desktop supervision, project shell cleanup, unmount, import admission)
ask here instead of interpreting PIDs themselves. A PID alone never proves
anything: liveness requires the recorded process creation time, and ownership
reuses the native owner's exact executable/argv proof
(``workspace_native_mysql._owned_process``). Nothing here starts, signals or
stops a process, and nothing here opens SQL.

States:

- ``never_started``: no owner receipt, credentials, runtime record or data.
- ``stopped_clean``: the owner receipt records an authenticated clean shutdown.
- ``stopped_unclean``: no live owned process, but no clean shutdown receipt
  (crash, failed first start, interrupted initialization, stale runtime record).
  Whether such data may be opened stays with the native per-project gate.
- ``running_owned``: the recorded server is alive and exactly this project's.
- ``running_foreign``: a recorded process is alive but is not provably this
  project's server (changed ownership, a copied project's source database, or
  an unverifiable/unreadable record). It blocks this project only.
"""
from __future__ import annotations

import json
import os
import math
from sys import platform as _platform
from pathlib import Path

NEVER_STARTED = 'never_started'
STOPPED_CLEAN = 'stopped_clean'
STOPPED_UNCLEAN = 'stopped_unclean'
RUNNING_OWNED = 'running_owned'
RUNNING_FOREIGN = 'running_foreign'
RUNNING = frozenset({RUNNING_OWNED, RUNNING_FOREIGN})

RUNTIME_REF = 'database/native-runtime.json'
OWNER_REF = 'database/native-owner.json'
CREDENTIALS_REF = 'database/native-credentials.json'
STORAGE_REF = 'database/mysql'
_CREATE_TIME_TOLERANCE = 0.001


def _small_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('Runtime evidence must be a small regular file')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Runtime evidence must be an object')
    return value


def process_birth_time(process):
    """Stable PID identity, never psutil's clock-adjusted macOS display time.

    psutil 7.2.2 uses this same kernel timestamp for its own PID-reuse checks.
    Keep the narrow private adapter here: an unsupported backend fails closed,
    rather than falling back to the clock-dependent value on macOS.
    """
    try:
        value = (process._proc.create_time(monotonic=True) if _platform == 'darwin'
                 else process.create_time())
    except (AttributeError, TypeError) as error:
        raise ValueError('Stable process birth time is unavailable') from error
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('Stable process birth time is invalid')
    return value


def current_process_created():
    """Creation time recorded beside a PID so later checks survive PID reuse."""
    try:
        import psutil
        return psutil.Process().create_time()
    except Exception:  # Optional evidence; absence keeps conservative checks.
        return None


def recorded_process_alive(pid, created=None, *, entry_points=None):
    """True only when the recorded process may still be the same process.

    With a recorded creation time, a different creation time is a recycled PID.
    Older records without one fall back to the command line when entry points
    are given (an unrelated program reusing the PID is not ours), otherwise to
    plain existence. Unverifiable processes count as alive (fail closed).
    """
    if type(pid) is not int or pid <= 0:
        return False
    import psutil
    try:
        process = psutil.Process(pid)
        if process.status() == psutil.STATUS_ZOMBIE:
            return False
        if isinstance(created, (int, float)) and not isinstance(created, bool):
            return abs(process.create_time() - created) <= _CREATE_TIME_TOLERANCE
        if entry_points:
            try:
                command = process.cmdline()
            except psutil.AccessDenied:
                return True
            return any(Path(argument).name in entry_points for argument in command)
        return True
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


IMPORT_ENTRY_POINTS = frozenset({'recording_workspace.py', 'workspace_api.py', 'workspace_desktop.py', 'workspace_updates.py'})
_IMPORT_FINISHED = frozenset({'complete', 'failed', 'duplicate'})


def import_worker_alive(progress):
    """Whether an interrupted import's recorded worker may still be running."""
    if not isinstance(progress, dict) or progress.get('stage') in _IMPORT_FINISHED:
        return False
    pid = progress.get('pid')
    if type(pid) is not int or pid <= 0 or pid == os.getpid():
        return False
    return recorded_process_alive(pid, progress.get('process_created'), entry_points=IMPORT_ENTRY_POINTS)


def project_runtime_state(project_dir):
    """Classify one project's private database without changing anything."""
    root = Path(project_dir).expanduser()
    result = {'state': None, 'pid': None, 'reason': None}
    try:
        root = root.resolve()
        if not root.is_dir():
            # A detached drive cannot host a running server; it is not clean either.
            return {**result, 'state': STOPPED_UNCLEAN, 'reason': 'project folder is unavailable'}
        runtime_path, owner_path = root / RUNTIME_REF, root / OWNER_REF
        owner = _small_json(owner_path) if owner_path.exists() or owner_path.is_symlink() else None
        runtime = _small_json(runtime_path) if runtime_path.exists() or runtime_path.is_symlink() else None
    except (OSError, ValueError) as error:
        return {**result, 'state': RUNNING_FOREIGN, 'reason': 'Runtime evidence is unreadable: ' + str(error)}
    clean = bool(owner and owner.get('clean_shutdown') is True)
    if runtime is not None:
        result['pid'] = runtime.get('pid')
        result['shutdown_requested'] = runtime.get('shutdown_requested') is True
        same_instance = owner is not None and all(owner.get(key) == runtime.get(key) for key in ('project_uuid', 'instance_uuid'))
        if clean and same_instance:
            # Same authority as the native owner: a completed shutdown wins.
            return {**result, 'state': STOPPED_CLEAN, 'reason': 'clean shutdown receipt'}
        import workspace_native_mysql as native
        machine = native._machine_identity()
        if runtime.get('machine_id') is None or runtime['machine_id'] == machine:
            try:
                process = native._owned_process(runtime)
            except ValueError as error:
                return {**result, 'state': RUNNING_FOREIGN, 'reason': str(error)}
            if process is not None:
                if runtime.get('project_path') != str(root):
                    return {**result, 'state': RUNNING_FOREIGN,
                            'reason': 'A copied project refers to another folder\'s active database'}
                return {**result, 'state': RUNNING_OWNED, 'reason': 'owned database process is alive',
                        'bootstrap': runtime.get('bootstrap') is True}
        return {**result, 'state': STOPPED_CLEAN if clean else STOPPED_UNCLEAN,
                'reason': 'runtime record is stale; no owned process is alive'}
    if owner is not None:
        return {**result, 'state': STOPPED_CLEAN if clean else STOPPED_UNCLEAN,
                'reason': 'clean shutdown receipt' if clean else 'no clean shutdown receipt'}
    data = root / STORAGE_REF
    try:
        has_data = data.is_dir() and any(data.iterdir())
    except OSError:
        has_data = True
    if (root / CREDENTIALS_REF).exists() or has_data:
        return {**result, 'state': STOPPED_UNCLEAN, 'reason': 'database initialization was interrupted'}
    return {**result, 'state': NEVER_STARTED, 'reason': 'database was never started'}
