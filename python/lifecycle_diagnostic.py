"""Owned-fixture diagnostics only; never a readiness or integrity authority."""
import contextlib
import itertools
import json
import os
import sys
import time

_sequence = itertools.count()

def mark(phase, state='event', span=None):
    directory = os.environ.get('DISCO_LIFECYCLE_DIAGNOSTIC_DIR')
    if not directory:
        return
    # Parent harness must provision a private, owned directory before launch.
    # Per-process files avoid concurrent writers; no paths, capabilities or data.
    record = dict(version=1, pid=os.getpid(), role='project' if '--project-dir' in sys.argv else 'root',
                  phase=phase, state=state, span=span, monotonic_ns=time.monotonic_ns(), wall_ns=time.time_ns())
    try:
        filename = os.path.join(directory, 'python-%s.jsonl' % os.getpid())
        fd = os.open(filename, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, (json.dumps(record, separators=(',', ':')) + '\n').encode())
        finally:
            os.close(fd)
    except OSError:
        # Missing evidence invalidates a diagnostic run, never changes app work.
        pass

@contextlib.contextmanager
def phase(name):
    span = next(_sequence)
    mark(name, 'begin', span)
    try:
        yield
    except BaseException:
        mark(name, 'error', span)
        raise
    else:
        mark(name, 'end', span)

def measured(name):
    def decorate(function):
        def wrapped(*args, **kwargs):
            with phase(name):
                return function(*args, **kwargs)
        return wrapped
    return decorate


def install_read_observers():
    """Opt-in timing wrappers; preserve cache contracts and scientific behavior."""
    if not os.environ.get('DISCO_LIFECYCLE_DIAGNOSTIC_DIR'):
        return
    import workspace_project_database, workspace_api, workspace_service
    targets = [(workspace_project_database, 'ensure_project_database'),
               (workspace_api, 'create_app'), (workspace_service, 'read_response_window'),
               (workspace_service, 'connect'), (workspace_service, 'evaluate_protocol_file')]
    targets += [(workspace_service.WorkspaceService, name) for name in
                ('refresh', '_verified_source', '_read_source_metadata', 'epoch', 'trace')]
    for owner, name in targets:
        function = getattr(owner, name)
        if getattr(function, '_disco_observed', False):
            continue
        wrapped = measured(getattr(owner, '__name__', type(owner).__name__) + '.' + name)(function)
        wrapped._disco_observed = True
        setattr(owner, name, wrapped)
