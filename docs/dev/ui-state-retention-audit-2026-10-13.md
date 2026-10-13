# UI state retention and selective refresh audit

> Later baseline reconciliation: this design worktree is now `codex/ui-cache-design` at local UI base `386e72d`. The observations below retain their original installed-source attribution (`add33d1`); separate local branches are reconciled in `local-cache-baseline-audit.md`.

Audit date: 2026-10-13. User intent: returning to a workspace should restore its last live state immediately; navigation alone should not reconstruct UI, refetch unchanged summaries, or reread recorded samples. Data changes should update affected values in place.

This is a source audit and proposed implementation sequence, not an application patch or performance qualification. It covers the desktop project switch, frontend root/router, presentation sessions, shared read hooks, overview/tree/search/trace caches, Inspect, Workbench, predicate search, Cell QC, preferences, import monitoring, and external annotation monitoring. It does not claim to have measured every interaction or audited every backend operation.

Installed source remains clean `add33d153ae8f533d5c4a68c50690764323c4336` (0.1.12), inspected at `/private/tmp/disco-release-0111-20261011`. Live main was rechecked at `8cd61822aa78bf6e9d221c90fbae6a5c8a90f66a`; it does not contain that release source. All application references below describe the installed release, not this documentation worktree's older application files.

## Decision to carry forward

**Visibility, retained state, and freshness need separate lifetimes.** Navigating away changes visibility. It should not destroy a view or declare its data changed. A data change updates a relevant resource. It should not reset the component identity. A new scientific action validates its own authority without clearing useful presentation.

Ordinary React rerenders are expected when a count changes. The undesirable work is remounting components, losing state, clearing successful responses, restarting requests, recomputing unchanged aggregates, and replacing the displayed page with loading UI.

The application already has useful mechanisms. Reuse and correct their ownership rather than introduce another general-purpose cache alongside them. Existing dependencies include React Activity and TanStack Query. Their mere presence does not provide consistent retention across the app.

## Confirmed repeated-work paths

| Area | Current source behavior | Effect | Required direction |
| --- | --- | --- | --- |
| Project switch | `App.selectProject` uses `location.assign`; desktop uses `loadURL` | Whole document/React root recreated; backend can remain alive | Retain bounded project documents; reveal the existing view on warm return |
| Root navigation | `useWorkspaceNavigation.go` creates a random visit key; App keys Protocol, Stores, Explorer and QC by visit identity and conditionally renders destinations | Saved snapshots can restore selected fields, but components and effect resources remount | Separate history-entry identity from retained destination identity |
| Protocol tabs | Inspect, Workbench and overview are conditionally mounted in `Protocol` | Leaving a tab destroys its component-local resources | Retain visited tab subtrees with explicit inactive behavior |
| Generic reads | `useResource` defaults to uncached requests; effect runs on mount and revision changes | Returning to an unchanged resource commonly reads it again | Project-owned resource lifetime independent of component mount |
| Loading state | `visibleResourceState` exposes null for a changed revision; `Status` substitutes loading/error UI | A refresh can remove the current subtree despite retaining data internally | Keep same-identity confirmed presentation during refresh; distinguish empty, refreshing, unavailable and invalid identity |
| Global change clock | `useWorkspaceChanges` increments one broad revision for every change; unspecified changes also increment structureRevision | Unrelated resource consumers refresh; narrow exceptions only cover annotations/curation | Typed, scoped change receipts and dependency-specific revisions |
| Overview | App owns a useful bounded overview cache, but focus/online/visibility refreshes it; document unmount clears it | Warm navigation across projects loses cache; focus can refresh multiple summaries | Keep cache with project; check changes once and refresh affected summaries only |
| Tree ancestors | TanStack payload cache already disables mount/focus automatic refetch, but provider manually retires it on focus, visibility, online and page lifecycle | Storage and authority leases disappear together | Preserve presentation/payload separately from expiring action/read authority; re-attest narrowly |
| Global search | App-level cache exists, but activation scope retires it on focus/online/pageshow/visibility | Returning to app loses search response reuse | Preserve displayed results; separately renew eligibility to act on them |
| Epochs/traces | Shared bounded cache has 30-second TTL and keys include general revision | Expiry or unrelated revision can reread unchanged recorded samples | Content/source-based sample cache separate from annotation/review overlays |
| External tag monitor | Its first successful scan always reports a changed revision (`null` to current); handler calls `epochResourceCache.invalidate()` | Each fresh frontend mount clears epoch AND trace entries even without newly arriving tags | Preserve project annotation watermark; reconcile first snapshot narrowly; never erase raw samples for tag-only changes |
| Workbench | `useWorkbenchQueue` starts a request each mount/revision; session saves UI selections/workflow data, not a reusable queue resource | Tab returns repeat queue/context reads | Retain queue/candidate view by protocol and frozen identity, with fresh operation receipts |
| Predicate search | Snapshot deliberately omits heavy memberships; mount reconstructs request state; selected epoch uses generic `useResource`; opening editor reloads field registry | Restoration is not live view retention; repeat catalog/detail requests | Retain live query workspace and bounded pages; cache field registry by schema/vocabulary revisions |
| Cell QC | Uses global revision for QC, pages, selected epoch, response summary and field catalog | One edit can refresh several independent layers | Separate recorded response/QC inputs from tags, inclusion and presentation |

