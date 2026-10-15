# Single-load browser statistics and QC drawing audit

The binary decoder now collects min/max and sample counts during its required
finite-value validation. Those local facts follow the exact decoded sample views
through whole-trace admission. The viewer reuses them for full-interval axes and
missing-sample presentation. There is no sample cache, prefetch, background work,
or float32 conversion. The final fidelity exception for manually clipped views
is documented below; line joins remain unchanged.

Statistics are not accepted from response JSON. Only views created by the local
binary decoder and exact arrays assembled from those admitted views retain weak
statistics metadata. Trace owners do not mutate their decoded payloads. Custom
and JSON arrays are scanned, including null/NaN/infinity gaps; merely being a
Float64Array does not grant a producer retained statistics. A zoomed subarray
gets statistics for that visible interval rather than borrowing whole-stream
extrema. Full-precision cursor reads continue to use the original samples.

## Owned million-sample browser timing

[Raw observations](../../../evidence/direct-recovery/frontend-fused-qa/browser-timing-results.json)
and [harness](../../../evidence/direct-recovery/frontend-fused-qa/browser-qa.mjs)
are in the durable local evidence folder adjacent to this source checkout.
Chrome 155.0.8059.40 ran headless at 1,103 CSS pixels, 2,000 physical plot columns,
and DPR 2. The exact 8,000,000-byte owned payload hash is
`79444f9a2c71e3f781daab20d9bccf3e75b181086d3d3b86406e2c9dadf701ea`.
Each observation creates a fresh binary response and validates every returned
sample against that payload outside the timer. There are no retained sample
reads between observations.

The baseline uses the bf5064d painter and decoder with only the already-reviewed
one-million-sample framing cap reproduced in the harness. Both baseline and
candidate use the same screen-resolution display reducer. Both run the real
whole-trace admission and actual production Canvas painter, exposed only by the
harness. First calls are retained separately, followed by seven interleaved
rounds per variant. The browser timing slot was serialized against the backup
and backend source-read work.

| Stage | Baseline median ms | Fused median ms |
| --- | ---: | ---: |
| Binary decode / finite validation | 2.6 | 2.4 |
| Whole-read admission including decode | 2.6 | 2.4 |
| Gap/statistics retrieval | 6.9 | 0.0 at clock resolution |
| Painter, including geometry and Canvas commands | 17.5 | 6.0 |
| Decode through complete command submission | 27.8 | 9.4 |
| Through two animation-frame opportunities | 33.6 | 16.8 |

Complete-command first calls were 49.5 ms baseline and 13.9 ms fused; these are
ordered first calls in one browser, not independent cold-process comparisons.
Repeated complete-command ranges were 18.5–31.1 ms and 7.6–11.4 ms respectively.
Stage medians need not sum to the total median. The first-call decoder was 5.0 ms
baseline and 5.7 ms fused; no first-call finite-validation speedup is claimed.

This measures an already loaded payload in a browser. It excludes HDF5, SQL,
source hashing, HTTP response transfer, React navigation, and user input. Two
animation frames are rendering opportunities, not proof of physical display
presentation. These measurements do not establish a sub-50-ms end-to-end click.

## QC comparison and limits

The separate [raster observations](../../../evidence/direct-recovery/frontend-fused-qa/browser-raster-results.json)
compare isolated spikes/troughs, alternating high frequency, clipping plateaus,
physical pixel boundaries, JSON null/nonfinite gaps and isolated finite points,
and an all-sample zoom. There are 72 combinations of 303/603/903 CSS-pixel widths,
DPR 1/2, and auto extent/manual amplitude [-2,2]. The independent raw oracle
visits every finite raw sample and breaks at every gap; it never calls the
production display reducer.

Every finite-run endpoint and per-physical-column first/last/min/max remained
present in recorded order. No connection crossed a missing/nonfinite sample.
All original values remained unchanged, and all-sample zoom rasters matched the
full raw oracle exactly. This verifies those properties for the adversarial
fixtures; it does not prove universal QC equivalence at screen resolution.

The full raw oracle and the existing reducer differed in 50 of 72 raster cases.
The largest difference was 6.5347% of canvas pixels for pixel-boundary spikes at
303 CSS pixels/DPR 1, clipped to [-2,2] while raw spikes reached ±40. The full
raw line colored 24,954 pixels and the reducer colored 30,498. The additional
coverage arises around clipped subpixel crossings. Preserving extrema does not
make the two rasters identical. A two-physical-pixel proximity diagnostic is
reported in the raw observations, not treated as a perceptual or QC guarantee.

