"""Isolated HTTP handoffs; never connect to the research database."""
import io
import hashlib
import sqlite3
import json
from pathlib import Path
from unittest.mock import patch
import uuid
import unittest
import zipfile

from scipy.io import loadmat
if __package__:
    from . import test_workspace_api as api_tests
else:
    import test_workspace_api as api_tests
from workspace_matlab_masks import read_ugm


class HandoffTests(unittest.TestCase):
    setUp = api_tests.WorkspaceAPITests.setUp
    revision = api_tests.WorkspaceAPITests.revision

    def manifests(self):
        self.service.project.update(format='recording-project', version=1, catalog_ref='catalog.json')
        root = Path(self.temp.name)
        (root / 'project.json').write_text(json.dumps(self.service.project))
        (root / 'catalog.json').write_text(json.dumps({'format': 'recording-catalog-reference',
            'version': 1, 'project_uuid': self.service.project['project_uuid']}))

    def test_matlab_bundle_and_saved_format_are_complete(self):
        source_id = str(uuid.uuid4())
        self.service.sources[0].update(experiment_uuid=source_id, metadata={'uuid': source_id, 'rig_type': 'PATCH'})
        response = self.client.post(self.base + '/exports', headers=self.headers,
            json={'query_revision': self.revision(), 'format': 'epictree-mat'})
        self.assertEqual(response.status_code, 201, response.get_json())
        saved = response.get_json()
        self.assertEqual(saved['format'], 'epictree-mat')
        download = self.client.get(saved['download_url'])
        self.assertEqual(download.status_code, 200)
        self.assertIn('.zip', download.headers['Content-Disposition'])
        with zipfile.ZipFile(io.BytesIO(download.data)) as bundle:
            self.assertEqual(set(bundle.namelist()), {'recordings.mat', 'selection.ugm', 'launch_epictree.m',
                'recipe.json', 'matlab_recipe.json', 'recordings.json', 'export-report.json', 'README.txt',
                'launchWorkspaceTree.m', 'tree_layout.m', 'annotations.json', 'readWorkspaceTags.m',
                'validateWorkspaceTags.m', 'workspaceTag.m', 'writeWorkspaceTags.m'})
            mat = loadmat(io.BytesIO(bundle.read('recordings.mat')), simplify_cells=True)
            self.assertEqual(mat['metadata']['dataset_uuid'], saved['dataset_uuid'])
            path = Path(self.temp.name) / 'returned.ugm'
            path.write_bytes(bundle.read('selection.ugm'))
            mask = read_ugm(path, expected_epoch_uuids=self.service.ids)
            self.assertEqual(mask['mask'], [True, True])
            self.assertEqual(mask['metadata']['dataset_uuid'], saved['dataset_uuid'])
            self.assertIn('selection.ugm', bundle.read('launchWorkspaceTree.m').decode())
            self.assertIn('launchWorkspaceTree', bundle.read('launch_epictree.m').decode())
            self.assertIn("{'date', 'cell', 'block'}", bundle.read('tree_layout.m').decode())
        summary = self.client.get('/api/exports').get_json()['exports'][0]
        self.assertEqual(summary['format'], 'epictree-mat')
        reuse = self.client.get('/api/exports/' + saved['dataset_uuid'] + '/reuse').get_json()
        self.assertEqual(reuse['format'], 'epictree-mat')

    def test_sqlite_export_is_queryable_self_describing_and_downloadable(self):
        for key, row in self.service.rows.items():
            self.service._fingerprints[key] = hashlib.sha256(json.dumps({
                'epoch': self.service.details[key], 'source_sha256': row['source_sha256']},
                sort_keys=True, allow_nan=False).encode()).hexdigest()
        response = self.client.post(self.base + '/exports', headers=self.headers,
            json={'query_revision': self.revision(), 'format': 'wheeler-sqlite'})
        self.assertEqual(response.status_code, 201, response.get_json())
        saved = response.get_json()
        self.assertEqual(saved['format'], 'wheeler-sqlite')
        download = self.client.get(saved['download_url'])
        self.assertEqual(download.status_code, 200)
        self.assertIn('.sqlite', download.headers['Content-Disposition'])
        file = Path(self.temp.name) / 'downloaded.sqlite'
        file.write_bytes(download.data)
        with sqlite3.connect(file.as_uri() + '?mode=ro', uri=True) as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual({row[0] for row in connection.execute('SELECT epoch_uuid FROM epochs')}, set(self.service.ids))
            self.assertEqual(connection.execute('SELECT count(*) FROM epoch_overview').fetchone()[0], 2)
            recipe = json.loads(connection.execute('SELECT recipe_json FROM export_metadata').fetchone()[0])
            self.assertEqual(recipe['export_uuid'], saved['dataset_uuid'])
            self.assertEqual(recipe['destination'], 'wheeler-sqlite')
            self.assertTrue(connection.execute('SELECT count(*) FROM example_queries').fetchone()[0])
        from query_workspace_export import describe_export
        self.assertEqual(describe_export(file)['counts']['epochs'], 2)
        reuse = self.client.get('/api/exports/' + saved['dataset_uuid'] + '/reuse').get_json()
        self.assertEqual(reuse['format'], 'wheeler-sqlite')

    def test_export_format_failure_does_not_register_success(self):
        response = self.client.post(self.base + '/exports', headers=self.headers,
            json={'query_revision': self.revision(), 'format': 'arbitrary'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/exports').get_json()['exports'], [])
        response = self.client.post(self.base + '/exports', headers=self.headers,
            json={'query_revision': self.revision(), 'format': 'epictree-mat'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/exports').get_json()['exports'], [])
        failures = list((Path(self.temp.name) / 'exports').glob('*/failure.json'))
        self.assertEqual(len(failures), 1)

    def test_project_identity_display_and_audit_rollback(self):
        self.manifests()
        original = self.service.project.copy()
        with patch('recording_workspace.workspace_tables', return_value=(None, self.sources, self.events, None)):
            result = self.client.post('/api/project/display-name', headers=self.headers,
                json={'display_name': 'Spike Response Model'})
        self.assertEqual(result.status_code, 200, result.get_json())
        project = result.get_json()['project']
        self.assertEqual(project['name'], original['name'])
        self.assertEqual(project['project_uuid'], original['project_uuid'])
        self.assertEqual(project['display_name'], 'Spike Response Model')
        registry = self.client.get('/api/projects').get_json()
        self.assertEqual(registry['projects'][0]['name'], 'Spike Response Model')
        with patch('recording_workspace.workspace_tables', side_effect=ValueError('audit failed')):
            result = self.client.post('/api/project/display-name', headers=self.headers,
                json={'display_name': 'Wrong'})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(json.loads((Path(self.temp.name) / 'project.json').read_text())['display_name'], 'Spike Response Model')

    def test_switch_routes_only_accept_registered_project(self):
        self.manifests()
        current = self.client.post('/api/projects/' + self.service.project['project_uuid'] + '/open', headers=self.headers)
        self.assertEqual(current.status_code, 200)
        with patch('workspace_project_servers.subprocess.Popen') as launch:
            missing = self.client.post('/api/projects/' + str(uuid.uuid4()) + '/open', headers=self.headers)
            self.assertEqual(missing.status_code, 400)
            launch.assert_not_called()
