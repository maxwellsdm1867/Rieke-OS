"""Select the user workflows a change can affect for Disco integration."""
import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess


NATIVE = (
    '.github/workflows/desktop-startup-quit.yml', 'tools/desktop_packaging_fs.cjs',
    'desktop/entry.cjs', 'desktop/bootstrap.cjs', 'desktop/main.cjs', 'desktop/supervisor.cjs',
    'desktop/preload.cjs', 'desktop/project-views.cjs', 'desktop/session-profiles.cjs',
    'desktop/runtime-generations.cjs', 'desktop/runtime-store.py', 'desktop/close/*.cjs',
    'desktop/startup/*.cjs', 'desktop/integrity/*.cjs', 'desktop/e2e/startup-quit*',
    'desktop/e2e/helpers.cjs', 'desktop/e2e/packaged-path.cjs', 'tools/organization_e2e_fixture.py',
    'desktop/distribution.json', 'desktop/package.json', 'desktop/package-lock.json',
    'desktop/tests/main-startup-restoration.test.cjs', 'desktop/drafts/*.cjs',
    'python/workspace_desktop.py', 'tools/desktop_build_runtime.py', 'tools/desktop_runtime_manifest.py',
    'desktop/python-runtime.json', 'desktop/seal-testing.cjs', 'desktop/sign-runtime.cjs',
    'desktop/distribution.cjs', 'desktop/entitlements.mac.plist', 'python/workspace-mysql-runtime.json',
    'python/workspace-runtime.lock', 'python/workspace-source.json',
)
INSTALL = (
    'install.sh', 'install.ps1', 'rieke.py', 'python/workspace_bootstrap.py',
    'python/workspace_mysql_runtime.py', 'python/workspace-mysql-runtime.json',
    'python/workspace-runtime.lock', 'requirements.txt', '.github/workflows/verify.yml',
)
PAGES = (
    'README.md', 'CHANGELOG.md', '.github/workflows/release-pages.yml',
    'tools/desktop_release_pages.py', 'python/tests/test_desktop_release_pages.py',
)
POLICY = ('.github/workflows/integration.yml', 'tools/integration_scope.py', 'tools/integration_reuse.py')


def select(paths):
    return {name: paths is None or any(PurePosixPath('/' + path).match('/' + pattern) for path in paths
                                        for pattern in (*patterns, *POLICY))
            for name, patterns in [('native', NATIVE), ('install', INSTALL), ('pages', PAGES)]}


def changed_paths(base):
    if not re.fullmatch(r'[0-9a-f]{40}', base) or base == '0' * 40:
        return None
    if subprocess.run(['git', 'merge-base', '--is-ancestor', base, 'HEAD']).returncode:
        return None
    data = subprocess.check_output(['git', 'diff', '--name-only', '--no-renames', '-z', base, 'HEAD'])
    return [path.decode('utf-8', 'surrogateescape') for path in data.split(b'\0') if path]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--github-output', required=True, type=Path)
    args = parser.parse_args()
    with args.github_output.open('a') as out:
        for key, value in select(changed_paths(args.base)).items():
            print(f'{key}={str(value).lower()}', file=out)
