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
