# Plan: tags as their own change channel (optimistic, per-target), and the frozen-view root cause

Paths below are under `/Users/maxwellsdm/Documents/Codex/disco-request-decoupling-2026-10-17/` (`W/` = `workspace-app/src/`, `P/` = `python/`). **V** = verified by reading code; **I** = inferred/design.

## 1. Inventory of tag readers/reactors

**(a) Displays tags — can apply store entries in place**

| Site | Note |
|---|---|
| `W/annotations/ui/AnnotationTags.jsx:61-63,92-99,129-131` | chips from `epoch.annotations`; posts `/annotations`, builds `confirmed`; suggestions keyed on `revision` (V) |
| `W/epoch-browser/ui/Inspector.jsx:104-105,207,449-453,460,494` | `useAnnotationReceipts`, `annotationState.apply` for focused epoch and `inclusionForEpoch` in trees; emits `onChange({kind:'annotations',origin,confirmed})` (V) |
| `W/epoch-browser/ui/MatchingEpochs.jsx:52-54,67` | own receipt `Map`, `applyAnnotationReceipts` (V) |
| `W/cell-qc/ui/CellQC.jsx:99-103,110,127,144` | own receipt `Map`; `liveRevision` from `annotationRevision` (V) |
| `W/epoch-browser/ui/InspectionCellTree.jsx:50-51` | `has-shared-tags` row marker (V) |
| `W/epoch-browser/ui/Inspector.jsx:156-158` + `W/incoming-workbench/incomingTagSummary.js:9` | cell chips in frozen cell list derived from page rows (V) |
| `W/components/Common.jsx:52` via `Overview.jsx:44`, `cell-qc/ui/CellTypeAccordions.jsx:30` | cell tags in cell lists (V) |
| `W/epoch-browser/ui/EpochViewer.jsx:53,67` + `W/annotations/useTreeCellSelection.js` | selected-cells editor (V) |
| `W/undo/useMutationUndo.js:28`, `W/annotations/ui/TagExchangeDialog.jsx:28`, `W/annotations/ui/ExternalTagSync.jsx:15`, `W/group-save/groupAnnotationRecovery.js:10` | producers that today enter as untyped `changed({kind:'annotations'})` (V) |

**(b) Result depends on tags — must refresh exactly once per confirmed batch**

| Site | Note |
|---|---|
| Tag filters: `W/annotations/annotationReceipts.js:62` (`annotationFilterNeedsRefresh`), `Inspector.jsx:104`, `W/epoch-browser/frozenReadContext.js:41`, `W/metadata-explorer/ui/MetadataExplorer.jsx:60,224-228` (explicit-refresh hold) | server evaluates on confirmed SQL (`P/disco/decisions/annotations.py:273-296`) (V) |
| Tree coverage: `W/tree-browser/treeBranchPresentation.js:46-57` from `shared_tag_coverage` (`P/disco/navigation/tree_pages.py:565`, `P/disco/workbench/workbench.py:996-1011`) (V) |
| Counts/summaries: `W/annotations/ui/ProtocolTagSummary.jsx:7-11`; server `P/workspace_api.py:345,421,479,840` (V) |
| Exports: `W/App.jsx:144,172` (`annotation_generation` witness), `P/workspace_api.py:1667-1670` (V) |
| Vocabulary: `/annotation-tags` in `AnnotationTags.jsx:61`, `W/typed-query/ui/ProtocolViewFilter.jsx:13`; field catalog `W/summary-jobs/useFieldRegistry.js:7` keyed `${revision}` (lazy refresh is enough) (V) |
| Activity log `App.jsx:193` (`/events`) (V) |

**(c) Unrelated, yet refetches/re-renders on a tag — must stop**

