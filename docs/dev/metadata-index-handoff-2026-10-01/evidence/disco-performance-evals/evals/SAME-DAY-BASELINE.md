Same-day baseline was measured sequentially against immutable source `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13` with the same 100k sealed fixture. Native uses ten samples per action; browser uses five repetitions.

| Native action | First ms | Median ms | Warm median ms | Observed max ms |
|---|---:|---:|---:|---:|
| api_epoch_first_60 | 159.0 | 61.3 | 61.3 | 159.0 |
| api_epoch_next_60 | 60.5 | 61.8 | 61.9 | 67.7 |
| api_tree_root | 2645.0 | 2022.0 | 2015.6 | 2645.0 |
| api_tree_expand_date | 2520.8 | 2415.7 | 2414.1 | 2693.0 |
| api_tree_expand_cell | 2698.9 | 2763.1 | 2765.8 | 2850.0 |
| api_tree_expand_block | 2875.6 | 2736.8 | 2732.2 | 2875.6 |
| api_epoch_details | 75.5 | 64.8 | 64.2 | 100.5 |
| api_overview | 1258.6 | 569.4 | 563.3 | 1258.6 |
| api_contrast_filter_preview | 4498.6 | 4195.9 | 4167.5 | 4573.7 |

| Browser action | n | Median ms | Observed max ms |
|---|---:|---:|---:|
| component_initial_tree_load_production_bundle_cold | 1 | 2904.6 | 2904.6 |
| expand_cell_first_time | 5 | 2465.9 | 2616.0 |
| expand_block_first_time | 5 | 2565.1 | 2650.1 |
| select_epoch_metadata | 5 | 97.2 | 113.7 |
| search_selected_epoch_metadata | 5 | 32.5 | 48.2 |
| collapse_cell_cached | 5 | 61.1 | 70.1 |
| reopen_cell_cached | 5 | 65.7 | 67.1 |
| scroll_loaded_tree | 5 | 32.2 | 33.8 |
| next_cell_page_60 | 5 | 2238.2 | 2293.1 |
| expand_disjoint_cell_first_use | 5 | 2549.7 | 2617.2 |
| expand_disjoint_block_first_use | 5 | 2615.6 | 2632.1 |

All native exact assertions passed. Native contract/context was real, zero legacy oracle calls were observed, source inventories matched, and owned MySQL stopped normally. Browser errors were empty; owned Chrome and preview closed normally. Initial component load is a single observation. Disjoint branches were not expanded by the native first-cell probe.

The first native run set the legacy, ineffective `RIEKE_USER_PREFERENCES_PATH`. Its API actions did not write author, appearance, or project-index settings; project creation can leave a unique empty creation lock in the default preferences directory. The current harness additionally pins the actual `RIEKE_PREFERENCES_DIR` and `RIEKE_PROJECT_INDEX`. The subsequent browser-server baseline and all candidate runs use these isolated paths. The two native harness snapshots are preserved beside the receipt for exact provenance. Preferences correction changes isolation and stronger metadata-value assertions, not measured request semantics.
