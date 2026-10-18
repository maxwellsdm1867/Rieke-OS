#!/usr/bin/env python3
"""Create exact-byte metadata for an explicitly unsigned GitHub testing release.

This is separate from production promotion and never claims Apple verification.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import tempfile
import zipfile

REPOSITORY='maxwellsdm1867/Rieke-OS'

def hashes(path):
    a,b=hashlib.sha256(),hashlib.sha512()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            a.update(block);b.update(block)
    return a.hexdigest(),base64.b64encode(b.digest()).decode()

def electron_helper(bundle, app_plist):
    # Electron 44.5.0 OverrideChildProcessPath probes Electron Helper first,
    # then the internal CFBundleName. CFBundleDisplayName is not its lookup key.
    frameworks = bundle/'Contents/Frameworks'
    helper_name = 'Electron Helper'
    executable = frameworks/(helper_name+'.app')/'Contents/MacOS'/helper_name
    if not executable.exists():
        name = app_plist.get('CFBundleName')
        if not isinstance(name, str) or not name or '/' in name or '\\' in name:
            raise ValueError('App has no valid internal name for Electron helper lookup')
        helper_name = name+' Helper'
        executable = frameworks/(helper_name+'.app')/'Contents/MacOS'/helper_name
    if (not executable.is_file() or not os.access(executable, os.X_OK)
            or not executable.resolve().is_relative_to(bundle.resolve())):
        raise ValueError('Electron helper executable is missing, non-executable or outside the app')
    info = executable.parent.parent/'Info.plist'
    helper = plistlib.loads(info.read_bytes())
    if (helper.get('CFBundleExecutable') != helper_name
            or helper.get('CFBundleIdentifier') != app_plist['CFBundleIdentifier']+'.helper'):
        raise ValueError('Electron helper identity or executable declaration differs')
    return executable, info

def build_descriptor(bundle,archive):
    bundle,archive=Path(bundle),Path(archive)
    runtime=bundle/'Contents/Resources/runtime'
    raw=(runtime/'runtime-manifest.json').read_bytes();manifest=json.loads(raw)
    version=manifest.get('application_version')
    if not isinstance(version,str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',version):raise ValueError('Invalid application version')
    if manifest.get('format')!='rieke-desktop-runtime' or manifest.get('version')!=1 or manifest.get('platform')!='darwin' or manifest.get('architecture')!='arm64':raise ValueError('Unsupported desktop runtime')
    app_info=bundle/'Contents/Info.plist';app_info_bytes=app_info.read_bytes();plist=plistlib.loads(app_info_bytes)
    if plist.get('CFBundleIdentifier')!='org.riekeos.desktop' or plist.get('CFBundleShortVersionString')!=version:raise ValueError('App identity or version differs')
    if plist.get('CFBundleDisplayName')!='DISCO' or plist.get('CFBundleName')!='Disco':raise ValueError('App display or bundle name differs from DISCO')
    executable=bundle/'Contents/MacOS/Disco'
    if bundle.name!='Disco.app' or plist.get('CFBundleExecutable')!='Disco' or not executable.is_file() or not os.access(executable,os.X_OK) or not executable.resolve().is_relative_to(bundle.resolve()):raise ValueError('Shipping app filename or executable differs from Disco')
    helper_executable,helper_info=electron_helper(bundle,plist)
    if archive.name!=f'Disco-{version}-arm64.zip':raise ValueError('Archive name differs from version')
    asar=hashes(bundle/'Contents/Resources/app.asar')[0]
    with zipfile.ZipFile(archive) as z:
        archived_manifest=z.read('Disco.app/Contents/Resources/runtime/runtime-manifest.json')
        archived_asar=hashlib.sha256(z.read('Disco.app/Contents/Resources/app.asar')).hexdigest()
        if archived_manifest!=raw or archived_asar!=asar:raise ValueError('Archive is not the inspected app')
        try:
            for file in [app_info,executable,helper_info,helper_executable]:
                archived=z.read(bundle.name+'/'+file.relative_to(bundle).as_posix())
                if hashlib.sha256(archived).hexdigest()!=hashes(file)[0]:raise ValueError('Archive app/helper identity differs from the inspected app')
        except KeyError as error:
            raise ValueError('Archive omits the inspected app or Electron helper identity') from error
    sha256,sha512=hashes(archive)
    return {'format':'rieke-desktop-test-release','version':1,'channel':'unsigned-testing','repository':'maxwellsdm1867/Rieke-OS','canonical_repository':REPOSITORY,
            **{key:manifest[key] for key in ['application_version','platform','architecture','workspace_formats','database_compatibility','mysql_version','minimum_macos_version']},
            'archive':{'filename':archive.name,'size':archive.stat().st_size,'sha256':sha256,'sha512':sha512},
            'asar_sha256':asar,'runtime_manifest_sha256':hashlib.sha256(raw).hexdigest(),
            'source_commit':manifest.get('source_commit'),'source_dirty':manifest.get('source_dirty'),
            'production_ready':False}

def publish(bundle, archive, output, notes, candidate_run_id, verification_run_id=None):
    """Publish only a fully checked exact-byte unsigned candidate; never replace assets."""
    from desktop_source_ci import api, artifact, require_source_ci, require_tag
    descriptor = build_descriptor(bundle, archive)
    if descriptor['source_dirty'] is not False:
        raise ValueError('Cannot publish a dirty or unproven source')
    verification = {} if verification_run_id is None else {'verification_run_id': verification_run_id}
    proof = require_source_ci(REPOSITORY, descriptor['source_commit'], candidate_run_id, **verification)
    qualified = artifact(REPOSITORY, {'id': proof['candidate_run']},
                         'desktop-release-metadata', 'desktop-release.json')
    if qualified != descriptor:
        raise ValueError('Local archive differs from the successful native candidate')
    output = Path(output)
    if output.name != 'desktop-release.json':
        raise ValueError('Publication descriptor must be named desktop-release.json')
    # All qualification and local reads precede the first remote mutation.
    note_text = Path(notes).read_text()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(descriptor, indent=2) + '\n')
    tag = 'desktop-test-v' + descriptor['application_version']
    # Candidate qualification already requires a reviewed version tag. Do not
    # rely on publication to create a missing Git ref.
    require_tag(REPOSITORY, tag, descriptor['source_commit'])
    with tempfile.TemporaryDirectory(prefix='disco-publication-') as temporary:
        root = Path(temporary)
        sums = root / 'SHA256SUMS'
        assets = [Path(archive), output]
        sums.write_text(''.join(f'{hashes(path)[0]}  {path.name}\n' for path in assets))
        assets.append(sums)
        release_notes = root / 'notes.md'
        release_notes.write_text('Unsigned Apple silicon testing prerelease. Not production-qualified.\n\n' + note_text)
        # Existing releases are refused by gh; no --clobber.
        subprocess.run(['gh', 'release', 'create', tag, '--repo', REPOSITORY,
                        '--target', descriptor['source_commit'], '--draft', '--prerelease',
                        '--title', f'Disco {descriptor["application_version"]} testing',
                        '--notes-file', str(release_notes), *map(str, assets)], check=True)
        # The REST tag endpoint only resolves published releases. gh's view
        # command also finds authenticated drafts; use its numeric ID thereafter.
        identity = json.loads(subprocess.check_output(
            ['gh', 'release', 'view', tag, '--repo', REPOSITORY,
             '--json', 'databaseId,tagName,isDraft,targetCommitish'], text=True))
        if (type(identity.get('databaseId')) is not int or identity['databaseId'] <= 0
                or identity.get('tagName') != tag or identity.get('isDraft') is not True
                or identity.get('targetCommitish') != descriptor['source_commit']):
            raise ValueError('Created draft identity differs; release remains a draft')
        release = api(f'repos/{REPOSITORY}/releases/{identity["databaseId"]}')
        if (release.get('id') != identity['databaseId'] or release.get('draft') is not True
                or release.get('tag_name') != tag
                or release.get('target_commitish') != descriptor['source_commit']):
            raise ValueError('Created draft identity differs; release remains a draft')
        uploaded = {row['name']: row for row in release['assets']}
        for path in assets:
            row = uploaded.get(path.name, {})
            if row.get('digest') != 'sha256:' + hashes(path)[0] or row.get('size') != path.stat().st_size:
                raise ValueError('Uploaded bytes differ; release remains a draft')
        # Recheck immediately before visibility: a newer pending/failed CI run blocks it.
        require_source_ci(REPOSITORY, descriptor['source_commit'], candidate_run_id, **verification)
        require_tag(REPOSITORY, tag, descriptor['source_commit'])
        subprocess.run(['gh', 'release', 'edit', tag, '--repo', REPOSITORY,
                        '--draft=false', '--prerelease', '--latest=false'], check=True)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app',type=Path,required=True);parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--candidate-run-id')
    parser.add_argument('--verification-run-id', help='Separate full-suite run verifying the original candidate archive')
    parser.add_argument('--notes', type=Path)
    args=parser.parse_args()
    if args.publish:
        if not args.candidate_run_id or not args.notes: parser.error('--publish requires --candidate-run-id and --notes')
        print(json.dumps(publish(args.app, args.archive, args.output, args.notes, args.candidate_run_id, args.verification_run_id)))
    else:
        descriptor=build_descriptor(args.app,args.archive)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(descriptor,indent=2)+'\n')
        print('Wrote unsigned test metadata for '+descriptor['application_version'])
