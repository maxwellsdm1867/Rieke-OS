"""Set up Rieke Lab OS, initialize workspace storage, and launch the chooser.

macOS/Linux only (the application uses POSIX process and file locking). Setup
requires git, uv, Node/npm and a C++ compiler. Setup, init and doctor never
start a database; opening a project in the launched app prepares its service.
"""
from __future__ import annotations
import argparse
import configparser
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from workspace_mysql_runtime import install_mysql_runtime, mysql_runtime

ROOT = Path(__file__).resolve().parents[1]


def source_spec(root=ROOT):
    return json.loads((Path(root) / 'python/workspace-source.json').read_text())


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def captured(args, timeout=30):
    return run(args, capture_output=True, text=True, timeout=timeout).stdout.strip()


def verify_checkout(checkout, spec):
    checkout = Path(checkout).resolve(strict=True)
    if captured(['git', '-C', checkout, 'rev-parse', 'HEAD']) not in [spec['commit'], *spec.get('compatible_local_commits', [])]:
        raise ValueError('RetinAnalysis revision differs from workspace-source.json; use the pinned checkout.')
    dirty = captured(['git', '-C', checkout, 'status', '--porcelain', '--untracked-files=no', '--ignore-submodules=none'])
    if dirty:
        raise ValueError('RetinAnalysis or its submodule has tracked changes; setup will not overwrite them.')
    module = checkout / spec['submodule']
    if captured(['git', '-C', module, 'rev-parse', 'HEAD']) != spec['submodule_commit']:
        raise ValueError('RetinAnalysis vision-utils submodule does not match the pinned revision.')
    if not (checkout / spec['utilities'] / 'setup.py').is_file():
        raise ValueError('RetinAnalysis vision-utils build source is missing.')
    return checkout


def write_compatibility_config(checkout, runtime):
    """Provide existing empty paths required by upstream imports, not data roots.

    Explicit checkouts keep existing configuration untouched. New managed
    checkouts use isolated empty directories; application imports pass their own
    project-specific source/catalog paths and never call bulk populate_database.
    """
    target = Path(checkout) / 'src/retinanalysis/config/config.ini'
    if target.exists():
        return False
    base = Path(runtime).resolve() / 'compatibility-data'
    values = {'user': getpass.getuser()}
    for key in ('analysis', 'data', 'raw', 'h5', 'meta', 'tags', 'query'):
        directory = base / key
        directory.mkdir(parents=True, exist_ok=True)
        values[key] = str(directory)
    config = configparser.ConfigParser(interpolation=None)
    config['DEFAULT'] = values
    for name in ('SECONDARY', 'LINUX_DEFAULT', 'LINUX_SECONDARY', 'WINDOWS_DEFAULT', 'WINDOWS_SECONDARY'):
        config[name] = values
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x') as handle:
        config.write(handle)
    return True


