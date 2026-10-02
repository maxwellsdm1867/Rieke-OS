"""All paths/catalogs here are disposable; no live scientific data is read."""
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from flask import Flask, jsonify
from workspace_launcher import register_project_routes
from workspace_lifecycle import register_project_lifecycle
from workspace_projects import create_project_at, list_managed_projects, list_projects
from workspace_startup_registry import remember_project_path, read_project_index, unmount_project_record


class UnmountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        env = patch.dict(os.environ, {'RIEKE_PROJECT_INDEX': str(self.root / 'profile/index.json')})
        env.start(); self.addCleanup(env.stop)
        self.project = create_project_at(str(self.root / 'projects/one'), 'One')
        self.other = create_project_at(str(self.root / 'projects/two'), 'Two')
        self.path = Path(self.project['path'])
        for name in ('recordings/sample.h5', 'annotations/tags.json', 'exports/export.json', 'backups/snapshot.json', 'database/scientific-fixture.bin'):
            file = self.path / name; file.parent.mkdir(exist_ok=True); file.write_bytes(b'preserved scientific content\0')
        remember_project_path(self.path, set_last=True)
        self.body = {'path': str(self.path), 'project_uuid': self.project['uuid']}
        self.stop = Mock(); self.shutdown = threading.Event()

    def app(self, current=False, busy=lambda:False):
        app = Flask(__name__)
        app.register_error_handler(ValueError, lambda error: (jsonify(error=str(error)), 400))
        register_project_routes(app, retinanalysis_dir=self.root, **({'project_dir': self.path} if current else {'root':self.path.parent}))
        if current:
            app.extensions['shutdown_project_server'] = self.shutdown.set
            register_project_lifecycle(app, busy=busy, stop_database=self.stop)
        return app

    def hashes(self):
        return {str(file.relative_to(self.path)):hashlib.sha256(file.read_bytes()).hexdigest() for file in self.path.rglob('*') if file.is_file()}

    def test_inactive_exact_idempotent_unmount_restart_and_explicit_remount(self):
        before = self.hashes(); client = self.app().test_client()
        result = client.post('/api/projects/unmount',json=self.body)
        self.assertEqual(result.status_code,200, result.json)
        self.assertEqual(result.json['state'],'unmounted')
        self.assertEqual([p['path'] for p in list_managed_projects(self.path.parent)['projects']], [self.other['path']])
        self.assertIsNone(read_project_index()['last_project_path'])
        self.assertTrue(self.app().test_client().post('/api/projects/unmount',json=self.body).json['already_unmounted'])
        for name, digest in before.items():self.assertEqual(self.hashes()[name],digest)
        with patch('workspace_launcher.open_project', return_value={'url':'http://127.0.0.1:9999/','project_uuid':self.project['uuid']}) as opened:
            result = client.post('/api/projects/open-folder', json={'directory':str(self.path)})
            self.assertEqual(result.status_code,200,result.json); opened.assert_called_once()
        self.assertEqual({p['path'] for p in list_managed_projects(self.path.parent)['projects']},{str(self.path),self.other['path']})
        self.assertEqual(read_project_index()['unmounted'],[])
        for name, digest in before.items():self.assertEqual(self.hashes()[name],digest)

    def test_active_close_precedes_catalog_detach_and_no_requests_after(self):
        before = self.hashes()
        self.stop.side_effect=lambda:self.assertEqual(len(list_managed_projects(self.path.parent)['projects']),2)
        client=self.app(current=True).test_client()
        response=client.post('/api/projects/unmount',json=self.body)
        self.assertEqual(response.status_code,200,response.json);self.assertTrue(response.json['closed'])
        self.stop.assert_called_once();self.assertTrue(self.shutdown.wait(1))
        self.assertEqual(client.get('/api/projects').status_code,503)
        for name,digest in before.items():self.assertEqual(self.hashes()[name],digest)

    def test_pending_import_or_background_export_refuses_without_detach(self):
        for kind in ('import','export'):
            app=self.app(current=True,busy=lambda:kind=='import')
            app.extensions['app_active_writers']=lambda:kind=='export'
            response=app.test_client().post('/api/projects/unmount',json=self.body)
            self.assertEqual(response.status_code,409,response.json)
            self.assertEqual(read_project_index().get('unmounted',[]),[])
        self.stop.assert_not_called()

    def test_admitted_accept_finishes_before_close_no_cancellation(self):
        app=self.app(current=True);started=threading.Event();finish=threading.Event()
        @app.post('/accept')
        def accept():
            started.set();finish.wait(5);return jsonify(saved=True)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            accepted=pool.submit(lambda:app.test_client().post('/accept'))
            self.assertTrue(started.wait(1))
            unmount=pool.submit(lambda:app.test_client().post('/api/projects/unmount',json=self.body))
            self.assertFalse(self.shutdown.wait(.1));self.stop.assert_not_called()
            finish.set();self.assertTrue(accepted.result(2).json['saved'])
            self.assertEqual(unmount.result(2).status_code,200)
        self.assertTrue(self.shutdown.wait(1))

    def test_failed_close_keeps_mounted_and_registry_failure_is_honest(self):
        self.stop.side_effect=ValueError('Ownership not proven')
        client=self.app(current=True).test_client()
        self.assertEqual(client.post('/api/projects/unmount',json=self.body).status_code,500)
        self.assertEqual(len(list_managed_projects(self.path.parent)['projects']),2)
        self.stop.side_effect=None
        with patch('workspace_project_unmount.unmount_project_record',side_effect=OSError('disk full')):
            response=client.post('/api/projects/unmount',json=self.body)
        self.assertEqual(response.status_code,507);self.assertEqual(response.json['state'],'closed')
        self.assertFalse(response.json['unmounted']);self.assertTrue(self.shutdown.wait(1))
        self.assertEqual(len(list_managed_projects(self.path.parent)['projects']),2)

    def test_inactive_owned_session_and_native_process_refuse_without_signalling(self):
        client=self.app().test_client()
        with (self.path/'.app-state-session.lock').open('w') as owner:
            fcntl.flock(owner,fcntl.LOCK_EX)
            self.assertEqual(client.post('/api/projects/unmount',json=self.body).status_code,409)
        (self.path/'database/native-runtime.json').write_text(json.dumps({'pid':os.getpid()}))
        self.assertEqual(client.post('/api/projects/unmount',json=self.body).status_code,409)
        self.assertEqual(read_project_index().get('unmounted',[]),[])

    def test_missing_path_can_detach_saved_reference_and_unknown_identity_cannot(self):
        # Rename disposable fixture to simulate a disconnected/moved drive.
        self.path.rename(self.path.with_name('moved'))
        client=self.app().test_client()
        self.assertFalse(next(p for p in client.get('/api/projects').json['projects'] if p['path']==str(self.path))['available'])
        self.assertEqual(client.post('/api/projects/unmount',json={**self.body,'project_uuid':self.other['uuid']}).status_code,409)
        self.assertEqual(client.post('/api/projects/unmount',json=self.body).status_code,200)
        self.assertTrue(self.path.with_name('moved').is_dir())

    def test_desktop_unmount_uses_authenticated_drain_and_stop(self):
        from workspace_desktop import DesktopBoundary
        from werkzeug.test import Client
        from werkzeug.wrappers import Response
        app=Flask('desktop');register_project_routes(app,retinanalysis_dir=self.root,project_dir=self.path)
        app.extensions['desktop_stop_database']=self.stop
        app.extensions['shutdown_project_server']=self.shutdown.set
        pending=[True];app.extensions['project_active_writers']=lambda:pending[0]
        boundary=DesktopBoundary(app,port=9998,capability='u'*48,identity={},deadline=.01)
        boundary.stop_callback=self.shutdown.set
        client=Client(boundary,Response)
        options=dict(base_url='http://127.0.0.1:9998',json=self.body,environ_overrides={'REMOTE_ADDR':'127.0.0.1'})
        self.assertEqual(client.post('/api/projects/unmount',**options).status_code,403)
        options['headers']={'X-Rieke-Desktop-Session':boundary.renderer_session}
        self.assertEqual(client.post('/api/projects/unmount',**options).status_code,409)
        self.assertFalse(boundary.draining);self.stop.assert_not_called()
        pending[0]=False
        response=client.post('/api/projects/unmount',**options)
        self.assertEqual(response.status_code,200,response.json);self.stop.assert_called_once()
        self.assertTrue(response.json['closed']);self.assertTrue(self.shutdown.wait(1))
        self.assertEqual(len(list_managed_projects(self.path.parent)['projects']),1)

    def test_copied_native_identity_only_detaches_selected_folder(self):
        # Native folder copies may deliberately share scientific UUIDs.
        for name in ('project.json','catalog.json'):
            file=Path(self.other['path'])/name;data=json.loads(file.read_text());data['project_uuid']=self.project['uuid'];file.write_text(json.dumps(data))
        self.assertEqual(self.app().test_client().post('/api/projects/unmount',json=self.body).status_code,200)
        self.assertEqual([p['path'] for p in list_managed_projects(self.path.parent)['projects']],[self.other['path']])

if __name__=='__main__':unittest.main()
