# Existing metadata interfaces

This package colocates existing disposable metadata readers and their lifetime
owners. Import the required leaf directly. The initializer performs no imports,
registration or eager native setup. No caller gains scientific authority from a
package import, cached row or successful disposable build.

| Existing interface | Responsibility and caller obligations |
| --- | --- |
| [typed_index](typed_index.py): build, TypedMetadataIndex, QueryCancelled, existing helpers/constants | Build and query a sealed typed sidecar over a verified immutable native base. Own a thread-confined reader, retain its paired native lease and close it. |
| [typed_query](typed_query.py): existing compiler/constants/functions and _TypedQueries | Exact typed predicate compilation used by typed_index; no new facade or visibility change. |
| [disk_index](disk_index.py): DiskMetadataIndex and existing constants | Sealed disposable native metadata projection, lazy details, catalogs, values and fingerprints. Caller supplies exact generation/project/source inputs and publication fence. |
| [metadata_objects](metadata_objects.py): Encoder, Decoder, canonical and existing constants/helpers | Lossless, source/UUID-owned ancestor storage; independent returned DTOs and bounded decoded-object retention. |
| [cache_lifecycle](cache_lifecycle.py): CacheNamespace, CacheLease, CacheLeaseGroup | Writer locks, reader leases, current-generation publication and conservative disposable reclamation. Caller closes leases; failed or stale work cannot authorize publication. |
| [projection_cache](projection_cache.py): ProjectionCache, VERSION | Source projection storage with lazy lossless ancestor reconstruction and leased publication. |
| [projection_contract](projection_contract.py): resolve_projection_contract, OWNER_PATHS | Exact reviewed whole-file compatibility; unknown vectors keep distinct witnesses. Bounded [literal review data](projection_contract_receipts.py) never changes cache seals or scientific admission. |
| [typed_lifecycle](typed_lifecycle.py): TypedGeneration, MembershipCache, VerifiedMembership, prepare | Prepare a typed sidecar only from a verified native reader; retain native lease through worker completion/publication/failure. Preparation is not publication. |
| [explore_queries](explore_queries.py): existing query_context, typed_reader, field_registry, SummaryJobs, explore_page, route registration and companion functions | Query and requested-summary orchestration; caller retains source eligibility, protocol binding, annotation authority, cursor and HTTP composition. |
| [search](search.py): search_workspace, register_search_routes | Bounded metadata lookup; no waveform reads, SQL text interface or mutation. |

These are named existing interfaces, including their current module attributes.
The package does not hide them behind a single initializer or require unrelated
owners to load together. Caller imports retain existing local aliases; lexical
helpers and existing imported helpers keep their behavior. Progressive discovery
starts at this table, then the chosen leaf and its executable examples.

## Exact values and read authority

Typed queries keep missing distinct from recorded null and Boolean distinct from
number. Numeric equality preserves exact integer/float rational identity; original
JSON values are returned. Arrays, objects, escaped fields, chronological rank
(date/start time/epoch UUID) and conjunctive scopes retain their existing meaning.
Empty source/epoch lists mean empty scope. Backend ranks are not public cursors.
Requested facets retain first chronological occurrence, missing/present counts and
existing 60-value truncation. This does not prove all raw fields are filterable.

Object encoding binds source, ancestor kind and UUID. Identical display labels do
not merge owners. Conflicting content for the same owner rejects, including
Boolean/number, integer/float, signed-zero, Unicode and order differences. Missing,
wrong-role, wrong-parent, wrong-source and corrupt-checksum references reject.
Decoder results remain independently mutable; cache accounting is not a process
RSS bound. No unit conversion or scientific value normalization is introduced.

Native index opening checks completion, format, seal, project/generation and file
signatures. Build uses a temporary asset, writer lease, integrity/seal checks and
replacement. Incomplete or failed builds are not publishable. Typed default open
hashes the sidecar seal and verifies native identity; open_verified borrows proof
only from a live verified reader with before/after file checks. Queries recheck
signatures. Unknown fields/operators, invalid bounds and malformed values retain
errors; a missing detail UUID remains KeyError.

A typed reader owns its SQLite connection and disk-backed temporary query state.
Do not interleave operations with an active membership iterator. cancel may be
called across threads; interruption raises QueryCancelled, never empty success.
close is idempotent. Native index reading has no generic cancellation token.
Query orchestration preserves generation, source eligibility, binding, publication
and annotation fences; disposable metadata cannot stand in for those proofs.

