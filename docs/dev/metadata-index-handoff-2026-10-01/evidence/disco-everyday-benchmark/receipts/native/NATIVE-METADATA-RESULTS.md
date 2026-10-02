# Genuine native metadata read followup

Source: `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`. Native MySQL8.4.2, actual WorkspaceService and current production Flask routes.100k synthetic epochs, empty shared annotations and default saved curation. No SQL doubles. Reused sealed metadata index generation `everyday-100000` with matching synthetic project identity in a disposable native project.

Passed: True. Native contract verified: True; native context ready: True (`protocol-state-v3`). Legacy oracle calls across backend and browser requests: 0. Owned native database stopped normally: True.

API times include Flask serialization and JSON decoding. Three samples each; report median/observed maximum, not tail percentiles. No browser paint, H5 source reads or waveforms included here. Native `_oracle` calls were observed by a wrapper around that method; no native contract, generation token, selected read, storage, or cache behavior was changed.

| API action | First (ms) | Median (ms) | Maximum (ms) |
|---|---:|---:|---:|
| api_epoch_first_60 | 144.8 | 56.1 | 144.8 |
| api_epoch_next_60 | 55.7 | 55.7 | 56.8 |
| api_tree_root | 2381.5 | 1982.6 | 2381.5 |
| api_tree_expand_date | 2285.4 | 2331.5 | 2632.4 |
| api_tree_expand_cell | 2645.7 | 2645.7 | 2679.3 |
| api_tree_expand_block | 2582.9 | 2656.7 | 2693.9 |
| api_epoch_details | 71.2 | 71.2 | 78.2 |
| api_overview | 1163.7 | 563.4 | 1163.7 |
| api_contrast_filter_preview | 3962.7 | 3904.9 | 3962.7 |

Setup phases (seconds):
- synthetic_model: 0.896
- owned_native_boot: 3.461
- existing_sealed_index_open: 0.747
- normal_create_app_empty_native_annotations: 9.556
- native_context_first_proof: 0.027

Annotation preparation: 1.002s; actual native protocol read preparation: 0.792s. First-populated native app construction was9.56s; this is not an ordinary reopen benchmark. Dense-annotation startup from the other benchmark is a separate146s initial migration.

Root/date/cell/block tree work and contrast preview remain slow on genuine native authority despite fast bounded epoch pages. The earlier empty SQL-double metadata API timings cannot be labeled ordinary native app behavior.

Browser window completed: True. Total154.52s includes waiting/serving the browser followup. Canonical clone git status remained clean.

Receipts:
- `native-metadata-100k.json` SHA256 `07708723d6c2b7727a8940218e02ea39b19bfc7525d4e0724fb3001cba1d0610`
- `native_metadata.py` SHA256 `599cce0ebb43a15d16d5b4e11a593a5fafbb1811b82aea4a03eadfbf53dff27f`

Reproduction:

```sh
PYTHONDONTWRITEBYTECODE=1 \
RIEKE_PREFERENCES_DIR=/private/tmp/disco-everyday-bench-20261001/native/preferences-native-metadata \
/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python \
/private/tmp/disco-everyday-bench-20261001/native/native_metadata.py
```

First fixture setup failed its own storage identity alignment and normally stopped its owned DB; retained `native-metadata-100k-setup-failed.json`. Corrected disposable fixture descriptors only, then successful rerun.
