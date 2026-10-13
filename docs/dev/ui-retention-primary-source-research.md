# Retain UI state; update only changed resources

> Later baseline reconciliation: this design worktree is now `codex/ui-cache-design` at local UI base `386e72d`. The observations below retain their original installed-source attribution (`add33d1`); separate local branches are reconciled in `local-cache-baseline-audit.md`.

Research dated 2026-10-13. Proposed direction for installed Disco 0.1.12 source `add33d1`, not an implementation or performance claim. The installed-source `workspace-app/package.json` already declares React `19.3.0` and TanStack React Query `5.104.1`. This document is saved in the separate documentation investigation checkout; its main baseline `8cd6182` is not the installed release source. See [project document retention](project-switching-primary-source-research.md) for the Electron boundary. The frontend source audit is separate; the practices below do not imply that every current resource hook uses TanStack.

## Three different kinds of state

The proposed ownership split is:

| Kind | Examples | Lifetime and authority |
| --- | --- | --- |
| View state | Active panel, expanded branches, scroll, selected trace, draft query, unsaved edits | Preserve by stable project/view identity. A navigation event should not reset it. |
| Resource cache | Tree pages, protocol summary, cell metadata, trace samples | Bounded by bytes/entries and keyed by complete resource identity. Can outlive a mounted panel. |
| Freshness authority | Backend instance, data revisions, selection generation, frozen membership, mutation receipt | Establishes whether a cached result is still valid for a particular operation. UI retention cannot substitute for it. |

Re-rendering a count after its value changes is normal. Destroying the view, resetting its controls, clearing unrelated caches, or refetching unchanged data is avoidable work. Conversely, suppressing all renders or reads can hide real changes.

## What the primary sources support

React keeps component state while the component occupies the same tree position. Removing it or changing its identity discards that state. [React preservation semantics](https://react.dev/learn/preserving-and-resetting-state). For retained panels, `Activity` preserves state and DOM while hidden, cleans up effects, and recreates effects on activation. This preserves the panel but does not prevent an effect from redundantly fetching every time it starts. [React Activity](https://react.dev/reference/react/Activity). Thus a retained-view mechanism and a freshness-aware resource hook solve separate problems.

TanStack distinguishes `staleTime` from `gcTime`: the former controls how long data is considered fresh; the latter controls disposal of inactive query data. Defaults consider cached data stale and collect inactive entries after five minutes. Stale queries normally refetch on mounting, refocus, or reconnect. `staleTime: Infinity` still permits manual invalidation; `'static'` blocks that path. Polling intervals are independent of `staleTime`. [TanStack important defaults](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/important-defaults.md). Therefore a cache with default settings can still refetch on every return, and a long garbage-collection timeout does not fix that behavior.

Query keys must include the variables that determine a resource. [TanStack query keys](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/query-keys.md). Exact-key, prefix, and predicate invalidation can mark only matching resources stale; active queries are normally refetched in the background. [TanStack invalidation](https://tanstack.com/query/latest/docs/framework/react/guides/query-invalidation). A successful mutation response can directly replace matching cached data through immutable `setQueryData` updates, avoiding a redundant fetch of the same returned object. [TanStack mutation responses](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/updates-from-mutation-responses.md).

Structural sharing preserves unchanged data references, while `select` lets a component subscribe to only a relevant projection, such as a count. This works with JSON-compatible results; other representations need appropriate handling. [TanStack render optimizations](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/render-optimizations.md). This is especially relevant when a summary changes but the displayed rows or trace samples do not.

For existing external stores, React's `useSyncExternalStore` combines a subscription with immutable snapshots. An unchanged snapshot must retain identity; a changed snapshot notifies subscribers. React recommends ordinary React state when sufficient, rather than introducing external stores by default. [React external-store subscriptions](https://react.dev/reference/react/useSyncExternalStore). Focus-triggered query refresh can be configured per query, and TanStack's default focus handler uses document visibility. [TanStack focus refresh](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/window-focus-refetching.md).

## Fit for Disco: proposed policy

Keep the last visited view usable while refreshing only resources with relevant changes. Retain stable component identities and local controls; move resource lifetime into the existing owning cache where it currently depends on panel mount. `Activity` is a possible tool for costly panels, not a reason to keep every panel or large trace buffer resident forever. Cache keys should distinguish project/backend instance, protocol/scope identity, query/filter parameters, page, and relevant revision dimensions. Do not attach a single global generation to all keys unless every result actually depends on it.

Use resource-specific policies. Immutable recording samples identified by recording identity and stream/range can remain reusable until recording replacement or deletion. Mutable tree metadata, selection summaries, and protocol memberships need their own invalidation paths. For resources whose changes are fully observed, event-driven invalidation can justify an infinite stale time. Where external changes are possible and no reliable notification exists, use a cheap revision check or bounded revalidation, retaining the view during that check. Do not label mutable scientific resources `'static'`.

Changes include more than imports:

| Change | Update or invalidate | Preserve when independent |
| --- | --- | --- |
| Import completes | Authoritative project summary, new recording/cell membership, affected tree/query scopes | Existing unrelated traces, drafts, scroll, navigation |
| Tags or metadata change | Edited entities and dependent filtered/split queries, tag coverage | Raw trace samples and unrelated scopes |
| Selection changes | Exact selection and summaries or actions depending on it | Unselected data pages and raw traces |
| Protocol membership changes | That protocol's membership-derived summaries/pages and freshness receipts | Other protocols' independent view state |
| Query/filter/layout changes | New query-key result or layout projection | Other saved queries and reusable raw data |
| Delete, restore, relocate, backend restart | Affected identities plus dependent resources; broad reset only when identity/authority is no longer compatible | Valid unrelated project views |

This table expresses desired dependency boundaries; implementation must follow actual scientific contracts. A count delta is safe only when the backend receipt establishes the exact committed before/after scope. Do not infer unique-cell increments from imported row counts, optimistically modify frozen membership, or assume an import is wholly additive. When a receipt is insufficient, invalidate and reread the affected summary alone.

Prefer successful mutation receipts containing authoritative updated objects or summary fragments and revisions. Apply them immutably and atomically to the relevant resource; invalidate dependent results the receipt cannot establish. Reject late responses whose project/backend/query revision no longer matches. Event coalescing should prevent an import batch from causing one global refresh per row or per completed file.

If changes originate outside the mounted panel, use one project-owned revision/subscription channel or the existing equivalent. Hidden views can retain dirty markers rather than refetching immediately; activation requests only dirty resources. The channel must account for reconnect gaps or missed revisions with a scoped reconciliation. A transport such as IPC, SSE, or polling is an implementation choice; no particular transport is established by this research as already present or necessary. Reliable revisions matter more than the transport.

Suspend hidden view-only polling, prefetch, and animation. Keep authoritative task/mutation ownership above visibility boundaries so hiding a panel does not abandon an import or an in-flight write. Avoid unconditional mount effects, focus refresh cascades, broad cache clearing, and loading branches that replace the entire existing UI after every small update.

## Verification before adoption

Use disposable fixtures and compare ordinary return-to-correct-view timing plus network requests. A no-change return should retain controls/scroll and make no repeated expensive reads. A relevant change should update exact values while preserving unrelated view state. Test imported duplicate cells, metadata/tag filters, exact selection, protocol membership, query changes, delayed responses, backend restart, missed events, hidden mutation completion, and bounded eviction. Measure CPU/memory and inactive request rate as well as visible latency. Keeping stale counts forever is not a successful optimization, and retaining all data without limits is not the proposed design.
