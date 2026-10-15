# Fresh trace-read overhead and retained outliers

The target remains a complete, correct million-sample display under 50 ms.
Component timing does not establish that target. All measurements below use an
owned gzip64 float64/S10 fixture, a warm OS file cache and fresh per-read HDF5
metadata; they do not establish cold-storage, installed-app or compositor timing.
No sample cache, source rewrite or GC-policy change is involved.

## Confirmed overhead

Retaining HDF5 callback records created thousands of Python objects per read.
Diagnostic runs observed 36–40 generation-0 collections, 3–4 generation-1
collections and occasional generation-2 collections. Request-local integer
arrays and scalar memoryview writes removed those retained records; diagnostic
candidate reads recorded no collections. This establishes a mechanism for the
observed callback allocation/GC work. It does not retroactively assign a cause
to every earlier uninstrumented slow sample.

A separate fresh-process profile found that endpoint validation in the geometry
encoder entered NumPy's general set-membership path and lazily imported masked
array support. Exact ordered lookup over already validated, strictly increasing
indices preserves endpoint coverage without that initialization. Four separate
process samples per arm measured encoder medians of 5.81 ms and 0.77 ms with
identical wire bytes. The existing endpoint validity checks remain required.

Commit `483e00b995a9e5d0be97a2314fb051fc2cb4d06e` combines those changes and
first-commit canvas measurement. Its ordinary browser samples were:

| Observation | First sample | Second sample | Third sample |
| --- | ---: | ---: | ---: |
| Click to request | 17.5 ms | 12.5 ms | 13.3 ms |
| Click to completed stroke | 68.1 ms | 53.4 ms | 56.6 ms |
| First RAF observing ready trace | 71.4 ms | 54.2 ms | 69.9 ms |
| Second RAF observing ready trace | 87.9 ms | 70.7 ms | 87.6 ms |

All geometry indices, point bytes, full statistics, Canvas coordinates, prepared
identity and exact cursor sample tiles passed independent checks. These are
production React with owned SQL doubles, not the installed application. The
under-50-ms target was not met. Pinned and previous-iteration everyday-query
comparisons passed without review flags; they do not qualify display latency.

## Native callback experiment

The remaining Python callback still processes 15,625 chunk records per million
samples. An external prototype replaces only collection of that fresh map with
a bounded C callback. HDF5 still supplies the metadata, and the existing owner
still validates physical ranges and source identity and decodes every sample.

The probe verified Darwin arm64, h5py 3.16.0, HDF5 2.0.0 and NumPy 2.4.6, with
identical HDF5 symbol addresses from the loaded dataset/identifier extensions and
the expected private library. Eight serial ABBA samples per implementation gave:

| Fresh open/read/close | Median | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| Python callback baseline | 25.3618 ms | 24.2295 ms | 26.6250 ms |
| Native callback prototype | 16.9390 ms | 16.1756 ms | 18.8710 ms |

Every 8,000,000-byte output matched exactly. Source SHA-256 and stat were unchanged.
Fifteen maps covered dense, reverse-fragmented, sparse, masked and tail layouts
with user blocks of 0, 512 and 4096 bytes. Six callback flag adversaries, 22
qualification/context/failure/locking checks and both copies of the existing 29
native-reader tests passed. An initial fault run found that a closed dataset was
queried before its validity check; the corrected ordering passed the retained
second run. The helper links only system runtime support and calls no HDF5 APIs.
These prototype numbers exclude HTTP and rendering and are not production
integration qualification.

## Evidence and rejected alternatives

Raw receipts are retained outside the checkout under the durable task kit's
`evidence/direct-recovery/`: `prepared-geometry-483e00b-ordinary-v1`,
`prepared-geometry-483e00b-diagnostic-v1`, `native-callback-prototype`, and the
matched everyday-query directories. Earlier slow rows remain in their original
receipts, including the uninstrumented 48.346 ms map comparison sample; they are
not removed or averaged into different runs.

