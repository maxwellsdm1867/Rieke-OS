"""Release qualification selection through the public CLI and real local Git history."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PLANNER = Path(__file__).resolve().parents[2] / 'tools/desktop_release_plan.py'
FLAGS = ('build_required', 'updater', 'database', 'packaging', 'full_ui')


class ReleasePlanCLITests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='rieke-release-plan-')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1'}
        self.git('init', '-q')
        self.git('config', 'user.name', 'Release fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.write('rieke-release.json', {'version': '0.1.3'})
        self.initial = self.commit()

    def git(self, *arguments):
        return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', *arguments], cwd=self.root, env=self.env, text=True).strip()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if isinstance(data, dict) else data)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'Isolated planner fixture')
        return self.git('rev-parse', 'HEAD')

    def plan(self, *arguments, success=True):
        output = self.root / '.git/release-plan.json'
        github_output = self.root / '.git/github-output'
        result = subprocess.run([sys.executable, str(PLANNER), *arguments, '--output', str(output), '--github-output', str(github_output)], cwd=self.root, env=self.env, text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(output.read_text())
            emitted = dict(line.split('=', 1) for line in github_output.read_text().splitlines())
            for flag in FLAGS:
                self.assertEqual(emitted[flag], str(value[flag]).lower())
            return value
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists(), result.stderr)
        return result

    def test_documentation_and_tests_only_do_not_build_an_application(self):
        self.write('.gitignore', 'docs/dev/desktop-smoke-e2e.json\n')
        self.write('docs/dev/guide.md', 'Updated release guide\n')
        self.write('python/tests/test_example.py', '# New coverage\n')
        head = self.commit()
        value = self.plan('--base', self.initial)
        self.assertEqual({flag: value[flag] for flag in FLAGS}, dict.fromkeys(FLAGS, False))
        self.assertEqual(value['base'], self.initial)
        self.assertEqual(value['head'], head)
        self.assertEqual(value['changed_paths'], ['.gitignore', 'docs/dev/guide.md', 'python/tests/test_example.py'])


    def test_close_test_changes_and_renames_do_not_build(self):
        self.write('desktop/tests/old.test.cjs', '// existing test\n')
        before = self.commit()
        self.write('desktop/close/tests/new.test.cjs', '// nearby test\n')
        self.git('mv', 'desktop/tests/old.test.cjs', 'desktop/close/tests/moved.test.cjs')
        self.commit()
        value = self.plan('--base', before)
        self.assertEqual(tuple(value[flag] for flag in FLAGS), (False,) * 5)

    def test_close_production_move_and_removal_keep_domain_classification(self):
        self.write('desktop/draft-barrier.cjs', '// existing production\n')
        before = self.commit()
        (self.root / 'desktop/close').mkdir(parents=True)
        self.git('mv', 'desktop/draft-barrier.cjs', 'desktop/close/draft-barrier.cjs')
        moved = self.commit()
        value = self.plan('--base', before)
        self.assertEqual(tuple(value[flag] for flag in FLAGS), (True, True, False, False, True))
        self.assertEqual(value['changed_paths'], ['desktop/close/draft-barrier.cjs', 'desktop/draft-barrier.cjs'])
        self.git('rm', 'desktop/close/draft-barrier.cjs')
        self.commit()
        value = self.plan('--base', moved)
        self.assertEqual(tuple(value[flag] for flag in FLAGS), (True, True, False, False, True))

    def test_state_owner_test_changes_and_renames_do_not_build(self):
        for owner in ('drafts', 'startup'):
            self.write(f'desktop/tests/{owner}.test.cjs', '// original coverage\n')
        before = self.commit()
        for owner in ('drafts', 'startup'):
            self.write(f'desktop/{owner}/tests/public.test.cjs', '// public example\n')
            self.git('mv', f'desktop/tests/{owner}.test.cjs', f'desktop/{owner}/tests/moved.test.cjs')
        self.commit()
        value = self.plan('--base', before)
        self.assertEqual(tuple(value[flag] for flag in FLAGS), (False,) * 5)

    def test_state_production_moves_and_deletions_keep_basename_classification(self):
        for owner, name, expected in [('drafts', 'draft-store', (True, True, False, False, True)),
                                      ('startup', 'startup-session', (True, True, False, False, False))]:
            with self.subTest(owner=owner):
                self.write(f'desktop/{name}.cjs', '// original owner\n')
                before = self.commit()
                (self.root / f'desktop/{owner}').mkdir(parents=True)
                self.git('mv', f'desktop/{name}.cjs', f'desktop/{owner}/{name}.cjs')
                moved = self.commit()
                value = self.plan('--base', before)
                self.assertEqual(tuple(value[flag] for flag in FLAGS), expected)
                self.assertEqual(set(value['changed_paths']), {f'desktop/{name}.cjs', f'desktop/{owner}/{name}.cjs'})
                self.git('rm', f'desktop/{owner}/{name}.cjs')
                self.commit()
                value = self.plan('--base', moved)
                self.assertEqual(tuple(value[flag] for flag in FLAGS), expected)

    def test_application_changes_select_routine_or_domain_qualification(self):
        cases = [
            ('workspace-app/src/components/Inspector.jsx', (True, False, False, False, False)),
            ('desktop/testing-install.cjs', (True, True, False, False, False)),
            ('desktop/unknown.test.cjs', (True, True, False, False, False)),
            ('python/workspace_mysql_runtime.py', (True, True, True, True, True)),
            ('desktop/bootstrap.cjs', (True, True, False, True, False)),
            ('desktop/recovery-install.cjs', (True, True, False, True, False)),
            ('desktop/supervisor.cjs', (True, True, False, False, True)),
            ('desktop/main.cjs', (True, True, False, False, True)),
            ('desktop/close/draft-barrier.cjs', (True, True, False, False, True)),
            ('desktop/close/quit-coordinator.cjs', (True, True, False, False, False)),
            ('desktop/drafts/draft-store.cjs', (True, True, False, False, True)),
            ('desktop/startup/startup-session.cjs', (True, True, False, False, False)),
            ('python/workspace_desktop.py', (True, True, True, False, True)),
            ('python/workspace_migration.py', (True, False, True, False, True)),
            ('python/workspace_annotations.py', (True, False, True, False, True)),
            ('desktop/requirements.lock', (True, True, False, True, False)),
            ('tools/desktop_build_runtime.py', (True, True, False, True, False)),
            ('python/new_runtime_component.py', (True, False, True, False, True)),
            ('desktop/new-native-resource.bin', (True, True, False, True, False)),
        ]
        for path, expected in cases:
            with self.subTest(path=path):
                self.write(path, '# Changed implementation\n')
                head = self.commit()
                value = self.plan('--base', self.initial, '--head', head)
                self.assertEqual(tuple(value[flag] for flag in FLAGS), expected)
                self.git('reset', '--hard', self.initial)

    def test_workflow_test_harness_and_research_changes_do_not_package(self):
        for path in ['.github/workflows/desktop.yml', 'desktop/e2e/packaged.e2e.cjs',
                     'workspace-app/src/components/Inspector.test.jsx', 'tools/desktop_scientific_e2e.py',
                     'tools/desktop_release_plan.py', 'tools/research_report.py']:
            self.write(path, '# Nonapplication change\n')
        self.commit()
        value = self.plan('--base', self.initial)
        self.assertEqual(tuple(value[flag] for flag in FLAGS), (False,) * 5)


    def test_version_only_changes_build_without_packaging_risk(self):
        self.write('desktop/package.json', {'name': 'desktop', 'version': '0.1.3', 'build': {'appId': 'org.riekeos.desktop'}})
        self.write('workspace-app/package.json', {'name': 'frontend', 'version': '0.1.3'})
        self.write('desktop/package-lock.json', {'name': 'desktop', 'version': '0.1.3', 'lockfileVersion': 3, 'packages': {'': {'name': 'desktop', 'version': '0.1.3'}, 'node_modules/library': {'version': '2.0.0'}}})
        base = self.commit()
        for name in ['rieke-release.json', 'desktop/package.json', 'workspace-app/package.json', 'desktop/package-lock.json']:
            data = json.loads((self.root / name).read_text())
            data['version'] = '0.1.4'
            if 'packages' in data:
                data['packages']['']['version'] = '0.1.4'
            self.write(name, data)
        self.commit()
        value = self.plan('--base', base)
        self.assertEqual(tuple(value[flag] for flag in FLAGS), (True, False, False, False, False))
        data = json.loads((self.root / 'desktop/package-lock.json').read_text())
        data['packages']['node_modules/library']['version'] = '2.1.0'
        self.write('desktop/package-lock.json', data)
        self.commit()
        self.assertTrue(self.plan('--base', base)['packaging'])

    def test_extended_requests_deep_checks_for_routine_application_changes(self):
        self.write('workspace-app/src/App.jsx', '// New UI\n')
        self.commit()
        value = self.plan('--base', self.initial, '--extended')
        self.assertEqual(tuple(value[flag] for flag in FLAGS), (True,) * 5)


    def test_no_comparable_release_requires_all_qualification(self):
        self.write('docs/guide.md', 'No earlier release\n')
        self.commit()
        self.git('tag', 'desktop-test-v0.1.4')
        value = self.plan()
        self.assertIsNone(value['base'])
        self.assertEqual(tuple(value[flag] for flag in FLAGS), (True,) * 5)
        self.assertIn('baseline', value['reason'].lower())

    def test_automatic_baseline_uses_highest_lower_ancestor_in_same_channel(self):
        self.git('tag', 'desktop-test-v0.1.2')
        self.git('tag', 'v0.1.3')
        self.write('docs/first.md', 'Earlier testing release\n')
        previous = self.commit()
        self.git('tag', 'desktop-test-v0.1.3')
        self.git('checkout', '--orphan', 'unrelated')
        self.write('docs/branch.md', 'Unrelated higher release\n')
        self.commit()
        self.git('tag', 'desktop-test-v0.1.9')
        self.git('checkout', '--detach', previous)
        self.write('docs/head.md', 'Current testing release\n')
        head = self.commit()
        self.git('tag', 'desktop-test-v0.2.0')
        value = self.plan('--head', 'desktop-test-v0.2.0')
        self.assertEqual(value['base'], previous)
        self.assertEqual(value['base_ref'], 'desktop-test-v0.1.3')
        self.assertEqual(value['head'], head)
        self.assertFalse(value['build_required'])

    def test_explicit_missing_and_nonancestor_bases_fail_closed(self):
        result = self.plan('--base', 'missing-release', success=False)
        self.assertTrue(result.stderr)
        self.git('checkout', '--orphan', 'other-history')
        self.write('docs/other.md', 'Different history\n')
        other = self.commit()
        self.git('checkout', '--detach', self.initial)
        self.plan('--base', other, success=False)
        self.plan('--base', '', success=False)

    def test_rename_and_deletion_keep_old_application_paths_in_scope(self):
        self.write('desktop/testing-install.cjs', '// Native update helper\n')
        self.write('desktop/requirements.lock', 'pinned-runtime==1\n')
        base = self.commit()
        (self.root / 'docs').mkdir()
        self.git('mv', 'desktop/testing-install.cjs', 'docs/retired-helper.cjs')
        self.git('rm', 'desktop/requirements.lock')
        self.commit()
        value = self.plan('--base', base)
        self.assertEqual(value['changed_paths'], ['desktop/requirements.lock', 'desktop/testing-install.cjs', 'docs/retired-helper.cjs'])
        self.assertTrue(value['build_required'])
        self.assertTrue(value['updater'])
        self.assertTrue(value['packaging'])

    def test_repository_argument_inspects_frozen_source_from_another_directory(self):
        self.write('workspace-app/src/App.jsx', '// User interface change\n')
        head = self.commit()
        output = self.root / '.git/external-plan.json'
        outside = self.root / '.git/outside'
        outside.mkdir()
        result = subprocess.run([sys.executable, str(PLANNER), '--repo', str(self.root), '--base', self.initial, '--output', str(output)], cwd=outside, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(output.read_text())
        self.assertEqual(value['head'], head)
        self.assertTrue(value['build_required'])


    def test_only_test_scripts_in_package_metadata_do_not_build(self):
        self.write('desktop/package.json', {'name': 'desktop', 'version': '0.1.3', 'scripts': {'test': 'node tests.cjs', 'dist': 'builder'}})
        base = self.commit()
        self.write('desktop/package.json', {'name': 'desktop', 'version': '0.1.3', 'scripts': {'test': 'node --test tests.cjs', 'test:e2e:smoke': 'node smoke.cjs', 'dist': 'builder'}})
        self.commit()
        self.assertFalse(self.plan('--base', base)['build_required'])
        self.write('desktop/package.json', {'name': 'desktop', 'version': '0.1.3', 'scripts': {'test': 'node --test tests.cjs', 'dist': 'different-builder'}})
        self.commit()
        value = self.plan('--base', base)
        self.assertTrue(value['build_required'])
        self.assertTrue(value['packaging'])

    def test_release_channel_is_not_inferred_from_unrelated_or_ambiguous_tags(self):
        self.git('tag', 'v0.1.2')
        self.write('docs/head.md', 'New head\n')
        self.commit()
        self.git('tag', 'desktop-test-v0.1.3')
        self.assertIsNone(self.plan()['base'])
        self.git('tag', 'v0.1.3')
        self.assertIsNone(self.plan()['base'])


    def test_version_bump_with_test_scripts_builds_routinely_but_production_changes_stay_deep(self):
        before = {'name': 'desktop', 'version': '0.1.3', 'scripts': {'test': 'node tests.cjs', 'dist': 'builder'},
                  'dependencies': {'library': '1.0.0'}, 'build': {'appId': 'org.riekeos.desktop'}}
        self.write('desktop/package.json', before)
        base = self.commit()
        after = {**before, 'version': '0.1.4', 'scripts': {'test': 'node --test tests.cjs', 'test:e2e:smoke': 'node smoke.cjs', 'dist': 'builder'}}
        self.write('desktop/package.json', after)
        self.write('rieke-release.json', {'version': '0.1.4'})
        self.commit()
        value = self.plan('--base', base)
        self.assertEqual(tuple(value[flag] for flag in FLAGS), (True, False, False, False, False))
        for change in ('production-script', 'dependency', 'build'):
            with self.subTest(change=change):
                data = json.loads(json.dumps(after))
                if change == 'production-script':
                    data['scripts']['dist'] = 'different-builder'
                elif change == 'dependency':
                    data['dependencies']['library'] = '2.0.0'
                else:
                    data['build']['appId'] = 'org.riekeos.changed'
                self.write('desktop/package.json', data)
                self.commit()
                value = self.plan('--base', base)
                self.assertEqual(tuple(value[flag] for flag in FLAGS), (True, True, False, True, False))


    def test_published_baseline_does_not_hide_changes_behind_an_unpublished_candidate(self):
        self.git('tag', 'desktop-test-v0.1.3')
        self.write('desktop/testing-install.cjs', '// Updater change not yet published\n')
        unpublished = self.commit()
        self.git('tag', 'desktop-test-v0.1.4')
        self.write('docs/head.md', 'Next release\n')
        self.commit()
        self.git('tag', 'desktop-test-v0.1.5')
        published = self.root / '.git/published-tags.json'
        published.write_text(json.dumps(['desktop-test-v0.1.3']))
        value = self.plan('--published-tags', str(published))
        self.assertEqual(value['base'], self.initial)
        self.assertEqual(value['base_ref'], 'desktop-test-v0.1.3')
        self.assertTrue(value['build_required'])
        self.assertTrue(value['updater'])
        # A reviewed explicit ancestor is still honored independently of the
        # discovery filter, including an unpublished candidate commit.
        value = self.plan('--base', unpublished, '--published-tags', str(published))
        self.assertEqual(value['base'], unpublished)
        self.assertFalse(value['build_required'])
        published.write_text('[]')
        value = self.plan('--published-tags', str(published))
        self.assertIsNone(value['base'])
        self.assertEqual(tuple(value[flag] for flag in FLAGS), (True,) * 5)


if __name__ == '__main__':
    unittest.main()
