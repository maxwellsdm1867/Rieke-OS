# Complete everyday action scorecard

The photograph contains nine actions. All nine remain mandatory. Historical rounded values and exact frozen same-day replay are retained. New million-epoch browser results use the **unchanged shared production frontend with an experimental typed SQL readmodel HTTP bridge**. This is a measured prototype, not current installed-app qualification.

| Action | Historical 100k | Frozen baseline 100k | Optimized candidate 100k | Typed SQLite 1m | Typed DuckDB 1m |
|---|---:|---:|---:|---:|---:|
| Select epoch and display metadata | 96.0 ms | 97.2 ms | 96.2 ms | 93.7 ms | 92.5 ms |
| Search selected metadata | 32.0 ms | 32.5 ms | 32.1 ms | 32.7 ms | 32.4 ms |
| Reopen cached cell | 65.0 ms | 65.7 ms | 66.4 ms | 66.2 ms | 65.4 ms |
| Scroll loaded rows | 33.0 ms | 32.2 ms | 32.7 ms | 31.4 ms | 32.3 ms |
| Expand unloaded cell | 2.480 s | 2.466 s | 101.5 ms | 100.3 ms | 100.1 ms |
| Expand unloaded block | 2.400 s | 2.565 s | 100.6 ms | 99.1 ms | 98.9 ms |
| Load next 60 cells | 2.140 s | 2.238 s | 93.0 ms | 92.7 ms | 109.0 ms |
| Tag ten epochs¹ | 52.0 ms | 52.2 ms | 25.4 ms | 21.3 ms² | Shared native writer² |
| Preview metadata filter¹ | 3.900 s | 4.196 s | 2.054 s | **Unqualified** | **Unqualified** |

¹ Tagging is native API revision preflight plus ten-epoch save, excluding browser rendering. Full filter preview includes the original catalog behavior; a bounded preview or catalog-only query cannot replace this benchmark. Original full API preview at one million remains unqualified.

² One million rows, native MySQL production annotation routes, experimental SQLite point-lookup adapter, sparse 1,000-epoch seed; ten samples, 211 checks. The authoritative writer is shared with DuckDB, so a second DuckDB write timing was not invented. This is not a direct density-controlled regression comparison with the dense 100k baseline. [Tagging details and limits](tagging/RESULTS.md).

All seven browser actions passed five repetitions per engine. Each run also passed five unopened disjoint cell/block pairs, 36 independent backend fixture oracle checks and exact rendered leaf UUID/order checks. The complete 36 page-request/response pairs also have exactly equal canonical SHA-256 hashes between engines. No HTTP or React errors. Both runs used fresh owned Chrome and fresh bridge processes; all owned servers and browsers stopped normally. Storage caches were not purged.

## First use and disjoint controls

| Additional control | Typed SQLite 1m | Typed DuckDB 1m |
|---|---:|---:|
| First component view (one observation) | 543.8 ms | 248.2 ms |
| Previously unopened cells (five) | 100.3 ms | 101.8 ms |
| Previously unopened blocks (five) | 99.0 ms | 95.9 ms |

First component view includes bundle navigation and initial tree request. It is not full App startup. First/warm samples and maxima for every action are saved in the raw receipts. These action timings include HTTP, response parsing, React commit, two animation frames and the same oracle assertions in both bridges; they exclude waveforms, packaging and physical screen display.

## Regression interpretation

DuckDB next-cell paging was 16.3 ms slower than SQLite in this run; all seven actions remained within the frozen comparison margin (both >20% and >20 ms are required to flag a slowdown). Five observations are too few to make reliable tail-percentile claims. The UI results do not show a material DuckDB advantage for ordinary warmed interactions; its first component view was lower in a single observation. Backend aggregates need their separate engine results.

Do not interpret the historical100k→typed1m comparison as an engine-only improvement: it changes dataset size and service architecture. The paired typed1m SQLite versus DuckDB comparison holds fixture/query semantics/frontend constant.

## Preserved failed attempt

The first SQLite bridge config omitted required catalog field `id`, so MetadataPanel crashed during epoch selection. That failed receipt/log is preserved under [browser/attempts/sqlite-missing-catalog-id](browser/attempts/sqlite-missing-catalog-id/browser.json). The owned config was corrected; no production frontend changes were made. Both final measurements restarted fresh bridge processes after correction. The failed partial timings do not enter this scorecard.

## Receipts and replay

- [Frozen100k metrics and source-receipt hashes](browser/frozen-scorecard.json)
- [Complete machine-readable scorecard](browser/scorecard.json)
- [SQLite million browser receipt](browser/sqlite/browser.json)
- [DuckDB million browser receipt](browser/duckdb/browser.json)
- [Receipt hashes](browser/receipt-manifest.json)
- [Scope, replay commands and measurement contract](browser/README.md)

The older production million-epoch metadata index build stopped at its experiment cap. This new typed model avoids retaining all metadata rows in Python and qualifies the stated component/prototype actions only. Full production app behavior at one million remains a separate integration task.
