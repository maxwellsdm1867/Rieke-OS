"""Actual read-only children and held-request shutdown, using owned fixtures."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from werkzeug.test import Client
from werkzeug.wrappers import Response

from disco.projects.project_inventory import ProjectInventory, ProjectInventoryUnavailable
from workspace_desktop import DesktopBoundary
from workspace_launcher import create_launcher
from workspace_projects import list_managed_projects, list_projects


class ProjectInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.managed = self.root / 'projects'
        self.managed.mkdir()
        self.index = self.root / 'preferences/project-index.json'
        environment = patch.dict(os.environ, {'RIEKE_PROJECT_INDEX': str(self.index),
            'RIEKE_DESKTOP_CAPABILITY': 'must-not-reach-the-read-worker'})
        environment.start()
        self.addCleanup(environment.stop)
        self.children = []
        self.spawned = threading.Event()
        self.addCleanup(self.reap)

    def reap(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)

    def held_read(self, command, **options):
        self.assertNotIn('RIEKE_DESKTOP_CAPABILITY', options['env'])
        self.assertNotIn('RIEKE_PARSER_CONFIG', options['env'])
        self.assertEqual(command[1:3], ['-I', '-B'])
        self.assertEqual(Path(command[3]).name, 'project_inventory.py')
        # This owned child performs only a held read substitute, never a DB job.
        child = subprocess.Popen([sys.executable, '-I', '-B', '-c',
            'import time; time.sleep(60)'], **options)
        self.children.append(child)
        self.spawned.set()
        return child

    def project(self, name, identity=None):
        folder = self.managed / name
        folder.mkdir()
        identity = identity or str(uuid.uuid4())
        (folder / 'project.json').write_text(json.dumps({'format': 'recording-project',
            'version': 1, 'project_uuid': identity, 'name': name, 'catalog_ref': 'catalog.json'}))
        (folder / 'catalog.json').write_text(json.dumps({'format': 'recording-catalog-reference',
            'version': 1, 'project_uuid': identity, 'managed_database': {'kind': 'native-mysql'},
            'connection': {'password': 'never-return-credentials'}}))
        return folder

    def snapshot(self):
        return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob('*') if path.is_file()}

    def launcher(self, inventory):
        frontend = self.root / 'frontend'
        frontend.mkdir()
        (frontend / 'index.html').write_text('<html><head></head><body><div id="root"></div></body></html>')
        with patch.dict(os.environ, {'RIEKE_DESKTOP_MODE': '1', 'RIEKE_DESKTOP_FRONTEND': str(frontend)}), \
                patch('disco.projects.project_inventory.ProjectInventory', return_value=inventory):
            app = create_launcher(self.managed, self.root / 'unused-parser')
        return app

    def test_real_children_preserve_exact_identity_and_never_write_or_return_credentials(self):
        first = self.project('first')
        identity = json.loads((first / 'project.json').read_text())['project_uuid']
        self.project('native-copy', identity)
        before = self.snapshot()
        inventory = ProjectInventory()
        self.assertEqual(inventory.managed(self.managed), list_managed_projects(self.managed))
        self.assertEqual(inventory.current(first), list_projects(first))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.index.parent.exists())
        self.assertNotIn('never-return-credentials', json.dumps(inventory.current(first)))

    def test_timeout_reaps_only_the_owned_read_worker(self):
        inventory = ProjectInventory(timeout=.15, process_factory=self.held_read)
        started = time.monotonic()
        with self.assertRaises(ProjectInventoryUnavailable):
            inventory.managed(self.managed)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(len(self.children), 1)
        self.assertIsNotNone(self.children[0].poll())

    def test_pause_cancels_read_without_waiting_for_its_deadline_and_resume_retries(self):
        inventory = ProjectInventory(timeout=20, process_factory=self.held_read)
        errors = []
        def read():
            try:
                inventory.managed(self.managed)
            except ProjectInventoryUnavailable as error:
                errors.append(error)
        thread = threading.Thread(target=read)
        thread.start()
        self.addCleanup(lambda: (inventory.pause(), thread.join(3)))
        self.assertTrue(self.spawned.wait(2))
        inventory.pause()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsNotNone(self.children[0].poll())
        with self.assertRaises(ProjectInventoryUnavailable):
            inventory.managed(self.managed)
        self.assertEqual(len(self.children), 1)
        inventory.process_factory = subprocess.Popen
        inventory.resume()
        self.assertEqual(inventory.managed(self.managed)['projects'], [])

    def test_initial_document_survives_timeout_as_unavailable_not_empty_success(self):
        inventory = ProjectInventory(timeout=.15, process_factory=self.held_read)
        app = self.launcher(inventory)
        result = app.test_client().get('/')
        self.assertEqual(result.status_code, 200)
        html = result.get_data(as_text=True)
        bootstrap = json.loads(html.split('id="rieke-projects-bootstrap">')[1].split('</script>')[0])
        self.assertTrue(bootstrap['launcher'])
        self.assertTrue(bootstrap['inventory_unavailable'])
        self.assertIn('folder access', bootstrap['inventory_error'])
        self.assertIsNone(bootstrap['current_project_uuid'])
        self.assertIsNotNone(self.children[0].poll())

    def test_inventory_api_reports_unavailable_and_reaps_its_reader(self):
        inventory = ProjectInventory(timeout=.15, process_factory=self.held_read)
        app = self.launcher(inventory)
        result = app.test_client().get('/api/projects')
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json['code'], 'project_inventory_unavailable')
        self.assertNotIn('projects', result.json)
        self.assertIsNotNone(self.children[0].poll())

    def test_quit_cancels_held_chooser_read_but_never_overrides_a_scientific_writer(self):
        inventory = ProjectInventory(timeout=20, process_factory=self.held_read)
        app = self.launcher(inventory)
        boundary = DesktopBoundary(app, port=8766, capability='x' * 48,
            identity={'pid': 1, 'session_id': 'fixture'}, deadline=.2)
        headers = {'X-Rieke-Desktop-Capability': 'x' * 48, 'X-Workspace-Request': '1'}
        responses = []
        def get():
            responses.append(Client(boundary, Response).get('/', base_url='http://127.0.0.1:8766',
                headers=headers, environ_overrides={'REMOTE_ADDR': '127.0.0.1'}, buffered=True))
        thread = threading.Thread(target=get)
        thread.start()
        self.addCleanup(lambda: (inventory.pause(), thread.join(3)))
        self.assertTrue(self.spawned.wait(2))
        app.extensions['project_active_writers'] = lambda: True
        def quit():
            return Client(boundary, Response).post('/api/desktop/quit',
                base_url='http://127.0.0.1:8766', headers=headers, json={},
                environ_overrides={'REMOTE_ADDR': '127.0.0.1'}, buffered=True)
        self.assertEqual(quit().status_code, 409)
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertIsNotNone(self.children[0].poll())
        self.assertEqual(boundary.active, 0)
        self.assertTrue(boundary.draining)
        app.extensions['project_active_writers'] = lambda: False
        self.assertEqual(quit().status_code, 200)
        self.assertEqual(responses[0].status_code, 200)

    def test_read_only_worker_policy_refuses_writes_deletion_and_network(self):
        sentinel = self.root / 'sentinel'
        sentinel.write_text('preserve')
        code = '''import os,sys,socket,sqlite3
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import workspace_projects
from disco.projects.project_inventory import main
operations=(lambda:Path(sys.argv[2]).write_text('changed'), lambda:os.unlink(sys.argv[2]), lambda:socket.socket(), lambda:sqlite3.connect(':memory:'))
workspace_projects.list_managed_projects=lambda folder:operations[int(sys.argv[3])]()
main(['managed',sys.argv[2]])
'''
        root = str(Path(__file__).resolve().parents[1])
        for action in range(4):
            result = subprocess.run([sys.executable, '-I', '-B', '-c', code, root, str(sentinel), str(action)],
                capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(json.loads(result.stdout), {'ok': False})
        self.assertEqual(sentinel.read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
