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
    if plist.get('CFBundleDisplayName')!='Disco' or plist.get('CFBundleName')!='Disco':raise ValueError('App display or bundle name differs from Disco')
    helper_executable,helper_info=electron_helper(bundle,plist)
    if archive.name!=f'Rieke-OS-{version}-arm64.zip':raise ValueError('Archive name differs from version')
    asar=hashes(bundle/'Contents/Resources/app.asar')[0]
    with zipfile.ZipFile(archive) as z:
        archived_manifest=z.read('Rieke OS.app/Contents/Resources/runtime/runtime-manifest.json')
        archived_asar=hashlib.sha256(z.read('Rieke OS.app/Contents/Resources/app.asar')).hexdigest()
        if archived_manifest!=raw or archived_asar!=asar:raise ValueError('Archive is not the inspected app')
        try:
            for file in [app_info,helper_info,helper_executable]:
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

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app',type=Path,required=True);parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();descriptor=build_descriptor(args.app,args.archive)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(descriptor,indent=2)+'\n')
    print('Wrote unsigned test metadata for '+descriptor['application_version'])
