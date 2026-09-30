"""Real POSIX import-process ownership; no database, recording or network access."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from workspace_api import import_worker_process

CHILD = '''from pathlib import Path
import sys,time
started,release=map(Path,sys.argv[1:])
started.write_text("writer running")
while not release.exists():time.sleep(.01)
'''


@unittest.skipUnless(os.name == 'posix', 'Project leases are POSIX flock contracts')
class ImportWorkerLeaseTests(unittest.TestCase):
    def test_desktop_child_retains_exclusive_ownership_after_backend_descriptor_closes(self):
        self._exercise_inheritance(desktop=True)

    def test_source_mode_keeps_original_noninheriting_subprocess_behavior(self):
        self._exercise_inheritance(desktop=False)

    def _exercise_inheritance(self, *, desktop):
        with tempfile.TemporaryDirectory(prefix='import-worker-lease-') as temporary:
            root = Path(temporary)
            lock_path = root / '.app-state-session.lock'
            lease = lock_path.open('a')
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertFalse(os.get_inheritable(lease.fileno()))
            app = SimpleNamespace(extensions={'app_state_session_lock': lease})
            started, release = root / 'started', root / 'release'
            outcome = {}
            with (root / 'private-child.log').open('w') as log:
                def worker():
                    try:
                        outcome['completed'] = import_worker_process(
                            [sys.executable, '-B', '-c', CHILD, str(started), str(release)], log, app)
                    except BaseException as error:
                        outcome['error'] = error
                with patch.dict(os.environ, {'RIEKE_DESKTOP_MODE': '1' if desktop else '0'}):
                    thread = threading.Thread(target=worker)
                    thread.start()
                    try:
                        deadline = time.monotonic() + 10
                        while not started.exists() and time.monotonic() < deadline:
                            time.sleep(.01)
                        self.assertTrue(started.exists(), repr(outcome))
                        # A process crash closes backend descriptors rather than
                        # deliberately issuing LOCK_UN. Its child still owns the
                        # same open-file description when pass_fds was applied.
                        lease.close()
                        with lock_path.open('a') as contender:
                            if desktop:
                                for kind in (fcntl.LOCK_EX, fcntl.LOCK_SH):
                                    with self.assertRaises(BlockingIOError):
                                        fcntl.flock(contender, kind | fcntl.LOCK_NB)
                            else:
                                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                fcntl.flock(contender, fcntl.LOCK_UN)
                    finally:
                        release.write_text('finish the synthetic writer')
                        thread.join(timeout=10)
                        if not lease.closed:
                            lease.close()
                    self.assertFalse(thread.is_alive(), 'Synthetic writer did not finish')
                    if 'error' in outcome:
                        raise outcome['error']
                    self.assertEqual(outcome['completed'].returncode, 0)
                    # The project becomes available after the scientific child
                    # exits; no watchdog, PID probe or force-unlock is necessary.
                    with lock_path.open('a') as reopened:
                        fcntl.flock(reopened, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_desktop_cannot_start_a_writer_without_a_live_project_lease(self):
        with patch.dict(os.environ, {'RIEKE_DESKTOP_MODE': '1'}), \
                patch('workspace_api.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'active project lease'):
                import_worker_process(['unused'], None, SimpleNamespace(extensions={}))
            run.assert_not_called()
            with tempfile.TemporaryFile() as lease:
                lease.close()
                with self.assertRaisesRegex(ValueError, 'active project lease'):
                    import_worker_process(['unused'], None,
                                          SimpleNamespace(extensions={'app_state_session_lock': lease}))
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
