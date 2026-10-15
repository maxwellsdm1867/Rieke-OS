# Independent review: one uncached million-sample trace

Date: 2026-10-15. Reviewed source: dirty working tree on `bf5064d7ad9ef4f6541395496bcd56c4c39a9003`, at `/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/source`. Exact reviewed file and diagnostic hashes are in [manifest.json](/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/evidence/direct-recovery/fresh-review/manifest.json). This clone's `origin` is the historical local checkout `/Users/maxwellsdm/Documents/GitHub/Rieke-OS`, whose main is `f52312f06a651500ea3e121feaebd118201d0f7b`; it is neither live GitHub main nor the reviewed working-tree identity. No application implementation, cache, prefetch, scientific file, or installed app was changed by this review.

## Decision

**Do not claim under 50 ms from click to complete correct display. That result remains unmeasured. Do not abandon single-load investigation in favor of caching:** a fresh, deliberately restricted experiment reduced an uncached sample read from approximately 155 ms to **38.85 ms** by reading compressed chunks and inflating them with four native workers. All million float64 values, including negative zero, exactly match the independent expected payload. That is a source-read diagnostic, not an integrated reader or UI result.

The fastest plausible correct path is one fresh authority check, one focused-stream demand request, exact source reading with a narrowly admitted compressed-chunk specialization if it passes further tests, one binary response, one browser validation/statistics pass, one geometry pass, and one complete paint. Keep ordinary HDF5 as the generic path. The lower-risk immediate opportunity is eliminating repeated frontend scans; it cannot alone fix the current approximately 162 ms source-and-encoding path.

Priorities before implementation:

1. Establish actual click-to-complete-display stage timing in both frozen Workbench and Inspect with Live metadata off. Prove exactly which requests occur and measure opening/closing authority separately from HDF5.
2. Prototype fused browser validation/statistics in a disposable harness, preserving exact arrays, missing-sample behavior, extrema, and viewport geometry. Current pure array work alone is about 26 ms.
3. Test the restricted native chunk reader against the actual source-layout family and adversarial owned fixtures. Only then decide whether its speed justifies production complexity. It offers the largest demonstrated uncached-source improvement.
4. Consider cache or preparation separately only after these single-load results. A retained decompressed chunk cache is not evidence about first demand reads.

## What the current path actually does

[`useEpochInspection.js`](../../workspace-app/src/epoch-browser/useEpochInspection.js) normally uses the admitted lightweight page row when Live metadata is off. It still requests detail when a supplied scoped owner lacks an attested trace descriptor. That request is an authority requirement, not a universal requirement to fetch metadata before traces. Count requests on both real entry points before deleting anything. Correct page descriptors should make the ordinary one-million-sample case one trace request without a metadata-value request.

[`TraceViewer.jsx`](../../workspace-app/src/traces/ui/TraceViewer.jsx) is the shared viewer; there is no separate `WholeTraceViewer.jsx` in this checkout. [`readWholeTrace.js`](../../workspace-app/src/traces/readWholeTrace.js) negotiates up to ten contiguous 100,000-sample windows in one binary foreground response for an exact complete stream. It admits complete identity/window/scope metadata before publishing. Contiguous binary windows become a single `Float64Array` view without another million-value copy. Imported snapshots and generic JSON retain their separate bounds and behavior.

[`workspace_service.py`](../../python/workspace_service.py) captures source/row/manifest authority, opens HDF5 once, resolves sealed paths, checks stream and epoch UUIDs and sample rate, then reads ten windows. Each window reads compound records, checks every unit, creates numeric values, checks finiteness and source stat; closure checks source and service publication witnesses. [`workspace_trace_binary.py`](../../python/workspace_trace_binary.py) checks finite arrays again and creates the bounded binary response. This last repeated finite scan is secondary: previous encoding measurements are already below 1 ms.

