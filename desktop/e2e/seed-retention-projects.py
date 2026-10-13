"""Create two empty owned projects; no user project or recordings are accepted."""
import json
import os
from pathlib import Path
import sys

application, home, runtime = map(lambda value: Path(value).resolve(), sys.argv[1:4])
if not home.name == 'home' or not home.parent.name.startswith('disco-retention-native-'):
    raise ValueError('Expected freshly owned native-retention HOME')
sys.path.insert(0, str(application / 'python'))
state = home / 'state/backend'
os.environ.update(HOME=str(home), RIEKE_DESKTOP_MODE='1', RIEKE_DESKTOP_USER_STATE=str(state),
                  RIEKE_DESKTOP_RUNTIME=str(runtime),
                  RIEKE_PROJECT_INDEX=str(state / 'preferences/project-index.json'),
                  RIEKE_PREFERENCES_DIR=str(home / '.rieke-os'),
                  RECORDING_WORKSPACE_ROOT=str(home / 'projects'),
                  RIEKE_MANAGED_PROJECTS_ROOT=str(home / 'projects'))
from workspace_projects import create_project

projects = home / 'projects'
records = [create_project(projects, name) for name in ['Retention project A', 'Retention project B']]
preferences = state / 'preferences'
preferences.mkdir(parents=True, exist_ok=True)
(preferences / 'workspace-selection.json').write_text(json.dumps({'version': 1, 'managed_root': str(projects)}))
(home / 'projects.json').write_text(json.dumps(records, indent=2))
