"""Initialize managed directories; explicitly relocate a stopped local MySQL store.

Run database relocation only while the workspace API is stopped. The original
container and cold data directory remain available for rollback.
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from recording_workspace import digest, now, write_json
from workspace_storage import initialize_layout, log_dir, migrate_legacy_logs


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, stderr=subprocess.PIPE).strip()


def database_snapshot(password, schemas):
    import pymysql
    connection = pymysql.connect(host='127.0.0.1', port=3306, user='root', password=password)
    snapshot = {}
    def encode(value):
        if isinstance(value, bytes):
            return {'bytes': base64.b64encode(value).decode()}
        return str(value)
    try:
        with connection.cursor() as cursor:
            for schema in schemas:
                if not schema.replace('_', '').isalnum():
                    raise ValueError('Unexpected schema name')
                cursor.execute(f'SHOW FULL TABLES FROM `{schema}`')
                tables = [name for name, kind in cursor.fetchall() if kind == 'BASE TABLE']
                for name in tables:
                    escaped = name.replace('`', '``')
                    cursor.execute(f'SELECT * FROM `{schema}`.`{escaped}`')
                    rows = sorted(json.dumps(row, default=encode, ensure_ascii=True) for row in cursor.fetchall())
                    snapshot[schema + '.' + name] = {'rows': len(rows), 'sha256': hashlib.sha256(
                        '\n'.join(rows).encode()).hexdigest()}
        return snapshot
    finally:
        connection.close()


def relocate_mysql(project):
    config = json.loads((project / 'catalog.json').read_text())
    container = config['connection']['credential_provider']['container']
    info = json.loads(docker('inspect', container))[0]
    mounts = info['Mounts']
    if len(mounts) != 1 or mounts[0]['Destination'] != '/var/lib/mysql' or mounts[0]['Type'] != 'bind':
        raise ValueError('Relocation supports this local, single-bind MySQL runtime only')
    original = Path(mounts[0]['Source']).resolve()
    target = project / 'database/mysql'
    if original == target:
        return {'status': 'already_managed', 'storage_path': str(target), 'container': container}
    if target.exists():
        raise ValueError('Destination already exists; refusing to merge SQL data directories')
    # Never display container environment or include it in the migration report.
    environment = info['Config']['Env']
    env_map = dict(item.split('=', 1) for item in environment)
    password = env_map['MYSQL_ROOT_PASSWORD']
    schemas = [config['database'], config['workspace_database']]
    networks = list(info['NetworkSettings']['Networks'])
    if len(networks) != 1:
        raise ValueError('Explicit network reconciliation is required for this container')
    baseline = database_snapshot(password, schemas)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup_name = container + '-before-managed-' + stamp.lower()
    report_file = log_dir(project, 'storage') / (stamp + '-mysql-relocation.json')
    report = {'started_at': now(), 'status': 'copying', 'container': container,
              'original_container_id': info['Id'], 'rollback_container': backup_name,
              'original_storage_path': str(original), 'storage_path': str(target),
              'image_id': info['Image'], 'baseline': baseline}
    write_json(report_file, report)
    renamed, created = False, False
    try:
        print('Stopping MySQL for a verified cold copy.', flush=True)
        docker('stop', '--time', '60', container)
        if json.loads(docker('inspect', container))[0]['State']['Running']:
            raise ValueError('MySQL did not stop')
        shutil.copytree(original, target, symlinks=True)
        def tree_hashes(folder):
            return {str(path.relative_to(folder)): digest(path) for path in folder.rglob('*')
                    if path.is_file() and not path.is_symlink()}
        before_files, after_files = tree_hashes(original), tree_hashes(target)
        if before_files != after_files:
            raise ValueError('Cold copy checksums differ')
        report['cold_copy_file_count'] = len(before_files)
        print(f'Cold copy verified: {len(before_files)} files. Starting the managed database.', flush=True)
        docker('rename', container, backup_name)
        renamed = True
        if any('\n' in item for item in environment):
            raise ValueError('Unsupported multiline container environment')
        with tempfile.NamedTemporaryFile(mode='w', prefix='recording-db-env-', delete=False) as env_file:
            env_path = Path(env_file.name)
            os.chmod(env_path, 0o600)
            env_file.write('\n'.join(environment) + '\n')
        try:
            docker('create', '--name', container, '--platform', 'linux/amd64',
                   '--network', networks[0], '--network-alias', 'db',
                   '--publish', '127.0.0.1:3306:3306', '--env-file', str(env_path),
                   '--mount', f'type=bind,source={target},target=/var/lib/mysql',
                   '--label', 'recording_workspace.project=' + report.get('project_uuid', project.name),
                   info['Image'], *(info['Config']['Cmd'] or []))
            created = True
        finally:
            env_path.unlink(missing_ok=True)
        docker('start', container)
        checked = None
        for _ in range(60):
            try:
                checked = database_snapshot(password, schemas)
                break
            except Exception:
                time.sleep(.5)
        if checked != baseline:
            raise ValueError('Managed database rows do not match the pre-migration snapshot')
        report.update(status='verified', finished_at=now(), verified_tables=len(checked))
        runtime = {'format': 'recording-database-runtime', 'version': 1, 'container': container,
                   'image_id': info['Image'], 'storage_relative_path': 'mysql',
                   'catalog_schemas': schemas, 'migration_report': str(report_file.relative_to(project)),
                   'rollback_container': backup_name, 'rollback_storage_path': str(original),
                   'verified_at': now()}
        write_json(project / 'database/runtime.json', runtime)
        write_json(report_file, report)
        print(f'Verified every row in {len(checked)} tables. Original cold copy retained.', flush=True)
        return report
    except Exception as error:
        report.update(status='failed', error=type(error).__name__, finished_at=now())
        if created:
            subprocess.run(['docker', 'stop', '--time', '30', container], capture_output=True)
            subprocess.run(['docker', 'rm', container], capture_output=True)
        if renamed:
            docker('rename', backup_name, container)
        docker('start', container)
        report['rolled_back'] = True
        write_json(report_file, report)
        raise RuntimeError('Database relocation failed; original runtime restored. See storage log.') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', type=Path, required=True)
    parser.add_argument('--migrate-database', action='store_true')
    parser.add_argument('--migrate-logs', action='store_true')
    args = parser.parse_args()
    project = args.project_dir.resolve()
    identity = json.loads((project / 'project.json').read_text())['project_uuid']
    initialize_layout(project, identity, Path(__file__).resolve().parents[1])
    if args.migrate_logs:
        moved = migrate_legacy_logs(project)
        write_json(log_dir(project, 'storage') / 'log-relocation.json', {'at': now(), 'moved': moved})
    if args.migrate_database:
        result = relocate_mysql(project)
        print(json.dumps({key: result[key] for key in ('status', 'container', 'storage_path')}))


if __name__ == '__main__':
    main()
