"""Collector lifetime for a dedicated, single-project worker process.

Only the desktop project worker and the disposable workflow server opt in.
Library callers and shared Python interpreters keep normal collector behavior.
The loaded heap stays reference-counted; cycles entirely within newly allocated
request objects still receive normal collection. Cycles involving frozen objects
remain until refresh or close thaws the old heap before collection.
"""
from __future__ import annotations

import contextlib
import gc
import threading


_owner = None
_ownership_lock = threading.Lock()


class ProjectHeap:
    def __init__(self):
        self.lock = threading.RLock()
        self.depth = 0
        self.frozen = False
        self.closed = False

    def start(self):
        global _owner
        with self.lock:
            with _ownership_lock:
                if self.closed or _owner is not None or gc.get_freeze_count():
                    raise RuntimeError('Project heap requires exclusive ownership of a dedicated process')
                _owner = self
            try:
                self._freeze()
            except BaseException:
                self.close()
                raise
        return self

    def _freeze(self):
        # Pay the full scan once at load/refresh, before interactive readiness.
        # Never disable cyclic GC or change its thresholds for later requests.
        gc.collect()
        gc.freeze()
        self.frozen = True

    def _thaw(self):
        if self.frozen:
            gc.unfreeze()
            self.frozen = False

    @contextlib.contextmanager
    def refresh(self):
        with self.lock:
            if self.closed or _owner is not self:
                raise RuntimeError('Project heap is closed')
            outer = self.depth == 0
            if outer:
                self._thaw()
            self.depth += 1
            succeeded = False
            try:
                yield
                succeeded = True
            finally:
                self.depth -= 1
                if outer:
                    if succeeded:
                        self._freeze()
                    else:
                        # A failed refresh restores ordinary collection; it must
                        # not pin partially constructed or retired project state.
                        gc.collect()

    def close(self):
        global _owner
        with self.lock:
            if self.closed:
                return
            if self.depth:
                raise RuntimeError('Cannot close the project heap during refresh')
            self.closed = True
            if _owner is self:
                self._thaw()
                try:
                    gc.collect()
                finally:
                    with _ownership_lock:
                        _owner = None


def install(app):
    """Opt in only after the dedicated worker has constructed its project app."""
    if 'project_heap' in app.extensions:
        return app.extensions['project_heap']
    service = app.extensions['workspace_service']
    if getattr(service, '_project_heap', None) is not None:
        raise RuntimeError('Workspace service already owns a project heap')
    owner = ProjectHeap().start()
    service._project_heap = owner
    app.extensions['project_heap'] = owner
    app.extensions['close_project_heap'] = owner.close
    return owner
