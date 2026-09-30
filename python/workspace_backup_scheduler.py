"""Coalesce recovery mirrors after committed SQL edits; flush before shutdown."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone


class BackupScheduler:
    def __init__(self, capture, database_lock, *, delay=1.0, max_delay=5.0, retry_delay=5.0, logger=None):
        self.capture=capture; self.database_lock=database_lock
        self.delay=delay; self.max_delay=max_delay; self.retry_delay=retry_delay; self.logger=logger
        self.condition=threading.Condition(); self.requested=0; self.completed=0
        self.first_dirty=None; self.last_dirty=None; self.retry_at=0.0
        self.running=False; self.stopped=False; self.last_error=None; self.last_success=None
        self.worker=threading.Thread(target=self._work,name='workspace-state-backup',daemon=True)
        self.worker.start()

    def request(self):
        with self.condition:
            self.requested+=1
            now=time.monotonic()
            if self.first_dirty is None:self.first_dirty=now
            self.last_dirty=now
            if self.stopped:self.last_error='Backup worker is stopped; flush before closing'
            self.condition.notify_all()

    def status(self):
        with self.condition:
            pending=self.requested>self.completed
            return {'status':'degraded' if self.last_error else 'running' if self.running else 'pending' if pending else 'current',
                'pending':pending,'running':self.running,'last_success':self.last_success,
                'last_error':self.last_error,'requested_sequence':self.requested,'completed_sequence':self.completed}

    def _capture_locked(self):
        # Always acquire the database lock before the condition. The close path
        # already holds the reentrant database lock when it calls flush().
        with self.condition:
            goal=self.requested; self.running=True
        try:
            self.capture()
        except Exception as error:
            with self.condition:
                self.last_error=str(error); self.retry_at=time.monotonic()+self.retry_delay
            raise
        else:
            with self.condition:
                self.completed=goal; self.last_error=None; self.retry_at=0.0
                self.last_success=datetime.now(timezone.utc).isoformat()
                if self.completed==self.requested:self.first_dirty=self.last_dirty=None
        finally:
            with self.condition:self.running=False; self.condition.notify_all()

    def flush(self):
        """Force a complete current mirror, including writes outside this queue."""
        with self.database_lock:self._capture_locked()
        return self.status()

    def close(self, *, flush=True):
        if flush:self.flush()
        with self.condition:self.stopped=True; self.condition.notify_all()
        # Do not join here: callers may hold database_lock while a worker waits
        # for it. The worker checks stopped again before any database operation.

    def _work(self):
        while True:
            with self.condition:
                if self.stopped:return
                if self.requested==self.completed:
                    self.condition.wait(); continue
                deadline=max(self.retry_at,min(self.last_dirty+self.delay,self.first_dirty+self.max_delay))
                remaining=deadline-time.monotonic()
                if remaining>0:self.condition.wait(remaining); continue
            with self.database_lock:
                with self.condition:
                    if self.stopped:return
                    if self.requested==self.completed:continue
                    # A newer edit may have arrived while waiting for SQL.
                    deadline=max(self.retry_at,min(self.last_dirty+self.delay,self.first_dirty+self.max_delay))
                    if time.monotonic()<deadline:continue
                try:self._capture_locked()
                except Exception:
                    if self.logger:self.logger.exception('Committed annotation recovery backup failed; retrying')
