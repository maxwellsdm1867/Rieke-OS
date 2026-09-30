#!/usr/bin/env python3
"""Audit exact desktop DMG/ZIP bytes and exercise their relocated private runtime.

Uses scratch copies only; the provided reference app and artifacts are read-only.
The reference may be a built candidate; this never updates the user's installed app.
This unsigned local-host evidence cannot qualify a clean machine or signed update.
"""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from desktop_runtime_manifest import inventory, native_audit
from desktop_release import artifact_inventory, verify_metadata, validate_evidence, baseline


def digest(path, algorithm='sha256'):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, algorithm).digest()


def execute(command, **options):
    return subprocess.run([str(part) for part in command], check=True, capture_output=True, **options)


def resource_modes(runtime, manifest):
    failures = []
    for relative, expected in manifest['resources'].items():
        file = runtime / relative
        if 'executable' in expected and bool(file.stat().st_mode & 0o111) != expected['executable']:
            failures.append(relative)
    return failures


def inspect_bundle(bundle):
    runtime = bundle / 'Contents/Resources/runtime'
    manifest = json.loads((runtime / 'runtime-manifest.json').read_text())
    plist = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    actual = inventory(runtime)
    if actual != manifest['resources']:
        raise ValueError('Artifact runtime bytes/links/modes differ from signed-resource manifest')
    modes = resource_modes(runtime, manifest)
    if modes:
        raise ValueError('Packaged executable modes changed')
    if plist['CFBundleIdentifier'] != 'org.riekeos.desktop' or plist['CFBundleShortVersionString'] != manifest['application_version']:
        raise ValueError('App identity/version differs from runtime')
    if plist.get('LSMinimumSystemVersion') != manifest.get('minimum_macos_version'):
        raise ValueError('App/runtime OS minimums differ')
    if not os.access(bundle / 'Contents/MacOS/Rieke OS', os.X_OK):
        raise ValueError('App entry is not executable')
    escaping = []
    for file in bundle.rglob('*'):
        if file.is_symlink() and (os.path.isabs(os.readlink(file)) or not file.resolve().is_relative_to(bundle.resolve()) or not file.exists()):
            escaping.append(file.relative_to(bundle).as_posix())
    if escaping:
        raise ValueError('Complete app contains escaping/broken absolute links')
    dependency = json.loads((runtime / 'dependency-inventory.json').read_text())
    license_coverage=dependency.get('native_license_coverage',{})
    missing_notices=[package['name'] for package in dependency['native_packages']
                     if not license_coverage.get(package['name']) or
                     any(not (runtime/name).is_file() for name in license_coverage.get(package['name'],[]))]
    application = runtime / 'application'
    forbidden = [file.relative_to(runtime).as_posix() for file in application.rglob('*') if file.is_file() and
                 (file.suffix.lower() in {'.h5', '.hdf5', '.mat'} or file.name in {'native-credentials.json','catalog.json','project.json','native-runtime.json'} or '.git' in file.parts)]
    if forbidden:
        raise ValueError('Private project/data files entered application resources')
    python_paths = []
    for file in (runtime / 'python').rglob('*.pth'):
        for line in file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(('#', 'import ', 'import\t')):
                continue
            if Path(line).is_absolute() or not (file.parent / line).resolve().is_relative_to(runtime.resolve()):
                python_paths.append(file.relative_to(runtime).as_posix())
    if python_paths or list(runtime.rglob('pyvenv.cfg')):
        raise ValueError('Python has editable/external/venv path state')
    missing = [name for name in ('epicTreeGUI.m','src/loadEpicTreeData.m','src/buildTreeFromEpicData.m',
             'src/tree/epicTreeTools.m','src/tree/launchWorkspaceTree.m','src/tree/readWorkspaceTags.m',
             'src/tree/validateWorkspaceTags.m','src/tree/workspaceTag.m','src/tree/writeWorkspaceTags.m')
             if not (application / name).is_file()]
    signature = subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(bundle)], capture_output=True)
    shell_paths = ('Contents/Info.plist', 'Contents/MacOS/Rieke OS', 'Contents/Resources/app.asar',
                   'Contents/Frameworks/Electron Framework.framework/Versions/A/Electron Framework')
    shell_hashes = {name:digest(bundle / name).hex() for name in shell_paths}
    return {'manifest_sha256':digest(runtime/'runtime-manifest.json').hex(), 'runtime_resources':len(actual),
            'shell_resource_sha256':shell_hashes,
            'internal_links':sum('symlink' in entry for entry in actual.values()),
            'python_distributions':len(dependency['python_distributions']), 'native_packages':len(dependency['native_packages']),
            'native_license_texts':len(dependency['native_license_files']),
            'native_packages_missing_license_coverage':missing_notices,
            'minimum_macos_version':manifest['minimum_macos_version'],
            'excluded_optional_features':manifest.get('excluded_optional_features',[]),
            'development_paths_in_operational_python_paths':[], 'private_application_data_files':[],
            'missing_matlab_export_resources':missing,
            'developer_id_qualified':False, 'codesign_structural_verification':signature.returncode==0,
            'source_dirty':manifest.get('source_dirty'), 'application_version':manifest['application_version']}, manifest


