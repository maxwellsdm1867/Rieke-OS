#!/usr/bin/env python3
"""Stage an exact development desktop over copied pinned dependencies, never install."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def command(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--runtime-source', type=Path, required=True)
    parser.add_argument('--dependency-root', type=Path, required=True,
                        help='Matching desktop dependency directory containing package-lock.json/node_modules')
    args = parser.parse_args()
    source, runtime_source, dependencies = [value.resolve(strict=True) for value in
                                           (args.source_root, args.runtime_source, args.dependency_root)]
    if sys.platform != 'darwin':
        raise ValueError('This staged native diagnostic currently requires macOS/APFS clone support')
    if any(part.endswith('.app') for part in runtime_source.parts):
        raise ValueError('Use an owned build runtime, never an installed application bundle')
    status = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True)
    if status.strip():
        raise ValueError('Freeze a clean candidate before staging')
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    def dependency_identity(file):
        value = json.loads(file.read_text())
        value.pop('version', None)
        value['packages'][''].pop('version', None)
        return value
    if dependency_identity(source / 'desktop/package-lock.json') != dependency_identity(dependencies / 'package-lock.json'):
        raise ValueError('Desktop dependency lock differs')
    for original, expected in [('python-lock.json', 'desktop/python-runtime.json'),
                               ('mysql-lock.json', 'python/workspace-mysql-runtime.json')]:
        if json.loads((runtime_source / original).read_text()) != json.loads((source / expected).read_text()):
            raise ValueError(f'Runtime dependency policy differs: {original}')
    stage = Path(tempfile.mkdtemp(prefix='disco-retention-stage-')).resolve()
    desktop = stage / 'desktop'
    desktop.mkdir()
    names = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z', 'desktop'], text=True).split('\0')
    for name in filter(None, names):
        original, target = source / name, stage / name
        if original.is_symlink():
            raise ValueError(f'Staged source link requires explicit review: {name}')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    (desktop / 'node_modules').symlink_to(dependencies / 'node_modules', target_is_directory=True)
    runtime = desktop / 'build/runtime'
    runtime.parent.mkdir(parents=True)
    # APFS clone preserves the dependency tree without modifying the original.
    # Failure is explicit; do not silently fall back to an installed application.
    command(['/bin/cp', '-cR', runtime_source, runtime])
    command([sys.executable, '-B', source / 'tools/desktop_build_runtime.py',
             '--refresh-application', '--output', runtime], cwd=source)
    manifest = json.loads((runtime / 'runtime-manifest.json').read_text())
    if manifest.get('source_commit') != commit or manifest.get('source_dirty') is not False:
        raise ValueError('Refreshed runtime does not attest the frozen clean candidate')
    receipt = {'stage': str(stage), 'desktop': str(desktop), 'runtime': str(runtime),
               'source_root': str(source), 'source_commit': commit,
               'runtime_dependencies_from': str(runtime_source), 'dependency_root': str(dependencies)}
    (stage / 'stage-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
