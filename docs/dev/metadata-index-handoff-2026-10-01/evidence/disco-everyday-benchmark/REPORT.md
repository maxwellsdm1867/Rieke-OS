# Disco everyday-action benchmark

Measured September 30, 2026 (Pacific), source `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`, Apple M1 Pro, 16 GiB RAM, 10 logical CPUs, macOS 14.2. Synthetic recording epochs; no user recordings or production source changed. No desktop packaging was required.

**At 100,000 epochs, selected metadata, bounded epoch pages and tagging are responsive. Uncached tree navigation takes about 2.4 seconds and metadata filter preview about 3.9 seconds. The same delay appears in the browser with the genuine native database.** These are measured on the current code, not estimates for an optimized implementation.

## What the user sees

Actual production-built React tree and metadata components, real HTTP to production Flask routes, real native MySQL 8.4.2 and sealed SQLite metadata index. Three repetitions per action except first view. Empty saved annotations/default curation. A minimal component shell was used; these are not installed Electron or full-App startup measurements.

| Browser action at 100k epochs | Median | Observed range |
|---|---:|---:|
| Expand an unloaded cell | 2.485 s | 2.434–2.584 s |
| Expand an unloaded block | 2.399 s | 2.398–2.548 s |
| Load next 60 cells | 2.141 s | 2.006–2.156 s |
| Select epoch and display metadata | 96 ms | 95–98 ms |
| Search within selected epoch metadata | 32 ms | 32–49 ms |
| Reopen cached cell | 65 ms | 65–66 ms |
| Scroll already loaded rows | 33 ms | 33–34 ms |
| First displayed component tree | 2.911 s | one observation |

Action completion was checked on animation frames, followed by two frames. Timings include automation input dispatch/actionability and a roughly two-frame observation floor. Scroll was programmatic; this is not a physical-wheel responsiveness measurement. Cached search/reopen/scroll make no API calls. Uncached tree requests themselves take roughly 1.9–2.5 seconds, identifying backend preparation as the main source of their delay. Request/action differences do not isolate React rendering cost.

## Backend actions

Production WorkspaceService and Flask API with genuine native MySQL, current `protocol-state-v3` context, zero legacy oracle fallback. Same 100k empty-annotation fixture. Three samples each, including the first invocation. Includes serialization and JSON decoding; excludes browser rendering.

| API action | First | Median | Observed maximum |
|---|---:|---:|---:|
| First 60 epochs | 145 ms | 56 ms | 145 ms |
| Next 60 epochs | 56 ms | 56 ms | 57 ms |
| Tree root | 2.382 s | 1.983 s | 2.382 s |
| Expand date | 2.285 s | 2.332 s | 2.632 s |
| Expand cell | 2.646 s | 2.646 s | 2.679 s |
| Expand block | 2.583 s | 2.657 s | 2.694 s |
| Epoch details including protocol state | 71 ms | 71 ms | 78 ms |
| Overview | 1.164 s | 563 ms | 1.164 s |
| Contrast filter preview, matching 20% | 3.963 s | 3.905 s | 3.963 s |

Browser and standalone API samples use different cache histories; their medians need not agree exactly. Selecting focused metadata is distinct from searching/filtering the entire workspace.

## Tagging with dense annotations

Separate real native MySQL fixtures: 3 authors × 5 tags per epoch/cell, 2 protocol curation scopes, 100 epochs per cell. Five samples. Timings are local API medians, with revisions read before writes where stated; they exclude browser paint.

| Action | 10k epochs | 100k epochs |
|---|---:|---:|
| Tag first ten selected epochs, including revision checks | 24 ms | 52 ms |
| Tag another ten, including revision checks | 24 ms | 23 ms |
| Filter to those twenty | 28 ms | 132 ms |
| Tag a cell and filter its hundred children | 52 ms | 155 ms |
| Remove tag from ten, commit only | 18 ms | 18 ms |
| Tag ten + another ten + filter twenty | 77 ms | 191 ms |