Sibling CSS layout containment was rejected after screenshot comparison showed
changed Select/Tag label wrapping. Earlier request dispatch was also rejected
for the general first-focus path: there is no canvas before commit, and opening
metadata can change its width in narrow or saved-closed sessions. The measured
1500px fresh fixture already has metadata open; its first focus does not change
the pane columns. The current hook dispatches at the first exact canvas
measurement. Predicting dimensions or creating an event-owned request would
need a different lifetime contract. Neither change is part of this fix.

## Integration checks

The integrated collector is an optional version-1 feature in the existing ABI-4
helper, accessed through one private Python bridge. The established physical-map
and sample-validation owner is unchanged. All 99 trace tests passed, including
actual callback use on a fragmented partial read and identical output through an
older helper lacking the optional symbols. An unqualified HDF5 build with all
helper symbols also proves exact Python fallback without invoking the callback.
The architecture guard passed. Desktop packaging ran 23 tests with one existing
skip because the pinned parser source was not provisioned. The actual strict
macOS 14 arm64 helper build and signature check passed; dependencies remain
zlib and libSystem. These checks precede clean-source full-path timing and do not
qualify an installed package or the 50 ms target.


## Combined callback result and remaining layout cost

Clean commit `6b9959840c513a4dbfba9c4fe8f7d86543a341a3` passed all three ordinary
geometry/cursor oracles. Click-to-stroke was 63.4, 50.1 and 47.4 ms; the later
second-RAF observations were 86.8, 68.9 and 70.4 ms. The complete-display target
remained unmet. Its core gate passed in 17.55 seconds. The first pinned query
comparison flagged repeated-root and setup timings; it remains retained. An
unchanged matched repeat and the previous-483e00b comparison both passed with no
flags. Neither tree run opened HDF5. No reproducible query regression was
established, but the particular cause of the first flagged run is unproven.

A separate production-render attribution capture passed all exact oracles. The
first canvas bounds read contained 6.5–8.6 ms of document-root layout. Selected
component bodies used 1.3–2.1 ms and persistence at most 0.1 ms; those intervals
overlap layout and must not be added. No retinal icon body ran before dispatch.
The first focus replaces the 620px blank placeholder with the complete detail
UI and adds metadata controls; the plot itself is already fixed-height with
absolutely positioned canvases. The 704-object layout-tree count is not a claim
that every object was recalculated equally. Diagnostic timings are not ordinary
latency improvements. The external report is `focus-attribution-6b99598-run-v1`.

## Parallel reduction experiment

The external parallel-M4 prototype matched 3,300 independent valid cases and
130 rejection cases. Allocation failures and thread-start failures preserved
caller-output canaries and joined every started worker. All 320 timing rows are
retained in `parallel-m4-prototype/timing-matrix.json`. At width 751, one million
samples reduced in 3.603 ms serial versus 0.793 ms with eight workers, including
boundaries, allocation, thread startup, joins and publication. The 300k comparison
was 1.073 versus 0.515 ms with four workers; the 100k gain was only 0.059 ms.
These component results justify a 300k activation threshold, not a complete-path
performance claim. No raw data or display algorithm changes are involved.

The separately pinned zlib-ng 2.3.3 experiment passed its bounded checks but saved
only about 0.96 ms on an eight-worker fresh million-sample read. It is held out
of production because the gain does not justify an additional packaged decoder
dependency. Its failures, build repairs, corpus and all timing rows remain in
`zlib-ng-prototype`; no system library or source recording was replaced.


## Parallel reduction and empty prepared viewer follow-up

Clean 09a2e58 passed all 104 trace checks, 23 packaging checks (one existing
parser-source skip), architecture checks, the 17.834-second core suite and both
required million-epoch comparisons against the pinned and preceding 6b99598
baselines, without new review flags. Ordinary fresh million-sample observations
were 56.4/49.4/45.1 ms to stroke, 57.8/54.7/54.3 ms to first RAF and
67.8/72.2/70.9 ms to second RAF. A separate diagnostic confirmed parallel M4
reduction at 0.892/1.118/0.927 ms, compared with the earlier serial 3.6 ms.

