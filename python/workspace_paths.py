"""Reject nested workspace/project roots before creating storage or preferences."""
from pathlib import Path


def workspace_root(folder, *, allow_workspace_descendant=False):
    candidate = Path(folder).expanduser()
    if candidate.is_symlink():
        raise ValueError('Workspace root cannot be a symbolic link')
    root = candidate.resolve()
    if root.exists() and not root.is_dir():
        raise ValueError('Workspace root must be a directory')
    # Resolve ancestor aliases too: alias/imports/new-root must not create a
    # second workspace inside the project reached by that alias.
    for ancestor in (root, *root.parents):
        marker = ancestor / 'project.json'
        if marker.exists() or marker.is_symlink():
            raise ValueError('Choose the parent workspace directory, not a project folder or a folder inside a project')
        marker = ancestor / '.rieke-workspace.json'
        if not allow_workspace_descendant and ancestor != root and (marker.exists() or marker.is_symlink()):
            raise ValueError(f'This folder is inside an existing workspace. Select its root: {ancestor}')
    return root
