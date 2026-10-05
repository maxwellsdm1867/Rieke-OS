# Session undo

Start with `mutationUndo.js` for `createUndoHistory`, the canonical `mutationUndo`
singleton, admission/target helpers and existing limits. `useMutationUndo.js` owns
`persistUndo`, React lifetime and browser/Electron shortcut installation;
`ui/UndoControls.jsx` presents that state. Each named entry remains public; no
barrel, new singleton or generic mutation facade is introduced.

Undo is session memory, never part of drafts, project snapshots or exports. Limits
remain 50 actions and 512 KiB estimated memory; oversized ordinary target gestures
are refused as whole undo steps. Project switches clear history. Pending work blocks
undo; repeated shortcuts cannot race. Original target UUIDs and own author revisions
survive navigation. An inverse creates a new revision and rebases only the nearest
matching preceding edit when its expected revision matches the original prior state.

Unconfirmed ordinary edits clear unsafe history; ordinary inverse SQL success with
recovery failure cannot be replayed as if it never happened. Group inverse recovery
retains the same durable operation instead of inventing another inverse. A conflict
keeps its existing refusal semantics and never automatically retargets current rows.
Temporary search-inclusion undo remains local to the original viewer and has no
scientific mutation path. Text inputs preserve native editing undo; saved empty tag
input handoff and Electron/browser dispatch still share one authoritative gesture.

Deleting this owner distributes serialization, original-target and revision-rebase
knowledge to editors. A smaller export list would hide needed capabilities rather
than reduce caller knowledge. KEEP the factory, singleton, hook and shortcut entries
as separate responsibilities; folder co-location adds navigation value, not new depth.
History logic is in-process; React/DOM and injected shortcut bridges are
local-substitutable; mutation requests are remote but owned. Native commit/recovery
and actual Electron dispatch remain outside source-test qualification.

From `workspace-app`, with the integration imports reconciled:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/mutationUndo.test.js src/mutationUndoWorkflow.test.js
```

These existing public examples exercise original targets, pending/failure outcomes,
conflicts, size limits, shortcut arbitration and saved-but-unconfirmed inverses.
Preserve the singleton's one canonical import identity in api, App and tests.
No actual scientific write, native recovery or memory benchmark is authorized here.
