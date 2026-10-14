# First project open after a version change

2026-10-14 UTC (October 13 local). The user identified a delay when first opening
an existing project in a new Disco version. This audit uses only owned disposable
projects, staged builds and an isolated HOME/profile. The installed app and real
scientific projects are unchanged.

## Completed pre-change native experiment

The complete four-process sequence ran old `add33d153ae8f533d5c4a68c50690764323c4336`
(released 0.1.12) to candidate `79449da`. The candidate's production bytes match
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

Source review approved the exact draft vector and integration. The architecture check and packaged-source closure check pass, along with 102
resolver, refresh, projection, native-index, object and typed-index checks, including each owner
and resolver mutation, malformed receipts, original-seal reopening without H5
walk/projection decode/index rebuild, and semantic equality to a forced fresh
build while SQL admission still runs. Equivalent-builder unit tests are not
historical-cache proof; the staged native upgrade supplies that separate evidence.

Post-change native upgrade measurements and required core/million gates are pending.
No cache-compatibility speedup, installed build or release qualification is claimed.
