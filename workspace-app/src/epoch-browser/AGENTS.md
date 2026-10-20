# Epoch browsing and inspection

## Public interface

`ui/Inspector.jsx`, `ui/MatchingEpochs.jsx` and `ui/EpochViewer.jsx` compose browsing, bounded pages, metadata and selection presentation. Request construction lives in `epochBrowserSource.js`; frozen scope identity in `frozenReadContext.js`; `useEpochBrowserPage.js` retains cancellation and keyed publication. Navigation, focus, scroll and curation submission remain named independent entries.

All existing exports and props remain public. Import the named entry directly; no
barrel, forwarding facade or export demotion is introduced. CSS stays beside its
view. Public entries and styles:

- `ui/EpochAnalysisInclusion.jsx`
- `ui/EpochBrowserChrome.jsx`
- `ui/EpochBrowserLayout.jsx`
- `ui/EpochConnections.css`
- `ui/EpochConnections.jsx`
- `ui/EpochDetailHeading.jsx`
- `ui/EpochInclusionToggle.css`
- `ui/EpochInclusionToggle.jsx`
- `ui/EpochSkimList.jsx`
- `ui/EpochTreePane.jsx`
- `ui/EpochViewer.css`
- `ui/EpochViewer.jsx`
- `ui/InspectionCellTree.css`
- `ui/InspectionCellTree.jsx`
- `ui/Inspector.css`
- `ui/Inspector.jsx`
- `ui/InspectorActions.jsx`
- `ui/InspectorPolish.css`
- `ui/MatchingEpochs.css`
- `ui/MatchingEpochs.jsx`
- `ui/MetadataPanel.css`
- `ui/MetadataPanel.jsx`
- `ui/MetadataTable.jsx`
- `curationSelection.js`
- `epochBrowserSource.js`
- `epochListScroll.js`
- `epochNavigationIntent.js`
- `epochSkimGroups.js`
- `frozenReadContext.js`
- `inspectionCellTree.js`
- `inspectionNavigation.js`
- `inspectionScope.js`
- `inspectorInteraction.js`
- `queryCounts.js`
- `useEpochBrowserPage.js`
- `useQueryCounts.js`

## Contract and authority

Keep UUIDs, source-specific query revisions, predicate values, frozen candidate identity and branch scope exact. Invalid frozen context must refuse rather than fall back globally. Curation submission checks current selection and receipt authority; browsing or restored focus never grants consent. Page requests remain bounded and preserve anchor versus offset behavior. Preserve loading/error states, abort cleanup and stale-result fences.