| Site | Effect |
|---|---|
| `W/useWorkspaceChanges.js:11-16` | `revision` bumps on every annotation event → App tree re-render incl. retained hidden views (audit: 40–60 ms) (V) |
| `W/App.jsx:216,225-226` → `W/protocol-overview/useOverviewResource.js:16` | `cache.invalidate()` on every `revision`; overview summaries re-read (V) |
| `App.jsx:132,144,173,183,184,193,327` | `summaryRevision`, export summary, `ProtocolExports`, `ProtocolViewFilter`, `IncomingWorkbench revision`, `HistoryPage`, `CellQC revision` (V) |
| `W/incoming-workbench/ui/IncomingWorkbench.jsx:19` (`useWorkbenchQueue(protocolId,revision)`), `FrozenIncomingReview.jsx:36-38` (`loadOwner` includes `revision`), `CumulativeIncomingReview.jsx:31` | candidate context reload → frozen relock (V; see §4) |
| `W/tree-browser/ui/HierarchyTree.jsx:23`, `ColumnTree.jsx:35` | `annotationRevision:groupTags.revision` in scopeKey → tree reload after group tag (audit A2) (V) |
| `W/resourceCache.js:30-37` | `invalidateAnnotations` bumps `generation++`, cancelling all in-flight prefetch (`prefetchWindows.current()`) (V) |
| `ExternalTagSync.jsx:15`, `groupAnnotationRecovery.js:10` | `epochResourceCache.invalidate()` (whole cache) (V) |
| `Inspector.jsx:126` | `navigationReadKey` includes live `revision` unless `kept` (V) |

## 2. Design: `tagStore` as a deep module

New module `W/annotations/tagStore.js` (+ `useTagStore.js` hooks), listed as a public entry in `W/annotations/AGENTS.md`. It replaces the three private receipt `Map`s, `useAnnotationReceipts`, and `annotationChange` on `useWorkspaceChanges`. Precedents: `useSyncExternalStore` already used in `useOverviewResource.js`, `GroupAnnotationRecovery.jsx`, `UndoControls.jsx` (V).

**State (I).** `entries: Map<key=[kind,uuid], Entry>`; `Entry = {confirmed:{revisions:{profile:n}, tags:[chip]}, pending:[Op], version:n}`; `Op = {ticket, profile, add|remove tag, status:'queued'|'inflight'|'failed', error}`; `confirmedGeneration` (bumps only when confirmed state changes); `annotationGeneration` (last server witness string, see §3). Bounds: existing `RECEIPT_LIMITS` (64 targets / 4 MiB) extended to an LRU of ~256 entries; eviction of an entry with a pending op is forbidden (pending ops are the only copy of intent); eviction of a confirmed-only entry is safe because the next epoch/page read supplies truth.

**Interface (I).**
- `read(kind,uuid)` → stable `Entry|undefined`; `subscribe(fn)`.
- `apply(epochOrRow)` → row with `annotations` overlaid: confirmed via the existing `applyAnnotationReceipts` rule (author-revision monotonic), then pending ops rendered as `chip.pending=true` / `chip.removing=true`. Memoised per `(row ref, entry.version)`.
- `begin({kind,uuid,profile,add,remove,ticket})`: appends `Op`, `version++`, notifies that target only. Synchronous; the chip paints in the same frame.
- `confirm(ticket, confirmedReceipt)`: merges receipt into `confirmed`, drops the op, `confirmedGeneration++`. Chip key stays `[profile,tag]`, so the DOM node persists (pending → normal class only; no reflow).
- `fail(ticket,error)`: drops the op and any queued ops on the same target; entry shows `error`; editor/row display rolls back to `confirmed`.
- `ingest(receipt)`: confirmed receipts from undo (`useMutationUndo.js:28` already builds one), tag import (`TagExchangeDialog.jsx:24` receipt; server returns rows — extend to full receipts), group saves (`treeGroupQueryTags.js`/`groupAnnotationRecovery`), external sync.
- `invalidate(targets|all)`: for events without receipts (external scan, group operations >64 targets): mark affected entries `stale` and bump `confirmedGeneration`; readers that show a stale target re-read that epoch only (`epochResourceCache.invalidateAnnotations` scoped, without `generation++` on unrelated paths — change `resourceCache.js:30` to remove only matching keys).
- Hooks: `useTargetTags(kind,uuid)` (per-target selector; only components showing that target re-render), `useTagDependents()` (returns `confirmedGeneration`, debounced by `ANNOTATION_AUTHORITY_IDLE_MS=75`; used by (b) consumers), `useTagLegacyAuthority()` (see below).

