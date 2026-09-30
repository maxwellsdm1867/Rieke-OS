"""Provision a private, SHA-256-pinned MySQL runtime; never install system services.

Conda-forge packages are installed offline from verified archives with a pinned
micromamba bootstrap. Prefix relocation is done at installation, not by copying
already-linked binaries. No PATH search, Homebrew or Docker is used for MySQL.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LOCK = 'python/workspace-mysql-runtime.json'
MAX_PACKAGE = 512 * 1024 * 1024


def runtime_spec(root=ROOT):
    value = json.loads((Path(root) / LOCK).read_text())
    if value.get('format') != 'rieke-native-mysql-runtime' or value.get('version') != 1:
        raise ValueError('Unsupported bundled MySQL runtime lock')
    key = f'{sys.platform}-{platform.machine().lower()}'
    if key not in value.get('platforms', {}):
        raise ValueError(f'Bundled native MySQL is not yet validated for {key}')
    return value, value['platforms'][key]


def _probe(prefix, version):
    result = {'root': str(prefix), 'version': version}
    for name in ('mysqld', 'mysql', 'mysqldump'):
        binary = prefix / 'bin' / name
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError(f'Bundled MySQL is missing {name}; run rieke.py setup')
        output = subprocess.run([str(binary), '--no-defaults', '--version'], check=True,
                                capture_output=True, text=True, timeout=20).stdout
        if not re.search(r'\b' + re.escape(version) + r'\b', output):
            raise ValueError(f'Bundled {name} version does not match MySQL {version}')
        result[name] = str(binary)
    return result


def _repair_macos_signatures(prefix):
    """Conda prefix relocation changes Mach-O bytes; restore local ad-hoc signatures."""
    if sys.platform != 'darwin':
        return
    magic = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
             b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
    for directory in ('bin', 'lib'):
        for binary in sorted((prefix / directory).rglob('*')):
            if binary.is_symlink() or not binary.is_file():
                continue
            with binary.open('rb') as source:
                executable = source.read(4) in magic
            if executable:
                subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(binary)],
                               check=True, capture_output=True, timeout=30)


def mysql_runtime(root=ROOT):
    """Return pinned private executable paths without connecting or starting SQL."""
    root = Path(root).resolve()
    spec, _ = runtime_spec(root)
    if os.environ.get('RIEKE_DESKTOP_RUNTIME'):
        # Desktop resources were linked and signed by the build. Launch never
        # invokes micromamba, changes dependency paths or repairs signatures.
        runtime = Path(os.environ['RIEKE_DESKTOP_RUNTIME']).resolve(strict=True)
        manifest = json.loads((runtime / 'runtime-manifest.json').read_text())
        if (manifest.get('format') != 'rieke-desktop-runtime' or manifest.get('version') != 1
                or manifest.get('mysql_version') != spec['mysql_version']):
            raise ValueError('Packaged MySQL compatibility manifest is invalid')
        prefix = runtime / 'mysql'
        if prefix.is_symlink() or not prefix.resolve().is_relative_to(runtime):
            raise ValueError('Packaged MySQL prefix escapes application resources')
        if hashlib.sha256((runtime / 'mysql-lock.json').read_bytes()).hexdigest() != hashlib.sha256((root / LOCK).read_bytes()).hexdigest():
            raise ValueError('Packaged MySQL runtime lock differs from application code')
        return _probe(prefix, spec['mysql_version'])
    prefix = root / '.rieke-runtime/mysql'
    if prefix.is_symlink():
        raise ValueError('Bundled MySQL prefix must not be a symbolic link')
    if prefix.is_dir():
        receipt = prefix / '.rieke-mysql-runtime.json'
        if not receipt.is_file():
            raise ValueError('Bundled MySQL setup is incomplete; inspect its setup log before retrying')
        value = json.loads(receipt.read_text())
        if value.get('lock_sha256') != hashlib.sha256((root / LOCK).read_bytes()).hexdigest():
            raise ValueError('Bundled MySQL runtime differs from the release lock; use a fresh release installation')
        return _probe(prefix, spec['mysql_version'])
    # The existing development prefix is app-private, never an arbitrary PATH installation.
    development = root / '.rieke-runtime/native'
    if development.is_dir() and not development.is_symlink():
        return _probe(development, spec['mysql_version'])
    raise ValueError('Bundled native MySQL is not installed; run rieke.py setup')


def _verified_package(package, cache):
    url, expected = package['url'], package['sha256']
    if not url.startswith('https://conda.anaconda.org/conda-forge/') or not re.fullmatch('[a-f0-9]{64}', expected):
        raise ValueError('Invalid pinned MySQL dependency')
    filename = url.rsplit('/', 1)[-1]
    if not filename or filename in ('.', '..'):
        raise ValueError('Invalid native package filename')
    path = cache / filename
    if path.is_symlink():
        raise ValueError('Native package cache cannot contain symbolic links')
    if path.exists():
        digest = hashlib.sha256()
        with path.open('rb') as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f'Cached native package checksum failed: {filename}')
        return path
    with tempfile.NamedTemporaryFile(dir=cache, delete=False) as out:
        temporary = Path(out.name)
        try:
            request = Request(url, headers={'User-Agent': 'Rieke-OS-native-runtime/1'})
            digest = hashlib.sha256()
            size = 0
            with urlopen(request, timeout=60) as source:
                if not source.url.startswith('https://'):
                    raise ValueError('Native runtime download redirected outside HTTPS')
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_PACKAGE:
                        raise ValueError('Native runtime package exceeds its size limit')
                    out.write(chunk)
                    digest.update(chunk)
            out.flush()
            if digest.hexdigest() != expected:
                raise ValueError(f'Native package checksum failed: {filename}')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return path


def install_mysql_runtime(root=ROOT):
    """Install a release-owned server/client prefix; no database is initialized."""
    root = Path(root).resolve()
    spec, selected = runtime_spec(root)
    runtime = root / '.rieke-runtime'
    if runtime.is_symlink():
        raise ValueError('Runtime directory cannot be a symbolic link')
    runtime.mkdir(exist_ok=True)
    prefix = runtime / 'mysql'
    if prefix.exists() or prefix.is_symlink():
        return mysql_runtime(root)
    cache = runtime / 'mysql-packages'
    if cache.is_symlink():
        raise ValueError('Native package cache cannot be a symbolic link')
    cache.mkdir(exist_ok=True)
    archives = [_verified_package(package, cache) for package in selected['packages']]
    installer = _verified_package(selected['installer'], cache)
    with tempfile.TemporaryDirectory(prefix='mysql-bootstrap-', dir=runtime) as temporary:
        temporary = Path(temporary)
        executable = temporary / 'micromamba'
        with tarfile.open(installer, 'r:bz2') as archive:
            entry = archive.getmember('bin/micromamba')
            if not entry.isfile():
                raise ValueError('Pinned runtime installer is not a regular executable')
            with archive.extractfile(entry) as source, executable.open('wb') as output:
                shutil.copyfileobj(source, output)
        executable.chmod(0o755)
        explicit = temporary / 'packages.txt'
        # SHA-256 verified above; local URLs make the linker completely offline.
        explicit.write_text('@EXPLICIT\n' + '\n'.join(
            p.as_uri() + '#' + package['sha256'] for p, package in zip(archives, selected['packages'])) + '\n')
        env = dict(os.environ, MAMBA_ROOT_PREFIX=str(temporary / 'mamba'), MAMBA_NO_BANNER='1')
        subprocess.run([str(executable), '--no-rc', 'create', '--offline', '--yes',
                        '--prefix', str(prefix), '--file', str(explicit)], env=env, check=True, timeout=300)
    _repair_macos_signatures(prefix)
    result = _probe(prefix, spec['mysql_version'])
    receipt = {'format': 'rieke-native-mysql-runtime', 'version': 1,
               'mysql_version': spec['mysql_version'],
               'lock_sha256': hashlib.sha256((root / LOCK).read_bytes()).hexdigest()}
    (prefix / '.rieke-mysql-runtime.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return result