Pending counts and the bounded cell list (requires backend #118/#119): a
multi-field query run or page may answer with null totals, `cells_pending: true`
and `counts: {status: "pending", request_id}`. `queryCounts.js` reads that job and
fills only the null totals from its exact ready result; nothing invents a count.
`useQueryCounts.js` polls the one job through the summary poll route and cancels
it when the query changes (hiding a view does not cancel). While pending,
MatchingEpochs shows the first page's rows and "counting…" in place of totals and
the cell list; navigation follows `has_more`. When ready, the first page is read
again with exact totals and cells. Predicate pages request the cell list in
windows of 200 (`cells_limit`), show `cells_total`, and load the next window
(`cells_after: cells_next`) when its marker scrolls into view. Single-field
queries keep instant totals and start no counts job. Ledger tests:
`pendingQueryCounts.test.js`, `queryCounts.test.js`.

Tree selection and tree-ancestor cache owners remain separate; trace samples and shared epoch cache lifetime remain with traces/shared resources. Metadata display does not attest provenance or terminal scientific membership.

Workbench focus-location failures retain the focused UUID on transient errors so
an explicit retry can recover the same recording. A fresh successful page proving
absence or an authoritative 404 still clears it. The shared resource hook exposes
optional errorStatus with the same keyed error receipt; it grants no freshness.
Frozen presentation keys never replace candidate-scope, selected-manifest or tree
revision checks. `candidateContinuity.test.js` covers failure, retry and absence.

With Live metadata off, `MetadataPanel` may preserve the measured tag footprint
and displayed field catalog for the same explicitly identified frozen cohort,
focus, selected view and structural revision. Unavailable tag controls unmount;
the reserved space contains no old command or reader. Retained catalog fields
are inert display only. Current errors and retry controls remain outside that
display and outside the scrolling content flow. Changed identity, Live/value
mode or a fresh empty catalog retires the snapshot. See
`metadataPresentation.test.js`; native pixel and scroll checks remain separate.
Protocol forwards its structural clock as `metadataPresentationRevision` through
both incoming review routes. This clock affects only sidebar presentation identity;
frozen `revision` and draft versions still renew catalog/page reads and authority.
Standalone Inspector defaults remain unchanged. `workbenchSessionLifecycle.test.js`
checks the real cumulative/frozen/Inspector/sidebar chain across these clocks.

Initial selected-view intent cannot use its parent page's prepared trace offer
while the selection manifest is pending. An existing selected view may retain
its own inert display during renewal. The strict capability validator remains
unchanged; `selectedTraceAdmission.test.js` exercises the real shared trace viewer
through held acquisition, renewal and membership-change reentry.

## Factoring decision

These files share a presentation responsibility and change locality. Pure helpers
are in-process; React and storage lifetimes are local-substitutable. Existing
remote reads use the existing adapter and test stand-ins. No new hypothetical
seam is introduced. Deleting a helper would spread its identity, bounds or
presentation rules across callers; moving it beside those callers improves
discovery. This is physical organization, not a claim of new behavioral depth.

## Executable public examples

From `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/epoch-browser/curationSelection.test.js src/epoch-browser/epochBrowserSource.test.js src/epoch-browser/epochListScroll.test.js src/epoch-browser/epochNavigationIntent.test.js src/epoch-browser/epochSkimGroups.test.js src/epoch-browser/inspectionCellTree.test.js src/epoch-browser/inspectionNavigation.test.js src/epoch-browser/inspectionScope.test.js src/epoch-browser/inspectorInteraction.test.js src/inspectionTreeLifecycle.test.js
```

Existing examples exercise the same named interfaces as callers. Cross-owner
lifetime tests stay at their existing paths where their composition belongs.
Run scoped tests after coordinating the frontend test lane. These checks do not
qualify browser paint, native reads, HTTP deployment or scientific results.

## Maintenance

Read this guide and the relevant named entry before editing. Preserve ordering,
identity, error, cancellation and lifetime contracts. Authority or runtime body
changes require independent review before implementation. The integration owner
maintains the shared catalog, ledger, path companion and root navigation; source
proof and coordinated integration checks bind this mechanical relocation.

## Progressive epoch list scrolling

The shared Inspector and workbench cell list appends bounded 60-row pages as its
scroll sentinel approaches the viewport. Each appended row keeps its original
page receipt and ordinal. All pages must agree on query revision, expected
binding version and total; malformed, overlapping or non-progressing pages retire
the accumulated list with explicit retry. Source/revision changes and collapse
retire the reads. Saved frontiers restore sequentially without cancelling pending
scroll restoration. Admitted keyboard focus reveals its cell page independently
of sentinel visibility. The accessible Load more fallback replaces pagination.

Fast trace-first navigation and optional metadata values use the tested cache and
request owners. Live metadata also loads independently of admitted trace rows;
metadata failure cannot hide a valid trace. Missing scoped trace descriptors still
require attested detail admission, with no global fallback. Neighbor warming reads
only bounded traces in both modes. Startup App/data activation remain unchanged. See
[trace worker execution](../../../docs/architecture/trace-worker-execution.md).


Incoming left browsing uses optional ephemeral highlighted UUIDs separate from
selected UUIDs. Plain/Command/Shift gestures affect highlights through existing
bounded range readers and freshness fences. The top selection toolbar has one
counted highlight action: Select Highlighted unions this set; when every highlighted
UUID is selected, Deselect Highlighted subtracts it, with no fixed epoch-count ceiling in capable Workbench views; Main tagging bounds remain.
The action is disabled for an empty set or while selection authority is unavailable.
Candidate/query/revision/split or presentation changes mask old highlights before
paint; highlights are not persisted and never imply merge/export consent.
Left browsing suppresses branch actions; Edit Tree keeps group controls. Individual
epoch switches retain actual selection and show Select/Deselect action labels.

Inspector requests all-cell summaries on the first page of an exact view. Later
anchor/offset pages reuse that list only while the project, actor/read owner,
query and binding receipts match. A mismatched receipt disables cell actions
and requests cells again. Scope/owner changes require fresh receipts; retained
cell presentation alone never grants authority. Focused-cell navigation retains
its separate all-cell read. This removes repeated full-cell payloads, not backend
scope-admission work. See inspectorNavigationLifecycle.test.js and
workflowResponsiveness.test.js for exact read counts and stale-action checks.

Main Protocol opens Inspect with the opt-in `projection=browse` descriptor rather
than the full overview summary. Definition, binding, query, source eligibility and
filter choices do not grant page or mutation authority. Project/actor/request-owner
changes retire retained descriptors; structural refresh keeps same-owner Inspector
presentation inert until the descriptor and bounded pages are fresh. Read failures
retain the existing error/retry presentation. Annotation-profile unavailability
does not prevent read-only entry. Overview and export demand their full summaries
only while visible; legacy protocol requests retain their full response. See
`../protocolBrowseEntry.test.js` and `../workflowResponsiveness.test.js`.

Workbench may provide an opaque `initialPageRead` for the exact first bounded
page. Inspector passes it only to its normal rows resource; focused-cell, anchor,
trace and later-page reads retain their own requests. The incoming owner validates
and owns the offer; `api.useResource` claims it in an effect and retires it on
pause/reload/owner/path/revision changes with first-render stale-data masking.
See [incoming bootstrap contract](../incoming-workbench/AGENTS.md#initial-contextpage-offer).

Retained Activity reveal preserves highlights only while their semantic scope is unchanged; changed scope still clears them and retires actions. InspectionCellTree reuses its last user scroll position after fresh membership and bounded pages settle, through the existing cancelable two-frame restoration. Shared toolbar and selection portals use RetainedPortal so hidden busy panels cannot expose controls in the current header.

## Compact pane geometry

Resizable inspection panes remain inline whenever the 300px trace center, 240px
metadata pane and optional 180px tree fit with their 7px dividers (734px with
tree, 547px without). Requested widths are clamped without replacing saved user
preferences. Below those minima metadata retains the existing overlay behavior.
Legacy container rules apply only to non-resizable layouts. Sizing examples live
in `inspectorInteraction.test.js`; the actual UI audit checks compact metadata
position and trace Apply hit targets. This is a layout correction, not a change
to response samples or presentation lifetime.

## Stable inspection navigation

Cell disclosure expands or collapses its rows without selecting the first epoch.
Explicit epoch clicks own inspection; cell tag actions remain separate. During
an exact-owner, exact-navigation-key anchor-to-offset handoff, retain the confirmed
list query identity while the offset request is pending. Prefer any current returned
query revision; owner/scope/revision changes and errors retire this reuse. Read-only
navigation may continue, but page/cell readiness still gates writes. Existing open
cell pages must remain mounted; opening another cell reads only that cell. Collapse
retires that branch’s reads; reopening restores its frontier with fresh bounded reads.
Regression examples are in `../inspectorNavigationLifecycle.test.js`.

Same-key failed navigation reads also retain list presentation identity; errors
never grant navigation or write authority. Predicate matching persists expansion,
frontier and scroll hints in its session, scoped by project, canonical predicate,
ordered splits and preview revision. Offset/focus/loading changes are not new list
scopes. `../navigationSurfaces.test.js` exercises actual list composition across
pinned, frozen Workbench and predicate sources, delayed and failed reads, rapid
Tab navigation, retained view transitions and per-view session isolation. Its
action timings use synthetic responses and exclude native paint.

`EpochViewer` accepts optional `traceReadContext` and `traceEpoch` separately
from scientific mutation `readContext` and the live metadata resource. Inspector
retains only the focused descriptor under an exact captured display capability;
annotation refresh may gate tags/tree actions without clearing those samples.
Actual epoch/source/token/publication and workspace owner changes fence display.
A selected subset requires its own admitted page capability. Undefined capability
means legacy routing; null means unavailable and cannot fall back globally.


A normal click in an admitted Workbench cell page may offer its exact row and
page receipt for focused display before the central anchor page resolves. The
original row reference, query/binding receipt, complete prepared capability and
current request/navigation lifetime must match. A selected view cannot borrow
its parent capability. This single focused offer does not enter central-page
refresh retention and cannot survive owner, navigation scope or capability
replacement. Anchor/offset reads and all curation/selection readiness gates remain
unchanged. `inspectionMetadata.test.js` holds the anchor while the real shared
TraceViewer starts geometry, and rejects stale/replaced/foreign offers.


For admitted prepared display outside tree design and SelectionOverview,
EpochViewer keeps one empty Trace shell in the existing 620px placeholder. It is
hidden, inert, excluded from accessibility and clipped without changing scroll
extents. The hidden child bounds its absolute accessibility helper as well.
Focus reveals the same canvas with normal heading/navigation and separately
guarded curation. It does not preload samples or borrow the empty canvas width:
the existing trace owner measures the focused committed canvas before every read.
Clearing focus retires reads and resets shell interactions; scientific context,
curation scope, legacy views and SelectionOverview precedence remain unchanged.

## Paged protocol cell lists (0.1.21)

Ordinary protocol Inspector reads request `cells_limit=200`. The shared
`useCellWindows` owner appends `cells_after` windows only while query revision,
binding version, project/actor and local navigation scope agree. Each later
window must advance its cursor with the same total; changed receipts or malformed
windows fail visibly. A/B/A returns, Activity hide and unmount retire in-flight
windows. Synchronous duplicate demand is coalesced. Incoming frozen/custom
owners retain their existing full-list contract; #121 does not implement paging
on those routes. Range selection spans loaded cells, as in predicate inspection.

`CellsWindow` loads once per observed entry into view, avoiding a repeated
autoload loop when type/date groups are collapsed; its button supports explicit
load/retry. Tests: `useCellWindows.test.js`, `cellWindows.test.js`,
`../inspectorNavigationLifecycle.test.js`, `../pagedOverviewLists.test.js`.
