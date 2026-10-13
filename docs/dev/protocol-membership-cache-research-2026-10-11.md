# Persistent protocol membership for Disco typed readers

Researched 2026-10-12 UTC / 2026-10-11 America/Los_Angeles. Read-only inspection of `/private/tmp/disco-membership-local-20261012`; no application edits or large benchmarks.

## Recommendation

**Build one immutable, disposable membership SQLite sidecar per trusted protocol binding and metadata generation; attach that same file read-only to each short-lived typed reader.** The sidecar contains only indexed member identities (and optionally chronology ranks), not copied epoch metadata or traces. Subsequent pages, summaries and tree queries reuse its rows without UUID enumeration, hashing, SQL inserts or full-table verification on each request.

This fits the existing design better than keeping a shared mutable SQL connection. SQLite TEMP tables are connection-private and disappear at connection close; they cannot solve reuse across current reader clones. SQLite shared-cache mode is discouraged by its maintainers and is unnecessary for independent connections reading an immutable file. [SQLite TEMP databases](https://www.sqlite.org/tempfiles.html#temp_databases), [SQLite shared-cache mode](https://www.sqlite.org/sharedcache.html).

## Existing integration evidence

- `disco/metadata/explore_queries.py::typed_reader` creates `owner.clone()` for each operation and closes it afterwards. The owner keeps native and typed generations alive. A TEMP-table cache attached only to the reader would be discarded every time.
- `typed_scope` currently hydrates `service.binding(protocol)` and produces an epoch UUID generator for every protocol operation. This is the correct seam to return a trusted reusable membership handle instead.
- `typed_index.py::open_verified` accepts a live verified reader, checks its file/seal identity, and opens a thread-owned connection without rehashing the database. This is the model for cheap repeated membership attachment after one complete verification.
- `typed_lifecycle.py::prepare` uses a generation-derived filename, `CacheNamespace.writer`, reader lease, temporary build, validation and publication. Its owner retains both typed/native proof. Reuse this pattern for membership with explicit handling of the caveats below.
- `cache_lifecycle.py::CacheNamespace` already supports generation-named `.sqlite` files and seals, per-name writer locks, shared reader leases, atomic current-generation manifests, and exclusive-lock reclamation. It recognizes known derived files and avoids deleting symlinks or another project's sealed caches.
- `decisions/explorer.py::protocol_binding_header` reads a small row with project/protocol/revision/version. `protocol_binding` copies the frozen recipe; avoid that copy on cache hits. `bind` uses an expected-version check and transaction to publish binding plus audit event.
- `explore_queries.py::generation` already fences metadata, typed generation, source state, annotation state, publication and binding authority. `explore_page` checks before/after and signs continuation tokens; summary jobs also capture/recheck generation. Preserve these fences.
- `workspace_service.py::_epoch_page_identities` already demonstrates a cheap header fast path and full binding read only on cold membership. Its custom/unbound fallback compares explicit membership rather than blindly trusting a header.

## Proposed authority and query API

Cache key/receipt: format and construction-contract version, project UUID, native generation, typed generation token if ranks are stored, protocol UUID, immutable recipe revision UUID, binding version, and any source-eligibility policy baked into membership. Include the recipe content hash on cold verification. Native generation is essential because integer `epoch_id` values can refer to different UUIDs after an index rebuild.

A small internal `VerifiedMembership` object should hold the receipt, file signature/seal proof, typed/native owner, and cache lease. It is a process-local proof, not a serializable client capability. Public requests continue to supply only existing protocol UUID/filter parameters; reject client paths, SQL names, asserted cache hashes or purported trusted handle objects. Preserve custom binding/provider fallback unless its authority guarantees are explicitly equivalent to the canonical immutable recipe path.

A minimal schema is `members(epoch_id INTEGER PRIMARY KEY)`. Add `sort_rank INTEGER UNIQUE` only if page plans need direct membership chronology access; populate it once from the bound typed generation. Recipe order and public chronological query order differ in current code, so do not accidentally change ordering semantics. A receipt table records construction key, admitted count and completion marker. Keep any original recipe ordinal separately only if required by a consumer.

Attach with a constant schema name and bound URI filename:

```sql
ATTACH DATABASE ? AS membership;
-- URI comes exclusively from the verified server-side cache owner.
-- file:/.../generation.sqlite?mode=ro&immutable=1
SELECT c.epoch_uuid
FROM membership.members m
JOIN typed_core c ON c.epoch_id=m.epoch_id
ORDER BY c.sort_rank;
```

Use explicit schema qualification. A temporary VIEW alias can adapt existing SQL without copying rows, but do not run the current `DELETE FROM supplied_scope` path against that view. Maintain separate explicit-iterable and trusted-handle code paths. Normal predicates and facets should keep the earlier member-first point-lookup improvement. Each operation needs at most one membership attachment; do not attach every cached protocol to each reader. SQLite supports attached-file tables but imposes a connection attachment limit. [SQLite ATTACH](https://www.sqlite.org/lang_attach.html), [SQLite limits](https://www.sqlite.org/limits.html).

## Build, publication and updates

1. Capture the authoritative small binding header and live native/typed owner under the existing service/registration synchronization. Reuse a verified owner immediately if its tuple matches.
2. On a miss, read the binding/recipe once, verify it still corresponds to the captured tuple, and build membership through indexed UUID lookup. Preserve existing duplicate, unknown-UUID and source-policy semantics; do not silently weaken pinned-dataset reconciliation. Own the source generation lease throughout the build.
3. Build a uniquely named temporary file in the destination cache directory with `journal_mode=DELETE`, commit, close all builder connections, verify receipt and seal, then publish the complete artifact. Never expose a half-built database as a ready cache entry.
4. Recheck current binding/generation before installing the service's cache owner. A bind during construction must not let the old scope become the new protocol's active membership. The completed old immutable file can safely be discarded or retained by its old key.
5. On accepted membership updates, a new binding version/revision produces a new key. On native/typed rebuild, a new generation produces a new key. A query already holding the previous file may finish reading that snapshot; existing closing authority fences determine whether the result can be returned. Rebuild only on such misses, not every query.

Python `os.replace` is atomic when successful and may fail across filesystems. It does **not** make two independent renames (database and seal) one atomic operation. Use the writer lock for all initial open/build verification and publish readiness only after both are present, or use a single receipt-bearing artifact plus separately serialized first verification. Treat crash residue as an invalid disposable cache and rebuild. Sync artifact and directory when durable reuse is desired; cache loss is recoverable. [Python os.replace](https://docs.python.org/3/library/os.html#os.replace).

`immutable=1` is a strong promise: SQLite omits locking and change detection, and modifying the underlying file may yield wrong results or corruption errors. Never write, truncate or overwrite a published file used by a reader. For repair, avoid replacing the same published pathname while old verified owners remain live; fail them closed and use a fresh physical artifact identity or perform repair only after all leases are released. `mode=ro` alone does not assert immutability. [SQLite URI parameters](https://www.sqlite.org/uri.html).

WAL is unnecessary for build-once sidecars. It adds checkpoint and companion-file lifecycle issues; SQLite recommends converting read-only images to DELETE journal mode. Never publish just the main file while committed content remains in WAL. Attaching the MySQL-authoritative binding and SQLite scope cannot provide a distributed atomic transaction; the captured immutable revision and existing opening/closing authority fence supply application consistency. [SQLite WAL](https://www.sqlite.org/wal.html).

## Retention and bounded work

Hold a membership lease for every live verified owner/query, with its native/typed owners retained. Closing a reader closes SQLite before dropping the final lease. Publish the **whole bounded retained set** of membership names: `CacheNamespace.publish([latest])` would mark all other cached protocols obsolete and defeat switching reuse. Choose an LRU size/disk-byte budget and retain active protocol keys plus in-flight leases. Avoid enumerating the directory or collecting garbage on every cache hit; do cleanup on miss/eviction/publication/shutdown. Because existing lease release can call `collect()`, use an owner-retained lease rather than creating/releasing a collecting lease for every query.

A persistent disk hit after process restart must be verified once against current binding and generation and its full seal; warm hits reuse live proof plus constant-size file signatures. Do not recalculate the entire file hash, member count, UUID sequence or recipe content digest on each attach. Membership freshness is distinct from filtered-result freshness: annotation/filter changes may invalidate query results while the base immutable member table remains reusable. Source policy should only enter the membership key if it changes admitted members; retain existing protocol-versus-global source semantics rather than universally excluding sources.

## Verification before claiming completion

- Count builds, full binding/recipe reads, membership inserts and seal hashes: repeated pages/summaries on separate clones should each remain zero after initial admission.
- Test restart disk reuse, two concurrent first users, independent reader connections, protocol switching, empty membership, source-policy differences and immutable generation mismatch.
- Hold an old reader through rebind/rebuild and cleanup; it must keep reading its original snapshot, while closing freshness rejects its obsolete result and reclamation waits for its lease.
- Inject interruption before/after commit and between database/seal publication. No partial artifact becomes readable; retry rebuilds safely.
- Reject cross-project/generation handles, symlink substitution, corrupted seals, malformed receipts and stale/custom-provider authority.
- Compare exact membership, chronological pages, facets and missing/null semantics against the existing authoritative path. Benchmark cold build separately from steady-state reader attach/query; do not hide repeated O(M) preparation behind faster SQL execution.

## Implemented scope

The initial implementation uses session-private temporary SQLite files instead of
restart-persistent storage. This supplies cross-reader reuse with a smaller
lifetime contract: a completed handle is published only in memory, files are
never replaced, and reference lifetime protects active readers. It intentionally
does not claim restart reuse. Cache eviction rebuilds on later access and never
limits membership size. Existing generation fences still decide whether results
may be returned.

### Planner verification

A tiny EXPLAIN check found that a temporary VIEW alias produces LIST SUBQUERY
and SCAN membership.members. The implementation now refers directly to the
trusted constant relation membership.members, retaining SQLite's primary-key
IN-operator optimization. Regression tests and the cache benchmark verify this
plan property; legitimate sorting/aggregation remains query work over members.
