# Incoming Workbench UI: initial source slice

Base: 6dc6e888e992ea931c8972ead94036bea7091736. Isolated branch `incoming-review-ui`.

The protocol workspace now has a Workbench tab. Import review opens the corresponding protocol Workbench; Review first opens the existing candidate browser inside that tab. Protocol sessions retain worklist choices, active revision, candidate viewer snapshots, and export receipts. These are view/session state, not actor scientific review decisions. Merely opening a proposal never approves an epoch.

The current authority returns the latest proposal per protocol. The initial queue labels this limitation. The sidebar count uses the authority's disjoint full `cell_changes.counts` groups, never truncated cell detail lists, epoch totals, or proposal counts. This is distinct affected cells in the current proposal, not a cumulative pending-cell union.

The existing candidate browser re-evaluates the recipe predicate. Its banner states that it is a live query and may differ from the immutable proposal. Shared tags publish immediately. Viewer exclusions remain temporary export selection state. Review-context export is direct only; protocol replacement/create destinations are hidden. Source eligibility, snapshot hashing, annotation freshness, acquisition compatibility, and backend concurrency fences are unchanged.

Direct queue Export uses the immutable full candidate and its SHA256, creating a one-off artifact without protocol masks or curation inheritance. Desired incoming-only selected export requires the forthcoming scoped export API. Additive Accept & export is disabled in this slice. It must not call the existing exact-replacement apply route under an additive label.

The staged legacy acceptance helper is independently tested: fresh comparison, compatibility, expected binding/query fences, authoritative binding receipt, interrupted acceptance reconciliation, export-only retry. This helper is not wired to additive acceptance. Export failure cannot trigger another binding write; interrupted artifact creation still requires export-history inspection because the legacy export API has no idempotency key.

## Separate additive service contract agreed with backend owner

- `GET /protocols/{p}/workbench`: versioned cumulative paginated proposals, full distinct pending cell/epoch counts, queue revision.
- Candidate root `/protocols/{p}/workbench/candidates/{revision}`.
- `/context`: frozen scope/hash, main binding/query fences, actor draft version and selection mode.
- `/epochs`, `/tree`, `/tree-fields`, `/epochs/{epoch}`: frozen browse with required scope revision; metadata predicate intersects frozen scope.
- `PATCH /draft`: expected draft/scope version, bounded UUID decisions selected/reviewed/excluded and deferred state. No shared annotations or main membership mutation.
- `/preview`: selected or all eligible candidate additions minus explicit exclusions; produces preview hash and current main/source/draft fences.
- `/accept`: explicit preview/fences and operation UUID; durable additive receipt preserving every existing main member and curation. No replacement relabel, no automatic scientific approval.
- Incoming-only export is a separate later capability. Acceptance plus export has staged receipts and retry without duplicate acceptance.

Scope owner implements the Inspector read-context adapter; backend owner implements persistence/frozen scientific APIs. The UI must gate capabilities before enabling these paths. Same-destination batches use fresh per-item previews and receipts, never one invented atomic transaction. New H5 imports, tag returns, saved export reuse, and package reimport remain distinct flows.

## Validation

28 focused helper/navigation/search-exclusion/suggestion tests and 2 actual React SSR/TestRenderer/JSX checks passed in the released UI test window. No live original project was written. Browser automation runtime failed; dynamic fixture capture remained blank. A static browser render of actual component SSR exists as layout evidence only, not client E2E proof. No package/build/push/merge.