def runtime_paths(root=ROOT, environ=None):
    root = Path(root).resolve()
    env = os.environ if environ is None else environ
    if env.get('RIEKE_DESKTOP_RUNTIME'):
        runtime = Path(env['RIEKE_DESKTOP_RUNTIME']).resolve(strict=True)
        validate_desktop_runtime(runtime)
        managed = env.get('RECORDING_WORKSPACE_ROOT') or str(Path.home() / 'Documents/RecordingWorkspace')
        return {'python': str(runtime / 'python/bin/python3.11'),
                'retinanalysis': str(runtime / 'parser'), 'managed_root': str(Path(managed).expanduser().resolve())}
    config_path = root / '.rieke-runtime/runtime.json'
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())
        if not isinstance(config, dict) or type(config.get('version')) is not int or config.get('version') != 1:
            raise ValueError('Invalid runtime configuration; rerun python3 rieke.py setup.')
    for key in ('python', 'retinanalysis', 'managed_root'):
        if key in config and (not isinstance(config[key], str) or not config[key].strip()):
            raise ValueError(f'Invalid runtime {key}; rerun python3 rieke.py setup.')
    def path(value):
        value = Path(value).expanduser()
        return str(value if value.is_absolute() else root / value)
    checkout = path(env.get('RETINANALYSIS_DIR') or config.get('retinanalysis') or '.rieke-runtime/retinanalysis')
    python = path(env.get('RECORDING_PYTHON') or config.get('python') or '.rieke-runtime/venv/bin/python')
    preference_root = Path(env['RIEKE_INSTALLATION_ROOT']) / 'preferences' if env.get('RIEKE_INSTALLATION_ROOT') else root / '.rieke-runtime'
    selected_path = preference_root / 'workspace-selection.json'
    selected = {}
    if selected_path.exists():
        selected = json.loads(selected_path.read_text())
        if not isinstance(selected,dict) or type(selected.get('version')) is not int or selected['version'] != 1 or not isinstance(selected.get('managed_root'),str) or not selected['managed_root'].strip():
            raise ValueError('Invalid saved workspace selection')
    managed = env.get('RECORDING_WORKSPACE_ROOT') or selected.get('managed_root') or config.get('managed_root')
    if not env.get('RECORDING_WORKSPACE_ROOT') and selected.get('managed_root'):
        saved = Path(path(selected['managed_root']))
        if not saved.is_dir():
            raise ValueError('Saved workspace is unavailable. Locate the moved workspace or explicitly choose a different workspace root.')
    if not managed:
        managed = str(Path(env['RECORDING_PROJECT_DIR']).expanduser().resolve().parent) if env.get('RECORDING_PROJECT_DIR') else str(Path.home() / 'Documents/RecordingWorkspace')
    return {'python': python, 'retinanalysis': checkout, 'managed_root': path(managed)}


PROBE = r'''
import importlib, importlib.metadata as md, importlib.util, json, os, pathlib, sys
checkout=pathlib.Path(sys.argv[1]).resolve()
assert sys.version_info[:2] == (3,11), 'The locked runtime requires Python 3.11'
import retinanalysis
assert pathlib.Path(retinanalysis.__file__).resolve().parent == (checkout/'src/retinanalysis').resolve(), 'Installed RetinAnalysis does not match the selected parser checkout or wheel'
if os.environ.get('RIEKE_DESKTOP_RUNTIME'):
    assert pathlib.Path(retinanalysis.__file__).resolve().is_relative_to(pathlib.Path(os.environ['RIEKE_DESKTOP_RUNTIME']).resolve()), 'Parser wheel escapes desktop resources'
for module in ('flask','datajoint','h5py','hdf5storage','numpy','scipy','bin2py'):
    importlib.import_module(module)
assert md.version('datajoint') == '2.2.2', 'DataJoint must be 2.2.2'
spec=importlib.util.spec_from_file_location('bootstrap_parser',checkout/'src/retinanalysis/utils/parse_data.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
print('RIEKE_PROBE='+json.dumps({'python':sys.version.split()[0],'datajoint':md.version('datajoint'),'parser_import':'ok'}))
'''


def prepare_desktop_parser_config(user_state):
    """Create import compatibility paths only in writable, private user state."""
    state = Path(user_state).expanduser().resolve()
    target = state / 'parser/config.ini'
    runtime_value = os.environ.get('RIEKE_DESKTOP_RUNTIME')
    if runtime_value and (state.is_relative_to(Path(runtime_value).resolve()) or Path(runtime_value).resolve().is_relative_to(state)):
        raise ValueError('Parser user state must be separate from signed application resources')
    if target.is_symlink() or not target.resolve().is_relative_to(state):
        raise ValueError('Parser configuration redirects outside private user state')
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        values = {'user': getpass.getuser()}
        for key in ('analysis', 'data', 'raw', 'h5', 'meta', 'tags', 'query'):
            directory = state / 'parser/compatibility-data' / key
            if not directory.resolve().is_relative_to(state):
                raise ValueError('Parser compatibility paths redirect outside private user state')
            directory.mkdir(parents=True, exist_ok=True)
            values[key] = str(directory)
        config = configparser.ConfigParser(interpolation=None)
        config['DEFAULT'] = values
        for name in ('SECONDARY', 'LINUX_DEFAULT', 'LINUX_SECONDARY', 'WINDOWS_DEFAULT', 'WINDOWS_SECONDARY'):
            config[name] = values
        with target.open('x') as handle:
            config.write(handle)
        target.chmod(0o600)
    os.environ['RIEKE_PARSER_CONFIG'] = str(target)
    return target


