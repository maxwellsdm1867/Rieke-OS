import threading
import unittest
from unittest.mock import Mock

from disco.backup.backup_scheduler import BackupScheduler


class BackupSchedulerTests(unittest.TestCase):
    def scheduler(self,capture,**kwargs):
        return BackupScheduler(capture,threading.RLock(),**kwargs)

    def test_each_request_backs_up_synchronously_without_timer_or_thread(self):
        before=threading.active_count()
        capture=Mock();scheduler=self.scheduler(capture)
        self.assertEqual(threading.active_count(),before)
        self.assertFalse(any(isinstance(value,threading.Thread) for value in vars(scheduler).values()))
        for attribute in ('delay','max_delay','retry_delay','activity','worker'):
            self.assertFalse(hasattr(scheduler,attribute),attribute)
        for number in range(1,4):
            scheduler.request()
            self.assertEqual(capture.call_count,number)  # Before request() returns.
            self.assertEqual(scheduler.status()['status'],'current')
        scheduler.flush()
        self.assertEqual(capture.call_count,4)

    def test_request_runs_under_the_database_lock(self):
        lock=threading.RLock();held=[]
        scheduler=BackupScheduler(lambda:held.append(lock._is_owned()),lock)
        scheduler.request();scheduler.flush()
        self.assertEqual(held,[True,True])

    def test_failed_backup_is_visible_without_raising_and_next_save_retries(self):
        logger=Mock()
        capture=Mock(side_effect=[OSError('Disk full'),None])
        scheduler=self.scheduler(capture,logger=logger)
        scheduler.request()  # The SQL edit is committed: never raise here.
        logger.exception.assert_called_once()
        self.assertEqual(scheduler.status()['status'],'degraded')
        self.assertTrue(scheduler.status()['pending'])
        self.assertEqual(scheduler.status()['last_error'],'Disk full')
        scheduler.request()
        self.assertEqual(scheduler.status()['status'],'current')
        self.assertFalse(scheduler.status()['pending'])

    def test_flush_failure_propagates_and_failed_close_stays_open(self):
        capture=Mock(side_effect=[OSError('Disk full'),None])
        scheduler=self.scheduler(capture)
        with self.assertRaisesRegex(OSError,'Disk full'):scheduler.close()
        self.assertFalse(scheduler.stopped)
        self.assertEqual(scheduler.status()['status'],'degraded')
        scheduler.close()
        self.assertTrue(scheduler.stopped)
        self.assertEqual(scheduler.status()['status'],'current')

    def test_flush_inside_held_database_lock_does_not_deadlock(self):
        capture=Mock();scheduler=self.scheduler(capture)
        with scheduler.database_lock:
            scheduler.request()
            scheduler.flush()
            scheduler.close(flush=False)
        self.assertEqual(capture.call_count,2)

    def test_request_after_close_is_reported_not_captured(self):
        capture=Mock();scheduler=self.scheduler(capture)
        scheduler.close(flush=False)
        scheduler.request()
        capture.assert_not_called()
        self.assertEqual(scheduler.status()['status'],'degraded')

    def test_concurrent_request_waits_for_the_running_capture_then_captures(self):
        began=threading.Event();release=threading.Event();calls=[]
        def capture():
            calls.append(1)
            if len(calls)==1:began.set();release.wait(2)
        scheduler=self.scheduler(capture)
        first=threading.Thread(target=scheduler.request);first.start()
        self.assertTrue(began.wait(2))
        second=threading.Thread(target=scheduler.request);second.start()
        self.assertEqual(len(calls),1)  # Serialized by the database lock.
        release.set();first.join(2);second.join(2)
        self.assertEqual(len(calls),2)
        self.assertEqual(scheduler.status()['completed_sequence'],2)
        self.assertFalse(scheduler.status()['pending'])
