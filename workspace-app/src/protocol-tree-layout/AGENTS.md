# Protocol tree layout

This module loads the saved protocol split order and serializes versioned view
layout writes. The import-free named [createTreeLayoutSaver](treeLayoutPersistence.js)
and default [useProtocolTreeLayout](useProtocolTreeLayout.js) are both public
entries. Their queue/ref state stays lexical; there is no barrel, singleton,
private test interface or configuration framework.

Read the [adoption record](../../../docs/architecture/0.1.8-first-port-slices.md),
[ledger](../../../docs/architecture/core-module-ledger.json) record
`FE14-view-preferences-and-layout`, and [architecture](../../../ARCHITECTURE.md).
App owns composition, readiness display and retry UI. Summary opt-in, tree
selection, scientific grouping, group recovery and export membership retain their
separate owners. Layout and initial recipe hints grant no mutation authority.

## Public behavior and dependencies

`createTreeLayoutSaver({version, splitOrder, write, onState = () => {}})` returns
`remember(fields)` and `retry()`. `write` receives `{split_order, expected_version}`;
a successful receipt must contain exactly the submitted order and version + 1.
Writes serialize; edits during a write coalesce to the latest desired order.
Version zero writes even an unchanged default. A positive acknowledged version
and unchanged order need no write. Arrays are copied into saved/desired state.

`onState` publishes `saving`, `saved` or `error` with the acknowledged version.
Failure retains desired order/version for explicit retry. Caught write failures
are reported as `error.message` through onState; they do not reject flush. A bad
receipt reports `Tree save returned an invalid receipt. Reload before retrying.`
Preserve this error contract; there is no automatic backoff or timeout policy.

`useProtocolTreeLayout(id, initial)` depends on React, [api](../api.js) and the
saver. It returns `order`, `remember`, `ready`, `error`, `save`, `retrySave`,
`reload`. It GETs `/protocols/${id}/tree-layout` with an AbortSignal and PUTs to
that endpoint through the saver. A load requires an array `split_order` and
integer `version`; invalid data reports `Invalid saved tree layout.` Keep current
validation rather than adding stronger bounds during organization.

The initial value is captured for the whole mount, including protocol changes.
A supplied array overrides saved order; a string is comma-split, trimmed and
filtered after loading. Without initial input, saved order is used. `remember`
updates local order immediately and does not return or await the saver promise.
Readiness and load errors are distinct from save status. Cleanup aborts loading
and suppresses late load/error/save publication; it does not cancel accepted
writes or clear the old saver. While a replacement load is pending, `remember`
and `retrySave` can still reach that prior saver. App gates main Inspect/Overview content through
readiness; incoming Workbench owns its frozen scope/layout and mounts independently; do not silently strengthen the hook's authority or reset behavior.

## Executable public example

The [saver suite](treeLayoutPersistence.test.js) executes
`public example: the first validated default layout is persisted before a query update can replace its fallback`:

```js
const writes = [];
const saver = createTreeLayoutSaver({
  version: 0, splitOrder: ['date', 'cell'],
  write: async body => {
    writes.push(body);
    return {version: 1, split_order: body.split_order};
  },
});
await saver.remember(['date', 'cell']);
await saver.remember(['date', 'cell']);
assert.deepEqual(writes, [{split_order: ['date', 'cell'], expected_version: 0}]);
```

This offline writer proves the public call shape, not server persistence. All
three original saver scenarios and assertions remain; direct wrong-version and
altered-order receipt cases require errors at the acknowledged version and exact
retry bodies. The [real-hook suite](useProtocolTreeLayout.test.js)
uses the actual hook, saver, API serialization and lifecycle write tracking with
controlled fetch; responses can resolve after abort. It covers invalid/failed
loads, reload, mount-scoped overrides, late success/error/save publication,
serialization, retry/receipt mismatch and retained old-saver behavior. It restores
fetch, unmounts and drains accepted requests in finally; no private refs or fake
hook replace production behavior.

## Checks and changes

From `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/protocol-tree-layout/treeLayoutPersistence.test.js src/protocol-tree-layout/useProtocolTreeLayout.test.js src/presentationSessionsApp.test.js src/presentationSessionsIntegration.test.js src/workflowResponsiveness.test.js src/importMergeWorkflow.test.js
```

The App presentation/workflow harnesses still intentionally substitute layout;
their resolver strings follow the new public path and their virtual IDs remain
unchanged. Those suites do not replace real-hook coverage. Recursive discovery
already finds both nearby suites. After shared integration, the parent coordinates
module/import/discovery regression checks, explicit-base mapped checks, full
`npm test` and `npm run build`. From repository root the source import check is
`python3 -B tools/architecture_guard.py check --language javascript`.

Discuss interface, dependency, error, lifetime and authority changes before
editing; update the existing adoption record and ledger. Preserve exact default
export and named saver export, zero saver imports and the hook's three direct
dependencies. Isolated missing-abort, late-publication, changed-initial and cleared
old-saver faults must fail public assertions. Version-zero and serialization tests
remain behavior detectors. Do not add mutation toggles or inspection exports.

See the canonical [benchmark registry](../../../benchmarks/registry.json) and
[benchmark guide](../../../docs/dev/benchmarks.md). No dedicated layout latency,
coalescing cost or memory benchmark exists. `correctness.navigation` is indirect
interaction evidence. Harness changes alter benchmark suite identity; preserve
historical receipts and do not claim comparability or speed improvements. Native
packaging, installed behavior and scientific import/export qualification remain
separate gates. Frontend source tests provide none of that qualification.
