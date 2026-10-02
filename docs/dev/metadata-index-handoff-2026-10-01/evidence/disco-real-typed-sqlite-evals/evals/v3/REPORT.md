Final v3 qualification of prior typed SQLite approach on actual metadata

All20 same-output comparisons passed; v1/v2/v3 membership, count, row/facet/cursor payload and next-page hashes are identical. Global47-page walk and actual601-epoch block11-page walk remain exact. Final candidate, executing evaluation harness, native decoder/index/predicate code were actually hashed before and after V3 and remained stable; all protected original data inputs stayed unchanged.

| Case | Epochs | Current warm median ms | Typed warm median ms | Speedup |
|---|---:|---:|---:|---:|
| global | 2781 | 33.15 | 5.44 | 6.10x |
| largest_protocol | 1857 | 30.82 | 7.95 | 3.87x |
| largest_cell | 687 | 18.62 | 4.85 | 3.84x |
| largest_block | 601 | 18.76 | 3.53 | 5.31x |
| number_eq | 1820 | 30.38 | 17.13 | 1.77x |
| numeric_order | 1820 | 30.53 | 16.39 | 1.86x |
| string_eq | 1249 | 24.13 | 11.14 | 2.17x |
| text_contains | 1249 | 24.34 | 11.56 | 2.10x |
| array_eq | 1857 | 35.70 | 16.81 | 2.12x |
| array_contains | 1857 | 37.17 | 16.60 | 2.24x |
| null_eq | 849 | 20.94 | 8.20 | 2.55x |
| missing | 924 | 19.34 | 12.46 | 1.55x |
| exists | 1857 | 30.22 | 19.06 | 1.59x |
| recorded_null | 849 | 20.24 | 7.53 | 2.69x |
| compound_all | 1156 | 23.47 | 16.86 | 1.39x |
| compound_any | 1913 | 31.26 | 22.31 | 1.40x |
| compound_not | 868 | 21.66 | 13.38 | 1.62x |
| mixed_types | 690 | 18.26 | 6.94 | 2.63x |
| empty_result | 0 | 0.75 | 0.08 | 9.93x |
| explicit_all_registered_eligible | 2781 | 28.66 | 19.15 | 1.50x |

Both backends return exact count, 60 chronological metadata rows, cursor and two requested typed facets; times include JSON serialization. Eleven samples per case, first separately and ten warm samples plus maximum. Correctness preparation precedes samples, so none represents cold application startup.
Next page global: 32.81 ms current, 5.28 ms typed.
Next page largest_block: 18.33 ms current, 3.70 ms typed.

The initial candidate empty-UUID validation regression is fixed: validation uses a representative only when construction/open proof establishes a completely present string-valued direct field. Original JSON/dictionary, arrays, nulls and seven acquisition/ancestor tables are retained. Real integer/float equality, arrays, missing values, present null, text, mixed string/null, compound expressions and empty results were checked. No real boolean fixture was observed; that dataset coverage remains unproven.

This is a metadata-only backend test, not full app/UI latency, annotation access, waveform I/O or observed live MySQL source exclusion policy. All three registered sources are included. Native warm-service row ranking is preloaded outside timing. Two requested facets are not equivalent to the existing full141-field statistics/suggestions catalog, measured separately. Real2781 epochs do not establish million-epoch performance.

Elapsed 11.629 seconds; peak RSS 147,947,520 bytes;120-second/513MiB cap. Runtime Python3.11.13, SQLite3.50.4.

V1 receipt/report/harness/candidate source hashes are preserved in attempts/v1; V2 remains in evals/v2. Initial duplicate-facet harness failure is preserved in attempts/initial-failure.json; partial timings from it are not used. V3 qualification.json records actual final source hashes and historical output comparisons.

Reproduce:

/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python -B /private/tmp/disco-real-typed-sqlite-20261001/evals/compare_preview.py --run --out /private/tmp/disco-real-typed-sqlite-20261001/evals/v3
