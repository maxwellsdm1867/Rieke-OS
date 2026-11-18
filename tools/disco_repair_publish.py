"""Publish bounded Disco repairs. Run only from the trusted default-branch workflow."""

import argparse
import ast
import base64
from collections import Counter
import difflib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlencode
import zipfile

if __package__:
    from . import integration_incidents as inbox
    from .desktop_source_ci import _download_archive
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import integration_incidents as inbox
    from desktop_source_ci import _download_archive

REPO = inbox.REPOSITORY
OWNER = REPO.split('/')[0]
WEB = 'https://github.com/' + REPO
BOT = 41898282  # github-actions[bot] on github.com
CONTEXT = 'Disco automated repair record'
PREFIX = 'codex/disco-repair-main-'
ZERO = '0' * 40
LIMIT = 2
PATCH_LIMIT = 100 * 1024
FILE_LIMIT = 256 * 1024
UI = 'workspace-app/src/'
# Only existing presentation modules and the designated startup/close owners.
ALLOWED = {
    UI + name
    for name in (
        'WorkspaceNavigation.css',
        'styles.css',
        'themes.css',
        'appearance/appAppearance.js',
        'appearance/appearanceThemes.js',
        'appearance/ui/AppAppearance.jsx',
        'appearance/ui/AppAppearance.css',
        'workspace-navigation/useWorkspaceNavigation.js',
        'workspace-navigation/workspaceNavigation.js',
        'components/NavigationLoading.jsx',
        'components/NavigationLoading.css',
        'components/PaneDivider.jsx',
        'components/StableContent.jsx',
        'components/StableContent.css',
        'components/DesktopDraftRecovery.jsx',
    )
} | {
    'desktop/main.cjs',
    'desktop/startup/startup-session.cjs',
    'desktop/close/quit-coordinator.cjs',
    'python/workspace_lifecycle.py',
    'python/workspace_startup_failure.py',
    'python/workspace_startup_registry.py',
}
# Refuse changes on either side of a hunk that touch external effects, scientific
# authority or ownership/safety checks. Ordinary lifecycle state changes can use
# the existing composition owner without changing its privileged operations.
SENSITIVE = re.compile(
    r'(?i)\b(?:import|require|export|fetch|URL|WebSocket|XMLHttpRequest|navigator|window\.open|ipc\w*|'
    r'process|exec\w*|spawn\w*|eval|Function|constructor|prototype|__proto__|globalThis|Buffer|atob|'
    r'child_process|subprocess|os|sys|fcntl|fs|net|http|https|shell|cookie|credential\w*|secret\w*|token|capability|'
    r'open|readFile\w*|writeFile\w*|unlink\w*|getattr|setattr|delattr|vars|globals|locals|'
    r'__\w+__|socket|environ|localStorage|sessionStorage|sendBeacon|XMLSerializer|document\.cookie|'
    r'validate\w*|authorize\w*|matchesHealth|expectedHealth|atomicJSON|database|sql|h5|'
    r'stopAcknowledged|abnormalExit|services_closed|drafts_saved|assert|sha256)\b|'
    r'/api/|https?:|data:|javascript:|@import|url\s*\(|dangerouslySetInnerHTML|innerHTML|'
    r'\\(?:u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2})'
)
ISSUE_MARK = re.compile(r'<!-- disco-repair-v1 root=(\d+) target=(\d+) failed=([0-9a-f]{40}) -->')
STATUS_MARK = re.compile(r'v1 (\d+) ([12]) (\d+) (\d+) (\d+)')


def api(path, method='GET', data=None, *, publisher=False, paginate=False):
    env = dict(os.environ)
    credential = env.pop('DISCO_REPAIR_PUSH_TOKEN', '')
    if publisher:
        if not credential or credential == env.get('GH_TOKEN'):
            raise ValueError('A separate Disco repair publisher credential is required')
        env['GH_TOKEN'] = credential
    endpoint = 'graphql' if path == 'graphql' else f'repos/{REPO}' + ('/' + path if path else '')
    cmd = ['gh', 'api', endpoint, '--method', method]
    if paginate:
        cmd.extend(['--paginate', '--slurp'])
    if data is not None:
        cmd.extend(['--input', '-'])
    raw = subprocess.check_output(
        cmd, input=json.dumps(data) if data is not None else None, text=True, env=env, timeout=60
    )
    value = json.loads(raw) if raw else None
    return [row for page in value for row in page] if paginate else value


