#!/usr/bin/env python3
"""Inventory and audit unsigned desktop resources; this is not qualification."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MACHO = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
         b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}


def inventory(runtime):
    runtime = Path(runtime).resolve(strict=True)
    result = {}
    for path in sorted(runtime.rglob('*')):
        relative = path.relative_to(runtime).as_posix()
        if relative in ('runtime-manifest.json', 'runtime-audit.json'):
            continue
        if path.is_symlink():
            target = os.readlink(path)
            if Path(target).is_absolute() or not path.resolve().is_relative_to(runtime):
                raise ValueError(f'Runtime link escapes packaged resources: {relative}')
            if not path.exists():
                raise ValueError(f'Runtime link is broken: {relative}')
            result[relative] = {'symlink': target}
        elif path.is_file():
            with path.open('rb') as handle:
                sha = hashlib.file_digest(handle, 'sha256').hexdigest()
            result[relative] = {'sha256': sha, 'size': path.stat().st_size,
                                'executable': bool(path.stat().st_mode & 0o111)}
    return result


def native_audit(runtime):
    problems, binaries, minimum = [], 0, set()
    for path in sorted(runtime.rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open('rb') as handle:
            if handle.read(4) not in MACHO:
                continue
        binaries += 1
        relative = path.relative_to(runtime).as_posix()
        header = subprocess.check_output(['/usr/bin/otool', '-l', path], text=True)
        rpaths = re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', header)
        for value in rpaths:
            if value.startswith('/') and not value.startswith(('/usr/lib/', '/System/Library/')):
                problems.append({'path': relative, 'code': 'external_rpath', 'value': value})
        minimum.update(re.findall(r'\bminos ([\d.]+)', header))
        minimum.update(re.findall(r'cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version ([\d.]+)', header))
        # otool -L includes the dylib's own ID and per-architecture headers.
        # Those are not loaded dependencies. Audit the actual load commands.
        deps = re.findall(r'cmd LC_(?:LOAD_DYLIB|LOAD_WEAK_DYLIB|REEXPORT_DYLIB|LAZY_LOAD_DYLIB|LOAD_UPWARD_DYLIB)\s+cmdsize \d+\s+name (.*?) \(offset', header)
        for value in deps:
            if value.startswith(('/usr/lib/', '/System/Library/')):
                continue
            if value.startswith('/'):
                problems.append({'path': relative, 'code': 'external_native_dependency', 'value': value})
            elif value.startswith('@loader_path/'):
                if not (path.parent / value[len('@loader_path/'):]).exists():
                    problems.append({'path': relative, 'code': 'missing_native_dependency', 'value': value})
            elif value.startswith('@rpath/'):
                filename = value[len('@rpath/'):]
                # Direct rpaths plus parent runtime library search; loader inheritance
                # must still be exercised in the relocation smoke qualification.
                candidates = [Path(r.replace('@loader_path', str(path.parent))) / filename for r in rpaths]
                candidates.extend(parent / 'lib' / filename for parent in path.parents if parent.is_relative_to(runtime))
                if not any(candidate.exists() for candidate in candidates):
                    problems.append({'path': relative, 'code': 'unresolved_native_dependency', 'value': value})
    return {'native_binaries': binaries, 'declared_macos_minimums': sorted(minimum),
            'problems': problems, 'production_ready': False,
            'not_validated': ['Developer ID signing and notarization', 'clean-machine installation',
                              'signed old-to-new update', 'complete scientific workflow qualification']}


def make_manifest(runtime, root=ROOT):
    release = json.loads((runtime / 'application/rieke-release.json').read_text())
    source = json.loads((runtime / 'application/python/workspace-source.json').read_text())
    mysql = json.loads((runtime / 'mysql-lock.json').read_text())
    python = json.loads((runtime / 'python-lock.json').read_text())
    commit = subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', root, 'status', '--porcelain'], text=True).strip())
    receipt = json.loads((runtime / 'build-receipt.json').read_text())
    return {'format': 'rieke-desktop-runtime', 'version': 1,
            'application_version': release['version'], 'source_commit': commit,
            'source_dirty': dirty, 'parser_commit': source['commit'],
            'platform': 'darwin', 'architecture': 'arm64', 'python_version': python['python_version'],
            'mysql_version': mysql['mysql_version'], 'workspace_formats': release['workspace_formats'],
            'database_compatibility': release['database_compatibility'],
            'excluded_optional_features': receipt.get('excluded_optional_features', []),
            'resources': inventory(runtime)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT / 'desktop/build/runtime')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--rehash-existing', action='store_true',
                        help='Preserve build identity and refresh hashes after nested signing')
    args = parser.parse_args()
    runtime = args.runtime.resolve(strict=True)
    if args.rehash_existing:
        manifest = json.loads((runtime / 'runtime-manifest.json').read_text())
        if manifest.get('format') != 'rieke-desktop-runtime' or manifest.get('version') != 1:
            raise ValueError('Cannot rehash an unrecognized manifest')
        manifest['resources'] = inventory(runtime)
    else:
        manifest = make_manifest(runtime)
    audit = native_audit(runtime)
    minimums = audit['declared_macos_minimums']
    if minimums:
        manifest['minimum_macos_version'] = max(minimums, key=lambda value: tuple(int(part) for part in value.split('.')))
    if args.write:
        (runtime / 'runtime-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        (runtime / 'runtime-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    else:
        existing = json.loads((runtime / 'runtime-manifest.json').read_text())
        if existing['resources'] != manifest['resources']:
            raise ValueError('Packaged resources differ from runtime manifest')
    print(json.dumps({'resources': len(manifest['resources']), **audit}, indent=2))
    if audit['problems']:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
