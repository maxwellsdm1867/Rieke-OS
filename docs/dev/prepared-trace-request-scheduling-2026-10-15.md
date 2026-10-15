# Prepared trace request scheduling

The prepared-display viewer now starts its exact captured read in a dedicated
layout-effect owner. It invokes the transport immediately and derives loading
from path/revision/owner/reload identity. The generic resource hook is unchanged.
Cancellation and late-result fencing remain mandatory; this is demand loading,
not background preparation or a completed-sample cache.

## Causal observations

The full React workflow fixture previously spent about 26 ms between the epoch
click and fetch invocation. Instrumentation separated render, layout commit,
passive effect, whole-trace admission and fetch entry. The trace's first render
occurred near 10 ms and layout near 17 ms. Passive resource setup occurred near
26 ms. Moving setup to layout alone was harmful: its loading state update caused
React to process effects and another render before the existing request
microtask ran. Fetch then started near 42 ms.

Each experiment used one excluded warmup followed by three interleaved baseline
and candidate pairs, fresh renderer contexts, an OS-warm owned H5 file, 1,000
metadata epochs and a 167-epoch prepared cohort. Every read transferred and
independently verified all 8,000,000 sample bytes after capturing timing. Every
response/window capability and canonical source/index/native-helper gate passed.

| Experiment | Median click to fetch | Median post-stroke | Median second RAF |
| --- | --- | --- | --- |
| Passive baseline, first experiment | 26.0 ms | 105.3 ms | 115.7 ms |
| Layout setup with existing microtask | 41.5 ms | 120.8 ms | 135.8 ms |
| Passive baseline, immediate experiment | 26.1 ms | 106.6 ms | 120.4 ms |
| Layout setup with immediate transport | 17.4 ms | 96.8 ms | 106.4 ms |
| Passive baseline, final product-hook comparison | 26.0 ms | 102.0 ms | 114.8 ms |
| Actual dedicated prepared hook | 17.4 ms | 96.5 ms | 108.8 ms |

The final comparison retained a passive sample with a 102.5 ms HTTP interval;
other final HTTP intervals were 57.3–63.3 ms. It was not removed. The change
reliably advances fetch invocation in this diagnostic; it does not establish a
sub-50-ms complete trace or remove the HTTP/decoding/painting cost.

These are **Vite development / React development**, Chrome 155 headless
measurements, using real production components and the prepared-display/H5
route, with SQL explicitly doubled. They are not installed-app production-mode,
native-MySQL, cold-storage, compositor, or release qualification. In particular,
the roughly 17 ms event/render/commit interval may be smaller in a production
build. The post-stroke timestamp and two stable RAF observations precede the
independent byte oracle and are not proof of physical display presentation.

## Evidence and lifecycle checks

The kit's sibling `evidence/direct-recovery/frontend-request-scheduling` retains
all requests, timings, marks, failed-policy comparison and exact source overrides:

- `run-20261015T064635Z`: passive versus layout/microtask.
- `run-20261015T064748Z`: passive versus experimental immediate layout dispatch.
- `run-20261015T065239Z`: passive versus the actual dedicated prepared hook.

Each run has `summary.json`, source receipt SHA, raw sample JSONL, exact-byte
verification, per-run harness and cleanup receipts. The base snapshot's 1,901
file hashes were verified after each experiment. Final candidate source overrides
for TraceViewer, EpochViewer and the new hook were captured and hash-compared
across all three candidate runs.

Nine focused tests passed: six request-lifetime tests plus three real canvas
lifecycle tests. They exercise immediate dispatch ordering, rapid A-B-A changes,
reload nonce, workspace owner replacement, cancellation, late completion,
unavailable authority, exact raw display, and tag refresh independence. Curation
retention is separately scoped by displayed epoch/source and mutation owner, so
old epoch tags/review never remain visible below another captured trace.

Independent source review found that a completed A result could reappear after
A-B-A under the same identity tuple. The final hook additionally requires the
published request's AbortSignal to remain live. Cleanup thus retires both pending
and completed results. Regression tests cover completed success/error A-B-A and
actual React Activity hide/reconnect. This final admission predicate was added
after the timed source capture; dispatch scheduling was unchanged, but the table
retains its exact pre-fence source attribution rather than claiming a new timing.
