# Retained frontend read owners

These existing named entries remain substantive modules. The organization wave
does not merge their independent authority, freshness or lifetime rules. See the
[ledger](../../docs/architecture/core-module-ledger.json) and
[path companion](../../docs/architecture/core-module-paths.json) for finite scope.

## Transport and epoch snapshots: keep current shared entries

[api.js](api.js) owns `api`, resource/epoch hooks and prefetch binding alongside
existing formatting, curation-target and export-count functions. POST/PUT/PATCH/
DELETE admission (including read POST) and the whole decode/undo-completion promise
participate in the desktop lifecycle. This deliberately differs from backend
backup exemptions. JSON decode failure returns an empty object; HTTP errors retain
status, data, saved:true and persistence facts. Abort never implies rollback or
automatic command retry. Undo and desktop lifecycle remain separate dependencies.

[resourceRequest.js](resourceRequest.js) exports `startResourceRequest` and
`visibleResourceState`. Path/revision/reload nonce identify visible data. Cancelling
clears delay, aborts transport and refuses late success/error even if abort is
ignored. Paused content grants no freshness. [resourceCache.js](resourceCache.js)
exports the bounded cache, global epoch singleton, cache admission, requests,
complete-pair peeking and metadata-only prefetch. Exact global epoch/stream/window,
revision and generation stay distinct. Default 64 entries, 12 MiB estimated
UTF-16 payload and 30-second TTL are limits, not measured heap. Only a valid
metadata/initial-trace pair skips delay; trace failure can leave usable metadata.
Candidate scope never falls back to global reads. Invalidation prevents late puts;
neighbor prefetch is serial and at most two distinct metadata reads, without traces.
Trace geometry remains its own dependency.

Keep rationale: these modules already hide request fencing and bounded retention
behind public operations used across independent views. A unified read cache or
transport facade would force callers to learn incompatible scope/profile/receipt
rules without removing complexity. Moving api while extracting its mixed exports
would broaden a mechanical wave. Existing names stay canonical; future extraction
requires a concrete caller simplification and characterization of the real hook.

Executable public examples: [resourceRequest.test.js](resourceRequest.test.js),
[resourceCache.test.js](resourceCache.test.js), [apiCommandPolicy.test.js](apiCommandPolicy.test.js)
and [epochResourceLifecycle.test.js](epochResourceLifecycle.test.js) cover delayed
cancellation, stale publication, generation refusal, complete pairs and read POST
close admission. They use the same exports as callers; no wrapper is needed.

## Display invalidation: keep the independent hook

[useWorkspaceChanges.js](useWorkspaceChanges.js) exports `useWorkspaceChanges`
and `useSummaryRevision`. Annotation/curation increments display revision only;
other events increment structure too. Only version-1 confirmed annotation deltas
propagate. Hidden summaries defer display revision until visible, while structure
changes refresh immediately. These are local integer clocks, never receipts or
scientific readiness. This small shared hook has a cohesive mount lifetime;
extraction adds no depth. [inspectorCurationLifecycle.test.js](inspectorCurationLifecycle.test.js),
[inspectorTreeAuthority.test.js](inspectorTreeAuthority.test.js) and
[presentationSessionsApp.test.js](presentationSessionsApp.test.js) remain caller
behavior detectors; dedicated hook characterization remains a future improvement.

## Epoch browser readiness: organization remains pending

[epochBrowserSource.js](epochBrowserSource.js), [epochNavigationIntent.js](epochNavigationIntent.js),
[inspectionNavigation.js](inspectionNavigation.js), [frozenReadContext.js](frozenReadContext.js),
[useEpochBrowserPage.js](useEpochBrowserPage.js) and [components/Inspector.jsx](components/Inspector.jsx)
span current page receipts, frozen context, navigation intent and view composition.
This is an explicit remaining organization item, not a completed keep decision for
all epoch-browser inventory. Other epoch-browser UI/policy paths in the companion
remain pending too. Existing [epochBrowserSource.test.js](epochBrowserSource.test.js),
[epochNavigationIntent.test.js](epochNavigationIntent.test.js),
[inspectionNavigation.test.js](inspectionNavigation.test.js),
[inspectorNavigationLifecycle.test.js](inspectorNavigationLifecycle.test.js) and
[inspectionTreeLifecycle.test.js](inspectionTreeLifecycle.test.js) document public
behavior. Moving them requires focused real-hook characterization and coordination
with tree/incoming owners. Retained rows/focus/selection are distinct from inclusion
and current write authority; frozen context cannot silently become global reads.
No new combined readiness abstraction is selected here.

## Verification and change rules

From `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/resourceRequest.test.js src/resourceCache.test.js src/apiCommandPolicy.test.js src/epochResourceLifecycle.test.js
```

Run the explicitly linked Inspector/readiness suites when changing those owners.
Interface, lifetime or authority changes require ledger/adoption review. The new
[search activation](search-activation/AGENTS.md) and
[requested summaries](requested-summaries/AGENTS.md) folders retain different
policies; tree ancestors are a separate characterization work item. Shared
[benchmark registry](../../benchmarks/registry.json) and
[guide](../../docs/dev/benchmarks.md) remain canonical. No source organization or
scoped test establishes whole-app, native, packaged or performance qualification.

## Factoring decision for this wave

The completed survey supplies the selected scope. Applying the codebase-design
skill's deletion test: deleting the bounded cache or summary controller would
redistribute invalidation, subscriber ownership and job cancellation across their
callers. They already earn their interfaces. Deleting a proposed generic read
facade would remove only forwarding; it is rejected. Folder moves improve
navigation/locality, and are not themselves new depth or a performance claim.

Dependencies are classified explicitly: typed identity, predicate/joint selection,
cache accounting and controller state are in-process; React/DOM lifetime and
storage preferences are local-substitutable dependencies exercised by existing
mounted tests; owned HTTP reads/jobs are remote but owned. Existing `load` and
submit/poll/cancel interfaces already have real HTTP and controlled test adapters.
No true-external network dependency or speculative adapter is added.

Search groups its dialog, activation lifetime, bounded reuse and typed search
interpretation because maintainers follow that read flow together. Summary groups
field selection, job lifetime and concrete HTTP adapter because they share one
requested job flow. Their separate entries remain necessary: cache-only consumers
need no React, dialog callers need no cache internals, preference callers need no
job transport. The interface knowledge remains explicit in their local guides.
KEEP is preferred over merging search activation, epoch retention, command
admission, display clocks or tree authority. The existing public-seam suites
already cover the retained interfaces; no private extraction tests or redundant
wrapper tests replace them.
