"""Owned fixture authority and profiler semantics; small scale is diagnostic only."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'benchmarks/workflow'))
sys.path.insert(0, str(ROOT / 'python/tests'))
from backend_timing import install
from server import build


class WorkflowBackendTests(unittest.TestCase):
    def test_real_prepare_predicate_trace_and_separate_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture, app, meta = build(ROOT, Path(folder), 200)
            self.addCleanup(fixture.doCleanups)
            self.addCleanup(install(app, folder, ROOT))
            client = app.test_client()
            headers = {'X-Workspace-Request': '1', 'Origin': 'http://localhost:8766', 'X-Benchmark-Action': 'prepare'}
            annotation = client.get('/api/epochs/' + meta['first_epoch'] + '/annotations')
            self.assertEqual(annotation.status_code, 200, annotation.get_json())
            presets = client.get('/api/search-presets')
            self.assertEqual(presets.status_code, 200, presets.get_json())
            run = client.post('/api/explore/run', json={'predicate': {'field': 'cell', 'operator': 'eq', 'value': meta['first_cell']}, 'splits': 'cell,block'}, headers=headers)
            self.assertEqual(run.status_code, 200, run.get_json())
            self.assertEqual(run.get_json()['last_run']['epoch_count'], 100)
            root = '/api/protocols/' + meta['protocol'] + '/workbench'
            queue = client.get(root).get_json()
            prepared = client.post(root + '/prepare', json={'expected_queue_revision': queue['queue_revision'], 'operation_uuid': str(uuid.uuid4())}, headers=headers)
            self.assertEqual(prepared.status_code, 201, prepared.get_json())
            context = prepared.get_json()['context']
            self.assertEqual(context['counts']['pending_epochs'], 20)
            main_page = client.get('/api/protocols/' + meta['protocol'] + '/epochs?limit=1').get_json()
            self.assertEqual(main_page['epochs'][0]['streams'][0]['uuid'], meta['trace_stream'])
            incoming_page = client.get(root + '/candidates/' + prepared.get_json()['candidate_revision_uuid'] + '/epochs', query_string={'limit': 1, 'candidate_scope_revision': context['candidate_scope_revision']})
            self.assertEqual(incoming_page.status_code, 200, incoming_page.get_json())
            self.assertEqual(incoming_page.get_json()['epochs'][0]['streams'][0]['uuid'], meta['trace_stream'])
            self.assertEqual(len(fixture.case.service.query_result(meta['protocol'])['epochs']), 180)
            self.assertFalse(meta['qualifying_scale'])
            search_response = client.post('/api/explore/preview', json={'predicate': {'field': 'cell', 'operator': 'eq', 'value': meta['first_cell']}, 'splits': 'cell,block', 'summary_only': True, 'catalog_summary': False}, headers=headers)
            self.assertEqual(search_response.status_code, 200, search_response.get_json())
            search = search_response.get_json()
            self.assertEqual(search['matched_count'], 100)
            exact = fixture.case.service.explore_preview({'field': 'cell', 'operator': 'eq', 'value': meta['first_cell']}, include_tree=False, include_catalog_summary=False)
            self.assertEqual({x['uuid'] for x in exact['membership']}, set(meta['first_cell_epochs']))
            trace = client.get('/api/epochs/' + meta['first_epoch'] + '/trace', query_string={'stream_uuid': meta['trace_stream']}, headers={**headers, 'X-Benchmark-Profile': '1'})
            self.assertEqual(trace.status_code, 200, trace.get_json())
            self.assertEqual(trace.get_json()['values'][0], 0)
            self.assertEqual(trace.get_json()['values'][-1], 9999)
            logs = [json.loads(x) for x in (Path(folder) / 'requests.jsonl').read_text().splitlines()]
            self.assertEqual(logs[0]['spans'], [])
            self.assertEqual(logs[-1]['phase'], 'profile')
            self.assertTrue(logs[-1]['spans'])
            self.assertGreaterEqual(logs[-1]['h5_access_count'], 1)
            self.assertTrue(logs[-1]['h5_accesses'][0]['allowed'])
            self.assertTrue(all(item['h5_access_count'] == 0 for item in logs[:-1]))
            import h5py
            with app.test_request_context('/api/metadata/fields'):
                with self.assertRaisesRegex(RuntimeError, 'H5 access refused'):
                    h5py.File(Path(folder) / 'trace-fixture.h5', 'r')
            with app.test_request_context('/api/epochs/x/trace'):
                with self.assertRaisesRegex(RuntimeError, 'H5 access refused'):
                    h5py.File(Path(folder) / 'unowned.h5', 'r')
            self.assertEqual(logs[-1]['request_id'], trace.headers['X-Benchmark-Request-ID'])
            self.assertTrue(all(x['self_ms'] <= x['inclusive_ms'] + 1e-8 for x in logs[-1]['spans']))

    def test_subset_membership_and_preparation_reset_are_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture, app, meta = build(ROOT, Path(folder), 1000, 300)
            self.addCleanup(fixture.doCleanups)
            service = fixture.case.service
            client = app.test_client()
            headers = {'X-Workspace-Request': '1', 'Origin': 'http://localhost:8766'}
            root = '/api/protocols/' + meta['protocol'] + '/workbench'
            self.assertEqual(len(service.rows), 1000)
            self.assertEqual(meta['main_count'], 270)
            self.assertEqual(meta['ambient_count'], 700)
            self.assertEqual(len(service.protocols[meta['protocol']]['result']['cells']), 3)
            self.assertEqual(len(service.query_result(meta['protocol'])['cells']), 3)
            result = service.explore_preview({'field': 'protocol', 'operator': 'eq', 'value': 'example'}, include_tree=False, include_catalog_summary=False)
            expected = {f'00000000-0000-0000-0000-{i:012x}' for i in [*range(270), *range(970, 1000)]}
            self.assertEqual({member['uuid'] for member in result['membership']}, expected)
            def prepare():
                queue = client.get(root).get_json()
                return client.post(root + '/prepare', json={'expected_queue_revision': queue['queue_revision'], 'operation_uuid': str(uuid.uuid4())}, headers=headers)
            fresh = prepare()
            self.assertEqual(fresh.status_code, 201, fresh.get_json())
            self.assertFalse(fresh.get_json()['reused'])
            reuse = prepare()
            self.assertEqual(reuse.status_code, 200, reuse.get_json())
            self.assertTrue(reuse.get_json()['reused'])
            self.assertEqual(client.post('/__benchmark__/reset-preparation').status_code, 403)
            reset = client.post('/__benchmark__/reset-preparation', headers=headers)
            self.assertEqual(reset.status_code, 200, reset.get_json())
            self.assertTrue(reset.get_json()['ready'])
            second = prepare()
            self.assertEqual(second.status_code, 201, second.get_json())
            self.assertFalse(second.get_json()['reused'])
            self.assertEqual(len(service.query_result(meta['protocol'])['epochs']), 270)
            fixture.case.protocol_bindings.rows[0]['version'] += 1
            refused = client.post('/__benchmark__/reset-preparation', headers=headers)
            self.assertEqual(refused.status_code, 409)

if __name__ == '__main__': unittest.main()
