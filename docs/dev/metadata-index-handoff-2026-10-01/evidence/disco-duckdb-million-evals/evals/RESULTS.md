# One million epochs: complete scorecard and engine experiments

All nine original actions are retained in [SCORECARD.md](SCORECARD.md), with their photograph values, frozen 100k baseline, optimized 100k candidate and measured one-million prototype results. Eight actions now have target-scale measurements within their stated scope. **The original full API filter preview and whole production application at one million remain unqualified.** The installed app and user checkout were not changed.

Seven unchanged React component actions passed five repetitions in each engine, disjoint unopened branches, independent fixture oracles and exact rendered identity/order checks. All 36 complete page request/response pairs match across engines. Browser medians stay within the documented comparison margin of the optimized 100k component results. These component measurements use a new experimental HTTP readmodel, so this is a prototype continuity check, not a full production app regression certification.

Native tagging ten epochs including revision preflight measured **21.34 ms** over one million metadata rows. Actual production annotation routes, MySQL authority, generation, recovery and revision behavior passed 211 checks. The annotation seed is sparse (1,000 annotated epochs); metadata point lookup uses the experimental SQLite adapter. There is one authoritative native writer, not a separate DuckDB annotation write experiment. See [tagging results](tagging/RESULTS.md).

## Configured engine comparison

One streamed synthetic CSV, the same fixed typed schema, SQL semantics and ten serialized-response samples per operation were used. Exact canonical JSON hashes match for every operation. SQLite gets ordinary lookup/chronology/parent/contrast B-trees; DuckDB gets a UUID ART index, two threads and a 512 MB engine memory setting. This compares sensible configured plans, not identical physical indexes.

| Backend operation at 1m | Typed SQLite | Typed DuckDB | SQLite after covering indexes |
|---|---:|---:|---:|
| First 60 epochs | 0.651 ms | 44.760 ms | 0.669 ms |
| Next 60 epochs | 0.661 ms | 55.347 ms | 0.660 ms |
| First 60 cells | 15.501 ms | 28.482 ms | 15.160 ms |
| Next 60 cells | 16.188 ms | 28.319 ms | 15.219 ms |
| Cell children | 0.185 ms | 2.521 ms | 0.175 ms |
| Block epochs | 0.317 ms | 2.540 ms | 0.294 ms |
| Epoch details | 0.038 ms | 0.412 ms | 0.033 ms |
| Bounded filter preview: count, page, two facets | 545.341 ms | 40.839 ms | 96.587 ms |
| Filtered seed facet, first 60 distinct values | 375.877 ms | 12.273 ms | 0.163 ms |
| Supplied 20-ID metadata join, excludes native membership lookup | 0.336 ms | 42.786 ms | 0.333 ms |

These timings include query execution and JSON serialization, excluding HTTP/browser/native annotation work. First and warm samples and maxima remain in raw receipts. The bounded preview is an additional operation, not the original full-preview row.

Typed metadata build/index/checkpoint took **18.82 s SQLite / 5.24 s DuckDB**; persisted files were **945.3 MB / 150.5 MB**. Peak worker RSS was **195.4 MiB / 655.6 MiB**, excluding the running app, MySQL and Chrome. Shared CSV generation took 93.48 s with about 20.3 MiB peak worker RSS and is excluded from either engine build time. Neither is raw H5 import or complete app startup.

## Adjustment after finding the bottleneck

The original contrast index required many table lookups and a temporary grouping B-tree for seed/currentMean facets. On a separate SQLite copy, covering indexes on `(contrast_present, contrast_kind, contrast, facet_present, facet_kind, facet)` removed those lookups. Recorded EXPLAIN QUERY PLAN output confirms the change. This made the filtered seed facet able to stop after enough ordered groups and brought bounded preview down to 96.6 ms.

Index creation plus ANALYZE took **6.62 s** and added **69.2 MB**. All ten original query output hashes still match; source database SHA-256 before/after matches. Three-sample unfiltered and 100-epoch cell-scope controls also retain exact output and show no material regression. This adjustment has backend-only measurements; the original nine-action browser scorecard uses the original paired databases. The fixed-schema facet-specific indexes are a measured candidate, not a universal arbitrary-metadata indexing policy.

## The expensive full catalog remains separate

At 100k, the unchanged production full catalog algorithm over the same EAV metadata and 20k contrast matches measured warm median **1.387 s SQLite / 0.319 s DuckDB**. Complete 16-field output hashes match. At one million, a SQL-derived DuckDB EAV projection with 200k matches measured **3.455 s** warm median and peaked at **1,476 MiB sampled RSS**. Independent membership, field statistics and numeric-type oracles pass, but there is no same-scale SQLite catalog hash control. The current Python catalog materialization remains costly even with DuckDB. See [catalog controls](readmodel/EAV-RESULTS.md).

These are catalog-stage measurements, excluding complete Flask preview validation, native revisions/curation and frozen membership handling. They do not fill the ninth original action with a different operation. Production million-epoch startup also retains eager metadata/baseline paths. [QUALIFICATION.json](QUALIFICATION.json) explicitly leaves both release gates false.

## Decision and remaining work

Keep indexed SQLite as the leading interactive readmodel candidate. DuckDB is promising for bulk ingestion and broader analytic aggregation; it is not a blanket replacement for small indexed requests or the native annotation writer. The experiment implements streaming input, bounded SQL pages/counts, SQL-backed lazy mappings, facet queries and the same shared HTML frontend. It evaluates one coherent query/storage strategy and an index adjustment, rather than integrating every proposed technique at once.

Production work remains: generic metadata representation, real acquisition/H5 import and integrity, immutable generation publication/cursor binding, replacing all eager maps and startup scans, production tag-filter integration, and full API filter preview at one million. See [experiment contract](EXPERIMENT.md). No merge, package, release or install was performed; issue #5 remains excluded.

## Reproduction and retained failures

Raw engine/build/adjustment receipts and logs are under [measurements/](measurements/); browser and native annotation artifacts are under their respective directories. `evaluate.py`, `adjust_sqlite.py`, readmodel/evaluate_catalog.py and each harness README preserve commands and operation definitions. The isolated DuckDB 1.5.6 wheel is installed under /private/tmp/disco-duckdb-deps-20261001; the existing Python/node/MySQL runtimes were read only. Full data files remain owned temporary artifacts and are reproducible from generate_csv.

The first SQLite query receipt precedes Boolean DTO normalization; its build phases remain valid, but final query comparisons use sqlite-normalized/receipt.json. Canonical JSON tests catch bool/int mismatches that ordinary Python equality misses. The fixed typed schema preserves this corpus, not arbitrary JSON primitive values/types.

The first browser bridge run failed on an incomplete catalog field definition and is retained; the corrected unchanged frontend replay passed. The first covering-index supervisor launch failed under sandbox process-enumeration permissions; it is retained separately, the guard now preflights and fails closed, and the authorized monitored rerun passed. All final owned Chrome/HTTP/MySQL and catalog/index workers exited normally.

## Final validation

Eleven small harness tests passed: five paired readmodel/catalog tests, one browser bridge contract test, three annotation point-map tests and two resource-supervisor failure tests. `verify_results.py` rechecks all nine rows, one-million sample coverage, engine/adjustment hashes, complete browser pages, catalog controls and source-database immutability. It requires the unresolved original full-preview/production gates to remain visibly false. `git diff --check` passed. These experiment tests supplement the retained prior production candidate validation; production code is unchanged in this branch.
