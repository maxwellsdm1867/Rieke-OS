# Tree selection reads

Start with the [public factory and JSDoc](treeSelectionReader.js) and the
[adopted P03 contract](../../../docs/architecture/0.1.8-first-port-slices.md#tree-selection-reader).
This module owns stateless, ordered first-epoch traversal and complete bounded
ranges. Its sole export is `createTreeSelectionReader`; returned operations are
`firstEpoch` and `rangeEpochIds`. Outside consumers import this file directly.
Helpers stay lexical; there is no barrel or private import exception.

The existing injected `requestPage(scope, options, signal)` seam substitutes owned
HTTP for tests. Its default preserves tracked `api` POST and frozen-context routing.
Pure request shaping remains in shared `../pagedTreeRequest.js`; shared selection
combiners, ancestor-cache leases and browser readiness retain their existing owners.
No additional adapter, cache or scientific authority belongs here.

`firstEpoch` resolves the original DTO or undefined, following only first branches.
Expected revision takes precedence. Range indices are inclusive, normalized,
nonnegative absolute positions in one branch; callers supply matching scope/path
and page offset. Preserve 60-row stepping, the 1,000-position limit, exact server
order and synchronous supplied-page completion. Missing rows, wrong epoch kind
and changed revisions fail without returning a partial range. Errors retain their
original transport object; cancellation throws/rejects AbortError. The reader does
not newly validate all DTO fields or reconstruct scientific values.

[PagedTree](../components/PagedTree.jsx) owns gesture anchors, abort controllers,
committed scope generations, continuity and final publication, including changed
selection checks. Those fences remain necessary after a reader resolves. Selection
continuity never establishes write readiness, inclusion or project/profile authority.

## Runnable consumer example

From `workspace-app`, run this offline example. The
[public contract test](treeSelectionReader.test.js), named "documented consumer
example preserves sync, Promise and cancellation results", executes this call shape
and asserts its results and errors through the same public interface.

```sh
node --input-type=module <<'JS'
import {createTreeSelectionReader} from './src/tree-selection/treeSelectionReader.js';
const page = offset => ({kind:'epochs', revision:'r', path:['opaque'], offset,
  epochs:Array.from({length:60}, (_,i) => ({epoch_uuid:`epoch-${offset+i}`}))});
const reader = createTreeSelectionReader({requestPage:async (_scope, options) => page(options.offset ?? 0)});
const scope = {expectedRevision:'r'}, supplied = page(0);
const first = await reader.firstEpoch(scope, {path:['opaque'], revision:'r'});
const samePage = reader.rangeEpochIds(scope, {page:supplied, firstIndex:0, lastIndex:1});
const pending = reader.rangeEpochIds(scope, {page:supplied, firstIndex:59, lastIndex:60});
console.log(first.epoch_uuid, Array.isArray(samePage), pending instanceof Promise, await pending);
const controller = new AbortController(); controller.abort();
try { await reader.firstEpoch(scope, {path:['opaque'], signal:controller.signal}); }
catch (error) { if (error.name !== 'AbortError') throw error; console.log(error.name); }
try { reader.rangeEpochIds(scope, {page:supplied, firstIndex:0, lastIndex:0, signal:controller.signal}); }
catch (error) { if (error.name !== 'AbortError') throw error; console.log(error.name); }
JS
```

## Verification and change procedure

With `RIEKE_TEST_DOM_MODULE` unset, from `workspace-app`:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/tree-selection/treeSelectionReader.test.js src/pagedTreeLifecycle.test.js src/pagedTreeRequest.test.js src/inspectorTreeAuthority.test.js src/stableContentInert.test.js src/candidateContinuity.test.js src/architectureModulePolicy.test.js src/architectureImports.test.js src/testDiscovery.test.js
```

Public tests preserve order, identity, errors, limits and cancellation; retain actual
PagedTree and Inspector composition tests for synchronous publication and stale
scope/selection rejection. Keep the reader API interception in
`../test-support/pagedTreeHarness.js` aligned with its actual import path.
Do not replace behavior tests with source-text or lexical-helper assertions.

Review changes to the interface, dependencies, scientific invariants, errors or
lifetime before implementation. Preserve existing tests unless equivalent coverage
is demonstrated. New production files require catalog ownership allow rules.
Run the [catalog](../../../docs/architecture/adopted-port-checks.json) guard from
the repository root (`python3 -B tools/architecture_guard.py check --language javascript`)
and explicit-base plan/mapped checks per root guidance. Finish with `npm test`
and `npm run build` for frontend closure, coordinated with other workers.
Record exact source/evidence and independent review; these checks confer no native
or release qualification.

The [ledger](../../../docs/architecture/core-module-ledger.json) record
`tree-selection` / `FE05-ordered-tree-selection` retains benchmark links
`ui.mounted.inspector.first`, `ui.mounted.inspector.return`, `correctness.navigation`.
These describe indirect mounted flows, not isolated selection timings. Native
restoration/authority, tree-range timing, traversal cancellation, UI scroll/paint
and total retained memory remain unmeasured. Startup/build/disk/backup/shutdown
costs gain no evidence from relocation. Do not copy historical receipts or infer
performance improvements from this folder change.
