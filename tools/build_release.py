#!/usr/bin/env python3
"""Build a signed application source release from a clean tested Git commit.

Private keys stay outside the repository. This creates artifacts; it never
publishes a release. Runtime dependencies are installed into the staged release.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from workspace_updates import REPOSITORY, release_metadata, verify_manifest
from workspace_mysql_runtime import runtime_spec, mysql_runtime


def validate_versions(root=ROOT):
    metadata = release_metadata(root)
    package = json.loads((root / 'workspace-app/package.json').read_text())
    lock = json.loads((root / 'workspace-app/package-lock.json').read_text())
    if package['version'] != metadata['version'] or lock['version'] != metadata['version'] or lock['packages']['']['version'] != metadata['version']:
        raise ValueError('Application, frontend package and lockfile versions must agree')
    return metadata


def build(output, private_key, public_key, target):
    metadata = validate_versions()
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT).strip():
        raise ValueError('Release builds require a clean reviewed checkout')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    expected = 'v' + metadata['version']
    tag_commit = subprocess.check_output(['git', 'rev-parse', expected + '^{commit}'], cwd=ROOT, text=True).strip()
    if tag_commit != commit:
        raise ValueError('Release version tag must point to this tested commit')
    frontend = ROOT / 'workspace-app/dist'
    if not (frontend / 'index.html').is_file():
        raise ValueError('Build and test the frontend before packaging')
    mysql_runtime(ROOT)  # All three native executables must pass their pinned version probe.
    _, native = runtime_spec(ROOT)
    native_archives = []
    for dependency in [native['installer'], *native['packages']]:
        path = ROOT / '.rieke-runtime/mysql-packages' / dependency['url'].rsplit('/', 1)[-1]
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != dependency['sha256']:
            raise ValueError('Bundled native MySQL dependency is missing or modified: ' + path.name)
        native_archives.append(path)
    # Tracked source and verified dependency archives only; never package database
    # files or an already-relocated private MySQL prefix.
    source = subprocess.check_output(['git', 'archive', '--format=tar', 'HEAD'], cwd=ROOT)
    output.mkdir(parents=True, exist_ok=True)
    name = f'rieke-os-{metadata["version"]}-{target}.tar.gz'
    artifact = output / name
    with tarfile.open(fileobj=io.BytesIO(source)) as archive, tarfile.open(artifact, 'w:gz') as result:
        for entry in archive:
            if not (entry.isfile() or entry.isdir()):
                raise ValueError('Release source contains unsupported symbolic links')
            result.addfile(entry, archive.extractfile(entry) if entry.isfile() else None)
        for path in sorted(frontend.rglob('*')):
            if path.is_file():
                result.add(path, arcname=path.relative_to(ROOT), recursive=False)
        for path in native_archives:
            result.add(path, arcname=path.relative_to(ROOT), recursive=False)
    payload = json.dumps({'format': 'rieke-release-manifest', 'updater_protocol': 1,
        'repository': REPOSITORY, 'version': metadata['version'], 'commit': commit,
        'database_compatibility': metadata['database_compatibility'],
        'artifacts': [{'platform': target, 'url': f'https://github.com/{REPOSITORY}/releases/download/{expected}/{name}',
                       'size': artifact.stat().st_size, 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}]},
        sort_keys=True, separators=(',', ':')).encode()
    payload_file = output / '.signing-payload'
    signature_file = output / '.signature'
    try:
        payload_file.write_bytes(payload)
        subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(private_key), '-out', str(signature_file), str(payload_file)], check=True)
        envelope = json.dumps({'algorithm': 'rsa-sha256', 'payload': base64.b64encode(payload).decode(),
                               'signature': base64.b64encode(signature_file.read_bytes()).decode()}, indent=2).encode()
        verify_manifest(envelope, public_key)
        (output / 'rieke-release-manifest.json').write_bytes(envelope)
    finally:
        payload_file.unlink(missing_ok=True)
        signature_file.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--private-key', type=Path)
    parser.add_argument('--public-key', type=Path, default=ROOT / 'release-signing-public.pem')
    parser.add_argument('--platform', choices=['darwin-arm64'], default='darwin-arm64')
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps(validate_versions()))
    else:
        if not args.output or not args.private_key:
            parser.error('--output and --private-key are required to build')
        build(args.output, args.private_key, args.public_key, args.platform)