The foreground read remains under the global DB lock, and frozen Workbench also holds registration/annotation authority. [`workbench.py`](../../python/disco/workbench/workbench.py) does fresh candidate/pending-membership and opening/closing scope checks; serialization happens afterward. [`ProtocolStateReader.read_revision`](../../python/workspace_protocol_state.py) avoids unused curation materialization where eligible, but `native_context` still constructs and exactly compares cohort metadata. The entire context is not constant-time. Moving HDF5 outside a shared lock may reduce contention but does not make its isolated serial work faster; it needs equivalent detached-plan and closing checks and is not a substitute for measuring authority cost.

`_verified_source` hashes the whole source file if its stored signature has not been verified. The reviewed read diagnostics hash before timing. A first read of an unverified large source therefore has an additional potentially dominant cost. Existing verified-source signatures are a separate authority fact from cached trace samples.

## Measurements made for this review

All source experiments use only [the owned fixture](/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/evidence/direct-recovery/million-loading/fixture.json): 1,000,000 records of `quantity:<f8` plus `units:S10`, gzip level 4, chunks of 64 records, 15,625 chunks, 9,345,026 source bytes. Each decompressed chunk is only 1,152 bytes. Source SHA-256 is `f2eb8edd9852f917c697584bea7f4cad367a09300cc4d7081a8075db049cdf5f`; the exact 8,000,000-byte numeric payload SHA-256 is `79444f9a2c71e3f781daab20d9bccf3e75b181086d3d3b86406e2c9dadf701ea`.

Each source variant reopens HDF5 and retains no decoded chunks between samples. File hashing warmed the OS cache before the first sample. **These are OS-warm, sample-uncached reads, not cold-storage measurements.** Every variant checks the same fixture identity/rate, every unit, finite values, final stat signature, and exact payload equality; the independent equality check is outside the timer. No HTTP, native project SQL, candidate scope, React, Canvas, or display frame is included. Five serial interleaved rounds follow the separately retained first call per variant. First calls are not independent cold runs.

| Experiment A | First call ms | Five-run median ms | Observed range ms |
| --- | ---: | ---: | ---: |
| Ordinary full HDF5 slice, checks, raw encoding | 198.38 | 159.06 | 158.40–178.15 |
| `read_direct_chunk` for every chunk, Python zlib inflate | 117.09 | 112.74 | 111.35–117.94 |
| `chunk_iter`, one fixture-bounded physical span read, Python zlib inflate | 98.42 | 96.38 | 95.02–98.62 |

The last median separates chunk-index enumeration (8.41 ms), span reading (1.26 ms), inflate plus assembly (79.49 ms), and unit/copy/finite validation (5.26 ms). This identifies decompression/assembly as the largest remaining cost in that variant. It does not label HDF5 slice time as disk latency.

| Experiment B, separately paired | First call ms | Five-run median ms | Observed range ms |
| --- | ---: | ---: | ---: |
| Ordinary full HDF5 slice | 188.04 | 155.46 | 154.80–171.32 |
| Chunk enumeration/span read, one native inflate worker | 100.76 | 99.62 | 97.96–101.03 |
| Same, four native inflate workers | 42.23 | **38.85** | 38.65–41.41 |

Four-worker median: open/identity 0.50 ms; chunk index 7.92 ms; span read 1.21 ms; inflate/assembly including native thread creation and descriptor arrays 23.71 ms; units/copy/finite 5.07 ms; close/stat 0.25 ms; raw encoding 0.15 ms. Stage medians need not sum to the total median. Native workers never call HDF5: they inflate independent zlib chunks already read into memory and write disjoint output ranges. Python and native zlib were both 1.2.12; Python 3.11.13, h5py 3.16.0, HDF5 2.0.0, NumPy 2.4.6. No dependency was installed. System `clang` compiled a diagnostic dylib kept only in the evidence folder.

Scripts, first calls, all observations, and helper source are preserved in [fresh-review evidence](/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/evidence/direct-recovery/fresh-review/manifest.json): [raw_chunks.py](/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/evidence/direct-recovery/fresh-review/raw_chunks.py), [raw_chunks.json](/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/evidence/direct-recovery/fresh-review/raw_chunks.json), [native_chunks.py](/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/evidence/direct-recovery/fresh-review/native_chunks.py), [native_chunks.json](/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/evidence/direct-recovery/fresh-review/native_chunks.json), and [inflate_chunks.c](/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/evidence/direct-recovery/fresh-review/inflate_chunks.c).

