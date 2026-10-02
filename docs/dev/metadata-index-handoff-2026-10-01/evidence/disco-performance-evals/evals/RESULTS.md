# Disco performance experiment results

The isolated candidate at `eb1e73e2ea4af821ddc73b957568f13746dd9b8f` improves common structural navigation markedly, preserves completed action results, and passes the frozen regression evaluations. Production source is on branch `codex/performance-evals` in `/private/tmp/disco-performance-evals-20261001`. The running app and original dirty checkout were not updated. No merge, packaging or release was performed.

## Everyday actions at 100,000 synthetic epochs

| Action and measurement scope | Same-day baseline median | Candidate median |
|---|---:|---:|
| Browser: open client-unloaded cell | 2,466 ms | 102 ms |
| Browser: open client-unloaded block | 2,565 ms | 101 ms |
| Browser: open previously unvisited cell | 2,550 ms | 100 ms |
| Browser: open previously unvisited block | 2,616 ms | 99 ms |
| Browser: next 60 cells | 2,238 ms | 93 ms |
| Browser: select epoch metadata | 97 ms | 96 ms |
| Browser: search focused metadata | 33 ms | 32 ms |
| Browser: reopen cached cell | 66 ms | 66 ms |
| Browser: scroll loaded rows | 32 ms | 33 ms |
| Native API: first/next 60 epochs | 61 / 62 ms | 61 / 60 ms |
| Native API: tree root/date/cell/block | 2,022 / 2,416 / 2,763 / 2,737 ms | 14 / 15 / 14 / 16 ms |
| Native API: epoch details | 65 ms | 63 ms |
| Native API: overview | 569 ms | 560 ms |
| Native API: full-catalog contrast preview | 4,196 ms | 2,054 ms |
| Real HTTP: existing lightweight filter preview | 586 ms | 578 ms |

Native API uses ten samples; browser uses five. Both use actual native MySQL, production Flask routes and sealed SQLite metadata, with no legacy oracle fallback. Browser mounts production React components in a minimal shell; this is not installed-app startup or a full-App usability qualification. Separate lightweight preview pairs use the same one-sample API prelude then ten HTTP requests. Exact canonical responses match. The existing UI already requests `catalog_summary:false` for filter/results flows; the older full-catalog metric describes metadata facets/layout analysis and is not substituted for lightweight filter performance.

First-use costs remain visible: first native root was 308 ms, first date 109 ms. Initial browser component view was 910 ms versus 2,905 ms, one observation each. Added disjoint branches confirm improvement beyond reopening a server-cached specific branch. Server-wide scope/group preparation is still cached, and full basic metadata remains in Python. This is the first conservative optimization pass, not SQL cursor paging or million-epoch qualification.

## Regression coverage and exactness

- 196 integrated Python tests passed after review fixes, including revision/binding policies, source integrity, refreshed-cache lifetime, missing/null, numeric types, Unicode, joint/dynamic fields, offsets and anchors.
- Same-day native API and browser comparisons passed all repeated-action median gates with no missing actions.
- Dense tag replays at 10k and 100k passed all 18 correctness checks each and all frozen action comparisons. At 100k, tag ten + another ten + filter twenty took 186 ms versus historical 191 ms; cell tag/filter 161 ms versus 155 ms. Initial dense migration 155.8 s versus historical 146.3 s is a descriptive single setup observation, not ordinary reopening.
- Real H5 trace controls passed source-integrity and same-size mutation rejection. Warm 20k-sample reads were 1.75 / 1.78 ms for 32 / 256 MiB payloads versus historical 1.85 / 2.33 ms. These are local file-cache-warm reads, not browser or NAS measurements.
- Default repeated-action regression policy requires both >20% relative and >20 ms absolute increase; trace replay used the stricter 1 ms absolute margin. Small historical five-sample tag baselines are flagged. First/setup observations remain separate descriptive checks.
- All native databases and owned browser/server processes stopped normally. Candidate Python inventories remained unchanged while measured. All runtime state/preferences for final runners used owned directories.

## Initial indexing and memory

Paired fresh 100k SQLite index builds, one observation per source: **27.13 s baseline versus 24.10 s candidate**. Both produced 185,298,944-byte databases, matching complete catalog hashes, exact boundary metadata and successful sealed reopen. Index reopen was 0.689 versus 0.536 s. This measures synthetic metadata-index creation/opening, not H5 import parsing, total app startup or a latency distribution.

The explicit full-generation catalog diagnostic improved 9.366 to 6.544 s with peak worker RSS 400.84 to 410.64 MiB (+9.8 MiB). Full-catalog aggregation retains more distinct values concurrently, so larger-scale memory needs qualification. A separate matched lightweight native sequence reported worker high-water RSS 592 to 448 MiB, one footprint pair; main ten-sample candidate worker peak was 506 MiB without a matched baseline measurement. These omit MySQL/Chrome and are not whole-application RAM claims. Fresh index workers peaked 465 versus 456 MiB. RSS can reflect paging/compression.

## Changes, adjustments and remaining work

Common date/cell/block navigation borrows existing basic rows instead of building an epoch-by-field matrix and decorated full selection at every depth. Exact scope identity is reused across depths; grouping and summary caches are bounded and charged before admission. Unsupported/custom policies retain authoritative general reads. Refresh releases obsolete row-generation references immediately after successful publication and preserves published data after failed verification.

Catalog reads batch statistics and reuse canonical indexed values. Full-generation scopes use a view instead of copying all IDs; true subsets use a measured scope-first plan. A forced plan for full generations was rejected after a slowdown. Independent review found and corrected custom-binding/policy bypass and cache-retention/accounting issues before final measurements.

The expensive full-catalog preview remains about 2 s, lightweight filtering about 0.58 s, and overview about 0.56 s. Targets for those actions remain unmet. Cursor-based SQL navigation, bounded selection handles, broader import streaming and 500k/1m qualification are still future experiments. The earlier larger builds hit time caps; no larger-scale capacity claim is made here.

`WORKLOG.md` records decisions and harness repairs, including correction of a failed 10k baseline accidentally selected by filename and the older ineffective preference override. `README.md` provides commands and evaluation policy; `CANDIDATE-RESULTS.md` and `catalog/README.md` give detailed scope and iterations. Baseline and candidate manifests protect raw JSON and runner snapshots. Data files, dependencies and private recordings are excluded from tracked receipts.
