"""Progress counters and labels are measured, typed and safe to render."""
import json
from pathlib import Path
import tempfile
import unittest
from workspace_import_progress import ProgressReporter, read_job, read_jobs, recover_jobs


class ProgressShapeTests(unittest.TestCase):
    def test_corrupt_progress_shapes_are_diagnostics_not_rendered_values(self):
        with tempfile.TemporaryDirectory() as root:
            job = Path(root) / 'job.json'
            job.write_text(json.dumps({'status': 'validating', 'owner_run_id': 'owner'}))
            sidecar = Path(root) / 'progress/job.json'
            sidecar.parent.mkdir()
            for fields in ({'stage_label': {}}, {'commit_state': []}, {'catalog_committed': []}, {'completed': True},
                           {'completed': 5, 'total': 3}, {'unit': []}):
                with self.subTest(fields=fields):
                    sidecar.write_text(json.dumps({'version': 1, 'stage': 'parsing', **fields}))
                    result = read_job(job, 'owner', {'job'})
                    self.assertNotIn('progress', result)
                    self.assertEqual(result['warnings'][0]['stage'], 'progress_log')

    def test_committed_marker_cannot_be_downgraded_by_later_error(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'progress.json'
            report = ProgressReporter(path)
            report.emit('catalog_committed', commit_state='committed', catalog_committed=True)
            report.emit('failed', outcome='failed', commit_state='not_started', catalog_committed=False)
            stored = json.loads(path.read_text())
            self.assertTrue(stored['catalog_committed'])
            self.assertEqual(stored['commit_state'], 'committed')


    def test_corrupt_job_display_text_retains_raw_evidence_and_healthy_history(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            broken = folder / 'broken.json'
            healthy = folder / 'healthy.json'
            healthy.write_text(json.dumps({'status': 'complete', 'message': 'Imported'}))
            invalids = ({'message': {}}, {'error': []}, {'warnings': [{'message': {}}]},
                        {'diagnostics': []}, {'diagnostics': {'message': {}}},
                        {'diagnostics': {'traceback_path': []}}, {'progress': {'stage_label': {}}})
            for fields in invalids:
                with self.subTest(fields=fields):
                    original = json.dumps({'status': 'validating', 'owner_run_id': 'old', **fields})
                    broken.write_text(original)
                    recover_jobs(folder, 'new')
                    self.assertEqual(broken.read_text(), original)
                    rows = read_jobs(folder, 'new')
                    self.assertEqual(len(rows), 2)
                    damaged = next(row for row in rows if row['job_uuid']=='broken')
                    self.assertEqual(damaged['status'], 'interrupted')
                    self.assertEqual(damaged['diagnostics']['path'], str(broken))
                    self.assertIsInstance(damaged['error'], str)
                    self.assertIsInstance(damaged['diagnostics']['message'], str)
                    self.assertEqual(next(row for row in rows if row['job_uuid']=='healthy')['message'], 'Imported')
