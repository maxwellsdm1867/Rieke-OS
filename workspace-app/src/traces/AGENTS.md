# Trace window presentation

Start with `ui/TraceViewer.jsx` for the bounded interactive viewer,
`ui/traceGeometry.js` for public pure geometry, and `traceReadContext.js` for
request/cache scope identity. All existing exports and viewer props remain public.

## Contract

Display windows use safe integer bounds up to the stream length. Whole-epoch
demand uses canonical/frozen windows of at most 100,000 full-rate samples,
optionally batched up to ten windows in one negotiated binary foreground HTTP request. Each
response envelope and contiguous window must match the exact requested extent,
source, rate, units and frozen candidate token before any result publishes.
An older endpoint returning one ordinary window to the opt-in request is admitted
only as that one window; remaining reads use the ordinary contract. Partial
Sample windows and imported snapshot endpoints
retain the 20,000-sample transport bound. No samples are omitted or resampled.
The active viewer defaults to Whole epoch:
`readWholeTrace.js` sequentially demand-reads exact chunks and publishes only the
complete trace after count, identity, source hash, rate and unit checks. Complete
arrays are never put in the shared cache. Cancellation and publication belong to
the existing useResource lifetime and supplied request owner. Direct Sample chooses start 0/count 200;
its subsequent start/count preference survives epoch and layout changes, clamping to shorter
streams without replacing the preference. `traceViewPreference.jsx` validates the
presentation-only record and supplies it independently of request authority.
Protocol owns the shared Inspect/Workbench choice in its existing session; history
uses that protocol's latest choice. Search predicate stores its own choice in the
Explorer session, separately from disposable matching navigation and result
revisions. Standalone MatchingEpochs retains its session fallback. Missing/invalid preferences
start Whole epoch; standalone trace viewers retain a local choice while mounted.
The unified controls show response identity/rate/total, Whole/Sample and Zoom/Pan
in one wrapping control row. Start/Count, Apply and previous/next window arrows
appear only in Sample mode. Displayed time/sample
range and brief keyboard hints sit below the plot. Stream choices are inline
buttons; no dropdown or disclosure hides the window controls.
Whole mode permits cursor inspection and zoom-in. The magnifying-glass Zoom-in button in Whole mode only arms drag selection.
Keyboard zoom or releasing a box selection enters Sample mode, shows its window controls and retains the
exact selected range, including ranges larger than 20,000 samples. Pan is unavailable at full extent;
Sample windows support pan with unchanged width and zoom-out up to stream length.
Box zoom selects both time and response bounds; the optional validated amplitude
range is presentation-only and follows the existing view preference. Pan moves
both axes continuously while dragging, with fixed time and response spans.
Pan uses the original grab point throughout the gesture and shows no zoom box. Whole resets both axes. Explicit
start/stop sample bounds are inclusive and remain visible below the plot.
Zoom only arms drag selection; releasing a drag chooses the displayed window.
The current resource retains its loaded interval while viewport bounds remain
inside it, so zoom/pan/Whole perform no additional reads after a full load.
Leaving the loaded interval demand-reads the requested range in bounded chunks.
Epoch, stream, source, revision and request-owner changes retire this reuse. Whole epoch and Reset/Home
return to the complete trace and hide manual window controls. Both modes show
displayed and total counts. No separate hidden zoom state exists in Whole mode.
Pan and zoom clamp to recording bounds. Time is seconds using the positive finite
sample rate; the span is `(count - 1) / sampleRate`, including both actual endpoint
samples. Only finite numeric samples determine extents. Null/nonfinite samples
break plotted segments; never interpolate or convert them to zero. Amplitude units
remain recorded units and ticks only format display.

Epoch and stream UUIDs remain exact. Frozen candidate roots and scope revisions
participate in both request and cache identity; invalid frozen context refuses
rather than falling back globally. No stream produces no request. Invalid rate
produces no time range and no finite samples produces no extent. Retrieval errors
remain visible/retryable.

