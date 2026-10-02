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
- Full summaries and the existing complete catalog/derived suggestions are
  separate explicit actions. Automatic requests revert to selected fields on
  scope changes. Missing saved axes/preferences remain intact.
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

71 frontend tests passed with Node v24.13.0: `requestedSummaries`,
`requestedSummariesLifecycle`, `predicateEditor`, `predicateState`,
`predicateValueSuggestions`, `treeFieldPresentation`, `treeLayoutPersistence`,
`epochViewerArchitecture`, `workflowResponsiveness`, `epochViewerRendering`, and
`pagedTreeLifecycle` (`node --test --test-concurrency=1`, each `.test.js`).
The 19 new tests include real mounted React hooks/components with mocked network
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
