"""Create one isolated project and an oracle-backed, donor-free Symphony H5."""
import json
import os
from pathlib import Path
import sys
import uuid

import h5py
import numpy as np

root, runtime = (Path(value).resolve(strict=True) for value in sys.argv[1:])
home = root / 'home'
if not root.name.startswith('rieke-packaged-ui-e2e-startup-quit-') or Path.home() != home:
    raise ValueError('Expected the private startup/quit fixture HOME')
sys.path.insert(0, str(runtime / 'application/python'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from organization_e2e_fixture import generate, specification, verify_raw
from workspace_projects import create_project

state = home / 'state/backend'
os.environ.update(RIEKE_DESKTOP_MODE='1', RIEKE_DESKTOP_USER_STATE=str(state),
                  RIEKE_DESKTOP_RUNTIME=str(runtime))
project = create_project(home / 'projects', 'Synthetic startup quit fixture')
preferences = state / 'preferences'
preferences.mkdir(parents=True, exist_ok=True)
(preferences / 'workspace-selection.json').write_text(json.dumps({
    'version': 1, 'managed_root': str(home / 'projects')}))
oracle = specification(str(uuid.uuid4()))
recording = home / 'synthetic-startup-quit.h5'
generate(recording, oracle, np, h5py)
verify_raw(recording, oracle, np, h5py)
print(json.dumps({'project': project, 'recording': str(recording),
                  'epoch': oracle['epochs'][0], 'epochs': oracle['counts']['epochs']}))