An additional same-view sequence first displayed a distinct 300k dataset, then
used Next to a never-before-requested million-sample dataset in the same canvas.
All six stages passed exact point/index/statistics/Canvas and 20k cursor checks.
The million-sample stages reached stroke in 36.8/31.5/31.5 ms, first RAF in
47.9/36.0/39.2 ms, and second RAF in 65.2/52.6/53.8 ms. The reused outer runner
rejected six rows because it expects three; that failed receipt is retained.
A separate sequence receipt validates both three-row stages with the unchanged
validator and checks all six transitions. This does not replace fresh-view data.

The isolated empty-viewer candidate 8315179 reduced dispatch median from 14.3 to
8.5 ms. Fresh matched baseline/candidate observations, all in milliseconds:

| Source | Dispatch | HTTP | Stroke | First RAF | Second RAF |
| --- | --- | --- | --- | --- | --- |
| 09 baseline | 14.3 / 14.9 / 14.3 | 86.4 / 43.5 / 32.4 | 106.2 / 63.9 / 51.6 | 115.2 / 76.3 / 52.5 | 131.8 / 92.9 / 67.4 |
| 831 candidate | 8.5 / 8.5 / 9.0 | 32.7 / 26.2 / 27.4 | 45.8 / 39.2 / 41.2 | 54.1 / 52.2 / 51.4 | 70.6 / 68.8 / 68.0 |

The HTTP outlier remains in evidence. Backend code did not change between these
UI sources; do not attribute the entire stroke/frame improvement to the shell.
The complete under-50-ms target remains unmet. A separate single setup
observation was 193.4 versus 203.5 ms, descriptive only: UI construction moves
to setup and has not been shown to improve setup-plus-focus as a whole.

All 48 empty/focused matrix cases matched geometry, scroll extents, accessibility
and keyboard behavior; all 24 focused plot crops matched pixel-for-pixel and
passed independent scientific oracles. Strict whole-image comparison retained
a failure for four pixels outside plots. The same differences reproduced with
unchanged baseline code; the supplemental proof documents that raster variation,
without rewriting the strict failure. Early Pan-reset, pointer-capture, hidden
overflow and Tab-contaminated screenshot failures remain recorded. Final isolated
9672804 adds tested SelectionOverview precedence after the 8315179 browser runs.
Integrated-source evidence must be recorded separately.

These screenshots use a synthetic sine/cosine million-sample fixture with
deliberate extrema, not user recordings. The saved complete project inventory
contains 8,529 registered responses across five sources, with a maximum of
600,000 samples. Actual-recording native checks therefore have that separate
limit; traces are not padded or concatenated to claim real million-sample data.

A Darwin worker-QoS experiment was not integrated: ordinary ABBA medians were
17.746 versus 17.729 ms, with unchanged process CPU. All first calls, including
275.919/231.720-ms lazy-load observations, remain recorded. Diagnostic getters
confirmed requested QoS, not effective priority or core placement. Exact output,
unchanged caller QoS and forced setter-failure checks passed; no meaningful gain
or cause for the earlier live read spikes was established.

A bounded diagnostic on unchanged 09a2e58 reproduced a fresh-read spike on the
eleventh observation: HTTP 114 ms, server trace read 106.784 ms and native
extraction 93.624 ms. The ten preceding extractions were 14.411–18.266 ms.
Process CPU during extraction remained comparable (101.380 ms on the spike,
94.959–98.622 ms before it), while the request thread used only 0.366 ms.
This localizes that observation to the parallel extraction interval and shows
reduced aggregate parallel progress; it does not identify scheduler placement,
worker startup, allocation or a particular worker as the cause. Browser main-thread
tasks totaled 15.166 ms across the HTTP interval and do not explain the measured
server extraction delay. All eleven exact-output observations and the earlier
browser-launch failure remain in `read-spike-09a2e58-diagnostic-v2`. Per-worker
instrumentation is separate diagnostic work and is not production code.

The integrated empty-shell iteration passed all 1,273 frontend checks and the
complete architecture guard using the pinned arm64 Python environment. An earlier
run retained 20 architecture-parser failures: inherited PATH selected Intel
Anaconda Python 3.9.13, whose Node subprocess requested an unavailable x64
rolldown binding. Its other 1,253 checks passed; the corrected full run is
separate evidence. Core and matched million-query checks follow the clean commit.