def validate_desktop_runtime(runtime, verify_hashes=False):
    """Validate resource identity; signed app authority is enforced by Electron/macOS."""
    runtime = Path(runtime).resolve(strict=True)
    manifest = json.loads((runtime / 'runtime-manifest.json').read_text())
    if (manifest.get('format') != 'rieke-desktop-runtime' or manifest.get('version') != 1
            or manifest.get('platform') != sys.platform or manifest.get('architecture') != os.uname().machine):
        raise ValueError('Desktop runtime manifest format or platform is incompatible')
    release = json.loads((runtime / 'application/rieke-release.json').read_text())
    source = json.loads((runtime / 'application/python/workspace-source.json').read_text())
    expected = {'application_version': release['version'], 'workspace_formats': release['workspace_formats'],
                'database_compatibility': release['database_compatibility'],
                'parser_commit': source['commit'], 'python_version': source['python']}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError('Packaged runtime versions differ from application compatibility declarations')
    resources = manifest.get('resources')
    if not isinstance(resources, dict) or not resources:
        raise ValueError('Packaged runtime has no resource inventory')
    for name in ('python/bin/python3.11', 'mysql/bin/mysqld', 'application/python/workspace_desktop.py', 'frontend/index.html'):
        if not (runtime / name).is_file() or name not in resources:
            raise ValueError(f'Required packaged resource is absent: {name}')
    if verify_hashes:
        actual_names = {path.relative_to(runtime).as_posix() for path in runtime.rglob('*')
                        if (path.is_symlink() or path.is_file())
                        and path.relative_to(runtime).as_posix() not in ('runtime-manifest.json', 'runtime-audit.json')}
        if actual_names != set(resources):
            raise ValueError('Packaged runtime resource inventory has unexpected or missing files')
        for name, entry in resources.items():
            path = runtime / name
            if Path(name).is_absolute() or not path.resolve().is_relative_to(runtime):
                raise ValueError('Resource inventory path escapes desktop resources')
            if 'symlink' in entry:
                if not path.is_symlink() or os.readlink(path) != entry['symlink']:
                    raise ValueError(f'Packaged resource link mismatch: {name}')
            else:
                if path.is_symlink() or not path.is_file():
                    raise ValueError(f'Packaged resource is missing or redirected: {name}')
                with path.open('rb') as handle:
                    actual = hashlib.file_digest(handle, 'sha256').hexdigest()
                if actual != entry.get('sha256') or path.stat().st_size != entry.get('size'):
                    raise ValueError(f'Packaged resource hash mismatch: {name}')
    return manifest


def probe_runtime(python, checkout):
    output = captured([python, '-c', PROBE, checkout], timeout=120)
    lines = [line for line in output.splitlines() if line.startswith('RIEKE_PROBE=')]
    if not lines:
        raise ValueError('Backend import check returned no readiness receipt')
    return json.loads(lines[-1].split('=', 1)[1])


def supported_node(version):
    parts = tuple(int(x) for x in version.strip().lstrip('v').split('.')[:3])
    return len(parts) == 3 and ((parts[0] == 20 and parts >= (20, 19, 0)) or parts >= (22, 12, 0))


