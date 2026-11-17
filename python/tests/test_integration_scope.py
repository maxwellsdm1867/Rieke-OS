import unittest
from unittest.mock import patch

from tools import integration_incidents as inbox
from tools.integration_scope import select


class IntegrationScopeTests(unittest.TestCase):
    def test_selects_user_workflows(self):
        self.assertEqual(select(['docs/dev/note.md']), dict(native=False, install=False, pages=False))
        self.assertEqual(select(['tools/desktop_release_pages.py']), dict(native=False, install=False, pages=True))
        self.assertTrue(select(['desktop/close/quit-coordinator.cjs'])['native'])
        self.assertFalse(select(['desktop/close/tests/quit-coordinator.test.cjs'])['native'])
        self.assertTrue(select(['tools/desktop_build_runtime.py'])['native'])
        self.assertTrue(select(['install.sh'])['install'])
        self.assertTrue(all(select(None).values()))
        self.assertTrue(all(select(['.github/workflows/integration.yml']).values()))

    def test_repair_only_current_completed_failures(self):
        run = dict(head_sha='a' * 40, head_branch='main', event='push', id=8, run_attempt=2,
                   status='completed', conclusion='failure', html_url='https://example.org/run/8',
                   repository={'full_name': inbox.REPOSITORY}, head_repository={'full_name': inbox.REPOSITORY}, path='.github/workflows/integration.yml')
        for changes, blocked in [({}, True), ({'status': 'in_progress'}, False), ({'conclusion': 'success'}, False),
                                 ({'conclusion': 'cancelled'}, False), ({'head_sha': 'b' * 40}, False),
                                 ({'event': 'workflow_dispatch'}, False), ({'head_repository': {'full_name':'other/disco'}}, False)]:
            with self.subTest(changes=changes), patch.object(inbox, 'get', return_value={'workflow_runs':[dict(run, **changes)]}):
                row = inbox.incident('main', 'a' * 40, 'push')
                self.assertEqual(row is not None, blocked)
                if blocked:
                    self.assertEqual(row['attempt'], 2)

    def test_pr_identity_and_superseded_failure(self):
        run = dict(head_sha='a' * 40, head_branch='feature', event='pull_request', id=8,
                   run_attempt=1, status='completed', conclusion='failure', html_url='link',
                   repository={'full_name': inbox.REPOSITORY}, head_repository={'full_name': inbox.REPOSITORY},
                   path='.github/workflows/integration.yml', referenced_workflows=[{'ref':'refs/pull/10/merge'}])
        other_pr = dict(run, id=9, referenced_workflows=[{'ref':'refs/pull/11/merge'}])
        with patch.object(inbox, 'get', return_value={'workflow_runs':[other_pr, run]}):
            self.assertEqual(inbox.incident('feature', run['head_sha'], 'pull_request', 10)['run_id'], 8)
        with patch.object(inbox, 'get', return_value={'workflow_runs':[dict(run, status='in_progress'), run]}):
            self.assertIsNone(inbox.incident('feature', run['head_sha'], 'pull_request', 10))
