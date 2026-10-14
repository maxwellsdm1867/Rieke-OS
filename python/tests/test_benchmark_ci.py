"""Execute CI scheduling with tiny owned commands; never run benchmark workers."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import benchmark_ci as ci


ROOT = Path(__file__).resolve().parents[2]
FAKE_HARNESS = r'''
import hashlib, json, os, pathlib, subprocess, sys
args = sys.argv[1:]
tool = pathlib.Path(__file__).stem
def option(name): return args[args.index(name) + 1]
def sha(path):
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
if args[0] == 'dependencies-match':
    sys.exit(0 if pathlib.Path(args[1]).read_bytes() == pathlib.Path(args[2]).read_bytes() else 1)
output = pathlib.Path(option('--output'))
action = args[0]
source = pathlib.Path(option('--source-root')) if '--source-root' in args else pathlib.Path(__file__).resolve().parents[1]
commit = sha(source)
smoke = '--smoke' in args
journal = pathlib.Path(os.environ['CI_FIXTURE_JOURNAL'])
active = journal.with_suffix('.active')
with active.open('x') as lock: lock.write(tool)
entry = dict(tool=tool, action=action, smoke=smoke, commit=commit, output=str(output), args=args)
with journal.open('a') as log: log.write(json.dumps(dict(entry, phase='start')) + '\n')
failed = commit == os.environ.get('CI_FIXTURE_FAIL_SHA') and action == 'run' and not smoke and tool != 'benchmark'
if action == 'run':
    output.mkdir(parents=True)
    source_state = dict(commit=commit, status='')
    receipt = dict(status='failed' if failed else 'passed', source_start=source_state,
                   source_end=source_state, source_root=str(source),
                   fixture_note='Owned scheduling test, not benchmark evidence')
    # Deliberately unusual formatting detects copied receipts being reserialized.
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=3) + '\n\n')
    (output / 'provenance.json').write_text('Original fixture provenance for ' + commit + '\n')
    (output / 'raw.log').write_text('Original fixture worker log\n')
    if tool == 'benchmark':
        source_state = dict(commit=commit, dirty=False)
        (output / 'benchmark.json').write_text(json.dumps(dict(validation_errors=[], fixture_cleaned=True,
            source_start=source_state, source_end=source_state)))
else:
    before, after = map(pathlib.Path, args[1:3])
    passed = before.is_file() and after.is_file()
    passed = passed and all(json.loads(p.read_text())['status'] == 'passed' for p in (before, after))
    failed = not passed
    comparison = dict(status='passed' if passed else 'failed', review_required=[],
        candidate_commit=json.loads(after.read_text())['source_start']['commit'] if after.is_file() else None,
        baseline_receipt_sha256=digest(before) if before.is_file() else None,
        candidate_receipt_sha256=digest(after) if after.is_file() else None)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(comparison))
print('Owned fake command', tool, action, commit, 'failed' if failed else 'passed')
with journal.open('a') as log: log.write(json.dumps(dict(entry, phase='end')) + '\n')
active.unlink()
sys.exit(2 if failed else 0)
'''


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='disco-ci-scheduling-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / 'harness'
        (self.repo / 'tools').mkdir(parents=True)
        for name in ('benchmark', 'benchmark_everyday', 'benchmark_workflow'):
            (self.repo / 'tools' / (name + '.py')).write_text(FAKE_HARNESS)
        for name in ('workspace-app', 'desktop'):
            package = self.repo / name
            package.mkdir()
            (package / 'package-lock.json').write_text('{"lockfileVersion":3,"packages":{}}')
            (package / 'node_modules').mkdir()
        (self.repo / '.gitignore').write_text('node_modules/\n')
        self.git('init', '-q')
        self.commits = []
        for index in range(3):
            (self.repo / 'fixture.txt').write_text(str(index))
            self.git('add', '.')
            self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                     'commit', '-qm', 'Owned scheduling fixture')
            self.commits.append(self.git('rev-parse', 'HEAD'))
        self.journal = self.root / 'commands.jsonl'
        root_patch = patch.object(ci, 'ROOT', self.repo)
        root_patch.start(); self.addCleanup(root_patch.stop)
        env_patch = patch.dict(os.environ, CI_FIXTURE_JOURNAL=str(self.journal),
                              GITHUB_RUN_ID='271', GITHUB_RUN_ATTEMPT='3')
        env_patch.start(); self.addCleanup(env_patch.stop)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()

    def plan(self, indices=(0, 1, 2)):
        return ci.resolve_sources(self.repo, *(self.commits[index] for index in indices), 'workflow_dispatch')

    def entries(self):
        return [json.loads(line) for line in self.journal.read_text().splitlines()] if self.journal.exists() else []

    def run_family(self, family, plan, name):
        output = self.root / name
        result = ci.run_family(family, plan, output, self.root / (name + '-sources'), sys.executable)
        return output, result

    def test_all_role_equivalence_patterns_measure_each_source_once_per_family(self):
        for family in ('backend', 'browser'):
            for indices in ((0, 1, 2), (0, 0, 1), (0, 1, 0), (0, 1, 1), (0, 0, 0)):
                with self.subTest(family=family, indices=indices):
                    self.journal.unlink(missing_ok=True)
                    plan = self.plan(indices)
                    output, _ = self.run_family(family, plan, family + '-' + ''.join(map(str, indices)))
                    entries = self.entries()
                    self.assertEqual([entry['phase'] for entry in entries], ['start', 'end'] * (len(entries) // 2))
                    runs = [entry for entry in entries if entry['phase'] == 'start'
                            and entry['action'] == 'run' and not entry['smoke'] and entry['tool'] != 'benchmark']
                    expected = list(dict.fromkeys(self.commits[index] for index in indices))
                    self.assertEqual([entry['commit'] for entry in runs], expected)
                    for entry in runs:
                        self.assertNotIn('--profile', entry['args'])
                        self.assertNotIn('--samples', entry['args'])
                        if family == 'browser':
                            self.assertEqual(entry['args'][entry['args'].index('--protocol-epochs') + 1], '20000')
                    prefix = 'workflow-' if family == 'browser' else ''
                    candidate = output / (prefix + 'candidate') / 'receipt.json'
                    self.assertTrue(candidate.is_file())
                    self.assertEqual(json.loads(candidate.read_text())['source_start']['commit'], self.commits[indices[2]])
                    for role, canonical in plan['canonical'].items():
                        for filename in ('receipt.json', 'provenance.json', 'raw.log'):
                            self.assertEqual((output / (prefix + role) / filename).read_bytes(),
                                             (output / (prefix + canonical) / filename).read_bytes())
                    comparisons = [entry for entry in entries if entry['phase'] == 'start' and entry['action'] == 'compare']
                    self.assertEqual(len(comparisons), 2)
                    for entry in comparisons:
                        self.assertEqual(Path(entry['args'][2]), candidate)
                    for role in ('pinned', 'previous'):
                        self.assertEqual(json.loads((output / f'{prefix}{role}-comparison.json').read_text())['status'], 'passed')
                    if family == 'browser':
                        smoke = [entry['commit'] for entry in entries if entry['phase'] == 'start' and entry['smoke']]
                        self.assertEqual(smoke, expected)

    def test_source_resolution_preserves_explicit_shas_and_documented_defaults(self):
        pinned, previous, candidate = self.commits
        manual = ci.resolve_sources(self.repo, pinned, '', '', 'workflow_dispatch')
        self.assertEqual(manual['sources'], dict(pinned=pinned, previous=previous, candidate=candidate))
        first_push = ci.resolve_sources(self.repo, pinned, '0' * 40, '', 'push')
        self.assertEqual(first_push['sources'], dict(pinned=pinned, previous=pinned, candidate=candidate))
        for bad in ('main', candidate[:12], 'g' * 40, ''):
            with self.subTest(invalid_previous=bad), self.assertRaises(ValueError):
                ci.resolve_sources(self.repo, pinned, bad, candidate, 'pull_request')

    def test_failed_measurement_is_retained_and_later_sources_and_comparisons_run(self):
        for family in ('backend', 'browser'):
            with self.subTest(family=family):
                self.journal.unlink(missing_ok=True)
                plan = self.plan()
                with patch.dict(os.environ, CI_FIXTURE_FAIL_SHA=self.commits[0]):
                    output, _ = self.run_family(family, plan, family + '-failure')
                prefix = 'workflow-' if family == 'browser' else ''
                self.assertEqual(json.loads((output / (prefix + 'pinned') / 'receipt.json').read_text())['status'], 'failed')
                self.assertIn('Original fixture worker log', (output / (prefix + 'pinned') / 'raw.log').read_text())
                self.assertEqual(json.loads((output / (prefix + 'candidate') / 'receipt.json').read_text())['status'], 'passed')
                for role, expected in (('pinned', 'failed'), ('previous', 'passed')):
                    self.assertEqual(json.loads((output / f'{prefix}{role}-comparison.json').read_text())['status'], expected)
                self.assertEqual(json.loads((output / f'{family}-family.json').read_text())['status'], 'failed')

    def aggregate_fixture(self):
        plan = self.plan((0, 1, 0))
        backend, backend_status = self.run_family('backend', plan, 'backend-aggregate')
        browser, browser_status = self.run_family('browser', plan, 'browser-aggregate')
        self.assertEqual(backend_status['status'], 'passed', backend_status)
        self.assertEqual(browser_status['status'], 'passed', browser_status)
        combined = self.root / 'combined'
        shutil.copytree(backend, combined)
        shutil.copytree(browser, combined, dirs_exist_ok=True)
        self.assertEqual(ci.aggregate(plan, combined, 'success', 'success')['status'], 'passed')
        return plan, combined

    def test_aggregate_rejects_absent_failed_skipped_cancelled_and_foreign_attempt_families(self):
        plan, output = self.aggregate_fixture()
        for outcome in ('failure', 'cancelled', 'skipped', '', 'neutral'):
            for backend in (True, False):
                with self.subTest(outcome=outcome, backend=backend):
                    result = ci.aggregate(plan, output, outcome if backend else 'success', 'success' if backend else outcome)
                    self.assertEqual(result['status'], 'failed')
        for family in ('backend', 'browser'):
            marker = output / (family + '-family.json')
            original = marker.read_bytes()
            for field, value in (('status', 'failed'), ('status', 'cancelled'), ('family', 'other')):
                record = json.loads(original)
                record[field] = value
                marker.write_text(json.dumps(record))
                self.assertEqual(ci.aggregate(plan, output, 'success', 'success')['status'], 'failed')
            record = json.loads(original)
            record['plan']['run_attempt'] = '2'
            marker.write_text(json.dumps(record))
            self.assertEqual(ci.aggregate(plan, output, 'success', 'success')['status'], 'failed')
            marker.unlink()
            self.assertEqual(ci.aggregate(plan, output, 'success', 'success')['status'], 'failed')
            self.assertFalse(marker.exists(), 'Missing family evidence must never be synthesized')
            marker.write_bytes(original)
        markers = {family: (output / (family + '-family.json')).read_bytes() for family in ('backend', 'browser')}
        for change in ({'order': list(reversed(plan['order']))}, {'harness': self.commits[0]},
                       {'run_id': '270'}, {'run_attempt': '2'}):
            with self.subTest(foreign_plan=change):
                altered = {**plan, **change}
                for family, raw in markers.items():
                    marker = json.loads(raw)
                    marker['plan'] = altered
                    (output / (family + '-family.json')).write_text(json.dumps(marker))
                self.assertEqual(ci.aggregate(altered, output, 'success', 'success')['status'], 'failed')
        for family, raw in markers.items():
            (output / (family + '-family.json')).write_bytes(raw)

    def test_aggregate_rejects_missing_tampered_source_alias_and_comparison_evidence(self):
        plan, output = self.aggregate_fixture()
        filenames = ['candidate/receipt.json', 'workflow-candidate/receipt.json', 'core/benchmark.json',
                     'pinned-comparison.json', 'previous-comparison.json',
                     'workflow-pinned-comparison.json', 'workflow-previous-comparison.json']
        for filename in filenames:
            with self.subTest(missing=filename):
                path = output / filename
                original = path.read_bytes()
                path.unlink()
                self.assertEqual(ci.aggregate(plan, output, 'success', 'success')['status'], 'failed')
                self.assertFalse(path.exists())
                path.write_bytes(original)
        for filename in ('candidate/receipt.json', 'workflow-candidate/receipt.json'):
            path = output / filename
            original = path.read_bytes()
            for key, value in (('commit', self.commits[2]), ('status', ' M dirty')):
                receipt = json.loads(original)
                receipt['source_start'][key] = value
                receipt['source_end'] = copy.deepcopy(receipt['source_start'])
                path.write_text(json.dumps(receipt))
                self.assertEqual(ci.aggregate(plan, output, 'success', 'success')['status'], 'failed')
            path.write_bytes(original)
        alias = output / 'pinned/receipt.json'
        original = alias.read_bytes()
        alias.write_bytes(original + b' ')
        self.assertEqual(ci.aggregate(plan, output, 'success', 'success')['status'], 'failed')
        alias.write_bytes(original)
        for filename in filenames[3:]:
            path = output / filename
            original = path.read_bytes()
            for change in ({'status': 'failed'}, {'review_required': ['regression']},
                           {'baseline_receipt_sha256': '0' * 64}, {'candidate_receipt_sha256': '0' * 64}):
                path.write_text(json.dumps({**json.loads(original), **change}))
                self.assertEqual(ci.aggregate(plan, output, 'success', 'success')['status'], 'failed')
            path.write_bytes(original)
        core_path = output / 'core/benchmark.json'
        original = core_path.read_bytes()
        for change in ({'validation_errors': ['failed oracle']}, {'fixture_cleaned': False},
                       {'source_start': {'commit': self.commits[2], 'dirty': False}},
                       {'source_end': {'commit': self.commits[0], 'dirty': True}}):
            core_path.write_text(json.dumps({**json.loads(original), **change}))
            self.assertEqual(ci.aggregate(plan, output, 'success', 'success')['status'], 'failed')
        core_path.write_bytes(original)
        self.assertEqual(ci.aggregate(plan, output, 'success', 'success')['status'], 'passed')


class WorkflowWiringTests(unittest.TestCase):
    def setUp(self):
        import yaml
        self.workflow = yaml.safe_load((ROOT / '.github/workflows/everyday-million.yml').read_text())
        self.jobs = self.workflow['jobs']

    def test_only_automatic_pr_runs_share_a_cancelling_group(self):
        concurrency = self.workflow['concurrency']
        self.assertEqual(concurrency['cancel-in-progress'], "${{ github.event_name == 'pull_request' }}")
        self.assertIn('github.event_name', concurrency['group'])
        self.assertIn("github.event_name == 'pull_request' && github.event.pull_request.number || github.run_id", concurrency['group'])

    def test_independent_families_join_a_fail_closed_stable_aggregate(self):
        for family, name in (('backend', 'Backend million query regression'),
                             ('browser', 'Browser million workflow regression')):
            job = self.jobs[family]
            self.assertEqual(job['name'], name)
            self.assertEqual(job['needs'], 'scope')
            self.assertEqual(job['runs-on'], 'ubuntu-latest')
            commands = '\n'.join(step.get('run', '') for step in job['steps'])
            self.assertIn('uv venv --python 3.11.13', commands)
            self.assertIn('tools/benchmark_ci.py run --family ' + family, commands)
            uploads = [step for step in job['steps'] if step.get('uses') == 'actions/upload-artifact@v4']
            self.assertEqual(len(uploads), 1)
            self.assertEqual(uploads[0]['if'], 'always()')
            self.assertEqual(uploads[0]['with']['name'], f'everyday-{family}-${{{{ github.run_id }}}}-${{{{ github.run_attempt }}}}')
        aggregate = self.jobs['everyday-million']
        self.assertEqual(set(aggregate['needs']), {'scope', 'backend', 'browser'})
        self.assertIn('Actual million metadata query regression', aggregate['name'])
        self.assertIn('always()', aggregate['if'])
        check = next(step for step in aggregate['steps'] if 'benchmark_ci.py aggregate' in step.get('run', ''))
        self.assertFalse(check.get('continue-on-error', False))
        self.assertEqual(check['env']['BACKEND_RESULT'], '${{ needs.backend.result }}')
        self.assertEqual(check['env']['BROWSER_RESULT'], '${{ needs.browser.result }}')
        upload = next(step for step in aggregate['steps'] if step.get('uses') == 'actions/upload-artifact@v4')
        self.assertEqual(upload['if'], 'always()')
        self.assertEqual(upload['with']['name'], 'everyday-million-${{ github.run_id }}-${{ github.run_attempt }}')
        sources = next(step for step in self.jobs['scope']['steps'] if step.get('id') == 'sources')
        self.assertEqual(sources['env']['PINNED_SHA'], '34ce2e06dec0e2886d5a2310f21e02cf818cb646')


if __name__ == '__main__':
    unittest.main()
