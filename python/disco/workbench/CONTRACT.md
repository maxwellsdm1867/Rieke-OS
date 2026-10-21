# Frozen review, recipes and export publication

The folder co-locates existing named owners. It changes discovery and import paths,
not authority, scientific membership, transaction ordering or depth. Choose the
public entry for the operation; do not import a combined facade.

| Responsibility | Public entry and interface |
| --- | --- |
| Membership comparison | [diff.py](diff.py): `summarize_diff(rows, previous, proposed, detail_limit=100)` distinguishes complete epoch/cell/protocol counts from bounded descriptive detail. |
| Frozen recipes | [recipes.py](recipes.py): capture/seal/verify/compare/prepare/save plus existing split/tree helpers. Integrity and prepared output do not imply review approval or completed export. |
| Import proposals | [suggestions.py](suggestions.py): `ProtocolSuggestions` and table definition persist proposals; no automatic protocol membership application. |
| Actor review and additive accept | [workbench.py](workbench.py): `ProtocolWorkbench`, `WorkbenchConflict`, `public_receipt`, tables and existing route registration. |
| Cumulative pending authority | [workbench_pending.py](workbench_pending.py): exact authority snapshot, fingerprint-bound draft carry and pending routes. |
| Candidate publication | [candidate_exports.py](candidate_exports.py): one-off saved-search export with explicit explorer-candidate scope, no protocol binding or implicit curation. |
| Incoming publication | [workbench_exports.py](workbench_exports.py): incoming-only or accepted-new export context/publication; acceptance and export have distinct durable receipts. |

Existing necessary helpers remain accessible, including `FORMATS` and
`_default_curation` used by incoming publication. Existing imported dependencies
remain available to their current callers/tests; relocation does not introduce
language privacy, shrink capabilities or wrap broad service objects in a new facade.

## Frozen membership and review

Canonical queue reads use current-publication proofs prepared by
`prepare_workbench_publication` during explicit startup/import/refresh preparation.
`POST /api/workbench/prepare` explicitly prepares Overview and Workbench under the
database and registration locks. Missing or stale proof returns HTTP 202 with
`status: preparing`, `preparation.status: pending`, and `resource: workbench`, with
no queue payload. Ordinary reads never repair main by scanning its membership.
Unsupported custom/legacy readers retain their existing exact fallback.

Each protocol retains its current and latest-undo pool/check proof independently
of the 1,024-entry historical revision cache. Shared revision proofs are reference
counted; additive merge derives checks from its delta and undo reuses the previous
proof. Publication, published map identity, source scope, annotation dependency,
query definition and binding checks still fence admission. Queue work is bounded
by pending membership, the caught-up delta and sources, plus existing candidate
history; it does not walk main epochs or clone all main cells. The fenced prepared
Overview checks only pending cell identities and never substitutes for the frozen
main fingerprint/source proof. Historical diff profiles keep their existing path.
The eviction regression deliberately limits the historical cache to 64 while
preparing more than 64 protocols; it does not claim production eviction at 65.

Canonical Workbench context summaries use the explicit cohort-only
`WorkspaceService.protocol(..., cross_protocols=False)` projection. Cells and
counts describe pending membership after the requested filters. The unused
`protocol_uuids` cross-protocol coverage field is omitted, not replaced with an
incomplete list. Project summaries keep their existing coverage; custom protocol
or cell-summary readers retain their original interface and behavior.

`ProtocolWorkbench.frozen_service(context)` returns a fresh adapter on every
call. Its internal `_FrozenReadProjections` retains at most one owned frozen
binding and its navigation work across requests. Its projection revision includes
project/protocol identity, immutable candidate/base/main revision IDs and checksums,
binding version, exact selected-view UUID set, and metadata generation. An unbound
main additionally retains its live query revision. Index and published mapping
identities fence the retained entry. Candidate minus base minus main determines
pending membership. Draft-only or shared-tag-only updates of a bound main can reuse
pure grouping while fresh adapters and closing checks read current decisions; coverage reads current tags.
Empty selected views are distinct from unrestricted pending membership. A scope
or generation change replaces the retained binding; custom readers execute
uncached. Index integrity and relevant fingerprints remain checked on reuse.

