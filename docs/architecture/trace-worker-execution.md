# Background trace execution

The retained `WorkspaceService` owns source admission and scientific trace semantics.
`workspace_trace_workers.py` owns bounded process execution only. The exact legacy
service may capture a detached plan under the shared DB lock, execute the unchanged
`read_response_window` in a spawned child, then revalidate its parent-only witness
under that lock before publishing bytes. No connection, authority witness, lease,
request context or mutable service enters a child. Imported snapshot and custom
service/JSON owners retain their existing read paths.

Selected foreground reads stay inline. Detached JSON encoding occurs outside the
shared DB lock. Background HTTP reads carry `X-Disco-Trace-Priority: background`;
this is scheduling information, never authorization. The first successful background
read starts two workers lazily. Requests remain inline until both acknowledge
readiness. Failed dispatched work is not transparently resubmitted; later requests
can use the inline path after a broken pool is observed.

Plans are limited to 64 KiB and responses to 4 MiB. At most two physical jobs and
four waiting jobs exist; background waiters leave one queue slot for foreground
admission at the worker API. The HTTP foreground route bypasses that queue.
Cancellation retires queued consumers but retains a running physical slot until its
reply or observed exit. HTTP disconnect does not establish Python cancellation.
IPC replies require a valid job identity and typed envelope. Invalid/oversized
replies close the pipe so a child cannot remain blocked sending a body.

The parent witness fences service/project, publication/readiness, row and manifest
object identity and contents, and source signature. Children retain exact epoch,
response, parent, samples/rate/units, finite-value and source-signature checks.
Values are neither decimated nor resampled; exact integer JSON behavior and legitimate
empty end-of-stream windows remain unchanged. This boundary grants no source import,
export, database mutation or new scientific-authority capability.

Close stops admission, wakes waiters, drains physical reads, sends stop, and joins
owned public Process handles outside the DB lock. Native database stop and session
lease release follow confirmed worker exit. A timeout or uncertain start preserves
handles and reports an unconfirmed trace-worker stage for retry; it does not kill a
process or claim a clean shutdown. API and desktop finally paths also close workers.

`python/tests/test_trace_workers.py` exercises real spawned reads against owned
synthetic H5, exact Flask bytes, source/publication invalidation, HTTP fallback and
retirement, bounded admission, malformed IPC, cancellation, and close retry.
`test_workspace_api.py` checks that actual JSON encoding releases the DB lock.
These are source tests, not qualification of an assembled application.

Global progressive warming uses two background trace requests from admitted page
descriptors in both metadata modes. Live metadata loads only for the focused epoch
and cannot delay its independently requested trace. Supplied/frozen request owners
remain excluded from global warming; missing scoped descriptors still require
attested detail admission. Cache limits, demand pause and generation retirement are
unchanged.

In the startup assembly, successful ProjectData activation publishes the worker
close callback into the shell gateway. Partial activation cleanup closes workers
before its database connection and native cleanup. The current assembly does not
include the imported-snapshot backend; mapped checks therefore use its retained
service/API and project-shell tests. The request-provider compatibility entry
isolates trace and metadata resources when explicitly supplied; scoped predicate
preference UI is outside this assembly.

## Foreground exact-window batches

Global and frozen Workbench trace GETs accept opt-in `chunks=1..5` for JSON and
`chunks=1..10` for canonical binary reads, retaining the 100,000-sample per-window
bound (at most 500,000 JSON or 1,000,000 binary samples). A batch returns an envelope
with contiguous ordinary window DTOs and shared identity/count fields; frozen
responses carry their normal closing scope fences on the envelope. One source
plan pins the signature across all windows and is revalidated before publication.
No partial batch is published. The fast path admits only the captured canonical
trace reader; custom trace policies refuse the option. Requests without `chunks`
remain unchanged. Batches are foreground-only and execute under the caller's
existing read guards, bypassing the workers' 4 MiB payload budget; JSON encoding
runs after guard closure. This changes request granularity, never sample values,
ordering, decimation, scientific membership or source validation.

## Bounded foreground whole-trace batches

Whole-epoch canonical and frozen Workbench demand can request up to five exact
100,000-sample windows in one foreground response. The service captures one source
plan, reads each bounded interval without filtering or resampling, then validates
the source and publication witness before returning any windows. Custom trace
reader overrides refuse batch admission. Workbench additionally performs its
ordinary fresh opening and closing candidate checks around the entire batch;
no candidate, pending-member or source authority is cached across requests.
JSON encoding occurs after those checks, outside the shared database lock.
Background worker response limits and imported snapshot endpoints are unchanged.

