"""Small durable launcher preference; no database credentials or source payloads."""
from pathlib import Path
import json
import uuid
from recording_workspace import write_json


def read_registry(root):
    path = Path(root) / '.rieke-os.json'
    if path.is_symlink():
        raise ValueError('Startup registry cannot be a symbolic link')
    if not path.exists():
        return {'format':'rieke-os-startup','version':1,'last_project_uuid':None}
    if path.stat().st_size > 64 * 1024:
        raise ValueError('Startup registry is unexpectedly large')
    value = json.loads(path.read_text())
    if not isinstance(value,dict) or value.get('format') != 'rieke-os-startup' or value.get('version') != 1:
        raise ValueError('Startup registry is invalid; preserve it and repair its configuration')
    if value.get('last_project_uuid') is not None:
        uuid.UUID(value['last_project_uuid'])
    return value


def remember_project(root, identity):
    value = read_registry(root)
    value['last_project_uuid'] = str(uuid.UUID(identity))
    write_json(Path(root) / '.rieke-os.json', value)
