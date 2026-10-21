import contextlib
import unittest
from types import SimpleNamespace
from disco.navigation.publication_changes import capture_changes, PreparationRequired


class CaptureTests(unittest.TestCase):
    def test_after_images_are_read_before_exit_and_failure_never_returns_them(self):
        events=[]
        class Tracker:
            @contextlib.contextmanager
            def capture(self,prior,**kwargs):
                events.append('enter')
                yield SimpleNamespace(complete=True,watermark=2,verify=lambda:events.append('verify'))
                events.append('exit')
            def token(self):return 2
        result=capture_changes(Tracker(),1,lambda plan:events.append('read') or ['detached'])
        self.assertEqual(result,(2,['detached']))
        self.assertEqual(events,['enter','read','verify','exit'])
        class Failed(Tracker):
            @contextlib.contextmanager
            def capture(self,prior,**kwargs):
                with super().capture(prior,**kwargs) as plan:yield plan
                raise RuntimeError('commit failed')
        with self.assertRaises(RuntimeError):capture_changes(Failed(),1,lambda plan:['not published'])

    def test_gap_or_postcapture_race_requires_preparation(self):
        class Tracker:
            complete=False
            @contextlib.contextmanager
            def capture(self,prior,**kwargs):
                yield SimpleNamespace(complete=self.complete,watermark=2,verify=lambda:None)
            def token(self):return 3
        tracker=Tracker()
        with self.assertRaises(PreparationRequired):capture_changes(tracker,1,lambda plan:self.fail('gap read'))
        tracker.complete=True
        with self.assertRaises(PreparationRequired):capture_changes(tracker,1,lambda plan:[])


if __name__=='__main__':unittest.main()
