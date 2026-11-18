"""No-network tests for guarded repair publication, lineage, and green reconciliation."""

import base64
import difflib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import disco_repair_publish as repair


A, B, C, D = (s * 40 for s in 'abcd')
PATH = 'workspace-app/src/components/NavigationLoading.jsx'
BOT = {'login': 'github-actions[bot]', 'id': 41898282}


def proposal(path, old, new):
    return ''.join(
        difflib.unified_diff(
            old.splitlines(True), new.splitlines(True), fromfile='a/' + path, tofile='b/' + path
        )
    ).encode()


def context(pr=12):
    return dict(
        run_id=7,
        attempt=1,
        head_sha=A,
        branch='feature' if pr else 'main',
        pr=pr,
        root=7,
        count=0,
        origin=pr or 0,
        actor=55 if pr else 0,
    )


class PatchTests(unittest.TestCase):
    def apply(self, name, raw, original=None, *, source_mode='100644'):
        original = (original or 'const visible = showing;\n').encode()
        oid = hashlib.sha1(b'blob ' + str(len(original)).encode() + b'\0' + original).hexdigest()

        def api(key):
            if key.startswith('contents/'):
                return dict(
                    type='file',
                    path=name,
                    encoding='base64',
                    size=len(original),
                    content=base64.b64encode(original).decode(),
                    sha=oid,
                )
            if key == 'git/commits/' + A:
                return {'tree': {'sha': B}}
            if key.startswith('git/trees/'):
                return {
                    'tree': [
                        {'path': x, 'type': 'tree', 'mode': '040000', 'sha': B} for x in name.split('/')[:-1]
                    ]
                    + [{'path': name.split('/')[-1], 'type': 'blob', 'mode': source_mode, 'sha': oid}]
                }
            self.fail(key)

        with tempfile.TemporaryDirectory() as tmp, patch.object(repair, 'api', side_effect=api):
            path = Path(tmp) / 'proposed.patch'
            path.write_bytes(raw)
            return repair.apply_patch(path, A)

    def test_existing_ui_and_startup_fix_apply_using_git_index(self):
        old, new = 'const visible = showing;\n', 'const visible = showing && !closing;\n'
        self.assertEqual(self.apply(PATH, proposal(PATH, old, new), old), {PATH: new})
        old = 'let elsewhere = true;\nasync function startScientificUI() {\n  lifecycleStatus = active;\n}\nfunction registerIPC() {\n}\n'
        new = old.replace('  lifecycleStatus', '  if (quitting) return;\n  lifecycleStatus')
        name = 'desktop/main.cjs'
        self.assertEqual(self.apply(name, proposal(name, old, new), old), {name: new})
        other = old.replace('let elsewhere = true', 'let elsewhere = false')
        with self.assertRaisesRegex(ValueError, 'startup composition'):
            self.apply(name, proposal(name, old, other), old)

    def test_protected_paths_modes_cap_limits_and_stale_context(self):
        old, new = 'const visible = showing;\n', 'const visible = true;\n'
        for name in (
            '.github/workflows/integration.yml',
            'workspace-app/package.json',
            'python/disco/metadata/typed_index.py',
            'desktop/security.cjs',
            'python/tests/test_benchmark.py',
            '.env',
            '../outside.js',
            'tools/disco_repair_publish.py',
        ):
            with self.subTest(name=name), self.assertRaises((ValueError, subprocess.CalledProcessError)):
                self.apply(name, proposal(name, old, new), old)
        for mode in ('120000', '100755'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'regular files'):
                self.apply(PATH, proposal(PATH, old, new), old, source_mode=mode)
        for raw in (
            b'x' * (repair.PATCH_LIMIT + 1),
            b'\x00binary',
            proposal(PATH, old, new) + proposal(PATH, old, new),
        ):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                self.apply(PATH, raw)
        with self.assertRaises(subprocess.CalledProcessError):
            self.apply(PATH, proposal(PATH, old, new), 'another document\n')

    def test_scientific_and_external_operations_refused_in_allowed_files(self):
        for line in (
            'fetch(url)',
            'require("node:fs")',
            'process.env.SECRET',
            'window.open(url)',
            'return authorizeRelease(x);',
        ):
            with self.subTest(line=line), self.assertRaises(ValueError):
                repair.safe_changes(PATH, 'const visible = true;', line)
        name = 'python/workspace_startup_registry.py'
        repair.safe_changes(
            name,
            'def ordered_projects(p):\n    return p\n',
            'def ordered_projects(p):\n    return sorted(p)\n',
        )
        for new in ('return other(p)', 'return load(p + "elsewhere")', 'return getattr(p, "env")'):
            with self.subTest(line=new), self.assertRaises(ValueError):
                repair.safe_changes(
                    name,
                    'def ordered_projects(p):\n    return load(p)\n',
                    'def ordered_projects(p):\n    ' + new + '\n',
                )

    def test_bounded_fetch_handles_only_one_ordinary_member_for_the_current_workflow(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, GITHUB_RUN_ID='9', GITHUB_RUN_ATTEMPT='2'),
        ):
            target = Path(tmp) / 'codex.patch'
            with self.assertRaises(ValueError):
                repair.fetch_patch(8, 2, target)
            for member, mode, raw, extra, allowed in [
                ('codex.patch', 0o100644, b'patch', False, True),
                ('../codex.patch', 0o100644, b'p', False, False),
                ('codex.patch', 0o120777, b'/etc/passwd', False, False),
                ('codex.patch', 0o100644, b'p', True, False),
                ('codex.patch', 0o100644, b'p' * (repair.PATCH_LIMIT + 1), False, False),
            ]:
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, 'w') as z:
                    info = zipfile.ZipInfo(member)
                    info.external_attr = mode << 16
                    z.writestr(info, raw)
                    if extra:
                        z.writestr('more', b'x')
                name = 'disco-repair-patch-9-2'
                row = {
                    'name': name,
                    'expired': False,
                    'digest': 'sha256:' + hashlib.sha256(archive.getvalue()).hexdigest(),
                }
                with (
                    patch.object(repair, 'api', return_value={'artifacts': [row]}),
                    patch.object(
                        repair,
                        '_download_archive',
                        side_effect=lambda repo, r, dest, limit: dest.write_bytes(archive.getvalue()),
                    ),
                ):
                    if allowed:
                        repair.fetch_patch(9, 2, target)
                        self.assertEqual(target.read_bytes(), b'patch')
                        target.unlink()
                    else:
                        with self.assertRaises(ValueError):
                            repair.fetch_patch(9, 2, target)
                        self.assertFalse(target.exists())