**Write path & ordering (I).** Per `(kind,uuid,profile)` ops are serialised: `expected_revisions` always come from `confirmed.revisions[profile]`, never from a pending op; a second op on the same target waits for the first receipt (POSTs ~8–20 ms, so "several tags quickly" costs one RTT each but all chips are visible at keystroke). Add-then-remove before the first receipt: the remove is shown immediately and queued; it POSTs with the confirmed revision once the add's receipt lands. Failure (409 `stale_workspace`, network): `fail(ticket)` cancels the queue for that target, the row re-renders from confirmed, the editor shows the server message with "Refresh tags". Different targets (Tab-to-next) proceed in parallel. Keep the existing contract "Tab waits for save before advancing" (`annotations/AGENTS.md`) in step 1: display is immediate; navigation follows the receipt (~20 ms). Relaxing that is a documented later option.

**Pending tags vs filters/exports (fail-closed).** Pending state never leaves the store: not in `expected_revisions`, not in `annotation_generation`, not in filter requests. An open tag filter is server-evaluated on confirmed SQL; the client shows the pending chip on the focused row but counts/membership do not include it; after `confirm`, `useTagDependents` triggers one refresh of the tag-dependent read (page/tree/counts), and the row may leave the set — same as today. Exports keep the `annotation_generation` witness; the export dialog is disabled while any op is pending.

**What stays on the app clocks.** `revision`: curation (dataset tags/inclusion — they change v4 `query_revision`), exports, undo of curation. `structureRevision`: imports, merges, sources, bindings. Remove `readOwnerRevision` and `annotationChange` from `useWorkspaceChanges.js`; `changed({kind:'annotations'})` stops bumping `revision` when the server advertises `protocol-state-v4`. For older servers (no contract), `useTagLegacyAuthority` makes a receipt also bump `revision` (tags change their `query_revision`, V `workspace_protocol_state.py:384-390`).

**Tree coverage (b).** Single-target receipt: adjust `shared_tag_coverage.tagged_epochs` of the row's ancestors in place by the exact delta derived from confirmed before/after `effective_tags` (0/±1); multi-target → one coverage refresh via `useTagDependents`. Pages themselves do not reload (drop `annotationRevision` from `HierarchyTree.jsx:23`/`ColumnTree.jsx:35` scopeKeys).

## 3. Server side

1. **Return the witness with the write (small, safe).** `POST /api/annotations` (`P/disco/decisions/annotations.py:584-588`) adds `annotation_generation` (`token.shared_epoch:shared_generation`, same format as `workspace_api.py:242-247`) read after commit. Add it to `/protocols/<id>/epochs` pages and `/explore/preview` responses (already on protocol overview). The client then knows whether a dependent read already includes its write and refreshes once, not twice.
2. **`GET /api/annotations/generation`** (lock-free; `tracker.token()` is an autocommit snapshot, V `workspace_state_generation.py:360-375`) for focus/visibility resync, replacing per-view polling. Read fences stay full-token (`workspace_api.py:1021-1026`), so stale reads still fail closed.
3. **Workbench scope (high risk, review required).** `candidate_scope_revision` = checksum of evidence including `shared_annotations_revision = shared.snapshot()['revision']` — a checksum over every annotation record in the project, O(A) per context (V `workbench.py:432-451`, `annotations.py:349-358`). Move it out of `candidate_scope_revision` into a separate `shared_annotation_witness` (the generation token) checked only by operations whose result depends on shared tags (tree coverage `workbench.py:1001`, tag-filtered selection). Shared tags are keyed by UUID and are not copied by merge, so membership operations do not need it (I; confirm in `P/disco/workbench/CONTRACT.md`). Update the adoption record.
   *Status (2026-10-17, branch `claude/workbench-tag-scope`, pending independent review):* implemented as `shared_annotation_witness` (native `shared_epoch:shared_generation`); only tree coverage checks it; the queue revision also drops the shared generation; context advertises `workbench-candidate-scope-v2` when no predicate reads tags. Contract text: `P/disco/workbench/CONTRACT.md`.
4. Optional later: `tag_predicates.snapshot` (B2) served from `SharedTagIndex`.

## 4. Frozen views: root cause

