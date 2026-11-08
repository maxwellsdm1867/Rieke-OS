"""Published release identity, history preservation and concurrent-update safety."""
import copy
import hashlib
import sys
import json
from pathlib import Path
import unittest

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
    release = {'id': 13, 'draft': False, 'prerelease': True, 'tag_name': tag,
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

    def releases(self):
        self.release_reads += 1
        if self.race == 'release' and self.release_reads > 1:
            new, _ = fixture('0.2.14'); new['id'] = 14
            return [self.release, new]
        return [copy.deepcopy(self.release)]

    def descriptor(self, tag):
        return self.raw

    def tag_commit(self, tag):
        return 'e' * 40 if self.race == 'tag' and self.release_reads > 1 else 'a' * 40

    def file(self, path, ref):
        return self.files[path]

    def request(self, endpoint, method='GET', data=None, paginate=False):
        if method != 'GET':
            self.writes.append((endpoint, method, data))
            if endpoint.endswith('/git/trees'):
                self.pending_files = {row['path']: row['content'] for row in data['tree']}
                return {'sha': 'f' * 40}
            if endpoint.endswith('/git/commits'):
                return {'sha': '1' * 40}
            if '/git/refs/heads/' in endpoint:
                if self.race == 'push':
                    raise RuntimeError('Update is not a fast forward')
                assert data['force'] is False
                self.files.update(self.pending_files); self.head = data['sha']
                return {}
            if '/releases/' in endpoint:
                assert set(data) == {'body'}
                self.release['body'] = data['body']
                return {}
            raise AssertionError(endpoint)
        if endpoint == f'repos/{pages.REPOSITORY}':
            return {'default_branch': 'main'}
        if '/git/ref/heads/' in endpoint:
            self.ref_reads += 1
            return {'object': {'sha': '2' * 40 if self.race == 'head' and self.ref_reads > 1 else self.head}}
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
        for fault in ('draft', 'stable', 'descriptor_digest', 'archive_digest', 'archive_name', 'tag', 'dirty', 'missing_sums'):
            with self.subTest(fault=fault):
                release, raw = fixture(); commit = 'a' * 40
                if fault == 'draft': release['draft'] = True
                if fault == 'stable': release['prerelease'] = False
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
        self.assertEqual(len([w for w in gh.writes if '/git/refs/' in w[0]]), 1)
        self.assertEqual(len([w for w in gh.writes if '/releases/' in w[0]]), 1)
        gh.writes.clear()
        self.assertFalse(pages.sync(gh, apply=True)['applied'])
        self.assertEqual(gh.writes, [])

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
