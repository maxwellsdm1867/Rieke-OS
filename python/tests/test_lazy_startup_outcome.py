import json,os,sys,unittest,tempfile,threading
from unittest.mock import Mock
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_desktop import validate_child_startup_receipt,initialize_before_project_database,DesktopServices
class PrivateOutcome(unittest.TestCase):
 def setUp(self):
  self.record=dict(pid=17,session_id='123',port=9000,project_uuid='project',project_path='/owned',application_version='1',source_commit='abc')
 def receipt(self,**changed):
  return 'RIEKE_DESKTOP_STARTUP_FAILED='+json.dumps({**self.record,'ready':False,'stage':'before_project_database',**changed})
 def test_matching_negative_is_not_ready(self):
  self.assertEqual(validate_child_startup_receipt(self.receipt(),self.record),dict(valid=False,pre_database_failed=True))
 def test_identity_and_later_stage_cannot_authorize_removal(self):
  for key in self.record:
   with self.subTest(key=key),self.assertRaises(ValueError):validate_child_startup_receipt(self.receipt(**{key:'wrong'}),self.record)
  for change in [dict(stage='after_database'),dict(ready=True)]:
   with self.assertRaises(ValueError):validate_child_startup_receipt(self.receipt(**change),self.record)
 def test_malformed_and_oversized_fail_closed(self):
  for line in ['RIEKE_DESKTOP_STARTUP_FAILED=[]','RIEKE_DESKTOP_STARTUP_FAILED={','x'*65537]:
   with self.assertRaises(ValueError):validate_child_startup_receipt(line,self.record)
 def test_failure_emitted_on_real_pipe_then_original_error_reraised(self):
  with tempfile.TemporaryDirectory() as folder:
   project=Path(folder);(project/'catalog.json').write_text('{"project_uuid":"project"}')
   read,write=os.pipe();args=SimpleNamespace(project_dir=project,ready_fd=write,session_id='00000000-0000-0000-0000-000000000001',port=9000)
   def fail():raise RuntimeError('parser failed')
   with self.assertRaisesRegex(RuntimeError,'parser failed'):initialize_before_project_database(args,dict(application_version='1',source_commit='abc'),fail)
   with os.fdopen(read) as handle:packet=json.loads(handle.read().split('=',1)[1])
   self.assertEqual(packet['stage'],'before_project_database');self.assertFalse(packet['ready']);self.assertEqual(packet['pid'],os.getpid())
class DelayedReceipt(unittest.TestCase):
 def test_late_private_reader_reconciles_exited_child_after_initial_wait(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);services=DesktopServices(root,root/'resources',root/'manifest','session','s'*48,{})
   process=Mock();process.poll.return_value=1
   record=dict(pid=17,session_id='session',port=9000,project_uuid='id',project_path=str(root/'project'),application_version='1',source_commit='abc',bound=False)
   services.children['project']=dict(record=record,process=process)
   release=threading.Event();finished=threading.Event()
   def reader():
    release.wait();services.accept_startup_receipt('project',process,'RIEKE_DESKTOP_STARTUP_FAILED='+json.dumps({**record,'stage':'before_project_database','ready':False}));finished.set()
   thread=threading.Thread(target=reader);thread.start()
   try:
    self.assertFalse(finished.wait(1.05))
    self.assertEqual(len(services.records()),1)
    release.set();self.assertTrue(finished.wait(1));thread.join()
    self.assertEqual(services.records(),[])
    self.assertEqual(json.loads(services.path.read_text())['services'],[])
    process.terminate.assert_not_called();process.kill.assert_not_called()
   finally:release.set();thread.join()
 def test_live_or_replaced_process_cannot_be_removed(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);services=DesktopServices(root,root/'resources',root/'manifest','session','s'*48,{})
   process=Mock();process.poll.return_value=None
   record=dict(pid=17,session_id='session',port=9000,project_uuid='id',project_path=str(root/'project'),application_version='1',source_commit='abc',bound=False)
   services.children['project']=dict(record=record,process=process)
   line='RIEKE_DESKTOP_STARTUP_FAILED='+json.dumps({**record,'stage':'before_project_database','ready':False})
   with self.assertRaises(ValueError):services.accept_startup_receipt('project',Mock(),line)
   services.accept_startup_receipt('project',process,line);self.assertEqual(len(services.records()),1)
   process.poll.return_value=1;self.assertEqual(services.records(),[])
if __name__=='__main__':unittest.main()