Two couplings, verified:
- **Client:** `Protocol` passes the app `revision` to `IncomingWorkbench` (`App.jsx:184`), which feeds `useWorkbenchQueue` (`IncomingWorkbench.jsx:19`) and `FrozenIncomingReview.loadOwner` (`:36-38`) / `CumulativeIncomingReview.owner` (`:31`). Every tag receipt (even one applied "in place") re-fetches the candidate context.
- **Server:** the re-fetched context carries a new `candidate_scope_revision` whenever any shared tag changed anywhere (`shared_annotations_revision`), so every frozen read token, selection manifest and tree `expectedRevision` differs → `useSelectedEpochView` renews manifests, `HierarchyTree`/`ColumnTree` re-read pinned pages, highlights/focus/scroll must be preserved by hand, and the tag editor locks until `pageReady` (`Inspector.jsx:143,460`).

The eight commits of 2026-10-15 (`952d4f5`, `d65d028`, `2eca986`, `5d01dd3`, `d4bcd57`, `a12073c`, `99166cc`, `f8488b9`) and the audit `docs/dev/workbench-tagging-reset-audit-2026-10-15.md` each retain presentation *across* a renewal they could not prevent; the trigger (tag → revision → context → scope revision) remained. The audit itself notes "Per-cell page authority still refreshes." The design removes both couplings: Workbench receives `structureRevision` (never bumped by tags) and shows tags via `tagStore`; the server stops folding the project-wide tag checksum into the frozen scope. Without the server change, tags by *other* actors/external imports still relock (rare, acceptable interim); own tags no longer do.

## 5. Migration (each step independently testable)

Tests use `W/test-support/workflowHarness.js` (it mocks all `.jsx` except Inspector, IncomingWorkbench, Common, MetadataRefresh, UndoControls, GroupAnnotationRecovery, traceViewPreference, treeBranchReads, navigationReadCache — V line 111; add `tagStore` to the real list and expose `h.renders` via a `React.Profiler` wrapper per route). Browser acceptance in Chrome on the real 5,669-epoch project: Event Timing (`PerformanceObserver({type:'event',durationThreshold:16})` → `duration` from keydown/click to paint), `longtask`, Resource Timing request count, React DevTools "highlight updates" / Profiler commit list; extend `benchmarks/prepared_geometry/observer.mjs` and add the audit's missing `tag edit → reloads` case to `tools/benchmark.py`.