These are architectural findings, not individually measured latency claims. The existing native request observations and 44.2-second SRM cold initialization remain in [the project-switch investigation](project-switch-investigation-2026-10-13.md).

## Existing pieces to preserve

- `workspacePresentationSessions` saves protocol, explorer and stores presentation snapshots. It is appropriate for recovery and eviction, but is owned by one App mount, does not retain DOM, and has no eviction policy.
- `RetainedTreePresentation` already uses React Activity for one eligible tree slot. This is a useful local example, although changed authority/revision keys evict the subtree and outer route destruction still destroys it.
- `overviewCache` is bounded (12 entries, 8 MiB), shares pending work and supports conditional responses. It is already above route mounts.
- Protocol overview has an ETag path that avoids building its payload on an unchanged conditional request. It is a useful fallback, not a reason to send a request on every navigation. Project overview is a separate expensive endpoint.
- Epoch/trace cache is bounded (128 entries, 32 MiB), has shared reads and source/stream checks. Keep the checks; improve retention identity and invalidation scope.
- Tree ancestors have bounded payload reuse and attested generation/lease validation. Do not discard the lease contract to make a cache hit look fresh.
- `createSharedReads` coalesces in-flight operations but explicitly does not retain completed payloads. It is not a return-to-view cache.
- Import monitor and upload queue already live above within-project routes. Keep accepted jobs outside view visibility; publish committed import changes once.
- Existing annotation receipts support targeted presentation updates. Extend that pattern instead of routing every result through an unspecified `changed()`.

## What belongs in which lifetime

| State/data | Owner and useful retention | What changes it |
| --- | --- | --- |
| Last route/tab, expanded nodes, pane widths, scroll, focused epoch, zoom, search draft | Per-project destination/view state; warm live view plus lightweight recovery snapshot | User intent; targeted pruning after deleted identities; explicit reset |
| Project rail and names | Desktop/project-session registry, with cached display | Open/close/mount/unmount/rename; discovery refresh; inaccessible path status |
| Source cells/epoch totals/recording dates/source sizes | Project source-summary resource | Successful import publication, source deletion/exclusion/restoration or explicit verified metadata change |
| Protocol cohort/counts | Protocol binding/query resource | Explicit binding/merge/query change; relevant source policy changes; saved-query source generation |
| Tag and review badges | Project/actor/entity annotation overlay | Confirmed local edit, undo, external annotation revision |
| Tree/query pages | Bounded project resource cache keyed by exact query, order, scope and relevant generations | Those query inputs or relevant membership/annotation dependencies change |
| Recorded trace samples | Bounded source-hash/stream/window/representation cache, with scoped admission | Changed source identity/representation; eviction; a failed source verification |
| Epoch metadata values/field registry | Recorded-metadata resource; separate field/vocabulary resource | Metadata/schema/import change; vocabulary-only changes affect only vocabulary-dependent fields |
| Workbench queue/candidate pages | Protocol/candidate resource plus retained workflow view | Queue/binding/source changes, candidate disposition or explicit review refresh |
| Export/activity history | Project history resource | Export/action completion; pagination; explicit refresh |
| Loading/error/request state | Resource owner, separate from displayed last success | In-flight request outcomes; errors don't silently mean empty data |
| Mutation/read authority, consent and retry identities | Existing operation owners | Existing source/revision/lease/actor rules; never revived from a view snapshot |

A general UI revision should not appear in a raw-sample identity. The content cache may be reusable, but displaying it in a new scoped context still requires that context's admission. Preserving a screenshot or DOM is not authority to edit or export.

## Change-to-refresh map

The user's import intuition is correct for newly acquired recordings. However, several supported actions alter other data without an H5 import. The solution is narrower updates, not treating every action as a source refresh.

