"""Opening an explicit existing project must never initialize arbitrary folders."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
from flask import Flask
from workspace_launcher import create_launcher, register_project_routes

class OpenFolderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        index = patch.dict(os.environ, {'RIEKE_PROJECT_INDEX': str(self.root / 'preferences/project-index.json')})
        index.start(); self.addCleanup(index.stop)
        self.current=self.project('workspace/current')
        self.other=self.project('other-workspace/other')
        self.client=create_launcher(self.current.parent,self.root/'parser').test_client()
        self.headers={'X-Workspace-Request':'1'}

    def project(self,name,identity=None):
        path=self.root/name; path.mkdir(parents=True)
        identity=identity or str(uuid.uuid4())
        (path/'project.json').write_text(json.dumps({'format':'recording-project','version':1,'project_uuid':identity,'name':name}))
        (path/'catalog.json').write_text(json.dumps({'format':'recording-catalog-reference','version':1,'project_uuid':identity}))
        return path

    def post(self,path,**kwargs):
        return self.client.post('/api/projects/open-folder',json={'directory':str(path)},headers=kwargs.get('headers',self.headers))

    def test_explicit_other_workspace_opens_exact_project_without_rewriting_manifests(self):
        before={p.name:p.read_bytes() for p in self.other.iterdir()}
        identity=json.loads(before['project.json'])['project_uuid']
        with patch('workspace_launcher.open_project',return_value={'url':'http://127.0.0.1:8877/','project_uuid':identity}) as opened:
            response=self.post(self.other)
            self.assertEqual(response.status_code,200)
            opened.assert_called_once_with(self.other.resolve(),identity,self.root/'parser')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.other.iterdir()})

    def test_external_open_is_remembered_after_launcher_restart(self):
        identity = json.loads((self.other / 'project.json').read_text())['project_uuid']
        with patch('workspace_launcher.open_project', return_value={'url': 'http://127.0.0.1:8877/', 'project_uuid': identity}):
            self.assertEqual(self.post(self.other).status_code, 200)
        restarted = create_launcher(self.current.parent, self.root / 'parser').test_client()
        inventory = restarted.get('/api/projects').get_json()
        external = next(project for project in inventory['projects'] if project['path'] == str(self.other.resolve()))
        self.assertTrue(external['available'])
        self.assertEqual(inventory['last_project_path'], str(self.other.resolve()))
        with patch('workspace_launcher.open_project', return_value={'url': 'http://127.0.0.1:8877/', 'project_uuid': identity}) as opened:
            response = restarted.post('/api/projects/' + identity + '/open', json={}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            opened.assert_called_once_with(self.other.resolve(), identity, self.root / 'parser')

    def test_new_project_at_arbitrary_root_is_indexed_without_parent_workspace(self):
        directory = self.root / 'independent' / 'user chosen study'
        response = self.client.post('/api/projects', json={'name': 'Independent study',
            'project_directory': str(directory)}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        inventory = create_launcher(self.current.parent, self.root / 'parser').test_client().get('/api/projects').get_json()
        self.assertIn(str(directory.resolve()), [project['path'] for project in inventory['projects']])
        self.assertFalse((directory.parent / '.rieke-workspace.json').exists())

    def test_completed_creation_is_reported_when_local_index_cannot_save(self):
        directory = self.root / 'created despite profile error'
        with patch('workspace_startup_registry.remember_project_path', side_effect=OSError('Profile disk is full')):
            response = self.client.post('/api/projects', json={'name': 'Completed creation',
                'project_directory': str(directory)}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()['project']['path'], str(directory.resolve()))
        self.assertIn('registry_warning', response.get_json())
        self.assertTrue((directory / 'project.json').is_file())

    def test_invalid_paths_and_bodies_never_start_services(self):
        empty=self.root/'empty';empty.mkdir()
        alias=self.root/'alias';alias.symlink_to(self.other,target_is_directory=True)
        with patch('workspace_launcher.open_project') as opened:
            for path in [self.root/'absent',self.other.parent,empty,alias,'relative/path']:
                with self.subTest(path=path):self.assertEqual(self.post(path).status_code,400)
            for body in [{}, {'directory':[]},{'directory':' '},{'directory':str(self.other),'extra':True}]:
                self.assertEqual(self.client.post('/api/projects/open-folder',json=body,headers=self.headers).status_code,400)
            opened.assert_not_called()
        self.assertFalse((self.root/'absent').exists())

    def test_bad_catalog_or_linked_manifest_never_starts(self):
        (self.other/'catalog.json').write_text(json.dumps({'format':'recording-catalog-reference','version':1,'project_uuid':str(uuid.uuid4())}))
        with patch('workspace_launcher.open_project') as opened:
            self.assertEqual(self.post(self.other).status_code,400)
            (self.other/'catalog.json').unlink();(self.other/'catalog.json').symlink_to(self.current/'catalog.json')
            self.assertEqual(self.post(self.other).status_code,400)
            opened.assert_not_called()

    def test_current_reuses_url_and_duplicate_identity_is_rejected(self):
        app=Flask(__name__)
        app.register_error_handler(ValueError,lambda error:({'error':str(error)},400))
        register_project_routes(app,retinanalysis_dir=self.root/'parser',project_dir=self.current)
        self.client=app.test_client()
        identity=json.loads((self.current/'project.json').read_text())['project_uuid']
        duplicate=self.project('duplicate',identity)
        with patch('workspace_launcher.open_project') as opened:
            response=self.post(self.current)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.get_json()['project_uuid'],identity)
            self.assertEqual(response.get_json()['url'],'http://localhost/')
            self.assertEqual(self.post(duplicate).status_code,400)
            opened.assert_not_called()

    def test_local_mutation_protection_applies(self):
        with patch('workspace_launcher.open_project') as opened:
            self.assertEqual(self.post(self.other,headers={}).status_code,403)
            self.assertEqual(self.post(self.other,headers={**self.headers,'Origin':'https://foreign.example'}).status_code,403)
            opened.assert_not_called()

    def test_normal_folder_inspection_detects_received_package_and_requires_restore(self):
        import workspace_portability as transfer
        package = self.root / 'received-package'
        package.mkdir()
        project = json.loads((self.other / 'project.json').read_text())
        transfer._write(package / 'project.json', project)
        (package / 'database.sql').write_text('-- logical backup fixture\n')
        transfer._write(package / transfer.MANIFEST, {'format': transfer.FORMAT,
            'version': 1, 'mode': 'complete', 'database_format': 'mysql8-logical-v1',
            'project_uuid': project['project_uuid'], 'sources': [], 'files': transfer._files(package)})
        before = {p.name: p.read_bytes() for p in package.iterdir()}
        with patch('workspace_launcher.open_project') as opened:
            response = self.client.post('/api/projects/inspect-folder',
                json={'directory': str(package)}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()['kind'], 'prepared-transfer')
            response = self.post(package)
            self.assertEqual(response.status_code, 400)
            self.assertIn('restore', response.get_json()['error'])
            opened.assert_not_called()
        self.assertEqual(before, {p.name: p.read_bytes() for p in package.iterdir()})

    def test_explicit_restored_instance_can_open_without_merging_original(self):
        app=Flask(__name__)
        register_project_routes(app,retinanalysis_dir=self.root/'parser',project_dir=self.current)
        self.client=app.test_client()
        identity=json.loads((self.current/'project.json').read_text())['project_uuid']
        restored=self.project('restored-copy',identity)
        instance=str(uuid.uuid4())
        owned={'project_uuid':identity,'instance_uuid':instance,
               'container':'rieke-os-'+identity.replace('-','')+'-'+instance.replace('-','')}
        catalog=json.loads((restored/'catalog.json').read_text());catalog['managed_database']=owned
        (restored/'catalog.json').write_text(json.dumps(catalog))
        (restored/'database').mkdir();(restored/'database/service.json').write_text(json.dumps(owned))
        with patch('workspace_launcher.open_project',return_value={'url':'http://127.0.0.1:8877/','project_uuid':identity}) as opened:
            self.assertEqual(self.post(restored).status_code,200)
            opened.assert_called_once_with(restored.resolve(),identity,self.root/'parser')
