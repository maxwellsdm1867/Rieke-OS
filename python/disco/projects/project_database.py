"""Provision only explicitly owned project databases; never adopt foreign data."""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import uuid

from workspace_mysql_profile import local_mysql_options


def _run(arguments, **options):
    try:
        return subprocess.run(['docker', *arguments], capture_output=True, text=True,
                              timeout=options.pop('timeout', 30), **options)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('Docker is unavailable or did not respond. Start Docker Desktop and try opening the project again.') from error


def ensure_project_database(project_dir, *, timeout=120, _restoring=False):
    project_dir = Path(project_dir).resolve()
    if (project_dir / '.portable-restore.pending').exists() and not _restoring:
        raise ValueError('Project transfer restore is incomplete; finish recovery before opening it')
    project = json.loads((project_dir / 'project.json').read_text())
    catalog = json.loads((project_dir / 'catalog.json').read_text())
    identity = project['project_uuid']
    if catalog['project_uuid'] != identity:
        raise ValueError('Project and database identities disagree')
    provider = catalog['connection']['credential_provider']
    if provider.get('kind') == 'native-project':
        from workspace_native_mysql import ensure_native_database
        return ensure_native_database(project_dir, timeout=timeout)
    container = provider['container']
    from workspace_projects import _read_manifest
    descriptor = project_dir / 'database/service.json'
    owned = _read_manifest(descriptor) if descriptor.exists() or descriptor.is_symlink() else catalog.get('managed_database')
    if catalog.get('managed_database') and owned != catalog['managed_database']:
        raise ValueError('Database ownership records disagree')
    if container.startswith('rieke-os-') and not owned:
        raise ValueError('Managed database ownership record is missing; refusing to attach it')
    if owned:
        expected = 'rieke-os-' + identity.replace('-', '')
        if isinstance(owned, dict) and 'instance_uuid' in owned:
            instance = str(uuid.UUID(owned['instance_uuid']))
            expected += '-' + instance.replace('-', '')
        if not isinstance(owned, dict) or type(owned.get('version')) is not int or owned['version'] != 1 or owned.get('project_uuid') != identity or owned.get('container') != expected or container != expected or owned.get('storage_ref') != 'database/mysql' or owned.get('image') != 'datajoint/mysql:8.0':
            raise ValueError('Managed database configuration does not match this project')
        if (project_dir / 'database').is_symlink():
            raise ValueError('Database storage cannot be a symbolic link')
    if _run(['info']).returncode:
        result = _run(['desktop','start'], timeout=90)
        if result.returncode:
            raise ValueError('Start Docker Desktop, then open the project again. Project files are preserved.')
    result = _run(['inspect',container])
    if result.returncode:
        if not owned:
            raise ValueError('The configured existing database container is unavailable; it was not replaced')
        data = project_dir / 'database/mysql'
        if data.is_symlink():
            raise ValueError('Database storage cannot be a symbolic link')
        data.mkdir(parents=True, exist_ok=True)
        # Existing storage with no owned container needs explicit recovery. Do
        # not initialize a guessed password against an orphaned database.
        if any(data.iterdir()):
            raise ValueError('Database files exist without their registered container. Recover that container before reopening.')
        environment = {**os.environ, 'MYSQL_ROOT_PASSWORD':secrets.token_urlsafe(36)}
        created = _run(['run','--detach','--name',container,
            '--label',f'rieke-os.project_uuid={identity}',
            '--label',f'rieke-os.project_path={project_dir}',
            '--publish','127.0.0.1::3306','--mount',f'type=bind,src={data},dst=/var/lib/mysql',
            '--env','MYSQL_ROOT_PASSWORD',owned['image'], 'mysqld',
            *local_mysql_options(legacy_redo=True)], env=environment, timeout=180)
        if created.returncode:
            raise ValueError('Could not prepare the project database. Check Docker Desktop; no existing database was replaced.')
        result = _run(['inspect',container])
    if result.returncode:
        raise ValueError('Project database container could not be inspected')
    info = json.loads(result.stdout)[0]
    if owned:
        labels = info.get('Config',{}).get('Labels') or {}
        if labels.get('rieke-os.project_uuid') != identity or labels.get('rieke-os.project_path') != str(project_dir):
            raise ValueError('Database container ownership does not match this project; refusing to attach it')
        bindings = info.get('HostConfig',{}).get('PortBindings',{}).get('3306/tcp') or []
        if not bindings or any(binding.get('HostIp') != '127.0.0.1' for binding in bindings):
            raise ValueError('Managed database must bind only to localhost')
        mounts = info.get('Mounts') or []
        if not any(m.get('Destination') == '/var/lib/mysql' and m.get('Source') == str(project_dir / 'database/mysql') and m.get('Type') == 'bind' for m in mounts):
            raise ValueError('Database container storage does not match this project')
    if not info.get('State',{}).get('Running'):
        if _run(['start',container]).returncode:
            raise ValueError('Project database could not start')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = _run(['exec',container,'sh','-c',
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot --batch --skip-column-names -e "SELECT 1"'],timeout=5)
        if ready.returncode == 0 and ready.stdout.strip() == '1':
            return
        time.sleep(.5)
    raise ValueError('Project database is still starting. Its files are preserved; try opening it again.')
