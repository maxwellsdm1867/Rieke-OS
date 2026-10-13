# Local source integration for UI retention

This isolated branch starts from newest local UI `386e72d` and merges
`86e395a` (released `add33d1`, scoped reads, overview caching, trace controls and
startup diagnostics). Merge commit: `d806f0f`. The intended managed-library
commit `4a9d247` was applied as `5929d98`; original branches remain untouched.

Conflict decisions:

- Retain both adoption-history sections, including the startup and scoped-read contracts.
- Retain release trace zoom/pan tests and newest UI trace descriptor checks; use the existing `Viewer` test import name.
- Preserve bounded discovery documentation alongside the new shared-library retention semantics.
- Keep DataStores count-column styling while using the correct shared-library deletion explanation.
- Recompute only reviewed merged-file byte witnesses for `recording_workspace.py` and `workspace_api.py`; dynamic-loader AST targets were not changed.

The integration source is committed separately from the upcoming retention work.
Raw diagnostic artifacts remain local, explicitly ignored under
`docs/dev/ui-cache-design-evidence-2026-10-13/`; the linked reports and harness
identities preserve attribution. Initial integration tests and later exact-source
gates are recorded separately; this note does not establish installed-build or
release qualification.
