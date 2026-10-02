# Protocol Workbench contract v1

The existing candidate apply route remains exact cohort replacement. Workbench
acceptance is a separate API that retains current main membership and adds an
exact reviewed incoming delta. Source imports, shared scientific tags and
protocol scientific approval are separate authorities.

## Membership and review

Let B be the immutable proposal baseline, C its immutable candidate, and M the
current bound main cohort, all native epoch UUID → metadata fingerprint maps.
Incoming membership is C − B. Publishing adds selected incoming members absent
from M, retaining every M member. Identical UUID/fingerprint overlaps are no-ops;
different fingerprints are conflicts. Acquisition Protocol ID must match the
destination. No predicate rerun can widen the saved candidate.

An older baseline is admissible only when every actual intervening binding
version has a committed additive acceptance receipt and immutable parent
membership retains all previous fingerprints. Replacement/rebinding histories
without that proof fail closed.

Drafts are actor/profile scoped, durable native SQL records with CAS versions.
Their selected/reviewed/excluded decisions are proposal review state, never
scientific approval or shared tags. Exclusion wins. `selected` mode requires
explicit selected + reviewed decisions and rejects any blocked saved selection.
`all` mode is explicit consent for the complete eligible incoming set minus
actor exclusions. Display filters do not alter either publication selection.

## Routes

All paths below have the `/api` prefix. Candidate root is
`/protocols/{protocol}/workbench/candidates/{candidate_revision}`.

| Route | Authority and response |
| --- | --- |
| GET `/protocols/{protocol}/workbench` | Historical candidate queue, stable cursor/queue revision, full distinct pending epoch/cell union, capabilities. |
| GET `/workbench/summary` | Per-protocol pending cell/epoch counts from the same union authority. |
| GET candidate `/context` | Compatible `protocol` DTO, `candidate_scope_revision`, draft version/decisions, incoming/pending counts and publication blockers. |
| GET candidate `/epochs`, `/epochs/{epoch}`, `/epochs/{epoch}/trace`, `/tree`, `/tree-fields` | Required `candidate_scope_revision`; exact frozen incoming membership, current verified native metadata. Trace checks membership before native stream access. |
| POST candidate `/tree/page` | Existing tree body + required candidate scope; no global predicate or client cohort reconstruction. |
| POST candidate `/summary` | Required candidate scope + filters; exact matched count, canonical filters/checksum, scope and generation witness; distributions unavailable. |
| PATCH candidate `/draft` | `expected_version`, `expected_candidate_scope_revision`; optional mode/deferred and ≤250 explicit native-epoch decisions. Entire malformed/stale patch rejects. |
| POST candidate `/preview` | `expected_candidate_scope_revision`, `expected_draft_version`, `mode`; authoritative exact selection counts, preview SHA, binding/query fences. |
| POST candidate `/accept` | Preview inputs + `preview_sha256`, `expected_binding_version`, `expected_query_revision`, `operation_uuid`; durable receipt. |
| POST candidate `/exports` | Accept preview fences + independent export operation UUID, format, optional name; exports only the new selected C − B − M delta, without binding. |
| GET `/protocols/{protocol}/workbench/receipts/{operation}` | Actor-owned immutable receipt; requires no current source/proposal availability. |
| GET acceptance receipt `/export-context` | Exact committed accepted delta, fresh export source/annotation witness, accepted count and supported formats. |
| POST acceptance receipt `/exports` | `expected_export_scope_revision`, independent export operation UUID, format, optional name; exports committed accepted fingerprints without rebinding. |

Canonical `filters.metadata_predicate` intersection requires the scoped predicate
commits. Origin-protocol curation filters are supported; foreign protocol
curation filters reject in this slice. Scope, source, binding, metadata and
annotation generations fence reads before and after DTO construction. Candidate
scope remains the frozen membership authority; generation is additional evidence.

Pending counts include unmerged blocked candidates; eligible pending counts are
separate. An old unavailable proposal without a frozen cell identity yields
`pending_cell_count: null` and unavailable status, never a fabricated zero.
Counts are distinct unions, not sums of proposal counts or loaded pages.

## Publication and recovery

Acceptance commits immutable union recipe/provenance, conditional binding, audit
and operation receipt in one native transaction. Same operation/body returns its
original receipt before current availability checks. Changed body with the same
operation rejects. No-op acceptance has an acceptance audit `event_uuid` and
nullable separate `binding_event_uuid`. Public accepted-ID arrays expose totals
and truncation at 250; durable receipt retains exact fingerprints.

Export uses `reference-json`, `wheeler-sqlite`, or `matlab-mat`. MATLAB annotation
or curation grouping (including joint components) is explicitly unsupported;
acceptance export-context omits that format. JSON/SQLite preserve it. Exports use
synthetic export-only scientific curation defaults and honest
`export_scope.kind = workbench_incoming`; branch review is selection provenance.
Native source/cell/epoch identities and scientific metadata are retained.

Artifact staging precedes a transaction that publishes DatasetRevision, audit,
export receipt and event. Staging/publication failure leaves acceptance intact.
Committed retry returns the existing dataset before source/proposal refresh;
retrying export never binds again. Filesystem staging and acceptance are not one
atomic operation. Main protocol export continues using the combined curated main.

Native DataJoint schema startup adds WorkbenchDraft, WorkbenchDecision and
WorkbenchReceipt (plus existing ProtocolSuggestion recovery coverage). Decisions
reference Draft; restore deletes children first and inserts parents first.
Legacy snapshots deliberately restore empty review tables. Recovery retains
required candidate/baseline/receipt/additive ancestor closure in SQL batches of
250, with no total 250-root cap; missing dependencies fail explicitly.

## Qualification limits

SQL-double/file-fixture tests and independent source review qualify implementation
semantics. Native DDL, fresh/populated FK restoration, crash/restart receipt
persistence, >250 ancestor closure and large-project memory/latency require the
coordinated disposable native qualification window. Queue/context processing
still materializes complete authorities; response pagination is not a claim of
bounded server memory or cheap constant-time global counts. Candidate group
annotation mutation/preflight is not implemented. Existing undo does not undo
membership acceptance. No push, merge, package or live-data publication is part
of these commits.
