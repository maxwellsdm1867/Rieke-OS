Source `eb1e73e2ea4af821ddc73b957568f13746dd9b8f` passed the same-day baseline/candidate native and browser performance comparisons. No repeated-action median regression exceeded both 20% and 20 ms; no action was missing. Native correctness assertions passed, native context remained real, legacy oracle count stayed zero, Python source inventory stayed unchanged, and owned MySQL stopped normally. Browser errors were empty and its owned Chrome/preview closed.

The UI now opens branches and pages in roughly 100 ms at 100k synthetic epochs. Backend warm tree pages take 14–16 ms. First API tree root still costs 308 ms; initial component view costs 910 ms. These are reported separately from warm medians.

| Native API action | Baseline median ms | Candidate median ms | Candidate first ms | Speedup |
|---|---:|---:|---:|---:|
| api_contrast_filter_preview | 4195.9 | 2054.0 | 2182.3 | 2.0× |
| api_epoch_details | 64.8 | 63.2 | 64.1 | 1.0× |
| api_epoch_first_60 | 61.3 | 60.9 | 150.3 | 1.0× |
| api_epoch_next_60 | 61.8 | 60.1 | 58.3 | 1.0× |
| api_overview | 569.4 | 560.2 | 1154.0 | 1.0× |
| api_tree_expand_block | 2736.8 | 16.2 | 15.5 | 168.4× |
| api_tree_expand_cell | 2763.1 | 14.2 | 15.1 | 194.3× |
| api_tree_expand_date | 2415.7 | 15.3 | 108.5 | 158.4× |
| api_tree_root | 2022.0 | 14.1 | 307.5 | 143.9× |

| Browser action | Baseline median ms | Candidate median ms | Samples | Speedup |
|---|---:|---:|---:|---:|
| collapse_cell_cached | 61.1 | 59.6 | 5 | 1.0× |
| component_initial_tree_load_production_bundle_cold | 2904.6 | 909.6 | 1 | 3.2× |
| expand_block_first_time | 2565.1 | 100.6 | 5 | 25.5× |
| expand_cell_first_time | 2465.9 | 101.5 | 5 | 24.3× |
| expand_disjoint_block_first_use | 2615.6 | 98.5 | 5 | 26.6× |
| expand_disjoint_cell_first_use | 2549.7 | 100.2 | 5 | 25.4× |
| next_cell_page_60 | 2238.2 | 93.0 | 5 | 24.1× |
| reopen_cell_cached | 65.7 | 66.4 | 5 | 1.0× |
| scroll_loaded_tree | 32.2 | 32.7 | 5 | 1.0× |
| search_selected_epoch_metadata | 32.5 | 32.1 | 5 | 1.0× |
| select_epoch_metadata | 97.2 | 96.2 | 5 | 1.0× |

Native uses ten samples per action; browser uses five except one initial-component observation. Medians include the first sample; raw receipts also keep first, warm median and maximum. Browser actions include real HTTP, JSON decode, React ready state and two animation frames. Native API timings include Flask serialization/JSON decode, excluding browser/network rendering.

The historical `api_contrast_filter_preview` ID is retained, but its scope is specifically the default full-catalog preview used for tree/layout metadata facets. It sends `summary_only:true` without `catalog_summary:false`, so it requests the full scoped catalog. Its median improved 4.196→2.054 s, still above the 500 ms optimization goal. Ordinary MetadataExplorer filter/result preview already explicitly sends `catalog_summary:false` in the baseline code; those requests are not described by the full-catalog timing.

A separate matched baseline/candidate real-native HTTP diagnostic uses one identical full API prewarming sequence followed by ten lightweight (`catalog_summary:false`) requests. It measured 586.3→578.0 ms median, 597.6→579.4 ms first, with identical complete canonical response SHA-256 hashes and 4,893 response bytes. Both native contexts were real, oracle counts zero, and owned databases stopped normally. This path is essentially unchanged and still above the 500 ms target. The earlier candidate-only post-browser diagnostic (582 ms median/1,368 ms first) remains preserved, but is not substituted for the matched pair.

Python-worker rusage high-water RSS was 505.6 MiB; sampled peak was 501.6 MiB. MySQL and Chrome are excluded. Original API baseline lacked RSS, so this is an unpaired footprint observation, not proof of memory improvement. Separate catalog paired-memory evidence is documented in catalog/. Sampling can miss transient peaks or reflect paging/compression.

All browser work and the separate lightweight diagnostic finished before the owned API stopped at its browser-wait deadline. The done-marker was written after that deadline, so `browser_done_signal:false` is preserved. This is the bounded-server stop mechanism, not a browser or correctness failure.

Dense-tag and waveform replay completed sequentially and passed their correctness/action-coverage/regression gates. All 18 native tag checks passed at both 10k and 100k, with unchanged source and normal database shutdown. Candidate uses ten tag samples per action; historical baseline uses five. Both actual H5 fixtures rejected a same-size source mutation, performed exactly one first-use full hash, and performed zero warm full hashes. Trace comparison used the stricter 1 ms absolute margin together with 20% relative margin. Larger-scale index construction remains unqualified. No installed app or production project was migrated.

The matched lightweight diagnostic processes also recorded rusage high-water RSS of 592.0 MiB baseline and 448.0 MiB candidate for their identical action sequence. This is one process pair, including fixture/native setup and all API prewarming; it excludes MySQL/Chrome and is not an estimate of whole installed-app RAM. Separate catalog-memory evidence shows about 9.8 MiB extra allocation (+2.4%) in the isolated full-scope catalog diagnostic.

| 100k dense-tag action | Baseline median ms | Candidate median ms |
|---|---:|---:|
| first10_selected_action_http_total | 52.2 | 25.4 |
| second10_selected_action_http_total | 23.5 | 25.9 |
| filter20 | 131.5 | 122.0 |
| cell_tag_then_cell_filter_http_total | 155.0 | 161.1 |
| tag10_then10_filter20_http_total | 190.6 | 186.5 |

100k first populated annotation migration took 155.8 s (historical 146.3 s), a descriptive single setup observation. It remains a preparation bottleneck and is not ordinary reopen latency. The full 100k tag evaluation took 239.5 s; its workflow peak RSS was 983.2 MiB.

| H5 payload | Historical warm 20k-sample median ms | Candidate median ms | Candidate first integrity+read ms |
|---|---:|---:|---:|
| 32 MiB | 1.85 | 1.75 | 22.44 |
| 256 MiB | 2.33 | 1.78 | 133.81 |

Trace files were freshly written real temporary H5 payloads; OS file caches were warm after construction. These are source-integrity/window-read measurements, with no HTTP/browser or cold NAS claim.