Only the binding and its epoch/tree projection caches are retained. Fresh adapters
keep fresh decision and annotation-coverage closures; neither context snapshots
nor authority receipts are cached. The existing epoch-page and tree-scope caches
each keep their 64 MiB estimated retention budget. One frozen recipe is retained
in addition, so its storage still scales with that candidate's recipe; this is
not a process RSS limit. Old adapters can retain their input until released, and
project/manager teardown releases the store. No cache eviction truncates a scope.
Canonical context derivation reads a binding header before freshly verifying its
main recipe within the existing context-local read scope. It avoids a detached
cached recipe that would be discarded. Custom binding/header/get overrides retain
full binding reads. Generation, transaction and acceptance checks are unchanged.

A read closes against the context it opened with
(`context(..., closing=opened)`), not a second full derivation. The close reads
fresh exactly what an opening reads for every mutable input: draft header and
decisions, binding header (version and revision UUID), query revision (the
captured transaction guard or a fresh native revision proof), source scope and
the candidate/origin predicate annotation witnesses. It keeps the opened values
only for immutable inputs: candidate/baseline recipes (insert-only, sealed with
their UUIDs), main (the same binding revision UUID) and values derived from
them. Current fingerprints are proven by the same published fingerprint map
and rows objects plus the same publication token: a refresh replaces both,
under the database lock every Workbench read holds, with a new token, and no
code mutates them in place. Any other case (a changed main revision, custom
binding or state readers, an unbound main, a replaced map or token) falls back
to the full context. A stored recipe tampered with during a read is refused by
the next opening context, which still verifies candidate, baseline and main.
Mutations (accept, prepare) keep full closing contexts.

Lock discovery and seen-recording reads use small facts (predicate, lineage
pointer, source revisions, origin UUIDs) derived once per revision UUID from a
verified recipe and kept in a bounded per-manager map; seen recordings are
remembered per main revision. They never confer scope authority, so per-read
recipe verification no longer grows with the number of imports. Custom recipe
readers keep per-call reads. This optimization does not claim page-size-only authority work:
candidate/main validation and persisted global annotation evidence still run.
Single-epoch detail reads retain their membership check but hydrate curation only
for that epoch, just as epoch pages already do; custom curation readers retain
their original full-reader behavior.

The cross-owner [scoped-read tests](../../tests/test_workspace_scoped_reads.py)
exercise real SQLite metadata indexes, exact/empty selected views, acceptance,
index/fingerprint changes, custom fallback, bounded annotation hydration and
closing-read rejection. SQL doubles do not qualify native transaction behavior.

Project/protocol/candidate/baseline/main UUIDs, recipe hashes, metadata fingerprints,
actor draft version, source/query/binding/shared-annotation witnesses are separate
identities.

Project-wide shared tags are not candidate scope. Shared tags are keyed by epoch
or cell UUID, merge never copies or removes them, and they never decide pending
membership, selection, preview or acceptance. `candidate_scope_revision` therefore
omits them (it keeps predicate annotation witnesses: a candidate or origin whose
predicate reads tags still changes scope when those tags change). `context()`
captures a separate `shared_annotation_witness` instead: natively the shared scope
generation `shared_epoch:shared_generation` (the `annotation_generation` format,
read without loading tag records), otherwise the compact revision projection. It
never snapshots every annotation record. Only reads whose result depends on shared
tags check it: tree tag coverage (below). Tag-filtered reads stay fenced inside
each response by the opening/closing read generation, which includes the shared
scope; across requests, tree pages are fenced by their membership revision and
list selection by exact cell counts. Tag-filtered epoch-page continuation is not
fenced across requests by shared tags, matching Main pages under
`protocol-state-v4`; the renderer re-reads tag-filtered pages once per confirmed
tag receipt. The queue revision likewise omits the shared generation (it keeps
the protocol curation generation), so another author's tag or an external import
neither re-prepares the combined review nor blocks `merge-all`. The public
context advertises `protocol.query_revision_contract =
'workbench-candidate-scope-v2'` only when no candidate/origin predicate reads
tags; a renderer may then keep page authority across tag receipts. Exports keep
their own shared-annotation snapshot witness, unchanged. Pending membership is candidate minus baseline minus current main.
Source eligibility and exact frozen fingerprints constrain reads and acceptance;
labels and current metadata do not substitute for historical witnesses. Counts mean
epochs or distinct cells, never interchangeable totals.

