# Disco browser action experiment

Measured on Apple M1 Pro, macOS arm64, fresh owned headless Chrome 154.0.8037.58. The source is `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`; every copied frontend source file matches that checkout byte for byte (`source-sha256.json`).

Actual production-built React `PagedTree` and `MetadataPanel` components ran in a minimal experiment shell against the actual current Flask routes and a real sealed SQLite metadata index. The fixture has 100,000 synthetic epochs, 1,000 cells, 100 epochs per cell, 20 per block, four scalar parameters, and no waveform data. The production API uses genuine disposable native MySQL 8.4.2, `native_contract=True`, current `protocol-state-v3` native context, and zero legacy oracle fallback. Saved annotations are empty and default curation applies. The separate native receipt proves this setup; no SQL doubles are used in these final timings. No user recording or app preference was modified. Browser, preview server and backend server were owned temporary processes.

| Action | Median | Range | Repeats |
|---|---:|---:|---:|
| First displayed tree, new browser context | 2.91 s | one observation | 1 |
| Expand a previously unloaded cell | 2.485 s | 2.434–2.584 s | 3 |
| Expand a previously unloaded block | 2.399 s | 2.398–2.548 s | 3 |
| Load next 60 cells | 2.141 s | 2.006–2.156 s | 3 |
| Select epoch and display metadata | 96 ms | 95–98 ms | 3 |
| Search focused epoch metadata | 32 ms | 32–49 ms | 3 |
| Collapse loaded cell | 62 ms | 57–62 ms | 3 |
| Reopen loaded cell | 65 ms | 65–66 ms | 3 |
| Scroll already-loaded tree | 33 ms | 33–34 ms | 3 |

These are input-to-observed-content timings using the renderer performance clock, completion checked on animation frames, followed by two frames. They include Playwright input dispatch/actionability and a roughly two-frame observation floor. Scroll was programmatic scroll plus frame completion, not a physical-wheel INP measurement. First view uses a host wall clock across navigation; it is component startup with an already prepared backend, not complete application cold startup. There is no statistically useful p95 from three samples.

The raw `browser-native-100k-raf.json` includes per-action Resource Timing request durations and response sizes. The observed expansion/page requests themselves take about 1.9–2.5 seconds. Cached collapse/reopen/search/scroll make no API calls. This supports the finding that the seconds-long delay lies chiefly in metadata/API preparation, while bounded frontend interactions are responsive. It does not assign the difference between action time and request time exclusively to React.

Earlier SQL-double runs are kept separately in `SQL-DOUBLE-RESULTS.md`, `browser-100k.json`, and `browser-100k-raf.json`. Those are not native app timings. The legacy SQL-double RAF median cell expansion was 2.600 s versus 2.485 s with actual native MySQL; block expansion 2.533 s versus 2.399 s; next cell page 2.275 s versus 2.141 s. Thus the seconds-long tree delay persists in the native path. The five-repeat SQL-double run used element-selector polling and added artificial observation delay. Use the native RAF run above for the final action table. Two failed harness setup attempts are preserved separately: incorrect proxy Origin (production guard returned 403), then a cached-reopen selector expecting a descendant block to remain open. Those were experiment setup problems, fixed without modifying application code. Final RAF run completed with zero browser or HTTP errors.

Limits: component shell, not the full React App; empty saved annotations/default curation, not dense annotations; no private H5 data, trace loading, dense tags, true initial indexing, million-epoch browser run, installed Electron, packaging, or physical-display INP. Metadata predicate filtering is measured by the separate production-API experiment, not by the focused-epoch metadata search action in this table.

Reproduce while the owned synthetic API is running:

```sh
node run-browser.mjs ../native/native-metadata-browser-config.json http://127.0.0.1:PORT browser-native-100k-raf.json 3
```

The runner builds the component shell with the existing local Vite dependencies, then serves it on an ephemeral loopback port. The API proxy sets its backend Origin to its target to satisfy the production same-origin guard. It does not disable that guard.
