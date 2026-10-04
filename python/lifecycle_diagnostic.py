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