| Event | Refresh or patch | Leave intact |
| --- | --- | --- |
| Switch project, page, protocol tab; return focus with no known change | Reveal retained view; reconcile lightweight change watermark only when needed | Source summaries, traces, trees, draft, scroll, expansions |
| Import upload accepted / progress tick | Job progress and task status | Committed source totals and frozen protocols until publication |
| Successful import committed | Source index/list/totals, relevant saved-source-query results, field catalog if changed, incoming suggestions | Existing raw samples; frozen protocol membership; current viewport |
| Duplicate import with no catalog change | Job receipt/history only | Source totals, protocol summaries and traces |
| Confirmed tag edit / external tags / undo | Affected entity overlays and tag-dependent aggregates/search/filter results | Raw samples, source membership/counts and unrelated protocols |
| Inclusion/review edit | Relevant inclusion/review/export-eligibility counts and overlays | Raw waveform samples and unrelated source summaries |
| Protocol merge / binding update / changed saved predicate | That protocol's membership, counts and dependent pages; Workbench disposition | Other protocols and recorded sample payloads |
| Source deletion/exclusion/restoration | Affected source policies, query membership, counts; prune or disable unavailable selections | Unrelated sources, route layout and unaffected identities |
| Export completion | Export history/status and aggregates with export dependencies | Source metadata, waveform data, tree expansion |
| Sort/filter/split changed by user | Fetch uncached requested result; preserve previous query's view for back navigation | Unrelated resources and other query snapshots |
| Backend restart, missed event sequence or explicit integrity failure | Revalidate identity and affected resources; rebuild cold view if necessary | Safe lightweight UI intent where identities still exist |

Frozen cohorts must not silently gain imported epochs. New data may create suggestions; changing a frozen protocol remains an explicit action. Similarly, a tag change need not silently replace a currently browsed frozen membership. Preserve the existing distinction between decoration and membership refresh.

## Implementation design

### 1. Make project and destination identities stable

Retain a small working set of live project documents in desktop-owned views. Key by canonical project UUID/path plus backend-instance identity. Reuse existing per-origin isolation and API clients. The previous note describes the necessary IPC/close/security ownership work.

Inside each project, use stable destination keys (protocol UUID plus tab, cell UUID plus QC view, saved/existing explorer workspace identity). Keep history entries separate from component keys. A deliberate new search, explicit reset, or incompatible scope is a new view; every visit is not. Retain recently used subtrees, using Activity or an equivalent explicit hide/suspend owner. Retain serializable snapshots for eviction/recovery.

Activity recreates effects on reveal: the resource lifetime must also be outside these mount effects. Otherwise the same retained UI still reissues requests. Inactive views pause replaceable read/prefetch work and animations; accepted imports, writes, exports and recoverable workflows remain project-owned.

### 2. Separate cached display from resource freshness

Use one canonical resource owner for each data class, preferably adapting the existing TanStack/tree, overview and trace owners rather than creating parallel stores. Consumers subscribe to existing data. An unchanged resource returns synchronously. Repeated consumers share in-flight work. Cache keys encode actual dependencies, not mount/visit counters.

On refresh, retain last-success data for the same project/resource identity. Publish updated values with stable entity UUID keys and unchanged object references where feasible. This lets React update a number or row without replacing the surrounding view. A project mismatch, deleted resource, actor-sensitive boundary or definitive integrity failure needs distinct handling; it must never display another project's data as current.

Do not label every arbitrary POST a mutation: some existing POST endpoints are reads. Conversely, job completion, external tags and background source changes can mutate state without a foreground mutation request.

### 3. Publish scoped committed changes

Replace unspecified `changed()` fanout incrementally with change descriptions carrying the committed project identity, operation identity, affected entities/protocols and resource revisions. Reuse existing confirmed receipts where available. For asynchronous import, publish the data change after successful catalog publication, not merely upload acceptance.

A proposed server change snapshot could contain backend-instance identity, a monotonic sequence, source/catalog generation, annotation revision, per-protocol binding revisions and history/queue revisions. This is a proposed interface, not an existing endpoint. It must be inexpensive to read from committed state and must not calculate the same full overview it is intended to avoid.

Use local operation results to patch exact data where the receipt is sufficient. Otherwise mark a narrowly defined dependency stale and issue one coalesced read for visible consumers. Keep hidden stale resources displayed only when appropriate and refresh on next need; do not eagerly fan out to every previously visited summary.

External producers require reconciliation. Keep the annotation/import monitors but let them publish typed changes only when their project-scoped watermark changes. A single missed-event or reconnect check can invalidate affected domains; ordinary focus should not clear every cache. An event stream can be added later if justified; a cheap revision check plus current monitors is sufficient to start.

### 4. Bound retention explicitly

Bound live project views, live destination subtrees, payload bytes and trace buffers independently. Count-based LRU alone does not bound large waveform memory. Avoid a blanket short TTL for immutable samples; memory pressure and source identity determine eviction. Mutable query freshness and unused-entry garbage collection are separate settings.

