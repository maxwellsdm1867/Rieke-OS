# Rieke OS data-efficiency audit — 2026-09-29

**Conclusion:** the raw-signal loading design is sound, and the remaining scientific SQL data is small. The biggest remaining problems are repeated ancestor metadata, work tied to whole-project state rather than the requested operation, and derived/history data with no lifecycle. Fix those before reconsidering the database engine.

This is a code and data-lifecycle audit, not a request to enforce an arbitrary byte budget. A representation earns its storage by serving a current feature, recovery requirement, or deliberate scientific export. Recomputable copies need a clear invalidation and reclamation path.

## Scope and evidence

Inspected the active app checkout at `/Users/maxwellsdm/Documents/GitHub/epicTreeGUI`, including the recent persistence changes. Compared core modules with `/Users/maxwellsdm/Documents/GitHub/Rieke-OS`; snapshot, cache, index, explorer, curation, and MATLAB modules matched at measurement time. Service/API/SQLite-export modules differ between checkouts; source hashes are recorded in the measurements. Findings refer to the active checkout unless stated otherwise.

Read live SRM database metadata and records in a read-only SQL transaction, inspected SQLite files read-only, and sampled GETs and the read-only annotation POST. No scientific records or application code were changed by this audit. Its read-only POST exercises the existing snapshot hook; unchanged snapshots were not rewritten. This was not a concurrent-user or large-project stress test.

Evidence: [measurements](dev/data-efficiency-audit/measurements.json), [local measurement runner](dev/data-efficiency-audit/measure.py). HTTP timings are medians of three local requests, not service-level guarantees. JSON sizes are decoded/uncompressed representations unless explicitly labeled gzip. SQL `information_schema` row counts are estimates; the separately reported revision counts are exact.

| Measured item | Result |
|---|---:|
| SRM epochs / cells / sources | 1,776 / 8 / 2 |
| Database directory, allocated | 167.9 MiB |
| Parsed imports, allocated | 38.9 MiB |
| Metadata indexes, allocated | 104.9 MiB |
| Compressed source projections, allocated | 20.5 MiB |
| Exports, allocated | 57.9 MiB |
| State snapshot | 538,865 bytes |
| Snapshot excluding export recipes | 31,971 bytes |
| SQL explorer revisions / active bindings | 28 / 5 |
| Epoch references across SQL explorer recipes | 6,886 |
| Explorer recipe JSON in MySQL | 1,577,166 bytes |

## Prioritized findings

### 1. High: the snapshot hook runs on read-only POSTs and captures too much

[API hook](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_api.py:1416), [capture](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_state_snapshot.py:34), [query compaction](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_state_snapshot.py:99).

Every successful POST/PUT/PATCH/DELETE performs a synchronous snapshot while holding the shared database lock. POST is also used for annotation reads, tree pages, predicate previews, and membership queries. These operations can therefore rebuild backup state without changing anything. The equality check prevents a final file write, but occurs **after** reading SQL, decoding JSON, sorting, rerunning pinned queries, and serializing the snapshot.

`capture()` also fetches all explorer/preset versions before filtering to active ones in Python. On this small project, capture alone used 26 SQL queries, fetched approximately 2.21 MB in serialized result representations, took 53–73 ms, and peaked at 7.33 MiB of traced Python allocations. These figures exclude pinned-query compaction. A 401-byte annotation-read response took a median 121 ms; this is an observed endpoint time, not an isolated attribution of all latency to the hook.

**Change:** mark actual committed state mutations, snapshot only when that state revision changes, select active revisions in SQL, and separate immutable export recipes from current settings. Keep transaction/backup-failure semantics explicit rather than simply making backups fire-and-forget.

**Acceptance:** repeated annotation reads, previews, and tree-page requests perform zero snapshot captures; a tag save creates one recoverable checkpoint; snapshot work does not scale with obsolete revision history. Retain the existing restore and crash-recovery tests.

### 2. High: each epoch carries a large copy of its block metadata

[Detail construction](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_service.py:273), [per-epoch index storage](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_disk_index.py:74), [detail cache](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_disk_index.py:396).

The inspected epoch response was 123,639 bytes. Its block metadata accounted for 112,287 bytes, including a **111,371-byte `frameTimesMs` array**. That block contains 430 epochs. The block array is copied into each epoch's serialized detail record and reconstructed on each uncached detail read. The current 64-entry detail cache holds independent decoded copies, so compression on disk hides repeated decoding and allocation.

