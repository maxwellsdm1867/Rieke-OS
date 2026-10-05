# Presentation sessions

This module owns in-memory route snapshots, Protocol/Explorer/Stores fallbacks,
checkpoint replacement and deletion pruning for one App mount. Start with the
[public factory and behavioral contract](workspacePresentationSessions.js).
Its five methods are `remember`, `read`, `checkpoint`, `restore`, `pruneDeleted`.
The returned values preserve existing shallow references and permissive inputs.

App owns navigation validation, stable callbacks, persistence, project/unmount
composition and scientific authority. Restore replaces stores before App validates
the returned route. Retained presentation does not establish scientific consent.
No adapter, I/O, project reset, eviction or new singleton belongs in this module.

Outside consumers import only `workspacePresentationSessions.js`. The pure pruning
helper in `internal/` is private. New production files need a catalog ownership
allow rule; there is no automatic internal import exemption. The helper's own
colocated test is the sole private test-import exception. Public contract tests
belong beside the factory; retain their behavior and real App composition tests.

From `workspace-app`, run:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/presentation/workspacePresentationSessions.test.js src/presentation/internal/deletedSourceSelections.test.js src/presentationSessionsApp.test.js src/presentationSessionsIntegration.test.js src/workspaceNavigation.test.js src/renderer-drafts/desktopDraftSession.test.js src/projectUnmount.test.js
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
