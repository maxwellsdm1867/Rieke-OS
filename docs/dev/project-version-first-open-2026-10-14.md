# First project open after a version change

2026-10-14 UTC (October 13 local). The user identified a delay when first opening
an existing project in a new Disco version. This audit uses only owned disposable
projects, staged builds and an isolated HOME/profile. The installed app and real
scientific projects are unchanged.

The compatibility fix now preserves the original sealed cache across the tested
upgrade. It does **not** demonstrate a cold-start speedup: the first upgraded open
still took about 63 seconds, and a same-version fresh-stage experiment reproduced
the long delay without a cache rebuild.

## Completed pre-change native experiment

The complete four-process sequence ran old `add33d153ae8f533d5c4a68c50690764323c4336`
(published 0.1.12 testing prerelease) to candidate `79449da`. The candidate's production bytes match
the previously qualified local UI candidate `27a0117`; intervening commits fix
only this experiment's driver. The same owned project, profile, paths, source
records and cache remain in place throughout old populate → old reopen → new
first open → new reopen. Each process quits normally before the next starts.

| Phase | Launch to data ready | Launch to usable Overview | Source projection | Native/typed indexes |
| --- | ---: | ---: | --- | --- |
| Old reopen | 12.487 s | 12.740 s | 1 hit, 0 rebuilds | Reopened |
| First upgraded open | 60.676 s | 61.052 s | 0 hits, 1 rebuild | Built new generation |
| New reopen | 11.946 s | 12.257 s | 1 hit, 0 rebuilds | Reopened same new generation |

The new reopen displayed its saved overview at 2.324 s; that display was inert
until canonical data became ready. All four phases verified exact 63-epoch and
2-cell membership, protocol identity/counts, unchanged original/managed H5 and
imported-metadata hashes, usable active Overview and ordinary exit 0. No page,
observer or unexpected HTTP errors were recorded. This tiny fixture does not
represent a large real project's timing or installed-app qualification.

Raw [receipt](../../benchmarks/results/ui-version-first-open-79449da-prefixed/receipt.json)
and [summary](../../benchmarks/results/ui-version-first-open-79449da-prefixed/summary.json)
bind the exact stages, harness, cache generations/files, inputs and observations.
These local evidence directories are ignored by Git; they remain available in
the investigation checkout. Observer coverage begins after Electron launch
resolves, so the request log does not claim complete early-bootstrap coverage.

Earlier attempts remain failed evidence. `efaa552` waited for usability while the
known author dialog was open. `c908c84` exposed a hidden initial Overview preceding
the visible restored Overview in the retained DOM. A separate forward-only native
diagnosis proved both nodes and preserved exact data on same-version reopen.
`65ea588` passed the upgraded first open, then an instantaneous assertion caught
a legitimate transient summary refresh after sidebar setup. The final driver
selects exactly one visible active owner, handles the known dialog, and waits for
the unchanged strict usable predicate within the original 120-second deadline.
It records bootstrap node changes rather than rejecting legitimate restoration.
No failed receipt was converted to a pass or resumed as a completed sequence.

## What the evidence establishes

The original source-projection contract hashes complete `recording_workspace`,
`projection_cache`, `metadata_objects` and `workspace_service` files. Relative to
`add33d1`, only four lines in new-import CLI handling changed: they add the managed
recording locator to new manifests. Existing-project projection construction,
decoding and verification did not change. Nevertheless the whole-file witness
changed, invalidating source projections and transitively the sealed indexes.

Independent source review also found unchanged `disk_index`, tree, predicate and
typed-index/lifecycle owners. Existing imports are not automatically migrated.
The native first-upgrade run confirms the resulting cache miss and new generation;
the next process reopens that same generation.

This does **not** attribute the entire 49-second difference to rebuilding. The
first upgraded refresh spent about 3.44 s rebuilding its source projection and
36.72 s in the metric named `sql_queries`. That metric also includes first import
of `retinanalysis.config.schema`, with its acquisition-table declarations, before
workspace-table setup and result queries. Same-version SQL admission still costs
several seconds. Fresh stage/runtime effects and host pressure are not controlled
independently here; a host observation during an earlier run showed substantial
swap use. No broad speedup claim follows from this single fixture sequence.

## Reviewed implementation

The new resolver binds an exact ordered vector of the four existing source-file
digests **and its own file digest**. One reviewed vector maps to the original
legacy four-file checksum. Unknown bytes use the complete five-file checksum;
there is no version-wide constant, semantic AST hash, wildcard or independent
per-file allowlist. Literal receipt parsing rejects executable statements,
invalid schemas, duplicate vectors/IDs and mismatched legacy checksums. Missing
or invalid receipts conservatively use the new full-vector identity.

The receipt records the actual legacy owners, checksum, rationale and evidence.
The resolver and data file are explicitly packaged and integrity checked. A mapped
test requires a compatible or breaking review decision for the current vector.
Native and typed index recipes, seals, leases, full SQL admission, recording and
metadata signatures, and final publication checks are unchanged. Compatible
opening reads the original generation under its original key and seal; it never
renames, reseals or relabels existing cache files.

