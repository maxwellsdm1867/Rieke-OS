> Public migration copy: see [migration notes](../METADATA_MIGRATION.md) for current implementation status, redactions and checksum semantics. The report below describes its original session.

# DISCO metadata performance — session report and next-session handoff

2026-10-01. This consolidates the experiments and design discussion from September 30–October 1. It preserves a reusable implementation handoff, not a claim that the running application has received the experimental query engine. No further experiments, package builds, live database writes or merges are part of this documentation update.

## Start here next time

1. Read [system requirements](../../design/metadata-query-requirements.md) and the decisions below.
2. Read [benchmark ledger](BENCHMARKS.md), which retains all nine everyday actions and distinguishes real, replayed and synthetic workloads.
3. Use [the evidence index](evidence/INDEX.md) for final reports, source snapshots, scripts, raw receipts and checksums. The copied text evidence is durable in this repository; large private experiment databases remain outside it.
4. Before changing code, check the current branch, dirty files, running app and schema/API state. The working checkout already contains unrelated changes. Work in an isolated testing worktree and do not install/restart the user's active app as part of a benchmark.

An additional completeness audit records each measured mechanism, safety fix,
regression control and proposal in the [improvement traceability ledger](IMPROVEMENTS.md).
It also preserves the earlier 100k candidate's exact changed Python source,
tests and patch, alongside its baseline, so those details do not depend on a
temporary worktree or commit available only in another repository.

**Required next-session benchmark:** use the sealed **one-million replay of the
real 2,781-epoch dataset**, not the earlier simplified synthetic million corpus.
Benchmark speed and [metadata storage/growth](STORAGE.md) together. A faster
query does not close the gate if its mapping/index grows disproportionately.
Retain both total metadata cost and the incremental optimization cost; measure
the ratio to raw recordings separately rather than treating the metadata base
as waveform storage. Follow-up [source-file inspection](STORAGE.md) measured
689.388 MB of actual H5 files for 2,781 epochs and projects approximately 248 GB
of equivalent files for the real-million mix. The 8.303 GB SQLite metadata is
about 3.35% of that estimated H5 footprint, or 6.29% versus projected compressed
response payload. Million H5 files were not physically generated.

## Decisions from today's work

| Decision | Evidence and implication |
|---|---|
| Keep SQLite and the complete typed/indexed model. | Ordinary SQLite typed core/dictionary tables and indexes substantially improve bounded reads. This is not TypeSQL or a new library. No same-corpus million-real-record DuckDB comparison establishes an engine winner. |
| Keep the complete discoverable field set. | The 28-preferred-field candidate barely changed common-query latency and regressed uncommon queries. All 140 currently eligible paths remain available; 140 is a dataset count, not a future protocol limit. |
| Narrow work before narrowing schema. | Materialize a bounded page's IDs/ranks before loading wide DTOs; apply cell/block/group scope before metadata membership; compute only requested summaries. |
| Use per-protocol preferences. | Real protocols have 72–101 paths. Their useful settings differ, and saved trees/logs provide better initial choices than one global list. Preserve complete source parameters and reconstruction dependencies. |
| Keep exact full summaries as an explicit operation. | Full catalogs, suggested layouts and derived joint fields are different work from a few requested facets. The full selected-cell batching optimization is independently validated. |
| Learn preferences later from explicit local actions. | Existing logs lack most query bodies and deduplicated human-action history. Add reliable bounded action telemetry before claiming coverage or automatically promoting costly summaries. Prefer caches/precomputation before adding unnecessary indexes. |
| Develop against the same browser/desktop source. | The existing React/Python path supports quick UI/query iteration. Packaging remains a release/integration gate, not a required step for every experiment. |

## Results worth retaining

These are local backend measurements with defined scopes and output contracts, not updated everyday UI medians.

| Operation | Before | Candidate / adjustment | Scope |
|---|---:|---:|---|
| Count + first 60 rows | 13.22 s | 18.25 ms | Million replay, global, no facets |
| Count + 60 rows + two facets | 13.58 s | 4.13 ms | Million replay, selected cell of 687 epochs |
| Broad compound filter after narrow-ID paging | 11.76 s | 1.71 s | Typed candidate before/after, equal payload |
| NDF filtering after scope-first membership | 1,624.72 ms | 5.79 ms | Selected cell; full 140 before/after, equal payload |
| Canvas-size filtering after scope-first membership | 1,614.72 ms | 5.91 ms | Selected cell; full 140 before/after, equal payload |
| Rig filtering after scope-first membership | 1,631.89 ms | 5.63 ms | Selected cell; full 140 before/after, equal payload |
| Requested four summaries versus all 140 | 167.46 ms | 6.59 ms | Same cell/count/rows/cursor; deliberately fewer facets |
| Complete native 141-field catalog, SQL batching | 25.59 s | 133.93 ms | Selected cell; full catalog/suggestions/layout equal |

The original 2,781-real-epoch typed experiment added **5.45 MB** and took **1.35 seconds** including streamed preservation checks. At one million replayed epochs, the auxiliary index is **1.107 GB**; extraction/ranking/index creation took **50.57 seconds**, and build plus exhaustive validation took **218.51 seconds**. These are different dataset sizes and validation workloads. Million replay construction itself took 420.35 seconds and is not index cost.

The earlier paired fresh 100k synthetic index builds improved **27.13 → 24.10 seconds**, and verified reopen **0.689 → 0.536 seconds**, with identical database size and catalog output. These are single setup observations, not a new production startup guarantee. Its final full-generation catalog diagnostic improved **9.366 → 6.544 seconds** while worker peak RSS increased **400.84 → 410.64 MiB**; preserve that memory tradeoff as well as the latency improvement.

