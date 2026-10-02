# Metadata performance strategy: primary-source research

Date: 2026-09-30 (America/Los_Angeles). Scope: strategy for browsing 100,000 to 1,000,000 recording epochs. This note makes no production changes and reports no new benchmark. The measured baseline comes from the separate everyday-action experiment at source commit `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`.

## Decision

**Retain the existing SQLite derived metadata index and native MySQL annotation store for the first optimization pass. Make tree and filter reads bounded before considering an engine migration.** This is an inference from the measured application behavior and official database documentation, not a guarantee that SQLite meets the million-epoch target.

The actual native 100,000-epoch path already returns 60 epoch rows in approximately 56 ms and epoch details in 71 ms. Uncached tree APIs take approximately 2–2.7 seconds and a contrast filter preview 3.9 seconds. These differences favor investigating work performed by particular endpoints. They do not establish a general storage-engine limit. The four-minute index-build stops at larger sizes establish an unqualified import path, not a maximum database capacity.

## What established systems do

### Seek into an indexed page

SQLite documents scrolling-window pagination using the last displayed compound key in the next `WHERE` predicate. Its `OFFSET` approach computes and discards preceding rows; cost grows with the offset. A matching index supports the alternative row-value comparison. Use a stable unique tie-breaker, explicit ordering, and cursor fields with defined null handling. [SQLite row values and scrolling windows](https://www.sqlite.org/rowvalue.html#scrolling_window_queries)

SQLite's planner documentation explains multicolumn indexes for multiple predicates and covering indexes that provide both filtering and output columns. An appropriate index can also satisfy ordering without a separate sort. These are capabilities, not proof that the current tree queries use them. [SQLite query planning](https://www.sqlite.org/queryplanner.html)

**Disco inference:** make a tree page query return the requested child nodes, `has_more`, and a continuation cursor. SQL should group or look up the relevant scope directly; Python should not construct the full hierarchy to obtain a page. Represent all matching epochs by a predicate or server-side result handle, rather than repeatedly transporting every matching UUID. Database work for arbitrary broad filters may still depend on the matching dataset; bounded JSON alone does not bound query work.

### Persist repeated summaries

PostgreSQL materialized views persist query results as a relation that can be indexed. Their documentation explicitly acknowledges the freshness tradeoff. `REFRESH MATERIALIZED VIEW` replaces contents, and concurrent refresh has prerequisites including an eligible unique index and an already populated view. The pattern is useful independently of choosing PostgreSQL. [PostgreSQL materialized views](https://www.postgresql.org/docs/current/rules-materializedviews.html), [refresh semantics](https://www.postgresql.org/docs/current/sql-refreshmaterializedview.html)

**Disco inference:** store structural summaries for each immutable source generation: date/cell/block parent relationships, child counts, labels, and ordering keys. Query those for an unfiltered tree. For arbitrary metadata filters, compute exact scoped aggregates in SQL or cache their result by predicate and generation. Base summaries alone cannot answer arbitrary filter intersections. Do not return every facet value and every match merely to preview a filter; return a count, a bounded sample/page, and only requested facet summaries. Label any delayed or approximate count explicitly.

Use bounded caches keyed by project identity, immutable metadata generation, protocol/scope, canonical predicate, page cursor, and any annotation/curation revisions that affect the result. Retain the existing integrity verification and cache lifecycle rather than replacing scientific identity with TTL-only freshness. Cache size and lifetime must be limited; million-member scope lists are not small cache entries.

### Build once, incrementally reuse

SQLite recommends grouping insert operations in transactions to amortize transaction overhead. Its FAQ explicitly warns that turning synchronization off can risk corruption. [SQLite insertion/transaction FAQ](https://www.sqlite.org/faq.html#q19)

Code inspection found that `DiskMetadataIndex._build` already commits the main insertion phase once. Therefore, “add a transaction” is not a sufficient diagnosis. It creates secondary indexes before insertion, serializes/fingerprints per epoch, and builds catalogs after loading; split phase timing is needed before choosing a change.

PostgreSQL's bulk-import documentation recommends bulk loading a fresh table before building indexes and collecting planner statistics afterward. Applying deferred **non-unique secondary** index creation to Disco's disposable SQLite build is a hypothesis to test, not a cross-engine speed promise. Preserve identity uniqueness and final validation. [PostgreSQL bulk population](https://www.postgresql.org/docs/current/populate.html)

SQLite recommends `PRAGMA optimize` after schema changes, particularly `CREATE INDEX`. Its bounded analysis behavior is documented for SQLite 3.46.0 and later; inspect the shipped SQLite version before relying on that behavior. A sealed read-only database cannot be updated by normal readers: gather and persist useful planner statistics during building, before sealing. [SQLite optimize pragma](https://www.sqlite.org/pragma.html#pragma_optimize)

**Disco inference:** stream source records through bounded batches; avoid retaining all detail objects or duplicating all basic metadata in Python. Consider immutable per-source projections plus a project manifest so adding one source need not rebuild every unchanged source. This changes cross-source query planning and integrity contracts, so measure it as a separate architectural experiment. Build a provisional index in a worker with progress/cancellation, validate and seal it, then publish; readers should continue using a validated generation until the replacement is ready.

## Choosing an engine

| Choice | Reason to use it | Decision for Disco now |
|---|---|---|
| Existing SQLite index | Embedded local relational reads, compound indexes, deterministic paged lookup | Optimize existing read model first. Keep acquisition data and scientific annotations authoritative elsewhere. |
| DuckDB | Large analytical scans and aggregate workloads; column projection/filter pushdown | Candidate only if bounded SQL summaries still miss targets and profiling identifies scan/aggregate cost. Test the exact workload against SQLite. |
| PostgreSQL | A shared service needing server-side collaborative reads/writes and indexed persistent summaries | Revisit for a hosted collaboration requirement, not simply because a local project has a million epochs. |
| Dedicated search/facet service | A demonstrated requirement for sophisticated ranked text search or facet scale beyond local SQL | No demonstrated need in this benchmark. It adds another synchronized projection and runtime. |

DuckDB states that many small concurrent queries are not its primary design goal. It recommends reusing connections and prepared statements for repetitive small queries. Its in-process model supports a single read/write process or multiple read-only processes. Current documentation also describes multi-process writes through the Quack remote protocol (documented as beta in v1.5.2), or DuckLake with a PostgreSQL catalog. Thus a blanket claim that DuckDB cannot support multi-process writes would be outdated; these options introduce a different deployment architecture. Do not substitute it for the annotation store solely because it accelerates analytical workloads. [DuckDB workload tuning](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads), [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency)

SQLite WAL permits simultaneous readers and a writer, with one writer at a time. It requires same-host shared memory and does not work across a network filesystem; checkpoints also matter for latency. Disco's published metadata index is immutable, so enabling WAL is not the first response to its read bottlenecks. If a future mutable local cache uses WAL, keep it on a local disk, preserve appropriate durability, and measure checkpoint effects. Acquisition H5 files may remain on shared storage. [SQLite WAL](https://www.sqlite.org/wal.html)

## Verification before committing to the architecture

Instrument native tree and filter endpoints by phase: scope/revision preparation, SQL execution, decode/grouping, facets/counts, response serialization. Record response bytes and peak process memory as well as elapsed time. Capture representative query plans; SQLite exposes scans, indexed searches, covering indexes, and temporary sorting/grouping structures through `EXPLAIN QUERY PLAN`. Its textual output is for diagnostics and can change, so correctness tests must not depend on exact plan strings. [SQLite query-plan diagnostics](https://www.sqlite.org/eqp.html)

Then compare one change at a time on 100k, 500k, and 1m fixtures with realistic metadata diversity, selective and broad filters, high-cardinality facets, dense annotations, and repeated edits. Check exact identity/order/count equality against a reference; ensure annotation changes invalidate affected summaries. Measure first invocation and steady-state separately, use browser completion for user-visible latency, and report sample counts. Import/build and prepared-project reopen are different measurements. Targets such as sub-200 ms page/preview interaction are acceptance goals, not achieved results or documentary guarantees.

Preserve missing-versus-null behavior, value types, numeric comparison, Unicode semantics, custom hierarchy splits, curation scope, and provenance during SQL translation. A compact selection handle must include the relevant revisions; freeze its exact membership at the appropriate save/export or write commit boundary. Existing 60-row frontend paging, ancestor caches, and `AbortController` request cancellation are already useful foundations. Extend them only as needed for the new backend contract; these measurements do not call for replacing React or maintaining separate browser/desktop UI sources.


## Proposed implementation order for Disco

The next work should consist of independently reviewable changes, each evaluated with the existing native and browser action harnesses. This sequence is a proposal; no optimization or product migration has been applied.

1. **Establish phase receipts for the two slow native endpoints.** Separate scope preparation, selection revision, SQL, grouping, facet/suggestion calculation, and serialization. Existing legacy-fallback profiles are useful clues but cannot attribute genuine native tree latency by themselves. Establish realistic fixture distributions before using a million-epoch qualification target.
2. **Implement a database query for one tree page.** Start with the ordinary date/cell/block layout. Add a compact typed navigation projection and only the composite indexes required by those queries. Query an explicit parent scope, return 60 children plus a continuation cursor, and decorate only those displayed nodes. Store reusable structural summaries with the immutable metadata generation. Handle arbitrary grouping fields through the existing value index with SQL aggregation, separately measured. Arbitrary filtered groups can still require scans of matching values; no promise of constant work is implied. Preserve deterministic ordering, missing values and anchor navigation. Introduce cursors alongside existing offset contracts before changing the UI; seek paging must also preserve stable previous-page behavior.
3. **Split filter results from full catalog analysis.** Return a canonical predicate/selection handle, bounded rows and exact counts when affordable. Fetch requested facets separately; defer full layout suggestions and complete catalogs. Keep an explicit pending state if a count is computed later. A global/unfiltered rollup must never stand in for a filtered count. Avoid repeated UUID arrays in Python, HTTP and temporary scope tables. A heavy result that truly needs materialization may use a bounded, expiring server-side result table; it should not be rebuilt for every branch/page. Freeze exact membership for a save/export or scientific write at its established boundary, under the relevant metadata, source, protocol and annotation revisions. Changes during evaluation require retry or rejection, not a mixed snapshot.
4. **Make creation and reopen scale independently.** Add timing/progress for data conversion, insert/link construction, secondary index creation, catalog summaries, integrity check, hashing/sealing and publication. Compare secondary indexes built after loading, batched dictionary/link inserts, planner statistics before sealing, and removal of duplicate full Python row/fingerprint maps. Preserve source UUID identity, ancestor deduplication, integrity checks and atomic publication. Per-source reusable projections are a later architectural option if rebuilding unchanged sources is a major cost; do not introduce shards before measuring global-query overhead. Source-at-a-time publication must clearly identify the available subset until the full requested project is ready.

The frontend already bounds displayed pages, preserves ancestor pages and aborts superseded requests. Keep the shared React UI and current H5 window loading. Additional frontend caching should be byte-bounded and keyed by all result-affecting revisions; a tag edit should invalidate affected tag-dependent results without rebuilding unrelated structural summaries. Avoid adding another client framework purely for this performance task.

### Acceptance goals and comparison experiments

Suggested goals, **not measured achievements**: common native tree-page requests under 100 ms and browser branch/page actions under 200 ms on the 100k fixture; bounded filter-result preview under 250 ms, with any delayed expensive facets/counts measured separately. Verify whether these budgets remain feasible at 500k and 1m rather than extrapolating the 100k result. Include broad and selective filters, unusual sorting/missing values, large cells, many dates/protocols, high-cardinality fields and dense tags.

Use at least 30 action samples for a more useful latency distribution; keep first-use, warmed reads, prepared-project reopen and fresh import separate. Record backend and browser timings, response bytes, database work, Python/DB peak memory and import stages. Validate exact rows/order/counts and stale-revision behavior against the established reference, including missing-versus-recorded-null, numeric-versus-string values, case/Unicode, tag inheritance, protocol curation, source eligibility and exports. Maintain the existing H5 integrity behavior.

Only compare DuckDB for a remaining measured analytical scan bottleneck after the page/preview contracts are bounded. Prefer existing MySQL or a separately evaluated PostgreSQL service if hosted collaboration becomes the requirement. A new engine must win an end-to-end comparison including import, memory, deployment and scientific exactness, not just an isolated SQL benchmark.

### Current code locations behind the proposal

- `python/workspace_tree_pages.py:93`: selection revision encodes sorted member UUID/fingerprint pairs.
- `python/workspace_tree_pages.py:176`: navigation scope gathers all rows and requested grouping values; `page` then groups/sorts before taking the displayed slice.
- `python/workspace_disk_index.py:236`: connection helper populates a temporary scope, including all epochs when no IDs are supplied.
- `python/workspace_disk_index.py:291`: scoped catalog computes field statistics; `_suggest` at line 520 reads candidate columns for signatures.
- `python/workspace_service.py:1005`: preview combines scoped catalog analysis and explicit UUID/fingerprint membership.
- `python/workspace_disk_index.py:80`: builder inserts data, then constructs full summaries before sealing; existing secondary indexes are maintained while loading.
- `workspace-app/src/components/ColumnTree.jsx:43`: request cancellation, revision checks and ancestor reuse already exist.

These code observations identify broad work; phase timings are still needed to assign each one's cost on the genuine native path.
