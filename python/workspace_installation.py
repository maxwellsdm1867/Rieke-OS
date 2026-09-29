"""Standard-library workspace entry point; initialization never starts a database."""
from __future__ import annotations

import json
from pathlib import Path

MANIFEST = '.rieke-workspace.json'
LAUNCHER = 'rieke-workspace.py'


def read_workspace(folder):
    folder = Path(folder).expanduser().resolve()
    path = folder / MANIFEST
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('Workspace manifest must be a small regular local file')
    value = json.loads(path.read_text())
    if (not isinstance(value, dict) or value.get('format') != 'rieke-workspace'
            or type(value.get('version')) is not int or value['version'] != 1):
        raise ValueError('Unsupported workspace manifest')
    return folder


def discover_workspace(directory):
    directory = Path(directory).resolve()
    for folder in (directory, *directory.parents):
        if (folder / MANIFEST).exists() or (folder / MANIFEST).is_symlink():
            return read_workspace(folder)
    return None


def initialize_workspace(folder, application):
    candidate = Path(folder).expanduser()
    if candidate.is_symlink():
        raise ValueError('Workspace root cannot be a symbolic link')
    folder, application = candidate.resolve(), Path(application).resolve()
    if folder.is_relative_to(application) or application.is_relative_to(folder):
        raise ValueError('Workspace storage must be separate from application code')
    if (folder / 'project.json').exists():
        raise ValueError('Choose the parent workspace directory, not an individual project')
    # Claim neither an existing entry point nor an existing configuration.
    for name in (MANIFEST, LAUNCHER):
        if (folder / name).exists() or (folder / name).is_symlink():
            raise ValueError(f'{name} already exists; nothing was overwritten. Launch the existing workspace.')
    folder.mkdir(parents=True, exist_ok=True)
    launcher = '''#!/usr/bin/env python3
"""Launch this workspace with its installed Rieke Lab OS checkout."""
from pathlib import Path
import subprocess
import sys

application = Path(APPLICATION)
if not (application / 'rieke.py').is_file():
    sys.exit('Application checkout moved or is missing. Edit application in this launcher to its new location.')
raise SystemExit(subprocess.call([
    sys.executable, str(application / 'rieke.py'), 'launch',
    '--workspace', str(Path(__file__).resolve().parent), *sys.argv[1:]
]))
'''.replace('APPLICATION', repr(str(application)))
    with (folder / LAUNCHER).open('x') as handle:
        handle.write(launcher)
    (folder / LAUNCHER).chmod(0o755)
    with (folder / MANIFEST).open('x') as handle:
        json.dump({'format': 'rieke-workspace', 'version': 1}, handle, indent=2)
        handle.write('\n')
    return folder


def select_workspace(folder, application):
    """Select an existing workspace or initialize a new root without replacing data.

    The preference is local to this application installation. Explicit command
    line/environment roots continue to take precedence on the next launch.
    """
    import os
    import uuid
    candidate = Path(folder).expanduser()
    if not candidate.is_absolute():
        raise ValueError('Choose an absolute workspace folder path')
    if candidate.is_symlink():
        raise ValueError('Workspace root cannot be a symbolic link')
    root, application = candidate.resolve(), Path(application).resolve()
    if root.is_relative_to(application) or application.is_relative_to(root):
        raise ValueError('Workspace storage must be separate from application code')
    if root.exists() and not root.is_dir():
        raise ValueError('Workspace root must be a directory')
    if (root / 'project.json').exists():
        raise ValueError('This is a project folder. Choose its parent as the workspace root, then open the project.')
    existing = (root / MANIFEST).exists() or (root / MANIFEST).is_symlink()
    if existing:
        read_workspace(root)
    else:
        initialize_workspace(root, application)
    from workspace_projects import list_managed_projects
    list_managed_projects(root)  # Validate existing startup preferences before selecting.
    runtime = application / '.rieke-runtime'
    runtime.mkdir(exist_ok=True)
    preference = runtime / 'workspace-selection.json'
    if preference.is_symlink():
        raise ValueError('Workspace preference must be a regular local file')
    temporary = runtime / f'.workspace-selection-{uuid.uuid4()}.tmp'
    try:
        with temporary.open('x') as handle:
            json.dump({'version':1,'managed_root':str(root)},handle)
            handle.write('\n')
        os.replace(temporary,preference)
    finally:
        temporary.unlink(missing_ok=True)
    return root
