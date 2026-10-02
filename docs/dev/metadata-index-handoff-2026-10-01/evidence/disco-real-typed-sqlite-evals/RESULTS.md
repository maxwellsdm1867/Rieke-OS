# Previous typed SQLite approach on real metadata

Completed 2026-10-01T11:36:49.982906-07:00. This tests the earlier typed/indexed SQLite pattern against the mounted dataset: **2,781 actual epochs, 140 existing query fields, three sources**. No synthetic expansion or new library was used. The installed app and mounted database were unchanged.

Both bounded-preview implementations return an exact match count, the first 60 chronological rows, continuation cursor and two requested typed field summaries. JSON serialization is included. Eleven observations per case retain the first separately, ten warm samples and the observed maximum. The final v3 results are:

| Equivalent bounded operation | Current SQLite | Typed/indexed SQLite |
|---|---:|---:|
| All 2,781 epochs | 33.15 ms | 5.44 ms |
| Largest protocol, 1,857 epochs | 30.82 ms | 7.95 ms |
| Largest cell, 687 epochs | 18.62 ms | 4.85 ms |
| Largest block, 601 epochs | 18.76 ms | 3.53 ms |
| Numeric equality | 30.38 ms | 17.13 ms |
| Array equality | 35.70 ms | 16.81 ms |
| Compound OR | 31.26 ms | 22.31 ms |
| Empty UUID result | 0.753 ms | 0.076 ms |
| Explicit all 2,781 eligible UUIDs supplied | 28.66 ms | 19.15 ms |

All 20 representative scenarios pass exact membership, chronology, count, row, facet and cursor comparisons against independent production predicate evaluation. Full walks verify all 47 global pages and 11 pages of the 601-epoch block. Arrays, null, missing, numeric equality and observed mixed types are retained. Every original table, compressed detail and shared ancestor object remains exact. There is no observed Boolean-valued fixture; that dataset coverage remains unproven. See [every measured case](evals/v3/REPORT.md).

## What improved

The same earlier pattern is applied to real data: typed core columns, UUID/chronology/parent indexes, SQL counts, bounded rows and facets, and continuation. Generic scalar dictionary indexes cover the full existing native field set while preserving original JSON and native recursive equality. The original detail decoder still resolves shared metadata objects. This evaluates the combined indexed query model; it does not show that datatype annotations alone improve speed.

Construction plus streamed preservation checks took **1.35 seconds**, adding **5.45 MB** (20.79 MB to 26.23 MB). Build peak RSS was 64.6 MiB. Final evaluation ran in 11.63 seconds with 141.1 MiB peak RSS. Actual candidate, harness, decoder and native-code hashes were checked before and after; every output also matches earlier attempts. Original data/generation inputs stayed stable.

## Full catalog remains separate

The original slow catalog computes all field statistics, grouping suggestions and layouts. Adding typed tables does not automatically make that existing code use them. A control ran the unchanged current catalog on an ANALYZE-only copy and a typed-plus-ANALYZE copy:

| Full catalog recomputation | ANALYZE only | Typed + ANALYZE |
|---|---:|---:|
| All real epochs | 642 ms | 734 ms |
| Largest cell | 258 ms | 285 ms |

Five warm samples per case after an excluded warmup. Typed global timings varied substantially, so these measurements do not establish a meaningful slowdown. They establish that neither makes the current full catalog fast. Exact 141-field outputs, suggestions and layouts match. All seven original tables and source files remain unchanged. [Attribution receipt](catalog/extra-report.json).

The earlier shared catalog optimization separately reduces repeated statistics and variation queries from 140 each to one each, preserving complete outputs:

| Full catalog scope | Current algorithm | Earlier optimized algorithm |
|---|---:|---:|
| All real epochs | 685 ms | 519 ms |
| Largest protocol | 474 ms | 324 ms |
| Largest cell | 234 ms | 122 ms |
| Numeric filter | 460 ms | 317 ms |
| Text filter | 329 ms | 217 ms |
| Missing field | 333 ms | 185 ms |

All six complete catalog hashes match. Separate cProfile and SQL tracing identify aggregate SQL work as the remaining cost; broad aggregate scans persist even after batching. Instrumented profiling values are not normal latency samples. Catalog/report.json and the profile receipts retain the evidence.

A 5 ms bounded preview and a 600 ms full catalog perform different work. Typed indexes speed up ordinary filtering. Making all-field summaries optional or lazy is a separate interface/algorithm change. These backend controls do not qualify the full native API preview or UI.

## Regression fixes and retained attempts

V1 exposed an empty-UUID regression: 3.78 ms versus 0.75 ms. Validation decoded every recorded UUID merely to establish string type. V2 uses a representative after construction/open checks prove a completely present string-valued core field; the lookup is now 0.076 ms, with the database unchanged. Block group ordering also follows recorded start time then UUID. Smoke tests and full chronological pagination pass.

An initial harness mistake requested duplicate facets for an empty result. The failure metadata is retained, its partial timings discarded, and all comparisons rerun. V1 code/receipts and V2 results remain saved. V3 adds actual candidate/harness/decoder before-and-after source hashes; all result hashes remain identical across attempts.

## Remaining scope

Passing an explicit eligible-UUID list still costs work: the 2,781-ID case loses much of the improvement. Production selection/generation handling must avoid rebuilding or transporting million-ID scopes on every query. This immutable prototype does not implement live native source exclusions/annotations, refreshed cursor binding, startup/import, waveforms or UI integration. All three registered sources are included explicitly in this backend snapshot.

The target remains one million, but this experiment proves behavior only on **2,781 real epochs**. Representative scaling and production integration remain separate gates. The prior nine everyday-action benchmarks remain retained; these 20 backend cases supplement rather than replace UI, tagging and startup measurements.

## Evidence and reproduction

Final [receipt](evals/v3/receipt.json), [source/output qualification](evals/v3/qualification.json), model/build-receipt.json, model/smoke-v2-receipt.json, catalog/report.json and catalog/extra-report.json are saved. Python helpers, source snapshots, profiles and earlier attempts are included. Actual scientific SQLite copies stay private under /private/tmp/disco-real-typed-sqlite-20261001; database files and credentials are not included here or published to GitHub.
