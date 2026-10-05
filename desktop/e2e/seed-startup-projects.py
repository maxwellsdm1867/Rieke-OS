"""Create disposable empty/sparse projects for the desktop startup smoke test."""
import json
import os
from pathlib import Path
import sys

application, home = map(Path, sys.argv[1:3])
runtime = Path(sys.argv[3]) if len(sys.argv)>3 else application / 'desktop/build/runtime'
sys.path.insert(0, str(application / 'python'))
state = home / 'state/backend'
os.environ.update(RIEKE_DESKTOP_MODE='1', RIEKE_DESKTOP_USER_STATE=str(state),
                  RIEKE_DESKTOP_RUNTIME=str(runtime))
from workspace_projects import create_project

projects = home / 'projects'
small = create_project(projects, 'Startup small project')
large = create_project(projects, 'Startup 200 GB project')
database = Path(large['path']) / 'database/mysql'
database.mkdir(exist_ok=True)
with (database / 'unavailable-data.ibd').open('wb') as file:
    file.truncate(200 * 1024**3)
recordings = Path(large['path']) / 'raw-uploads'
for i in range(10000):
    (recordings / ('unread-data-%05d.h5' % i)).touch()
(recordings / 'missing-recording.h5').symlink_to(home / 'absent-recording.h5')
preferences = state / 'preferences'
preferences.mkdir(parents=True, exist_ok=True)
(preferences / 'workspace-selection.json').write_text(json.dumps({'version': 1, 'managed_root': str(projects)}))
(home / 'projects.json').write_text(json.dumps({'small': small, 'large': large}, indent=2))