Serializing that shared array for all 430 epoch details represents approximately 45.7 MiB of repeated JSON. This is a representation-volume calculation, not a claim of 45.7 MiB extra physical disk or simultaneous RAM.

**Change:** store source/cell/group/block metadata once under immutable identity plus version; let epoch details reference it. Fetch and cache block context separately when needed. Preserve the recorded frame-time arrays exactly—do not discard them or infer an epoch-to-array mapping without validating the acquisition format.

**Acceptance:** inspecting many epochs in one block fetches/decodes the shared block object once; scientific metadata and legacy/export round trips remain exact.

### 3. High: obsolete cache generations are never reclaimed

[Generation selection](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_service.py:380), [index publication](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_disk_index.py:140), [projection writer](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_projection_cache.py:42).

There are **seven complete indexes**, each covering the same 1,776 epochs. They total 100.3 MiB logical / 104.9 MiB allocated; one index is 14.3 MiB logical. Source projections add another 20.5 MiB allocated. Changed signatures/code produce new filenames; cleanup removes temporary build files, not superseded published generations.

**Change:** introduce ownership/reference tracking for active generations and collect unreferenced indexes and projections after successful publication. A small explicit rollback set can be retained if it serves a real workflow. Do not remove a generation still referenced by a running reader.

**Acceptance:** repeated metadata refreshes/upgrades cease increasing retained cache generations once readers release old ones; unchanged restarts reuse the current index; interrupted rebuilds keep the last valid generation.

### 4. Medium: query-based recovery does not yet make live SQL pins query-based

[Revision creation](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_explorer.py:125), [recipe cache](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_explorer.py:58).

The recent backup optimization removes epoch lists from reproducible pins **in the backup**. Live `ExplorerHistory.create()` still stores a complete epoch list, UUID diff lists, and provenance in every new revision. There are 28 revisions containing 6,886 epoch references for five active bindings. `_recipe_cache` is also keyed by revision UUID without eviction.

The present 1.50 MiB of recipe JSON is modest. The concern is growth proportional to selected epochs × applied revisions, even when the source recordings do not change. This is not a reason to delete existing frozen history blindly: bindings, parents, and exports can refer to it.

**Change:** represent ordinary working pins as predicates + exact source/metadata versions + result digest, with sparse explicit overrides where a selection is not reproducible. Retain explicit frozen export records. Reclaim unreferenced materialized memberships and evict retired recipe-cache entries after auditing dependencies.

**Acceptance:** repeatedly applying a large unchanged query does not append another full epoch list; edited/tag-dependent subsets and immutable exports retain their scientific meaning.

### 5. Medium: the overview mostly transports historical event detail

[Overview events](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_service.py:623), [five visible events](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/workspace-app/src/components/Overview.jsx:34).

The overview response was 284,851 bytes; its `events` value alone was 265,071 bytes (about 93%). The server includes 25 full events while the view displays five. Old provenance-heavy events remain large even though routine new edits no longer create them. With gzip, the complete response body was 40,774 bytes: compression helps transport, but not SQL decoding and constructing the original JSON objects.

**Change:** return a small activity summary for the visible items. Load a selected event's full evidence through the existing detail endpoint. Keep detailed history where the user requests it.

**Acceptance:** overview does not retrieve full event payloads; opening an event still retrieves the original evidence.

### 6. Medium: bounded page responses still require whole-scope work

[Filtered rows](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_service.py:572), [epoch pagination](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_service.py:637), [temporary query scope](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_disk_index.py:172), [export-membership copy](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_curation.py:397).

A one-epoch page is small on the wire, but `filtered_rows()` constructs/decorates/sorts the whole protocol membership before slicing. Query helpers create and populate a temporary scope table for each call, and predicate matching materializes Python sets. Protocol binding access deep-copies the full recipe. Some summary paths deep-copy the project-wide export-membership index as well.

The measured one-epoch page was 3,793 bytes and 54 ms median. This small-project number does not establish a problem at present; the implementation establishes that work is not bounded by page size.

**Change:** reuse immutable query results by generation, push indexed filtering/order/pagination into the disk index where semantics permit, and return memberships for the requested scope rather than cloning all export links.

