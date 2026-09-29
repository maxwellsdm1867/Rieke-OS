# Shared epoch browser

Pinned protocols (`Inspector`) and predicate results (`MatchingEpochs`) are two
sources for the same browsing interface. Implement shared UX changes in these
components, rather than adding a second source-specific copy:

- `EpochBrowserChrome`: compact toolbar, selection actions, list heading and
  previous/next epoch controls.
- `InspectionCellTree`: collapsed date → cell → epoch hierarchy, cell-local
  pages, checkbox selection, protocol/type/tag summaries.
- `AnnotationTags`: single/cell/bulk annotation editing, suggestions, profile
  selection and Tab-locked save-and-navigate behavior.
- `TraceViewer`, `MetadataPanel`, `PagedTree`: response, details and tree views.
- `epochShortcutDirection`, `epochNavigationIntent`: keyboard rules and bounded
  chronological navigation semantics.

`epochBrowserSource` describes the request; `useEpochBrowserPage` fetches it and
cancels outdated requests. Protocol requests retain saved membership and filters.
Predicate requests retain the exact predicate, split order and verified preview
revision. An optional cell UUID narrows that scope; it never replaces the query.

The predicate endpoint's `include_cells` overview covers the complete match set,
not just the current 60-epoch page. Cell branches fetch bounded metadata pages
only when expanded. Neither source auto-expands branches or selects an initial
epoch on a fresh visit. An explicit saved/deep-linked focus may be restored.

Dataset inclusion/exclusion, dataset-only tags and protocol exports remain
protocol-specific. Predicate saves/exports still require a current preview and
use the existing explicit refresh after annotation changes. Shared cell/epoch
tags use the same UUID-based API and transactionally audited batch saves in both.

Regression checks: `epochBrowserSource.test.js`, `inspectionCellTree.test.js`,
`inspectorInteraction.test.js`, `epochNavigationIntent.test.js`,
`annotationTags.test.js`, `test_workspace_matching_epochs.py`, and
`test_workspace_annotations.py`.
