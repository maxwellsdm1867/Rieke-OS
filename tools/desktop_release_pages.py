#!/usr/bin/env python3
"""Synchronize public testing-release navigation; never publish or qualify an app."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

REPOSITORY = 'maxwellsdm1867/Rieke-OS'
WEB = f'https://github.com/{REPOSITORY}'
TAG = re.compile(r'desktop-test-v((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))')
SHA = re.compile(r'[0-9a-f]{40}')


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
    if not match or release.get('draft') or release.get('prerelease') is not True:
        raise ValueError('Expected a published testing prerelease')
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
              'Unsigned, unnotarized Apple silicon testing prerelease; not production-qualified. '
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
             'Unsigned, unnotarized Apple silicon testing prerelease.\n\n'
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
             'Unsigned, unnotarized Apple silicon testing prerelease; not production-qualified.')
    notes = release['notes']
    if '<!-- disco:release-links:start -->' in notes:
        notes = replace_block(notes, 'release-links', links)
    else:
        notes = notes.rstrip() + '\n\n' + block('release-links', links) + '\n'
    return {'README.md': readme, 'CHANGELOG.md': changelog}, notes


class GitHub:
    def request(self, endpoint, method='GET', data=None, paginate=False):
        args = ['gh', 'api', endpoint, '--method', method]
        if paginate:
            args += ['--paginate', '--slurp']
        if data is not None:
            args += ['--input', '-']
        value = json.loads(subprocess.check_output(args, input=None if data is None else json.dumps(data), text=True))
        return [item for page in value for item in page] if paginate else value

    def releases(self):
        return self.request(f'repos/{REPOSITORY}/releases?per_page=100', paginate=True)

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


def sync(github, apply=False):
    selected = newest(github.releases())
    release = validate(selected, github.descriptor(selected['tag_name']), github.tag_commit(selected['tag_name']))
    repo = github.request(f'repos/{REPOSITORY}')
    branch = repo['default_branch']
    ref = f'repos/{REPOSITORY}/git/refs/heads/{branch}'
    head = github.request(f'repos/{REPOSITORY}/git/ref/heads/{branch}')['object']['sha']
    before = {p: github.file(p, head) for p in ('README.md', 'CHANGELOG.md')}
    files, notes = render(before['README.md'], before['CHANGELOG.md'], release)
    changed = {p: text for p, text in files.items() if text != before[p]}
    result = {'tag': release['tag'], 'source_commit': release['source'], 'branch': branch,
              'base_commit': head, 'changed_files': list(changed),
              'release_notes_changed': notes != selected['body'], 'applied': False}
    if not apply or (not changed and notes == selected['body']):
        return result
    # Re-read after planning; an old event must never move pages back a version.
    fresh = newest(github.releases())
    if (fresh['id'], fresh['updated_at']) != (selected['id'], selected['updated_at']):
        raise ValueError('Published release changed during planning; rerun the hook')
    if github.tag_commit(selected['tag_name']) != release['source']:
        raise ValueError('Release tag changed during planning')
    if github.request(f'repos/{REPOSITORY}/git/ref/heads/{branch}')['object']['sha'] != head:
        raise ValueError('Default branch changed during planning; rerun the hook')
    if changed:
        tree = github.request(f'repos/{REPOSITORY}/git/commits/{head}')['tree']['sha']
        created = github.request(f'repos/{REPOSITORY}/git/trees', 'POST', {
            'base_tree': tree, 'tree': [{'path': p, 'mode': '100644', 'type': 'blob', 'content': text}
                                      for p, text in changed.items()]})
        commit = github.request(f'repos/{REPOSITORY}/git/commits', 'POST', {
            'message': f'docs: synchronize Disco {release["version"]} release pages',
            'tree': created['sha'], 'parents': [head]})
        # Non-fast-forward rejection preserves concurrent changes. A failed run is
        # visible in Actions and can be rerun; it never force-pushes or moves tags.
        latest = newest(github.releases())
        if (latest['id'], latest['updated_at']) != (selected['id'], selected['updated_at']):
            raise ValueError('Published release changed before documentation update; rerun')
        github.request(ref, 'PATCH', {'sha': commit['sha'], 'force': False})
        result['documentation_commit'] = commit['sha']
    if notes != selected['body']:
        current = github.request(f'repos/{REPOSITORY}/releases/{selected["id"]}')
        if current['updated_at'] != selected['updated_at'] or current['body'] != selected['body']:
            raise ValueError('Release notes changed concurrently; rerun to preserve the edit')
        github.request(f'repos/{REPOSITORY}/releases/{selected["id"]}', 'PATCH', {'body': notes})
    result['applied'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Update only README, changelog and release-body presentation')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = sync(GitHub(), apply=args.apply)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
