"""Official release discovery and fail-closed, per-version application staging.

No project is opened or migrated here. Installation is deliberately unavailable
until a trusted release signing key is distributed with the application. The
stable launcher holds a shared installation lock; activation needs it exclusive.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import datetime
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import shlex
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'maxwellsdm1867/Rieke-OS'
API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
TRUST_KEY = 'release-signing-public.pem'
MANIFEST_ASSET = 'rieke-release-manifest.json'
MAX_MANIFEST = 1024 * 1024
MAX_ARTIFACT = 512 * 1024 * 1024
_cache = {}
_cache_lock = threading.Lock()


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('Release versions must be stable major.minor.patch versions')
    return tuple(map(int, value.split('.')))


def _read(path):
    return json.loads(Path(path).read_text())


def _atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        json.dump(value, out, indent=2)
        out.flush()
        os.fsync(out.fileno())
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def release_metadata(root=ROOT):
    value = _read(Path(root) / 'rieke-release.json')
    if value.get('format') != 'rieke-application-release' or value.get('repository') != REPOSITORY:
        raise ValueError('Invalid application release metadata')
    _version(value.get('version'))
    if value.get('updater_protocol') != 1:
        raise ValueError('Unsupported updater protocol')
    return value


def installation_status(root=ROOT):
    """Local-only status, safe to call during app startup."""
    metadata = release_metadata(root)
    trusted = (Path(root) / TRUST_KEY).is_file()
    installation = managed_installation(root)
    staged = None
    if installation:
        try:
            candidate = _read(installation / 'staged.json')['version']
            _version(candidate)
            ready = _read(installation / 'releases' / candidate / '.release-ready.json')
            if ready.get('version') == candidate and _version(candidate) > _version(metadata['version']):
                staged = candidate
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return {'installed': metadata['version'], 'state': 'not_checked', 'available': None,
            'release_url': None, 'checked_at': None, 'can_install': False,
            'installation': str(installation) if installation else None,
            'can_stage': bool(installation) and trusted and bool(shutil.which('openssl')),
            'staged_version': staged,
            'message': ('Check for an official release.' if trusted else
                        'Release checking is available. Installation awaits a trusted signed release and managed launcher.')}


def managed_installation(root=ROOT):
    """Only recognize an explicitly managed release, never a development checkout."""
    value = os.environ.get('RIEKE_INSTALLATION_ROOT')
    if not value:
        return None
    try:
        installation = _installation(value)
        resolved = Path(root).resolve()
        if resolved.parent != installation / 'releases':
            return None
        ready = _read(resolved / '.release-ready.json')
        if ready.get('version') != release_metadata(resolved)['version']:
            return None
        return installation
    except (OSError, ValueError, KeyError):
        return None


def _download(url, limit=MAX_MANIFEST):
    if not isinstance(url, str) or not url.startswith('https://'):
        raise ValueError('Release downloads require HTTPS')
    request = Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Rieke-OS-updater/1'})
    with urlopen(request, timeout=20) as response:
        if not response.url.startswith('https://'):
            raise ValueError('Insecure release download redirect')
        value = response.read(limit + 1)
    if len(value) > limit:
        raise ValueError('Release download exceeds its size limit')
    return value


def check_for_updates(root=ROOT, *, force=False):
    """Check the official stable channel. A missing release is not up-to-date."""
    root = Path(root).resolve()
    with _cache_lock:
        cached = _cache.get(str(root))
        if not force and cached and time.monotonic() - cached[0] < 900:
            return {**cached[1], 'staged_version': installation_status(root)['staged_version']}
        result = installation_status(root)
        result['checked_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            release = json.loads(_download(API))
            if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
                raise ValueError('No usable stable release was returned')
            tag = release.get('tag_name', '')
            version = tag.removeprefix('v')
            _version(version)
            release_url = f'https://github.com/{REPOSITORY}/releases/tag/{tag}'
            if release.get('html_url') != release_url:
                raise ValueError('Release is outside the official repository')
            available = _version(version) > _version(result['installed'])
            result.update(state='update_available' if available else 'up_to_date', available=version,
                          release_url=release_url, release_notes=str(release.get('body') or '')[:12000],
                          message=(f'Rieke OS {version} is available.' if available else
                                   'This installation is at or ahead of the latest published release.'))
            if available and not result['can_stage']:
                result['message'] += ' Automatic installation is not configured; review the release instructions.'
        except HTTPError as error:
            result.update(state='unavailable' if error.code == 404 else 'error',
                          message=('No stable Rieke OS release has been published yet.' if error.code == 404
                                   else f'The release server returned HTTP {error.code}. Try again later.'))
        except (OSError, URLError, ValueError, TypeError) as error:
            result.update(state='error', message='Could not verify release availability. Your current app remains usable.')
        if result['state'] == 'error' and cached and cached[1]['state'] == 'update_available':
            # Keep the last discovered release through transient offline/server
            # failures, including when the page is reopened against this service.
            previous = cached[1]
            result.update(state='update_available', available=previous['available'],
                          release_url=previous['release_url'], release_notes=previous.get('release_notes', ''),
                          checked_at=previous['checked_at'], check_error=result['message'],
                          message=previous['message'])
        _cache[str(root)] = (time.monotonic(), dict(result))
        return result


def verify_manifest(envelope_bytes, public_key):
    """RSA PKCS#1 v1.5/SHA-256 signature over exact base64-decoded payload bytes."""
    if len(envelope_bytes) > MAX_MANIFEST:
        raise ValueError('Release manifest is too large')
    envelope = json.loads(envelope_bytes)
    if not isinstance(envelope, dict) or envelope.get('algorithm') != 'rsa-sha256':
        raise ValueError('Unsupported release signature')
    try:
        payload = base64.b64decode(envelope['payload'], validate=True)
        signature = base64.b64decode(envelope['signature'], validate=True)
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError('Malformed release signature') from error
    public_key = Path(public_key)
    if not public_key.is_file() or public_key.is_symlink():
        raise ValueError('No trusted release signing key is installed')
    with tempfile.TemporaryDirectory(prefix='rieke-signature-') as folder:
        folder = Path(folder)
        (folder / 'payload').write_bytes(payload)
        (folder / 'signature').write_bytes(signature)
        check = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(public_key),
                                '-signature', str(folder / 'signature'), str(folder / 'payload')],
                               capture_output=True, timeout=20)
        if check.returncode:
            raise ValueError('Release signature did not verify against the installed key')
    manifest = json.loads(payload)
    if manifest.get('format') != 'rieke-release-manifest' or manifest.get('updater_protocol') != 1:
        raise ValueError('Unsupported signed release manifest')
    _version(manifest.get('version'))
    if manifest.get('repository') != REPOSITORY or not re.fullmatch('[0-9a-f]{40}', manifest.get('commit', '')):
        raise ValueError('Invalid signed release provenance')
    return manifest


