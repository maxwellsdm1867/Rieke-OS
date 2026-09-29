# Incremental metadata refresh

The toolbar's **Refresh metadata** action invokes `/api/metadata/refresh` and
validates the project read model. It does not import an H5, apply a protocol
proposal, or recreate an export. Its receipt records source reuse/rebuild counts,
elapsed time, and completion time; the SQL activity log records success or failure.
An audit-write failure is reported separately from successful validation.

Verified projections now persist in two disposable disk caches: compressed
per-source projections under `cache/source-projections`, and a sealed SQLite
metadata index under `cache/metadata/<generation>.sqlite`. These caches are not
scientific sources of truth and do not replace DataJoint, source H5 files, or
saved dataset revisions.

Each source key includes registration/manifest identity, the normalized metadata
checksum and filesystem signature, the H5 filesystem signature, and the projection
implementation contract. The complete index generation also includes the project
and index/tree/predicate code checksums. Metadata checksums and current SQL
protocol membership validation still run on refresh.

For an unchanged generation, the running service reuses its verified index. After
restart, it can reopen the same sealed index after SHA256, generation, project,
format/completeness, and SQLite integrity checks. This happens **before** decoding
complete source projection JSON. Source rows and fingerprints remain lightweight;
epoch details load lazily from compressed SQLite records through a bounded shared
cache. Cell descriptors read only one epoch per cell. Raw trace samples continue
to load on demand.

If no matching valid index exists, the service reuses verified per-source
projections where possible and validates/rebuilds missing or changed projections.
It then builds a **whole new derived index** for the new generation. Incremental
replacement of individual source partitions inside that index is not implemented.
A malformed cache is a cache miss, never permission to skip source validation.
Cache reuse and index reuse are separate: two reused sources can still require a
new index after an index-contract change.

Initial indexing and changed-generation index rebuilding currently block the
service load/refresh path. An indexing phase is recorded internally, but this is
not yet a fully background job with detailed visible build progress. See
[SCALABILITY.md](SCALABILITY.md) and the exact
[disk-index benchmark](DISK_METADATA_INDEX_BENCHMARK.json) for measured cold and
warm costs and workload limitations.

The service read model is published only after validation succeeds for the
complete refresh. Derived cache files may already have been written, but they do
not make a failed refresh queryable.
Failures leave the service unavailable for scientific queries until a successful
refresh; they do not publish a partially refreshed catalog. The previous
successful refresh receipt remains distinct from the latest failed attempt.

**Check sources** in Data stores performs a lightweight filesystem availability
and size check. Each source reports when it was checked. Available means reachable
at that check; it is not a new full checksum guarantee. A size change is marked
Changed, and missing/unreadable sources remain visible in the inventory.

Imports already refresh the catalog and rerun saved queries after commit. They
now benefit from the same source cache. Protocol suggestions still require an
explicit Add; source checks and metadata refresh do not apply those suggestions.

Historical read-only validation before the disk-index/lazy-restart changes,
against the two-source project, measured 7.08 s for
the initial load (including connection startup), then 0.71 s for an unchanged
refresh. All 1,776 epoch read-model fingerprints and protocol results remained
identical; all five protocol SQL queries still ran. The live UI refresh returned
0.94 s with two sources reused, zero rebuilt, and a recorded audit event. Source
availability checks and their timestamps were verified in the live Data stores
view. See `metadata_refresh_validation.json` and `live_scale_validation.json`.

The historical timings above are not a measurement of the final disk-index
restart path. Final combined regression verification passed 348 Python tests,
107 frontend tests, and the frontend production build. Index tests cover exact
typed catalog/predicate parity, eager/lazy projection parity, source scope, fresh
metadata copies, concurrent cache readers, checksum tampering, and failed rebuild
publication. These tests do not imply instantaneous refresh for large projects.

The final live disk-index check is recorded in `disk_index_live_validation.json`.
For the same 1,776 epochs, eight cells, and two sources, a verified restart took
3.30 s including SQL startup; opening the sealed index took 47 ms. An unchanged
refresh took 0.42 s, including 0.33 s for SQL queries. Both operations succeeded
with full projection decoding and H5 header reads deliberately forbidden. All
typed field values, field catalogs, and epoch fingerprints matched exactly.

Latest read-only production-project proof is in
[disk_index_live_validation.json](disk_index_live_validation.json): 1,776 epochs,
8 cells, and 2 sources. Restart succeeded with complete source-projection decoding
and H5 access deliberately blocked, with exact catalog and all typed-value parity
and unchanged fingerprints. Index reopen took 47 ms; total startup was 3.30 s
(including 2.72 s of SQL checks). Unchanged refresh took 415 ms, including 331 ms
of SQL checks. These are measurements of this project, not 50,000-epoch timings.
The test counts above describe the documented verification checkpoint.
