# Trace window presentation

Start with `ui/TraceViewer.jsx` for the bounded interactive viewer,
`ui/traceGeometry.js` for public pure geometry, and `traceReadContext.js` for
request/cache scope identity. All existing exports and viewer props remain public.

## Contract

Display windows use safe integer bounds up to the stream length; each transport
read remains bounded to at most 20,000 full-rate recorded samples. The active viewer defaults to Whole epoch:
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
