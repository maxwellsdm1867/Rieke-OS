# Group-save sessions and recovery

Start with the [public owner](groupAnnotationRecovery.js) and its
[colocated behavioral tests](groupAnnotationRecovery.test.js). The named exports
are `createGroupSaveSession`, `groupAnnotationRecovery` and `confirmGroupReceipt`.
This module owns exact request retention, first-save admission, retry, receipt
validation and deferred preview release. The records, admission constants,
listeners and transition helpers are lexical implementation details in the entry.
There is no barrel, private-file test exception or runtime test injection export.

Read the existing [adopted contract](../../../docs/architecture/0.1.8-first-port-slices.md#group-save-session-ownership)
and [ledger](../../../docs/architecture/core-module-ledger.json), record `group-save`.
Outside consumers import only `groupAnnotationRecovery.js`. Any new production
file needs a reviewed catalog ownership allow rule. The compatibility receipt
re-export in `../treeGroupQueryTags.js` remains available to inverse consumers.

## Interface and lifetime

A verified preview supplies the selection UUID, profile, count, request adapter
and project captured **before** its preview request began. Its frozen handle
exposes these selection/profile/count facts plus `save`, `release`, `canPublish`.
The recovery singleton exposes `subscribe`, `version`, `project`, `currentProject`,
`view`, `dismiss`, `onChange`, `retry`. Views contain compact copies, never mutable
operation records. Changing project does not clear recovery. Keep the singleton
at renderer-module lifetime, including across editor dismissal and project changes.
Do not add per-editor construction, unmount reset, persistence or eviction.

Preview consumes no slot. First save reserves before dispatch and freezes exact
selection/operation UUID, tag and profile. Four retained records maximum, including
rejected rows until dismissed; admission is `JSON.stringify(body).length*4+4096`
within 16 KiB, a compact-request estimate, not a heap measurement. Failed admission
attaches no operation. Undo admission can leave a reserved ready row pinned.
Concurrent calls share dispatch/undo; confirmed retries reuse the accepted receipt.

Only unsaved 400/409 is terminal refusal. Saved errors, network failures and
malformed receipts remain uncertain and cannot be dismissed or retargeted. A
refused/detached handle cannot redispatch. Keep error messages and the 1024-character
display-error truncation. Receipt checks preserve exact identity/count arithmetic;
absent persistence remains accepted, while present database state must be committed.
This check does not establish native transaction or recovery-copy durability.

Release is best effort once, deferred through ready/pending/unconfirmed; it is not
cancellation or rollback. Save/retry/publication use original-project fences.
Preserve cache invalidation, event ordering and project-scoped undo publication.
Recovery events carry original project and useMutationUndo filters them. Retained
requests contain no target graphs. Backend frozen membership remains authoritative.

## Executable public example

The test named `public example: uncertain save retries unchanged and releases before
publishing` in the [public suite](groupAnnotationRecovery.test.js) executes this
sequence with a controlled request adapter, a saved 507 followed by a valid receipt,
and assertions on exact request identity, release count, publication and undo:

```js
const session = createGroupSaveSession({
  project: originalProject, selectionUuid, profileUuid, count, request,
});
const original = {tag, profileUuid};
// For this example, the first call is known to fail with saved:true.
await assert.rejects(session.save(original), /Recovery copy unconfirmed/);
await session.release(); // Editor close requests release; uncertainty keeps it pinned.
const result = await session.save(original); // Retry without changing tag or author.
await session.release();
if (session.canPublish()) publish(result);
```

In product callers, present failures and let the original operation be retried;
this example is not an instruction to automatically retry arbitrary failures.
A terminal refusal requires dismissal/reopening rather than replay. A recovery
panel may call `groupAnnotationRecovery.retry(operationUuid)` for the same retained
operation. Keep the existing mounted panel/composer/undo tests: they cross the
same seam and establish caller composition beyond this executable example.

## Dependencies and checks

`mutationUndo` and `epochResourceCache` are in-process shared owners. Browser crypto
supplies operation UUIDs. The injected request is the existing remote-but-owned
transport seam, exercised by production API and controlled test adapters. Query
construction/preview validation remain in treeGroupQueryTags; React UI, project
composition and shared undo remain outside. No additional adapter is justified.

From `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/group-save/groupAnnotationRecovery.test.js src/treeGroupLifecycleWorkflow.test.js src/treeGroupAnnotationWorkflow.test.js src/mutationUndo.test.js src/mutationUndoWorkflow.test.js src/apiCommandPolicy.test.js
```

For integration closure, run the existing `architectureModulePolicy.test.js`,
`architectureImports.test.js` and `testDiscovery.test.js`, then `npm test` and
`npm run build`. From the repository root run
`python3 -B tools/architecture_guard.py check --language javascript`; use its
explicit-base plan/mapped checks as described in the architecture guide.

Preserve the existing early-release, retry-identity, terminal-redispatch and
post-await-project behavioral fault detectors, plus byte/slot/ready/coalescing and
late-publication assertions. Deliberate faults belong in isolated disposable source
copies, never services or user data. The guard catches unauthorized imports/exports;
it is not a semantic proof. Keep meaningful public tests unless equivalent or
stronger coverage is demonstrated.

Agree on interface, dependency, authority, error or lifetime changes before editing;
record exact source/check/review provenance in the existing adoption record/ledger.
Folder relocation provides locality, not extra behavioral depth or performance.
There is no dedicated group benchmark (`benchmark_case_ids` stays empty).
`db.native.tag_latency` remains unsupported; retention latency, whole-heap memory,
native transaction timing, startup, first useful result, disk, build, backup and
shutdown costs remain unmeasured. Frontend checks grant no native qualification.
