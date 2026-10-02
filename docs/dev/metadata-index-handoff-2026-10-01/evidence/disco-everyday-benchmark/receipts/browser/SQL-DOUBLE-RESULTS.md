# Disco browser action experiment

Measured on Apple M1 Pro, macOS arm64, fresh owned headless Chrome 154.0.8037.58. The source is `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`; every copied frontend source file matches that checkout byte for byte (`source-sha256.json`).

Actual production-built React `PagedTree` and `MetadataPanel` components ran in a minimal experiment shell against the actual current Flask routes and a real sealed SQLite metadata index. The fixture has 100,000 synthetic epochs, 1,000 cells, 100 epochs per cell, 20 per block, four scalar parameters, and no waveform data. API annotation/SQL tables are existing test doubles containing no annotations. No user recording or app preference was modified. Browser, preview server and backend server were owned temporary processes.

| Action | Median | Range | Repeats |
|---|---:|---:|---:|
| First displayed tree, new browser context | 2.91 s | one observation | 1 |
| Expand a previously unloaded cell | 2.600 s | 2.566–2.699 s | 3 |
| Expand a previously unloaded block | 2.533 s | 2.515–2.648 s | 3 |
| Load next 60 cells | 2.275 s | 2.242–2.443 s | 3 |
| Select epoch and display metadata | 97 ms | 91–97 ms | 3 |
| Search focused epoch metadata | 32 ms | 31–49 ms | 3 |
| Collapse loaded cell | 62 ms | 57–62 ms | 3 |
| Reopen loaded cell | 66 ms | 66–66 ms | 3 |
| Scroll already-loaded tree | 32 ms | 32–33 ms | 3 |

These are input-to-observed-content timings using the renderer performance clock, completion checked on animation frames, followed by two frames. They include Playwright input dispatch/actionability and a roughly two-frame observation floor. Scroll was programmatic scroll plus frame completion, not a physical-wheel INP measurement. First view uses a host wall clock across navigation; it is component startup with an already prepared backend, not complete application cold startup. There is no statistically useful p95 from three samples.

The raw `browser-100k-raf.json` includes per-action Resource Timing request durations and response sizes. The observed expansion/page requests themselves take about 2.2–2.6 seconds. Cached collapse/reopen/search/scroll make no API calls. This supports the finding that the seconds-long delay lies chiefly in metadata/API preparation, while bounded frontend interactions are responsive. It does not assign the difference between action time and request time exclusively to React.

An earlier five-repeat successful run is preserved in `browser-100k.json`; its expansion completion used element-selector polling, which added artificial observation delay. Use the RAF run above for final latency. Two failed harness setup attempts are preserved separately: incorrect proxy Origin (production guard returned 403), then a cached-reopen selector expecting a descendant block to remain open. Those were experiment setup problems, fixed without modifying application code. Final RAF run completed with zero browser or HTTP errors.

Limits: component shell, not the full React App; empty annotation SQL doubles, not native MySQL; no private H5 data, trace loading, dense tags, true initial indexing, million-epoch browser run, installed Electron, packaging, or physical-display INP. Metadata predicate filtering is measured by the separate production-API experiment, not by the focused-epoch metadata search action in this table.

Reproduce while the owned synthetic API is running:

```sh
node run-browser.mjs ../metadata/browser-config.json http://127.0.0.1:PORT browser-100k-raf.json 3
```

The runner builds the component shell with the existing local Vite dependencies, then serves it on an ephemeral loopback port. The API proxy sets its backend Origin to its target to satisfy the production same-origin guard. It does not disable that guard.
