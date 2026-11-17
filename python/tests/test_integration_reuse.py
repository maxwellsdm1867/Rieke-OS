"""Prove main push reuse against GitHub metadata and actual checked-out Git trees."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import integration_reuse as reuse


class IntegrationReuseTests(unittest.TestCase):
    def setUp(self):
        self.before, self.head, self.after, self.tested, self.tree = (v * 40 for v in 'abcde')
        self.repo = 'example/Disco'
        self.workflow = 'disco-integration.yml'
        self.env = {'GITHUB_REPOSITORY': self.repo, 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main',
                    'GITHUB_SHA': self.after, 'GITHUB_WORKFLOW_REF': f'{self.repo}/.github/workflows/{self.workflow}@refs/heads/main'}
        self.event = {'ref': self.env['GITHUB_REF'], 'repository': {'full_name': self.repo}, 'before': self.before,
                      'after': self.after, 'forced': False, 'deleted': False}
        self.pr = {'number': 42, 'state': 'closed', 'merged_at': '2026-11-17T10:15:00Z', 'merge_commit_sha': self.after,
                   'base': {'ref': 'main', 'sha': self.before, 'repo': {'full_name': self.repo}},
                   'head': {'sha': self.head, 'repo': {'full_name': self.repo}}}
        self.run = {'id': 701, 'run_attempt': 2, 'status': 'completed', 'conclusion': 'success', 'event': 'pull_request',
                    'path': '.github/workflows/' + self.workflow, 'head_sha': self.head,
                    'repository': {'full_name': self.repo}, 'head_repository': {'full_name': self.repo},
                    'referenced_workflows': [{'path': f'{self.repo}/.github/workflows/{child}@{self.tested}',
                                              'ref': 'refs/pull/42/merge', 'sha': self.tested}
                                             for child in ('workspace-ci.yml', 'everyday-million.yml')]}
        self.proof = {'format': reuse.FORMAT, 'repository': self.repo, 'workflow': self.workflow, 'pull_request': 42,
                      'base_ref': 'main', 'base': self.before, 'head': self.head, 'tested_commit': self.tested,
                      'tested_tree': self.tree, 'run_id': 701, 'run_attempt': 2}
        self.tested_commit = {'sha': self.tested, 'tree': {'sha': self.tree}, 'parents': [{'sha': self.before}, {'sha': self.head}]}
        base = f'repos/{self.repo}'
        self.prs_url = f'{base}/commits/{self.after}/pulls?per_page=100'
        self.runs_url = f'{base}/actions/workflows/{self.workflow}/runs?event=pull_request&head_sha={self.head}&per_page=1'
        self.responses = {self.prs_url: [self.pr], self.runs_url: {'workflow_runs': [self.run]},
                          f'{base}/git/commits/{self.tested}': self.tested_commit}
        self.parents = [self.before, self.head]

    def check(self, **kwargs):
        with patch.object(reuse, 'checkout', return_value=(self.tree, self.parents)), \
             patch.object(reuse, 'api', side_effect=kwargs.get('api', self.responses.__getitem__)), \
             patch.object(reuse, 'artifact', return_value=self.proof) as artifact, \
             patch.object(reuse, 'require_jobs', side_effect=kwargs.get('job_failure')) as jobs:
            result = reuse.check(self.env, self.event)
            jobs.assert_called_once_with(self.repo, self.run, [reuse.VERDICT])
            artifact.assert_called_once_with(self.repo, self.run, 'integration-pr-proof-701-2', reuse.PROOF_FILE)
            return result

    def test_merge_or_single_squash_requires_exact_tested_tree_and_adjacent_base(self):
        for parents in ([self.before, self.head], [self.before]):
            with self.subTest(parents=parents):
                self.parents = parents
                result = self.check()
                self.assertTrue(result['reused'])
                self.assertEqual(result['merged_commit'], self.after)
                self.assertEqual(result['proof']['tested_commit'], self.tested)
                self.assertEqual(result['run_url'], 'https://github.com/example/Disco/actions/runs/701/attempts/2')

    def test_missing_wrong_or_ambiguous_proof_falls_back(self):
        wrong = 'f' * 40
        for label, mapping, key, value in [
            ('direct push', self.responses, self.prs_url, []),
            ('ambiguous', self.responses, self.prs_url, [self.pr, self.pr]),
            ('merge sha', self.pr, 'merge_commit_sha', wrong),
            ('newer base', self.pr['base'], 'sha', wrong),
            ('other base branch', self.pr['base'], 'ref', 'master'),
            ('fork PR', self.pr['head']['repo'], 'full_name', 'fork/Disco'),
            ('expired or missing run', self.responses[self.runs_url], 'workflow_runs', []),
            ('failed', self.run, 'conclusion', 'failure'),
            ('not completed', self.run, 'status', 'in_progress'),
            ('other workflow', self.run, 'path', '.github/workflows/diagnostic.yml'),
            ('manual run', self.run, 'event', 'workflow_dispatch'),
            ('fork run', self.run['head_repository'], 'full_name', 'fork/Disco'),
            ('wrong run head', self.run, 'head_sha', wrong),
            ('missing called workflows', self.run, 'referenced_workflows', []),
            ('another PR ref', self.run['referenced_workflows'][0], 'ref', 'refs/pull/7/merge'),
            ('different tested source', self.run['referenced_workflows'][1], 'sha', wrong),
            ('different PR', self.proof, 'pull_request', 7),
            ('superseded artifact', self.proof, 'run_attempt', 1),
            ('unrelated run', self.proof, 'run_id', 700),
            ('recorded tree differs', self.proof, 'tested_tree', wrong),
            ('server tree differs', self.tested_commit['tree'], 'sha', wrong),
            ('server parents differ', self.tested_commit, 'parents', [{'sha': self.before}, {'sha': wrong}]),
            ('forced push', self.event, 'forced', True),
            ('wrong push ref', self.event, 'ref', 'refs/heads/other'),
            ('manual qualification', self.env, 'GITHUB_EVENT_NAME', 'workflow_dispatch'),
        ]:
            with self.subTest(case=label), patch.dict(mapping, {key: value}), self.assertRaises(ValueError):
                self.check()
        self.parents = [wrong, self.head]
        with self.assertRaisesRegex(ValueError, 'different base'):
            self.check()
        self.parents = [self.before, wrong]
        with self.assertRaisesRegex(ValueError, 'head differs'):
            self.check()

    def test_missing_actual_verdict_or_newer_attempt_cannot_reuse(self):
        with self.assertRaisesRegex(ValueError, 'missing verdict'):
            self.check(job_failure=ValueError('missing verdict'))
        calls = 0
        def api(path):
            nonlocal calls
            if path == self.runs_url:
                calls += 1
                if calls == 2:
                    return {'workflow_runs': [dict(self.run, run_attempt=3)]}
            return self.responses[path]
        with self.assertRaisesRegex(ValueError, 'superseded'):
            self.check(api=api)

    def test_record_reads_real_commit_parents_even_at_depth_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, shallow = root/'repo', root/'shallow'
            subprocess.run(['git','init','-q','-b','main',repo], check=True)
            def git(*args, data=None):
                return subprocess.check_output(['git','-C',repo,'-c','user.name=CI','-c','user.email=ci@example.test',*args],
                                               input=data, text=True).strip()
            tree = git('mktree', data='')
            base = git('commit-tree',tree,'-m','base')
            head = git('commit-tree',tree,'-p',base,'-m','PR')
            merge = git('commit-tree',tree,'-p',base,'-p',head,'-m','synthetic merge')
            git('update-ref','refs/heads/main',merge)
            subprocess.run(['git','clone','-q','--depth=1',repo.as_uri(),shallow],check=True)
            self.assertFalse(subprocess.run(['git','-C',shallow,'cat-file','-e',base], capture_output=True).returncode == 0)
            pr = copy.deepcopy(self.pr)
            pr['base']['sha'], pr['head']['sha'] = base, head
            event_file, output = root/'event.json', root/'proof.json'
            event_file.write_text(json.dumps({'repository': {'full_name': self.repo}, 'pull_request': pr}))
            env = {**os.environ, **self.env, 'GITHUB_EVENT_NAME':'pull_request', 'GITHUB_REF':'refs/pull/42/merge',
                   'GITHUB_SHA': merge, 'GITHUB_RUN_ID':'701', 'GITHUB_RUN_ATTEMPT':'2', 'GITHUB_EVENT_PATH':str(event_file)}
            cli = [sys.executable,'-B',reuse.__file__,'record','--output',str(output)]
            subprocess.run(cli,cwd=shallow,env=env,check=True,capture_output=True)
            self.assertEqual(json.loads(output.read_text()), dict(self.proof, base=base, head=head, tested_commit=merge, tested_tree=tree))
            (shallow/'untested').write_text('changed')
            subprocess.run(cli,cwd=shallow,env=env,check=True,capture_output=True)
            self.assertFalse(json.loads(output.read_text())['reused'])

    def test_cli_returns_normal_checks_even_if_metadata_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root/'receipt.json'
            github = root/'github-output'
            env = dict(os.environ, GITHUB_EVENT_PATH=str(root/'missing-event'))
            subprocess.run([sys.executable,'-B',reuse.__file__,'check','--output',str(output),'--github-output',str(github)],
                           env=env,check=True,capture_output=True)
            self.assertFalse(json.loads(output.read_text())['reused'])
            self.assertEqual(github.read_text().splitlines(), ['reused=false', 'run_url='])


if __name__ == '__main__':
    unittest.main()
