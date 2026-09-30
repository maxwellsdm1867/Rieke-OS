#!/usr/bin/env python3
"""Fail-closed desktop baseline, artifact evidence and serialized promotion controls.

This tool cannot create scientific qualification evidence; reviewed real-device
receipts must be supplied independently against the exact candidate hashes.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'maxwellsdm1867/Rieke-OS'
REQUIREMENTS = [f'R{index:02}' for index in range(1, 13)]


def run(*arguments):
    return subprocess.check_output(arguments, text=True).strip()


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('A stable version is required')
    return tuple(map(int, value.split('.')))


def baseline(tag, repository):
    if repository != REPOSITORY or not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError('Desktop release requires the canonical repository and stable version tag')
    release = json.loads((ROOT / 'rieke-release.json').read_text())
    frontend = json.loads((ROOT / 'workspace-app/package.json').read_text())
    desktop = json.loads((ROOT / 'desktop/package.json').read_text())
    if release['version'] != tag[1:] or any(item['version'] != release['version'] for item in (frontend, desktop)):
        raise ValueError('Release, frontend, desktop and tag versions differ')
    version(release['version'])
    if release['repository'] != REPOSITORY or release['channel'] != 'stable':
        raise ValueError('Desktop release provider or channel differs')
    if run('git', '-C', str(ROOT), 'status', '--porcelain'):
        raise ValueError('Desktop release requires a clean reviewed checkout')
    commit = run('git', '-C', str(ROOT), 'rev-parse', 'HEAD')
    if run('git', '-C', str(ROOT), 'rev-parse', tag + '^{commit}') != commit:
        raise ValueError('Desktop build must use the exact reviewed tag commit')
    return {'format': 'rieke-desktop-baseline', 'version': 1, 'source_commit': commit,
            'application_version': release['version'], 'repository': REPOSITORY,
            'workspace_formats': release['workspace_formats'], 'database_compatibility': release['database_compatibility']}


def digest(file, algorithm='sha256'):
    with file.open('rb') as handle:
        return hashlib.file_digest(handle, algorithm).digest()


def artifact_inventory(directory):
    result = {}
    for file in sorted(directory.iterdir()):
        if file.is_symlink():
            raise ValueError('Release artifact must not be a symlink')
        if file.is_file() and (file.suffix in {'.dmg', '.zip', '.blockmap'} or file.name == 'latest-mac.yml'):
            result[file.name] = {'sha256': digest(file).hex(), 'size': file.stat().st_size}
    if not any(name.endswith('.dmg') for name in result) or not any(name.endswith('.zip') for name in result) or 'latest-mac.yml' not in result:
        raise ValueError('Complete DMG, updater ZIP and latest-mac.yml are required')
    return result


def verify_metadata(directory, expected_version):
    # Read electron-builder's own YAML parser from the exact desktop lockfile.
    script = "const fs=require('fs'),yaml=require('js-yaml');process.stdout.write(JSON.stringify(yaml.load(fs.readFileSync(process.argv[1],'utf8'))))"
    metadata = json.loads(subprocess.check_output(['node', '-e', script, str(directory / 'latest-mac.yml')], cwd=ROOT / 'desktop', text=True))
    if metadata.get('version') != expected_version or not isinstance(metadata.get('files'), list):
        raise ValueError('Updater metadata has wrong version or missing files')
    found_zip = False
    for entry in metadata['files']:
        name = entry.get('url')
        if not isinstance(name, str) or Path(name).name != name or not re.fullmatch(r'[A-Za-z0-9._-]+', name):
            raise ValueError('Updater asset name is unsafe')
        file = directory / name
        if not file.is_file() or file.is_symlink() or entry.get('sha512') != base64.b64encode(digest(file, 'sha512')).decode():
            raise ValueError('Updater asset hash differs from final bytes')
        if entry.get('size') != file.stat().st_size:
            raise ValueError('Updater asset size differs from final bytes')
        found_zip |= name.endswith('.zip') and 'arm64' in name
    if not found_zip:
        raise ValueError('Updater metadata must contain the macOS arm64 ZIP')
    selected = next((entry for entry in metadata['files'] if entry['url'] == metadata.get('path')), None)
    if selected is None or selected.get('sha512') != metadata.get('sha512') or not selected['url'].endswith('.zip'):
        raise ValueError('Legacy updater fields disagree with selected ZIP metadata')
    return metadata


def validate_evidence(evidence, artifacts, expected_version):
    if evidence.get('format') != 'rieke-desktop-qualification' or evidence.get('version') != 1:
        raise ValueError('Real desktop qualification evidence is required')
    if evidence.get('application_version') != expected_version or evidence.get('platform') != 'darwin' or evidence.get('architecture') != 'arm64':
        raise ValueError('Qualification identity differs from candidate')
    if evidence.get('artifacts') != artifacts:
        raise ValueError('Qualification was not run against these exact artifact hashes')
    if not re.fullmatch(r'[a-f0-9]{40}', evidence.get('source_commit', '')):
        raise ValueError('Qualification requires reviewed source provenance')
    gates = evidence.get('requirements', {})
    for identifier in REQUIREMENTS:
        gate = gates.get(identifier, {})
        if gate.get('passed') is not True or not gate.get('receipts') or not isinstance(gate['receipts'], list):
            raise ValueError(f'{identifier} has no reviewed real-artifact qualification receipt')
        for receipt in gate['receipts']:
            if not isinstance(receipt, dict) or not re.fullmatch(r'[a-f0-9]{64}', receipt.get('sha256', '')) or not receipt.get('description'):
                raise ValueError(f'{identifier} receipt is incomplete')
    return evidence


def gh_json(*arguments, payload=None):
    command = ['gh', 'api', *arguments]
    if payload is not None:
        command += ['--input', '-']
    output = subprocess.check_output(command, input=json.dumps(payload) if payload is not None else None, text=True)
    return json.loads(output)


def promote(directory, tag, evidence_path):
    expected_version = tag.removeprefix('v')
    version(expected_version)
    artifacts = artifact_inventory(directory)
    verify_metadata(directory, expected_version)
    evidence = validate_evidence(json.loads(evidence_path.read_text()), artifacts, expected_version)
    remote_tag = gh_json(f'repos/{REPOSITORY}/git/ref/tags/{tag}')['object']
    if remote_tag['type'] == 'tag':
        remote_tag = gh_json(remote_tag['url'])['object']
    if remote_tag.get('type') != 'commit' or remote_tag.get('sha') != evidence['source_commit']:
        raise ValueError('Qualification source commit differs from canonical release tag')
    releases = gh_json(f'repos/{REPOSITORY}/releases?per_page=100')
    published = [release for release in releases if not release['draft'] and not release['prerelease'] and re.fullmatch(r'v\d+\.\d+\.\d+', release['tag_name'])]
    if any(version(release['tag_name'][1:]) > version(expected_version) for release in published):
        raise ValueError('A newer stable version is already published')
    release = next((item for item in releases if item['tag_name'] == tag), None)
    if release is None:
        release = gh_json(f'repos/{REPOSITORY}/releases', '-X', 'POST', payload={'tag_name': tag, 'target_commitish': evidence['source_commit'], 'name': 'Rieke OS ' + tag,
                           'draft': True, 'prerelease': False, 'make_latest': 'false'})
    if release['prerelease']:
        raise ValueError('Stable and prerelease channels cannot share a release')
    existing = {asset['name']: asset for asset in gh_json(f"repos/{REPOSITORY}/releases/{release['id']}/assets?per_page=100")}
    for name, record in artifacts.items():
        if name in existing:
            asset_digest = existing[name].get('digest')
            if existing[name]['size'] != record['size'] or asset_digest != 'sha256:' + record['sha256']:
                raise ValueError('Retry would replace existing release bytes; promotion rejected')
        elif not release['draft']:
            raise ValueError('Published release is incomplete; do not mutate its artifact set')
        else:
            subprocess.run(['gh', 'release', 'upload', tag, str(directory / name), '--repo', REPOSITORY], check=True)
    if release['draft']:
        gh_json(f"repos/{REPOSITORY}/releases/{release['id']}", '-X', 'PATCH', payload={'draft': False, 'make_latest': 'false'})
    # Expose the complete release without moving latest, then verify final public
    # download URLs with no authentication before changing stable selection.
    for name, record in artifacts.items():
        url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
        hasher, size = hashlib.sha256(), 0
        with urlopen(Request(url, headers={'User-Agent': 'Rieke-OS-release-verifier'}), timeout=60) as response:
            if not response.url.startswith('https://'):
                raise ValueError('Public release asset redirected outside HTTPS')
            while chunk := response.read(1024 * 1024):
                hasher.update(chunk); size += len(chunk)
        if size != record['size'] or hasher.hexdigest() != record['sha256']:
            raise ValueError('Public artifact bytes differ; latest has not been promoted')
    gh_json(f"repos/{REPOSITORY}/releases/{release['id']}", '-X', 'PATCH', payload={'make_latest': 'true'})
    return {'published': tag, 'artifacts': artifacts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['baseline', 'inventory', 'verify', 'promote'])
    parser.add_argument('--tag')
    parser.add_argument('--repository', default=REPOSITORY)
    parser.add_argument('--directory', type=Path, default=ROOT / 'desktop/dist')
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'baseline':
        result = baseline(args.tag, args.repository)
    elif args.command == 'inventory':
        result = {'format': 'rieke-desktop-artifacts', 'version': 1, 'artifacts': artifact_inventory(args.directory)}
    elif args.command == 'verify':
        artifacts = artifact_inventory(args.directory)
        verify_metadata(args.directory, args.tag.removeprefix('v'))
        result = validate_evidence(json.loads(args.evidence.read_text()), artifacts, args.tag.removeprefix('v'))
    else:
        if args.repository != REPOSITORY:
            raise ValueError('Publication is restricted to the canonical desktop repository')
        result = promote(args.directory, args.tag, args.evidence)
    serialized = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(serialized)
    print(serialized)


if __name__ == '__main__':
    main()