The shared resource/cache owner retains freshness, cancellation, eviction and
bounded lifetime. The viewer never prefetches an entire recording; full-stream reads are demand
loads only for the currently inspected epoch. Memory and paint work for Whole
epoch grow with stream length; native large-recording performance is unqualified. Backend trace
reads establish source ownership/provenance; geometry does not qualify bytes or
calibration. No scientific mutation belongs here.

## Factoring decision

Geometry/request identity are in-process. Trace retrieval is remote but owned,
through existing resource adapters, with shared cache lifecycle kept outside.
KEEP those separate owners: combining them would make geometry/cache consumers
learn React viewport state or transfer cache lifetime into one view. Deleting the
geometry entry would repeat bounds and missing-sample rules in viewer/cache callers.
This grouping improves locality and progressive discovery, not behavioral depth;
no wrapper or reduced-capability facade is introduced.

From `workspace-app`, run the public executable examples:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/traces/traceGeometry.test.js src/traceReadContext.test.js src/epochResourceLifecycle.test.js
```

Geometry examples cover the full-rate cap, inclusive time, finite segmentation and
ticks. Request-context examples preserve candidate scope. The context test remains
at its historical benchmark-bound path; resource lifetime tests remain cross-owner.
These tests do not establish browser drawing/paint or native H5 read performance.
Ledger: `trace-window-presentation`, with `epoch-snapshot-cache` a separate owner.

## Maintenance and evidence

Use the named file entries directly; there is no barrel, compatibility forwarding
module, or newly private export. The interface includes accepted types, identity,
ordering, freshness, errors and lifetime; a lower export count is not the goal.
The executable examples above use the same public seam as callers. Preserve the
original tests; this organization does not replace them with implementation tests.

Read this guide and the relevant entry before editing. Agree on changes to
scientific meaning, authority, request identity or lifetime before implementation.
Keep local changes within those contracts, run the scoped examples and retained
composition tests, and obtain independent source review. The integration owner
updates the existing catalog, ledger and path companion and runs the coordinated
import/build checks. Benchmark links in the ledger are historical/indirect;
relocation establishes neither new performance nor native qualification. Browser
layout/paint, native data reads and full backend qualification remain separate.

The navigation assembly retains `traceResponseMatches` as a public read-context
comparison helper. TraceViewer obtains explicit supplied request/context owners
from `../workspaceRequest.js`; supplied contexts cannot borrow global cache or
trace prefetch. Default legacy rendering remains supported. The viewport resize
paint runs before display, retaining exact samples and existing geometry.

Canonical short trace reads use `requestTraceWindow` from the existing `api.js`
resource adapter. Source/descriptor checks, shared cache lookup, generation tokens
and fresh-response admission stay with that resource owner; the viewer supplies
its epoch, stream, exact window and cache revision. Scoped/imported reads still
use their supplied owner and never enter the global cache. This preserves the
existing prefetch keys and rejects stale warm or in-flight responses without
making presentation depend directly on `resourceCache.js`.

For a worked regression and dependency example, see the
[predicate trace and cache boundary note](../../../docs/dev/predicate-trace-boundary.md).
Run the architecture guard when adding cross-module imports, before packaging.

An unchanged Activity reveal preserves unfinished sample-window entry text. Epoch, stream or applied window changes synchronize the inputs to the new bounded window. Trace read/cancellation authority remains independent of those text fields.

The existing trace preference checkpoint also retains one last explicit
`responseSelection: {epoch_uuid, stream_uuid}` pair. Both strings are bounded;
normalization strips all other fields. Restore uses it only when the current
epoch and an indexed response descriptor match exactly, including when descriptors
arrive after the component. Missing/different identities fall back to the first
current response; device labels never establish identity. A mounted viewer keeps
its own current selection. Window, Whole and zoom changes preserve the pair.
This is one presentation preference, not a per-epoch history or read capability.
`responsePreferenceRetention.test.js` covers remount, hide/reveal, delayed
descriptors and mismatched identities; native dual-channel/H5 checks are separate.


Canonical/frozen foreground batches optionally negotiate
`application/vnd.disco.trace-f64le.v1`. `traceBinary.js` checks the DTF1/versioned
framing, bounded UTF-8 metadata, zero alignment padding, exact payload length,
ordered contiguous windows and finite binary64 values. The normal whole-trace
owner still validates every scientific identity and frozen authority field.
Malformed binary never falls back to JSON. An ordinary application/json response
from an older endpoint retains the existing decoder and legacy window fallback.
Imported snapshot reads and custom scientific authority remain unchanged.

One admitted binary batch supplies contiguous Float64Array views without another
sample copy. Multiple binary batches copy once into a preallocated Float64Array;
mixed/JSON batches preserve null gaps in an ordinary array. Viewport slices of
typed samples use subarray views. No trace sample is omitted, resampled or coerced
from null to zero. Complete arrays remain outside the shared epoch cache. The
binary frame is at most 1,000,000 samples and a 64 KiB metadata header; request and
cancellation bounds are unchanged. `traceBinary.test.js` exercises framing faults,
bit-exact finite values and signed zero, transport fallback, source/scope checks,
zero-copy admission, multiple batches and cancellation. Binary transport does not change recorded sample geometry; the separate display
policy follows below.


Dense display rendering is explicitly separate from scientific sample storage.
`traceDisplaySegments(values, physicalWidth)` visits the original samples once and
returns selected original indices: first, last, minimum and maximum in each
physical plot column, unique and in time order. Every nonfinite/missing sample
ends a connected segment; isolated samples and finite segment endpoints remain.
The plotted column width is CSS plot width multiplied by device pixel ratio.
Windows at or below four samples per physical column retain every sample.
Resize, DPR and viewport changes recompute display indices; colors, axes and
coordinates retain their existing geometry. Original arrays, HTTP requests,
recorded values, exact sample cursor and zoom navigation are unchanged. This is
an authorized display approximation, never a filtered or resampled recording.
The response heading tooltip and cursor help explain screen-resolution display
with exact cursor values. `traceGeometry.test.js` and `traceDisplayLifecycle.test.js`
cover million-sample spikes, endpoints, ordered gaps, physical-pixel bounds,
resize/DPR, zoomed all-sample drawing and full-precision cursor readout. Independent
pixel comparisons remain separate from these geometry and drawing-call checks.

The binary decoder fuses its mandatory finite-value validation with exact
min/max/count statistics. `traceStatistics.js` associates those facts only with
locally decoded sample views and the exact admitted arrays assembled from them;
wire fields never grant statistics authority. This is weak metadata attached to
the response lifetime, not a cross-navigation sample cache. Trace owners do not
mutate decoded samples. Arbitrary/custom Float64Array and JSON producers receive
no persistent statistics and retain ordinary missing/nonfinite handling.
The viewer obtains one statistics result for its visible sample view and reuses
it for axes and missing-count presentation. Partial viewport slices obtain their
own statistics; whole-stream extrema must never substitute for a zoomed range.
Exact raw values, gap breaks, source/scope admission and full-precision cursor
inspection are unchanged. No background reads or prefetch are added.

Manual amplitude clipping is an exact-display exception: if the chosen response
range excludes any finite sample in the current viewport, the painter submits
every original finite sample, with the original gap breaks and isolated points.
The decision uses raw viewport min/max, not padded axes or whole-stream extrema.
Line joins and scientific data stay unchanged. Auto extent and nonclipping
manual ranges retain the existing physical-pixel first/last/min/max policy.
This prioritizes waveform appearance over paint speed when clipping can amplify
subpixel interpolation or apparent-density differences. Exact clipped views can
be slower, especially at large sample counts; no speed claim overrides this
fidelity rule. See the fused-statistics QC audit for raw-raster comparisons.

Prepared Workbench display capabilities use a separate strict `prepared_display`
context and `/trace-views/<token>/epochs/<epoch>/trace` route. They authorize
historical raw display only. The envelope and every window echo the exact context
and must not claim candidate scope authority. Source, stream, rate, units and
window admission remain exact. Display identity includes the captured token and
source, excluding annotation revision; owner changes still retire all reads.
No prepared capability enters tree, tag or inclusion mutations. Unsupported
backends omit the field and retain existing routes; malformed capabilities fail
closed. Selected views wait for their own page capability, never their parent's.

`usePreparedTraceRead.js` owns only the mounted prepared-display request lifetime.
It dispatches synchronously from a layout effect, with loading derived from the
read identity rather than a pre-dispatch state update. Publication requires exact
path, captured revision, reload nonce, request-port object, request function and
a non-aborted request signal;
cleanup aborts the transport and rejects late completions even if it ignores
cancellation. It has no sample cache, prefetch, membership or mutation authority.
The ordinary `useResource` implementation and legacy scheduling are unchanged.
`preparedTraceRead.test.js` exercises A-B-A replacement, reload, owner replacement,
abort, late success/error and unavailable authority. The real canvas lifecycle
also covers held tag refresh and cross-epoch curation pairing. Timing evidence is
qualified in `docs/dev/prepared-trace-request-scheduling-2026-10-15.md`.

## Prepared whole-epoch display geometry

`traceDisplayGeometry.js` owns the distinct negotiated DTM1 representation
(`application/vnd.disco.trace-m4le.v1`), separate from full-rate DTF1 samples.
Only prepared whole/automatic-amplitude views with at most one million samples,
physical width in (0, 16384], and count > 4 ceil(width) request geometry. Exact
floating width is `(max(1, canvas CSS width - 103)) * DPR`; it is never rounded.
The response echoes the complete prepared context and exact source/stream/rate/
units/count/width. Bounded aligned binary framing, original ordered uint32 indices,
finite binary64 point values, full-stream statistics and exact body length are
validated. Each physical bin must include its original first/last indices and at
most four points; boundaries use binary search over the exact reduction formula.
The original point bits are retained. Wire statistics remain separate from raw
sample statistics and must agree with extrema among emitted points.

The painter has an explicit admitted geometry branch using raw sample count for
coordinates and the supplied original indices. It performs no second reduction.
A geometry response never masquerades as a raw values array. Manual amplitude,
clipping and sample/zoom views retain the exact raw route. Only typed HTTP 409
`trace_geometry_unavailable` permits the same prepared raw fallback; malformed
geometry, wrong representation or authority errors fail closed. Unsupported
geometry retains its single raw interval across resize, scoped to the current
source/context/request owner. No automatic background raw trace is loaded.

`useTraceViewport.js` measures the mounted canvas and observes CSS size and
resolution changes, rearming the DPR media query. Width changes retire geometry
reads. The painter independently clears/refuses old-width geometry before a new
state commit, so observer delivery order cannot paint the wrong bins.

`useExactTraceCursor.js` owns at most one 20k raw tile and one in-flight cursor
request. Hover waits 50 ms and coalesces to the latest tile; explicit cursor input
or click dispatches immediately or joins the same tile. Returning to a loaded
sample cancels delayed work elsewhere. Pending/unavailable values are explicit,
never interpolated, guessed or mislabeled as missing. Owner/source changes and
replacement dispatch abort old requests; old index intents cannot publish after
newer ones. Raw sample views use their existing local exact interval directly.
`traceDisplayGeometry.test.js`, `exactTraceCursor.test.js` and
`traceGeometryLifecycle.test.js` cover framing/negotiation, owner and cursor races,
no hidden whole reads, raw fallback, actual painting, resize and DPR-only changes.
The external native/JS/RGBA oracle remains separate performance/fidelity evidence.