Both native runs passed 18 correctness/source checks, including revisions, hierarchy, Unicode distinctions and protocol independence. Small sample counts support medians and observed maxima, not reliable p95/p99 estimates.

## Initial preparation and larger scales

The 100k metadata index built in **25.7 s**, producing a **185 MB** SQLite file; reopening that persisted index took **0.70 s**. This measures index opening, not total application reopening.

The densely seeded native annotation fixture required **146.3 s** for its first populated app construction/migration at 100k, versus **7.36 s** at 10k. Annotation preparation accounted for 124.1 s of the 100k setup. This is initial preparation with derived lookup tables absent, not ordinary reopening of an already prepared project. The separate empty-annotation native fixture took 9.56 s to construct after index opening.

The 500k metadata fixture generated in 38.7 s, but its index build was stopped after 242 s under the experiment's four-minute build cap. It produced no sealed index or everyday-action timings. This is a bounded experiment stop, not proof of an intrinsic 500k database limit.

The **1,000,000-epoch** model generated in **76.8 s**, but index construction was stopped at **240.3 s**, also under the build cap. No sealed index or action measurements were obtained. Worker maximum RSS reported by rusage was **1,213 MiB**. The stop was for elapsed build time, not a breached memory or disk guard.

Larger runs were bounded by 1,700 MiB worker RSS, 600 MiB available RAM, 4 GiB free disk, a 240-second index build and a 600-second total worker limit. Only owned temporary workers could be stopped. RSS can fall with macOS paging/compression and is not a complete heap measure.

## Waveform read control

Actual temporary H5 files, 20,000-sample windows, current trace integrity/read code. A 32 MiB payload took 21.7 ms for the first integrity check plus read, then 1.85 ms median for five subsequent windows. A 256 MiB payload took 144.4 ms first, then 2.33 ms median. Initial reads hashed the full source once; subsequent windows did not. Same-size source mutation was correctly rejected.

These are local reads with OS cache warm after fixture construction. They exclude HTTP, chart rendering, cold storage, NAS and multi-gigabyte recordings.

## What to optimize next

1. **Tree requests:** page and group using indexed SQL before constructing workspace-wide state. A 60-row response still incurs seconds of broader preparation.
2. **Metadata filter preview:** use bounded preview rows and SQL aggregates; avoid rebuilding full catalogs, suggestion lists and matching-ID collections for each preview. The service-level 20%-match summary internally produced 2.63 MB even though the final native API response was smaller.
3. **Initial lookup/index preparation:** profile and improve bulk construction separately from interactive reads. The capped 500k/1m attempts do not qualify the current implementation at those scales.

Keep the shared browser UI as the iteration path. Re-run these same actions after each targeted backend change; package desktop when native integration needs validation. No performance fixes were applied during this experiment.

## Diagnostic controls and provenance

Earlier metadata API probes used transactional SQL doubles that selected the legacy state oracle. Their API latency is **not representative of the native fast path** and is retained only in `metadata-legacy.md`. Genuine native measurements above supersede them.

Read-only SQL controls on the same sealed 100k index took 0.267 ms for 60 ordered epoch rows and 1.563 ms for an indexed contrast count plus 60 rows, including JSON decoding. These omit native state, facets, curation, full memberships and API work; they show storage headroom, not achieved application latency. An instrumented preview profile spent 3.74 s in catalog preparation; genuine native preview latency confirms that this remains relevant beyond legacy fallback.

The browser, native databases and temporary servers were owned experiment processes and were closed normally. The source checkout and original user workspace were not edited. Exactness checks passed for completed 100k runs. Larger stopped fixtures have no fabricated or extrapolated action measurements.

Raw JSON, reproduction harnesses, source inventory, detailed reports and SHA-256 manifest accompany this report in `receipts/`. Database files and generated dependency trees are excluded from the saved bundle. Detailed scopes are in the individual reports.
