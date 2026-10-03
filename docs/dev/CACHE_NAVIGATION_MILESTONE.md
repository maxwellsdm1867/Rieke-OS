# Bounded GlobalSearch cache pilot

Base: `3d9f15fffb8c36e24b799656b073fec45552c2cf`. Branch: `codex/cache-research-20261003`. This is an isolated, one-view pilot. Implementation milestone `a616055d2868fea297666c611016eaf1a1079f0b` passed independent source review and the subsequently granted bounded native qualification below. No push, deployment, scientific mutation, authority caching or broader page cache was performed.

## Behavior and ownership

At the checkpoint, GlobalSearch retained its query but fetched it again after every dialog reopen. The App shell now owns a disposable search read cache above the dialog's open/closed lifetime. A fresh identical search renders its retained result immediately without another GET. The 180ms debounce remains for uncached input.

Only GET `/search?q=…&limit=20` is allowlisted. Other endpoints, candidates, epochs, mutations and bodies fail closed; there is no generic fallback. Existing epoch/detail/trace caches, destination validation, selection and mutation receipts are untouched. QC analyses, other route caches, hidden editor retention, adaptive indexing and JSON import remain outside this pilot.

Version 1 identity includes exact project UUID, renderer-owned activation (including current project path/open identity), actor namespace, resource, exact typed search request and local workspace revision. Existing App revision changes invalidate reuse after known imports, source changes and annotations. Object key order is canonicalized; array order, types, null/missing and negative zero remain distinct. Non-JSON identity/payload values fail closed. Retained response snapshots are recursively frozen and preserve negative zero.

Project UUID alone is insufficient: same UUID under a different open identity retires reads, and a newly mounted owner cannot inherit the previous owner's results. Selected author UUIDs and explicit browse-only/loading/preference-unavailable namespaces are separate. Search remains available for browsing while optional author preferences load or fail; every such transition revokes previous results. These provisional namespaces convey no scientific authority.

Focus, online, pageshow, visible visibility changes and desktop status transitions retire the activation synchronously, cancel subscribers, and revoke captured navigation callbacks before rerender. The current backend `/api/health` exposes project UUID but no session-incarnation token; the desktop bridge exposes lifecycle status, not a backend generation receipt. This activation is therefore a client fence. Silent backend replacement with no observable lifecycle/reconnect event can remain undetected until the 30s freshness limit or next read; it must not be treated as a server dependency witness for mutable scientific pages.

## Freshness, failure safety and bounds

Defaults are 16 retained identities, 32 MiB estimated UTF-8 payload + key/envelope bytes, 30s freshness, 5min retention and at most four reserved/dispatched transports. Byte accounting bounds retained serialized data; it does not measure or cap total JS heap, rendering allocations, response parsing or RSS.

Compatible stale results remain visible while refreshing, with a clear notice and disabled navigation. Ordinary failure keeps only compatible previous content and an explicit Retry. Successful empty results replace old content. 409 clears retained reads and displayed rows, exposes the error and requires a new explicit intent; it does not automatically retry. Freshness expiration while the dialog is open starts revalidation and makes previous content inert. Query/revision/project/actor/activation changes hide incompatible results immediately. Captured callbacks check current identity, generation, content and elapsed freshness even when invoked after their render becomes obsolete.

Exact pending reads coalesce with separate subscriber cancellation. The last departing subscriber aborts; ignored aborts cannot publish late data. Canceled/retired transports continue counting toward the admission bound until they settle. Four genuinely stuck, abort-ignoring loaders consequently stop new reads with a retryable capacity error instead of launching unbounded work. Successful oversized replacements evict the predecessor before bypassing retention. Closing clears dialog-local response state, so an oversized result cannot be reused on reopen.

Aggregate diagnostics contain counters and entry/estimated-byte/in-flight counts only. No queries, scientific identifiers, paths, payloads or persistent telemetry are emitted.

## Review fixes and evidence

The three early review findings are addressed with targeted regressions:

1. A retained A followed by oversized successful B evicts A; reopening dispatches a new read rather than resurrecting A. Covered both in the cache core and mounted adapter.
2. Held abort-ignoring loaders stay counted across cancel and activation changes until settlement. Repeated retirement cannot exceed the configured transport limit.
3. Predicate negative zero survives delivery and reuse. The snapshot clone no longer roundtrips through JSON parsing.

