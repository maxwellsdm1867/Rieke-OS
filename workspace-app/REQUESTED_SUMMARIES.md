# Requested metadata summaries: frontend integration

This slice preserves the existing scientific preview/run/save, tree, annotation,
detail, and export contracts. It consumes the additive service contract agreed
with the service job on 2026-10-01. No Python/API files are changed here.

## Behavior

- `/explore/field-registry` supplies complete predicate definitions (`fields`)
  and tree definitions (`tree_fields`) without distributions. New fields remain
  available in both choosers; there is no preferred-field whitelist.
- Tree requests derive native summary IDs from active saved axes (expanding joint
  components), the active predicate, and explicit protocol/view preferences.
  Predicate-editor requests derive from valid active conditions and preferences.
  Invalid drafts never trigger an unfiltered replacement summary.
- Summary submit/poll/cancel uses `/explore/summaries`, exact typed bucket DTOs,
  and the latest registry generation at admission. Initial receipts compare
  metadata/typed/source/publication witnesses; scoped annotation/binding tokens
  belong to the acknowledged job. Polls fence against that exact job token.
  Pending, cancelled, stale, and failed work has
  visible status and cancel/refresh controls. Request and generation fences
  suppress late results, including A/B/A navigation and late job acknowledgments.
- Navigation and field editing remain usable while summaries run. Missing
  summaries and truncated distinct counts are unavailable, rather than zero.
  Recorded nulls, arrays, numeric values, and text retain their source types.
- Normal tree/filter views request active axes/conditions and explicitly pinned
  field summaries. The normal all-fields-summary action has been removed.
  Complete registry discovery, raw details, export and reconstruction remain
  available regardless of summary selection. Missing saved axes/preferences
  remain intact.
- Predicate-dialog **Preview matches** explicitly sends `catalog_summary:false`
  to the existing `/explore/run` route. Its authoritative `last_run.cell_count`
  and `epoch_count` remain the displayed preview counts; epoch facet buckets
  never substitute for unique-cell counts.
- Existing complete catalog/derived suggestions remain an explicit action under
  the closed **Advanced layout suggestions** disclosure. Opening that disclosure
  or browsing the chooser does not fetch distributions. Only its load button
  computes the full catalog. Changes to the scope/layout/generation resume
  lightweight previews before request effects run.
- New preferences are local to this browser/device, under
  `workspace.summary-preferences.v1:<JSON [project UUID, protocol UUID, view]>`,
  with payload `{version:1,fields:[exact IDs]}`. Tree and filter views are distinct.
  This is a new schema, not an assumed existing protocol field. Saved layouts
  seed requests through active axes; they are never overwritten by preferences.
- Protocol Inspector summaries use the protocol's frozen dataset plus existing
  filters. Search/export target `initialProtocolId` supplies preference context
  only; it does not narrow the search's scientific membership.
- Older services fall back to the original field catalog only for missing routes
  (404/405). Validation/publication/server failures remain visible. Async summary
  controls stay unavailable with a legacy registry.

## Focused verification

The earlier integration passed 71 frontend tests with Node v24.13.0: `requestedSummaries`,
`requestedSummariesLifecycle`, `predicateEditor`, `predicateState`,
`predicateValueSuggestions`, `treeFieldPresentation`, `treeLayoutPersistence`,
`epochViewerArchitecture`, `workflowResponsiveness`, `epochViewerRendering`, and
`pagedTreeLifecycle` (`node --test --test-concurrency=1`, each `.test.js`).
Its 19 new tests include real mounted React hooks/components with mocked network
receipts, exact adapter payloads, source changes/late completion/cancellation,
new and missing fields, typed facets, preference isolation, legacy fallback,
and a responsive predicate editor. JSX for MetadataExplorer/App is loaded by the
mounted harness. Existing annotation/export/navigation regressions also pass.

Dependencies were copied from the available app runtime into `/tmp`, excluding
its large `.vite` cache; no installation or package build was performed. Python
file edits used the approved `.rieke-runtime/venv/bin/python -B` runtime. No live
database/app access, active-app changes, external experiments, or scale benchmarks
were run. Six tracked MAT fixtures are absent from the approved snapshot
(`.snapshot/manifest.json`); frontend fixtures do not exercise those MATLAB,
waveform, stimulus reconstruction, or native-source fidelity gates.

The focused current-workflow revision passes **74 tests** with the same Node and
local dependency copy: the eleven files above plus `protocolSelectionSummary`.
Two additional mounted cases verify lightweight explicit preview with independent
cell/epoch counts and advanced-catalog opt-in clearing on layout/generation
changes. The tree case now verifies absent all-fields control, complete discovery,
preserved frozen filters/missing axes and no catalog fetch when opening its chooser.
Run with `node --test --test-concurrency=1 src/{requestedSummaries,requestedSummariesLifecycle,predicateEditor,predicateState,predicateValueSuggestions,treeFieldPresentation,epochViewerArchitecture,workflowResponsiveness,epochViewerRendering,pagedTreeLifecycle,protocolSelectionSummary}.test.js src/protocol-tree-layout/treeLayoutPersistence.test.js`.
Existing mounted fixtures emit sandbox-denied HMR-listen warnings; all 74 checks
pass without a running HTTP service. No native timing or package build ran here.

