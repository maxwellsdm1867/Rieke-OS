#!/usr/bin/env python3
"""Build a private, relocatable desktop runtime before signing.

Build dependencies (uv, C++ toolchain, npm) are allowed here, never at launch.
Downloads are SHA-256 pinned. Does not sign with Developer ID or qualify release.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OPTIONAL_PID_ATTACH = 'python/lib/python3.11/site-packages/debugpy/_vendored/pydevd/pydevd_attach_to_process/attach.dylib'
MATLAB_EXPORT_HELPERS = ('launchWorkspaceTree', 'readWorkspaceTags', 'validateWorkspaceTags', 'workspaceTag', 'writeWorkspaceTags')
sys.path.insert(0, str(ROOT / 'python'))
from workspace_bootstrap import verify_checkout
from workspace_mysql_runtime import install_mysql_runtime, mysql_runtime


def run(command, **kwargs):
    subprocess.run([str(x) for x in command], check=True, **kwargs)


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def patch_parser(checkout):
    """Patch only config ownership, leaving parser algorithms byte-identical."""
    path = checkout / 'src/retinanalysis/config/settings.py'
    text = path.read_text()
    old = 'config_path = ir.files(retinanalysis) / os.path.join("config", "config.ini")'
    new = '''# Rieke desktop wheels store mutable configuration outside signed resources.
config_path = os.environ.get("RIEKE_PARSER_CONFIG")
if config_path:
    if not os.path.isabs(config_path):
        raise ValueError("RIEKE_PARSER_CONFIG must be an absolute user-state path")
else:
    config_path = ir.files(retinanalysis) / os.path.join("config", "config.ini")'''
    if text.count(old) != 1:
        raise ValueError('Pinned parser config patch no longer applies exactly')
    path.write_text(text.replace(old, new))
    (checkout / 'src/retinanalysis/config/config.ini').unlink(missing_ok=True)
    return {'path': 'src/retinanalysis/config/settings.py',
            'original_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'patched_sha256': digest(path), 'purpose': 'RIEKE_PARSER_CONFIG external user state'}


def stage_tracked_parser(checkout, staged):
    """Only reviewed tracked parser/submodule source can enter the wheel build."""
    names = subprocess.check_output(['git', '-C', checkout, 'ls-files', '--recurse-submodules', '-z']).decode().split('\0')
    for name in filter(None, names):
        source, target = checkout / name, staged / name
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Tracked parser source path escapes staging')
        if source.is_symlink():
            if not source.resolve().is_relative_to(checkout):
                raise ValueError('Tracked parser source link escapes checkout')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(os.readlink(source))
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def download_python(spec, cache):
    path = cache / 'standalone-python.tar.gz'
    if not path.exists():
        temporary = path.with_suffix('.download')
        try:
            with urlopen(spec['url'], timeout=60) as source, temporary.open('wb') as out:
                shutil.copyfileobj(source, out)
            if digest(temporary) != spec['sha256']:
                raise ValueError('Standalone Python download SHA-256 mismatch')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if digest(path) != spec['sha256']:
        raise ValueError('Cached standalone Python SHA-256 mismatch')
    return path


def copy_application(root, output, frontend_source=None):
    application = output / 'application'
    if application.exists():
        shutil.rmtree(application)
    (application / 'python').mkdir(parents=True)
    # Explicit allowlist excludes tests, projects, source runtime, credentials and receipts.
    for path in (root / 'python').glob('*.py'):
        shutil.copy2(path, application / 'python' / path.name)
    for name in ('workspace-source.json', 'workspace-mysql-runtime.json'):
        shutil.copy2(root / 'python' / name, application / 'python' / name)
    shutil.copy2(root / 'rieke-release.json', application / 'rieke-release.json')
    shutil.copy2(root / 'workspace-app/package.json', application / 'workspace-app-package.json')
    copy_matlab_application(root, application)
    dist = Path(frontend_source) if frontend_source else root / 'workspace-app/dist'
    if not (dist / 'index.html').is_file():
        raise ValueError('Build the frontend before assembling desktop resources')
    frontend = output / 'frontend'
    if frontend.exists():
        shutil.rmtree(frontend)
    shutil.copytree(dist, frontend)
    (application / 'workspace-app').mkdir()
    # Existing Flask static route contract, contained relocatable link.
    (application / 'workspace-app/dist').symlink_to('../../frontend', target_is_directory=True)
    shutil.copy2(root / 'workspace-app/package.json', application / 'workspace-app/package.json')


def copy_matlab_application(root, application):
    """Ship the source closure required by MAT exports and their GUI launcher.

    MATLAB is not required to create exports. These reviewed source helpers let
    a recipient with MATLAB use the exported launcher without the source clone.
    Recordings, examples, tests and arbitrary adjacent files are not resources.
    """
    root, application = Path(root), Path(application)
    required = [root / 'epicTreeGUI.m', root / 'src/loadEpicTreeData.m',
                root / 'src/buildTreeFromEpicData.m', root / 'src/tree/epicTreeTools.m']
    required.extend(root / 'src/tree' / (name + '.m') for name in MATLAB_EXPORT_HELPERS)
    if any(not path.is_file() for path in required):
        raise ValueError('MATLAB export/launcher source closure is incomplete')
    paths = [root / 'epicTreeGUI.m', *sorted((root / 'src').rglob('*.m'))]
    for source in paths:
        if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError('MATLAB application source escapes the reviewed code tree')
        target = application / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def build_frontend():
    # Source development keeps old chunks for in-flight browsers. A desktop
    # release includes only a fresh build, not that accumulated history.
    dist = ROOT / 'desktop/build/renderer'
    run(['npm', 'run', 'build', '--', '--outDir', dist, '--emptyOutDir'], cwd=ROOT / 'workspace-app')
    return dist


def relocate_native(output):
    """Remove build-host loader paths and close wheel/native library references."""
    from desktop_runtime_manifest import MACHO
    modified = []
    for path in sorted(output.rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open('rb') as handle:
            if handle.read(4) not in MACHO:
                continue
        header = subprocess.check_output(['/usr/bin/otool', '-l', path], text=True)
        changes = []
        rpaths = set(re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', header))
        for value in sorted(rpaths):
            if value.startswith('/') and not value.startswith(('/usr/lib/', '/System/Library/')):
                changes.extend(['-delete_rpath', value])
        deps = set(re.findall(r'cmd LC_(?:LOAD_DYLIB|LOAD_WEAK_DYLIB|REEXPORT_DYLIB|LAZY_LOAD_DYLIB|LOAD_UPWARD_DYLIB)\s+cmdsize \d+\s+name (.*?) \(offset', header))
        for value in sorted(deps):
            if value.startswith('/') and not value.startswith(('/usr/lib/', '/System/Library/')):
                candidates = [path.parent / Path(value).name,
                              output / 'mysql/lib' / Path(value).name]
                target = next((p for p in candidates if p.exists()), None)
                if target is None:
                    raise ValueError(f'Cannot relocate external native dependency {path.name}: {value}')
                changes.extend(['-change', value, '@loader_path/' + os.path.relpath(target, path.parent)])
        # PyTorch loads its package globally but sibling wheel extensions should
        # have explicit contained paths rather than depending on import order.
        torch = output / 'python/lib/python3.11/site-packages/torch/lib'
        if any(value.startswith('@rpath/libtorch') or value == '@rpath/libc10.dylib' for value in deps):
            contained = '@loader_path/' + os.path.relpath(torch, path.parent)
            if contained not in rpaths:
                changes.extend(['-add_rpath', contained])
        if changes:
            run(['/usr/bin/install_name_tool', *changes, path], capture_output=True)
            # ARM executables need valid signatures after relocation. This is
            # build-time local signing; Developer ID signing follows in CI.
            run(['/usr/bin/codesign', '--force', '--sign', '-', path], capture_output=True)
            modified.append(path.relative_to(output).as_posix())
    return modified


def dependency_inventory(output):
    """Retain package metadata and native archive license texts, without build paths."""
    script = '''import importlib.metadata as m,json
print(json.dumps(sorted([{'name':d.metadata['Name'],'version':d.version,
 'license':d.metadata.get('License-Expression') or d.metadata.get('License') or 'see distribution metadata'}
 for d in m.distributions()],key=lambda d:d['name'].lower())))'''
    python = json.loads(subprocess.check_output([output / 'python/bin/python3.11', '-c', script], text=True))
    lock = json.loads((output / 'mysql-lock.json').read_text())
    packages = lock['platforms']['darwin-arm64']['packages']
    copied = []
    for package in packages:
        archive = ROOT / '.rieke-runtime/mysql-packages' / package['url'].rsplit('/', 1)[-1]
        if not archive.is_file() or digest(archive) != package['sha256']:
            raise ValueError(f'Native license archive missing or checksum mismatch: {package["name"]}')
        with zipfile.ZipFile(archive) as compressed:
            info = next(name for name in compressed.namelist() if name.startswith('info-') and name.endswith('.tar.zst'))
            data = subprocess.check_output([output / 'mysql/bin/zstd', '--decompress', '--stdout'],
                                           input=compressed.read(info))
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            for member in tar.getmembers():
                if not member.isfile() or not member.name.startswith('info/licenses/'):
                    continue
                relative = Path(member.name).relative_to('info/licenses')
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Native license archive path escape')
                target = output / 'licenses/native' / package['name'] / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, target.open('wb') as out:
                    shutil.copyfileobj(source, out)
                copied.append(target.relative_to(output).as_posix())
    (output / 'dependency-inventory.json').write_text(json.dumps(
        {'python_distributions': python, 'native_packages': packages,
         'native_license_files': copied}, indent=2) + '\n')


def refresh_native_license_inventory(output, root=ROOT):
    """Fill archives lacking notices from exact upstream versions/hash pins."""
    root, output = Path(root), Path(output)
    pin = root / 'desktop/native-license-sources.json'
    sources = json.loads(pin.read_text())
    if sources.get('format') != 'rieke-native-license-sources' or sources.get('version') != 1:
        raise ValueError('Unrecognized native license source lock')
    inventory_path = output / 'dependency-inventory.json'
    value = json.loads(inventory_path.read_text())
    versions = {package['name']: package['version'] for package in value['native_packages']}
    coverage = {name: [] for name in versions}
    files = set(value['native_license_files'])
    for relative in files:
        parts = Path(relative).parts
        if len(parts) > 2 and parts[:2] == ('licenses', 'native') and parts[2] in coverage:
            coverage[parts[2]].append(relative)
    cache = root / 'desktop/build/license-cache'
    cache.mkdir(parents=True, exist_ok=True)
    for source in sources['sources']:
        names = source.get('applies_to', [source['package']])
        if any(versions.get(name) != source['version'] for name in names):
            raise ValueError('Native license source version differs from bundled dependency')
        if not source['url'].startswith('https://raw.githubusercontent.com/') or not re.fullmatch('[a-f0-9]{64}', source['sha256']):
            raise ValueError('Native license source must use an exact SHA-256 pin')
        name = source['file']
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('Unsafe native license filename')
        cached = cache / name
        if not cached.exists():
            with urlopen(source['url'], timeout=30) as response:
                data = response.read(1024 * 1024)
            if hashlib.sha256(data).hexdigest() != source['sha256']:
                raise ValueError('Upstream native license text checksum mismatch')
            cached.write_bytes(data)
        if cached.is_symlink() or digest(cached) != source['sha256']:
            raise ValueError('Cached native license text checksum mismatch')
        target = output / 'licenses/native' / source['package'] / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached, target)
        relative = target.relative_to(output).as_posix()
        files.add(relative)
        for package in names:
            coverage[package].append(relative)
    # ICU's archive installs its notice in the runtime share tree itself.
    icu = output / 'mysql/share/icu' / versions.get('icu', 'missing') / 'LICENSE'
    if icu.is_file():
        relative = icu.relative_to(output).as_posix()
        files.add(relative)
        coverage['icu'].append(relative)
    if any(not notices for notices in coverage.values()):
        raise ValueError('Bundled native dependency is missing its license notice')
    value['native_license_files'] = sorted(files)
    value['native_license_coverage'] = {name: sorted(set(notices)) for name, notices in coverage.items()}
    value['native_license_sources'] = sources['sources']
    inventory_path.write_text(json.dumps(value, indent=2) + '\n')
    shutil.copy2(pin, output / 'native-license-sources.json')


def exclude_optional_features(output):
    """Omit the debugger PID injection feature, which desktop never exposes.

    debugpy's normal package, metadata and licenses remain pinned and installed.
    This production profile does not ship a debugger attach-to-existing-process
    interface. Its optional helper has a higher deployment floor than the app.
    """
    output = Path(output)
    helper = output / OPTIONAL_PID_ATTACH
    original_sha256 = None
    if helper.is_file():
        original_sha256 = digest(helper)
        helper.unlink()
    elif (output / 'build-receipt.json').exists():
        previous = json.loads((output / 'build-receipt.json').read_text())
        for entry in previous.get('excluded_optional_features', []):
            if entry.get('path') == OPTIONAL_PID_ATTACH:
                original_sha256 = entry.get('original_sha256')
    if not original_sha256:
        raise ValueError('Optional debugger helper exclusion has no pinned build provenance')
    features = [{'path': OPTIONAL_PID_ATTACH, 'distribution': 'debugpy',
                 'purpose': 'Attach a debugger to an existing process PID',
                 'reason': 'Desktop scientific UI exposes no debugger PID attach feature; helper requires macOS 15',
                 'original_sha256': original_sha256}]
    inventory = output / 'dependency-inventory.json'
    if inventory.exists():
        value = json.loads(inventory.read_text())
        value['excluded_optional_features'] = features
        inventory.write_text(json.dumps(value, indent=2) + '\n')
    return features


def build(output, skip_frontend=False):
    spec = json.loads((ROOT / 'desktop/python-runtime.json').read_text())
    if sys.platform != spec['platform'] or os.uname().machine != 'arm64':
        raise ValueError('Initial desktop runtime build supports macOS Apple Silicon only')
    parser_spec = json.loads((ROOT / 'python/workspace-source.json').read_text())
    checkout = ROOT / '.rieke-runtime/retinanalysis'
    if not checkout.exists():
        checkout = ROOT / 'desktop/build/parser-source'
        if not checkout.exists():
            run(['git', 'clone', '--no-checkout', parser_spec['repository'], checkout])
            run(['git', '-C', checkout, 'checkout', '--detach', parser_spec['commit']])
            run(['git', '-C', checkout, 'submodule', 'update', '--init', '--recursive'])
    checkout = verify_checkout(checkout, parser_spec)
    if parser_spec['python'] != spec['python_version']:
        raise ValueError('Source and desktop Python pins differ')
    output.mkdir(parents=True, exist_ok=True)
    cache = ROOT / 'desktop/build/cache'
    cache.mkdir(parents=True, exist_ok=True)
    archive = download_python(spec, cache)
    interpreter = output / 'python/bin/python3.11'
    if not interpreter.exists():
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                # Python >=3.12 data filter not available in the source runtime.
                target = output / member.name
                if not target.resolve().is_relative_to(output.resolve()):
                    raise ValueError('Standalone Python archive path escape')
                if member.issym() or member.islnk():
                    linked = target.parent / member.linkname if member.issym() else output / member.linkname
                    if not linked.resolve().is_relative_to(output.resolve()):
                        raise ValueError('Standalone Python archive link escape')
            tar.extractall(output)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    run(['uv', 'pip', 'install', '--python', interpreter, '--system', '--require-hashes',
         '-r', ROOT / 'python/workspace-runtime.lock', '-r', ROOT / 'desktop/requirements.lock'], env=env)
    with tempfile.TemporaryDirectory(prefix='parser-wheel-', dir=cache) as temporary:
        staged = Path(temporary) / 'parser'
        stage_tracked_parser(checkout, staged)
        patch = patch_parser(staged)
        run([interpreter, '-m', 'hatchling', 'build', '-t', 'wheel'], cwd=staged, env=env)
        wheel = next((staged / 'dist').glob('*.whl'))
        parser_wheel = cache / wheel.name
        shutil.copy2(wheel, parser_wheel)
        # Build native parser utilities from pinned submodule, never editable installs.
        utilities = staged / parser_spec['utilities']
        run([interpreter, 'setup.py', 'bdist_wheel', '--dist-dir', cache], cwd=utilities, env=env)
        vision_wheel = next(cache.glob('vision_utils-1.1.1-*.whl'))
        run(['uv', 'pip', 'install', '--python', interpreter, '--system', '--no-deps', '--reinstall',
             parser_wheel, vision_wheel], env=env)
    prefix = output / 'mysql'
    if not prefix.exists():
        if not (ROOT / '.rieke-runtime/mysql').exists():
            install_mysql_runtime(ROOT)
        mysql = mysql_runtime(ROOT)
        shutil.copytree(mysql['root'], prefix, symlinks=True,
                        ignore=shutil.ignore_patterns('conda-meta', 'include', 'pkgconfig', 'cmake', '*.a', '*.la'))
    # Keep source provenance and licenses without embedding conda build-user history.
    shutil.copy2(ROOT / 'python/workspace-mysql-runtime.json', output / 'mysql-lock.json')
    shutil.copy2(ROOT / 'desktop/python-runtime.json', output / 'python-lock.json')
    licenses = output / 'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copy2(checkout / 'LICENSE.txt', licenses / 'retinanalysis.txt')
    vision_license = checkout / parser_spec['submodule'] / 'LICENSE'
    if vision_license.exists():
        shutil.copy2(vision_license, licenses / 'vision-utils.txt')
    site = output / 'python/lib/python3.11/site-packages'
    # Console script absolute shebangs and installation receipts are build artifacts,
    # not runtime authority. Runtime starts the interpreter and registered Python entry.
    for path in (output / 'python/bin').iterdir():
        if path.is_file() and not path.is_symlink() and path.read_bytes()[:2] == b'#!':
            path.unlink()
    for path in (output / 'python/bin').iterdir():
        if path.is_symlink() and not path.exists():
            path.unlink()
    for pattern in ('direct_url.json', 'uv_cache.json', 'uv_build.json'):
        for path in site.rglob(pattern):
            path.unlink()
    for path in output.rglob('__pycache__'):
        shutil.rmtree(path)
    view = output / 'parser/src'
    view.mkdir(parents=True, exist_ok=True)
    link = view / 'retinanalysis'
    if not link.exists():
        link.symlink_to('../../python/lib/python3.11/site-packages/retinanalysis', target_is_directory=True)
    frontend = ROOT / 'workspace-app/dist' if skip_frontend else build_frontend()
    copy_application(ROOT, output, frontend)
    relocated = relocate_native(output)
    dependency_inventory(output)
    refresh_native_license_inventory(output)
    exclusions = exclude_optional_features(output)
    receipt = {'python_archive_sha256': spec['sha256'], 'parser_source_commit':
               subprocess.check_output(['git', '-C', checkout, 'rev-parse', 'HEAD'], text=True).strip(),
               'parser_patch': patch, 'parser_wheel_sha256': digest(parser_wheel),
               'vision_wheel_sha256': digest(vision_wheel),
               'python_lock_sha256': digest(ROOT / 'python/workspace-runtime.lock'),
               'desktop_requirements_sha256': digest(ROOT / 'desktop/requirements.lock')}
    receipt['relocated_native_files'] = relocated
    receipt['excluded_optional_features'] = exclusions
    (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    run([sys.executable, ROOT / 'tools/desktop_runtime_manifest.py', '--runtime', output, '--write'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'desktop/build/runtime')
    parser.add_argument('--skip-frontend', action='store_true')
    parser.add_argument('--refresh-application', action='store_true')
    args = parser.parse_args()
    if args.refresh_application:
        frontend = ROOT / 'workspace-app/dist' if args.skip_frontend else build_frontend()
        copy_application(ROOT, args.output.resolve(), frontend)
        refresh_native_license_inventory(args.output.resolve())
        run([sys.executable, ROOT / 'tools/desktop_runtime_manifest.py', '--runtime', args.output.resolve(), '--write'])
    else:
        build(args.output.resolve(), args.skip_frontend)

if __name__ == '__main__':
    main()
