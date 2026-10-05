# Workspace navigation

Start at the import-free [route/session helpers](workspaceNavigation.js) or the
React [useWorkspaceNavigation](useWorkspaceNavigation.js) hook. Both are public:
helpers export `WORKSPACE_PAGES`, `validWorkspaceRoute`, `routeAddress`,
`makeWorkspaceRoute`, `resolveProtocolSession`, `restoredEpochFocus` and
`snapshotExplorerState`; the hook retains its default export. No barrel,
singleton, private test API or configurable router is introduced.

Read the [adoption record](../../../docs/architecture/0.1.8-first-port-slices.md),
[ledger](../../../docs/architecture/core-module-ledger.json) inventory
`FE07-route-history-intent` and [architecture](../../../ARCHITECTURE.md).
App owns gestures/composition; [presentation](../presentation/AGENTS.md) owns
checkpoints and [renderer drafts](../renderer-drafts/AGENTS.md) owns persistence.
[incomingMergeIntent](../incomingMergeIntent.js) remains the separate live-consent
owner. Restored hints never grant scientific mutation consent.

## Interfaces, errors and lifetime

`WORKSPACE_PAGES` is the existing mutable destination Set. `validWorkspaceRoute`
checks known page/string key, requiring string protocol on protocol pages; it is
not a full route validator. `makeWorkspaceRoute(page, details, key)` throws
`Unknown workspace destination` for unknown pages. `routeAddress` retains encoded
protocol-before-cell identity precedence.

`resolveProtocolSession({saved, recipe, inspection, restore})` gives restore+saved
priority and preserves its object identity. Recipes separate browsing/export
filters; explicit inspection resets focus/offset/filter state while retaining
compatible preferences. Ordinary reopening resets design/tree modes; history
restoration retains them. `restoredEpochFocus` honors explicit cleared null.
`snapshotExplorerState` preserves draft/revision IDs/counts while omitting heavy
epoch/diff/content hashes and preview membership without mutating inputs.
Preserve current defaults and permissive shapes.

`useWorkspaceNavigation()` returns `intent`, `route`, `go`, `restore`,
`consumeMergeIntent`, `canBack`, `canForward`, `back`, `forward`. Dependencies are
React, colocated helpers, browser history/events and crypto.randomUUID. There is
no readiness fetch or configuration. It admits saved valid route/integer index
or starts overview index zero. Mount replaces history; cleanup removes popstate.
`go` increments intent before validation, pushes index+1 and resets furthest.
Back/forward increment intent and delegate to history. Popstate increments intent
even for malformed entries; valid entries publish route and extend furthest.
`restore` validates and replaces at index zero without adding intent.
`consumeMergeIntent` strips only matching request UUID and replaces history;
it never grants/renews consent. Same route key does not erase intervening intent.

## Executable example and checks

The [whole helper suite](workspaceNavigation.test.js) executes this shape in
`workspace history admits local destinations only and preserves exact route identities`:

```js
const route = makeWorkspaceRoute('protocol', {protocol: 'uuid:one'}, 'visit-1');
assert.equal(validWorkspaceRoute(route), true);
assert.equal(routeAddress(route), '#/protocol/uuid%3Aone');
```

All original helper tests remain, including compact 50k-member snapshots, null
focus and restoration precedence. Real [App/history tests](../presentationSessionsApp.test.js)
verify away/back refuses delayed drafts and restored merge intent lacks consent.
[Import/merge tests](../importMergeWorkflow.test.js) load the real hook through SSR
and check consume/restore without replay. The workflow harness intentionally
stubs navigation; retain its virtual ID and exact public-path resolver, and do
not claim it tests real-hook behavior.

From `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/workspace-navigation/workspaceNavigation.test.js src/searchInclusion.test.js src/presentationSessionsApp.test.js src/presentationSessionsIntegration.test.js src/importMergeWorkflow.test.js src/renderer-drafts/desktopDraftSession.test.js
```

Discuss interface/dependency/lifetime/error/authority changes before editing and
update existing adoption/ledger evidence. Use public assertions, not private
refs/source-string behavior checks. Missing snapshot pruning, history intent or
merge consumption must fail existing tests. Parent coordinates policy/import/
discovery, explicit-base mapped checks and later full frontend/build runs.
From repository root: `python3 -B tools/architecture_guard.py check --language javascript`.

## Benchmark provenance and qualification

The canonical [registry](../../../benchmarks/registry.json) and
[guide](../../../docs/dev/benchmarks.md) remain authoritative. NAV_TESTS in
[benchmark.py](../../../tools/benchmark.py) uses suffix-free
`workspace-navigation/workspaceNavigation`. Revision-owned recipes preserve old
flat paths; no aliases, fallback searching or rewritten receipts are allowed.
[Benchmark regression tests](../../../python/tests/test_benchmark.py) retain
independent current/legacy oracles, distinct synthetic rename targets and checks
that deliberate source mutations change bytes. Run this source-fixture suite
with the existing provisioned Python profile; its workers are mocked. Do not run
an actual benchmark/native launcher merely to validate paths.

Changed runner, suite and harness bytes change suite identity. Old receipts stay
verifiable for their own revisions but noncomparable with this suite and invalid
for its current gate. `correctness.navigation` is indirect interaction coverage,
not a new latency/memory measurement. Native navigation/release qualification
remain separate unsupported gates; these source tests do not satisfy them.
