The previous typed SQLite approach tested on real metadata

All 20 bounded metadata comparisons passed. The same immutable snapshot has 2781 epochs and 140 native fields across 3 source revisions. Both arms returned exactly the same count, first 60 rows, next cursor, and two requested typed facet buckets. Numeric integer/float equivalence, actual arrays, recorded null, missing values, string/null mixed fields, compound expressions, and empty results were checked against production predicates applied independently to original indexed JSON values.

| Case | Epochs | Current median ms | Typed median ms | Speedup |
|---|---:|---:|---:|---:|
| global | 2781 | 32.05 | 5.88 | 5.45x |
| largest_protocol | 1857 | 29.32 | 7.82 | 3.75x |
| largest_cell | 687 | 19.18 | 4.11 | 4.67x |
| largest_block | 601 | 17.74 | 3.67 | 4.83x |
| number_eq | 1820 | 35.50 | 15.97 | 2.22x |
| numeric_order | 1820 | 28.40 | 16.11 | 1.76x |
| string_eq | 1249 | 25.65 | 12.21 | 2.10x |
| text_contains | 1249 | 24.02 | 11.15 | 2.15x |
| array_eq | 1857 | 36.40 | 18.79 | 1.94x |
| array_contains | 1857 | 35.59 | 18.09 | 1.97x |
| null_eq | 849 | 20.34 | 7.85 | 2.59x |
| missing | 924 | 20.17 | 12.44 | 1.62x |
| exists | 1857 | 31.37 | 19.80 | 1.58x |
| recorded_null | 849 | 19.46 | 7.50 | 2.59x |
| compound_all | 1156 | 24.50 | 17.19 | 1.43x |
| compound_any | 1913 | 31.13 | 23.57 | 1.32x |
| compound_not | 868 | 21.04 | 13.50 | 1.56x |
| mixed_types | 690 | 18.38 | 7.38 | 2.49x |
| empty_result | 0 | 0.75 | 3.78 | 0.20x |
| explicit_all_registered_eligible | 2781 | 27.80 | 19.13 | 1.45x |

Measurements include query work and JSON serialization: 11 samples, first reported separately followed by 10 warm samples and maximum. Correctness preparation precedes those samples, so the first sample is not cold application startup.
Next page global: current 32.57 ms, typed 5.32 ms, exact payload SHA-256 a0f6ec7d3d290a46024f4569ead8e7fcc74a7bc6e30bba01b9f248e9baefce94.
Next page largest_block: current 16.92 ms, typed 3.61 ms, exact payload SHA-256 5da50def9cb2e5a154ad2cfd776e02c244be878a81ec1140d95822c02e217c87.

Global chronological order matched across 47 pages; the largest actual block has 601 epochs and matched across 11 pages. Order uses production date,start_time,epoch_uuid. Facets retain original primitive JSON and are merged with production equality_key semantics, first 60 in chronological first appearance. Missing counts, recorded null and truncation flags are exact.

Interpretation: the typed auxiliary indexes make the bounded query payload faster on this real dataset. The separate full-catalog measurement remains necessary: two requested facets do not replace the existing 141-field catalog, statistics and suggestions. Empty UUID results regress from approximately 0.75 ms to 3.78 ms because candidate predicate validation scans the UUID dictionary. Supplying the entire eligible UUID universe via a temporary scope reduces the global benefit (27.80 ms to 19.13 ms). Neither cost affects correctness.

Limitations: metadata-only backend, no full application/UI latency claim, no waveform or annotation operations. All three registered source projections were selected; live MySQL exclusion policy was not queried. No real boolean-valued fixture was observed, so boolean dataset coverage is unproven. Real 2,781-epoch timings do not qualify one million. Warm service row ranking is prepared outside timings for the native baseline, consistent with already loaded production rows.

No protected inputs changed: before/after source manifests, projections, sealed metadata clone, mounted sealed index, and native predicate/index code hashes are in receipt.json. All project accesses were reads; clone leases and outputs are isolated under /private/tmp.

Run elapsed 11.742 seconds; peak RSS 135,872,512 bytes; cap 180 seconds / 513 MiB. Runtime: Python 3.11.13, SQLite 3.50.4.

Reproduce after constructing model/real-typed.sqlite:

/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python -B /private/tmp/disco-real-typed-sqlite-20261001/evals/compare_preview.py --run