@contextlib.contextmanager
def installation_lock(installation, *, exclusive=False, filename='application.lock'):
    installation = Path(installation).resolve()
    with (installation / filename).open('a') as handle:
        try:
            fcntl.flock(handle.fileno(), (fcntl.LOCK_EX | fcntl.LOCK_NB) if exclusive else fcntl.LOCK_SH)
        except BlockingIOError as error:
            raise ValueError('Close all Rieke OS launchers and project services before activating an update.') from error
        yield handle.fileno()


def initialize_installation(installation, *, root=ROOT):
    """Create stable management files only in a new, empty application directory."""
    root = Path(root).resolve()
    installation = Path(installation).expanduser()
    if installation.is_symlink() or (installation.exists() and any(installation.iterdir())):
        raise ValueError('Choose a new, empty application installation directory')
    if not (root / TRUST_KEY).is_file():
        raise ValueError('Managed installation requires the officially distributed trusted signing key')
    installation.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / TRUST_KEY, installation / TRUST_KEY)
    shutil.copy2(Path(__file__), installation / 'manager.py')
    _atomic(installation / 'installation.json', {'format': 'rieke-installation', 'version': 1, 'repository': REPOSITORY})
    return installation.resolve()


def _installation(path):
    path = Path(path).expanduser().resolve()
    info = _read(path / 'installation.json')
    if info != {'format': 'rieke-installation', 'version': 1, 'repository': REPOSITORY}:
        raise ValueError('Choose a managed application installation')
    return path