The frozen checkpoint component is byte-identical to the base commit (SHA-1 `1a079ca4a0e9f35652603ced4eac7c053abc3119`). Both versions use the same isolated, source-mounted one-cell fake-backend fixture:

| Synthetic interaction | Checkpoint | Pilot |
| --- | ---: | ---: |
| Initial query GETs | 1 | 1 |
| Additional GETs on fresh close/reopen | 1 | 0 |
| Total initial + reopen GETs | 2 | 1 |
| Retained result on first React reopen render | No | Yes |

This is a 50% reduction in total requests for that two-open fixture, and zero additional warm reopen requests. It is not a painted latency, native navigation, database-query-count or memory-plateau measurement.

Focused command: `node --test src/pageReadCache.test.js src/globalSearchBaseline.test.js src/globalSearchCache.test.js src/navigationReadStrictMode.test.js` — **25 passed**. Coverage includes allowlisting, typed identity, LRU/byte/retention limits, independent cancellation, late completion, A→B→A reversal, revision reversal, same entity/project UUID under distinct opens, real App owner profile loading/error/browse/author transitions, mounted expiry, reconnect/focus/pageshow, desktop recovery/running transitions, 409 without retry, oversize replacement, and ReactDOM StrictMode effect replay/remount/listener cleanup.

Final full regression: `npm test` — **601 passed, 0 failed**, including existing epoch cache, mutation/annotation authority, selection, cancellation and mounted workflow regressions. Final `npm run build` — **passed**. Local receipts: `/tmp/disco-cache-final-tests-20261003.log` and `/tmp/disco-cache-final-build-20261003.log`. The output bundle is approximately 808 kB before gzip; the existing >500 kB chunk warning remains. No latency inference is made from build/test duration.

The first full run exposed an App test harness that stubbed the newly imported provider; that harness now uses the real provider and supplies window listener methods. The default sandbox also blocked the existing Workbench rendering test's synthetic `review-evidence/workbench-component.html` write; an authorized checkout-local run resolved that environment limitation. Generated review evidence was removed after verification. Build output is generated locally only, with no deployment.

## Native qualification still required

Before making latency or memory claims, obtain an exclusive slot for the parent's existing packaged/native fixture; do not duplicate its H5s or operate services concurrently. Measure cold/warm dialog opens, first useful paint and input responsiveness with recorded project/backend identity, request counts, query cost and errors. Repeat close/reopen and query/project/actor changes long enough to observe retained entries/bytes and heap/RSS settling. Exercise suspended/resumed desktop and backend recovery, real focus and keyboard behavior, and destination validation after source/author changes. Preserve failure/conflict correctness while measuring.

The parent subsequently granted an exclusive slot. The actual checkpoint/pilot components were compared in an owned Electron/profile diagnostic shell against an isolated native API/MySQL clone; see [CACHE_NAVIGATION_NATIVE_QUALIFICATION.md](CACHE_NAVIGATION_NATIVE_QUALIFICATION.md) and its sanitized receipt. Twenty fresh reopens made 20 search GETs at the checkpoint and zero in the pilot; observed useful-frame p95 was 403.9ms versus 8.0ms under the explicitly limited RAF/DOM method. Keyboard, fresh destination GETs, controlled failures, real mounted expiry and actual owned API recovery passed. One hundred additional reopens retained 16 entries / 12,678 estimated bytes; short memory observations do not establish a production plateau. Granted source files and scientific tables were unchanged; owned processes/ports stopped cleanly.

The unobserved-backend test confirmed that locally fresh cached rows remain clickable until expiry or an observed lifecycle/reconnect event. Client response time is not a server-generation witness. Cached selection issued a fresh destination GET and failed while the backend was down. This is acceptable only for navigation intent with separate destination reads/mutation authority, never membership or decision caching without server witnesses.

The proposed all-page warm p95 ≤100ms goal remains unqualified. Full packaged App lifecycle, a real second-project switch, large payloads, long-duration memory and compositor/INP measurements remain separate qualification work. Broader page caching and adaptive indexing wait for the parent's evidence review.