Source review approved the exact vector and integration. The architecture and
packaged-source closure checks pass, along with 102 resolver, refresh, projection,
native-index, object and typed-index checks, including each owner
and resolver mutation, malformed receipts, original-seal reopening without H5
walk/projection decode/index rebuild, and semantic equality to a forced fresh
build while SQL admission still runs. Equivalent-builder unit tests are not
historical-cache proof; the staged native upgrade supplies that separate evidence.

## Completed compatible-upgrade experiment

The [post-change four-process receipt](../../benchmarks/results/ui-version-first-open-b026a29-compatible/receipt.json)
binds old `add33d1` to `b026a29db869d6cca962d53aa0260c1ed1f59f0d`.
The [staged contract witness](../../benchmarks/results/ui-version-first-open-b026a29-staged-contracts.json)
checks the staged resolver/receipt bytes and the unchanged upgrade harness.
Old populate, old reopen, first upgraded open and new reopen all passed their
membership/identity checks and exited normally with code 0.

| Phase | Launch to data ready | Launch to usable Overview | Source projection | Native/typed indexes |
| --- | ---: | ---: | --- | --- |
| Old reopen | 11.401 s | 11.601 s | 1 hit, 0 rebuilds | Reopened |
| First upgraded open | 63.049 s | 63.447 s | 1 hit, 0 rebuilds | Reopened original generation |
| New reopen | 13.303 s | 13.500 s | 1 hit, 0 rebuilds | Reopened original generation |

The [cache proof](../../benchmarks/results/ui-version-first-open-b026a29-compatible/cache-compatibility-proof.json)
confirms that source-projection files, native/typed SQLite indexes, seals and
published-generation records kept their original names and SHA256 hashes through
both new-version phases. Nothing was renamed or resealed. The separate passive
[scientific stat witness](../../benchmarks/results/ui-version-first-open-b026a29-compatible/scientific-stat-witness.json)
confirms unchanged original/managed H5 and all three imported metadata files,
including hashes, device/inode, size, mtime and ctime. Exact 63-epoch/two-cell
membership and protocol identity remain checked against the original project.

A separate [dual-response trace check](../../benchmarks/results/ui-version-first-open-b026a29-traces/receipt.json)
passed after the four timing phases: Amp1 and Amp2 each returned all 127 expected
values at start 17, with exact stream identity, units and sample rate. This used
authenticated renderer requests to the native trace API; it is not another native
channel-button UI audit and its time is excluded from the upgrade measurements.

There is **no demonstrated cold-latency improvement**. With source rebuild time
zero, the first upgraded refresh still took 49.608 s, including 41.757 s in the
broad `sql_queries` metric. The same-stage reopen spent 8.498 s in refresh and
6.495 s in that metric. Cache preservation is established independently of this
remaining delay.

## Same-version fresh-stage diagnostic

The [stage-path pair](../../benchmarks/results/ui-version-first-open-b026a29-stage-path-pair/receipt.json)
then opened the already candidate-warmed project from a fresh stage of the same
`b026a29` source, followed by a second process from that stage. The prior and fresh
stages contained 111 Python application files with identical relative paths and
SHA256 bytes. No version change or source/index rebuild occurred in either phase.

| Phase | Launch to data ready | Launch to usable Overview | Refresh | Broad `sql_queries` metric |
| --- | ---: | ---: | ---: | ---: |
| Fresh-stage first open | 62.253 s | 62.415 s | 47.835 s | 40.414 s |
| Same-stage reopen | 12.560 s | 12.746 s | 8.038 s | 6.114 s |

Both phases reused the original generation, preserved cache/scientific files and
exact membership, and exited normally. This reproduces the long delay without a
version change or projection rebuild. It does not isolate the cause: finer SQL,
Python import/schema declaration and filesystem costs remain unresolved, while OS
caches and memory pressure were uncontrolled. This was an unprofiled experiment.
`PYTHONPROFILEIMPORTTIME` was omitted because the unchanged supervisor filters it;
no environment allowlist or loader hook was changed to obtain profiling output.

## Current validation boundary

At `b026a29`, the [core gate](../../benchmarks/results/ui-cache-compatible-b026a29-core/benchmark.json)
completed in 15.724 s with no validation errors and cleaned fixtures. The
[pinned million-epoch comparison](../../benchmarks/results/ui-cache-compatible-b026a29-pinned/comparison.json)
passed with `review_required: []`. The [comparison against previous candidate
`79449da`](../../benchmarks/results/ui-cache-compatible-b026a29-previous/comparison.json)
also passed both registered million-epoch lanes with `review_required: []`.
Both comparisons used the same current harness and permanent fixture serially;
all exact-result/refusal checks passed. Neither required a repeat. These query
and correctness gates do not establish a native startup speedup.

These are owned synthetic-project, unpackaged native-development observations.
They do not qualify an installed application, real-data scale or a production
release. Renderer request coverage starts after launch resolves and excludes
main-process authorization traffic. All pre-change and failed evidence remains
preserved, and no general startup or waveform speedup is claimed.
