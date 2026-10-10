# Trace window presentation

Start with `ui/TraceViewer.jsx` for the bounded interactive viewer,
`ui/traceGeometry.js` for public pure geometry, and `traceReadContext.js` for
request/cache scope identity. All existing exports and viewer props remain public.

## Contract

Sample windows and each transport read use safe integer bounds and at most
20,000 full-rate recorded samples. The active viewer defaults to Whole epoch:
`readWholeTrace.js` sequentially demand-reads exact chunks and publishes only the
complete trace after count, identity, source hash, rate and unit checks. Complete
arrays are never put in the shared cache. Cancellation and publication belong to
the existing useResource lifetime and supplied request owner. Sample is explicit;
its start/count preference survives epoch and layout changes, clamping to shorter
streams without replacing the preference. `traceViewPreference.jsx` validates the
presentation-only record and supplies it independently of request authority.
Protocol owns the shared Inspect/Workbench choice in its existing session; history
uses that protocol's latest choice. Search predicate stores its own choice in the
Explorer session, separately from disposable matching navigation and result
revisions. Standalone MatchingEpochs retains its session fallback. Missing/invalid preferences
start Whole epoch; standalone trace viewers retain a local choice while mounted.
The unified controls show response identity/rate/total, Whole/Sample, Start/Count,
window navigation and brief keyboard hints directly. Stream choices are inline
buttons; no dropdown or disclosure hides the window controls.
Full mode permits cursor inspection; zoom/pan/window controls require Sample.
Reset/Home returns to Whole epoch. Both modes show displayed and total counts.
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
