"""Update the recovery mirror synchronously after each committed SQL edit.

The mirror is incremental (only rows changed since its watermark are written),
so it runs at the commit point: no timer, delay, quiet period or worker thread.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone


class BackupScheduler:
    def __init__(self, capture, database_lock, *, logger=None):
        self.capture=capture; self.database_lock=database_lock; self.logger=logger
        self.state_lock=threading.Lock(); self.requested=0; self.completed=0
        self.running=False; self.stopped=False; self.last_error=None; self.last_success=None

    def request(self):
        """Back up a just-committed edit now, under the database lock.

        The edit is already committed, so a failure is recorded (status
        ``degraded``, still pending) and logged rather than raised; the next
        request or flush covers it. A request made during a capture on the same
        thread stays pending instead of recursing.
        """
        with self.database_lock:
            with self.state_lock:
                self.requested+=1
                if self.stopped:
                    self.last_error='Backup is stopped; flush before closing'
                    return
                if self.running:return
            try:self._capture_locked()
            except Exception:
                if self.logger:self.logger.exception('Committed edit recovery backup failed; the next save retries')

    def status(self):
        with self.state_lock:
            pending=self.requested>self.completed
            return {'status':'degraded' if self.last_error else 'running' if self.running else 'pending' if pending else 'current',
                'pending':pending,'running':self.running,'last_success':self.last_success,
                'last_error':self.last_error,'requested_sequence':self.requested,'completed_sequence':self.completed}

    def _capture_locked(self):
        # Callers hold the reentrant database lock; the state lock only guards
        # the counters, never the capture itself.
        with self.state_lock:
            goal=self.requested; self.running=True
        try:
            self.capture()
        except Exception as error:
            with self.state_lock:self.last_error=str(error)
            raise
        else:
            with self.state_lock:
                self.completed=max(self.completed,goal); self.last_error=None
                self.last_success=datetime.now(timezone.utc).isoformat()
        finally:
            with self.state_lock:self.running=False

    def flush(self):
        """Force a complete current mirror, including writes outside this path."""
        with self.database_lock:self._capture_locked()
        return self.status()

    def close(self, *, flush=True):
        if flush:self.flush()
        with self.state_lock:self.stopped=True