def doctor(root=ROOT, environ=None):
    checks = []
    def check(name, fn, required=True):
        try:
            detail = fn()
            checks.append({'check': name, 'ok': True, 'required': required, 'detail': detail})
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            detail = str(error)
            if isinstance(error, subprocess.CalledProcessError) and error.stderr:
                # Import diagnostics contain no configured database credentials.
                detail = error.stderr[-3000:]
            checks.append({'check': name, 'ok': False, 'required': required, 'detail': detail})
    paths = runtime_paths(root, environ)
    env = os.environ if environ is None else environ
    managed = bool(env.get('RIEKE_INSTALLATION_ROOT'))
    def platform_check():
        if sys.platform not in ('darwin','linux'):
            raise ValueError('Managed launcher supports macOS/Linux; Windows needs a Linux environment.')
        return sys.platform
    check('platform', platform_check)
    def node_check():
        version = captured(['node','--version'])
        if not supported_node(version):
            raise ValueError('Node 20.19+ (20.x) or 22.12+ is required by Vite')
        return version
    if not managed:
        check('node', node_check)
        check('npm', lambda: captured(['npm','--version']))
    def frontend_check():
        package = Path(root) / 'workspace-app/node_modules/vite/package.json'
        if not package.is_file():
            raise ValueError('Frontend dependencies are missing; rerun setup or npm ci in workspace-app.')
        return json.loads(package.read_text())['version']
    def built_frontend():
        if not (Path(root) / 'workspace-app/dist/index.html').is_file():
            raise ValueError('Installed frontend assets are missing; restage this release')
        return 'prebuilt frontend ready'
    check('frontend_assets' if managed else 'frontend_dependencies', built_frontend if managed else frontend_check)
    def parser_receipt():
        receipt = json.loads((Path(root) / '.rieke-runtime/runtime.json').read_text())
        if receipt.get('retinanalysis_commit') != source_spec(root)['commit']:
            raise ValueError('Installed parser receipt differs from the release pin')
        return receipt['retinanalysis_commit']
    check('pinned_parser', parser_receipt if managed else lambda: str(verify_checkout(paths['retinanalysis'], source_spec(root))))
    check('backend_imports', lambda: probe_runtime(paths['python'], paths['retinanalysis']))
    check('native_mysql', lambda: mysql_runtime(root), required=False)
    return {'ready': all(row['ok'] for row in checks if row['required']),
            'project_open_ready': all(row['ok'] for row in checks),
            'paths': paths, 'checks': checks,
            'note': 'Readiness checks do not open SQL, import recordings, or start database services. MySQL is bundled privately with the app.'}


