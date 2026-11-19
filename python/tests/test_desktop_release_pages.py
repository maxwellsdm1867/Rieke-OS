"""Published release identity, history preservation and concurrent-update safety."""
import copy
import hashlib
import sys
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

_import_path = sys.path[:]
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
    import desktop_release_pages as pages
finally:
    sys.path[:] = _import_path


def fixture(version='0.2.13'):
    tag = 'desktop-test-v' + version
    descriptor = {'format': 'rieke-desktop-test-release', 'version': 1,
                  'application_version': version, 'repository': pages.REPOSITORY,
                  'canonical_repository': pages.REPOSITORY, 'channel': 'unsigned-testing',
                  'platform': 'darwin', 'architecture': 'arm64',
                  'source_dirty': False, 'production_ready': False, 'source_commit': 'a' * 40,
                  'archive': {'filename': f'Disco-{version}-arm64.zip', 'sha256': 'b' * 64, 'size': 42}}
    raw = json.dumps(descriptor).encode()
    release = {'id': 13, 'draft': False, 'prerelease': True, 'tag_name': tag, 'name': f'Disco {version} testing',
               'published_at': '2026-11-07T23:28:23Z', 'updated_at': '2026-11-07T23:29:00Z',
               'body': "Unsigned testing.\n\n## What's new\n\n- First feature\n  continued.\n\n- Second feature\n\n## History\n\nEarlier failed run retained.\n",
               'assets': []}
    for name, digest, size in [('desktop-release.json', hashlib.sha256(raw).hexdigest(), len(raw)),
                               (descriptor['archive']['filename'], 'b' * 64, 42), ('SHA256SUMS', 'c' * 64, 176)]:
        release['assets'].append({'name': name, 'state': 'uploaded', 'size': size, 'digest': 'sha256:' + digest,
                                 'browser_download_url': f'{pages.WEB}/releases/download/{tag}/{name}'})
    return release, raw


class FakeGitHub:
    def __init__(self):
        self.release, self.raw = fixture()
        self.files = {'README.md': pages.block('release-banner', 'Old download') + '\n\n# DISCO\n\n'
                      + pages.block('current-release', 'Old current') + '\n\nKeep scientific docs.\n',
                      'CHANGELOG.md': '# Disco changelog\n\n<!-- disco:changelog-insert -->\n\n## 0.1.10\n\nHistory.\n'}
        self.head = 'd' * 40
        self.writes = []
        self.release_reads = 0
        self.race = None
        self.ref_reads = 0
        self.stage = None
        self.removed = []
        self.verdicts = ['success']
        self.run_overrides = {}
        self.run_reads = []
        self.job_overrides = {}
        self.badge = {'databaseId': 2, 'tagName': 'desktop-test-v0.2.2', 'publishedAt': '2026-10-01T00:00:00Z'}

    def latest(self):
        return self.badge

    def releases(self):
        self.release_reads += 1
        if ((self.race == 'release' and self.release_reads > 1)
                or (self.race == 'late release' and self.release_reads > 2)):
            new, _ = fixture('0.2.14'); new['id'] = 14
            return [self.release, new]
        return [copy.deepcopy(self.release)]

    def descriptor(self, tag):
        return self.raw

    def tag_commit(self, tag):
        if ((self.race == 'tag' and self.release_reads > 1)
                or (self.race == 'late tag' and self.release_reads > 2)):
            return 'e' * 40
        return 'a' * 40

    def file(self, path, ref):
        return self.files[path]

    def remove_staging(self, commit):
        if self.stage != commit:
            raise ValueError('Staging ref no longer owned')
        self.removed.append(commit)
        self.stage = None

    def request(self, endpoint, method='GET', data=None, paginate=False, *, api_version=None):
        if method != 'GET':
            self.writes.append((endpoint, method, data))
            if endpoint.endswith('/git/trees'):
                self.pending_files = {row['path']: row['content'] for row in data['tree']}
                return {'sha': 'f' * 40}
            if endpoint.endswith('/git/commits'):
                return {'sha': '1' * 40}
            if endpoint.endswith('/git/refs'):
                if self.stage is not None:
                    raise ValueError('Staging ref already exists')
                self.stage = data['sha']
                assert data['ref'] == 'refs/heads/' + pages.staging_branch(self.stage)
                return {'object': {'sha': self.stage}}
            if endpoint.endswith('/workflows/integration.yml/dispatches'):
                assert api_version == '2026-03-10'
                assert data == {'ref': pages.staging_branch(self.stage), 'inputs': {'base_sha': self.head}}
                return {'workflow_run_id': 71}
            if '/statuses/' in endpoint:
                assert endpoint.endswith('/statuses/' + self.stage)
                assert data['context'] == pages.VERDICT and data['state'] == 'success'
                assert data['target_url'] == pages.WEB + '/actions/runs/71/attempts/1'
                return {}
            if '/git/refs/heads/' in endpoint:
                assert self.writes[-2][0].endswith('/statuses/' + data['sha'])
                if self.race == 'push':
                    raise RuntimeError('Update is not a fast forward')
                assert data['force'] is False
                self.files.update(self.pending_files); self.head = data['sha']
                return {}
            if '/releases/' in endpoint:
                assert set(data) <= {'body', 'name', 'prerelease', 'make_latest'}
                if 'make_latest' in data:
                    assert data['make_latest'] == 'true' and data['prerelease'] is False
                    self.badge = {'databaseId': self.release['id'], 'tagName': self.release['tag_name'],
                                  'publishedAt': self.release['published_at']}
                self.release.update({k: v for k, v in data.items() if k != 'make_latest'})
                return {}
            raise AssertionError(endpoint)
        if endpoint == f'repos/{pages.REPOSITORY}':
            return {'default_branch': 'main'}
        if '/git/ref/heads/disco-release-pages-ci/' in endpoint:
            return {'object': {'sha': self.stage}}
        if '/git/ref/heads/' in endpoint:
            self.ref_reads += 1
            moved = ((self.race == 'head' and self.ref_reads > 1)
                     or (self.race == 'late head' and self.ref_reads > 2))
            return {'object': {'sha': '2' * 40 if moved else self.head}}
        if endpoint.endswith('/actions/runs/71'):
            if self.run_reads:
                result = self.run_reads.pop(0)
                if isinstance(result, Exception): raise result
                self.run_overrides = result
            repo = {'full_name': pages.REPOSITORY}
            return dict({'id': 71, 'head_sha': self.stage, 'event': 'workflow_dispatch', 'head_branch': pages.staging_branch(self.stage),
                         'repository': repo, 'head_repository': repo, 'path': pages.INTEGRATION,
                         'status': 'completed', 'conclusion': 'success', 'run_attempt': 1}, **self.run_overrides)
        if endpoint.endswith('/runs/71/attempts/1/jobs?per_page=100'):
            return {'jobs': [dict({'name': pages.VERDICT, 'status': 'completed', 'conclusion': verdict,
                                  'head_sha': self.stage, 'run_id': 71}, **self.job_overrides) for verdict in self.verdicts]}
        if '/git/commits/' in endpoint:
            return {'tree': {'sha': '3' * 40}}
        if '/releases/' in endpoint:
            result = copy.deepcopy(self.release)
            if self.race == 'notes':
                result.update(body='Concurrent scientist edit', updated_at='later')
            return result
        raise AssertionError(endpoint)