### Browser-array work

A separate Node diagnostic runs the actual current decoder, gap-count expression, `finiteExtent`, and `traceDisplaySegments` on the same exact million-sample payload, at 2,000 physical plot columns. One first call plus nine repeated calls are retained in [scan_geometry.json](/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/evidence/direct-recovery/fresh-review/scan_geometry.json), with [script](/Users/maxwellsdm/Documents/Codex/disco-trace-latency-2026-10-15/evidence/direct-recovery/fresh-review/scan_geometry.mjs).

| Stage | First call ms | Median ms |
| --- | ---: | ---: |
| Binary decode and finite scan | 5.96 | 2.01 |
| Gap-count reduction | 8.52 | 7.45 |
| Finite extent | 14.06 | 11.47 |
| Display geometry | 9.07 | 5.03 |
| Total | 37.60 | **26.01** |

This is Node, not Electron presentation qualification. It excludes fetching/copying the response, React updates, DOM/layout, Canvas commands/rasterization, and compositor/display. No timing improvement is claimed for a fused implementation because none was built. `getLoadedExtent` can add another scan later during interaction but is not automatically part of initial load; do not double-count it.

For the finite binary path, calculate min/max/count while doing the required decoder validation, retain those facts with that exact loaded array, and reuse them for full-interval extents and gap count. JSON/null/nonfinite input must retain its own correct handling. Partial viewport extents need separate viewport statistics. Keep original arrays for cursor/zoom and preserve the existing first/last/min/max sample indices in recorded order for each physical pixel, with gap breaks. A Web Worker or OffscreenCanvas is not the first recommendation: moving work can preserve responsiveness, but adds transfer/scheduling and does not by itself reduce complete-result latency.

## What primary sources support, and what they do not

