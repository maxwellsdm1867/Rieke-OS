# Preserved evidence inventory

Copied from existing conversation artifacts on 2026-10-01. Reports, scripts, source snapshots and raw text receipts are preserved byte-for-byte. No experiment was rerun. The archive excludes scientific databases, binary profiles, images and generated/large assets; INVENTORY.json enumerates every copied and excluded file and the original source root.

| Bundle | Primary report | Copied files | Text bytes |
|---|---|---:|---:|
| disco-everyday-benchmark | [Report](disco-everyday-benchmark/REPORT.md) | 32 | 540,154 |
| disco-performance-evals | [Report](disco-performance-evals/evals/CANDIDATE-RESULTS.md) | 69 | 1,405,065 |
| disco-duckdb-million-evals | [Report](disco-duckdb-million-evals/evals/RESULTS.md) | 75 | 1,998,461 |
| disco-real-data-evals | [Report](disco-real-data-evals/engines/REPORT.md) | 18 | 481,941 |
| disco-real-typed-sqlite-evals | [Report](disco-real-typed-sqlite-evals/RESULTS.md) | 40 | 1,037,271 |
| disco-real-million-evals | [Report](disco-real-million-evals/RESULTS.md) | 58 | 359,986 |
| disco-metadata-priorities | [Report](disco-metadata-priorities/PROPOSAL.md) | 6 | 186,705 |
| disco-priority-benchmark-evals | [Report](disco-priority-benchmark-evals/RESULTS.md) | 38 | 332,675 |

The original SHA256.json files remain unchanged and may refer to excluded binary assets. ARCHIVE-SHA256.json validates this repository text archive; INVENTORY.json maps its files to the originals. Paths inside historical scripts/reports are retained as evidence and may still depend on temporary databases or installed local runtimes.

The earlier metadata-priorities proposal and its draft field policy are historical. The subsequent priority experiment rejects narrowing the hot field index as a speed optimization. The current [requirements](../../../design/metadata-query-requirements.md) and [handoff](../README.md) govern the next integration.