## Explicit membership query work

`DiskMetadataIndex.cell_epoch_ids` and `cell_epoch_count` read the complete
registered cell through `epochs_cell`, without decoding unrelated row/detail JSON.
IDs retain registration order; the count does not hydrate rows. The existing
connection lifetime checks index integrity before and after each query. The
`WorkspaceService.cell_rows` and `cell_epoch_count` interface supplies canonical
UUID handling and a row-mapping fallback for legacy/custom index adapters.
Cell QC and annotation display counts share this interface. These operations
include excluded sources, as the earlier registered-cell scans did; they do not
represent a protocol's narrower membership or grant scientific action authority.

For the native path, the published index and basic-row mapping must describe the
same immutable metadata generation. Callers do not edit cell membership in place;
refresh publishes replacement mappings and an index together. Index-less/custom
index adapters retain live mapping behavior. This is not permission to pair an
old sealed index with independently edited row maps. `cell_rows` also rejects a
returned row whose recorded cell disagrees with the requested indexed cell.

The added SQL index is built with a new disposable generation because refresh
hashes `disk_index.py` into its generation identity. Existing artifacts are never
modified or resealed in place. The additive index does not change format 3's
recorded data layout; a standalone caller explicitly reopening an old format-3
file with its old generation can still read correctly but will not acquire this
new acceleration until rebuilt. One-time generation rebuilding is distinct from
rebuilding a cohort on every browse operation.

Explicit UUID scopes are admitted through the native UUID index before predicate
compilation. When sources are supplied, source eligibility is applied in one batch over
admitted members; no project-wide source-member relation is materialized first.
One-shot UUID/source iterables are consumed once, duplicate/unknown UUID handling
is unchanged, and empty sources or membership still mean an empty intersection.

Explicit scopes use the existing correlated epoch/field predicate and facet
paths. Contains and wide-number comparisons enumerate distinct dictionary values
reachable from admitted members, retaining the exact native predicate evaluator.
Global discovery retains its existing dictionary/source strategy. Arbitrary UUID
iterables retain connection-owned scratch admission. Canonical frozen protocol
bindings instead reuse an immutable, session-private SQLite membership file via
`TypedGeneration.memberships`. Its key contains the typed/native generation,
project/protocol/revision/version and exact source eligibility. Only the canonical
header/recipe provider receives this shortcut; unbound/custom policies fall back.
Warm readers attach the verified file read-only without recipe hydration, UUID
iteration or membership insertion. SQL references the indexed table directly; a
view alias would force SQLite to reconstruct an IN-list. Existing opening/closing response fences
retain authority. Filters and annotations do not change base membership.

Construction is serialized and publishes only a fully committed file; exceptions
remove the unfinished artifact. Files are never overwritten, and signature changes
fail closed. An attached reader retains the file, its private directory and native
owner through connection close. Retention is an LRU of at most 16 entries/256 MiB,
except that a single larger membership is allowed; eviction never truncates scope.
Restart loses this acceleration cache and first use rebuilds it. These files are
not durable scientific state and grant no standalone authority. Session-private
files avoid cross-process publication and immutable-file repair races.

The typed-index truth-table/facet tests now include explicit scopes, source
intersections and empty cohorts; dictionary tests count evaluated values.

## Lifetime and source witnesses

Projection, native and typed generations keep their existing independent witness
recipes. WorkspaceService hashes the real projection/object implementation files
plus its own implementation; its native recipe hashes disk index, tree, predicates
and object encoding in the existing order. prepare hashes the real typed_index and
typed_query files in the existing order. Aliased imports still expose each actual
leaf's __file__; they never hash this inert initializer instead.

The digest inputs are file bytes, not renamed package labels. Import-path changes
alter some implementation bytes, so these ordered witness digests change and may
conservatively rebuild disposable generations. That relocation authorized no
digest override, cache reseal, persistent science change or claim of unchanged
cache keys. Build,
reopen and cold-start costs have not been measured for this relocation.

### Reviewed source-projection compatibility

`projection_contract.resolve_projection_contract` now selects the source witness
from the existing four ordered whole-file digests plus its own whole-file digest.
An exact reviewed five-file vector may return the recorded legacy four-file
checksum. Unknown bytes, mixed vectors, missing or invalid review data use the
full five-file checksum instead. Missing or invalid owner digests fail rather
than silently omitting a witness. Index and typed-sidecar recipes are unchanged.

