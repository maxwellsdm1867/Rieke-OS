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

Paged tree browsing requests `counts_only: true`: split group totals and epoch
counts remain; duration, distinct-cell and branch tag-coverage aggregates are not
requested or displayed. Direct annotations and tag/selection actions remain separate.

Incoming branch switches are binary user commands: green on, blue off. Descendants
inherit the nearest branch command; explicit child switches override it without
changing the parent's switch. Flipping a parent again replaces downstream overrides.
A command resolves and verifies every descendant UUID before changing selection,
with the existing 1,000-epoch bound. Leaf switches reflect the actual selected UUIDs;
merge/export continue using those UUIDs, never branch appearance or saved tags.
Inspector keeps commands only in ephemeral scoped state across tree presentations.
Fresh global Select/Deselect all commands explicitly seed a root switch; individual
leaf changes do not clear parent commands. Scope/revision changes clear markers.
See `treeTagCoverageWorkflow.test.js` and the incoming branch selection tests.


Incoming left browsing uses optional ephemeral highlighted UUIDs separate from
selected UUIDs. Plain/Command/Shift gestures affect highlights through existing
bounded range readers and freshness fences. Select Highlighted and Deselect
Highlighted explicitly union/subtract this set, with the existing 1,000 limit.
Candidate/query/revision/split or presentation changes mask old highlights before
paint; highlights are not persisted and never imply merge/export consent.
Left browsing suppresses branch actions; Edit Tree keeps group controls. Individual
epoch switches retain actual selection and show Select/Deselect action labels.
