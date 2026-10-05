# Trace window presentation

Start with `ui/TraceViewer.jsx` for the bounded interactive viewer,
`ui/traceGeometry.js` for public pure geometry, and `traceReadContext.js` for
request/cache scope identity. All existing exports and viewer props remain public.

## Contract

Windows use safe integer bounds and at most 20,000 full-rate recorded samples.
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
bounded lifetime. The viewer never prefetches an entire recording. Backend trace
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
