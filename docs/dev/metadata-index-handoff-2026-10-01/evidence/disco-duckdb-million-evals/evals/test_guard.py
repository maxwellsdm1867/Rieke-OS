"""Failure-mode tests for protecting the running app during experiments."""
import json,runpy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch

GUARD=Path(__file__).with_name('guard.py')
class GuardFailures(unittest.TestCase):
 def test_failed_preflight_never_launches_worker(self):
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory)/'guard'
   with patch.object(sys,'argv',[str(GUARD),'--out',str(out),'--','/usr/bin/true']),patch('psutil.Process') as process,patch('subprocess.Popen') as spawn:
    process.return_value.children.side_effect=PermissionError('enumeration denied')
    with self.assertRaises(SystemExit) as exit:runpy.run_path(str(GUARD),run_name='__main__')
    self.assertEqual(exit.exception.code,1);spawn.assert_not_called()
   report=json.loads((out/'guard.json').read_text());self.assertFalse(report['passed']);self.assertNotIn('owned_pid',report)
 def test_supervisor_failure_after_launch_stops_owned_worker(self):
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory)/'guard';owned=Mock(pid=123)
   state={'alive':True}
   owned.poll.side_effect=lambda:None if state['alive'] else -15
   owned.terminate.side_effect=lambda:state.update(alive=False)
   owned.wait.return_value=-15
   preflight=Mock();preflight.children.return_value=[]
   monitored=Mock();monitored.children.side_effect=PermissionError('enumeration lost')
   with patch.object(sys,'argv',[str(GUARD),'--out',str(out),'--','/usr/bin/true']),patch('psutil.Process',side_effect=[preflight,monitored,monitored]),patch('psutil.virtual_memory'),patch('psutil.disk_usage'),patch('subprocess.Popen',return_value=owned):
    with self.assertRaises(SystemExit) as exit:runpy.run_path(str(GUARD),run_name='__main__')
    self.assertEqual(exit.exception.code,1)
   owned.terminate.assert_called_once();owned.wait.assert_called_once()
   report=json.loads((out/'guard.json').read_text());self.assertFalse(report['passed']);self.assertEqual(report['owned_pid'],123)
if __name__=='__main__':unittest.main()