The frontend checks the outer extent, source, rate, units and frozen candidate
token, then every ordered contiguous window and sample count. Publication remains
complete-only and cancellation retires later responses. An older endpoint returning
one ordinary window to the opt-in request triggers ordinary remaining reads; it
cannot be mistaken for a complete batch. Requests without the option retain their
previous response shape. The adoption review covered source/publication closing
checks, override refusal, exact envelope admission and legacy fallback. Existing
observer and method-capture syntax/targets remain unchanged; the catalog refreshes
only their reviewed owner-source witnesses. Scoped backend and frontend regressions
cover changed sources, late cancellation, missing/corrupt windows and all samples
of a 300,000-sample trace. These checks do not by themselves qualify installed
application latency or release readiness.

## Opt-in binary64 foreground transport

An explicit `Accept: application/vnd.disco.trace-f64le.v1` on a foreground batch
request selects the same Content-Type. Default and unsupported Accept values keep
JSON; errors remain JSON. Negotiation is captured once before reading. The
canonical binary batch retains detached finite float64 arrays and shares one H5
handle across its bounded windows. Every window checks count, all recorded units,
finiteness and source signature; H5 closure checks the signature again, followed
by the unchanged source/publication and HTTP scope guards. Fixed byte/unicode
units use exact vector equality; other representations retain decoded validation.
Custom batch/window readers retain their legacy call/representation policy.
Only after closing guards succeed does the codec encode little-endian IEEE754
binary64 bytes, preserving negative zero and every sample bit. It accepts only
one-dimensional finite float64 arrays or existing finite Python-float lists;
non-native byte order and strided arrays are serialized exactly. Binary batches
are nonempty (1–1,000,000 samples, 1–10 nonempty windows); valid empty EOF windows
remain JSON even with binary Accept. Background execution and its payload budget
remain unchanged. Canonical binary requests permit ten 100,000-sample windows
under one H5 handle; JSON and custom readers retain the five-window limit.

The body begins with ASCII `DTF1` followed by a little-endian uint32 UTF-8 JSON
header length. The header retains every envelope/window metadata and scope field,
removes only each window's `values`, and adds `byte_offset` and `byte_length`
relative to the sample payload. Zero padding aligns the payload to eight bytes.
The header is at most 64 KiB; the payload is exactly eight times the admitted sample
count, contiguous and without trailing bytes. Custom JSON providers still encode
the header metadata. No float32 conversion, resampling, compression or lossy
fallback occurs. Unsupported requests stay on existing JSON; malformed binary is
an error, never silently interpreted as JSON. The client independently validates
identity, scope, source, rate/units, counts, offsets, padding, length and finiteness.

`X-Disco-Trace-Timing: 1` optionally adds `Server-Timing` with four fixed elapsed
wall-clock stages: `trace_open` (guard entry, context and frozen adapter),
`trace_read` (batch source admission, sample reads and source closing witness),
`trace_close` (final candidate context and guard closure), and `trace_encode`.
Global routes use lock entry/read/exit for the first three. Values contain only
milliseconds, no scientific metadata. Ordinary requests do not read these clocks.
These elapsed groups do not claim CPU attribution or include browser/network time.

## Optional bounded native gzip64 decoding

Canonical binary batches may use `workspace_trace_native.read_native_samples`
inside the same H5/source/publication guards. Admission requires a requested span
of at least 100,000 samples, a one-dimensional dataset of at most 1,000,000 samples,
exact packed `quantity:<f8, units:S10` records, 64-record chunks, sole DEFLATE filter,
sec2 file driver, and dense chunks with no skipped filters. This initial lower
bound avoids indexing an entire large stream for a tiny slice; it is not a
universal measured crossover. Other layouts, endian variants, sparse chunks,
filter masks, unavailable helpers or occupied native capacity retain ordinary H5.
No sample data is cached between reads. Exact H5 datatype equality admits ASCII
NULLPAD or NULLTERM unit strings only. For NULLTERM, the helper zeros bytes after
the first NUL exactly as H5 converts to NumPy NULLPAD strings; full-width strings
and quantity bits remain unchanged. UTF-8/padded/custom H5 types retain generic H5.

HDF5 resolves sealed paths and chunk metadata on the caller thread. Physical
ranges must not overlap and must remain within the source file. Reads coalesce
only up to 4 MiB per span with gaps no larger than 64 KiB, and at most 32 MiB total.
A duplicate of the admitted H5 sec2 descriptor supplies `pread`; its source stat
must match before and after the read. Logical chunk order is independent of file
placement. A tail chunk inflates its full 1,152 bytes, then requested sample bounds
exclude padding. Every requested unit and finite value remains checked, either in the fused native
extraction or the generic per-window reader. Count/source checks and final
publication/frozen-scope checks remain required.

`desktop/native/trace_inflate.c` exposes ABI 4 and uses system zlib,
pthreads and bounded memory/math operations, never HDF5 or filesystem APIs. At most one native operation
per Python process uses at most eight threads, capped by available logical CPUs.
Requests below 500,000 samples use at most four. Count is capped at 15,625 chunks,
compound output at 18,000,000 bytes or fused float64 output at 8,000,000 bytes,
input at 32 MiB; compressed buffers may briefly coexist
with their coalesced pieces during assembly. Each worker initializes one zlib
decoder and resets it between independent chunks. Every chunk must end with
`Z_STREAM_END`, consume its entire input and produce exactly 1,152 bytes.
Decoder state is released on success or failure; worker joins precede publication. Corruption, trailing compressed
bytes, truncation, malformed chunk locations and source changes fail the read;
no partial samples or successful fallback are published after those failures.