class LifecycleTests(unittest.TestCase):
    def test_candidate_requires_one_verified_parent_then_marks_before_nonforced_compare_and_swap(self):
        for pr in (12, None):
            ctx = context(pr)
            calls = []

            def api(path, method='GET', data=None, **kw):
                calls.append((path, method, data, kw))
                if path == 'git/commits/' + A:
                    return {'tree': {'sha': D}}
                if path == 'git/trees':
                    return {'sha': B}
                if path == 'git/commits':
                    return {'sha': C, 'parents': [{'sha': A}], 'tree': {'sha': B}}
                if path == '' and method == 'GET':
                    return {'node_id': 'repo-id'}
                if path == 'graphql':
                    return {'data': {'updateRefs': {'clientMutationId': None}}}
                if path == 'pulls':
                    return {
                        'number': 13,
                        'user': {'id': 55},
                        'base': {'ref': 'main'},
                        'head': {'sha': C, 'ref': repair.PREFIX + '7'},
                    }
                if path.startswith('statuses/'):
                    return {'creator': BOT, 'description': data['description']}
                self.fail(path)

            with (
                patch.object(repair, 'plan', return_value=dict(ctx, action='generate')),
                patch.object(repair, 'current', return_value=ctx),
                patch.object(repair, 'apply_patch', return_value={PATH: 'safe'}),
                patch.object(repair, 'api', side_effect=api),
            ):
                result = repair.publish(7, 1, Path('offline'))
            self.assertEqual(result['pr'], pr or 13)
            paths = [row[0] for row in calls]
            self.assertLess(paths.index('statuses/' + C), paths.index('graphql'))
            command = next(row for row in calls if row[0] == 'graphql')
            update = command[2]['variables']['input']['refUpdates'][0]
            self.assertEqual(
                update,
                dict(
                    name='refs/heads/' + ('feature' if pr else repair.PREFIX + '7'),
                    beforeOid=A if pr else repair.ZERO,
                    afterOid=C,
                    force=False,
                ),
            )
            self.assertTrue(command[3]['publisher'])
            self.assertFalse(
                any(kw.get('publisher') for key, _, _, kw in calls if key.startswith('statuses/'))
            )
            if not pr:
                self.assertEqual(paths[-2:], ['pulls', 'statuses/' + C])

    def test_immutable_bot_records_bind_attempts_and_ignore_untrusted_markers(self):
        row = {
            'state': 'success',
            'creator': BOT,
            'context': repair.CONTEXT,
            'target_url': repair.WEB + '/actions/runs/7',
            'description': 'v1 7 2 12 12 55',
        }
        forged = dict(row, creator={'login': repair.OWNER, 'id': 55}, description='v1 77 1 9 9 99')
        with patch.object(repair, 'api', return_value=[forged, row]):
            rec = repair.marker(A)
        self.assertEqual(rec, dict(root=7, count=2, origin=12, pr=12, actor=55))
        ctx = dict(context(), count=rec['count'])
        with (
            patch.object(repair, 'current', return_value=ctx),
            patch.object(repair, 'issues', return_value=[]),
        ):
            self.assertEqual(repair.plan(7, 1)['action'], 'exhausted')
        with (
            patch.object(repair, 'api', return_value=[dict(row, target_url='https://elsewhere')]),
            self.assertRaises(ValueError),
        ):
            repair.marker(A)
        with (
            patch.object(repair, 'api', return_value={'creator': {'id': 55, 'login': repair.OWNER}}),
            self.assertRaises(ValueError),
        ):
            repair.mark(A, rec)

    def test_escalation_deduplicates_and_uses_trusted_failed_job_link(self):
        ctx = context()
        issue = {'number': 22, 'user': BOT, 'assignees': [{'login': repair.OWNER}]}
        steps = [{'conclusion': 'failure', 'name': 'Restore workspace'}]
        jobs = {
            'jobs': [
                {'conclusion': 'failure', 'id': 101, 'name': 'Installed Startup and Quit', 'steps': steps}
            ]
        }
        with (
            patch.dict(os.environ, GITHUB_RUN_ID='900'),
            patch.object(repair, 'issues', return_value=[]),
            patch.object(repair, 'api', side_effect=[jobs, issue]) as api,
        ):
            self.assertEqual(repair.handoff(ctx, 'generation')['issue'], 22)
        payload = api.call_args.args[2]
        self.assertEqual(payload['assignees'], [repair.OWNER])
        self.assertEqual(payload['title'], '[Disco] Action needed — installed startup and Quit')
        self.assertIn('Restore workspace', payload['body'])
        self.assertIn('/actions/runs/900', payload['body'])
        self.assertIn('/actions/runs/7/job/101', payload['body'])
        with (
            patch.object(repair, 'issues', return_value=[(7, 12, A, issue)]),
            patch.object(repair, 'api') as api,
        ):
            self.assertEqual(repair.handoff(ctx, 'generation')['action'], 'already_escalated')
            api.assert_not_called()
        with (
            patch.object(repair, 'issues', return_value=[]),
            patch.object(repair, 'api', side_effect=[jobs, dict(issue, assignees=[])]),
            self.assertRaises(ValueError),
        ):
            repair.handoff(ctx, 'generation')

    def test_green_only_merges_the_proved_main_repair_after_exact_base_and_head_recheck(self):
        ctx = dict(context(), branch=repair.PREFIX + '7', origin=0, count=1)
        names = ('workspace-ci.yml', 'everyday-million.yml')
        references = [
            {'path': f'{repair.REPO}/.github/workflows/{n}@{D}', 'sha': D, 'ref': 'refs/pull/12/merge'}
            for n in names
        ]
        for base, merged in ((B, True), (C, False)):
            calls = []

            def api(path, method='GET', data=None, **kw):
                calls.append((path, method, data, kw))
                if path == 'actions/runs/8':
                    return {'referenced_workflows': references}
                if path == 'actions/runs/7':
                    return {'event': 'push', 'head_branch': 'main', 'head_sha': B}
                if path == 'branches/main':
                    return {'commit': {'sha': base}}
                if path == 'git/commits/' + D:
                    return {'parents': [{'sha': B}, {'sha': A}]}
                if path == 'pulls/12/merge':
                    return {'merged': True, 'sha': D}
                self.fail(path)

            with (
                patch.object(repair, 'current', return_value=ctx),
                patch.object(repair, 'api', side_effect=api),
                patch.object(repair, 'handoff', return_value={'action': 'escalated'}),
            ):
                result = repair.reconcile(8, 1)
            self.assertEqual(result['action'], 'merged' if merged else 'stale')
            writes = [row for row in calls if row[1] == 'PUT']
            self.assertEqual(len(writes), int(merged))
            if merged:
                self.assertEqual(writes[0][2], {'sha': A, 'merge_method': 'merge'})

    def test_normal_green_pr_only_closes_related_handoffs_after_verified_ancestry(self):
        ctx = context()
        issues = [(8, 12, B, {'number': 22, 'state': 'open'}), (9, 14, C, {'number': 23, 'state': 'open'})]
        with (
            patch.object(repair, 'current', return_value=ctx),
            patch.object(repair, 'issues', return_value=issues),
            patch.object(repair, 'api', side_effect=[{'status': 'ahead'}, {}]) as api,
        ):
            self.assertEqual(repair.reconcile(77, 1), {'action': 'resolved', 'issues': [22]})
            self.assertEqual(api.call_args.args[0], 'issues/22')
            self.assertFalse(any('merge' in str(call.args[0]) for call in api.call_args_list))

    def test_green_main_closes_merged_pr_issue_only_with_included_failed_lineage(self):
        ctx = context(None)
        issue = (8, 12, B, {'number': 22, 'state': 'open'})
        pr = {
            'number': 12,
            'state': 'closed',
            'merged_at': '2026-11-17',
            'merge_commit_sha': C,
            'base': {'ref': 'main', 'repo': {'full_name': repair.REPO}},
            'head': {'sha': D, 'repo': {'full_name': repair.REPO}},
        }
        for state, ancestry, expected in [
            ('closed', 'ahead', [22]),
            ('open', 'ahead', []),
            ('closed', 'diverged', []),
        ]:

            def api(path, *args, **kwargs):
                if path == 'pulls/12':
                    return dict(pr, state=state)
                if path == f'compare/{B}...{D}':
                    return {'status': ancestry}
                if path in (f'compare/{C}...{A}', f'compare/{B}...{A}'):
                    return {'status': 'ahead'}
                if path == 'issues/22' and expected:
                    return {}
                self.fail(path)

            with (
                self.subTest(state=state, ancestry=ancestry),
                patch.object(repair, 'current', return_value=ctx),
                patch.object(repair, 'issues', return_value=[issue]),
                patch.object(repair, 'api', side_effect=api),
            ):
                self.assertEqual(repair.reconcile(77, 1)['issues'], expected)


if __name__ == '__main__':
    unittest.main()
