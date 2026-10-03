# 0.1.7 React tree read reuse

This slice uses pinned `@tanstack/react-query` 5.104.1 with existing React 18.3.1.
`TreeBranchReadOwner` places QueryClientProvider above within-project routes.
Inspector presentation state remains a separate bounded mechanism.

Every ColumnTree operation still fetches its target/anchor. Only nonterminal
ancestor pages may be reused after that response supplies a complete current
backend witness. Terminal epochs, filters/predicates, frozen incoming scopes,
annotation/joint fields, summary jobs, range/selection/tag/action preparations,
and raw H5 are outside this cache. Existing action preparation remains fresh;
branch labels and counts are presentation only.

The backend witness is captured before and after page construction under existing
DB/registration and shared/protocol annotation locks. It requires the native
tracker, DiskMetadataIndex's unchanged structural contract, and authoritative
recorded-field definitions. It includes metadata, typed-index, source, annotation,
binding and process-publication generations plus project path/UUID, protocol and
tree revision. Unqualified readers return ordinary fresh responses without a
witness. Changed generations during construction fail closed.

QueryClient is the only payload store. QueryObserver handles concurrent query
coalescing and independent observer cancellation. The adapter retains only domain
leases, physical-work accounting, and a byte/entry/recency admission ledger.
Canonical typed key strings preserve distinctions not guaranteed by JSON query
hashing. Ancestors must have the exact fresh target witness.

Explicit query defaults: retry false, local networkMode always, no automatic
mount/focus/reconnect refetch, no placeholder data, structuralSharing false,
staleTime Infinity, and gcTime 120 seconds. Infinity is an optimization after
witness validation, never scientific freshness. Focus, visibility, page lifecycle,
online, backend status, project/path/revision and actor changes revoke ownership.
There is no enabled:false authority shortcut.

Bounds: 24 reusable pages, 4 MiB accounted key+payload bytes, eight physically
outstanding ancestor transports, 120-second retention, 10-second operation lease,
60 rows per page, eight split levels. Oversized responses may finish the current
read but are not retained. Cancellation does not release physical capacity until
the underlying transport actually settles. These are cache bounds, not claims
about total renderer heap or active DOM memory.

Validation: ten adapter/loader regressions include identical two-ancestor
first=3 POSTs / return=1 fresh-anchor POST, missing/mismatched witness, identity
isolation, independent cancellation, abort-ignoring work, bounds, local offline,
focus/reconnect and explicit error retry. Backend witness and existing related
suites pass 65 tests. The full frontend suite passes 617 tests and the production build passes
(with the existing large-chunk warning). These synthetic request counts are not native Electron latency results.

Qualification gaps: recorded-field Protocol ancestor reuse only; filtered,
frozen, joint and untracked sources always fetch. Native same-fixture before/after
latency, resource measurements and authority scenarios require independent
benchmarking on the immutable commit. No schema migration or general backend
cache is introduced. No React framework upgrade is needed.

Primary references:
- https://tanstack.com/query/v5/docs/framework/react/guides/important-defaults
- https://tanstack.com/query/v5/docs/framework/react/guides/query-cancellation
- https://tanstack.com/query/v5/docs/framework/react/guides/network-mode
