import threading
import time
import unittest
from unittest.mock import Mock

from workspace_backup_scheduler import BackupScheduler


class BackupSchedulerTests(unittest.TestCase):
    def scheduler(self,capture,**kwargs):
        value=BackupScheduler(capture,threading.RLock(),**kwargs)
        self.addCleanup(lambda:value.close(flush=False))
        return value

    def wait_for(self,predicate):
        deadline=time.monotonic()+2
        while not predicate() and time.monotonic()<deadline:time.sleep(.005)
        self.assertTrue(predicate())

    def test_burst_is_coalesced_and_flush_captures_current_state(self):
        capture=Mock();scheduler=self.scheduler(capture,delay=.08)
        for _ in range(20):scheduler.request()
        self.assertEqual(capture.call_count,0)
        self.assertEqual(scheduler.status()['status'],'pending')
        self.wait_for(lambda:scheduler.status()['status']=='current')
        self.assertEqual(capture.call_count,1)
        scheduler.flush()
        self.assertEqual(capture.call_count,2)

    def test_failed_backup_is_visible_and_flush_retries(self):
        capture=Mock(side_effect=[OSError('Disk full'),None])
        scheduler=self.scheduler(capture,delay=.01,retry_delay=10)
        scheduler.request()
        self.wait_for(lambda:scheduler.status()['status']=='degraded')
        self.assertTrue(scheduler.status()['pending'])
        self.assertEqual(scheduler.status()['last_error'],'Disk full')
        scheduler.flush()
        self.assertEqual(scheduler.status()['status'],'current')

    def test_flush_inside_database_lock_does_not_deadlock_waiting_worker(self):
        capture=Mock();scheduler=self.scheduler(capture,delay=0)
        with scheduler.database_lock:
            scheduler.request();time.sleep(.02)
            scheduler.flush()
            scheduler.close(flush=False)
        scheduler.worker.join(1)
        self.assertFalse(scheduler.worker.is_alive())
        self.assertEqual(capture.call_count,1)

    def test_failed_clean_close_keeps_worker_available(self):
        capture=Mock(side_effect=[OSError('Disk full'),None])
        scheduler=self.scheduler(capture,delay=10)
        scheduler.request()
        with self.assertRaisesRegex(OSError,'Disk full'):scheduler.close()
        self.assertFalse(scheduler.stopped)
        scheduler.close()
        self.assertEqual(scheduler.status()['status'],'current')

    def test_new_request_during_capture_remains_pending(self):
        began=threading.Event();release=threading.Event()
        def capture():began.set();release.wait(1)
        scheduler=self.scheduler(capture,delay=.01)
        scheduler.request();self.assertTrue(began.wait(1));scheduler.request();release.set()
        self.wait_for(lambda:scheduler.status()['completed_sequence']==2)
        self.assertFalse(scheduler.status()['pending'])
