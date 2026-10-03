# React Activity presentation pilot

Experimental branch based on b60ee585b3a9c599337fdddd4e6f8931d35e7967.
React, React DOM and the test renderer are pinned together to stable 19.3.0;
TanStack React Query remains 5.104.1 (peer React 18 or 19). This is a deliberate
framework-upgrade experiment, not deployment or release qualification. The React
18 manual pilot is preserved separately at ccaafcf for comparison.

## One retained surface

EpochViewer keeps one visited PagedTree/ColumnTree under React's actual Activity
boundary. EpochBrowserLayout supplies a stable parent; otherwise its editing
conditional would still unmount the boundary. The host does not pre-render an
unvisited tree. Only Protocol presentation with an existing query owner can stay
hidden; frozen incoming views are evicted on hide. It does not retain all routes,
TreeBuilder, raw recording preview, mutation panels or an additional query cache.

The exact slot key covers the query owner's project/path/actor/lifecycle identity,
protocol, filters, predicate, splits, revision, expected revision and selected
focus. A key change evicts the old subtree, including while hidden. At most one
slot exists. Its columns already use at most eight split levels, 60 rows per page;
this is bounded presentation state, including a last terminal page, not permission
to reuse terminal responses for authority or to mutate their rows. QueryClient
remains the reusable query payload store. Renderer heap qualification is pending.

## Visibility and authority transitions

- Unvisited: no tree subtree or hidden fetch.
- First open: visible, loading, actions fenced; fresh target and ancestors load.
- Current: visible and interactive after exact current read validation.
- Hide: Activity hides DOM and cleans effects. Layout cleanup synchronously
  revokes callback permission, aborts page/range reads and releases subscriptions.
  Existing group-tag dialog cleanup dismisses its portal and releases previews;
  submitted durable writes retain their existing receipt callback semantics.
- Return: same DOM/state, new presentation activation, previous content explicitly
  marked refreshing. Rows and parent curation/tag panels stay fenced until a fresh
  anchor and validated ancestors finish. Raw preview/actions are not mounted while
  this presentation is unqualified. New activation prevents a skipped hidden
  render from accidentally restoring old action authority.
- Failure: retained content remains inert with the existing explicit Reload path.
- Owner/view change: evict; do not show an old actor/project/filter as current.

Ordinary Inspector browsing uses its existing membership authority while the
separate tree is hidden. Frozen merge/export authority is not supplied by this
retained Protocol tree. Page selection/range callbacks additionally check active
state and actionsDisabled; Activity alone is not an authorization boundary.

## Tests and qualification

A React DOM test (not only react-test-renderer) mounts the actual stable layout,
Activity host, PagedTree and ColumnTree. It checks identical epoch-row DOM across
hide/return, Activity's hidden style, no hidden requests, disabled return actions,
abort-ignoring delayed response refusal, fresh recovery, and owner/filter eviction.
Child tagging UI is mocked in that focused test; actual portal, draft/focus and
parent-toolbar behavior still require independent source and native review.
Existing full workflow tests cover frozen receipts and parent actions separately.

React 19 requires an explicit act-environment opt-in for the Node test runner.
Existing mock boundaries now allow the query-owner hook through. The shared-viewer
architecture assertion follows its Activity host. The existing 40 ms search expiry
test uses its injected cache clock so CPU contention cannot expire its first result
before the test installs the next response handler. No product timeout is relaxed.

No native latency/memory/scroll improvement is claimed from unit-test duration or
DOM identity. Compare the immutable Activity candidate with b60 and the preserved
React 18 manual experiment on the same owned fixture and normal persistence path.
The known selected-row reveal versus saved-scroll issue is not claimed fixed here.
The framework upgrade changes dependency identity: older benchmark receipts do
not qualify this commit, and cross-runtime measurements must label that treatment.

Primary API documentation: https://react.dev/reference/react/Activity

## Follow-up after 422 native qualification

The native comparison qualified earlier retained presentation only: median first
previous rows 15.2 ms versus 82.5 ms, with fresh warm content 96.65 ms versus
94.7 ms. Cold content was 420.4 ms versus 220.7 ms; framework upgrade and Activity
implementation remain confounded. Corrected endpoint heap samples were about
8.48–8.49 MiB versus 7.83–7.96 MiB; these are not universal memory budgets.
Admission is any owner-backed view without readContext, broader than the selected
Protocol route that was native-tested. Other routes remain unqualified.

The follow-up renders a parent-derived readPending label and busy state outside
the Activity boundary on the first visible commit. The child's busy state also
includes pending activation/owner validation, rather than waiting for a passive
loading effect. An error is fenced with Reload rather than labeled as an ongoing
refresh. Existing disabled controls and scientific validation are unchanged.

Reload now replays one saved navigation descriptor (anchor or deliberately chosen
path, offset and scroll positions), bound to the exact owner/scope/activation.
It requests fresh authority without the failed revision. Hidden/scope cleanup
clears the descriptor; stale callbacks cannot replay it. Frozen expectedRevision
continues to delegate to onRefreshPreview. No page payload or mutation receipt is
stored in this descriptor. Mounted tests first reproduced missing anchor and
missing first-commit label, then passed, including deliberate branch navigation,
stale-filter retry refusal and frozen refresh delegation.

Proposed cold-cost control, not yet implemented: a b60 branch with only matching
React 19.3.0 packages and required test-harness compatibility, preserving b60's
unmounting product code. React 18 unmount versus React 19 unmount estimates the
framework contribution; React 19 unmount versus this pilot still includes the
layout/gating/retention treatment and must not be called an Activity-only effect.

Independent review caught a continuation-grammar error in c909: native path or
nonzero-offset pages require a revision. The corrected retry first reads a fresh
root, checks current scope/cancellation, then requests the saved continuation with
that root revision. Anchored retries remain direct and revision-free. The mock
now rejects unversioned continuations, and tests cover both branch paths and
pagination, including supersession while root authority is pending. c909 remains
an immutable rejected checkpoint, not a native-qualified fix.