Protect dirty/recoverable views and accepted operations from eviction. Flush serializable view state before disposing a safe inactive view. App quit and explicit project close must visit hidden views too. If a resource is evicted, its next use may reload; this is an explicit exception to warm-switch behavior.

### 5. Narrow persistent cache compatibility separately

The prior investigation found full-module hashes in disk projection/index keys. Give projection formats and compatibility their own narrow, tested contracts so unrelated UI/service edits do not rebuild scientific metadata. Preserve source hash/signature verification and record precise cache-miss reasons. This fixes cold starts; it does not substitute for live UI retention.

## Implementation order and review gates

1. Establish observable baselines on owned disposable fixtures: document/subtree mount counters, request list, expensive backend operation counters, source/index rebuild reasons, memory, and normal click-to-correct-result latency. Separate cold open from return navigation. Existing user-project observations are diagnostics only.
2. Correct refresh fanout: typed change events, external-tag first-scan behavior, independent trace/annotation identities, stable same-resource refresh presentation. Preserve current scientific fences.
3. Retain within-project routes/tabs and lift their request owners; verify restoration doesn't reissue accepted actions or undo consent.
4. Retain whole project views and adapt desktop lifecycle/IPC/commands for hidden documents. Coalesce activation reconciliation and remove unconditional focus invalidation only once replacement freshness handling is demonstrated.
5. Optimize cold-load compatibility and backend summary memoization by real dependencies. A server cache is useful for eviction/restart, but isn't needed on the unchanged warm-return path.

Each slice should be reviewable and use the repository's required correctness and benchmark gates before any app-update claim. Do not make this a single large frontend rewrite.

### Behavioral acceptance

- A→B→A with unchanged data displays A's exact retained tree/trace/scroll/draft; no document reload, remount, source rebuild or summary reconstruction is required.
- Overview→Inspect→Workbench→Inspect retains Inspect; previously loaded data is visible immediately and no review/export operation is replayed.
- Returning after 30 seconds does not reread an unchanged waveform solely because time passed.
- One tag receipt changes relevant badges/counts without trace requests or unrelated protocol reads.
- One committed import updates totals once in place, coalesces repeated notifications, preserves expansion/scroll, and does not alter frozen cohorts automatically.
- A failed background refresh preserves a same-identity last-good display and its error context, without silently granting fresh action authority.
- Changed relevant query/membership does refresh; a genuinely new filter does fetch if uncached.
- Hidden views don't generate avoidable periodic requests, leak memory or accept shortcuts intended for another project.
- Eviction, backend restart, close/quit, pending writes, actor changes and source replacement preserve existing ownership and recovery behavior.

## Source map

All paths resolve under installed commit [add33d153ae8f533d5c4a68c50690764323c4336](https://github.com/maxwellsdm1867/Rieke-OS/tree/add33d153ae8f533d5c4a68c50690764323c4336):

- Composition/navigation: `workspace-app/src/App.jsx`, `workspace-navigation/useWorkspaceNavigation.js`, `workspace-navigation/workspaceNavigation.js`, `presentation/workspacePresentationSessions.js`.
- Reads/publication: `workspace-app/src/api.js`, `resourceRequest.js`, `resourceCache.js`, `useWorkspaceChanges.js`, `components/Common.jsx`.
- Retention: `protocol-overview/overviewCache.js`, `protocol-overview/useOverviewResource.js`, `tree-ancestors/treeBranchReads.jsx`, `tree-ancestors/treeBranchReadCache.js`, `tree-browser/ui/RetainedTreePresentation.jsx`, `search-activation/navigationReadCache.jsx`.
- Workspaces: `incoming-workbench/useWorkbenchQueue.js`, `incoming-workbench/ui/IncomingWorkbench.jsx`, `metadata-explorer/ui/MetadataExplorer.jsx`, `cell-qc/ui/CellQC.jsx`, `epoch-browser/useEpochBrowserPage.js`, `epoch-browser/epochPageReads.js`, `epoch-browser/useEpochInspection.js`, `traces/ui/TraceViewer.jsx`.
- Changes: `recording-import/useImportQueue.js`, `recording-import/useImportMonitor.js`, `annotations/externalTagMonitor.js`, `annotations/ui/ExternalTagSync.jsx`, `annotations/annotationTags.js`, `project-preferences/useProjectPreference.js`.
- Backend/desktop: `python/workspace_service.py`, `python/workspace_api.py`, `python/workspace_desktop.py`, `desktop/main.cjs`.

See [primary-source practices](ui-retention-primary-source-research.md) and [project-view research](project-switching-primary-source-research.md) for the external rationale. No new implementation measurements or passing test claims are made by this audit.
