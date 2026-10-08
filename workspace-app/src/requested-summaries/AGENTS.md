# Requested summaries

This folder groups the existing requested-field policy/controller, React lifetime
and HTTP adapter. They retain separate public entries and exports, with no barrel
or new abstraction. See ledger record `requested-summary-jobs` in the
[ledger](../../../docs/architecture/core-module-ledger.json) and the
[architecture map](../../../ARCHITECTURE.md).

[requestedSummaries.js](requestedSummaries.js) exports preference normalization
and keys, requested-field selection, typed result decoration, request identity,
registry witness comparison and `createSummaryController`. Joint grouping and
predicate identity remain shared dependencies. [useRequestedSummaries.js](useRequestedSummaries.js)
exports the real React hook; [summaryApi.js](summaryApi.js) exports the concrete
submit/poll/cancel adapter over shared api. TreeBuilder, PredicateDialog and the
protocol preference hook remain callers. Preferences storage/UI, field registry,
scientific membership and server computation retain their own owners.

Requested fields deduplicate in first-seen order after joint expansion. Registry
eligibility does not promise all raw fields are indexed. Typed buckets preserve
null/missing and truncated distinctions; distinct count is inferred only for
`values_truncated === false`. The local request key differs from server request ID
and generation. First admission compares common metadata/typed/source/publication
witnesses; later receipts require exact job identity/generation. Invalid ID,
status or missing ready payload fails; changed generation yields stale without
results. Poll delay defaults to 250 milliseconds.

`createSummaryController({adapter,onState,pollMs,schedule,unschedule})` returns
`start(request)`, `cancel()` and `dispose()`. One run owns its AbortController and
timer. Replacement/disposal refuses publication even when transport ignores
abort; pending receipts arriving after retirement are cancelled best effort.
Cancellation is not server rollback. The hook hides old-scope statistics during
render, before effect cleanup, and explicit retry starts a new run. Summary
submit/cancel POSTs continue participating in renderer close tracking.

TreeBuilder requests summaries only while Add a split or Combine fields is open.
Closed axis cards use registry labels and the existing preview count, so mounting,
removing/reordering axes or changing scope with both choosers closed starts no
summary job. Closing both retires the request; reopening requests the current
eligible axes, predicate and saved fields under the existing scope/generation
fences. Frozen candidates retain their separate scoped-catalog read policy.

## Public examples and checks

[requestedSummaries.test.js](requestedSummaries.test.js) executes the factory
with a controlled submit/poll/cancel adapter, validating scope replacement,
late receipt cancellation, exact generation and typed decorations.
[requestedSummariesLifecycle.test.js](requestedSummariesLifecycle.test.js)
mounts the actual hook, TreeBuilder and PredicateDialog through real api fetch
serialization; it checks rapid scope changes, late jobs, preferences and field
eligibility. These existing public examples are kept with all original assertions.

From `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/requested-summaries/*.test.js
```

Keep controller internals lexical and adapter cancellation best effort. Interface,
witness, field/unit and authority changes need review and ledger/adoption updates.
Recursive discovery already finds these tests; shared catalog/import/build closure
belongs to wave integration. The [benchmark registry](../../../benchmarks/registry.json)
and [guide](../../../docs/dev/benchmarks.md) remain canonical. These tests do not
qualify backend cancellation latency, native durability or performance.