**Acceptance:** benchmark fixed-size pages at increasing epoch and export counts, checking CPU, rows visited, and peak memory—not just response size. Preserve exact typing, null/missing distinctions, and anchor ordering.

### 7. Medium: cold rebuild and MATLAB export can defeat lazy metadata loading

[Index build](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_disk_index.py:85), [cold source JSON load](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_service.py:418), [MATLAB catalog construction](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_matlab.py:139).

Changed generations build a complete new index. On a projection-cache miss, the full source JSON is decoded before index construction. Warm loading still keeps lightweight rows/fingerprints for every epoch in memory; only detailed metadata is lazy.

The MATLAB export builder separately runs `catalog(list(service.rows.values()), service.details, ...)` for the whole project before cataloging its selected records. A small export can therefore visit detailed metadata for unrelated epochs. The SQLite exporter also receives an already materialized complete package and hashes a complete serialized representation; it is not a streaming export pipeline.

**Change:** reuse the sealed index's schema/catalog for MATLAB exports, project only selected IDs/fields, and stream large export records where integrity checks allow. For ingestion growth, build per-source partitions or incrementally merge additions rather than rebuilding unchanged sources.

**Acceptance:** a small MATLAB export does not decode unrelated epoch details; cold/import benchmarks report peak memory and temporary disk alongside elapsed time. The older repository benchmark of 50,000 epochs reports a 63-second full index build and a 238 MB index; it is historical fixture evidence, not a new production measurement.

### 8. Medium: daily state backups repeatedly embed immutable exports

[Captured state tables](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_state_snapshot.py:17), [daily snapshot](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_state_snapshot.py:194).

Current settings/query/edit state is 31,971 bytes, while the complete snapshot is 538,865 bytes because it includes seven existing export recipes. On each active new UTC date a complete new SQLite snapshot is written, even if the state is identical. At the current logical payload alone, 365 active days would repeat about 188 MiB. That is arithmetic, not an observed annual workload.

**Change:** store immutable export recipes once by content hash and reference them from compact state snapshots; make each recovery package's dependencies explicit and verified. Deduplicate identical daily content. Preserve independent backups where they are intentional—deduplication is not a reason to leave recovery dependent on missing files.

**Acceptance:** adding a day of unchanged state does not duplicate every frozen export recipe; restoring a packaged snapshot works without the original live SQL server and detects missing immutable objects.

## What is already appropriate

- Raw traces are read from H5 in bounded windows of at most 100,000 samples. They are not copied into scientific SQL waveform rows.
- Source SHA verification is cached by file signature. A first trace can require a full source checksum read; that integrity cost is distinct from eagerly loading waveforms into memory.
- The SQLite detail cache is limited to 64 entries. The frontend epoch cache has entry, estimated-byte, and TTL bounds; adjacent prefetch is limited to metadata for two epochs. There is no evidence here of unbounded raw-trace caching.
- Typed field values and exported parameter sets already have deduplication. Export files intentionally contain queryable metadata plus a compressed exact archive; the measured frozen-record archive is only roughly 9–14% of each inspected SQLite export. Do not call all of that redundancy waste or remove reproducibility checks casually.
- Tags use stable target/author identities and current-state updates. Query last-run state updates a row per distinct predicate rather than appending one per execution. No-op shared-tag and layout saves are already handled.
- The reduced redo allocation and durable-commit settings should remain. Disabling crash recovery is not an efficiency improvement.

## Recommended order

1. Fix snapshot triggering and SQL projection; remove heavyweight event payloads from overview.
2. Normalize shared block/ancestor metadata and add cache-generation reclamation.
3. Move ordinary live pins to query/version descriptors and audit history dependencies.
4. Address page-level work, small-export behavior, and incremental ingestion with representative larger fixtures.
5. Deduplicate immutable objects in recovery archives while testing full restore bundles.

A reusable efficiency check for every new feature: identify its authoritative data; list every retained copy; distinguish configuration, cache, and frozen scientific output; specify invalidation/reclamation; measure bytes read/written and objects decoded for a common operation; test growth with data size and operation count separately; then verify recovery from the retained representations.

The storage reduction already completed remains valid. This audit identifies additional work; it does not claim the whole data lifecycle has already been optimized.