def setup(root=ROOT, *, checkout=None, managed_root=None):
    root = Path(root).resolve()
    if sys.platform not in ('darwin','linux'):
        raise ValueError('Setup supports macOS/Linux (POSIX locking is required).')
    for tool in ('git','uv','node','npm'):
        if not shutil.which(tool):
            raise ValueError(f'{tool} is required on PATH. See workspace-app/README.md setup prerequisites.')
    if not (shutil.which('c++') or shutil.which('clang++') or shutil.which('g++')):
        raise ValueError('Install a C++ compiler (Xcode Command Line Tools or build-essential) for vision-utils.')
    if not supported_node(captured(['node','--version'])):
        raise ValueError('Install Node 20.19+ (20.x) or 22.12+ before setup.')
    if managed_root:
        location = Path(managed_root).expanduser().resolve()
        if location.is_relative_to(root) or root.is_relative_to(location):
            raise ValueError('Managed projects must be separate from the application checkout.')
    runtime = root / '.rieke-runtime'
    if runtime.is_symlink():
        raise ValueError('Runtime directory cannot be a symbolic link.')
    runtime.mkdir(exist_ok=True)
    spec = source_spec(root)
    selected = Path(checkout).expanduser().resolve() if checkout else runtime / 'retinanalysis'
    if not selected.exists():
        if checkout:
            raise ValueError('Explicit RetinAnalysis checkout does not exist.')
        run(['git','clone',spec['repository'],selected])
        run(['git','-C',selected,'checkout','--detach',spec['commit']])
        run(['git','-C',selected,'submodule','update','--init','--recursive'])
    selected = verify_checkout(selected, spec)
    write_compatibility_config(selected, runtime)
    environment = runtime / 'venv'
    if environment.is_symlink():
        raise ValueError('Runtime venv cannot be a symbolic link to another environment.')
    python = environment / 'bin/python'
    if not python.exists():
        run(['uv','venv','--python',spec['python'],environment])
    else:
        actual = captured([python,'-c','import sys; print(".".join(map(str,sys.version_info[:3])))'])
        if actual != spec['python']:
            raise ValueError('Existing runtime Python differs from the pinned version; choose a clean clone/runtime.')
    # Never sync or uninstall from a supplied scientist environment. This venv
    # belongs only to this clone, and every registry package is hash pinned.
    run(['uv','pip','install','--python',python,'--require-hashes','-r',root/'python/workspace-runtime.lock'])
    run(['uv','pip','install','--python',python,'--no-deps','--no-build-isolation','-e',selected,
         selected/spec['utilities']])
    run(['uv','pip','check','--python',python])
    probe_runtime(python, selected)
    run(['npm','ci'], cwd=root/'workspace-app')
    run(['npm','run','build'], cwd=root/'workspace-app')
    database_runtime = install_mysql_runtime(root)
    config = {'version':1, 'python':str(python.relative_to(root)),
              'retinanalysis':str(selected.relative_to(root)) if selected.is_relative_to(root) else str(selected),
              'retinanalysis_commit':captured(['git','-C',selected,'rev-parse','HEAD']),
              'mysql_runtime':str(Path(database_runtime['root']).relative_to(root))}
    if managed_root:
        location = Path(managed_root).expanduser().resolve()
        if location.is_relative_to(root) or root.is_relative_to(location):
            raise ValueError('Managed projects must be separate from the application checkout.')
        config['managed_root'] = str(location)
    with tempfile.NamedTemporaryFile('w',dir=runtime,delete=False) as handle:
        json.dump(config,handle,indent=2)
        temporary = Path(handle.name)
    temporary.replace(runtime/'runtime.json')
    return config


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    install=sub.add_parser('setup',help='Install source-pinned backend and locked frontend into this clone')
    install.add_argument('--retinanalysis',help='Use an explicit clean checkout at the pinned revision')
    install.add_argument('--managed-root',help='Keep projects outside this application checkout')
    inspect=sub.add_parser('doctor',help='Read-only readiness and dependency-origin checks')
    inspect.add_argument('--json',action='store_true')
    initialize=sub.add_parser('init',help='Create a workspace folder and its local launch command (no database)')
    initialize.add_argument('directory',type=Path)
    launch=sub.add_parser('launch',help='Build the UI and start the local project chooser')
    launch.add_argument('--workspace',type=Path,help='Initialized workspace; otherwise discover from the current directory')
    launch.add_argument('--port',type=int,default=8766,help='Local chooser port (default: 8766)')
    args=parser.parse_args(argv)
    try:
        if args.command == 'setup':
            setup(checkout=args.retinanalysis,managed_root=args.managed_root)
            print('Setup complete. Run python3 rieke.py doctor, then python3 rieke.py launch.')
        elif args.command == 'init':
            from workspace_installation import initialize_workspace
            folder=initialize_workspace(args.directory,ROOT)
            print(f'Workspace ready: {folder}\nRun python3 rieke-workspace.py from that folder.\nProjects are created in the chooser; databases start only when opened.')
        elif args.command == 'doctor':
            result=doctor()
            if args.json:
                print(json.dumps(result,indent=2))
            else:
                for row in result['checks']:
                    label='OK' if row['ok'] else ('MISSING' if row['required'] else 'OPTIONAL / NOT READY')
                    print(f"{label}: {row['check']}: {row['detail']}")
                print(result['note'])
            return 0 if result['ready'] else 1
        else:
            from workspace_installation import discover_workspace, read_workspace
            if not 1 <= args.port <= 65535:
                raise ValueError('Choose a port between 1 and 65535')
            workspace=read_workspace(args.workspace) if args.workspace else discover_workspace(Path.cwd())
            environment=dict(os.environ)
            if workspace:
                environment['RECORDING_WORKSPACE_ROOT']=str(workspace)
            environment['RIEKE_LAUNCHER_PORT']=str(args.port)
            if environment.get('RIEKE_INSTALLATION_ROOT'):
                readiness = doctor(ROOT, environment)
                if not readiness['ready']:
                    raise ValueError('Installed app is not ready; run doctor or restore the release')
                paths = readiness['paths']
                run([paths['python'], ROOT/'python/workspace_launcher.py', '--managed-root',
                     paths['managed_root'], '--retinanalysis', paths['retinanalysis'],
                     '--port',str(args.port)], cwd=ROOT, env=environment)
            else:
                run(['node',ROOT/'workspace-app/start.mjs'],cwd=ROOT,env=environment)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'Setup/launch stopped: {error}',file=sys.stderr)
        return 1