HDF5 chunk layout makes every touched compressed chunk participate in a read. Small chunks increase chunk-processing work; compound-field selection does not turn this fixture into a separate contiguous quantity array. `read_direct` can avoid an intermediate array copy but still uses normal HDF5 reading. These mechanisms explain why one-open batching is useful without making tiny-chunk decompression disappear. The prior exact-fixture trials found full slice/read-direct around 160.6/153.8 ms and separate quantity/unit reads around 330.9 ms; those are supporting local evidence, not general API speed promises. [h5py dataset documentation](https://docs.h5py.org/en/stable/high/dataset.html)

h5py's raw chunk API explicitly bypasses normal filters, while chunk iteration provides logical positions, filter masks, physical locations, and sizes. That enables the diagnostic, but it also transfers responsibility for filter correctness to the caller. [h5py low-level DatasetID documentation](https://api.h5py.org/h5d.html)

Simply putting ordinary h5py reads in several Python threads will not produce the tested decompression parallelism: h5py serializes calls into HDF5 with a global lock. The experiment parallelizes only independent non-HDF5 inflate operations. [h5py threading documentation](https://docs.h5py.org/en/stable/threads.html)

zlib's in-memory functions validate compressed data and support independent thread-safe streams with appropriate allocation. The C helper uses bounded `uncompress` calls and requires exactly 1,152 output bytes per fixture chunk. It is not a generic HDF5 implementation. [zlib manual](https://zlib.net/manual.html)

libdeflate is a plausible alternative decoder because it is designed for independent blocks and exposes zlib-buffer decompression with explicit size/error results. It was not available locally and was not installed or benchmarked. No speed claim is made for it. [libdeflate project](https://github.com/ebiggers/libdeflate), [public header](https://raw.githubusercontent.com/ebiggers/libdeflate/master/libdeflate.h)

A larger retained HDF5 raw-chunk cache can eliminate repeated decompression after the initial read. It cannot demonstrate a faster first uncached load; the previous roughly 30.9 ms repeated/192 ms first result is consistent with that distinction. [h5py file/chunk-cache documentation](https://docs.h5py.org/en/stable/high/file.html#chunk-cache)

Browser animation callbacks occur within the rendering-update sequence before final rendering/UI update. Consequently a timestamp inside the paint function or its first animation callback is not proof that the new complete trace was presented. [HTML rendering-update specification](https://html.spec.whatwg.org/multipage/webappapis.html#update-the-rendering)

## Production viability and correctness boundary

The native experiment is promising but deliberately supports only one dense, one-dimensional, exact compound dtype with gzip as its sole filter, no skipped-filter chunks, and a fixed chunk size/count. A production specialization must reject unsupported layouts before starting and use the ordinary HDF5 path. It must correctly handle or explicitly exclude endian variants, padding/field offsets, shuffle/checksum/custom filters and filter masks, sparse/fill chunks, edge chunks, virtual/external datasets, unexpected storage drivers, truncated/corrupt chunks, and source replacement during reading. Corruption must remain an error, not silently become successful fallback data.

The diagnostic's single physical span is bounded by this approximately 9 MB owned file. **Do not transplant that technique as an unbounded min-offset-to-max-offset read:** a real dataset's chunks may be spread across a huge recording with unrelated data between them. Use capped/coalesced reads or a bounded direct-chunk fallback, with freshly verified file identity and correct logical placement. Index enumeration and allocation must remain in the uncached timing.

Four worker threads also consume cores shared with Electron and other requests. Limit foreground concurrency, cancellation, memory, and output publication; never emit partial unvalidated data. A native extension requires pinned builds, packaging/profile inclusion, supported macOS/architecture checks, and tests beyond the diagnostic's same-host correctness. The existing HDF5 reader already handles this complexity; maintaining that general correctness is the main cost of specialization.

Every-unit validation is necessary under the current contract. A header's unit string alone does not prove all compound records agree. Keep exact values, sample count/rate/units, UUIDs, source hash, frozen pending membership, and opening/closing publication freshness. No float32 conversion, resampling, reduced scientific payload, reimport, source rewriting, or changed interpretation is proposed.

## Next falsifiable experiment

Run a bounded comparison on owned data through both actual UI surfaces, with Live metadata off and samples never previously loaded into the renderer. Use the same exact source, viewport, scale, hardware, and canonical harness for baseline/candidate. First measure the current full path, then a disposable fused-scan variant, then the admitted native-reader variant if its layout tests pass. Keep first-process/first-HDF5 samples and repeated OS-warm samples separate. Do not flush system caches or label a reopen as physical cold I/O.

Measure: user input timestamp → request issuance; authority opening/lock wait; source verification/hash if incurred; HDF5 metadata/index/read/decompression; sample/unit validation; closing authority; binary serialization; response body completion; browser decode/statistics; React commit; geometry/Canvas completion; first presented frame containing the complete new trace. Retained old pixels and request completion are not completion. Use compositor/presentation evidence where available and state the approximation if the harness only observes a later frame/screenshot.

For each successful display, check the million-value float64 payload hash, full count/time range, expected extrema/gaps, sample-rate/units, exact epoch/stream/source identity, and frozen candidate token. Exercise a changed closing source/scope and rapid epoch replacement to prove stale results never publish. Include one genuinely new target stream per uncached trial. Test corrupt filter data, unsupported layouts, and a fragmented owned fixture before admitting a specialization. Retain every raw row and failures; report first-run, median and tail separately rather than hiding contention.

**Success criterion is under 50 ms to the complete correct displayed trace, not under 50 ms HDF5 or first pixels.** At the measured 38.85 ms native source cost, the current 26.01 ms array work already exceeds that budget in a rough additive estimate before all other stages. Fusing scans may create enough headroom to make a real test worthwhile; adding separate-stage medians does not predict the integrated result. If the integrated path or initial source hash remains over budget, report that result and decide explicitly between accepting the measured first-load cost and separately authorizing amortization. Current evidence proves neither universal impossibility nor achievement of the full target.
