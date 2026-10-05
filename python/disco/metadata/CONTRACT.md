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
| [typed_lifecycle](typed_lifecycle.py): TypedGeneration, prepare | Prepare a typed sidecar only from a verified native reader; retain native lease through worker completion/publication/failure. Preparation is not publication. |
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

## Lifetime and source witnesses

Projection, native and typed generations keep their existing independent witness
recipes. WorkspaceService hashes the real projection/object implementation files
plus its own implementation; its native recipe hashes disk index, tree, predicates
and object encoding in the existing order. prepare hashes the real typed_index and
typed_query files in the existing order. Aliased imports still expose each actual
leaf's __file__; they never hash this inert initializer instead.

The digest inputs are file bytes, not renamed package labels. Import-path changes
alter some implementation bytes, so these ordered witness digests change and may
conservatively rebuild disposable generations. No digest override, cache reseal,
persistent science change or claim of unchanged cache keys is authorized. Build,
reopen and cold-start costs have not been measured for this relocation.

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