def _extract(archive, destination):
    """Only regular files/directories; no links, traversal or filesystem devices."""
    total = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        members = tar.getmembers()
        if len(members) > 50000:
            raise ValueError('Release archive has too many files')
        for member in members:
            parts = PurePosixPath(member.name)
            total += member.size
            if (parts.is_absolute() or '..' in parts.parts or '\\' in member.name or
                    not (member.isfile() or member.isdir()) or total > 2 * 1024**3):
                raise ValueError('Unsafe release archive entry')
            target = destination.joinpath(*parts.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Release archive escapes staging directory')
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, target.open('xb') as out:
                    shutil.copyfileobj(source, out)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)


def stage_release(installation, *, root=ROOT):
    """Download the latest signed source artifact and build its isolated runtime.

    A failed stage never changes active.json. Requires the documented compiler,
    uv, Node and Git prerequisites. It never opens a workspace or starts MySQL.
    """
    installation = _installation(installation)
    with installation_lock(installation, exclusive=True, filename='stage.lock'):
        release = json.loads(_download(API))
        if release.get('draft') or release.get('prerelease'):
            raise ValueError('Only official stable releases may be installed')
        tag = release.get('tag_name', '')
        _version(tag.removeprefix('v'))
        prefix = f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
        assets = [a for a in release.get('assets', []) if a.get('name') == MANIFEST_ASSET]
        if len(assets) != 1 or assets[0].get('browser_download_url') != prefix + MANIFEST_ASSET:
            raise ValueError('This release has no official signed updater manifest')
        manifest = verify_manifest(_download(assets[0]['browser_download_url']), installation / TRUST_KEY)
        version = manifest['version']
        if tag != 'v' + version:
            raise ValueError('Signed version does not match the official release tag')
        active = _read(installation / 'active.json') if (installation / 'active.json').exists() else None
        if active and _version(version) <= _version(active['version']):
            raise ValueError('The update must be newer than the active release')
        system = f'{sys.platform}-{platform.machine().lower()}'
        artifacts = [a for a in manifest.get('artifacts', []) if a.get('platform') == system]
        if len(artifacts) != 1:
            raise ValueError(f'This release does not support {system}')
        artifact = artifacts[0]
        url = artifact.get('url', '')
        if not url.startswith(prefix) or '/' in url[len(prefix):] or not url.endswith('.tar.gz'):
            raise ValueError('Artifact must belong to this official release')
        if type(artifact.get('size')) is not int or not 0 < artifact['size'] <= MAX_ARTIFACT:
            raise ValueError('Invalid release artifact size')
        if active:
            old = _read(installation / 'releases' / active['version'] / '.release-ready.json')
            if old['database_compatibility'] != manifest.get('database_compatibility'):
                raise ValueError('This update requires a separately verified project migration; automatic download is disabled')
        destination = installation / 'releases' / version
        command = shlex.join([sys.executable, str(installation / 'manager.py'),
                              '--installation', str(installation), 'activate-and-launch'])
        result = {'state': 'staged', 'version': version, 'apply_command': command,
                  'message': 'Update ready. Close Rieke OS and all project services; the next launch will use this version.'}
        if destination.exists():
            # Other tabs/project services may already have prepared this exact
            # signed artifact. Reuse only its matching completed receipt.
            ready = _read(destination / '.release-ready.json') if (destination / '.release-ready.json').is_file() else {}
            if ready != {'version': version, 'commit': manifest['commit'], 'sha256': artifact['sha256'],
                         'database_compatibility': manifest['database_compatibility']}:
                raise ValueError('Release directory already exists; inspect the previous stage before retrying')
            _atomic(installation / 'staged.json', {'version': version})
            return result
        archive = _download(url, artifact['size'])
        if len(archive) != artifact['size'] or hashlib.sha256(archive).hexdigest() != artifact.get('sha256'):
            raise ValueError('Release artifact checksum or size does not match')
        destination.mkdir(parents=True)
        try:
            _extract(archive, destination)
            metadata = release_metadata(destination)
            if metadata['version'] != version or metadata.get('database_compatibility') != manifest.get('database_compatibility'):
                raise ValueError('Artifact metadata does not match the signed release')
            # Trust stays with the installed manager, never a downloaded replacement key.
            shutil.copy2(installation / TRUST_KEY, destination / TRUST_KEY)
            subprocess.run([sys.executable, str(destination / 'rieke.py'), 'setup'], check=True,
                           cwd=destination, timeout=1800)
            subprocess.run([sys.executable, str(destination / 'rieke.py'), 'doctor', '--json'], check=True,
                           cwd=destination, timeout=180)
            _atomic(destination / '.release-ready.json', {'version': version, 'commit': manifest['commit'],
                     'sha256': artifact['sha256'], 'database_compatibility': manifest['database_compatibility']})
            _atomic(installation / 'staged.json', {'version': version})
        except Exception:
            # Keep failure evidence; never delete anything outside this newly created release.
            _atomic(destination / '.stage-failed.json', {'version': version, 'message': 'Stage did not finish; active release unchanged.'})
            raise
        return result


