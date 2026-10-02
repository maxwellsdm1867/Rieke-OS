# Exact full-catalog DuckDB controls

These results measure the complete current production **catalog algorithm**,
including all sixteen synthetic metadata fields and layout suggestions, plus
canonical JSON serialization. They do not measure the entire Flask filter
preview, native curation/revisions, frozen selection payload or browser paint.
All timing workers ran serially, separately from browser and native tagging
workers. Ten samples were collected per measured arm.

| Scope | Engine | First invocation | Warm median | Observed maximum |
|---|---|---:|---:|---:|
| 100k epochs; 20k contrast matches | Current SQLite EAV | 2,118 ms | 1,387 ms | 2,118 ms |
| Same 100k metadata, EAV representation and algorithm | DuckDB EAV | 336 ms | 319 ms | 347 ms |
| 1m epochs; 200k contrast matches | SQL-derived DuckDB EAV | 3,826 ms | 3,455 ms | 3,826 ms |

At 100k, the **complete output hashes match**, including catalog field
statistics, grouping roles and suggestions:
`5403306490374815a47f309e927396b2612b1732dd1ac392b399eb53df83d1c2`.
The same metadata and EAV schema are used; this isolates the configured engine
more directly than comparison to the separate typed bounded-preview prototype.

At 1m, no same-scale SQLite EAV control exists. The receipt explicitly records
that exact-control result as null. Independent arithmetic verifies the complete
ordered contrast membership, all sixteen expected distinct/missing/null/total
counts, and the exact numeric JSON kinds. Small-scale imported and SQL-derived
controls also match the actual SQLite algorithm exactly.

The 100k bulk EAV copy took 3.47 seconds and occupied 73.7 MB. This is import
from an **already built sealed index**, not complete metadata index building.
The million-epoch EAV derivation took 6.17 seconds and occupied 406.3 MB,
including sixteen million field relations. This is an **additional SQL
projection from already built typed DuckDB metadata**, not raw import or total
application startup.

Both process guards passed and workers exited normally. Peak sampled worker
RSS was 443 MiB at 100k and **1,476 MiB at 1m**, near the 1.5 GiB experiment
limit. The 512 MB DuckDB setting bounds its managed database memory, not all
Python objects or whole-process RSS. Broad Python catalog materialization
remains an architectural and memory concern at the target scale.

First invocation means first measured invocation in these workers; it is not
an OS-cold disk test. The metadata corpus is synthetic, has one protocol and
four fixed scalar parameters, and preserves the prior benchmark's date fixture.
These controls qualify catalog behavior only, not the whole production app.

Raw receipts and corresponding ten-sample arrays:

- `/private/tmp/disco-duckdb-million-runs-20261001/catalog-100k/receipt.json`
- `/private/tmp/disco-duckdb-million-runs-20261001/catalog-100k/guard.json`
- `/private/tmp/disco-duckdb-million-runs-20261001/catalog-million/receipt.json`
- `/private/tmp/disco-duckdb-million-runs-20261001/catalog-million/guard.json`

Catalog output JSON files are saved beside each receipt. Methods and replay
interfaces are in `README.md` and `evaluate_catalog.py`.