| Step | Change | Tests | Lifecycle/guard | Acceptance (Chrome, real project) |
|---|---|---|---|---|
| 1. Store + optimistic editor | `tagStore.js`, `useTagStore.js`; `AnnotationTags` calls `begin` before POST, `confirm/fail` after; chips keyed `[profile,tag]` with `pending` class; `CellQC`, `MatchingEpochs`, `Inspector` replace private Maps with `apply`/`useTargetTags` | new `tagStore.test.js` (pure: ordering, coalescing, rollback, eviction refusal with pending); extend `annotationReceiptWorkflow.test.js`, `cellQCNavigationLifecycle.test.js`: chip present before the fetch promise resolves, confirmed without remount, rollback on 409 | New module receipts in `docs/architecture/retained-ui-lifetimes.json` for `AnnotationTags.jsx`, `CellQC.jsx`, `MatchingEpochs.jsx`, `Inspector.jsx`, `useAnnotationReceipts.js` (deleted); run `node retainedLifecyclePolicy.mjs --census`; guard: public entry listed in `annotations/AGENTS.md` | keystroke/Enter → chip paint ≤16 ms (Event Timing `duration`); receipt-confirm commit touches only editor + focused row; 1 POST, 0 GETs |
| 2. Stop the app clock | `useWorkspaceChanges`: annotations no longer bump `revision` on v4; delete `readOwnerRevision`/`annotationChange`; `App.jsx:327,329` route events into `tagStore.ingest/invalidate`; `useOverviewCache` invalidates on `confirmedGeneration` only for summaries | `retainedWorkspaceViews.test.js`: hidden retained views receive 0 renders on a tag; `inspectorNavigationLifecycle.test.js` legacy (non-v4) still reloads | `App.jsx`, `useWorkspaceChanges.js` receipts | 0 React commits outside tagged row/editor (Profiler); 0 long tasks; tag visible ≤16 ms with Overview + Workbench + QC mounted |
| 3. Dependents refresh once | `useTagDependents` in tag-filtered Inspector/Explorer pages, `ProtocolTagSummary`, counts, coverage delta; server step §3.1 lets client skip refresh when page `annotation_generation` ≥ receipt | `annotationReceiptWorkflow` filter case: exactly one page re-read per receipt batch; coverage delta exactness; `treeTagCoverageWorkflow.test.js` | `tree-browser` receipts | with a tag filter open: 1 extra read (page) ≤ one RTT; filter toggle off→on with loaded data: UI state paint ≤16 ms, results at network latency (~20–40 ms for a page; a filter is a server read, so sub-frame results are only possible from the retained committed page, which we show inert until the fresh page lands) |
| 4. Group/undo/import/external enter typed | `TreeGroupTags.changed` → `ingest` (≤64) or `invalidate(targets)`; drop `annotationRevision` from tree scopeKeys; `useMutationUndo` passes `confirmed` to store; `TagExchangeDialog` returns receipts; `ExternalTagSync` → `invalidate(all)` + `confirmedGeneration++` without `epochResourceCache.invalidate()`; `resourceCache.invalidateAnnotations` no longer bumps `generation` | `treeGroupAnnotationWorkflow`, `treeCellTagWorkflow`, `tagExchange.test.js`, `externalTagMonitor.test.js` | receipts for those modules | group tag: 0 tree page reloads, 1 coverage refresh; undo: chip reverts in place |
| 5. Workbench off the live clock | `App.jsx:184` passes `structureRevision` to `IncomingWorkbench`; frozen Inspector tag editor enabled by entry presence, not `pageReady`, for epoch/cell scope | `workbenchSessionLifecycle.test.js`, `hierarchyRetention.test.js`: tag in frozen view → 0 context fetches, selection/expansion/scroll untouched, editor not locked | `incoming-workbench` receipts; contract notes in `incoming-workbench/AGENTS.md` | tag in Workbench: 1 POST, 0 `/workbench/*` reads, chip ≤16 ms |
| 6. Server scope split (§3.3) | separate `shared_annotation_witness`; `finish()`/coverage recheck it; `snapshot()` no longer per context | `P/tests/test_workspace_workbench.py`: other-actor tag does not change `candidate_scope_revision`; coverage read raises on changed witness; export witness unchanged | `P/disco/workbench/CONTRACT.md` + adoption record review | external tag import while Workbench open: no relock; `workbench.*` benchmark medians flat vs. tag count |

## 6. Risks and what stays fail-closed

- Per-target author revisions remain the only write guard; pending ops never supply `expected_revisions` (store enforces).
- Page/tree reads keep full generation-token fences and 409 on change; a pending chip is presentation only.
- Export requires `annotation_generation` equality and no pending ops.
- Eviction never drops a pending op; a failed op rolls back visibly with the server message.
- Group saves/recovery keep their durable-operation identity; the store only displays.
- Legacy servers (no `protocol-state-v4`) keep the old full-revision path.
- Risk: step 6 changes Workbench closing authority; needs independent review and the release-gate native check named in the 10-15 audit. Risk: coverage delta is client arithmetic — exact only for single-target receipts; everything else refreshes.
- Not verified: `TagExchangeDialog` apply response shape for building receipts; actual render cost of `useSyncExternalStore` per tree row (use per-target selectors only on rows that render tags).

### Critical Files for Implementation
- /Users/maxwellsdm/Documents/Codex/disco-request-decoupling-2026-10-17/workspace-app/src/useWorkspaceChanges.js
- /Users/maxwellsdm/Documents/Codex/disco-request-decoupling-2026-10-17/workspace-app/src/annotations/ui/AnnotationTags.jsx
- /Users/maxwellsdm/Documents/Codex/disco-request-decoupling-2026-10-17/workspace-app/src/annotations/useAnnotationReceipts.js (to be replaced by `annotations/tagStore.js`)
- /Users/maxwellsdm/Documents/Codex/disco-request-decoupling-2026-10-17/workspace-app/src/App.jsx
- /Users/maxwellsdm/Documents/Codex/disco-request-decoupling-2026-10-17/python/disco/workbench/workbench.py