`ProtocolWorkbench` owns versioned prepare/context/draft/preview/accept choreography.
Draft batches are bounded to 250 boolean decisions. Selected preview uses saved
selected+reviewed, nonexcluded eligible pending members; all mode uses eligible
pending minus explicit exclusion. Explicit `source` preview/accept mode resolves only
the held recording’s exact frozen pending UUIDs on the server, without changing the
draft selection mode or requiring a bounded client selection. It retains complete
exclusions even when public draft detail is truncated. The source SHA is sealed in
the preview, acceptance request hash, receipt and additive audit provenance.
Additive acceptance preserves all previous main
members and their curation. Opening, highlighting, deferring, hashing or exporting
never grants scientific approval. Actor identity and expected authority fences stay
explicit at each mutation.

The pending pool is new data for main: epochs from recordings main has not
seen that main's saved query matches, from active sources, under a protocol
name the entry accepts (`pending_pool`). "Seen" recordings are those present
when main was last defined (query save, pinned creation or baseline freeze);
additive merges do not change it. A main-level blocker offers nothing. The pool
is cached and recomputed only when main's bound revision, sources, the service
publication token (every refresh publishes a new one; map addresses are never a
key), fingerprints, the entry definition or tags its query uses change. The
binding version is not an input: an undo back to a revision reuses that
revision's pool. An additive merge admits the pool of main' as the old pool
minus the accepted epochs (main's query and seen recordings are unchanged), so
neither merge nor undo re-runs main's query. Re-running a search predicate
is the separate, explicit full-diff path.

The combined review is one immutable candidate per main revision and pool
(`prepare_pool_candidate`): main plus the whole pool, parented on main, with no
origin proposals to re-prove. Left-out decisions carry forward for unchanged
fingerprints; new epochs never inherit an earlier 'all' consent. The actor's
latest combined-review draft is the one with the highest draft version (newest
candidate on ties): carries start at the latest version and every edit adds
one. When a pool returns to an earlier content (a recording excluded and
included again) and reuses that candidate, its existing draft is brought up to
the latest draft exactly as a fresh carry would be, at the latest version, so
the queue fence is unchanged and the queue and `merge-all` read the same
decisions. A derived
prepare operation replays its receipt unless the queue is unchanged but its
context went stale. `merge-all` adds every pending, not left-out epoch in one
locked request fenced by the queue revision the scientist saw, and replays its
receipt for the same operation UUID only when that receipt is an additive 'all'
acceptance of the same protocol. It resolves 'all' for that request only: it
never persists 'all' consent or advances the draft version, so a failed merge
leaves the draft unchanged. An accepted-additions export refuses (409) once
that merge is undone (code `workbench_merge_undone`) or main no longer holds
every epoch it merged with the merged fingerprint (`workbench_conflict`); an
unrelated later merge that keeps them does not block it, and the export is
exactly the merge's frozen accepted membership. Merge receipts
returned by accept, `merge-all` and the receipt read carry `undone` and
`undone_by_operation_uuid` (the undo receipt's operation UUID, or null), read
from the durable undo receipt, so a reloaded client can withdraw export.

A successful preparation response that computed and closed its context during
that request includes `X-Disco-Workbench-Context: fresh-v1` only after its SQL
transaction exits successfully. This covers both a new cumulative recipe and
a new operation reusing an existing candidate. Durable receipt replay, including
all early replay returns, does not include the header. The stored receipt and
returned JSON body remain exact and unchanged by this signal. A renderer may
use that one response's context for its initial display under matching local
owner/lifetime checks; the header grants no new page, mutation or replay authority.
The pending suite checks fresh 200/201 responses, byte-identical replay bodies,
absent replay headers and failed-commit refusal using transactional doubles.

## Delta merges (O(added), not O(main))

With the canonical explorer reader, Workbench revisions are read as verified
headers plus shared member views (`ExplorerHistory.header/members`); custom
recipe readers keep full recipes. The combined review candidate is a
membership delta over main (added = the pool), and an additive merge publishes
main' as a delta over main (added = the accepted epochs), so neither writes,
copies nor hashes main's membership. Context derivation for a candidate that is
its baseline plus a sealed delta takes incoming, base conflicts and unavailable
members from the delta. Main's changed-fingerprint and inactive-recording sets
are computed once per (revision, publication token, the same published
fingerprint map and rows, source scope) and derived for a delta from its
parent in O(delta); a refresh publishes new maps and a new token under the
database lock and nothing mutates them in place. `current_fingerprints_sha256`
hashes the members whose current fingerprint differs (and those values), which
together with the sealed recipes determines every current member fingerprint.
merge-all builds one context and passes it to accept; the in-transaction check
is the token close. `verify_sources` re-verifies the added epochs' recordings;
main's carried members are proven by the context (sealed recipe, current
fingerprints, active sources). The binding diff summary is derived from a
cached per-revision profile (`summarize_additions`, equal to `summarize_diff`
for additions). Lineage and undo read the delta: a delta over its exact parent
that removes nothing is additive by construction, and undo rebinds the parent
and retires the delta's index rows in the same binding-CAS transaction.
Binding version fences, preview/draft/queue fences, source eligibility and
fingerprint checks of added epochs are unchanged. Exports still freeze an
explicit exact member list. The protocol query revision (protocol-state proof)
is owned by the protocol-state reader and is still O(protocol) until its
bound-main token (protocol-state-v5) lands.

## Recipes and separate publication

Recipes preserve canonical UUID/fingerprint membership, typed metadata, source
provenance and ordered arrays. Canonical SHA-256 sorts object keys and rejects NaN;
it proves content integrity, not actor permission. Frozen membership does not rerun
a query. Comparison refuses incompatible project/protocol/query/catalog/fingerprint
versions. Prepared exports distinguish included, excluded, held-by-review and eligible
members; current native review validation still belongs to publication callers.

`save_snapshot` verifies, writes/fsyncs a temporary and hard-links a new immutable
path, refusing overwrite; no directory-fsync guarantee is added. Completion belongs
to publication, not preparation or the existence of a recipe file.

Candidate exports retain deterministic export-only scope UUID and explicit recipe
scope; they create no protocol, binding, pin or curation record. Incoming publication
checks exact incoming additions or accepted-new fingerprints, source/shared-annotation
witnesses and the independent export operation. Confirmed acceptance never reruns or
rolls back because an export fails. Filesystem artifacts stage separately from the
native dataset/audit/receipt transaction; preserve failure reporting and publication
order instead of claiming cross-resource atomicity.

[workspace_export_artifacts.py](../../workspace_export_artifacts.py) stays flat and
is the single owner of export staging for all three exports (protocol route,
saved candidate, incoming workbench). `stage_export(output, recipe, *, format,
build_package, publish, matlab_writer, write_json, save_snapshot, now,
linked_sources=None, failure_fields=None)` creates the fresh folder outside its
catch, then writes `recipe.json`, the reference JSON (or prepares the linked
package), materializes the format through `materialize_export_format` and returns
`publish(artifact)`. Any failure after the folder exists writes one `failure.json`
shape (`at`, `status`, `error`, `artifact_published: false`, plus caller
`failure_fields` such as `export_scope`) and re-raises the original error; an
OSError while writing the marker never replaces it. Callers no longer own staging
or the failure marker. They keep locks, validation, frozen membership and package
contents (`build_package`), freshness/source/annotation rechecks and publication
(`publish`: dataset revision, audit and receipts). Partly staged files are left in
place for diagnosis; the helper does no cleanup, hashing or SQL itself. Format
adapters and their imports stay lazy. See the existing
[P05 contract](../../../docs/architecture/0.1.8-export-materialization-design.md)
for the original format tail; the 2026-10-18 consolidation (user-approved) moved
staging and the failure marker into this owner.

## Why these entries remain separate

The deletion test favors retaining substantive owners: removing recipe verification
spreads seal/provenance rules among query/export callers; removing workbench authority
spreads actor/version/replay rules into routes; removing publication ownership
spreads staging/failure/transaction order into UI-facing code. A generic read/write
workbench facade would force read callers to learn acceptance and export preconditions.
Co-location reduces navigation cost without claiming a smaller or deeper interface.

Diff and canonical recipe computation are in-process. Owned request/route orchestration
is remote but owned, with existing service and controlled test adapters. Filesystem
staging can be locally substituted for limited ordering examples, but this wave runs
no export fixtures. Native SQL/DataJoint, H5 and format writers remain true external
qualification dependencies; in-memory stand-ins cannot prove durability, triggers,
foreign keys, native exit, byte provenance or scientific export correctness.

## Public examples and deferred qualification

The existing [membership examples](tests/test_workspace_diff.py) call the same
`summarize_diff` interface as review/proposal callers and import only stdlib plus the
inert package/public diff module. Run from the repository root:

```sh
PYTHONPATH=python python3 -B -m unittest disco.workbench.tests.test_workspace_diff
```

They verify complete counts despite detail truncation, existing-cell additions,
changed fingerprints, missing rows, stable order and invalid limits. No private
extraction tests replace them. Existing [workbench](../../tests/test_workspace_workbench.py),
[pending](../../tests/test_workspace_workbench_pending.py),
[recipes](../../tests/test_workspace_recipes.py),
[candidate exports](../../tests/test_workspace_candidate_exports.py) and
[incoming exports](../../tests/test_workspace_workbench_exports.py) remain root
integration detectors with canonical imports. They were not executed in this wave.

Native export qualification is explicitly deferred: no export workloads, export
fixtures, real database, scientific imports, app launch or HTTP runtime checks.
Source-body/import verification does not replace these gates. The parent owns shared
profile/catalog/CI/path-companion registration and coordinated package closure;
source organization claims no benchmark improvement or release support.

## Frozen tree tag coverage

Frozen paged tree branches and ancestors include `shared_tag_coverage` with exact
`total_epochs` and `tagged_epochs`, or null if shared annotations are unavailable.
Coverage counts each descendant epoch once when it has any direct or inherited
shared tag; tag names and authors may differ. It does not imply scientific review,
approval, incoming selection or main membership. A merged epoch is removed from
pending scope; merge alone never creates tags.

Coverage is built lazily, only when branch coverage is requested (the app's
counts-only tree pages never request it): one request-local index of tagged epoch
and cell targets read for the candidate's pending epochs and their cells, in
bounded batches, never a project-wide snapshot (custom adapters without targeted
reads keep the full snapshot). The shared witness is compared with the value
`context` captured before and after building the index; a change raises
`WorkbenchConflict`, and the response-end read generation still rejects a later
change in the same response. No annotation records are part of the public context.
Frontend saved-tag badges require matching current candidate scope and complete
validated counts; partial coverage and unavailable/retained reads remain distinct.
Badges use neutral styling. Green/blue branch switches describe the separate
ephemeral incoming selection command, never shared-tag coverage.
Executable cases: `test_workspace_workbench.WorkbenchTests` coverage and shared-tag
scope tests, `test_workspace_workbench_pending` (another author's tag keeps queue,
scope and tokens), `workspace-app/src/treeTagCoverageWorkflow.test.js` and
`workspace-app/src/workbenchTagScope.test.js`.

## Response-local native attestation

Read-only GET and existing preview and tree-page POST routes (the candidate count-preview
`POST .../candidates/<r>/summary` route was removed with query-building previews)
reuse the exact native `response_contract` only while holding their annotation
locks. Schema authority is attested at both boundaries, with live scope counters
inside. A failed closing check discards the response. Custom authorities retain
their prior path. Preparation and mutation routes never enter this read lease;
their independent transaction fences and backup policy are unchanged.


## Fresh column navigation batches

A public context advertises `tree_column_pages: true`. Candidate `tree/page`
accepts `include_ancestors: true` and at most eight `ancestor_offsets`: null means
use the target receipt's recorded parent offset; integer offsets retain the
existing 0–10,000,000 bound. Anchor navigation always uses recorded offsets.
Each target/ancestor remains bounded by the ordinary page limit (at most 100).

The endpoint builds all pages freshly from one frozen service inside one guarded
read, then runs the existing closing generation/candidate check before returning.
Parents receive that same final generation, candidate, query and binding fence.
It neither admits cached candidate data nor changes selection/publication consent.
The existing Workbench suite compares batched bodies to separate fresh reads and
covers anchor offsets, malformed options, bounds and closing-scope rejection.


Paged browsing opts into strictly boolean `counts_only: true`. Root, selection,
branch and ancestor summaries then contain epoch counts, with group totals in
`total`; full-bucket duration, distinct-cell and shared-tag coverage scans are
skipped. Legacy requests retain their full response. Mode-specific group caches
remain bounded; revisions, membership, labels and authority fences are unchanged.
The existing representative-only label renderer is retained. Live ancestor JSON
keys include the request mode, so full and count-only responses cannot collide.

## Exact selected summary

Context advertises `selection_summary: true`. Read-only POST `selection-summary`
accepts only `candidate_scope_revision` and at most 1,000 distinct canonicalizable
epoch UUIDs. Every UUID must belong to the frozen pending candidate; changed or
unavailable fingerprints and incomplete/conflicting cell metadata fail closed.
It returns echoed UUIDs, exact epoch/unique-cell counts, and unique recorded
`cell_uuid`/`cell_type` pairs under opening/closing scope and native read guards.
An empty selection returns zero counts. View filters do not prune explicit selected
UUIDs. This bounded read does not compute aggregates over unselected branches or
change scientific/draft state, consent or acceptance authority.

## Bounded branch selection read

Context advertises `tree_selection: true`. POST `tree/selection` accepts a current
candidate scope and tree revision, exact opaque path, splits/filters and expected
count 1–1,000. One guarded context resolves metadata membership once, then emits exact DFS
UUID order without rendering descendant pages. Typed grouping, missing values,
joint fields, block chronology and leaf chronology match paged browsing. Actual
oversized/mismatching groups are refused before descendant enumeration. Custom
pager overrides retain the existing counts-only 60-row traversal fallback.
Unique complete UUIDs are returned with path/count/revision and one closing
authority check. Client offsets, anchors and paging-mode overrides are rejected.
It creates no draft, annotation, merge or export authority.

For canonical pagers, column batches reuse the target projection across its
ancestor prefixes only within one guarded response. Target validation and the
closing generation/scope check remain mandatory. Overridden page/scope readers
retain independent page reads. No metadata projection or permission is shared
across requests by this optimization.


## Response-local recipe derivation and list selection

Each context derivation owns a private recipe resolver. Only the existing pinned
canonical ExplorerHistory readers can share a fully verified detached recipe and
its membership map within that derivation. Dependency discovery is outside this
scope; closing context creates a new resolver and freshly verifies all recipes,
including current main rather than treating the binding's UUID cache as storage
authority. Custom readers retain direct calls. Nested reads and exceptions restore
the previous context; no recipe or derived map is reused across context boundaries.
This reduces repeated work but remains linear in frozen membership.

Context advertises `list_selection: true`. POST `list-selection` receives the
current candidate scope, filters, and an ordered list of unique cells with exact
nonnegative epoch counts totaling at most 1,000. One guarded read uses the existing
bounded page reader (including custom overrides) to enumerate each requested cell
in its usual chronology, refuses partial/wrong-cell/duplicate/mismatched pages,
and returns the exact per-cell and flattened UUID order after an independent
closing check. Empty selection returns empty IDs; an incorrect zero cell count
still refuses. No draft, annotation, merge or export state changes. Renderer
selection verifies counts, per-cell order, flattened identity equality, candidate
scope, binding and cancellation before publishing; older contexts retain paging.

## Optional context and first-page response

Queue capability `initial_page: true` supports the strictly boolean URL option
`include_initial_page=true` on GET candidate `context` and POST protocol `prepare`.
The prepare body, request hash, operation UUID and durable receipt are unchanged.
Default responses retain their existing shape. Opt-in responses keep their normal
top-level fields and add a response-only `bootstrap` containing current context,
actor/project/protocol/candidate/root identity, requested filters, and the ordinary
60-row initial epoch page with exact cell counts. The existing protocol/page readers
are used, including custom overrides; both outputs share one opening generation
and independent closing check. No global or cross-request projection is reused.

Fresh preparation builds that page beside the context before the existing closing
transaction checks, then publishes only after successful commit. All replay paths
construct a new guarded bootstrap, including a receipt found after transaction
entry using the captured locked authority. They retain the original receipt's
body and never gain `fresh-v1`. The bootstrap is attached to a new response object;
neither stored receipt nor its nested context is mutated. Thus historic receipt
scope and fresh bootstrap scope may differ deliberately. Existing exact receipt
recovery remains available without the option. Failed closing checks or commits
publish neither context/page bundle nor freshness signal.

The pending tests cover fresh/ordinary/replay equivalence, changed-draft replay,
transaction-race replay, native token refusal and failed commit. Workbench tests
compare bundled context/page with independent fresh reads and reject closing changes.
## Linked internal export extension

The opt-in `linked-sqlite` format follows the [linked export contract](../../../docs/architecture/linked-sqlite-managed-recordings.md). Only this format omits duplicate full reference JSON staging. It delivers a compact SQLite database plus a standalone Python loader in a ZIP. Existing formats retain their staging and publication behavior. Selection, acceptance, and export receipts retain their existing authority.


## Exact selection manifests

Current contexts advertise `selection_manifests`. The read-only manifest endpoint
accepts up to 1,000 canonical UUIDs per 64KiB request with an upload UUID, offset,
exact total and current candidate scope. It rejects missing/duplicate/changed
batches, verifies pending membership and seals only the complete ordered set.
Manifests are process-local, actor/project/protocol/candidate/scope bound, expire
after 15 minutes without use and use a 32-entry eviction budget. Expiration or
eviction refuses rather than widening a selection. No draft or consent is created.

A selection token is a separate read option, never a typed metadata predicate.
Frozen list/tree/summary reads resolve it against current authority and constrain
the frozen recipe membership. Standard filters and closing attestation remain.
The selected-review command checks scope, version, availability, exclusions and
explicit review consent, then atomically replaces selected draft membership using
complete server decisions. Main publication still uses the existing preview,
operation UUID and durable acceptance receipt. Main tagging/undo bounds remain;
Workbench tree selection admits only the exact current pending cardinality.

## Pinned acquisition sets

`recording_workspace.validate_protocol_definition` retains the v1 single-clause
`eq` form (string return) and accepts an explicit `in` form (list return), limited
to 1–2000 distinct nonempty recorded names. Empty, duplicate and unknown shapes
fail closed. Native query evaluation uses a disjunction of exact names; source
refresh independently verifies complete membership against that set. Display
summaries do not define membership. Newly created pins always bind the exact saved
candidate revision, even when their starter query allows several protocols.
`workspace_protocol_identity` requires the reviewed IDs to exactly equal all IDs
in that revision; update/export compatibility requires every member to fit the
allowed set. No epoch is dropped or reassigned to make a mixed selection fit.
Rename changes only manifest display name with expected-name checking and an audit
record, retaining creation retry identity, binding and prior export provenance.
HTTP tests in `test_workspace_protocol_binding.py` cover mixed creation, export,
mismatch rejection and rename/retry; native SQL durability remains unqualified.


## Trace response encoding

Frozen trace reads retain the opening candidate scope, pending-membership check,
verified source window, closing generation/scope check, and native response
attestation. After those guards close successfully, JSON encoding operates on
the detached samples and response fences outside the DB/registration/annotation
locks, matching the global trace endpoint. A changed closing scope still refuses
before sample serialization. The Workbench integration tests hold encoding open
and verify an unrelated overview read can complete, plus changed-scope refusal.

Foreground trace GETs may opt into `chunks=1..5` with the existing per-window
`count=1..100000` and nonnegative `start`. The response envelope contains exact
`windows`, shared epoch/stream/source/rate/units/total-sample identity, the initial
start and summed count, plus the ordinary candidate/query/binding/generation
fences. Windows are contiguous and stop at EOF, with at most 500,000 samples.
One opening/closing candidate scope covers the complete batch. A detached source
plan pins one stat signature and row/manifest authority; every H5 window retains
ordinary identity/rate/units/finite-value checks, and the final publication/source
witness must still match. Failure returns no partial windows. Custom trace readers
refuse batch admission rather than bypassing their policy. Requests without
`chunks` retain their existing response. Background batches are refused; encoding
occurs after the guards close. Source mutation between windows and final scope or
publication changes are covered by service and HTTP integration tests.

Frozen foreground batches can explicitly request the lossless binary64 transport
specified in [trace execution](../../../docs/architecture/trace-worker-execution.md#opt-in-binary64-foreground-transport).
The same opening/closing scope encloses the unchanged scientific batch read. The
response codec runs only after guard closure; its metadata header retains all
candidate/query/binding/generation fences. Default JSON and source/scope refusal
are unchanged. Optional fixed-name elapsed headers separate guard opening, read,
closing and encoding without including project or scientific metadata.

## Bound-main revision-only context reads

Canonical bound-main context derivation may obtain its current query revision
through `ProtocolStateReader.read_revision`. The method obtains a fresh native
metadata/generation proof and returns the identical v3 revision without
materializing unused curation state. If native authority is unsupported or
unavailable, it executes the unchanged full-state oracle once. Unbound membership
and custom history readers keep the original materialized-state path. Explicit
transaction revision guards take precedence and retain their locked checks.

This stores no context or authority receipt. Main/candidate/base recipes,
cohort fingerprints, source eligibility, actor draft and pending membership are
still independently checked. Closing context derivation performs another fresh
revision read; foreign generation, in-place metadata and draft changes still
reject the response. Native metadata proof itself remains cohort-sized and can
fall back; this is not an O(1) authority claim. Workbench tests exercise the actual
native metadata reader with explicit generation doubles and verify equivalent
revisions, one fallback invocation, custom/unbound behavior and late-change
refusal. Actual MySQL timing and transaction qualification remain separate.

### Prepared display diagnostic boundary

The prepared display route may open `workspace_trace_native.capture_native_timing`
only for the existing opt-in trace timing dictionary. This is an observability
seam, not read admission or authority: the same batch, source checks, geometry
and wire bytes remain required. Only the native module's fixed numeric metric
allowlist is emitted. See the [native diagnostic contract](../../../docs/architecture/trace-worker-execution.md#opt-in-native-read-diagnostics)
for cleanup, thread/GC attribution and timing limits. The timed/untimed route
example in `python/tests/test_trace_views.py` compares the complete wire bytes.
