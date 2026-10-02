# Metadata experiment, current source

Source: `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`. Synthetic 100,000 epochs, 10 sources, one protocol, one date, 1,000 cells, 5,000 blocks, and four scalar parameters. Real current WorkspaceService and sealed SQLite index. Actual Flask API routes and JSON decode use empty-curation transactional SQL doubles. These select a legacy protocol-state oracle fallback; they do not represent the optimized native MySQL provider. This probe omits MySQL/network latency, dense annotations, H5/waveforms and full app navigation.

Method: first measured invocation and five subsequent samples. First API invocations follow service warmup, so there is no cold OS page-cache claim. Guards: sampled RSS 1,700 MiB, available memory 600 MiB, free disk 4 GiB, index build 240 seconds, worker 600 seconds.

| Action | First (ms) | Warm median (ms) | Warm max (ms) | JSON bytes |
|---|---:|---:|---:|---:|
| service_epoch_first_60 | 87.99 | 11.60 | 12.04 | 44832 |
| service_epoch_next_60 | 11.67 | 11.52 | 11.68 | 44883 |
| service_exact_epoch_predicate | 56.89 | 56.79 | 58.02 | 128 |
| service_contrast_preview_summary | 3743.39 | 3723.63 | 3755.42 | 2630709 |
| service_epoch_details | 0.86 | 0.10 | 0.11 | 1257 |
| service_overview | 826.47 | 825.05 | 840.79 | 264766 |
| api_epoch_first_60 | 920.29 | 926.44 | 981.23 | 52745 |
| api_epoch_next_60 | 930.19 | 919.15 | 927.24 | 52796 |
| api_tree_root | 1935.90 | 1935.68 | 1988.43 | 831 |
| api_tree_expand_date | 2289.77 | 2307.06 | 2343.27 | 23949 |
| api_tree_expand_cell | 2525.37 | 2730.39 | 3151.64 | 3904 |
| api_tree_expand_block | 2812.29 | 2668.99 | 3187.98 | 7984 |
| api_exact_epoch_search_preview | 566.26 | 584.89 | 807.30 | 9854 |
| api_contrast_filter_preview | 4032.72 | 3921.20 | 3991.84 | 10694 |
| api_epoch_details | 0.56 | 0.44 | 0.48 | 1381 |
| api_overview | 3200.83 | 3681.15 | 9277.70 | 295012 |

All count, detail ID and page oracles passed. Empty curation, dataset and event tables remained unchanged. Index cold build: 25.713 s; persistent reopen: 0.696 s; synthetic model generation: 7.437 s; index: 185,298,944 bytes. Initial sandbox loopback bind failure and benchmark API response-oracle correction are preserved in initial-build-receipt.json and prior-attempt.json. The resumed receipt identifies cached index reuse.

## Indexed SQL diagnostic control

Control only, not an application optimization. Same fixture count and protocol insertion order; bounded 60 rows.
- control_sql_epoch_first_60: warm median 0.267 ms, maximum 0.284 ms. Exact count and order oracles passed.
- control_sql_contrast_count_first_60: warm median 1.563 ms, maximum 1.672 ms. Exact count and order oracles passed.

API 60-page cProfile: instrumented 2.81 s, read_selected/_oracle/legacy_state 2.78 s; curation read 1.31 s, scope 1.14 s. These are instrumented profile times, not latency measurements. Contrast preview: instrumented 4.40 s, catalog 3.74 s, 54 SQLite execute calls 1.96 s, suggestions 0.71 s.

## Higher scales

500,000: synthetic generation completed in 38.715 s. Index build stopped at 241.983 s under the declared 240-second cap. There is no sealed index and no API action measurement. Sampled RSS peak: 1,630.58 MiB; minimum available memory: 2,466.75 MiB. RSS sampling every two seconds does not measure compressed heap. An experiment cap does not establish an intrinsic 500k limit. 1,000,000: synthetic model generation completed in 76.835 s. Index build stopped at 240.264 s under the same cap. Sampled RSS peak: 1,201.22 MiB; rusage maximum RSS: 1,212.88 MiB; minimum available memory: 2,444.75 MiB. No sealed index or everyday action timings exist for this scale. Neither stopped build establishes intrinsic capacity or query latency. Both owned workers exited with code 75 under their declared guard. No source modifications, user catalog operations or installer builds were performed.