The million experiment's native full-file verification/open took 69.65 seconds; warm query timings exclude that separately recorded cost. The preferred 28 hot-file build reused the full core, and its 1.159 seconds is not a complete million-row build. Its projected 30% auxiliary-space saving is only an estimate; the experiment still attaches the intact full index and saves no physical storage.

Global two-field facets remain about **3.2 seconds**; some broad scientific filters remain approximately 0.8–2.3 seconds. Scope-first membership does not optimize global/protocol-only plans. Million scale alone does not make every operation fast.

## Data and scientific interpretation

The mounted snapshot contains 2,781 epochs, three source revisions, 140 eligible query paths and 340 decoded detail paths. The million corpus repeats those records in 359 complete acquisition namespaces plus a 1,621-epoch whole-block tail. Scientific values and timestamps repeat; identities are mapped. It does not qualify a million independent acquisitions, increasing scientific cardinality, new H5 trace access or live native source registration.

The retained usage audit found 18 underlying paths across saved/logged trees and filters, but refreshes/automation and missing request bodies prevent any valid “80% of daily operations” claim. See [per-protocol defaults](evidence/disco-priority-benchmark-evals/usage/DEFAULTS.md). The saved mean-noise layout references history 1/history 2/target, absent in its actual records; keep its saved missing-field behavior rather than silently changing it.

Pipette/amplifier offsets were requested, but not identified in this cached inventory. Visual centerOffset is separate. Protocol controlMode has not been established as electrical clamp mode. Internal solution additions, pipette solution and recording technique are null throughout this sample; external additions is the literal string `[]`; series-resistance compensation is integer zero. These facts must not become fabricated scientific defaults.

No populated tags exist in the real snapshot. Shared cell/epoch annotations, inherited cell tags and protocol/dataset curation retain their separate contracts. Synthetic tag stress receipts do not establish live million-scale tagging performance. Full stimulus reconstruction and exports need complete dependencies even when those fields have low summary priority.

## What is implemented versus proposed

| State | Contents |
|---|---|
| Existing application | Native metadata index/decoder, React interface, DataJoint/MySQL scientific state, source eligibility, annotations and saved layouts. Verify current checkout; it has pre-existing unrelated development. |
| Isolated and measured | Full typed SQLite read model, bounded ID-first pages, structurally scoped requested facets, scope-first scientific membership, previous full-catalog SQL batching, priority 28/fallback prototype and independent evaluation harnesses. |
| Rejected as the default | Restricting the hot query model to 28 preferred paths to improve speed. It did not materially improve common cases and worsened some uncommon queries. |
| Designed, not integrated | Protocol-aware requested summaries, nonblocking exact aggregates, generation-bound aggregate caches, learning from usage, explicit action telemetry, specialized indexes justified by measured workloads. |
| Still unqualified | Complete current UI/API at one million, startup/recovery, native eligibility, empty acquisition branches, concurrent tags, export/reconstruction fidelity and packaged desktop behavior with the candidate. |

## Next implementation slice

1. **Preserve the existing contract.** Wire the full typed read model into an isolated testing service; keep native detail decoding, original field validation, recorded identities, source eligibility and tag ownership. Avoid building/transporting a million-ID scope on each request.
2. **Port the measured query fixes together.** Narrow ID/rank paging, cell/block/group-driven facets and correlated scientific membership address different bottlenecks. The final scope fix is `model/scoped_full.py` in the preserved priority experiment; the preceding bounded model is `typed/typed_bounded.py` in the million experiment. Port the complete 141-field native batching path separately.
3. **Request what the screen needs.** Keep a complete lightweight field registry. Derive initial summary requests from the active tree/filter and explicit protocol preferences. Add pending/cancelled/stale states for broad aggregate work while retaining navigation and full-field access.
4. **Qualify real behavior and storage.** Use the sealed real-million replay for scale comparisons. Repeat independent all-field truth/DTO/cursor/facet checks, source/annotation generation faults and complete UI action measurements. Record total/added metadata bytes, per-epoch cost, component breakdown, metadata/raw-recording ratios, growth curve and rebuild high-water disk. Preserve prior samples and investigate repeatable speed or storage regressions before merging. Use an isolated writable project copy for live tag/edit/export qualification.
5. **Then address broad work and learning.** Profile remaining global aggregates and startup verification. Add bounded generation-aware caches and deliberate-action records; evaluate adaptive precomputation or specialized indexes only against the retained baseline.

Do not expand the first integration into a new engine migration, a universal field whitelist or an autonomous indexing system before validating the existing improvements. No numerical production SLO is certified by these local medians.

## Durable evidence and reproduction limits

The evidence inventory records each original absolute artifact path, repository copy, file count/bytes and SHA-256. It preserves reports, scripts, code snapshots and machine-readable receipts; images, binary profiles and databases are excluded from this text archive. Some original reports/scripts contain local paths and retain them unchanged to preserve provenance. Their database dependencies must be restored or regenerated before execution; copying a script does not make it portable automatically.

Large corpus dependencies were under `/private/tmp/disco-real-million-20261001`, `/private/tmp/disco-real-typed-sqlite-20261001`, `/private/tmp/disco-priority-benchmark-20261001` and `/private/tmp/disco-real-data-evals-20261001`. These temporary paths may disappear. The sealed replay checksum and construction/oracle scripts are preserved; do not assume a matching million corpus exists next session. The actual original source recordings remain scientific inputs and are not included in the report.

Use the existing runtime where available: `/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python -B` (observed Python 3.11.13, SQLite 3.50.4). Inspect saved scripts before rerunning; preserve resource caps and execute timing arms serially. The scoped harness supports resuming completed pairs; clear/archive its receipt to perform a fresh paired run. If the source generation differs, establish a new baseline rather than comparing new inputs to today's hashes.
