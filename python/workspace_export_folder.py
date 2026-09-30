"""One stable local handoff folder per project, shared by every export format."""
from pathlib import Path

GUIDE = '''# Local project exports

Point Wheeler, MATLAB, or another analysis service at this folder once.
Each UUID subfolder is one export; keep its recipe and identities with its data.

- recordings.sqlite: frozen metadata for Wheeler and other SQL clients.
- matlab/recordings.mat: standard MATLAB data with embedded query, provenance and H5 references.
- recordings.json and recipe.json: exact source identities and export membership.
- annotation-return.json: tag-return format and exact allowed targets for SQLite exports.

Return new tags to <export UUID>/annotations/incoming/ as complete JSON messages.
The open project app picks these up automatically. Read annotation-return.json for examples.

Load recordings.mat with MATLAB load or a compatible MAT reader, then use
standard h5read to read lazy response pointers. No plotting GUI or scripts are
required. Keep original H5 files accessible and verify their source_sha256.
Generic UUID-based JSON selection masks can be explicitly imported in the app.
Do not edit completed artifacts; their checksums preserve each frozen export.

Use completed exports shown in the app's Export log. A failure.json marks an
unsuccessful export attempt. This folder belongs to one project; UUIDs must not
be replaced with filenames, cell labels, or row numbers.
'''


def prepare_export_root(project_dir):
    root = Path(project_dir) / 'exports'
    from workspace_desktop_paths import require_external_data_path
    require_external_data_path(root)
    root.mkdir(parents=True, exist_ok=True)
    guide = root / 'README.md'
    try:
        with guide.open('x') as handle: handle.write(GUIDE)
    except FileExistsError:
        pass  # Preserve an existing local guide.
    return root
