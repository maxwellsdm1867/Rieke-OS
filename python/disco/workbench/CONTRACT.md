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

Project/protocol/candidate/baseline/main UUIDs, recipe hashes, metadata fingerprints,
actor draft version, source/query/binding/shared-annotation witnesses are separate
identities. Pending membership is candidate minus baseline minus current main.
Source eligibility and exact frozen fingerprints constrain reads and acceptance;
labels and current metadata do not substitute for historical witnesses. Counts mean
epochs or distinct cells, never interchangeable totals.

`ProtocolWorkbench` owns versioned prepare/context/draft/preview/accept choreography.
Draft batches are bounded to 250 boolean decisions. Selected preview uses saved
selected+reviewed, nonexcluded eligible pending members; all mode uses eligible
pending minus explicit exclusion. Additive acceptance preserves all previous main
members and their curation. Opening, highlighting, deferring, hashing or exporting
never grants scientific approval. Actor identity and expected authority fences stay
explicit at each mutation.

Cumulative preparation uses current queue/main/source/query authority and preserves
old decisions only for the same fingerprints. Changed draft/scope/binding/query/
preview or conflicting lineage rejects. Multi-request renderer draft batches may
partly commit; refresh after a later failure. Durable operation UUID replay and
uncertain request recovery keep their existing exact body/root/receipt semantics.
No client-intent cohort key or remembered view acquires backend authority.

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

[workspace_export_artifacts.py](../../workspace_export_artifacts.py) stays flat as
the adopted lazy format materialization seam. It already hides writer selection
behind a caller-frozen package and caller-bound adapters, while callers retain locks,
validation, staging, failure cleanup and publication. It returns an artifact Path,
not an export-success receipt. Adapter exceptions propagate and partly staged files
remain caller-owned. Its existing MATLAB/SQLite imports stay lazy; the workbench
export tail remains separate. This wave neither universalizes that helper nor runs
its adapters. See the existing [P05 contract](../../../docs/architecture/0.1.8-export-materialization-design.md).

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

The read reuses the private shared-annotation snapshot already captured by
`context`, builds a request-local UUID index only when branch coverage is requested,
and applies it to exact bucket membership. No per-epoch queries or extra snapshot
read is added. The existing response-end scope check rejects changed annotation
witnesses. Private snapshot records are never part of the public context payload.
Frontend saved-tag badges require matching current candidate scope and complete
validated counts; partial coverage and unavailable/retained reads remain distinct.
Badges use neutral styling. Green/blue branch switches describe the separate
ephemeral incoming selection command, never shared-tag coverage.
Executable cases: `test_workspace_workbench.WorkbenchTests` coverage tests and
`workspace-app/src/treeTagCoverageWorkflow.test.js`.

## Response-local native attestation

Read-only GET and existing preview, tree-page and candidate-summary POST routes
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
