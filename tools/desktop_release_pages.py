#!/usr/bin/env python3
"""Synchronize public testing-release navigation; never publish or qualify an app."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import quote

REPOSITORY = 'maxwellsdm1867/Rieke-OS'
WEB = f'https://github.com/{REPOSITORY}'
TAG = re.compile(r'desktop-test-v((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))')
SHA = re.compile(r'[0-9a-f]{40}')
INTEGRATION = '.github/workflows/integration.yml'
VERDICT = 'Disco integration verdict'


def block(name, content):
    return f'<!-- disco:{name}:start -->\n{content.strip()}\n<!-- disco:{name}:end -->'


def replace_block(text, name, content):
    start, end = f'<!-- disco:{name}:start -->', f'<!-- disco:{name}:end -->'
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) >= text.index(end):
        raise ValueError(f'Missing or ambiguous managed block: {name}')
    before, rest = text.split(start)
    _, after = rest.split(end)
    return before + block(name, content) + after


def newest(releases):
    eligible = [r for r in releases if not r.get('draft') and r.get('published_at')
                and TAG.fullmatch(r.get('tag_name', ''))]
    if not eligible:
        raise ValueError('No published desktop testing release')
    return max(eligible, key=lambda r: tuple(map(int, TAG.fullmatch(r['tag_name'])[1].split('.'))))


def release_notes(body):
    """Use reviewed bullets; never infer changes from commits or invent results."""
    heading = re.search(r"(?mi)^## What's new\s*$", body.replace('’', "'"))
    if heading:
        section = re.split(r'(?m)^## ', body[heading.end():], maxsplit=1)[0]
        normalized = body
    else:
        # Existing release notes used the first feature list without a heading.
        first = re.search(r'(?m)^- ', body)
        if not first:
            raise ValueError("Release notes need a What's new bullet list")
        normalized = body[:first.start()] + "## What's new\n\n" + body[first.start():]
        section = re.split(r'(?m)^## ', body[first.start():], maxsplit=1)[0]
    lines, started = [], False
    for line in section.splitlines():
        if line.startswith('- '):
            lines.append(line); started = True
        elif started and line.startswith(('  ', '\t')) and line.strip():
            lines.append(line)
        elif started and not line.strip():
            continue
        elif started:
            break
        elif line.strip():
            raise ValueError("What's new must start with reviewed bullets")
    if not lines:
        raise ValueError("Release notes need a What's new bullet list")
    return '\n'.join(lines), normalized


def validate(release, raw_descriptor, tag_commit):
    match = TAG.fullmatch(release.get('tag_name', ''))
    if not match or release.get('draft') is not False or type(release.get('prerelease')) is not bool:
        raise ValueError('Expected a published desktop testing release')
    version = match[1]
    date = datetime.fromisoformat(release['published_at'].replace('Z', '+00:00')).date().isoformat()
    d = json.loads(raw_descriptor)
    expected = {'format': 'rieke-desktop-test-release', 'version': 1,
                'application_version': version, 'repository': REPOSITORY,
                'canonical_repository': REPOSITORY, 'channel': 'unsigned-testing',
                'platform': 'darwin', 'architecture': 'arm64',
                'source_dirty': False, 'production_ready': False}
    if any(type(d.get(k)) is not type(v) or d.get(k) != v for k, v in expected.items()):
        raise ValueError('Published descriptor identity or testing channel differs')
    source = d.get('source_commit', '')
    if not SHA.fullmatch(source) or source != tag_commit:
        raise ValueError('Published source and immutable tag differ')
    assets = release.get('assets', [])
    by_name = {a['name']: a for a in assets}
    if len(by_name) != len(assets):
        raise ValueError('Duplicate release assets')
    archive = d.get('archive', {})
    filename = f'Disco-{version}-arm64.zip'
    if archive.get('filename') != filename or not re.fullmatch(r'[0-9a-f]{64}', archive.get('sha256', '')):
        raise ValueError('Archive identity differs from release version')
    for name, digest, size in [
        ('desktop-release.json', hashlib.sha256(raw_descriptor).hexdigest(), len(raw_descriptor)),
        (filename, archive['sha256'], archive.get('size')),
    ]:
        a = by_name.get(name, {})
        if (type(size) is not int or size <= 0 or a.get('state') != 'uploaded'
                or a.get('size') != size or a.get('digest') != 'sha256:' + digest
                or a.get('browser_download_url') != f'{WEB}/releases/download/{release["tag_name"]}/{name}'):
            raise ValueError(f'Published asset metadata differs: {name}')
    if by_name.get('SHA256SUMS', {}).get('state') != 'uploaded':
        raise ValueError('Published checksum asset missing')
    summary, notes = release_notes(release.get('body') or '')
    return {'version': version, 'date': date, 'source': source, 'tag': release['tag_name'],
            'url': f'{WEB}/releases/tag/{release["tag_name"]}',
            'download': f'{WEB}/releases/download/{release["tag_name"]}/{filename}',
            'summary': summary, 'notes': notes}


def render(readme, changelog, release):
    v, url, source = release['version'], release['url'], release['source']
    download = f"[Download the Apple silicon ZIP]({release['download']})"
    tag_link = f"[Source tag: {release['tag']}]({WEB}/tree/{release['tag']})"
    banner = (f'> **DISCO {v} · Mac desktop testing build:** {download} · '
              f'[Release details and checksums]({url}) · [What\'s new](CHANGELOG.md). '
              'Existing users: **App Updates → Download update → Restart to update**. '
              'For manual installation, extract the ZIP and open **Disco.app**. '
              'Python and native MySQL are bundled; no Docker or Terminal setup is needed. '
              'Unsigned, unnotarized Apple silicon testing build; not production-qualified. '
              'Targets macOS 14+, with macOS 14 runtime support unqualified and Intel unsupported. '
              'macOS may require **Privacy & Security → Open Anyway**.')
    current = (f'### DISCO {v}\n\n{download} · [Release notes and checksums]({url})\n\n'
               f"#### What's new\n\n{release['summary']}\n\n"
               f'{tag_link} identifies packaged source [`{source[:7]}`]({WEB}/commit/{source}). '
               'Later documentation commits do not change the published app. '
               'See the release notes for verification results and limitations.')
    readme = replace_block(readme, 'release-banner', banner)
    readme = replace_block(readme, 'current-release', current)
    entry = (f"## {v} - {release['date']}\n\n"
             f'[Download and release details]({url}) · {tag_link}\n\n'
             'Unsigned, unnotarized Apple silicon testing build.\n\n'
             f"### What's new\n\n{release['summary']}\n\n"
             f'Packaged source: [`{source[:7]}`]({WEB}/commit/{source}). '
             'See the release notes for qualification evidence and testing limits.')
    marker = f'changelog-{v}'
    if f'<!-- disco:{marker}:start -->' in changelog:
        changelog = replace_block(changelog, marker, entry)
    elif re.search(rf'(?m)^## {re.escape(v)}(?:\s|$)', changelog):
        raise ValueError('Current changelog entry is not managed; preserve it for review')
    else:
        anchor = '<!-- disco:changelog-insert -->'
        if changelog.count(anchor) != 1:
            raise ValueError('Missing or ambiguous changelog insertion marker')
        changelog = changelog.replace(anchor, anchor + '\n\n' + block(marker, entry), 1)
    links = (f'## Download and source\n\n{download} · [Checksums and metadata]({url})\n\n'
             'Existing users: **App Updates → Download update → Restart to update**.\n\n'
             f'{tag_link} · Packaged source [`{source[:7]}`]({WEB}/commit/{source}).\n\n'
             'Unsigned, unnotarized Apple silicon testing build; not production-qualified.')
    notes = release['notes']
    if '<!-- disco:release-links:start -->' in notes:
        notes = replace_block(notes, 'release-links', links)
    else:
        notes = notes.rstrip() + '\n\n' + block('release-links', links) + '\n'
    return {'README.md': readme, 'CHANGELOG.md': changelog}, notes


class GitHub:
    def request(self, endpoint, method='GET', data=None, paginate=False, *, api_version=None):
        args = ['gh', 'api', endpoint, '--method', method]
        if api_version:
            args += ['-H', 'X-GitHub-Api-Version: ' + api_version]
        if paginate:
            args += ['--paginate', '--slurp']
        if data is not None:
            args += ['--input', '-']
        value = json.loads(subprocess.check_output(args, input=None if data is None else json.dumps(data),
                                                   text=True, timeout=60))
        return [item for page in value for item in page] if paginate else value

    def releases(self):
        return self.request(f'repos/{REPOSITORY}/releases?per_page=100', paginate=True)

    def latest(self):
        owner, name = REPOSITORY.split('/')
        query = ('query($owner:String!,$name:String!) { repository(owner:$owner,name:$name) '
                 '{ latestRelease { databaseId tagName publishedAt } } }')
        result = self.request('graphql', 'POST', {'query': query, 'variables': {'owner': owner, 'name': name}})
        return result['data']['repository']['latestRelease']

    def descriptor(self, tag):
        return subprocess.check_output(['gh', 'release', 'download', tag, '--repo', REPOSITORY,
                                        '--pattern', 'desktop-release.json', '--output', '-'])

    def tag_commit(self, tag):
        obj = self.request(f'repos/{REPOSITORY}/git/ref/tags/{tag}')['object']
        for _ in range(5):
            if obj['type'] == 'commit':
                return obj['sha']
            if obj['type'] != 'tag':
                break
            obj = self.request(f'repos/{REPOSITORY}/git/tags/{obj["sha"]}')['object']
        raise ValueError('Tag does not resolve to a commit')

    def file(self, path, ref):
        value = self.request(f'repos/{REPOSITORY}/contents/{path}?ref={quote(ref, safe="")}')
        if value.get('type') != 'file' or value.get('encoding') != 'base64' or value.get('size', 0) > 1_000_000:
            raise ValueError('Unexpected documentation file')
        return base64.b64decode(value['content']).decode('utf-8')

    def remove_staging(self, commit):
        # A leased delete is atomic even if the ref moved after we last read it.
        # Clearing credential helpers limits authentication to the configured gh identity.
        ref = 'refs/heads/' + staging_branch(commit)
        subprocess.run(['git', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential',
                        'push', f'--force-with-lease={ref}:{commit}', WEB + '.git', ':' + ref],
                       cwd=Path(__file__).resolve().parents[1], check=True, timeout=60)


def staging_branch(commit):
    if not SHA.fullmatch(commit):
        raise ValueError('Invalid generated documentation commit')
    return 'disco-release-pages-ci/' + commit


def integration_proof(github, commit, base, *, timeout=900):
    branch = staging_branch(commit)
    api = f'repos/{REPOSITORY}/actions'
    # The dated API returns the ID for this dispatch, avoiding a lookup that
    # could mistake another invocation on the same ref for our requested run.
    dispatch = github.request(f'{api}/workflows/integration.yml/dispatches', 'POST',
                              {'ref': branch, 'inputs': {'base_sha': base}}, api_version='2026-03-10')
    run_id = dispatch.get('workflow_run_id')
    if type(run_id) is not int or run_id <= 0:
        raise ValueError('Integration dispatch did not return its run ID')
    logging.info('Checking %s/actions/runs/%s for %s', WEB, run_id, commit)
    endpoint = f'{api}/runs/{run_id}'
    deadline = time.monotonic() + timeout
    read_failures = 0
    while time.monotonic() < deadline:
        try:
            run = github.request(endpoint)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Retry only the read. Dispatch itself must never be repeated.
            read_failures += 1
            if read_failures >= 3:
                raise
            time.sleep(min(5, max(0, deadline - time.monotonic())))
            continue
        read_failures = 0
        if (run.get('id') != run_id or run.get('path') != INTEGRATION or run.get('event') != 'workflow_dispatch'
                or run.get('head_sha') != commit or run.get('head_branch') != branch
                or run.get('repository', {}).get('full_name') != REPOSITORY
                or run.get('head_repository', {}).get('full_name') != REPOSITORY):
            raise ValueError('Integration run does not match the generated commit, staging branch and workflow')
        if run.get('status') == 'completed':
            attempt = run.get('run_attempt')
            if run.get('conclusion') != 'success' or type(attempt) is not int or attempt <= 0:
                raise ValueError(f'Documentation integration did not pass: {run_id}')
            jobs = github.request(f'{endpoint}/attempts/{attempt}/jobs?per_page=100')['jobs']
            verdicts = [job for job in jobs if job.get('name') == VERDICT]
            if (len(verdicts) != 1 or verdicts[0].get('status') != 'completed' or verdicts[0].get('conclusion') != 'success'
                    or verdicts[0].get('head_sha') != commit or verdicts[0].get('run_id') != run_id):
                raise ValueError('Missing successful Disco integration verdict on the generated commit')
            return {'run_id': run_id, 'attempt': attempt, 'commit': commit,
                    'url': f'{WEB}/actions/runs/{run_id}/attempts/{attempt}'}
        time.sleep(min(10, max(0, deadline - time.monotonic())))
    raise TimeoutError(f'Documentation integration {run_id} did not finish within {timeout}s')


def needs_latest(selected, latest):
    if latest is None:
        return True
    if latest['databaseId'] == selected['id']:
        return False
    # A subsequent stable or source publication can deliberately take Latest.
    # An edit or repair run for an older testing release must respect that choice.
    if not TAG.fullmatch(latest['tagName']):
        return (datetime.fromisoformat(selected['published_at'].replace('Z', '+00:00')) >
                datetime.fromisoformat(latest['publishedAt'].replace('Z', '+00:00')))
    return True


def sync(github, apply=False):
    selected = newest(github.releases())
    descriptor = github.descriptor(selected['tag_name'])
    release = validate(selected, descriptor, github.tag_commit(selected['tag_name']))
    repo = github.request(f'repos/{REPOSITORY}')
    branch = repo['default_branch']
    if apply and branch != 'main':
        raise ValueError('Release page updates require main to be the default branch')
    ref = f'repos/{REPOSITORY}/git/refs/heads/{branch}'
    head = github.request(f'repos/{REPOSITORY}/git/ref/heads/{branch}')['object']['sha']
    before = {p: github.file(p, head) for p in ('README.md', 'CHANGELOG.md')}
    files, notes = render(before['README.md'], before['CHANGELOG.md'], release)
    changed = {p: text for p, text in files.items() if text != before[p]}
    latest = github.latest()
    set_latest = needs_latest(selected, latest)
    edits = {}
    if notes != selected['body']:
        edits['body'] = notes
    if set_latest:
        edits.update(prerelease=False, make_latest='true')
        title = selected.get('name') or f"Disco {release['version']}"
        if not re.search(r'\btesting\b', title, re.I):
            edits['name'] = title + ' (testing build)'
    result = {'tag': release['tag'], 'source_commit': release['source'], 'branch': branch,
              'base_commit': head, 'changed_files': list(changed), 'latest_changed': set_latest,
              'release_notes_changed': notes != selected['body'], 'applied': False}
    if not apply or (not changed and not edits):
        return result
    def still_current(expected_head):
        fresh = newest(github.releases())
        if (fresh['id'], fresh['updated_at'], fresh['body']) != (selected['id'], selected['updated_at'], selected['body']):
            raise ValueError('Published release changed; rerun the hook')
        validate(fresh, descriptor, github.tag_commit(selected['tag_name']))
        if github.request(f'repos/{REPOSITORY}/git/ref/heads/{branch}')['object']['sha'] != expected_head:
            raise ValueError('Default branch changed; rerun the hook')

    still_current(head)
    if changed:
        tree = github.request(f'repos/{REPOSITORY}/git/commits/{head}')['tree']['sha']
        created = github.request(f'repos/{REPOSITORY}/git/trees', 'POST', {
            'base_tree': tree, 'tree': [{'path': p, 'mode': '100644', 'type': 'blob', 'content': text}
                                      for p, text in changed.items()]})
        commit = github.request(f'repos/{REPOSITORY}/git/commits', 'POST', {
            'message': f'docs: synchronize Disco {release["version"]} release pages',
            'tree': created['sha'], 'parents': [head]})
        candidate = commit['sha']
        stage = staging_branch(candidate)
        github.request(f'repos/{REPOSITORY}/git/refs', 'POST', {'ref': 'refs/heads/' + stage, 'sha': candidate})
        # Only the process whose create succeeded owns this ref. A collision
        # fails before this try/finally, preserving the existing owner's branch.
        try:
            result['integration'] = integration_proof(github, candidate, head)
            still_current(head)
            if github.request(f'repos/{REPOSITORY}/git/ref/heads/{stage}')['object']['sha'] != candidate:
                raise ValueError('Staging ref changed before documentation update')
            # Rulesets do not evaluate workflow_dispatch job checks. Report the
            # verified verdict as a commit status on the very same docs-only SHA.
            github.request(f'repos/{REPOSITORY}/statuses/{candidate}', 'POST', {
                'state': 'success', 'context': VERDICT, 'target_url': result['integration']['url'],
                'description': 'Verified release-page integration on this exact commit',
            })
            github.request(ref, 'PATCH', {'sha': candidate, 'force': False})
            result['documentation_commit'] = candidate
        finally:
            github.remove_staging(candidate)
    if edits:
        still_current(result.get('documentation_commit', head))
        if github.latest() != latest:
            raise ValueError('Latest release changed concurrently; rerun the hook')
        current = github.request(f'repos/{REPOSITORY}/releases/{selected["id"]}')
        if current['updated_at'] != selected['updated_at'] or current['body'] != selected['body']:
            raise ValueError('Release notes changed concurrently; rerun to preserve the edit')
        github.request(f'repos/{REPOSITORY}/releases/{selected["id"]}', 'PATCH', edits)
        if set_latest and (github.latest() or {}).get('databaseId') != selected['id']:
            raise ValueError('GitHub did not confirm the Latest badge for the selected testing release')
    result['applied'] = True
    return result


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Synchronize release documentation and the testing release’s Latest badge')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = sync(GitHub(), apply=args.apply)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