class ReleasePagesTests(unittest.TestCase):
    def test_numeric_version_order_ignores_drafts_and_unrelated_releases(self):
        old, _ = fixture('0.2.9'); latest, _ = fixture('0.2.13')
        draft, _ = fixture('0.2.99'); draft['draft'] = True
        unrelated = dict(latest, tag_name='some-other-v9.0.0')
        self.assertEqual(pages.newest([old, draft, latest, unrelated]), latest)

    def test_descriptor_tag_and_asset_identity_refuse_tampering(self):
        for fault in ('draft', 'wrong_channel', 'descriptor_digest', 'archive_digest', 'archive_name', 'tag', 'dirty', 'missing_sums'):
            with self.subTest(fault=fault):
                release, raw = fixture(); commit = 'a' * 40
                if fault == 'draft': release['draft'] = True
                if fault == 'wrong_channel':
                    d = json.loads(raw); d['channel'] = 'stable'; raw = json.dumps(d).encode()
                if fault == 'descriptor_digest': release['assets'][0]['digest'] = 'sha256:' + 'e' * 64
                if fault == 'archive_digest': release['assets'][1]['digest'] = 'sha256:' + 'e' * 64
                if fault == 'archive_name': release['assets'][1]['name'] = 'Disco-0.2.12-arm64.zip'
                if fault == 'tag': commit = 'e' * 40
                if fault == 'dirty':
                    d = json.loads(raw); d['source_dirty'] = True; raw = json.dumps(d).encode()
                if fault == 'missing_sums': release['assets'].pop()
                with self.assertRaises(ValueError): pages.validate(release, raw, commit)

    def test_render_preserves_history_and_unmanaged_text_and_is_idempotent(self):
        gh = FakeGitHub(); release = pages.validate(gh.release, gh.raw, 'a' * 40)
        files, notes = pages.render(gh.files['README.md'], gh.files['CHANGELOG.md'], release)
        self.assertIn('Keep scientific docs.', files['README.md'])
        self.assertIn('## 0.1.10\n\nHistory.', files['CHANGELOG.md'])
        self.assertIn('- Second feature', files['CHANGELOG.md'])
        self.assertIn('Earlier failed run retained.', notes)
        release['notes'] = notes
        self.assertEqual(pages.render(files['README.md'], files['CHANGELOG.md'], release), (files, notes))
        newer, raw = fixture('0.2.14')
        newfiles, _ = pages.render(files['README.md'], files['CHANGELOG.md'], pages.validate(newer, raw, 'a' * 40))
        self.assertLess(newfiles['CHANGELOG.md'].index('## 0.2.14'), newfiles['CHANGELOG.md'].index('## 0.2.13'))
        self.assertEqual(newfiles['CHANGELOG.md'].count('## 0.2.13'), 1)

    def test_legacy_reviewed_bullets_get_heading_without_losing_history(self):
        text = 'Intro.\n\n- Approved change\n\n## History\nRetain this.\n'
        summary, normalized = pages.release_notes(text)
        self.assertEqual(summary, '- Approved change')
        self.assertIn("## What's new\n\n- Approved change", normalized)
        self.assertIn('## History\nRetain this.', normalized)
        with self.assertRaises(ValueError): pages.release_notes('No reviewed feature list.')

    def test_missing_or_ambiguous_markers_and_unmanaged_current_entry_refuse(self):
        gh = FakeGitHub(); release = pages.validate(gh.release, gh.raw, 'a' * 40)
        for readme in ('No markers', gh.files['README.md'] + '<!-- disco:current-release:start -->'):
            with self.assertRaises(ValueError): pages.render(readme, gh.files['CHANGELOG.md'], release)
        with self.assertRaisesRegex(ValueError, 'not managed'):
            pages.render(gh.files['README.md'], gh.files['CHANGELOG.md'] + '\n## 0.2.13 - old\n', release)

    def test_dry_run_no_mutations_and_apply_atomic_docs_then_noop(self):
        gh = FakeGitHub()
        result = pages.sync(gh)
        self.assertEqual(result['changed_files'], ['README.md', 'CHANGELOG.md'])
        self.assertEqual(gh.writes, [])
        result = pages.sync(gh, apply=True)
        self.assertTrue(result['applied'])
        self.assertEqual(result['integration']['commit'], result['documentation_commit'])
        self.assertEqual(result['integration']['run_id'], 71)
        self.assertEqual(gh.removed, [result['documentation_commit']])
        self.assertEqual(len([w for w in gh.writes if '/git/refs/' in w[0]]), 1)
        self.assertEqual(len([w for w in gh.writes if '/releases/' in w[0]]), 1)
        gh.writes.clear()
        self.assertFalse(pages.sync(gh, apply=True)['applied'])
        self.assertEqual(gh.writes, [])

    def test_badge_only_repair_and_next_testing_release(self):
        gh = FakeGitHub()
        for version, identifier in [('0.2.15', 15), ('0.2.16', 16)]:
            gh.release, gh.raw = fixture(version)
            gh.release['id'] = identifier
            release = pages.validate(gh.release, gh.raw, gh.tag_commit(gh.release['tag_name']))
            gh.files, gh.release['body'] = pages.render(gh.files['README.md'], gh.files['CHANGELOG.md'], release)
            self.assertTrue(pages.sync(gh)['latest_changed'])
            self.assertFalse(gh.writes)
            pages.sync(gh, apply=True)
            self.assertEqual(gh.writes, [(f'repos/{pages.REPOSITORY}/releases/{identifier}', 'PATCH',
                                          {'prerelease': False, 'make_latest': 'true'})])
            self.assertEqual(gh.latest()['tagName'], gh.release['tag_name'])
            self.assertIn('testing', gh.release['name'])
            gh.writes.clear()
            self.assertFalse(pages.sync(gh, apply=True)['applied'])
            self.assertFalse(gh.writes)

    def test_absent_badge_and_newer_non_testing_latest(self):
        gh = FakeGitHub()
        gh.badge = None
        self.assertTrue(pages.sync(gh)['latest_changed'])
        gh.badge = {'databaseId': 99, 'tagName': 'v1.0.0', 'publishedAt': '2026-11-10T12:00:00Z'}
        result = pages.sync(gh, apply=True)
        self.assertFalse(result['latest_changed'])
        self.assertTrue(gh.release['prerelease'])
        self.assertEqual(gh.latest()['databaseId'], 99)

    def test_wrong_or_missing_integration_cannot_update_main_or_release_notes(self):
        for field, value in [('conclusion','failure'),('head_sha','0'*40),('event','push'),('id',72),
                             ('path','.github/workflows/other.yml'),('head_branch','main'),
                             ('repository',{'full_name':'other/repo'}),('head_repository',{'full_name':'other/repo'}),
                             ('run_attempt',0),('verdicts',[]),('verdicts',['skipped']),
                             ('verdicts',['failure']),('verdicts',['success','success']),
                             ('job',{'head_sha':'0'*40}),('job',{'run_id':72}),('job',{'name':'Other check'})]:
            with self.subTest(field=field,value=value):
                gh = FakeGitHub()
                if field == 'verdicts': gh.verdicts = value
                elif field == 'job': gh.job_overrides = value
                else: gh.run_overrides[field] = value
                with self.assertRaises(ValueError):
                    pages.sync(gh, apply=True)
                self.assertFalse(any(write[1]=='PATCH' or '/statuses/' in write[0] for write in gh.writes))
                self.assertEqual(gh.removed, ['1'*40])

    def test_queued_and_temporarily_unreadable_run_is_only_dispatched_once(self):
        gh = FakeGitHub()
        gh.run_reads = [subprocess.CalledProcessError(1, 'gh api'), {'status':'queued','conclusion':None}, {}]
        with patch.object(pages.time,'sleep'):
            result = pages.sync(gh, apply=True)
        self.assertTrue(result['applied'])
        self.assertEqual(sum(w[0].endswith('/dispatches') for w in gh.writes), 1)

    def test_release_body_only_edit_does_not_stage_or_mutate_a_git_ref(self):
        gh = FakeGitHub()
        release = pages.validate(gh.release, gh.raw, gh.tag_commit(gh.release['tag_name']))
        gh.files, _ = pages.render(gh.files['README.md'], gh.files['CHANGELOG.md'], release)
        result = pages.sync(gh, apply=True)
        self.assertTrue(result['applied'])
        self.assertEqual(result['changed_files'], [])
        self.assertEqual([(p.rsplit('/',2)[1],method) for p,method,_ in gh.writes], [('releases','PATCH')])

    def test_timeout_and_late_races_preserve_main_and_release(self):
        for race in ('late release','late head','late tag'):
            gh = FakeGitHub(); gh.race = race
            with self.subTest(race=race), self.assertRaises(ValueError):
                pages.sync(gh, apply=True)
            self.assertFalse(any(write[1]=='PATCH' for write in gh.writes))
            self.assertEqual(gh.removed, ['1'*40])
        gh = FakeGitHub()
        gh.run_overrides = {'status':'in_progress', 'conclusion':None}
        with patch.object(pages.time,'monotonic',side_effect=[0,1,901,901]), patch.object(pages.time,'sleep'), self.assertRaises(TimeoutError):
            pages.sync(gh, apply=True)
        self.assertFalse(any(write[1]=='PATCH' for write in gh.writes))
        self.assertEqual(gh.removed, ['1'*40])

    def test_staging_collision_preserves_other_owner(self):
        gh = FakeGitHub(); gh.stage = '1'*40
        with self.assertRaisesRegex(ValueError, 'already exists'):
            pages.sync(gh, apply=True)
        self.assertEqual(gh.removed, [])
        self.assertFalse(any('/dispatches' in write[0] or write[1]=='PATCH' for write in gh.writes))

    def test_leased_staging_cleanup_preserves_moved_tip(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)/'local.git'
            subprocess.run(['git','init','--bare','-q',repo], check=True)
            def git(*args, data=None):
                return subprocess.check_output(['git','-C',repo,'-c','user.name=Test','-c','user.email=test@example.test',
                                                *args], input=data,text=True).strip()
            tree = git('mktree',data='')
            candidate = git('commit-tree',tree,'-m','docs')
            moved = git('commit-tree',tree,'-p',candidate,'-m','concurrent change')
            ref = 'refs/heads/' + pages.staging_branch(candidate)
            git('update-ref',ref,moved)
            with patch.object(pages,'WEB',str(repo.with_suffix(''))):
                with self.assertRaises(subprocess.CalledProcessError):
                    pages.GitHub().remove_staging(candidate)
                self.assertEqual(git('rev-parse',ref), moved)
                git('update-ref',ref,candidate,moved)
                pages.GitHub().remove_staging(candidate)
            self.assertEqual(git('for-each-ref',ref), '')

    def test_release_head_and_tag_races_fail_before_writes(self):
        for race in ('release', 'head', 'tag'):
            with self.subTest(race=race):
                gh = FakeGitHub(); gh.race = race
                with self.assertRaises(ValueError): pages.sync(gh, apply=True)
                self.assertEqual(gh.writes, [])

    def test_non_fast_forward_is_not_forced_and_concurrent_notes_are_preserved(self):
        gh = FakeGitHub(); gh.race = 'push'
        with self.assertRaises(RuntimeError): pages.sync(gh, apply=True)
        self.assertFalse(gh.writes[-1][2]['force'])
        self.assertFalse(any('/releases/' in w[0] for w in gh.writes))
        gh = FakeGitHub(); gh.race = 'notes'
        with self.assertRaisesRegex(ValueError, 'concurrently'): pages.sync(gh, apply=True)
        self.assertFalse(any('/releases/' in w[0] for w in gh.writes))


if __name__ == '__main__':
    unittest.main()