`projection_contract_receipts.py` is bounded literal data, parsed without executing
it. Each decision binds a complete vector, legacy witnesses and checksum,
rationale and evidence. It permits no wildcard or independent per-file match.
Its data is excluded from the resolver fingerprint to avoid a self-reference;
the application profile and staged integrity manifest include both files.
The mapped `test_workspace_projection_contract.py` requires an explicit compatible
or breaking decision for the current vector. Updating a receipt requires review
of the actual owner changes and equivalence evidence, not merely copying hashes.

The first decision covers the reviewed 0.1.12 `add33d1` implementation: four
new-import CLI lines do not change existing-project projection semantics. Opening
its unchanged cache uses its original generation and seal. No cache is renamed,
resealed, relabeled or migrated. Complete SQL validation, source/metadata
signatures, source eligibility, generation checks and leases remain mandatory.
An incompatible recording, decoder, index or query change still invalidates or
refuses through its existing witnesses. Reuse never replaces scientific admission.

The [version-opening audit](../../../docs/dev/project-version-first-open-2026-10-14.md)
separates native historical-cache evidence from equivalent-builder unit tests and
from timing. Cache compatibility alone does not eliminate cold schema setup or
the SQL validation required on every reopen.

Cache namespaces retain current manifests, exact owner identity, writer/reader
locks and orphan/foreign-file conservatism. Old readers keep assets alive until
last lease release; active builders protect staging. Typed generation preparation
keeps the native lease and releases it on failure. Query workers keep their
cloned reader/native lease until completion. Publication remains caller-owned.

## Dependency and deletion review

Typed compilation, tree/predicate semantics and object encoding are in-process.
SQLite and owned temporary-file storage are local-substitutable dependencies;
existing tests use SQLite itself with disposable files. HTTP route adapters and
native database/source validation are remote-owned or native dependencies of
specific orchestration leaves, not reasons to eager-load the package. Existing
Flask/native/recording dependencies remain on their original call paths; no new
port is invented solely for tests.

Deleting the substantive readers would push seal, typed-query, source-ownership
and lease reasoning back into their callers. Deleting only this folder placement
would restore the same flat modules. This change improves locality and discovery;
it does not claim a deeper interface, fewer caller obligations or fewer exports.
Nearby tests exercise existing interfaces; cross-owner tests stay at their current
owners. No duplicate test layer or private export demotion is introduced.

## Executable examples and bounded checks

The [disk-index fixture](tests/test_workspace_disk_index.py) supplies complete
owned row/detail/source DTOs and uses DiskMetadataIndex.build/open/close. The
[typed tests](tests/test_workspace_typed_index.py) build a sidecar from that base,
query exact values and scopes, and exercise cancellation, seal changes and
verified-open lifetime. Use these complete fixtures rather than inventing a
partial scientific witness.

[Object round trips](tests/test_workspace_metadata_objects.py) exercise
Encoder.encode and Decoder.decode with owned SQLite memory. The
[exact object contract](tests/test_workspace_metadata_object_contract.py) retains
numeric-bit, source/parent, mutation-isolation and corrupt-object cases. Existing
introspection assertions are preserved; relocation adds no private test exports.

From repository root, using a source-test Python, the bounded standard-library lane:

```sh
PYTHONPATH=python:python/tests python3 -B -m unittest -v \
  disco.metadata.tests.test_workspace_metadata_objects \
  disco.metadata.tests.test_workspace_metadata_object_contract \
  disco.metadata.tests.test_workspace_disk_index \
  disco.metadata.tests.test_workspace_typed_index
```

These 55 cases use owned SQLite files and standard-library dependencies; they do
not import recording/Flask/native scientific stacks or certify real data. Other
cross-owner query/projection/search/state/trace cases retain their own environment
requirements. In particular cache lifecycle/crash suites contain process killing;
they are not part of this lane. Native/HTTP/trace/qualified benchmarks and full
application execution require their separately authorized gates.

Root integration owns profile v2 file entries, current benchmark source paths,
Python named-public-module policy, CI local-test discovery, ledger and navigation.
Run their source/mapped checks after those exact changes are composed. Historical
qualification receipts and suite identity remain tied to their measured revisions.
The fixed [benchmark guide](../../../docs/dev/benchmarks.md) and
[registry](../../../benchmarks/registry.json) retain unmeasured field completeness,
fallback, native authority, memory/build/open and whole-app qualification gaps.
