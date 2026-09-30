import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from workspace_projects import create_project, list_managed_projects
from workspace_startup_registry import remember_project, read_registry
from workspace_launcher import create_launcher
from workspace_project_database import ensure_project_database


class ProjectStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'managed'
        isolated_index=patch.dict(os.environ,{'RIEKE_PROJECT_INDEX':str(Path(self.temp.name)/'user-state/project-index.json')})
        isolated_index.start();self.addCleanup(isolated_index.stop)
        native_start=patch('workspace_native_mysql.ensure_native_database',side_effect=AssertionError('Unit startup tests must not start a native server'))
        native_start.start();self.addCleanup(native_start.stop)

    def test_zero_projects_welcome_requires_no_database_or_h5(self):
        app=create_launcher(self.root, self.root/'unused-retinanalysis')
        client=app.test_client()
        with patch('workspace_project_database._run') as docker:
            result=client.get('/api/projects').get_json()
            self.assertEqual(result['projects'],[])
            self.assertTrue(result['launcher'])
            self.assertIsNone(result['current_project_uuid'])
            self.assertIsNone(result['last_project_uuid'])
            docker.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_new_projects_are_empty_and_isolated_and_survive_rediscovery(self):
        first=create_project(self.root,'First study')
        second=create_project(self.root,'Second study')
        self.assertNotEqual(first['uuid'],second['uuid'])
        catalogs=[]
        for project in [first,second]:
            folder=Path(project['path'])
            catalog=json.loads((folder/'catalog.json').read_text())
            catalogs.append(catalog)
            self.assertEqual(catalog['project_uuid'],project['uuid'])
            self.assertEqual(list((folder/'protocols').iterdir()),[])
            self.assertEqual(list((folder/'imports').iterdir()),[])
            self.assertEqual(list((folder/'raw-uploads').iterdir()),[])
            self.assertNotIn('password',json.dumps(catalog).lower())
            self.assertFalse((folder/'database/mysql').exists())
        self.assertNotEqual(catalogs[0]['managed_database']['instance_uuid'],catalogs[1]['managed_database']['instance_uuid'])
        for catalog in catalogs:
            self.assertEqual(catalog['connection']['credential_provider']['kind'],'native-project')
            self.assertNotIn('container',catalog['managed_database'])
        remember_project(self.root,second['uuid'])
        result=list_managed_projects(self.root)
        self.assertEqual(result['last_project_uuid'],second['uuid'])
        self.assertEqual(len(result['projects']),2)
        self.assertEqual(read_registry(self.root)['last_project_uuid'],second['uuid'])

    def test_duplicate_name_and_nonempty_or_escaping_paths_fail_without_overwrite(self):
        project=create_project(self.root,'Study')
        before=(Path(project['path'])/'project.json').read_bytes()
        with self.assertRaises(ValueError):create_project(self.root,' study ')
        with self.assertRaises(ValueError):create_project(self.root,'Different',directory=project['path'])
        for path in ['../escape','a/b','.hidden']:
            with self.assertRaises(ValueError):create_project(self.root,'Escape',directory=path)
        self.assertEqual((Path(project['path'])/'project.json').read_bytes(),before)
        (self.root/'alias').symlink_to(Path(project['path']),target_is_directory=True)
        with self.assertRaises(ValueError):create_project(self.root,'Linked',directory='alias')
        self.assertEqual(len(list_managed_projects(self.root)['projects']),1)

    def test_precreated_empty_folder_accepted_and_creation_has_no_docker_side_effect(self):
        folder=self.root/'chosen';folder.mkdir(parents=True)
        with patch('workspace_project_database._run') as docker:
            project=create_project(self.root,'Chosen',directory=str(folder))
            self.assertEqual(project['path'],str(folder.resolve()))
            docker.assert_not_called()

    def test_api_validation_and_csrf_guard(self):
        client=create_launcher(self.root,self.root/'retinanalysis').test_client()
        self.assertEqual(client.post('/api/projects',json={'name':'One'}).status_code,403)
        headers={'X-Workspace-Request':'1'}
        response=client.post('/api/projects',json={'name':'One'},headers=headers)
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.get_json()['database_status'],'not_started')
        created=Path(response.get_json()['project']['path'])
        catalog=json.loads((created/'catalog.json').read_text())
        self.assertEqual(catalog['connection']['credential_provider']['kind'],'native-project')
        self.assertEqual(catalog['managed_database']['kind'],'native-mysql')
        self.assertFalse((created/'database/mysql').exists())
        self.assertEqual(client.post('/api/projects',json={'name':'One'},headers=headers).status_code,400)
        self.assertEqual(client.post('/api/projects',json={'name':'Two','source':'copied.h5'},headers=headers).status_code,400)
        self.assertEqual(client.post('/api/projects',json={'name':'Two'},headers={**headers,'Origin':'https://foreign.example'}).status_code,403)

    def test_create_in_chosen_root_preserves_existing_folders(self):
        client=create_launcher(self.root,self.root/'retinanalysis').test_client()
        headers={'X-Workspace-Request':'1'}
        other=self.root/'another workspace'
        response=client.post('/api/projects',json={'name':'Elsewhere','root_directory':str(other),'directory':'study'},headers=headers)
        self.assertEqual(response.status_code,201)
        folder=Path(response.get_json()['project']['path'])
        self.assertEqual(folder,(other/'study').resolve())
        before=(folder/'project.json').read_bytes()
        duplicate=client.post('/api/projects',json={'name':'Other','root_directory':str(other),'directory':'study'},headers=headers)
        self.assertEqual(duplicate.status_code,400)
        self.assertEqual((folder/'project.json').read_bytes(),before)
        for root in ['', 'relative', 42]:
            self.assertEqual(client.post('/api/projects',json={'name':'Bad','root_directory':root},headers=headers).status_code,400)

    def test_exact_project_folder_is_independent_of_preferred_location(self):
        client=create_launcher(self.root,self.root/'retinanalysis').test_client()
        headers={'X-Workspace-Request':'1'}
        chosen=self.root.parent/'anywhere'/'my study'
        response=client.post('/api/projects',json={'name':'Exact folder','project_directory':str(chosen)},headers=headers)
        self.assertEqual(response.status_code,201,response.get_json())
        self.assertEqual(response.get_json()['project']['path'],str(chosen.resolve()))
        self.assertTrue((chosen/'project.json').is_file())
        self.assertFalse(self.root.exists())
        before=(chosen/'project.json').read_bytes()
        self.assertEqual(client.post('/api/projects',json={'name':'Other','project_directory':str(chosen)},headers=headers).status_code,400)
        self.assertEqual((chosen/'project.json').read_bytes(),before)
        for body in [{'name':'Bad','project_directory':'relative'}, {'name':'Bad','project_directory':str(chosen),'root_directory':str(self.root)}]:
            self.assertEqual(client.post('/api/projects',json=body,headers=headers).status_code,400)

    def test_exact_folder_accepts_system_alias_parent_but_not_linked_project(self):
        from workspace_projects import create_project_at
        actual=self.root.parent/'actual';actual.mkdir()
        alias=self.root.parent/'alias';alias.symlink_to(actual,target_is_directory=True)
        record=create_project_at(str(alias/'study'),'System path')
        self.assertEqual(record['path'],str((actual/'study').resolve()))
        link=actual/'project-link';link.symlink_to(actual/'study',target_is_directory=True)
        with self.assertRaises(ValueError):create_project_at(str(link),'No linked roots')

    def test_project_may_be_next_to_application_but_never_inside_it(self):
        from workspace_projects import create_project_at
        app=self.root.parent/'app';app.mkdir()
        chosen=self.root.parent/'research'
        record=create_project_at(str(chosen),'Research',code_root=app)
        self.assertEqual(record['path'],str(chosen.resolve()))
        for path in [app/'project', app, app.parent]:
            with self.assertRaises(ValueError):create_project_at(str(path),'Bad',code_root=app)

    def test_open_route_passes_uuid_and_remains_separate_from_creation(self):
        project=create_project(self.root,'Route test')
        client=create_launcher(self.root,self.root/'retinanalysis').test_client()
        expected={'url':'http://127.0.0.1:45678/','project_uuid':project['uuid']}
        with patch('workspace_launcher.open_project',return_value=expected) as opened:
            response=client.post(f"/api/projects/{project['uuid']}/open",json={},headers={'X-Workspace-Request':'1'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.get_json(),expected)
            self.assertEqual(opened.call_args.args[1],project['uuid'])
            self.assertEqual(opened.call_args.args[0], Path(project['path']))
            self.assertNotIn('managed', opened.call_args.kwargs)

    def _legacy_project(self,name):
        """Legacy tests explicitly retain Docker descriptors after the default changed."""
        project=create_project(self.root,name)
        identity=project['uuid'];container='rieke-os-'+identity.replace('-','')
        descriptor={'version':1,'project_uuid':identity,'container':container,
                    'image':'datajoint/mysql:8.0','storage_ref':'database/mysql'}
        catalog={'format':'recording-catalog-reference','version':1,'project_uuid':identity,
            'adapter':'datajoint','database':'schema','workspace_database':'recording_workspace',
            'connection':{'host':'127.0.0.1','port':None,
                          'credential_provider':{'kind':'docker-container-env','container':container}},
            'managed_database':descriptor}
        root=Path(project['path'])
        (root/'catalog.json').write_text(json.dumps(catalog))
        (root/'database/service.json').write_text(json.dumps(descriptor))
        return project

    def _info(self,project):
        return {'Config':{'Labels':{'rieke-os.project_uuid':project['uuid'],'rieke-os.project_path':project['path']}},
                'State':{'Running':True},'HostConfig':{'PortBindings':{'3306/tcp':[{'HostIp':'127.0.0.1','HostPort':'44001'}]}},
                'Mounts':[{'Type':'bind','Destination':'/var/lib/mysql','Source':str(Path(project['path'])/'database/mysql')}]}

    def test_database_created_only_on_open_with_owned_storage_and_private_random_password(self):
        project=self._legacy_project('Owned')
        info=self._info(project)
        result=lambda code=0,stdout='':SimpleNamespace(returncode=code,stdout=stdout,stderr='')
        with patch('workspace_project_database._run',side_effect=[result(),result(1),result(),result(stdout=json.dumps([info])),result(stdout='1')]) as run:
            ensure_project_database(project['path'])
            create=run.call_args_list[2]
            self.assertIn('127.0.0.1::3306',create.args[0])
            self.assertIn(f"rieke-os.project_uuid={project['uuid']}",create.args[0])
            self.assertGreater(len(create.kwargs['env']['MYSQL_ROOT_PASSWORD']),30)
            self.assertNotIn(create.kwargs['env']['MYSQL_ROOT_PASSWORD'],' '.join(create.args[0]))

    def test_existing_database_reopened_without_recreation_and_wrong_owner_rejected(self):
        project=self._legacy_project('Owned')
        info=self._info(project)
        result=lambda stdout='':SimpleNamespace(returncode=0,stdout=stdout,stderr='')
        with patch('workspace_project_database._run',side_effect=[result(),result(json.dumps([info])),result('1')]) as run:
            ensure_project_database(project['path'])
            self.assertFalse(any(call.args[0][0]=='run' for call in run.call_args_list))
        info['Config']['Labels']['rieke-os.project_uuid']='foreign'
        with patch('workspace_project_database._run',side_effect=[result(),result(json.dumps([info]))]) as run:
            with self.assertRaisesRegex(ValueError,'ownership'):ensure_project_database(project['path'])
            self.assertFalse(any(call.args[0][0]=='start' for call in run.call_args_list))

    def test_ownership_guard_survives_importers_catalog_reference_rewrite(self):
        project=self._legacy_project('Imported')
        path=Path(project['path'])/'catalog.json'
        catalog=json.loads(path.read_text());catalog.pop('managed_database');path.write_text(json.dumps(catalog))
        info=self._info(project);info['Config']['Labels']['rieke-os.project_uuid']='another-project'
        result=lambda stdout='':SimpleNamespace(returncode=0,stdout=stdout,stderr='')
        with patch('workspace_project_database._run',side_effect=[result(),result(json.dumps([info]))]):
            with self.assertRaisesRegex(ValueError,'ownership'):ensure_project_database(project['path'])

    def test_orphaned_database_storage_never_reinitialized(self):
        project=self._legacy_project('Orphan')
        data=Path(project['path'])/'database/mysql';data.mkdir();(data/'existing-data').write_text('preserve')
        result=lambda code=0:SimpleNamespace(returncode=code,stdout='',stderr='')
        with patch('workspace_project_database._run',side_effect=[result(),result(1)]):
            with self.assertRaisesRegex(ValueError,'Recover'):ensure_project_database(project['path'])
        self.assertEqual((data/'existing-data').read_text(),'preserve')

if __name__=='__main__':unittest.main()
