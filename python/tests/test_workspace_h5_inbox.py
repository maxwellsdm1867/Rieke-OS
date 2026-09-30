import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workspace_h5_inbox import H5Inbox


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.time = 100
        self.jobs = []
        self.busy = False
        def submit(source, identity):
            if self.busy:
                return False
            self.jobs.append((source, identity))
            file = self.root / 'logs/app-jobs' / (identity + '.json')
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps({'status': 'queued'}))
            return True
        self.submit = submit
        self.inbox = H5Inbox(self.root, submit, clock=lambda: self.time)
        self.inbox.scan()

    def add(self, name='recording.h5'):
        path = self.inbox.path / name
        path.write_bytes(b'H5 fixture')
        return path

    def settle(self):
        self.inbox.scan()
        self.time += 6
        self.inbox.scan()

    def test_waits_for_copy_to_settle_and_ignores_partial_symlink_and_nested(self):
        self.add('partial.h5.part')
        self.add('.hidden.h5')
        self.add('empty.h5').write_bytes(b'')
        source = self.add()
        (self.inbox.path / 'linked.h5').symlink_to(source)
        (self.inbox.path / 'folder.h5').mkdir()
        self.inbox.scan()
        self.assertEqual(self.jobs, [])
        self.time += 4
        source.write_bytes(b'growing copy')
        self.inbox.scan()
        self.time += 4
        self.inbox.scan()
        self.assertEqual(self.jobs, [])
        self.time += 2
        self.inbox.scan()
        self.assertEqual([path.name for path, _ in self.jobs], ['recording.h5'])
        self.assertTrue(source.exists())

    def test_restart_and_failed_job_do_not_reimport_unchanged_file(self):
        source = self.add()
        self.settle()
        identity = self.jobs[0][1]
        (self.root / 'logs/app-jobs' / (identity + '.json')).write_text(json.dumps({'status': 'failed', 'error': 'Identity collision'}))
        self.inbox = H5Inbox(self.root, self.submit, clock=lambda: self.time)
        for _ in range(4):
            self.time += 10
            self.inbox.scan()
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(self.inbox.status()['files'][0]['status'], 'failed')
        self.assertEqual(self.inbox.status()['files'][0]['error'], 'Identity collision')
        source.write_bytes(b'changed bytes')
        self.settle()
        self.assertEqual(len(self.jobs), 2)
        self.assertNotEqual(identity, self.jobs[1][1])

    def test_preserved_size_and_mtime_still_rechecks_changed_file(self):
        source = self.add()
        self.settle()
        previous = source.stat()
        source.write_bytes(b'XX fixture')
        os.utime(source, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        self.settle()
        self.assertEqual(len(self.jobs), 2)

    def test_stop_rejects_thread_that_has_not_stopped(self):
        from unittest.mock import Mock
        self.inbox._thread = Mock()
        self.inbox._thread.is_alive.return_value = True
        self.inbox.enabled = True
        with self.assertRaisesRegex(RuntimeError, 'still finishing'):
            self.inbox.stop()
        self.assertTrue(self.inbox.enabled)

    def test_folder_drop_is_retained_in_place_without_second_copy(self):
        import hashlib
        from workspace_recording_files import retain_recording
        source = self.add()
        self.settle()
        watched = self.jobs[0][0]
        retained = retain_recording(self.root, watched, hashlib.sha256(watched.read_bytes()).hexdigest())
        self.assertEqual(retained, source.resolve())
        self.assertEqual(self.inbox.path, self.root.resolve() / 'raw-uploads')
        self.assertEqual(list(self.inbox.path.iterdir()), [source])
        self.assertFalse((self.root / 'h5-inbox').exists())

    def test_busy_import_retries_admission_without_new_job_identity(self):
        self.add()
        self.busy = True
        self.settle()
        identity = self.inbox.status()['files'][0]['job_uuid']
        self.assertFalse(self.jobs)
        self.busy = False
        self.inbox.scan()
        self.assertEqual(self.jobs[0][1], identity)

    def test_multiple_files_are_not_forgotten_after_first_submission(self):
        self.add('a.h5')
        self.add('b.h5')
        self.settle()
        self.inbox.scan()
        self.inbox.scan()
        self.assertEqual(len(self.jobs), 2)
        self.assertEqual(len(self.inbox.status()['files']), 2)

    def test_reserved_job_recovered_without_second_submission(self):
        self.add()
        self.settle()
        saved = json.loads(self.inbox.ledger_path.read_text())
        saved['files']['recording.h5']['status'] = 'planned'
        self.inbox.ledger_path.write_text(json.dumps(saved))
        self.inbox = H5Inbox(self.root, self.submit, clock=lambda: self.time)
        self.inbox.scan()
        self.assertEqual(len(self.jobs), 1)

    def test_corrupt_ledger_fails_closed_and_folder_opener_has_fixed_target(self):
        self.inbox.ledger_path.write_text('{invalid')
        second = H5Inbox(self.root, self.submit)
        with self.assertRaises(ValueError):
            second.scan()
        with patch('workspace_h5_inbox.subprocess.run') as run:
            self.inbox.open_folder()
        self.assertEqual(run.call_args.args[0][-1], str(self.inbox.path))


if __name__ == '__main__':
    unittest.main()
