The previous typed SQLite approach tested on real metadata, final v2

All 20 paired bounded comparisons passed. Every v1/v2 scenario membership, count/page/facet payload and next-page hash is identical. Global47-page and actual601-epoch block11-page walks remain identical. Original native data/code inputs stayed unchanged.

| Case | Epochs | Current median ms | Typed median ms | Speedup | Typed v1 ms |
|---|---:|---:|---:|---:|---:|
| global | 2781 | 33.89 | 5.88 | 5.77x | 5.88 |
| largest_protocol | 1857 | 30.05 | 7.61 | 3.95x | 7.82 |
| largest_cell | 687 | 17.55 | 3.65 | 4.81x | 4.11 |
| largest_block | 601 | 20.41 | 3.76 | 5.42x | 3.67 |
| number_eq | 1820 | 28.78 | 18.47 | 1.56x | 15.97 |
| numeric_order | 1820 | 30.18 | 16.70 | 1.81x | 16.11 |
| string_eq | 1249 | 24.03 | 11.82 | 2.03x | 12.21 |
| text_contains | 1249 | 24.38 | 11.89 | 2.05x | 11.15 |
| array_eq | 1857 | 35.98 | 17.76 | 2.03x | 18.79 |
| array_contains | 1857 | 36.87 | 17.56 | 2.10x | 18.09 |
| null_eq | 849 | 20.69 | 7.53 | 2.75x | 7.85 |
| missing | 924 | 20.80 | 12.50 | 1.66x | 12.44 |
| exists | 1857 | 35.06 | 19.23 | 1.82x | 19.80 |
| recorded_null | 849 | 20.91 | 7.63 | 2.74x | 7.50 |
| compound_all | 1156 | 23.94 | 17.52 | 1.37x | 17.19 |
| compound_any | 1913 | 30.92 | 22.49 | 1.37x | 23.57 |
| compound_not | 868 | 21.31 | 13.44 | 1.59x | 13.50 |
| mixed_types | 690 | 17.86 | 6.96 | 2.57x | 7.38 |
| empty_result | 0 | 0.75 | 0.08 | 9.83x | 3.78 |
| explicit_all_registered_eligible | 2781 | 27.06 | 19.19 | 1.41x | 19.13 |

The original v1 empty-UUID regression came from candidate validation decoding every UUID dictionary value. V2 uses a string representative after construction proved each direct field is completely present and string-valued, matching native UUID fast-path semantics. Original acquisition JSON and metadata tables are unchanged.

Both backends produce the same exact count, 60 chronological metadata rows, cursor, and two requested typed facets. Timing includes JSON serialization. Each case has 11 samples: first reported separately, then 10 warm samples and maximum. Correctness checks precede timing; the first sample is not a cold application startup.
Next-page global: current 32.95 ms, typed 5.70 ms.
Next-page largest_block: current 18.68 ms, typed 4.80 ms.

Tested actual numeric values, integer/float equality (construction smoke), arrays, missing fields, recorded nulls, mixed string/null fields, text, conjunction/disjunction/negation, empty results and explicit full registered eligible-ID scope. Facets preserve JSON types, numeric semantic equality, first60 chronological appearance, missing counts and truncation. No real boolean fixture was observed, so boolean dataset coverage is unproven.

These metadata-only backend timings do not measure the full application/UI, annotations, waveform I/O or live MySQL source exclusion policy. All three registered source projections are included. The current full141-field catalog/statistics/suggestions is measured separately and is not equivalent to two requested facets. Real2781-epoch timings do not establish performance at one million. Native baseline global row ranking is preloaded outside timing, consistent with warm service state.

Elapsed 11.836 seconds, peak RSS 129,794,048 bytes, cap 120 seconds /513MiB. Python 3.11.13, SQLite 3.50.4.

The initial pre-v1 partial attempt stopped on a duplicate facet name chosen by the harness. The harness was corrected, all timings rerun, and that failed attempt is recorded in attempts/initial-failure.json; its partial timings are not used. V1 full receipt/report/code remain under attempts/v1.

Reproduce:

/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python -B /private/tmp/disco-real-typed-sqlite-20261001/evals/compare_preview.py --run --out /private/tmp/disco-real-typed-sqlite-20261001/evals/v2
