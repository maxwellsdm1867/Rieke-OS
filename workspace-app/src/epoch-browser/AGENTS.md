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
- `useEpochBrowserPage.js`

## Contract and authority

Keep UUIDs, source-specific query revisions, predicate values, frozen candidate identity and branch scope exact. Invalid frozen context must refuse rather than fall back globally. Curation submission checks current selection and receipt authority; browsing or restored focus never grants consent. Page requests remain bounded and preserve anchor versus offset behavior. Preserve loading/error states, abort cleanup and stale-result fences.

Tree selection and tree-ancestor cache owners remain separate; trace samples and shared epoch cache lifetime remain with traces/shared resources. Metadata display does not attest provenance or terminal scientific membership.

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
request owners; startup App/data activation remain unchanged. See
[trace worker execution](../../../docs/architecture/trace-worker-execution.md).


Incoming left browsing uses optional ephemeral highlighted UUIDs separate from
selected UUIDs. Plain/Command/Shift gestures affect highlights through existing
bounded range readers and freshness fences. The top selection toolbar has one
counted highlight action: Select Highlighted unions this set; when every highlighted
UUID is selected, Deselect Highlighted subtracts it, with the existing 1,000 limit.
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
