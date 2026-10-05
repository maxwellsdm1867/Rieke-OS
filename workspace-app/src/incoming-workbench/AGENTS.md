# Incoming workbench

Start with `ui/IncomingWorkbench.jsx` for queue presentation and
`ui/FrozenIncomingReview.jsx` / `ui/CumulativeIncomingReview.jsx` for review.
`useWorkbenchQueue.js` owns queue loading/paging; `incomingSelection.js` owns
complete ordered frozen selection. The small public UI entries render cell types,
review decisions, merge preview, selection controls and tag summaries. Their
matching named policy files retain the current callable interfaces.

## Read, command and consent owners

Queue/read presentation (`useWorkbenchQueue.js`, `incomingSelection.js`, and the
review UI) does not acquire acceptance authority by sharing this folder.
`workbenchAuthority.js` retains explicit versioned draft/preview/accept choreography;
`selectedIncomingWorkflow.js` composes selected decisions through it.
`incomingReview.js` retains proposal acceptance and export helpers.
`incomingMergeIntent.js` and `useIncomingMergeIntent.js` retain ephemeral single-use
consent; App routing issues and consumes intent. A saved view is inert and cannot
reconstruct that consent. Backend transactions and replay remain authoritative.

Queue candidates deduplicate exact UUIDs within one queue revision. Protocol,
project, candidate scope revision, draft version, queue revision and one-shot request
UUID remain distinct. Explicit contract v1/capability checks and safe nonnegative
counts remain mandatory; null counts mean unavailable. Frozen selection traverses
60-row pages in scoped cell order up to 1,000 complete epochs. Main cell totals,
partial pages, duplicates, wrong-cell rows or changed revisions cannot substitute
for exact scoped membership. Counts do not sum overlapping proposal totals.

Preserve abort signals plus generation/isCurrent publication fences on refresh,
paging, scope changes and unmount. Retained data may display inert after failure;
closing a review proves no rollback. UI labels never create recorded identities.

## Entry readiness

App mounts Workbench independently of the main protocol summary and main tree
layout. Incoming queue negotiation, preparation and fresh candidate context still
gate the frozen browser. A pending or failed main summary cannot block incoming
queue loading; main Inspect and protocol export retain their own readiness gates.
Workbench does not request a filtered main summary for retained browsing filters.
`workbenchRouteRendering.test.js` holds or rejects the main summary and verifies
this separation without connecting to a user project. It is ordering/correctness
evidence, not a measured native latency improvement.

## Factoring decision

Pure selection/count/review policy is in-process; queue and scientific commands use
remote but owned endpoints through existing request adapters. Tests inject owned
request stand-ins and mount actual UI/hook lifetimes. The deletion test favors KEEP
for existing authority and consent entries: flattening them into the UI spreads
version/replay rules, while one generic workbench facade makes read callers learn
acceptance and consent preconditions. Multiple entries preserve clear responsibilities
and needed capabilities. Co-location improves locality without claiming new depth.

From `workspace-app`, run executable public examples and retained composition:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/incoming-workbench/*.test.js src/incomingReviewDecision.test.js src/incomingSelectionRendering.test.js src/incomingWorkbenchRendering.test.js src/incomingWorkbenchStrictMode.test.js src/workbenchSessionLifecycle.test.js src/workbenchRouteRendering.test.js src/incomingAuthorityRecovery.test.js
```

Selection examples demonstrate complete paging and all-or-nothing refusal; authority
examples exercise versioned payloads and separate acceptance/export behavior.
Mounted examples preserve real controls, StrictMode lifetime and inert restoration.
Ledger: `incoming-read-presentation`; scientific command record
`frozen-workbench-review` retains its separate authority.

## Maintenance and evidence

Use the named file entries directly; there is no barrel, compatibility forwarding
module, or newly private export. The interface includes accepted types, identity,
ordering, freshness, errors and lifetime; a lower export count is not the goal.
The executable examples above use the same public seam as callers. Preserve the
original tests; this organization does not replace them with implementation tests.

Read this guide and the relevant entry before editing. Agree on changes to
scientific meaning, authority, request identity or lifetime before implementation.
Keep local changes within those contracts, run the scoped examples and retained
composition tests, and obtain independent source review. The integration owner
updates the existing catalog, ledger and path companion and runs the coordinated
import/build checks. Benchmark links in the ledger are historical/indirect;
relocation establishes neither new performance nor native qualification. Browser
layout/paint, native data reads and full backend qualification remain separate.
