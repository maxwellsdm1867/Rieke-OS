"""Metadata refresh and lightweight source checks, with disposable SQL doubles."""
import unittest
import gzip
import json
from pathlib import Path
from unittest.mock import patch

try:
    from . import test_workspace_api as api_fixture
except ImportError:
    import test_workspace_api as api_fixture


class MetadataRefreshAPITests(unittest.TestCase):
    def setUp(self):
        self.fixture = api_fixture.WorkspaceAPITests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.client, self.service = self.fixture.client, self.fixture.service
        tables = patch('recording_workspace.workspace_tables',
                       return_value=(None, self.fixture.sources, self.fixture.events, None))
        tables.start()
        self.addCleanup(tables.stop)

    def refresh(self, body=None):
        return self.client.post('/api/metadata/refresh', json={} if body is None else body,
                                headers=self.fixture.headers)

    def test_refresh_checks_catalog_once_and_logs_without_applying_protocols(self):
        before = len(self.fixture.protocol_bindings.rows)
        response = self.refresh()
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()['refresh']
        self.assertEqual(self.service.refresh_count, 1)
        self.assertIn('completed_at', result)
        self.assertGreaterEqual(result['elapsed_seconds'], 0)
        self.assertEqual(len(self.fixture.protocol_bindings.rows), before)
        self.assertEqual(self.fixture.events.rows[-1]['action'], 'metadata_refreshed')
        self.assertEqual(self.client.get('/api/metadata/status').get_json()['last_refresh'], result)

    def test_malformed_refresh_request_does_not_refresh(self):
        for body in ([], {'force': True}, 'refresh'):
            self.assertEqual(self.refresh(body).status_code, 400)
        self.assertEqual(self.service.refresh_count, 0)

    def test_failed_validation_releases_lock_for_recovery(self):
        with patch.object(self.service, 'refresh', side_effect=ValueError('Source checksum changed')):
            response = self.refresh()
        self.assertEqual(response.status_code, 400)
        self.assertIn('Source checksum changed', response.get_json()['error'])
        self.assertEqual(self.refresh().status_code, 200)

    def test_parallel_refresh_is_rejected_without_second_validation(self):
        original = self.service.refresh
        def attempt_parallel():
            response = self.refresh()
            self.assertEqual(response.status_code, 409)
            return original()
        with patch.object(self.service, 'refresh', side_effect=attempt_parallel):
            self.assertEqual(self.refresh().status_code, 200)
        self.assertEqual(self.service.refresh_count, 1)

    def test_audit_failure_does_not_misreport_successful_read_model_refresh(self):
        with patch.object(self.fixture.events, 'insert1', side_effect=PermissionError('audit unavailable')):
            response = self.refresh()
        self.assertEqual(response.status_code, 200)
        self.assertIn('audit unavailable', response.get_json()['warnings'][0])

    def test_source_ping_distinguishes_missing_available_and_size_changed(self):
        source = self.service.sources[0]
        path = Path(source['source_path'])
        missing = self.client.get('/api/data-stores').get_json()['data_stores'][0]
        self.assertEqual(missing['file_status'], 'missing')
        path.write_bytes(b'fixture')
        self.service.manifests[source['source_sha256']]['source_size'] = 7
        available = self.client.get('/api/data-stores').get_json()['data_stores'][0]
        self.assertEqual(available['file_status'], 'available')
        self.assertTrue(available['checked_at'])
        self.assertEqual(available['check_kind'], 'filesystem_availability_and_size')
        path.write_bytes(b'changed-size')
        changed = self.client.get('/api/data-stores').get_json()['data_stores'][0]
        self.assertEqual(changed['file_status'], 'changed')
        self.assertEqual(self.service.refresh_count, 0)

    def test_large_json_compression_is_lossless_and_respects_client_opt_out(self):
        payload = {'cells': [{'cell_uuid': str(index), 'note': 'repeated metadata'} for index in range(1000)]}
        with patch.object(self.service, 'predicate_fields', return_value=payload):
            normal = self.client.get('/api/explore/predicate-fields')
            zipped = self.client.get('/api/explore/predicate-fields', headers={'Accept-Encoding': 'gzip'})
            declined = self.client.get('/api/explore/predicate-fields', headers={'Accept-Encoding': 'gzip;q=0'})
        self.assertEqual(zipped.headers['Content-Encoding'], 'gzip')
        self.assertNotIn('Content-Encoding', declined.headers)
        self.assertEqual(json.loads(gzip.decompress(zipped.data)), normal.get_json())
        self.assertEqual(declined.get_json(), payload)
        self.assertLess(len(zipped.data), len(normal.data) / 4)
        self.assertEqual(zipped.headers['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
