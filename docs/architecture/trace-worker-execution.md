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

Global metadata-off progressive warming uses two background requests. Live metadata
warming remains one; supplied/frozen request owners remain excluded from global
warming. Cache limits, demand pause and generation retirement are unchanged.

In the startup assembly, successful ProjectData activation publishes the worker
close callback into the shell gateway. Partial activation cleanup closes workers
before its database connection and native cleanup. The current assembly does not
include the imported-snapshot backend; mapped checks therefore use its retained
service/API and project-shell tests. The request-provider compatibility entry
isolates trace and metadata resources when explicitly supplied; scoped predicate
preference UI is outside this assembly.
