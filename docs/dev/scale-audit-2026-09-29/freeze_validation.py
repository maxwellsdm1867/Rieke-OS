"""Capture checked source copies and validate that fixed snapshot, preserving evidence.

The snapshot is assembled in a temporary directory, checked against source hashes
before and after copying, then retained with results. No checkout/branch changes.
Only Python runtime binaries and node_modules are symlinked; application/parser
source is copied. External installed dependencies are hashed before/after use.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
AUDIT = HERE.relative_to(REPO)
IGNORED = {'__pycache__', '.git', '.pytest_cache', '.DS_Store'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def walk(folder, *, dependency=False):
    if not folder.exists():
        raise FileNotFoundError(folder)
    ignored = IGNORED | ({'.cache', '.vite', '.vite-temp'} if dependency else set())
    for current, directories, files in os.walk(folder, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in ignored)
        for name in sorted(files):
            path = Path(current) / name
            if name in ignored or path.suffix in {'.pyc', '.pyo'}:
                continue
            yield path
        for name in directories:
            path = Path(current) / name
            if path.is_symlink():
                # Do not silently omit a tree that may contain executed code.
                raise ValueError('Directory symlink requires explicit dependency handling: ' + str(path))


def source_inventory():
    paths = set()
    for folder in ('python', 'tools', 'tests', 'src', 'workspace-app/src', 'workspace-app/public'):
        paths.update(walk(REPO / folder))
    for path in (REPO / 'workspace-app').iterdir():
        if path.is_file():
            paths.add(path)
    for name in ('rieke-release.json', 'rieke.py', 'README.md', 'LICENSE', 'epicTreeGUI.m', 'install.m'):
        paths.add(REPO / name)
    paths.update(HERE.glob('*.py'))
    paths.update(HERE.glob('*.mjs'))
    parser_root = REPO / '.rieke-runtime/retinanalysis'
    paths.update(path for path in walk(parser_root) if path.suffix == '.py')
    paths.update(parser_root / name for name in ('pyproject.toml', 'LICENSE.txt'))
    result = {}
    for path in sorted(paths):
        if path.is_symlink():
            raise ValueError('Application/parser source must be copied from a regular file: ' + str(path))
        result[str(path.relative_to(REPO))] = digest(path)
    return result


def dependency_inventory(python_packages, node_modules, python_binary, node_binary):
    result = {'python_binary': digest(python_binary), 'node_binary': digest(node_binary), 'files': {}}
    for label, root in (('python_packages', python_packages), ('node_modules', node_modules)):
        for path in walk(root, dependency=True):
            entry = {'sha256': digest(path)}
            if path.is_symlink():
                target = path.resolve(strict=True)
                if not target.is_relative_to(root.resolve()):
                    raise ValueError('Dependency link escapes its recorded root: ' + str(path))
                entry['symlink_target'] = os.readlink(path)
            result['files'][label + '/' + str(path.relative_to(root))] = entry
    return result


def mysql_inventory(prefix):
    """Hash the explicitly reused native runtime, never a database directory."""
    values = {}
    for directory, folders, files in os.walk(prefix, followlinks=False):
        for name in sorted(files + [n for n in folders if (Path(directory) / n).is_symlink()]):
            path = Path(directory) / name
            relative = str(path.relative_to(prefix))
            if path.is_symlink():
                values[relative] = {'symlink': os.readlink(path)}
                if path.is_file():
                    values[relative]['sha256'] = digest(path)
            elif path.is_file():
                values[relative] = {'sha256': digest(path)}
    return values


def capture(output, retries):
    attempts = []
    for number in range(1, retries + 1):
        before = source_inventory()
        with tempfile.TemporaryDirectory(prefix='rieke-frozen-source-') as temporary:
            snapshot = Path(temporary) / 'snapshot'
            snapshot.mkdir()
            for name in before:
                destination = snapshot / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / name, destination)
            copied = {name: digest(snapshot / name) for name in before}
            after = source_inventory()
            changed = sorted(name for name in before.keys() | after.keys()
                             if before.get(name) != after.get(name) or copied.get(name) != before.get(name))
            attempts.append({'attempt': number, 'changed_paths': changed})
            if changed:
                print(f'Snapshot attempt {number} changed during copying; retrying', flush=True)
                continue
            destination = output / 'snapshot'
            shutil.move(str(snapshot), destination)
            # Check the retained files too, including any cross-filesystem move.
            if {name: digest(destination / name) for name in before} != before:
                raise ValueError('Retained snapshot differs from its checked source copy')
            return destination, before, attempts
    write_json(output / 'snapshot-rejected.json', {'attempts': attempts, 'release_ready': False})
    raise RuntimeError('Could not capture a stable source snapshot within the retry limit')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs', type=int, default=100000)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--copy-attempts', type=int, default=3)
    parser.add_argument('--native-dense', action='store_true',
                        help='Also run the disposable native 5-tag API/backup benchmark against copied application source')
    parser.add_argument('--physical-manifest', type=Path,
                        help='Read-only imported recording manifest for the ancestor-metadata round-trip oracle')
    parser.add_argument('--physical-block', help='Exact block UUID to verify with --physical-manifest')
    args = parser.parse_args()
    if not 100 <= args.epochs <= 1000000 or not 1 <= args.copy_attempts <= 5:
        parser.error('epochs must be 100–1000000; copy-attempts must be 1–5')
    if bool(args.physical_manifest) != bool(args.physical_block):
        parser.error('physical-manifest and physical-block must be provided together')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)  # Preserve every earlier run.
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    print('Capturing checked source snapshot', flush=True)
    snapshot, hashes, attempts = capture(output, args.copy_attempts)
    python_binary = Path(sys.executable).resolve(strict=True)
    node_binary = Path(shutil.which('node') or '').resolve(strict=True)
    python_packages = Path(sys.prefix) / f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages'
    node_modules = REPO / 'workspace-app/node_modules'
    if not python_packages.is_dir() or not node_binary.is_file():
        raise ValueError('Run with the installed project venv and Node runtime')

    # A minimal isolated venv avoids executing installed editable .pth files that
    # point at live application/parser source. Packages are on PYTHONPATH directly.
    venv = snapshot / '.rieke-runtime/venv'
    (venv / 'bin').mkdir(parents=True)
    (venv / f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages').mkdir(parents=True)
    (venv / 'pyvenv.cfg').write_text(f'home = {python_binary.parent}\ninclude-system-site-packages = false\nversion = {sys.version.split()[0]}\n')
    for name in ('python', 'python3', f'python{sys.version_info.major}.{sys.version_info.minor}'):
        (venv / 'bin' / name).symlink_to(python_binary)
    (snapshot / 'workspace-app/node_modules').symlink_to(node_modules, target_is_directory=True)
    runtime_bin = output / 'runtime-bin'
    runtime_bin.mkdir()
    (runtime_bin / 'node').symlink_to(node_binary)
    env = dict(os.environ)
    env.pop('PYTHONHOME', None)
    env.pop('NODE_PATH', None)
    env.pop('NODE_OPTIONS', None)
    env['PYTHONPATH'] = os.pathsep.join(map(str, [snapshot / 'python', snapshot / 'python/tests',
        snapshot / '.rieke-runtime/retinanalysis/src', python_packages]))
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONNOUSERSITE'] = '1'
    env['PATH'] = str(runtime_bin) + os.pathsep + env.get('PATH', '')
    # This runner certifies the explicitly implemented disposable gates only.
    # Never inherit opt-in flags that could start a native integration workload.
    disabled_opt_ins = {key: env.pop(key) for key in list(env) if key.startswith('RIEKE_TEST_')}
    interpreter = venv / 'bin/python'
    probe = subprocess.run([str(interpreter), '-c',
        'import sys,json,importlib.util,importlib.metadata; '
        'print(json.dumps({"python":sys.version,"prefix":sys.prefix,"sys_path":sys.path,'
        '"modules":{n:importlib.util.find_spec(n).origin for n in '
        '["workspace_service","retinanalysis","h5py","bin2py"]},'
        '"packages":sorted((d.metadata["Name"],d.version) for d in importlib.metadata.distributions())}))'],
        cwd=snapshot, env=env, text=True, capture_output=True, check=True)
    runtime = json.loads(probe.stdout)
    for name in ('workspace_service', 'retinanalysis'):
        if not Path(runtime['modules'][name]).is_relative_to(snapshot):
            raise ValueError('Snapshot resolved live application code: ' + name)
    runtime['node_version'] = subprocess.check_output([str(node_binary), '--version'], text=True).strip()
    runtime['external_roots'] = {'python_packages': str(python_packages), 'node_modules': str(node_modules),
                                 'python_binary': str(python_binary), 'node_binary': str(node_binary)}
    runtime['disabled_native_test_flags'] = sorted(disabled_opt_ins)
    print('Hashing external dependency files before validation', flush=True)
    dependencies = dependency_inventory(python_packages, node_modules, python_binary, node_binary)
    write_json(output / 'dependencies.json', dependencies)
    write_json(output / 'runtime.json', runtime)
    manifest = {'original_root': str(REPO), 'snapshot_root': str(snapshot), 'started_at': started,
        'source_sha256': hashes, 'source_manifest_sha256': checksum(hashes), 'copy_attempts': attempts,
        'dependency_manifest_sha256': checksum(dependencies),
        'mapping': 'Every source_sha256 key maps original_root/key to snapshot_root/key; all are copied regular files.',
        'external_dependencies': 'Installed Python packages and Node modules are reused and checked before/after; editable .pth files are not executed.',
        'coherence_limit': 'Equal inventories before/after copying and copied-file hashes establish an observed stable capture; this is not an operating-system transactional filesystem snapshot.'}
    write_json(output / 'source-manifest.json', manifest)
    mysql_root = None
    mysql_before = None
    if args.native_dense:
        sys.path.insert(0, str(REPO / 'python'))
        from workspace_mysql_runtime import mysql_runtime
        mysql_root = Path(mysql_runtime(root=REPO)['root']).resolve()
        mysql_before = mysql_inventory(mysql_root)
        write_json(output / 'native-runtime.json', {'root': str(mysql_root), 'files': mysql_before,
            'scope': 'Runtime executables/assets reused; all app/parser source comes from the copied snapshot. Database is newly created and destroyed by the harness.'})
    gates = output / 'gates'
    command = [str(interpreter), str(snapshot / AUDIT / 'run_stress_gates.py'),
               '--epochs', str(args.epochs), '--output-dir', str(gates)]
    print('Running fixed-snapshot strict gates', flush=True)
    timer = time.perf_counter()
    with (output / 'runner.log').open('w') as log:
        completed = subprocess.run(command, cwd=snapshot, env=env, stdout=log, stderr=subprocess.STDOUT)
    native_code = None
    if args.native_dense:
        print('Running fixed-snapshot native dense-tag API benchmark', flush=True)
        native_env = {**env, 'PYTHONPATH': str(snapshot / AUDIT) + os.pathsep + env['PYTHONPATH']}
        with (output / 'native-dense.log').open('w') as log:
            native = subprocess.run([str(interpreter), str(snapshot / AUDIT / 'benchmark_native_dense_tags.py'),
                '--epochs', str(args.epochs), '--samples', '20', '--edits', '20', '--tags', '5',
                '--mysql-runtime-root', str(mysql_root), '--output', str(output / 'native-dense.json')],
                cwd=snapshot, env=native_env, stdout=log, stderr=subprocess.STDOUT)
            native_code = native.returncode
    physical_code = None
    if args.physical_manifest:
        print('Running fixed-snapshot read-only physical metadata oracle', flush=True)
        with (output / 'physical-metadata.log').open('w') as log:
            physical = subprocess.run([str(interpreter), str(snapshot / AUDIT / 'metadata_ancestor_physical_oracle.py'),
                '--manifest', str(args.physical_manifest.resolve()), '--block-uuid', args.physical_block,
                '--output', str(output / 'physical-metadata.json')],
                cwd=snapshot, env=env, stdout=log, stderr=subprocess.STDOUT)
            physical_code = physical.returncode
    print('Checking snapshot and external dependencies after validation', flush=True)
    source_changes = [name for name, sha in hashes.items()
                      if not (snapshot / name).is_file() or digest(snapshot / name) != sha]
    after_dependencies = dependency_inventory(python_packages, node_modules, python_binary, node_binary)
    dependency_changes = sorted(name for name in dependencies['files'].keys() | after_dependencies['files'].keys()
        if dependencies['files'].get(name) != after_dependencies['files'].get(name))
    for name in ('python_binary', 'node_binary'):
        if dependencies[name] != after_dependencies[name]:
            dependency_changes.append(name)
    summary = json.loads((gates / 'summary.json').read_text()) if (gates / 'summary.json').exists() else {}
    passed = completed.returncode == 0 and summary.get('implemented_gates_passed') is True and not source_changes and not dependency_changes
    mysql_changes = []
    if args.native_dense:
        mysql_after = mysql_inventory(mysql_root)
        mysql_changes = sorted(name for name in mysql_before.keys() | mysql_after.keys()
                               if mysql_before.get(name) != mysql_after.get(name))
        passed = passed and native_code == 0 and not mysql_changes
    if args.physical_manifest:
        passed = passed and physical_code == 0
    result = {'epochs': args.epochs, 'captured_source_manifest_sha256': checksum(hashes),
        'snapshot_gate_exit_code': completed.returncode, 'implemented_gates_passed': passed,
        'snapshot_source_changed_during_run': source_changes, 'external_dependencies_changed_during_run': dependency_changes,
        'native_dense_exit_code': native_code, 'native_runtime_changed_during_run': mysql_changes,
        'physical_metadata_exit_code': physical_code,
        'seconds': time.perf_counter() - timer, 'gate_summary': 'gates/summary.json',
        'retained_snapshot': 'snapshot', 'release_ready': False,
        'required_unexecuted_trials': summary.get('required_unexecuted_trials', ['Gate runner did not produce a summary']),
        'scope': 'Only the captured code was validated. Later edits to the original workspace are not covered.'}
    write_json(output / 'summary.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
