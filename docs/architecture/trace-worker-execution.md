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

Global and frozen Workbench trace GETs accept opt-in `chunks=1..5`, retaining the
100,000-sample per-window bound (at most 500,000 total). A batch returns an envelope
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
JSON; errors remain JSON. The service's scientific batch reader is unchanged.
Only after its source/publication and HTTP scope guards close does the response
codec convert the already-admitted finite Python floats into little-endian IEEE754
binary64 samples, preserving negative zero and every sample bit. Binary batches
are nonempty (1–500,000 samples, 1–5 nonempty windows); ordinary JSON retains valid
empty EOF windows. Background execution and its payload budget remain unchanged.

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