A second check compares the existing production painter with the fused-statistics
painter using full RGBA bytes, including axes, for all 72 cases: **zero changed
bytes**. The speed change therefore preserves the existing raster in this audit.
The [stats-only triptych](../../../evidence/direct-recovery/frontend-fused-qa/worst-before-clipped-fallback.png)
shows the full raw oracle, prior production baseline, and fused candidate side by
side; the last two are identical. Individual raw/baseline/candidate images are
saved beside it at the original resolution.

The proximity diagnostic is directional. There were zero raw colored pixels
without reduced ink within two physical pixels, but up to 84 reduced pixels
without raw ink within that distance in the JSON-gap/sine fixture at width 303,
DPR 2, amplitude [-2,2]. Therefore even this loose neighborhood test does not
establish identical spatial coverage. Stroke joins and subpixel interpolation
remain separate visual questions; no unmeasured causal explanation is asserted.
The statistics-only audit did not alter rendering policy. The subsequent
explicitly approved clipped-range correction follows below; no line-join change
is included.
A coarse view cannot preserve every temporal detail of a million-sample signal;
exact cursor inspection and all-sample zoom remain necessary for resolving
subpixel features. This audit does not claim that every possible QC anomaly is
perceptually preserved at whole-trace scale.


## Final fidelity exception for manual clipping

When manual amplitude limits exclude any finite sample in the current viewport,
the production painter now draws the complete raw polyline. It uses the raw
viewport min/max statistics, rather than padded axis bounds, to make that
choice. Every original finite index is emitted in order, with exact gap breaks
and isolated points. There is no new control, change in line joins, resampling,
or mutation of scientific samples. Auto extent and nonclipping manual limits
keep the existing reduction policy.

This deliberately spends more paint time to preserve waveform appearance in a
pathological clipped view. A harness-only owned-million-sample comparison at
1,103 CSS pixels/DPR 2 measured median command submission of 9.3 ms reduced and
27.7 ms exact, across three paired rounds after separately retained first calls.
Two-animation-frame opportunities were 33.3 and 33.8 ms. These are paint-only
measurements on this signal, not a guaranteed bound on other waveforms. See
[all clipped-cost rows](../../../evidence/direct-recovery/frontend-fused-qa/browser-clipped-cost-results.json).

The round-join diagnostic eliminated the 84 distant extra pixels in the
sine/gap fixture, but still differed from the original raw raster by 244 mask
pixels. Comparing both references with round joins gave the same discrepancy.
That experiment supports stroke-join amplification as one contributor, but it
is not a universal correction. Production therefore keeps its joins and uses
exact raw drawing for clipped ranges instead.

The [final 72-case audit](../../../evidence/direct-recovery/frontend-fused-qa/browser-final-results.json)
verifies zero changed RGBA bytes between the candidate and the full raw oracle
for **all 36 clipped cases**, and zero changed RGBA bytes between the candidate
and the prior production painter for **all 36 unclipped cases**. The
[final worst-case triptych](../../../evidence/direct-recovery/frontend-fused-qa/worst-raw-baseline-fused.png)
now has identical raw and candidate panels. The original production baseline
remains visibly different. The remaining unclipped reduction is still an
approximation: the largest raw-vs-candidate mask difference in this set is 3.43%
and there are up to eight reduced pixels farther than two physical pixels from
raw ink. These are unchanged baseline properties, not a claim of universal QC
fidelity.

The final first-ever candidate check in a fresh Chrome process submitted the
complete owned-million-sample trace in 32.6 ms and reached two animation-frame
opportunities in 34.3 ms (decode 13.2 ms, painting 18.3 ms). It is retained as a
single startup observation, not substituted for the earlier interleaved warmed
median and not presented as full application click latency. Exact final source
hashes are in the final audit receipt.

Validation: 117 frontend trace, resource/context, retention, and shared
Inspect/Workbench/Search tests passed in 9.168 seconds. The new component test
checks every original finite point, exact gap boundaries, isolated drawing, and
continued reduction for a range that contains every sample. The log is
[frontend-final-tests.log](../../../evidence/direct-recovery/frontend-final-tests.log).
