# Renderer view drafts

This module owns renderer view-draft load/save/recovery and its React lifetime
binding. Start at the import-free [createDesktopDraftSession](desktopDraftSession.js)
or the named React hook [useDesktopDraft](useDesktopDraft.js). Both files are public
entries; neither is a wrapper or private test seam. Their existing exports are
`createDesktopDraftSession` and `useDesktopDraft`, respectively. The factory's
records/generation/save queue and the hook's refs are lexical implementation details.
There is no module singleton, barrel, extra adapter or configuration object.

Read the [adopted draft contract](../../../docs/architecture/0.1.8-first-port-slices.md#renderer-draft-session-ownership),
[existing P07 obligations](../../../docs/architecture/0.1.8-first-port-slices.md#project-runtime-lifecycle-obligations)
and [ledger](../../../docs/architecture/core-module-ledger.json), record
`renderer.desktop-draft-session`. Native draft scope, filesystem persistence,
barrier/quit and process exit remain separate owners. Restored view/recipe/merge
hints are not scientific mutation consent.

## Interface, dependencies and lifetime

`createDesktopDraftSession({bridge, projectId, snapshot, restore, isBusy,
navigationIdentity = () => null, onState = () => {}})` starts loading immediately
and returns `flush`, `fresh`, `retry`, `preserveForQuit`, `close`. The existing bridge
provides `loadDraft(projectId)`, `saveDraft({projectId,value})` and
`resetDraft(projectId)`. Preserve the nested renderer envelope shown below.
Callbacks are in-process dependencies; the injected desktop bridge is the existing
local process/persistence seam with native and controlled test implementations.
The factory has zero imports and must stay usable without React.

A load restores only when its generation and captured navigation intent remain
current. Navigating away and back is still a later intent. Save calls serialize,
wait for loading and capture the latest view when their turn runs. A previous save
failure does not permanently break that queue. Closed, busy and not-ready states
reject; invalid identity, load failure or restore failure enters recovery. Keep
existing messages and permissive object shape checks; relocation is not permission
to tighten the schema. Only the unreadable recovery marker grants resetAllowed.
`fresh` is not generic permission to discard unread bytes. `preserveForQuit`
bypasses saving preserved bytes only while in recovery.

`close` suppresses late load publication; it does not cancel submitted native saves
or strengthen `fresh` into a generation-fenced operation. Project ID alone cannot
replace native path/version/scope validation.

`useDesktopDraft({projectId, snapshot, restore, busy, navigationIdentity})` returns
visible phase/message/resetAllowed/projectId state plus `startFresh`, `retry` and
`quitPreserving`. It uses the latest callbacks without restarting a same-project
session, binds that session to projectId, registers its flush with the shared
[desktopLifecycle](../desktopLifecycle.js), and attempts idle autosave every three
seconds. Project switch/unmount closes and unregisters the old session and clears
its timer. A previous project's recovery state is hidden immediately. App remains
the production hook consumer and recovery UI owner. Navigation, presentation,
project preferences and lifecycle fencing stay outside this folder.

## Executable public example

The [factory suite](desktopDraftSession.test.js) executes this shape in
`public example saves the unchanged nested renderer envelope through an injected bridge`:

```js
const writes = [], view = {route: {page: 'files'}, stores: {}};
const bridge = {
  loadDraft: async () => null,
  saveDraft: async payload => writes.push(payload),
};
const session = createDesktopDraftSession({
  bridge, projectId: 'example-project', snapshot: () => view,
  restore: () => {}, isBusy: () => false,
});
try {
  await session.flush();
  assert.deepEqual(writes, [{projectId: 'example-project', value: {
    format: 'rieke-renderer-draft', version: 1,
    projectId: 'example-project', value: view,
  }}]);
} finally {
  session.close();
}
```

This offline bridge writes to an array; it neither starts desktop services nor
proves disk durability. Recovery/load/intent ordering is characterized separately
in the existing public factory tests. The [hook suite](useDesktopDraft.test.js)
mounts the real hook/factory and calls public `flushDesktopDrafts`, controlling only
bridge responses and timers. It observes project/unmount cleanup, pending loads,
latest callbacks and stale recovery visibility, restoring globals in finally.
Do not replace it with source-text assertions or a fake hook.

## Checks and change procedure

From `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/renderer-drafts/desktopDraftSession.test.js src/renderer-drafts/useDesktopDraft.test.js src/presentationSessionsApp.test.js src/presentationSessionsIntegration.test.js src/desktopLifecycle.test.js src/projectUnmount.test.js src/apiCommandPolicy.test.js src/startupRestore.test.js src/workspaceNavigation.test.js
```

The real App/presentation harness must keep the real draft hook/factory; it needs
no resolver substitution for this move. The shared lifecycle identity stays at
`src/desktopLifecycle.js`. Preserve existing tests unless equivalent or stronger
public coverage is demonstrated. Isolated missing-unregister/close, stale-callback
and stale-recovery faults must fail public hook assertions; factory tests retain
navigation-intent, load-generation, serialization and unreadable-state detectors.
Never put mutation switches or private-inspection exports into production.

After shared integration, run the existing module-policy/import/discovery checks,
`npm test`, `npm run build` and the repository guard's explicit-base mapped checks
under the parent's coordinated test plan. From repository root the import check is
`python3 -B tools/architecture_guard.py check --language javascript`.
The reviewed multi-entry policy must cover both public files and ownership allow
rules for every production file; there is no private test-import exception here.

Agree on interface/dependency/error/lifetime/authority changes before editing.
Preserve three-second cadence, save envelope, current-callback behavior and
singleton lifecycle composition. Record exact source/check/review identity in the
existing ledger and adoption record. No dedicated draft latency benchmark exists;
`correctness.navigation` is an indirect interaction, not a draft timing measurement.
See the [benchmark registry](../../../benchmarks/registry.json) and
[benchmark guide](../../../docs/dev/benchmarks.md). Queue/bridge/recovery latency,
retained memory/timers, startup/build/disk/backup/shutdown and native quit remain
unmeasured. Source/frontend checks establish no native durability or performance.