NETWORK_GUARD = r'''
import ipaddress,socket
_original_connect=socket.socket.connect
_original_ex=socket.socket.connect_ex
def _allowed(sock,address):
    if sock.family == socket.AF_UNIX: return
    host=address[0]
    if host == 'localhost':return
    try:
        if ipaddress.ip_address(host).is_loopback:return
    except ValueError:pass
    raise OSError('Artifact test denies non-loopback network access')
def connect(sock,address):
    _allowed(sock,address);return _original_connect(sock,address)
def connect_ex(sock,address):
    _allowed(sock,address);return _original_ex(sock,address)
socket.socket.connect=connect
socket.socket.connect_ex=connect_ex
_original_resolver=socket.getaddrinfo
def getaddrinfo(host,*args,**kwargs):
    if host not in (None,'localhost','127.0.0.1','::1'):
        try:
            if not ipaddress.ip_address(host).is_loopback:raise OSError('External DNS disabled')
        except ValueError:raise OSError('External DNS disabled')
    return _original_resolver(host,*args,**kwargs)
socket.getaddrinfo=getaddrinfo
'''

DATABASE_PROBE = r'''
import hashlib,json,os,sys,socket
from pathlib import Path
resources=Path(sys.argv[1]).resolve();runtime=resources/'runtime'
sys.path.insert(0,str(runtime/'application/python'))
os.environ['RIEKE_DESKTOP_RUNTIME']=str(runtime)
os.environ['RIEKE_INSTALLATION_ROOT']=str(Path.home()/'state')
try:socket.getaddrinfo('dependency-provider.invalid',443)
except OSError:pass
else:raise ValueError('External DNS guard was not enforced')
with socket.socket() as blocked:
    try:blocked.connect(('192.0.2.1',443))
    except OSError:pass
    else:raise ValueError('External connection guard was not enforced')
from workspace_bootstrap import prepare_desktop_parser_config,probe_runtime,validate_desktop_runtime
prepare_desktop_parser_config(Path.home()/'state')
validate_desktop_runtime(runtime,verify_hashes=True)
parser=probe_runtime(str(runtime/'python/bin/python3.11'),str(runtime/'parser'))
from workspace_projects import create_project
from workspace_native_mysql import ensure_native_database,stop_native_database,connection_parameters,native_binary
import pymysql,subprocess
project=Path(create_project(Path.home()/'projects','Artifact native restore',code_root=runtime/'application')['path'])
def connect():return pymysql.connect(**connection_parameters(project),autocommit=True)
def rows():
    with connect() as c:
        with c.cursor() as cursor:
            cursor.execute('SELECT id,amount,payload,JSON_EXTRACT(tags,"$.name") FROM `schema`.artifact_fixture ORDER BY id')
            return [(row[0],str(row[1]),row[2].hex(),row[3]) for row in cursor.fetchall()]
try:
    ensure_native_database(project)
    with connect() as c:
        with c.cursor() as cursor:
            cursor.execute('CREATE DATABASE `schema`')
            cursor.execute('CREATE TABLE `schema`.artifact_fixture(id INTEGER PRIMARY KEY,amount DECIMAL(20,8),payload BLOB,tags JSON)')
            cursor.executemany('INSERT INTO `schema`.artifact_fixture VALUES(%s,%s,%s,%s)',[(1,'1.23456789',bytes([0,1,255]),json.dumps({'name':'tag α'})),(2,'-9876.50000000',bytes(range(32)),json.dumps({'name':'tag β'})),(3,'0.00000001',b'',json.dumps({'name':'empty'}))])
    expected=rows()
    config=connection_parameters(project);env=dict(os.environ,MYSQL_PWD=config['password'])
    common=['--no-defaults','--protocol=TCP','--host=127.0.0.1','--port='+str(config['port']),'--user=root']
    dump=subprocess.check_output([str(native_binary('mysqldump')),*common,'--single-transaction','--skip-lock-tables','--no-tablespaces','--set-gtid-purged=OFF','--hex-blob','--skip-comments','--databases','schema'],env=env,timeout=60)
    backup=Path.home()/'database-backup.sql';backup.write_bytes(dump)
    stop_native_database(project)
    if json.loads((project/'database/native-owner.json').read_text()).get('clean_shutdown') is not True:raise ValueError('Initial clean shutdown not recorded')
    ensure_native_database(project)
    if rows()!=expected:raise ValueError('Restart changed exact decimal/binary/JSON values')
    with connect() as c:
        with c.cursor() as cursor:cursor.execute('DROP DATABASE `schema`')
    config=connection_parameters(project);env=dict(os.environ,MYSQL_PWD=config['password'])
    common=['--no-defaults','--protocol=TCP','--host=127.0.0.1','--port='+str(config['port']),'--user=root']
    subprocess.run([str(native_binary('mysql')),*common,'--binary-mode','--local-infile=0'],input=dump,env=env,check=True,capture_output=True,timeout=60)
    if rows()!=expected:raise ValueError('Logical restore changed exact decimal/binary/JSON values')
    print('RIEKE_ARTIFACT_DATABASE='+json.dumps({'parser':parser,'mysql_restart':'passed','logical_backup_restore':'passed','fixture_rows':len(expected),'fixture_values_sha256':hashlib.sha256(json.dumps(expected).encode()).hexdigest(),'backup_sha256':hashlib.sha256(dump).hexdigest(),'external_dns_and_connections_denied':True,'development_path_excluded':True,'fresh_home':True}))
finally:stop_native_database(project)
validate_desktop_runtime(runtime,verify_hashes=True)
'''


