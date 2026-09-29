"""Validate workspace boundaries before creating directories or preferences."""
from pathlib import Path


def workspace_root(folder):
    candidate = Path(folder).expanduser()
    if candidate.is_symlink():
        raise ValueError('Workspace root cannot be a symbolic link')
    root = candidate.resolve()
    if root.exists() and not root.is_dir():
        raise ValueError('Workspace root must be a directory')
    for ancestor in (root, *root.parents):
        marker = ancestor / 'project.json'
        if marker.exists() or marker.is_symlink():
            raise ValueError('Choose the parent workspace directory, not a project folder or a folder inside a project')
        workspace = ancestor / '.rieke-workspace.json'
        if ancestor != root and (workspace.exists() or workspace.is_symlink()):
            raise ValueError(f'This folder is inside an existing workspace. Select its root: {ancestor}')
    return root