def valid_sha(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{40}', value):
        raise ValueError('Invalid commit identity')
    return value


def bot(user):
    return (user or {}).get('id') == BOT and user.get('login') == 'github-actions[bot]'


def marker(head):
    rows = api(f'commits/{valid_sha(head)}/statuses?per_page=100', paginate=True)
    for row in rows:  # GitHub returns immutable statuses newest first.
        if row['context'] != CONTEXT or not bot(row.get('creator')):
            continue
        match = STATUS_MARK.fullmatch(row.get('description') or '')
        if not match or row['state'] != 'success':
            raise ValueError('Malformed hosted repair record')
        root, count, origin, pr, actor = map(int, match.groups())
        if root <= 0 or row['target_url'] != f'{WEB}/actions/runs/{root}':
            raise ValueError('Invalid hosted repair origin')
        return dict(root=root, count=count, origin=origin, pr=pr, actor=actor)
    return None


def mark(head, record):
    value = 'v1 {root} {count} {origin} {pr} {actor}'.format(**record)
    row = api(
        f'statuses/{head}',
        'POST',
        {
            'context': CONTEXT,
            'state': 'success',
            'description': value,
            'target_url': f"{WEB}/actions/runs/{record['root']}",
        },
    )
    if not bot(row.get('creator')) or row.get('description') != value:
        raise ValueError('Repair records require the built-in GitHub Actions token')


def current(run_id, attempt, *, green=False):
    run = api(f'actions/runs/{run_id}')
    if (
        run['id'] != run_id
        or run['run_attempt'] != attempt
        or run['status'] != 'completed'
        or run['conclusion'] not in ({'success'} if green else inbox.BLOCKED)
        or run['path'] != '.github/workflows/' + inbox.WORKFLOW
        or run['repository']['full_name'] != REPO
        or (run.get('head_repository') or {}).get('full_name') != REPO
    ):
        return None
    head, branch, event = valid_sha(run['head_sha']), run['head_branch'], run['event']
    pr = None
    if event == 'push' and branch == 'main':
        if api('branches/main')['commit']['sha'] != head:
            return None
    elif event == 'pull_request':
        numbers = inbox.pr_numbers(run, head, branch)
        if len(numbers) != 1:
            return None
        pr = api(f'pulls/{next(iter(numbers))}')
        if (
            pr['state'] != 'open'
            or pr['head']['sha'] != head
            or pr['head']['ref'] != branch
            or pr['base']['ref'] != 'main'
            or pr['base']['repo']['full_name'] != REPO
            or (pr['head']['repo'] or {}).get('full_name') != REPO
            or branch == 'main'
        ):
            return None
    else:
        return None
    if green:
        args = urlencode(dict(head_sha=head, event=event, branch=branch, per_page=100))
        runs = api(f'actions/workflows/{inbox.WORKFLOW}/runs?{args}')['workflow_runs']
        newest = next(
            (
                r
                for r in runs
                if r['head_sha'] == head
                and r['event'] == event
                and (r.get('head_repository') or {}).get('full_name') == REPO
                and (not pr or inbox.pr_numbers(r, head, branch) == {pr['number']})
            ),
            None,
        )
        if not newest or (newest['id'], newest['run_attempt']) != (run_id, attempt):
            return None
        jobs = api(f'actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100')['jobs']
        if [j['conclusion'] for j in jobs if j['name'] == 'Disco integration verdict'] != ['success']:
            return None
    else:
        incident = inbox.incident(branch, head, event, pr['number'] if pr else None)
        if not incident or (incident['run_id'], incident['attempt']) != (run_id, attempt):
            return None
    m = marker(head)
    if pr and branch.startswith(PREFIX):
        if not (
            m
            and m['origin'] == 0
            and m['pr'] == pr['number']
            and m['actor'] == pr['user']['id']
            and branch == PREFIX + str(m['root'])
        ):
            return None  # Human-modified or unrelated lookalike; never auto-merge.
        main = api('branches/main')['commit']['sha']
        root_failure = inbox.incident('main', main, 'push')
        if not root_failure or root_failure['run_id'] != m['root']:
            return None  # The original failure already recovered or main advanced.
    elif pr and pr['user']['login'].casefold() != OWNER.casefold():
        return None
    elif (
        not pr
        or not m
        or (m['origin'], m['pr'], m['actor']) != (pr['number'], pr['number'], pr['user']['id'])
    ):
        m = None  # A human commit, or evidence from a different branch.
    number = pr['number'] if pr else 0
    return {
        'run_id': run_id,
        'attempt': attempt,
        'head_sha': head,
        'branch': branch,
        'pr': number or None,
        'root': m['root'] if m else run_id,
        'count': m['count'] if m else 0,
        'origin': m['origin'] if m else number,
        'actor': pr['user']['id'] if pr else 0,
    }


def issues():
    query = urlencode(dict(state='all', creator='github-actions[bot]', per_page=100))
    rows = api('issues?' + query, paginate=True)
    result = []
    for row in rows:
        match = ISSUE_MARK.fullmatch((row.get('body') or '\n').split('\n')[0])
        if not row.get('pull_request') and bot(row.get('user')) and match:
            root, target, failed = match.groups()
            result.append((int(root), int(target), failed, row))
    return result


def plan(run_id, attempt):
    ctx = current(run_id, attempt)
    if not ctx:
        return {'action': 'stale'}
    if any(root == ctx['root'] and target == ctx['origin'] for root, target, _, _ in issues()):
        return dict(ctx, action='stale')  # This incident was already handed off.
    if not ctx['pr']:
        ref = 'refs/heads/' + PREFIX + str(ctx['root'])
        if any(r['ref'] == ref for r in api('git/matching-refs/heads/' + PREFIX + str(ctx['root']))):
            prs = api(
                'pulls?'
                + urlencode(dict(state='open', base='main', head=OWNER + ':' + PREFIX + str(ctx['root'])))
            )
            for pr in prs:
                prior = marker(pr['head']['sha'])
                if (
                    prior
                    and prior['root'] == ctx['root']
                    and prior['origin'] == 0
                    and prior['pr'] == pr['number']
                    and prior['actor'] == pr['user']['id']
                    and pr['head']['repo']['full_name'] == REPO
                ):
                    return dict(ctx, action='stale')  # The existing repair already owns this incident.
            return dict(ctx, action='exhausted')
    return dict(ctx, action='exhausted' if ctx['count'] >= LIMIT else 'generate')


def safe_changes(path, old, new):
    if path.endswith('.py'):
        # Preserve every external call and its arguments, even when an operation
        # is reached through a project-specific name that a word list misses.
        pure = {
            'len',
            'str',
            'int',
            'bool',
            'isinstance',
            'sorted',
            'list',
            'dict',
            'set',
            'tuple',
            'min',
            'max',
            'enumerate',
            'range',
            'get',
            'strip',
            'startswith',
            'endswith',
            'jsonify',
        }

        def effects(source):
            calls = []
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    calls.append(ast.dump(node))
                if isinstance(node, ast.Call):
                    callee = node.func
                    name = callee.id if isinstance(callee, ast.Name) else getattr(callee, 'attr', None)
                    if name not in pure:
                        calls.append(ast.dump(node))
            return Counter(calls)

        if effects(old) != effects(new):
            raise ValueError('Python repair changes external operations or imports')
    if path == 'desktop/main.cjs':
        bounds = ('async function startScientificUI() {', '\nfunction registerIPC() {')

        def regions(text):
            if any(text.count(x) != 1 for x in bounds):
                raise ValueError('Unrecognized startup composition boundary')
            before, body = text.split(bounds[0])
            body, after = body.split(bounds[1])
            return before, body, after

        left, right = regions(old), regions(new)
        if (left[0], left[2]) != (right[0], right[2]):
            raise ValueError('Desktop main changes must stay inside startup composition')
        old, new = left[1], right[1]
    lines = [
        line[2:]
        for line in difflib.ndiff(old.splitlines(), new.splitlines())
        if line.startswith(('+ ', '- '))
    ]
    secret = re.compile(
        r'-----BEGIN [A-Z ]*PRIVATE KEY|github_pat_|gh[pousr]_[A-Za-z0-9]{15,}|sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|[A-Za-z0-9_+/=-]{60,}'
    )
    if not lines or any(SENSITIVE.search(line) or secret.search(line) for line in lines):
        raise ValueError('Patch touches a protected boundary or is ambiguous')


def apply_patch(patchfile, base):
    """Apply only to a private Git index populated with verified existing blobs."""
    info = patchfile.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= PATCH_LIMIT:
        raise ValueError('Expected one bounded regular patch')
    patch = patchfile.read_bytes()
    patch.decode('utf-8')
    if b'\0' in patch or b'GIT binary patch' in patch:
        raise ValueError('Expected a text patch')
    with tempfile.TemporaryDirectory(prefix='disco-repair-index-') as tmp:
        env = {
            'PATH': os.defpath,
            'HOME': tmp,
            'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_ATTR_NOSYSTEM': '1',
            'LC_ALL': 'C',
        }

        def git(*args, data=None):
            return subprocess.check_output(
                [
                    'git',
                    '-c',
                    'core.hooksPath=' + os.devnull,
                    '-c',
                    'core.attributesFile=' + os.devnull,
                    *args,
                ],
                cwd=tmp,
                env=env,
                input=data,
                stderr=subprocess.PIPE,
                timeout=30,
            )

        git('init', '-q', '--bare')
        items = git('apply', '--numstat', '-z', '-', data=patch).split(b'\0')
        if items[-1] or not 1 <= len(items) - 1 <= 3:
            raise ValueError('Expected changes to one to three existing files')
        before = {}
        total = 0
        for item in items[:-1]:
            added, removed, name = item.decode().split('\t')
            if not added.isdecimal() or not removed.isdecimal() or name not in ALLOWED or name in before:
                raise ValueError('File is outside the automatic production repair scope')
            total += int(added) + int(removed)
            if total > 160:
                raise ValueError('Patch exceeds the automatic review scope')
            file = api('contents/' + name + '?ref=' + valid_sha(base))
            if (
                file.get('type') != 'file'
                or file['path'] != name
                or file['encoding'] != 'base64'
                or not 0 < file['size'] <= FILE_LIMIT
            ):
                raise ValueError('Expected an existing regular text file')
            # Contents API follows symlinks. The Git tree establishes actual mode and OID.
            entry = git_entry(base, name)
            raw = base64.b64decode(file['content'])
            oid = git('hash-object', '-w', '--stdin', data=raw).decode().strip()
            if len(raw) != file['size'] or oid != entry or oid != file['sha']:
                raise ValueError('Source blob does not match the original Git tree')
            git('update-index', '--add', '--cacheinfo', '100644', oid, name)
            before[name] = raw.decode('utf-8')
        git('apply', '--cached', '--check', '--whitespace=error', '-', data=patch)
        git('apply', '--cached', '--whitespace=error', '-', data=patch)
        result = {}
        for record in git('ls-files', '--stage', '-z').split(b'\0')[:-1]:
            meta, name = record.decode().split('\t')
            mode, oid, stage = meta.split()
            if name not in before or mode != '100644' or stage != '0':
                raise ValueError('Renames, new files and mode changes require human review')
            raw = git('cat-file', 'blob', valid_sha(oid))
            if not raw or len(raw) > FILE_LIMIT or b'\0' in raw:
                raise ValueError('Refusing binary, oversized or empty output')
            updated = raw.decode('utf-8')
            safe_changes(name, before[name], updated)
            result[name] = updated
        if set(result) != set(before):
            raise ValueError('Deletion requires human review')
        return result


def git_entry(commit, path):
    tree = api('git/commits/' + valid_sha(commit))['tree']['sha']
    parts = path.split('/')
    for i, part in enumerate(parts):
        listing = api('git/trees/' + valid_sha(tree))
        matches = [row for row in listing['tree'] if row['path'] == part]
        if listing.get('truncated') or len(matches) != 1:
            raise ValueError('Missing or ambiguous tree entry')
        row = matches[0]
        expected = ('blob', '100644') if i == len(parts) - 1 else ('tree', '040000')
        if (row['type'], row['mode']) != expected:
            raise ValueError('Automatic repair only permits existing regular files')
        tree = row['sha']
    return valid_sha(tree)


def move(branch, before, after):
    if branch in ('main', 'master') or branch.startswith('disco-release-pages-ci/'):
        raise ValueError('Direct updates to protected branches are prohibited')
    update = {'name': 'refs/heads/' + branch, 'beforeOid': before, 'afterOid': after, 'force': False}
    query = 'mutation($input:UpdateRefsInput!){updateRefs(input:$input){clientMutationId}}'
    value = api(
        'graphql',
        'POST',
        {
            'query': query,
            'variables': {'input': {'repositoryId': api('')['node_id'], 'refUpdates': [update]}},
        },
        publisher=True,
    )
    if value.get('errors') or not value.get('data', {}).get('updateRefs'):
        raise ValueError('Atomic branch update refused')


def fetch_patch(run_id, attempt, destination):
    if (str(run_id), str(attempt)) != (os.environ.get('GITHUB_RUN_ID'), os.environ.get('GITHUB_RUN_ATTEMPT')):
        raise ValueError('Patch must come from this repair workflow and attempt')
    name = f'disco-repair-patch-{run_id}-{attempt}'
    response = api(f'actions/runs/{run_id}/artifacts?name={name}&per_page=100')
    rows = [row for row in response['artifacts'] if row['name'] == name and not row['expired']]
    if len(rows) != 1 or not re.fullmatch(r'sha256:[0-9a-f]{64}', rows[0].get('digest') or ''):
        raise ValueError('Missing or ambiguous current patch artifact')
    with tempfile.TemporaryDirectory(prefix='disco-patch-archive-') as tmp:
        archive = Path(tmp) / 'proposal.zip'
        _download_archive(REPO, rows[0], archive, 1024 * 1024 + 4096)
        with zipfile.ZipFile(archive) as z:
            items = z.infolist()
            if len(items) != 1:
                raise ValueError('Expected exactly one patch file')
            item = items[0]
            mode = stat.S_IFMT(item.external_attr >> 16)
            if (
                item.filename != 'codex.patch'
                or mode not in (0, stat.S_IFREG)
                or item.is_dir()
                or item.flag_bits & 1
                or not 0 < item.file_size <= PATCH_LIMIT
            ):
                raise ValueError('Invalid patch member or size')
            with z.open(item) as stream:
                patch = stream.read(PATCH_LIMIT + 1)
            if len(patch) != item.file_size:
                raise ValueError('Patch bytes differ from the member declaration')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as output:
        output.write(patch)
    return {'action': 'fetched', 'bytes': len(patch)}


def publish(run_id, attempt, patch):
    ctx = plan(run_id, attempt)
    if ctx['action'] == 'stale':
        return ctx
    if ctx['action'] != 'generate':
        raise ValueError('Repair budget exhausted')
    head = ctx['head_sha']
    changes = apply_patch(patch, head)
    if current(run_id, attempt) != {k: v for k, v in ctx.items() if k != 'action'}:
        return {'action': 'stale'}
    original = api('git/commits/' + head)
    tree = api(
        'git/trees',
        'POST',
        {
            'base_tree': original['tree']['sha'],
            'tree': [
                {'path': k, 'content': v, 'mode': '100644', 'type': 'blob'}
                for k, v in sorted(changes.items())
            ],
        },
        publisher=True,
    )
    candidate = api(
        'git/commits',
        'POST',
        {
            'message': f'Disco: repair integration run {run_id}',
            'tree': valid_sha(tree['sha']),
            'parents': [head],
        },
        publisher=True,
    )
    sha = valid_sha(candidate['sha'])
    if candidate['tree']['sha'] != tree['sha'] or [x['sha'] for x in candidate['parents']] != [head]:
        raise ValueError('Generated commit identity differs')
    number = ctx['pr'] or 0
    state = {
        'root': ctx['root'],
        'count': ctx['count'] + 1,
        'origin': ctx['origin'],
        'pr': number,
        'actor': ctx['actor'],
    }
    mark(sha, state)
    branch = ctx['branch'] if number else PREFIX + str(ctx['root'])
    move(branch, head if number else ZERO, sha)
    if not number:
        pr = api(
            'pulls',
            'POST',
            {
                'head': branch,
                'base': 'main',
                'title': f"Repair Disco integration run {ctx['root']}",
                'body': f"Automated repair for [the failing main integration]({WEB}/actions/runs/{ctx['root']}).",
            },
            publisher=True,
        )
        if pr['head']['sha'] != sha or pr['head']['ref'] != branch or pr['base']['ref'] != 'main':
            raise ValueError('Created repair PR differs from the generated commit')
        number = pr['number']
        mark(sha, dict(state, pr=number, actor=pr['user']['id']))
    return {
        'action': 'published',
        'commit': sha,
        'pr': number,
        'root': state['root'],
        'count': state['count'],
    }


REASONS = {
    'generation': 'No unambiguous in-scope candidate was produced.',
    'publication': 'A guarded repair could not be published.',
    'exhausted': 'The automatic repair budget was exhausted or its branch needs inspection.',
    'credentials': 'The hosted repair credentials need attention.',
    'merge': 'GitHub did not permit the tested repair PR to merge.',
}
NEXT_ACTION = {
    'generation': 'Review the diagnosis in the repair log. Confirm the intended behavior or assign the change to the module owner before trying a different fix.',
    'publication': 'Inspect the publication guard in the repair log. Review a proposed change manually if it crosses a protected boundary.',
    'exhausted': 'Compare the attempted revisions with the failing assertion and decide what should change before starting another repair.',
    'credentials': 'Verify the Disco OpenAI and GitHub repair credentials in repository Actions settings, then run the credential check.',
    'merge': 'Inspect the protected repair PR for a changed base, conflicts, required reviews or missing permissions. Complete the normal review process.',
}


def handoff(ctx, reason):
    for root, target, _, issue in issues():
        if (root, target) == (ctx['root'], ctx['origin']):
            return {'action': 'already_escalated', 'issue': issue['number']}
    failed = ctx['head_sha']
    if not ctx['origin'] and ctx['pr']:
        failed = valid_sha(api(f"actions/runs/{ctx['root']}")['head_sha'])
    identity = f"<!-- disco-repair-v1 root={ctx['root']} target={ctx['origin']} failed={failed} -->"
    attempt_url = f"{WEB}/actions/runs/{ctx['run_id']}/attempts/{ctx['attempt']}"
    jobs = api(f"actions/runs/{ctx['run_id']}/attempts/{ctx['attempt']}/jobs?per_page=100")['jobs']

    def label(value):
        # Treat server-reported job/step names as text. Prevent issue mentions,
        # links and markup from being supplied by a PR's workflow.
        return re.sub(r'[^A-Za-z0-9 /_.()-]', ' ', str(value))[:130].strip()

    failures = []
    affected = []
    for job in jobs:
        if job['conclusion'] in inbox.BLOCKED and type(job['id']) is int:
            step = next((s for s in job.get('steps', []) if s.get('conclusion') in inbox.BLOCKED), None)
            failed = label(job['name']) + (' — ' + label(step['name']) if step else '')
            failures.append(f"- [{failed}]({WEB}/actions/runs/{ctx['run_id']}/job/{job['id']})")
            if job['name'] != 'Disco integration verdict':
                affected.append(failed)
    body = (
        f"{identity}\n\n{REASONS[reason]}\n\n{NEXT_ACTION[reason]}\n\n"
        f"[Original integration run]({attempt_url}) · revision `{ctx['head_sha']}` · "
        f"{ctx['count']} published repair attempt(s)."
    )
    if failures:
        body += '\n\nAffected workflow checks:\n\n' + '\n'.join(failures[:6])
    repair_run = os.environ.get('GITHUB_RUN_ID', '')
    if repair_run.isdecimal():
        body += f'\n\n[Hosted repair diagnosis and publication details]({WEB}/actions/runs/{repair_run}).'
    workflow = 'Disco integration'
    if affected:
        workflow = affected[0][:75]
        text = workflow.lower()
        for keyword, title in [
            ('startup', 'installed startup and Quit'),
            ('native /', 'installed startup and Quit'),
            ('install', 'source installation'),
            ('trace', 'trace performance'),
            ('browser million', 'browser workflow performance'),
            ('backend million', 'million-row metadata queries'),
            ('regression', 'source regression'),
        ]:
            if keyword in text:
                workflow = title
                break
    if reason == 'credentials':
        workflow = 'hosted repair credentials'
    if reason == 'merge':
        workflow = 'merge the tested repair'
    issue = api(
        'issues', 'POST', {'title': f"[Disco] Action needed — {workflow}", 'body': body, 'assignees': [OWNER]}
    )
    if not bot(issue.get('user')) or OWNER.casefold() not in {
        a['login'].casefold() for a in issue.get('assignees', [])
    }:
        raise ValueError('GitHub did not confirm bot issue ownership and owner assignment')
    return {'action': 'escalated', 'issue': issue['number']}


def reconcile(run_id, attempt):
    ctx = current(run_id, attempt, green=True)
    if not ctx:
        return {'action': 'stale'}
    if ctx['branch'].startswith(PREFIX):
        # A bot record binds this exact tip, the PR number and the PR creator.
        # Also require the tested integration merge to have the *current* base.
        run = api(f'actions/runs/{run_id}')
        root = api(f"actions/runs/{ctx['root']}")
        main = api('branches/main')['commit']['sha']
        if root['event'] != 'push' or root['head_branch'] != 'main' or root['head_sha'] != main:
            return {'action': 'stale'}
        tested = set()
        for name in ('workspace-ci.yml', 'everyday-million.yml'):
            entries = [
                row
                for row in run.get('referenced_workflows', [])
                if row['path'].split('@')[0] == f'{REPO}/.github/workflows/{name}'
            ]
            if len(entries) != 1 or entries[0].get('ref') != f"refs/pull/{ctx['pr']}/merge":
                return handoff(ctx, 'merge')
            tested.add(valid_sha(entries[0]['sha']))
        if len(tested) != 1 or [p['sha'] for p in api('git/commits/' + tested.pop())['parents']] != [
            main,
            ctx['head_sha'],
        ]:
            return handoff(ctx, 'merge')
        if current(run_id, attempt, green=True) != ctx:
            return {'action': 'stale'}
        try:
            merged = api(
                f"pulls/{ctx['pr']}/merge",
                'PUT',
                {'sha': ctx['head_sha'], 'merge_method': 'merge'},
                publisher=True,
            )
        except (ValueError, subprocess.SubprocessError):
            return handoff(ctx, 'merge')
        if merged.get('merged') is not True:
            return handoff(ctx, 'merge')
        return {'action': 'merged', 'pr': ctx['pr'], 'commit': merged['sha']}
    target = ctx['pr'] or 0
    closed = []
    for _, origin, failed, issue in issues():
        if issue['state'] != 'open':
            continue
        if origin != target:
            if target or not origin:
                continue
            # The PR may have merged between its green run and this workflow.
            # Only its own merged PR and verifiable history can resolve it here.
            pr = api(f'pulls/{origin}')
            if (
                pr['number'] != origin
                or pr['state'] != 'closed'
                or not pr['merged_at']
                or pr['base']['ref'] != 'main'
                or pr['base']['repo']['full_name'] != REPO
                or (pr['head']['repo'] or {}).get('full_name') != REPO
            ):
                continue
            merge = valid_sha(pr['merge_commit_sha'])
            pr_head = valid_sha(pr['head']['sha'])
            if api(f"compare/{merge}...{ctx['head_sha']}")['status'] not in ('ahead', 'identical') or api(
                f"compare/{failed}...{pr_head}"
            )['status'] not in ('ahead', 'identical'):
                continue
        comparison = api(f"compare/{failed}...{ctx['head_sha']}")
        if comparison['status'] in ('ahead', 'identical') and current(run_id, attempt, green=True) == ctx:
            api(f"issues/{issue['number']}", 'PATCH', {'state': 'closed', 'state_reason': 'completed'})
            closed.append(issue['number'])
    return {'action': 'resolved', 'issues': closed}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['plan', 'fetch', 'publish', 'escalate', 'reconcile'])
    p.add_argument('--run-id', type=int, required=True)
    p.add_argument('--attempt', type=int, required=True)
    p.add_argument('--reason', choices=sorted(REASONS))
    p.add_argument('--patch', type=Path)
    args = p.parse_args()
    if args.run_id <= 0 or args.attempt <= 0:
        p.error('Expected positive run ID and attempt')
    if args.action == 'plan':
        result = plan(args.run_id, args.attempt)
    elif args.action in ('publish', 'fetch'):
        if not args.patch:
            p.error('Missing patch path')
        operation = publish if args.action == 'publish' else fetch_patch
        result = operation(args.run_id, args.attempt, args.patch)
    elif args.action == 'reconcile':
        result = reconcile(args.run_id, args.attempt)
    else:
        if not args.reason:
            p.error('Missing escalation reason')
        ctx = current(args.run_id, args.attempt)
        result = handoff(ctx, args.reason) if ctx else {'action': 'stale'}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
