"""Concurrent route regression for the shared, non-thread-safe SQL connection."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from unittest.mock import patch

from flask import request

if __package__:
    from . import test_workspace_api as fixtures
else:
    import test_workspace_api as fixtures


class ConcurrentDatabaseRequests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.WorkspaceAPITests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.app = self.case.app
        self.candidate_entered = threading.Event()

        @self.app.before_request
        def candidate_arrived():
            if request.path.endswith(('/protocol-options', '/create-protocol')):
                self.candidate_entered.set()

        saved = self.case.client.post('/api/explore/revisions', json={
            'predicate': {'all': []}, 'splits': 'cell'}, headers=self.case.headers)
        self.assertEqual(saved.status_code, 201, saved.get_json())
        self.candidate = saved.get_json()

    def concurrent_candidate(self, suffix, method='GET', body=None):
        reading_fields = threading.Event()
        release_fields = threading.Event()
        unsafe_read = threading.Event()
        history = self.case.explorer_history
        original_get = history.get

        def blocked_fields():
            reading_fields.set()
            if not release_fields.wait(5):
                raise RuntimeError('Test did not release field query')
            return {'fields': []}

        def checked_get(*args, **kwargs):
            if reading_fields.is_set() and not release_fields.is_set():
                unsafe_read.set()
                raise RuntimeError('Concurrent use of shared SQL connection')
            return original_get(*args, **kwargs)

        def send(path, method='GET', body=None):
            with self.app.test_client() as client:
                return client.open(path, method=method, json=body, headers=self.case.headers)

        path = '/api/explore/revisions/' + self.candidate['revision_uuid'] + suffix
        with patch.object(self.case.service, 'predicate_fields', blocked_fields), \
                patch.object(history, 'get', checked_get), ThreadPoolExecutor(max_workers=3) as workers:
            fields = workers.submit(send, '/api/explore/predicate-fields')
            try:
                self.assertTrue(reading_fields.wait(2))
                candidate = workers.submit(send, path, method, body)
                self.assertTrue(self.candidate_entered.wait(2))
                # Progress polling must remain usable while a database request waits.
                jobs = workers.submit(send, '/api/jobs')
                self.assertEqual(jobs.result(timeout=2).status_code, 200)
                self.assertFalse(unsafe_read.wait(.15), 'Candidate read SQL before acquiring the shared lock')
            finally:
                release_fields.set()
            self.assertEqual(fields.result(timeout=2).status_code, 200)
            return candidate.result(timeout=5)

    def test_protocol_options_wait_for_inflight_catalog_query(self):
        response = self.concurrent_candidate('/protocol-options')
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertIn('expected_recipe_sha256', response.get_json())

    def test_protocol_creation_waits_and_releases_lock_after_stale_request(self):
        response = self.concurrent_candidate('/create-protocol', 'POST', {
            'name': 'Concurrent candidate', 'protocol_id': 'example',
            'expected_recipe_sha256': 'changed'})
        self.assertEqual(response.status_code, 409, response.get_json())
        # A different request thread must be able to take the lock after the error.
        with ThreadPoolExecutor(max_workers=1) as worker:
            def query():
                with self.app.test_client() as client:
                    return client.get('/api/explore/predicate-fields')
            self.assertEqual(worker.submit(query).result(timeout=2).status_code, 200)


if __name__ == '__main__':
    unittest.main()
