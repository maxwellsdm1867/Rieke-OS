# Project unmount/remount

Unmount removes exactly one folder/identity from the mounted-project catalog.
It never deletes project files, recordings, SQL rows, annotations, exports, or
backups. A durable `unmounted` entry suppresses automatic sibling discovery;
opening the exact folder again clears that entry and retains project identity.
Unavailable saved paths can also be detached. Other catalog entries are retained.

Use **Projects** beside the current project name or **+** in the project rail.
Each project row has **Unmount project**; the active project also has a compact
unmount button beside **Projects**. Confirmation identifies the exact folder,
explains retention/remount, and defaults keyboard focus to Cancel.

Active unmount refuses pending renderer writes/uploads and drains admitted API
requests through the existing clean-close lifecycle. Background import and
transfer writers block closure. It flushes existing draft savers and preserves
the workspace navigation/session snapshot in this browser before close. That
snapshot restores once when this browser revisits the same project origin;
private mode, cleared browser storage or a changed origin cannot carry that view.
Desktop draft persistence continues through the established desktop bridge.
Scientific state remains in the project independently of browser drafts.

New renderer mutations are fenced during active unmount. No accepted operation
is aborted, no database process is killed, and no close success is fabricated.
Catalog detachment follows successful owned database shutdown. A catalog save
failure after shutdown reports **closed, still mounted** and returns the user to
the chooser to retry. Inactive running/owned services must be opened and unmounted
through their own lifecycle. Legacy active servers without managed clean close
refuse unmount and explain that their owner must close them first.

## Acceptance specification

- Discoverable compact project actions, no wordy new settings card.
- Cancel, Escape, default focus and Tab containment cause no catalog mutation.
- Inactive and active detach preserve scientific files and identity.
- Pending import/accept/export/transfer operations are blocked or drained safely.
- Stale async renderer callbacks cannot submit writes after active close begins.
- Remount explicitly selects the existing folder without recreating the project.
- Catalog suppression persists across restart; repeat detach is idempotent.
- Missing paths and unrelated or native copied identities are handled separately.
- Native ownership is respected: no forced process termination or global cleanup.
- Tests use only disposable tiny projects and an explicit owned project index.
- No live scientific data, live checkout, package build, install or deploy in this task.

## Verification

`python/tests/test_workspace_project_unmount.py` covers catalog isolation,
identity, file hashes, pending operations, in-flight request draining, ownership,
missing folders, restart/remount, desktop session authorization, close failure and
post-close registry failure. Existing project, native and desktop suites provide
related coverage. `workspace-app/src/projectUnmount.test.js` covers renderer write
fencing, draft-save refusal, inactive behavior and saved-view restoration.

`evidence/native-unmount-probe.py` exercises two tiny real MySQL fixtures using the
already installed private runtime. SQL content and scientific-file hashes are
compared after close/remount, while the second database stays accessible.
`evidence/verify-ui.mjs` exercises the actual React UI against a disposable catalog.
No package build is needed; the Vite preview compiles source for browser checks.
