# Native SQL tag workflow validation

The 500-epoch native SQL run passes. At 100,000 epochs all workflow correctness checks pass, but the overall receipt is invalidated by source changes during execution; its timings are provisional. The 100k run also exposes slow autocomplete (9–10 seconds), so these results do not support declaring the performance work complete. Neither run calls the legacy SQLite tag membership or refresh path.

Each fixture has three profiles, five seeded tags per annotation, cell annotations, and two independent protocol curation scopes. The timed sequence reads revisions and durably tags 10 epochs, reads revisions and tags another 10 in another cell, then immediately filters the exact 20. Five complete cycles were measured.

| Operation (median milliseconds) | 500 prior | 500 native | 100k prior | 100k native (provisional) |
|---|---:|---:|---:|---:|
| First 10 epochs: durable POST | 15.2 | 15.5 | 17.6 | 20.8 |
| Next 10 epochs: durable POST | 13.4 | 15.7 | 16.2 | 24.3 |
| First filter after the two saves: exactly 20 epochs | 31.1 | 21.9 | 119.2 | 124.5 |
| Two revision reads + two saves + filter | 73.6 | 66.9 | 166.0 | 217.5 |
| One cell: durable POST | 6.7 | 7.3 | 7.8 | 8.6 |
| Cell filter: exactly 100 inherited epochs | 41.5 | 39.7 | 129.8 | 156.8 |
| Cell AND epoch filter: exactly 10 epochs | 17.4 | 18.4 | 106.2 | 124.6 |
| Cell save + cell filter | 48.1 | 47.0 | 137.8 | 165.8 |

The total uses paired per-cycle timings and includes both revision reads. POST timing ends only after canonical MySQL save acknowledgment. The separately scheduled recovery mirror is flushed and checked after the operations. These are Flask HTTP client timings on a disposable native MySQL database, not browser interaction or paint timings.

The native run performs no preparatory tag filtering or SQLite tag checkpoint after seeding. Its very first filter request took 38.0 ms at 500 epochs and 984.3 ms at 100k; the first full sequences took 105.9 and 1074.7 ms. “First” means the first HTTP filter after seeding, not a cold MySQL/OS cache. The prior SQLite receipts prepared their tag caches before timing. Five samples do not establish tail-latency guarantees.

## Index, persistence and correctness

The actual 20-epoch filter uses the persistent `by_tag` covering index with `ref` access and an estimate of 20 lookup rows at both scales. Both runs distinguish `QC` from `qc` and NFC `é` from decomposed `é`, and verify AND, OR, NOT, inherited cell membership, direct-only epoch scope, exact author chips and revisions. Cell tagging changes one canonical cell record and creates no child annotation copies; both protocol curation scopes remain unchanged.

The lookup is checkpointed and reopened as a fresh Python adapter in the same server, reusing the persistent SQL table. This is not a MySQL process restart. The reopened exact-20 filter takes 19.7/143.9 ms at 500/100k. Initial setup timing in the raw receipts is empty-database schema/trigger setup before seeding, not a populated-database migration benchmark.

Both final backup receipts are `current`, with no pending/running work or error, and requested/completed sequence 34. The flushed recovery mirror matches all 63 tracked canonical records, including final removals. Both owned native servers stopped successfully.

## Autocomplete diagnostic

Two untimed-workflow diagnostic calls request `q=gate&limit=12`, checking exact counts and profile authors. Each is a single observation; “cold/warm” labels mean first/repeated endpoint calls after the timed workflow, not cold/warm storage.

| Scale | First endpoint ms | Repeated endpoint ms | Aggregate SQL first/repeated ms | Author SQL first/repeated ms |
|---|---:|---:|---:|---:|
| 500 | 25.7 | 28.5 | 6.4 / 7.2 | 2.8 / 2.8 |
| 100,000 | 10202.6 | 9474.2 | 5976.9 / 5332.8 | 4200.6 / 4116.7 |

At 100k, autocomplete scans the project-wide PRIMARY prefix (613,093 estimated rows) and filesorts for `COUNT(DISTINCT target_kind,target_uuid)` grouped by tag. The author subquery also selects PRIMARY project-prefix access instead of `by_tag`; the canonical join uses only project/kind (key length 111). These SQL operations account for essentially the entire 9–10 second endpoint latency. This remains a material responsiveness issue; it is separate from the indexed point-tag query. The raw receipts preserve actual SQL, timings and EXPLAIN output.

## Reproducible evidence

- [500-epoch native receipt](native-tag-sequence-pre-autocompletefix-500.json) and [100,000-epoch native receipt](native-tag-sequence-pre-autocompletefix-100000.json).
- [Prior 500-epoch receipt](tag-sequence-after-500.json) and [prior 100,000-epoch receipt](tag-sequence-after-100000.json).
- [Native harness](benchmark_native_tag_sequence.py) and [machine-readable comparison](native-tag-sequence-pre-autocompletefix-results.json).

The 500-epoch source and harness inventories are unchanged. The 100k harness is unchanged, but `workspace_api.py`, `workspace_paths.py`, `workspace_projects.py`, and `tests/test_workspace_path_api.py` changed during execution. `tests/test_workspace_root_boundaries.py` also changed between scales. The raw receipt deliberately remains `passed: false`; its benchmark results must not be promoted to final unchanged-source evidence. Full before/after SHA-256 inventories and loaded-module paths are preserved.

Native harness SHA-256: `a2b5e70861826936fdb4c9d6a5c76efd7645486ad5ce05e1482e3e6aab694fde`.

These receipts validate this workflow and its stated checks; they do not certify a complete desktop release.