The optional helper is loaded from `RIEKE_DESKTOP_RUNTIME/native/` in a packaged
runtime, or the repository's `.rieke-runtime/trace-native/` development build.
There is no launch-time compilation or dependency download. Packaging owns its
compiler/platform flags, signature, integrity manifest and ABI verification.
Owned `test_trace_native` fixtures compile the C helper on macOS/Linux and exercise
actual decoding, tails, fragmentation, skipped filters, sparse allocation,
unsupported layouts, malformed bytes, bounds, source changes and missing-helper
fallback. Those checks do not establish installed-app latency or release readiness.


## Prepared display views

A prepared trace view is a server-owned, display-only snapshot of exact pending
or selected membership. It is issued during the existing checked Workbench view
preparation. It is not a receipt for current draft, annotation, binding or merge
state. Later tag or review changes do not rewrite this captured membership.
Mutation endpoints retain their current authority and never accept the display
token as permission to save or accept changes.

`workspace_trace_views.py` owns bounded immutable member/source witnesses and an
opaque session-local token. Reads use `/trace-views/<token>/epochs/<epoch>/trace`.
They check the same project, owner and source publication, exact selected member,
sealed single-epoch row/fingerprint, stream identity and source file before and
after reading. They do not acquire the catalog/annotation lock, run a query,
rebuild a cohort, or read tags. Metadata publication replacement revokes old
views and releases their retained publication roots. Expired, mismatched and
unsupported capabilities fail closed; legacy/custom callers keep their existing
checked route rather than being admitted by object identity alone.

The renderer keeps `trace_read_context` separate from tree and mutation context.
The dedicated token identifies trace request and paint lifetimes independently
of tag revisions; the response envelope and every window must echo that exact
context. Selected pages require their own captured subset, never a broader
pending-view capability. Actual epoch, source, stream or display-publication
changes still replace the trace lifetime. Tag reads and saves do not grant or
revoke a historical display capability.


### Whole-view display geometry

The prepared `/display` endpoint has a distinct `application/vnd.disco.trace-m4le.v1`
representation. It accepts only a complete stream of at most one million samples,
a finite physical plot width in `(0, 16384]`, and the explicit
`first-last-extrema-v1` algorithm. The same exact source/units/finite checks run
before reduction, and the display source witness closes after reduction. No tag,
draft or current membership read is added to the click path.

For each screen column, reduction preserves the first, earliest minimum, earliest
maximum and last original sample indices in sorted unique order. The floating
bin expression matches the existing browser renderer without rounding the physical
width. Fused extraction checks all requested units and finite values while copying
original float64 bits. Geometry computes full-stream extrema, including signed-zero
ties. Unsupported helper availability uses a bounded NumPy reducer; source or native
corruption never silently retries. The representation is explicitly sparse display
geometry, never a raw million-sample array or a claim of `decimated: false`.

Wire format is `DTM1`, uint32-LE JSON header length, JSON and zero padding to eight
bytes, uint32-LE original indices, zero padding to eight bytes, and binary64-LE
original point values. Header identity includes the exact prepared context,
source/epoch/stream, sample rate, units, raw start/count, physical width, point count
and full-stream finite extrema/counts. The browser admits this separately from raw
sample decoding and draws the supplied ordered points without reducing them again.
Width, DPR, owner, source or epoch changes retire incompatible geometry.

Whole automatic-amplitude views can use geometry. Raw zoom and manually clipped
amplitude preserve their exact sample path. An exact cursor uses a bounded demand
sample window and reports pending while its value is unavailable; it never substitutes
an adjacent geometry point. No full raw request runs automatically behind a geometry
read. Only the explicit `trace_geometry_unavailable` response permits ordinary raw
fallback; identity, source, malformed response and lifetime failures fail closed.

The initial native prototype matched all 14 independent index/value/statistics
cases and 46 valid Canvas raster comparisons across Light/Dark and DPR 1/2.
These establish equivalence to the existing whole-view M4 renderer, not universal
pixel equivalence to a full raw polyline. Full application and package measurements
remain separately attributed to the implementation they execute.

Desktop startup starts one isolated, standard-library-only child after runtime
validation to map the packaged helper and check ABI 4 symbols. It reads no
samples and grants no trace authority. A five-second deadline and bounded
shutdown cleanup own the child; missing helpers or probe failures retain the
ordinary optional-helper path. Actual reads independently load and validate
the helper. `test_trace_native_initialization` checks ordering, one-shot
startup, isolation, deadline, and normal/error cleanup.
