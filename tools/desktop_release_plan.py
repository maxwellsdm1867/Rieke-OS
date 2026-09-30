#!/usr/bin/env python3
"""Select desktop builds and qualification from committed local Git changes.

Routine frontend/version changes build with the normal smoke checks. Updater
changes select native update qualification; lifecycle/domain changes select full
UI checks. Packaging inputs also select updater checks because a new runtime can
break the native install helper. An absent comparable release selects everything.
No application, project, permissions or release assets are modified.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import subprocess

FLAGS = ('build_required', 'updater', 'database', 'packaging', 'full_ui')


def git(repo, *arguments):
    result = subprocess.run(['git', '-C', str(repo), *arguments], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'Git revision or ancestry check failed')
    return result.stdout.strip()


def revision(repo, value):
    return git(repo, 'rev-parse', '--verify', '--end-of-options', value + '^{commit}')


def change_kind(path):
    """Paths in the committed application closure, with conservative unknowns."""
    name = Path(path).name
    if (path.startswith(('docs/', '.github/', 'python/tests/', 'desktop/tests/', 'desktop/test/',
                         'desktop/e2e/', 'workspace-app/tests/', 'workspace-app/test/', 'tools/tests/', 'tests/', 'test/'))
            or name.endswith(('.md', '.rst'))
            or path.startswith('workspace-app/src/') and ('.test.' in name or '.spec.' in name)):
        return set()
    if path.startswith('tools/') and (name.endswith(('_e2e.py', '_smoke.py', '_failures.py'))
                                     or 'research' in name or name == 'desktop_release_plan.py'):
        return set()
    if (path.startswith('tools/') or name.endswith(('.lock', '.plist'))
            or path in {'desktop/package.json', 'desktop/package-lock.json',
                        'workspace-app/package.json', 'workspace-app/package-lock.json',
                        'package.json', 'package-lock.json', 'desktop/distribution.json',
                        'desktop/application-profile.json', 'rieke-release.json'}
            or path.startswith('desktop/') and name in {'sign-runtime.cjs', 'seal-testing.cjs'}):
        return {'packaging', 'updater'}
    if path.startswith('workspace-app/'):
        return {'routine'}
    if path.startswith('desktop/'):
        if name in {'bootstrap.cjs', 'recovery-install.cjs'}:
            return {'updater', 'packaging'}
        if name in {'main.cjs', 'supervisor.cjs', 'draft-barrier.cjs', 'draft-store.cjs'}:
            return {'updater', 'full_ui'}
        return {'updater'} if name.endswith(('.cjs', '.js')) else {'packaging', 'updater'}
    if path.startswith('python/'):
        if name == 'workspace_mysql_runtime.py':
            return {'packaging', 'updater', 'database', 'full_ui'}
        if name == 'workspace-mysql-runtime.json':
            return {'packaging', 'updater', 'database'}
        if name == 'workspace_bootstrap.py' or not name.endswith('.py'):
            return {'packaging', 'updater'}
        if name == 'workspace_updates.py':
            return {'updater'}
        if name in {'workspace_desktop.py', 'workspace_desktop_paths.py'}:
            return {'updater', 'database', 'full_ui'}
        return {'database', 'full_ui'}
    # Unknown files can change the shipping closure or its packaging inputs.
    return {'packaging', 'updater'}


VERSION_FILES = {'rieke-release.json', 'python/rieke-release.json', 'desktop/package.json',
                 'desktop/package-lock.json', 'workspace-app/package.json',
                 'workspace-app/package-lock.json', 'package.json', 'package-lock.json'}
SEMVER = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)')


def version_only(repo, path, base, head):
    if path not in VERSION_FILES:
        return False
    try:
        before, after = (json.loads(git(repo, 'show', f'{commit}:{path}')) for commit in (base, head))
        if not all(isinstance(value, dict) and isinstance(value.get('version'), str)
                   and SEMVER.fullmatch(value['version']) for value in (before, after)):
            return False
        versions = before['version'], after['version']
        for value in (before, after):
            value.pop('version')
            if path.endswith('package.json') and isinstance(value.get('scripts'), dict):
                production = {key: command for key, command in value['scripts'].items()
                              if not key.startswith('test')}
                if production:
                    value['scripts'] = production
                else:
                    value.pop('scripts')
            if path.endswith('package-lock.json') and isinstance(value.get('packages', {}).get(''), dict):
                package = value['packages']['']
                if isinstance(package.get('version'), str) and SEMVER.fullmatch(package['version']):
                    package.pop('version')
        return versions[0] != versions[1] and before == after
    except (ValueError, TypeError, AttributeError):
        return False


def test_scripts_only(repo, path, base, head):
    if path not in VERSION_FILES or not path.endswith('package.json'):
        return False
    try:
        before, after = (json.loads(git(repo, 'show', f'{commit}:{path}')) for commit in (base, head))
        if not all(isinstance(value, dict) for value in (before, after)):
            return False
        scripts_before, scripts_after = before.pop('scripts', {}), after.pop('scripts', {})
        if not isinstance(scripts_before, dict) or not isinstance(scripts_after, dict) or before != after:
            return False
        missing = object()
        keys = {key for key in scripts_before.keys() | scripts_after.keys()
                if scripts_before.get(key, missing) != scripts_after.get(key, missing)}
        return bool(keys) and all(key.startswith('test') for key in keys)
    except (ValueError, TypeError, AttributeError):
        return False


def changed_paths(repo, base, head):
    records = git(repo, 'diff', '--name-status', '-z', '--find-renames', base, head).split('\0')
    paths, offset = set(), 0
    while offset < len(records) and records[offset]:
        status = records[offset]
        offset += 1
        count = 2 if status.startswith(('R', 'C')) else 1
        paths.update(records[offset:offset + count])
        offset += count
    return sorted(paths)


TAG_VERSION = re.compile(r'(desktop-test-v|v)((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*))')


def automatic_base(repo, head, published_tags=None):
    exact = []
    for tag in git(repo, 'tag', '--points-at', head).splitlines():
        match = TAG_VERSION.fullmatch(tag)
        if match:
            exact.append((match[1], tuple(map(int, match[2].split('.')))))
    if len(set(exact)) != 1:
        return None
    channel, current = exact[0]
    candidates = []
    for tag in git(repo, 'tag', '--merged', head).splitlines():
        if published_tags is not None and tag not in published_tags:
            continue
        match = TAG_VERSION.fullmatch(tag)
        if not match or match[1] != channel:
            continue
        value = tuple(map(int, match[2].split('.')))
        if value < current and revision(repo, tag) != head:
            candidates.append((value, tag))
    return max(candidates)[1] if candidates else None


def plan(repo, base, head, extended=False, published_tags=None):
    head_sha = revision(repo, head)
    if base is None:
        base = automatic_base(repo, head_sha, published_tags)
    base_sha = revision(repo, base) if base is not None else None
    if base_sha:
        git(repo, 'merge-base', '--is-ancestor', base_sha, head_sha)
    if base_sha is None:
        return {'format': 'rieke-desktop-release-plan', 'version': 1, 'base': None, 'head': head_sha,
                'base_ref': None, 'head_ref': head, 'reason': 'No comparable ancestor release baseline; all qualification is required',
                'changed_paths': sorted(git(repo, 'ls-tree', '-r', '--name-only', head_sha).splitlines()),
                **dict.fromkeys(FLAGS, True), 'risk_reasons': {'baseline': ['No comparable ancestor release baseline']}}
    paths = changed_paths(repo, base_sha, head_sha)
    classified = {}
    for path in paths:
        if test_scripts_only(repo, path, base_sha, head_sha):
            classified[path] = set()
        elif version_only(repo, path, base_sha, head_sha):
            classified[path] = {'routine'}
        else:
            classified[path] = change_kind(path)
    risks = {kind for values in classified.values() for kind in values}
    build = bool(risks)
    selected = {flag: flag in risks for flag in FLAGS[1:]}
    risk_reasons = {kind: [path for path in paths if kind in classified[path]] for kind in sorted(risks)}
    if extended and build:
        selected = dict.fromkeys(FLAGS[1:], True)
        risk_reasons['extended'] = ['Explicit extended qualification requested']
    return {'format': 'rieke-desktop-release-plan', 'version': 1, 'base': base_sha, 'head': head_sha,
            'base_ref': base, 'head_ref': head,
            'reason': 'Application changes require a build' if build else 'No application changes',
            'changed_paths': paths, 'build_required': build, **selected,
            'risk_reasons': risk_reasons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--base')
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--extended', action='store_true')
    parser.add_argument('--published-tags', type=Path, help='JSON array of published release tag names; filters automatic baselines only')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--github-output', type=Path)
    arguments = parser.parse_args()
    try:
        published = None
        if arguments.published_tags is not None:
            value = json.loads(arguments.published_tags.read_text())
            if not isinstance(value, list) or any(not isinstance(tag, str) for tag in value):
                raise ValueError('Published tags must be a JSON array of tag-name strings')
            published = set(value)
        result = plan(arguments.repo, arguments.base, arguments.head, arguments.extended, published)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2) + '\n')
    if arguments.github_output:
        with arguments.github_output.open('a') as stream:
            for key in (*FLAGS, 'base', 'head'):
                value = result[key]
                stream.write(key + '=' + (str(value).lower() if isinstance(value, bool) else value or '') + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