def isolated_database_probe(resources, scratch):
    home=scratch/'isolated HOME with spaces';home.mkdir()
    guard=scratch/'no external network';guard.mkdir()
    (guard/'sitecustomize.py').write_text(NETWORK_GUARD)
    env={'HOME':str(home),'TMPDIR':str(scratch),'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1',
         'PYTHONNOUSERSITE':'1','PYTHONPATH':str(guard),'LANG':'en_US.UTF-8','MPLCONFIGDIR':str(home/'matplotlib'),
         'HTTP_PROXY':'http://127.0.0.1:9','HTTPS_PROXY':'http://127.0.0.1:9','NO_PROXY':'localhost,127.0.0.1,::1'}
    result=execute([resources/'runtime/python/bin/python3.11','-B','-c',DATABASE_PROBE,resources],env=env,cwd=home,text=True,timeout=300)
    return json.loads(next(line.split('=',1)[1] for line in result.stdout.splitlines() if line.startswith('RIEKE_ARTIFACT_DATABASE=')))


def extracted_scientific_probe(resources, scratch, recording):
    """Reuse real workflow assertions while forbidding external network/dependency access."""
    from desktop_backend_smoke import run as backend_run
    output=scratch/'extracted-backend-smoke.json'
    guard=scratch/'scientific network guard';guard.mkdir()
    (guard/'sitecustomize.py').write_text(NETWORK_GUARD)
    original=subprocess.Popen
    def guarded_spawn(*arguments,**options):
        env=dict(options.get('env') or os.environ)
        env.update(PYTHONPATH=str(guard),HTTP_PROXY='http://127.0.0.1:9',HTTPS_PROXY='http://127.0.0.1:9',
                   NO_PROXY='localhost,127.0.0.1,::1')
        options['env']=env
        return original(*arguments,**options)
    try:
        subprocess.Popen=guarded_spawn
        backend_run(resources,output,recording=recording)
    finally:subprocess.Popen=original
    return json.loads(output.read_text())


