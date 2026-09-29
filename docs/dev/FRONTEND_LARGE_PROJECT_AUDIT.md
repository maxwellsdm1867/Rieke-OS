# Frontend large-project audit — 2026-09-27

## Subsequent paged-tree and interaction update

Inspector and its Design tree workspace now use `POST /api/tree-pages`; they no longer fetch or index the full protocol tree. The component holds one page of at most 60 branch or epoch rows plus a bounded ancestor path. Opaque server path keys and a revision token gate continuation requests; stale failures disable old entries and offer explicit reload. Selecting an epoch can locate its path without materializing all leaves. Explorer now requests compact summaries and server-computed membership differences. Its paged tree sends the summary’s exact tree revision, including on root reload and anchored lookup, so a stale tree cannot silently replace the displayed selection. Exact saved memberships remain on the server.

The tree/grouping and metadata pane widths are draggable and persist locally. Focusable separators support Left/Right (10 px), Shift+Left/Right (40 px) and Home/End. Bounds reserve center plotting space; narrow windows use a resizable metadata overlay. Scope, inclusion and export settings are unaffected.

In inspection mode, Up/Down moves through chronological matching epochs from ordinary workspace focus. Crossing pages requests the adjacent metadata page; an off-page tree selection uses `anchor_uuid` to locate its chronological page. Editable fields, native selectors, dialogs/menus/listboxes and resize handles are excluded, and already-handled widget keys are respected. Design mode does not navigate epochs. Raw trace Left/Right and zoom shortcuts remain local to the trace; unhandled Up/Down bubbles to epoch navigation. Focused rows scroll into view. Page failures retain the focused epoch and show an error instead of guessing another epoch. Errors from old request paths cannot cancel new anchor navigation. Inspector and Explorer also retain the Design tree’s opaque path, page offset and revision across navigation, without caching branch/epoch rows; changed grouping resets that view explicitly.

Validation now passes 107 frontend tests and a production build, including pane limits, keyboard exclusion rules and chronological page/anchor transitions. Native browser interaction verification is performed separately by the parent agent.

## Implemented

The inspection tree now pages every group list and epoch list at 60 rows, including root groups. A focused item outside the visible page is pinned as at most one additional row. The page summary reports the full count and explains the extra focused row. Only the focused epoch's ancestor path automatically opens; cell focus still highlights all matching paths without opening every branch containing that cell. Paging does not change protocol filters, inclusion, bulk targets, or export scope.

The shared cell list now displays at most 60 cells per page, grouped by cell type. Partial groups show visible and full counts. The page clamps when its input scope shrinks. Cell UUIDs, dated labels and inspection/QC actions are preserved.

Saved-versus-current membership comparisons in MetadataExplorer are memoized by their input snapshots. Typing a predicate no longer rebuilds unchanged membership maps on every keypress.

## Request behavior verified in code

- Predicate inputs change local drafts. Full metadata evaluation is triggered by explicit Preview matches or Save, not each keypress. Obsolete preview responses are aborted and gated by request identity.
- TreeBuilder delays grouping changes 250 ms; dependent tree requests cancel their predecessors.
- Global search waits 180 ms, requests at most 20 results, and aborts stale searches.
- Raw traces request at most 20,000 full-rate samples. Pointer movement paints a requestAnimationFrame overlay; pointer release commits the window request. AbortController plus epoch/stream/start/count checks prevent stale waveforms being shown.
- Metadata tables initially render 80 fields from the focused epoch, and epoch navigation requests pages of 60.

## Validation

`npm test --prefix workspace-app` passes 98 tests. New synthetic tests exercise 50,000 root groups, 20,000 branches sharing one cell, and 10,003 cells. They verify page bounds, exact membership coverage, no duplicate focus row, off-page selected-path retention and clamping after scope changes. `npm run build --prefix workspace-app` passes. These are correctness/row-bound checks, not end-to-end browser latency measurements. No research database writes were used.

## Remaining costs and limits

- Inspector and Explorer use bounded tree pages; Explorer summary responses omit full trees and membership arrays. Backend field-index and transport work is separate. Existing legacy endpoints remain available to external consumers.
- TreePreview initially renders 60 groups per column; its explicit Show more action can accumulate additional rows. Users can also manually expand multiple Inspector branches. The implementation bounds automatic initial rendering, not every possible user-expanded DOM.
- Explorer history snapshots now retain revision IDs, counts, predicate drafts and view state, and discard preview trees/catalogs, trace data and membership/diff arrays. Comparisons are calculated by the server against the retained immutable revision ID. The history session map is still unbounded in number of visited entries, but a 50,000-epoch fixture snapshot test verifies that saved membership arrays do not remain in it.
- Complex metadata values are serialized for display in collapsed detail elements, and Show next fields can accumulate rows. Large individual metadata arrays remain a possible cost despite bounded initial field count.

These limitations are explicit; this change does not claim all tens-of-thousands-epoch operations have constant cost.
