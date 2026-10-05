# Tree browsing presentation

## Public interface

`ui/PagedTree.jsx` composes column and hierarchy views; `ui/ColumnTree.jsx`, `ui/HierarchyTree.jsx`, `ui/TreePreview.jsx` and `ui/RetainedTreePresentation.jsx` retain their public props. Named entries `boundedTree.js`, `columnTreeNavigation.js`, `hierarchyTreeState.js`, `treeBranchPresentation.js` and `treeFieldPresentation.js` own presentation and navigation rules.

All existing exports and props remain public. Import the named entry directly; no
barrel, forwarding facade or export demotion is introduced. CSS stays beside its
view. Public entries and styles:

- `boundedTree.js`
- `columnTreeNavigation.js`
- `ui/ColumnTree.css`
- `ui/ColumnTree.jsx`
- `ui/HierarchyTree.css`
- `ui/HierarchyTree.jsx`
- `ui/PagedTree.css`
- `ui/PagedTree.jsx`
- `ui/RetainedTreePresentation.jsx`
- `ui/TreePreview.css`
- `ui/TreePreview.jsx`
- `hierarchyTreeState.js`
- `treeBranchPresentation.js`
- `treeFieldPresentation.js`

## Contract and authority

Paging changes presentation only: pinned rows never replace page members and grouping precedes paging. Preserve exact path identity, bounded hierarchy restoration, selected UUIDs, requested offsets, loading/errors and existing cancellation. Retained presentation is not a fresh scientific read.

KEEP tree-selection, tree-ancestors, protocol-tree-layout and shared request/cache owners separate: selection ordering, freshness witnesses and cache admission must not migrate into view state. Terminal epoch membership remains the reader authority.

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
node --import ./src/test-support/reactTestEnvironment.js --test src/tree-browser/boundedTree.test.js src/tree-browser/columnTreeNavigation.test.js src/tree-browser/hierarchyTreeState.test.js src/tree-browser/treeBranchPresentation.test.js src/tree-browser/treeFieldPresentation.test.js
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

Workbench branch coverage uses exact backend `shared_tag_coverage` counts, never
loaded children or direct cell chips as a descendant-total substitute. All epochs
with any direct/inherited shared tag are green; partial coverage shows a count.
Tag names may differ. Neither appearance nor tags grant approval/merge membership.
Missing, malformed, stale-scope and refreshing coverage cannot paint green. Keep
`treeTagCoverageWorkflow.test.js` with the pure branch presentation examples.
