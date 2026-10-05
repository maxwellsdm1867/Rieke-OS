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


class HandoffTests(unittest.TestCase):
    setUp = api_tests.WorkspaceAPITests.setUp
    revision = api_tests.WorkspaceAPITests.revision

    def manifests(self):
        self.service.project.update(format='recording-project', version=1, catalog_ref='catalog.json')
        root = Path(self.temp.name)
        (root / 'project.json').write_text(json.dumps(self.service.project))
        (root / 'catalog.json').write_text(json.dumps({'format': 'recording-catalog-reference',
            'version': 1, 'project_uuid': self.service.project['project_uuid']}))

    def test_matlab_data_download_and_saved_format_are_complete_without_gui(self):
        source_id = str(uuid.uuid4())
        self.service.sources[0].update(experiment_uuid=source_id, metadata={'uuid': source_id, 'rig_type': 'PATCH'})
        response = self.client.post(self.base + '/exports', headers=self.headers,
            json={'query_revision': self.revision(), 'format': 'matlab-mat'})
        self.assertEqual(response.status_code, 201, response.get_json())
        saved = response.get_json()
        self.assertEqual(saved['format'], 'matlab-mat')
        download = self.client.get(saved['download_url'])
        self.assertEqual(download.status_code, 200)
        self.assertIn('.mat', download.headers['Content-Disposition'])
        mat = loadmat(io.BytesIO(download.data), simplify_cells=True)
        download.close()
        self.assertEqual(mat['metadata']['dataset_uuid'], saved['dataset_uuid'])
        root = Path(saved['artifact_path']).parent
        self.assertFalse(any(file.suffix in {'.m', '.ugm'} for file in root.rglob('*')))
        self.assertNotIn('EpicTree', (root / 'README.txt').read_text())
        summary = self.client.get('/api/exports').get_json()['exports'][0]
        self.assertEqual(summary['format'], 'matlab-mat')
        reuse = self.client.get('/api/exports/' + saved['dataset_uuid'] + '/reuse').get_json()
        self.assertEqual(reuse['format'], 'matlab-mat')

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
        download.close()
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
            json={'query_revision': self.revision(), 'format': 'matlab-mat'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/exports').get_json()['exports'], [])
        failures = list((Path(self.temp.name) / 'exports').glob('*/failure.json'))
        self.assertEqual(len(failures), 1)

    def test_legacy_matlab_history_and_exact_zip_download_survive_but_new_gui_exports_reject(self):
        from disco.workbench.recipes import seal
        response = self.client.post(self.base + '/exports', headers=self.headers,
            json={'query_revision': self.revision(), 'format': 'reference-json'})
        self.assertEqual(response.status_code, 201, response.get_json())
        record = self.datasets.rows[0]
        # Seed a completed historical artifact in this isolated relation fixture.
        artifact = Path(record['artifact_path']).with_name('epictree-bundle.zip')
        with zipfile.ZipFile(artifact, 'w') as bundle:
            bundle.writestr('historical-data.txt', 'immutable legacy artifact')
        record['artifact_path'] = str(artifact)
        record['artifact_sha256'] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        record['recipe'] = seal({key: value for key, value in {**record['recipe'], 'destination': 'epictree-mat'}.items()
                                 if key != 'content_sha256'})
        before = json.dumps(self.datasets.rows, sort_keys=True, default=str)
        original = artifact.read_bytes()
        saved = self.client.get('/api/exports').get_json()['exports'][0]
        self.assertEqual(saved['format'], 'epictree-mat')
        download = self.client.get(saved['download_url'])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, original); download.close()
        self.assertEqual(self.client.get('/api/exports/' + saved['dataset_uuid'] + '/reuse').get_json()['format'], 'epictree-mat')
        rejected = self.client.post(self.base + '/exports', headers=self.headers,
            json={'query_revision': self.revision(), 'format': 'epictree-mat'})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.get_json()['error'], 'Unsupported export format')
        self.assertEqual(json.dumps(self.datasets.rows, sort_keys=True, default=str), before)
        self.assertEqual(artifact.read_bytes(), original)

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
