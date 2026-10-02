# One-million-epoch native tagging evaluation

Passed: **True**. 211 checks; ten samples per action; 9.99 seconds total.

One million real rows in the shared typed SQLite metadata fixture, 10,000 cells. Annotation writes use production native MySQL 8.4.2, unchanged `SharedAnnotations`, and the actual registered annotation routes. The focused Flask harness uses the production native authority, lookup preparation, recovery mirror and scheduler. It excludes whole-app startup, protocol `/epochs`, browser rendering and network. Metadata lookups are the isolated SQL-backed adapter.

Initial annotation density is **0.1%**: 1,000 epochs × three authors × five tags (3,000 records and 15,000 memberships). Selected existing targets have the same three-author/five-tag shape as earlier dense cases. Global sparse density and the narrower route harness mean these numbers must not be presented as a direct improvement over dense 100k app measurements.

| Action | First ms | Median ms | Maximum ms |
|---|---:|---:|---:|
| Read revisions for ten existing targets | 4.83 | 4.15 | 4.83 |
| Tag ten existing targets, write only | 41.83 | 17.03 | 41.83 |
| Tag ten existing targets including revision preflight | 46.66 | 21.34 | 46.66 |
| Tag another ten including revision preflight | 23.04 | 21.81 | 24.90 |
| Autocomplete tag prefix | 22.68 | 22.71 | 36.12 |
| Tag one cell (one canonical record) | 6.76 | 6.72 | 10.33 |
| Remove tag from twenty epochs | 34.57 | 29.51 | 63.82 |
| Remove cell tag | 5.95 | 5.95 | 9.36 |
| Read ten initially unannotated targets | 2.34 | 1.71 | 2.34 |
| Tag ten initially unannotated targets¹ | 10.05 | 13.58 | 15.92 |
| Remove those ten tags | 13.54 | 13.65 | 15.23 |
| Production hierarchy filter on selected 100-child cell scope | 38.15 | 21.16 | 55.75 |

¹Only the first sample inserts new canonical annotation records: **10.05 ms**. Removing a tag leaves an empty record with its revision, so later samples update existing empty records. First preflight is **2.34 ms**, and median preflight **1.71 ms**. Do not call the ten-sample median a repeated fresh-insert benchmark.

The tag predicate evaluator above runs unchanged production logic over a preselected 100-row cell scope, not the full million-row universe. It confirms inherited cell tags intersect direct epoch tags into exactly ten children.

## Experimental native membership joined to SQL metadata

The native MySQL lookup supplies authoritative target membership. Each arm joins those targets into the immutable million-row metadata projection; the native generation is checked before and after. These are backend read-model timings, not the existing full-universe production protocol filter endpoint.

| Action | SQLite median ms | DuckDB median ms | SQLite maximum ms | DuckDB maximum ms |
|---|---:|---:|---:|---:|
| Twenty direct tagged epochs | 21.44 | 23.11 | 33.21 | 53.46 |
| One inherited cell, 100 children | 21.34 | 24.23 | 31.45 | 240.78 |

Both arms pass exact ordered membership parity. DuckDB showed no latency advantage for these small tag-filter joins; its inherited-cell observed maximum was **240.78 ms**. Ten sequential samples do not characterize stable tail latency. Annotation writes stay in MySQL in both arms.

## Correctness, resources and remaining limits

- Every addition/removal is checked against canonical SQL tag presence and exact author revisions; committed native generation counters advance.
- Cell tagging changes one canonical record and leaves child epoch records unchanged.
- Case (`QC`/`qc`) and composed/decomposed Unicode (`é`/`é`) remain distinct exact identities.
- A stale revision rejects the entire multi-target transaction without changing canonical content or native generation.
- Unregistered targets are rejected without changing generation.
- Final recovery mirror content exactly matches canonical annotation content; scheduler flush finishes current.
- Native lookup ready, native generation authority available; **zero SQLite tag-membership fallback calls**.
- Source Python inventory unchanged; owned MySQL stopped normally; no setup/run failure occurred.
- Worker peak RSS **163.02 MiB**, excluding MySQL. Point cache retained **120** epochs. No million-row Python mapping was constructed.
- Owned MySQL boot 3.493 s; sparse seed 0.105 s; lookup prep 0.485 s; final recovery flush 0.035 s.
- Dense one-million annotation migration, whole-app startup, full-universe production tag filtering and concurrent browser editing remain unqualified by this experiment.
- Full `create_app` startup invokes supporting-voltage baseline preparation; its present repeated epoch scans per cell remain a separate million-scale startup concern. It was not overridden here.

## Exact artifacts and replay

Raw receipt: [receipt.json](receipt.json). Raw log: [benchmark.log](benchmark.log). Harness: [benchmark.py](benchmark.py). Methods: [README.md](README.md). Three focused adapter tests passed.

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/disco-duckdb-deps-20261001 \
  /PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python -B \
  docs/dev/duckdb-million-evals-2026-10-01/tagging/benchmark.py \
  --source-root /private/tmp/disco-duckdb-million-20261001 \
  --sqlite /private/tmp/disco-duckdb-million-runs-20261001/sqlite-million/metadata.sqlite \
  --duckdb /private/tmp/disco-duckdb-million-runs-20261001/duckdb-million/metadata.duckdb \
  --mysql-runtime-root /PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/mysql \
  --output-dir /private/tmp/disco-duckdb-million-runs-20261001/tagging-million-replay \
  --samples 10 --cap-seconds 300
```

Source commit: `1017530311709477492a551c844f1b2a200e242c`. DuckDB 1.5.6; threads=2, memory limit=512MB. Metadata read-only.

Receipt SHA256: `de27d794f7fc054ee52257d3b2e574c1866fde5abaabf2bc849d0faefe0a79f2`.
Harness SHA256: `19f928568cbed3ab7f9222c5b389cfb8263ad05ddbb9be7d355649bbde3a0249`.