def expected_rejection(name, action, results):
    try:action()
    except Exception as error:
        results.append({'case':name,'rejected':True,'error_type':type(error).__name__})
    else:raise ValueError('Fault accepted: '+name)


def fault_checks(directory, manifest, scratch, bundle):
    faults=[]
    expected_rejection('foreign publication repository',lambda:baseline('v'+manifest['application_version'],'untrusted/repository'),faults)
    expected_rejection('dirty or unreviewed source baseline',lambda:baseline('v'+manifest['application_version'],'maxwellsdm1867/Rieke-OS'),faults)
    artifacts=artifact_inventory(directory)
    evidence={'format':'rieke-desktop-qualification','version':1,'application_version':manifest['application_version'],
              'platform':'darwin','architecture':'arm64','source_commit':manifest['source_commit'],'artifacts':artifacts,'requirements':{}}
    expected_rejection('missing R01-R12 qualification',lambda:validate_evidence(evidence,artifacts,manifest['application_version']),faults)
    wrong=copy.deepcopy(evidence);wrong['artifacts']={}
    expected_rejection('qualification exact artifact hash mismatch',lambda:validate_evidence(wrong,artifacts,manifest['application_version']),faults)
    faultdir=scratch/'metadata faults';faultdir.mkdir()
    for file in directory.iterdir():
        if file.is_file() and file.suffix in ('.zip','.dmg','.blockmap'):os.link(file,faultdir/file.name)
    original=(directory/'latest-mac.yml').read_text()
    variants={'wrong metadata version':original.replace('version: '+manifest['application_version'],'version: 9.9.9'),
              'metadata checksum corruption':original.replace('sha512:','sha512: invalid',1),
              'unsafe metadata artifact path':original.replace('url: Rieke-OS','url: ../Rieke-OS',1),
              'metadata size mismatch':original.replace('size:','size: 1 #',1)}
    for name,text in variants.items():
        (faultdir/'latest-mac.yml').write_text(text)
        expected_rejection(name,lambda:verify_metadata(faultdir,manifest['application_version']),faults)
    missing_dmg = next(faultdir.glob('*.dmg'))
    missing_dmg.unlink()
    expected_rejection('incomplete release artifact set', lambda:artifact_inventory(faultdir), faults)
    damaged_zip=scratch/'actual candidate CRC corruption.zip'
    execute(['/bin/cp','-c',next(directory.glob('*.zip')),damaged_zip])
    import struct
    with zipfile.ZipFile(damaged_zip) as archive:
        entry=next(item for item in archive.infolist() if item.filename.endswith('/Contents/Info.plist'))
    with damaged_zip.open('r+b') as handle:
        handle.seek(entry.header_offset)
        header=handle.read(30)
        filename_length,extra_length=struct.unpack_from('<HH',header,26)
        offset=entry.header_offset+30+filename_length+extra_length+entry.compress_size//2
        handle.seek(offset);byte=handle.read(1);handle.seek(offset);handle.write(bytes([byte[0]^0x80]))
    def crc_check():
        with zipfile.ZipFile(damaged_zip) as archive:
            archive.read(entry.filename)
    expected_rejection('corrupted actual candidate ZIP payload', crc_check, faults)
    damaged_zip.unlink()
    javascript=r'''
const fs=require('fs'),p=require('path');const v=require(process.argv[1]);
const current=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const good={...current,source_dirty:false,application_version:'0.1.1'};const tests=[];
function reject(name,fn){try{fn();throw new Error('accepted')}catch(e){if(e.message==='accepted')throw e;tests.push({case:name,rejected:true});}}
reject('dirty candidate provenance',()=>v.compatibleCandidate({...good,source_dirty:true},current,'0.1.1'));
reject('incompatible database',()=>v.compatibleCandidate({...good,database_compatibility:999},current,'0.1.1'));
reject('incompatible workspace',()=>v.compatibleCandidate({...good,workspace_formats:[999]},current,'0.1.1'));
reject('wrong native architecture',()=>v.compatibleCandidate({...good,architecture:'x64'},current,'0.1.1'));
reject('older candidate version',()=>v.compatibleCandidate({...good,application_version:'0.0.9'},current,'0.0.9'));
reject('unsupported host OS',()=>v.compatibleMacMinimum('15.0','14.2'));
reject('runtime traversal path',()=>v.safeResource('/tmp','../escape'));
(async()=>{try{await v.signingIdentity(process.argv[3]);throw Error('unsigned app accepted')}catch(e){if(e.message==='unsigned app accepted')throw e;tests.push({case:'unsigned real app rejected by update signing gate',rejected:true});}
const installer=require(process.argv[4]);try{await installer.installCompleteBundle({source:process.argv[3],destination:p.join(process.argv[5],'must not install','Rieke OS.app')});throw Error('unsigned install accepted')}catch(e){if(e.message==='unsigned install accepted')throw e;tests.push({case:'unsigned real app rejected by first-open signed installer',rejected:true});}
process.stdout.write(JSON.stringify(tests));})();
'''
    result=execute(['node','-e',javascript,ROOT/'desktop/updater-validation.cjs',bundle/'Contents/Resources/runtime/runtime-manifest.json',bundle,ROOT/'desktop/bootstrap.cjs',scratch],text=True)
    faults.extend(json.loads(result.stdout))
    runtime=bundle/'Contents/Resources/runtime'
    verify="const v=require(process.argv[1]),fs=require('fs');v.verifyResources(process.argv[2],JSON.parse(fs.readFileSync(process.argv[3],'utf8')).resources).catch(e=>{process.stderr.write(e.message);process.exitCode=1;})"
    def verify_corruption():
        execute(['node','-e',verify,ROOT/'desktop/updater-validation.cjs',runtime,runtime/'runtime-manifest.json'],text=True)
    extra=runtime/'.artifact-unexpected-file';extra.write_text('untracked resource')
    try:expected_rejection('unexpected actual runtime resource',verify_corruption,faults)
    finally:extra.unlink()
    target=runtime/'application/python/workspace_desktop.py';data=target.read_bytes()
    target.write_bytes(data+b'\n# corrupt scratch artifact only\n')
    try:expected_rejection('corrupted actual runtime code resource',verify_corruption,faults)
    finally:target.write_bytes(data)
    target=runtime/'python/bin/python3.11';mode=stat.S_IMODE(target.stat().st_mode);target.chmod(mode & ~0o111)
    try:expected_rejection('changed actual runtime executable permissions',verify_corruption,faults)
    finally:target.chmod(mode)
    target=runtime/'parser/src/retinanalysis';link=os.readlink(target);target.unlink();target.symlink_to(scratch)
    try:expected_rejection('escaping actual parser wheel symlink',verify_corruption,faults)
    finally:target.unlink();target.symlink_to(link)
    return faults