## Current workflow versus legacy diagnostics

For current-workflow comparisons, apply this same frontend patch to both backend
arms. Measure explicit filter preview with `catalog_summary:false`, count receipt,
active/pinned exact typed summaries, and relevant tree splitters separately from
rendered completion. Keep the exact scientific predicate, native membership,
source/frozen protocol context and field requests equal between arms.

The backend all-fields summary request and complete-catalog routes remain
compatible diagnostics. Label retained all-140-field measurements **legacy
full-distribution diagnostic**; they no longer represent a normal UI button.
Advanced catalog/layout suggestion timing is a separate opt-in workload. The
reduced requested-field workflow is a product change, not an equal-output
engine speedup. No native timing, unique-cell category aggregation or UI SLO is
established by the frontend mock tests. Existing infographic counts retain their
native count DTOs; any future category counts must provide distinct-cell counts
under the same authoritative scope rather than use epoch facet bucket counts.

## Remaining row-path seam

This commit does **not** consume `/explore/page`. Ordinary search still invokes
`/explore/run` or `/explore/preview` before mounting MatchingEpochs. Those legacy
operations can materialize full membership/exact count even with
`summary_only:true,catalog_summary:false`. MatchingEpochs then uses
`useEpochBrowserPage` / `/explore/epochs` with `tree_revision`, offset/anchor,
exact total, and cell aggregates; its tree/selection/export contracts remain
unchanged. Inspector's existing protocol cell/row APIs are unchanged as well.
Only distribution/catalog work is separated here; no completed UI SLO or ordinary
row-path performance improvement is claimed.

The follow-on must preserve the existing results presentation; no temporary flat
view is authorized for this slice. Before `/explore/page` replaces ordinary row
I/O, the service/frontend boundary needs these compatible receipts:

1. **One authoritative read context:** query, source eligibility, metadata/typed
   generation, protocol binding, scoped shared annotations/curation, and policy
   versions. All row/cell/tree/detail-navigation receipts must attest to this same
   context. Registry/job tokens have different annotation scope; compare common
   authority witnesses only when coordinating admission. Poll/cursor authority
   uses each exact contextual token. Never invent a legacy `tree_revision` from a
   cursor or treat live reads as saved scientific membership.
2. **Native cell navigation data:** exact recorded `cell_uuid`, label, date,
   cell_type, and matched `epochs`, with stable ordering. Compatible cell pages
   need a total/cursor/limit, source-policy equality, and retained empty acquisition
   branches. Adapt the existing cell browser to bounded append pages; do not infer
   cell identity from display labels or transport full epoch-ID lists.
3. **Anchor and ordinal receipts:** a supported `anchor_uuid` must prove
   membership in the exact context and return its bounded chronological page,
   exact position/offset, and next/previous continuation. Existing repeated-key,
   range selection, cell traversal, and restored-focus behavior must retain exact
   semantics. Either support bounded server offset/anchor seeking or provide a
   compatible cursor/rank adapter; a next-only cursor is insufficient by itself.
4. **Independent exact count:** `summary_fields:[]` is confirmed to produce
   `matched_count` asynchronously without distributions. Rows must remain usable
   while the count is pending/cancelled/stale/failed; total-dependent controls must
   wait for a same-context exact count rather than substituting zero.
5. **Revision and action compatibility:** define a service-issued authority usable
   by existing row/cell/tree readers without preliminary full membership
   materialization. If this is a new read token, version it and explicitly adapt
   `epochBrowserSource`, `useEpochBrowserPage`, MatchingEpochs,
   InspectionCellTree, PagedTree, and restored sessions. Keep legacy run attribution,
   saved query presets, frozen selection revisions, exports, and applying protocol
   datasets on their existing authoritative paths; require scientific membership
   capture at those explicit actions.
6. **Acceptance:** independent native row/detail equality, full chronological
   pagination, anchor/offset/selection equivalence, empty branches, source exclusion
   versus frozen-protocol behavior, generation faults and stale cursors, rapid
   A/B/A scope switching, tags/curation ownership, restored sessions, export/save
   action receipts, and count/first-page completion separation.

The decision remaining is the exact service-issued read-authority schema and
compatible cell/anchor/ordinal receipt shape shared by the existing reader APIs.
The current additive page DTO has full native rows, an opaque next cursor, and
contextual generation, but lacks these compatibility receipts. Service confirmed
count-only summaries and coordinated generation witnesses; no row-path replacement
or temporary display has been implemented here. Backend timings remain distinct
from rendered UI SLOs.