def activate_staged(installation):
    installation = _installation(installation)
    with installation_lock(installation, exclusive=True, filename='stage.lock'), installation_lock(installation, exclusive=True):
        staged = _read(installation / 'staged.json')
        version = staged['version']
        _version(version)
        ready = _read(installation / 'releases' / version / '.release-ready.json')
        if ready.get('version') != version:
            raise ValueError('Staged release is not ready')
        active = _read(installation / 'active.json') if (installation / 'active.json').exists() else None
        if active:
            _version(active['version'])
            if _version(version) <= _version(active['version']):
                raise ValueError('Staged update must be newer than the active release')
            old = _read(installation / 'releases' / active['version'] / '.release-ready.json')
            if old['database_compatibility'] != ready['database_compatibility']:
                raise ValueError('This update requires a separately verified project migration; automatic activation is disabled')
        _atomic(installation / 'active.json', {'version': version, 'previous': active['version'] if active else None})
        (installation / 'staged.json').unlink()
        return {'state': 'activated', 'version': version}


def activate_and_launch(installation, *, wait_seconds=300):
    """Run outside the app; wait for cooperative shutdown, never kill a writer."""
    installation = _installation(installation)
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            activate_staged(installation)
            break
        except ValueError as error:
            if 'Close all Rieke OS' not in str(error) or time.monotonic() >= deadline:
                raise
            time.sleep(0.5)
    return main(['--installation', str(installation), 'launch'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'stage', 'activate', 'activate-and-launch', 'launch', 'hold'))
    parser.add_argument('--installation', type=Path, required=True)
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == 'init':
        print(initialize_installation(args.installation))
        return 0
    installation = _installation(args.installation)
    if args.command == 'stage':
        print(json.dumps(stage_release(installation)))
    elif args.command == 'activate':
        print(json.dumps(activate_staged(installation)))
    elif args.command == 'activate-and-launch':
        return activate_and_launch(installation)
    else:
        if args.command == 'launch' and (installation / 'staged.json').is_file():
            try:
                activate_staged(installation)
            except (OSError, ValueError) as error:
                # A busy installation or incompatible update must not prevent
                # launching the current release. Never stop another service.
                print(f'Update deferred; launching the current version: {error}', file=sys.stderr)
        with installation_lock(installation) as lock_fd:
            env = dict(os.environ, RIEKE_INSTALLATION_ROOT=str(installation))
            extra = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
            if args.command == 'hold':
                if not extra:
                    raise ValueError('A held project service command is required')
                return subprocess.call(extra, env=env, pass_fds=(lock_fd,))
            active = _read(installation / 'active.json')
            _version(active['version'])
            release = installation / 'releases' / active['version']
            return subprocess.call([sys.executable, str(release / 'rieke.py'), 'launch', *extra], env=env,
                                   pass_fds=(lock_fd,))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'Update stopped: {error}', file=sys.stderr)
        raise SystemExit(1)