def run(args):
    directory=args.directory.resolve();reference=args.installed.resolve()
    scratch=Path(tempfile.mkdtemp(prefix="Rieke artifact audit ' unusual "))
    report={'format':'rieke-desktop-artifact-e2e','version':1,'production_ready':False,'local_host_only':True,
            'checks':[],'failures':[],'not_validated':['Developer ID signing/notarization','real signed old-to-new update',
            'another user/clean machine','minimum supported macOS 14.0 device','source-user migration']}
    report['installation_reference_kind']=('built-candidate' if reference == (ROOT/'desktop/dist/mac-arm64/Rieke OS.app').resolve()
                                           else 'provided-readonly-bundle')
    report['user_installation_updated']=False
    artifacts=artifact_inventory(directory);report['artifacts']=artifacts
    report['host_macos']=execute(['/usr/bin/sw_vers','-productVersion'],text=True).stdout.strip()
    bundles={}
    try:
        zipfile_path=next(directory.glob('*.zip'));dmg=next(directory.glob('*.dmg'))
        script="process.stdout.write(require(process.argv[1]).ARCHIVE_CHECK)"
        check=execute(['node','-e',script,ROOT/'desktop/updater-validation.cjs'],text=True).stdout
        execute([sys.executable,'-c',check,zipfile_path],timeout=60)
        report['checks'].append('actual updater ZIP path/link/bounds audit')
        ziproot=scratch/"ZIP extracted ' relocated";ziproot.mkdir()
        execute(['/usr/bin/ditto','-x','-k',zipfile_path,ziproot],timeout=180)
        bundles['zip']=ziproot/'Rieke OS.app'
        execute(['/usr/bin/hdiutil','verify',dmg],timeout=180)
        mount=scratch/'read-only DMG mount';mount.mkdir()
        execute(['/usr/bin/hdiutil','attach','-readonly','-nobrowse','-mountpoint',mount,dmg],timeout=180)
        try:
            dmgroot=scratch/'DMG copied relocated';dmgroot.mkdir()
            execute(['/usr/bin/ditto','--rsrc','--extattr','--acl',mount/'Rieke OS.app',dmgroot/'Rieke OS.app'],timeout=180)
            bundles['dmg']=dmgroot/'Rieke OS.app'
        finally:execute(['/usr/bin/hdiutil','detach',mount],timeout=30)
        report['checks'].append('actual DMG integrity/mount/copy preserving bundle')
        bundles['reference']=reference
        inspections={};manifests={}
        for name,bundle in bundles.items():
            inspections[name],manifests[name]=inspect_bundle(bundle)
            if inspections[name]['missing_matlab_export_resources']:
                report['failures'].append({'case':name+' MATLAB export closure','missing':inspections[name]['missing_matlab_export_resources']})
            if inspections[name]['native_packages_missing_license_coverage']:
                report['failures'].append({'case':name+' native license coverage',
                                          'missing':inspections[name]['native_packages_missing_license_coverage']})
        report['bundles']=inspections
        if len({item['manifest_sha256'] for item in inspections.values()})!=1:
            raise ValueError('DMG/ZIP/reference runtime manifests differ')
        if any(item['shell_resource_sha256']!=inspections['zip']['shell_resource_sha256'] for item in inspections.values()):
            raise ValueError('DMG/ZIP/reference Electron shell bytes differ')
        report['checks'].append('DMG/ZIP/read-only reference exact resources, modes, versions and contained links')
        audit=native_audit(bundles['zip']/'Contents/Resources/runtime');report['native_audit']=audit
        if audit['problems']:raise ValueError('Artifact native closure is external or incomplete')
        report['checks'].append('all packaged native load paths resolve privately or to macOS system libraries')
        verify_metadata(directory,manifests['zip']['application_version'])
        report['checks'].append('final updater YAML SHA512/size matches exact ZIP/DMG bytes')
        report['faults']=fault_checks(directory,manifests['zip'],scratch,bundles['zip'])
        report['checks'].append('baseline/metadata/compatibility/signature fault rejections')
        before=inventory(bundles['zip']/'Contents/Resources/runtime')
        report['bundled_database']=isolated_database_probe(bundles['zip']/'Contents/Resources',scratch)
        report['checks'].append('extracted bundled parser +native MySQL decimal/blob/JSON restart and logical backup/restore under isolated HOME/PATH/network guard')
        report['resources_unchanged_after_native_workflow']=before==inventory(bundles['zip']/'Contents/Resources/runtime')
        if not report['resources_unchanged_after_native_workflow']:raise ValueError('Native workflow changed artifact resources')
        if args.recording:
            report['extracted_scientific_backend']=extracted_scientific_probe(bundles['dmg']/'Contents/Resources',scratch,args.recording)
            report['checks'].append('DMG-extracted real H5 import/tag/query/export/restart/drain and resource invariance')
        if artifact_inventory(directory)!=artifacts:raise ValueError('Read-only tests changed published artifact bytes')
        report['checks'].append('distribution artifact bytes unchanged after testing')
    except (Exception,SystemExit) as error:
        message=str(error)[:500] if isinstance(error,ValueError) else 'Scratch subprocess check failed; private local diagnostics retained.'
        report['failures'].append({'case':'artifact test exception','error_type':type(error).__name__,'message':message})
        # Private failure diagnostics stay local and never enter release evidence.
        detail={'error':repr(error)}
        for key in ('stdout','stderr'):
            data=getattr(error,key,None)
            if data:
                detail[key]=data.decode(errors='replace') if isinstance(data,bytes) else data
        (scratch/'private-error.txt').write_text(json.dumps(detail,indent=2))
    report['passed']=not report['failures']
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if report['passed'] and not args.keep_scratch:shutil.rmtree(scratch)
    else:print('Private scratch retained:',scratch)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=ROOT/'desktop/dist')
    parser.add_argument('--installed',type=Path,default=Path.home()/'Applications/Rieke OS.app')
    parser.add_argument('--recording',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/dev/desktop-artifact-e2e.json')
    parser.add_argument('--keep-scratch',action='store_true')
    raise SystemExit(run(parser.parse_args()))
