# Presentation sessions

This module owns in-memory route snapshots, Protocol/Explorer/Stores fallbacks,
checkpoint replacement and deletion pruning for one App mount. Start with the
[public factory and behavioral contract](workspacePresentationSessions.js).
Its methods are `remember`, `read`, `checkpoint`, `restore`, `pruneDeleted`,
`readDraft`, `rememberDraft` and `authoredIntent`; `AUTHORED_DRAFT_LIMITS` declares the bounded
authored-field contract. The original snapshot methods retain their behavior.
The returned values preserve existing shallow references and permissive inputs,
except a protocol route snapshot is shallow-copied when its tracePreference differs
from that protocol’s latest saved choice. Only that presentation field is replaced;
route-specific focus and scientific authority remain unchanged.

App owns navigation validation, stable callbacks, persistence, project/unmount
composition and scientific authority. Restore replaces stores before App validates
the returned route. Retained presentation does not establish scientific consent.
The pure factory has no I/O or singleton. Draft fields are scoped by stable
project-contained destination and entity identity, never labels or row offsets.
`rememberDraft(route,key,value)` accepts strings/booleans; undefined retires an
entry. Limits are 256 entries, 8 KiB identity, 16 KiB field text, 512 KiB aggregate.
Rejected writes remain visible in the editor and block checkpoint acknowledgment
until corrected; old unfinished entries are never silently evicted. Restore
validates the authored collection before replacement; older checkpoints omit it.
Deletion pruning removes drafts whose exact identity includes a deleted UUID.
`authoredIntent()` counts local authored write/clear attempts, including rejected
ones. App combines it with navigation intent so a delayed draft load cannot
replace new input; recovery identities still hydrate independently. Reads and
restoration do not advance this counter.

`useAuthoredDraft` returns `[value,setValue,{edited,error,adopt,clear}]`. Canonical
async hydration calls `adopt` and cannot replace edited/restored text or create
an authored entry. Confirmed successful saves call `clear`; failures preserve
text. Reopening an editor restores its fields, not its confirmation, preview,
operation authority or submission. Existing Inspector/Protocol snapshots and
operation recovery identities retain their current owners.

Outside consumers use `workspacePresentationSessions.js` for the pure owner or
`useAuthoredDraft.js` for the named `useAuthoredDraft` hook and `AuthoredDraftScope`
provider. The hook binds text/options to the retained destination or project-shell
scope, using the same checkpoint and desktop DraftStore; it adds no disk store. The pure pruning
helper in `internal/` is private. New production files need a catalog ownership
allow rule; there is no automatic internal import exemption. The helper's own
colocated test is the sole private test-import exception. Public contract tests
belong beside the factory; retain their behavior and real App composition tests.

From `workspace-app`, run:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/presentation/workspacePresentationSessions.test.js src/authoredDrafts.test.js src/presentation/internal/deletedSourceSelections.test.js src/presentationSessionsApp.test.js src/presentationSessionsIntegration.test.js src/workspace-navigation/workspaceNavigation.test.js src/renderer-drafts/desktopDraftSession.test.js src/projectUnmount.test.js
```

The [App characterization](../presentationSessionsApp.test.js) and
[integration case](../presentationSessionsIntegration.test.js) exercise real
App/history/draft/Protocol composition via the existing harness; do not substitute
this owner. Run `npm test` and `npm run build` for frontend closure checks.

The existing [module ledger](../../../docs/architecture/core-module-ledger.json)
record `presentation-sessions` owns provenance and benchmark links
`ui.mounted.inspector.return` and `correctness.navigation`. These are indirect
flows, not presentation-owner timings. Startup, first useful result, memory,
disk, build, backup and shutdown costs remain unmeasured for this folder pilot;
checkpoint/prune cost and retained-map memory also remain gaps. Do not copy
historical receipts into new evidence or infer speed from relocation.

## Change procedure

Work on one selected responsibility at a time. Read the public contract and
existing evidence before editing. Agree on changes to the interface, dependencies,
invariants, errors or lifetime first; preserve behavior in an internal replacement.
There is no module configuration or I/O adapter to introduce here. Keep existing
tests unless equivalent behavior coverage is demonstrated. Finish with public and
App composition checks, the import guard and frontend build, then record exact
source/evidence and independent review in the ledger. Folder organization alone
proves neither performance nor additional behavioral depth. Deferred native,
backend, desktop and import/export qualification are outside this module task.
