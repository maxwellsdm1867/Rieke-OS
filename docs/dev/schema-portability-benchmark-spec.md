# Rieke-OS schema, portability and benchmark specification

Status: completed bounded research/design specification; OS restart completed by user. 2026-10-03. No migrations, adaptive-index implementation or benchmark execution authorized by this document.

## Decision and evidence

Keep project-private MySQL/DataJoint authoritative, H5 lazy and SQLite acceleration disposable. Preserve reviewed JSON adapter kit `1.0.0-draft.1`; do not invent a competing contract. No evidence currently requires a database-engine replacement. Schema and import generalization are distinct from performance tuning.

Inspected implementation: `fafb826ee00cfa14b657e91ecae5db0c1eda4a84`. Baseline `491afa` and release `3d9f15f` are supplied context, not freshly measured performance targets. Reviewed kit: task-8 from 2026-10-02, including exact 35-table source catalog, public-to-storage mapping, schema, validator, examples and review resolution. Shared H5 design and v2 comparison from task-6 were read. The 35-table catalog is a source snapshot at `4383b2a`, not live DDL or a new full-schema certification at fafb826. Key declarations were checked directly. Installed RetinAnalysis acquisition declarations were inspected, but equality to its pinned upstream commit remains unproven. No global scientific main database was established.

No DB connections/loads, tests, builds, services, H5 copies or large-file hashing ran. No production files were edited. CONTEXT.md was read; no applicable repository AGENTS.md/.agents instructions were found during inspection. Library routing honors the explicit local artifact destination.

| Code at fafb826 | Finding |
|---|---|
| `python/recording_workspace.py:595–639` | Source PK is exact H5 byte SHA256. project_uuid and experiment_id are application links, not declared foreign keys. Never put a JSON digest here. |
| `python/workspace_disk_index.py:93–103` | Unique epoch UUID, field/value dictionary and `(field_no,value_id,epoch_id)` reverse index already cover many flexible fields. |
| `python/workspace_typed_index.py:129–213` | Typed projections, scoped/rank indexes, numeric/text/equality dictionary indexes and ANALYZE already exist. |
| `python/workspace_typed_index.py:441–462` | Rank-seek bounded page selects IDs before decoding wide JSON. Backend rank is not by itself a portable public cursor. |
| `python/workspace_typed_query.py:60–160` | Exact typed predicates and scope intersections; contains/wide-number fallbacks may scan large dictionaries. |
| `python/workspace_tree.py:213–239` | Discovery limits dictionary depth, skips arrays longer than 32, omits values with encoded keys longer than 1024, and whitelists descriptive attributes. These violate the new all-metadata access goal. |
| `python/workspace_typed_index.py:383` | Registry inherits discovered definitions; “complete” here does not prove access to all retained metadata. |
| `python/workspace_native_tag_lookup.py:305–325` | Trigger-maintained tag lookup/dictionary/author projections; test one-author and all-author patterns separately. |
| `python/workspace_recipes.py:26–80` | Exact UUID/fingerprint frozen members, query/binding context and source revisions. |
| `python/workspace_sqlite.py:23–95,241,338` | v2 export requires H5 hashes/paths; FK enforcement and integrity checks; lossless frozen records plus queryable projection. Not metadata-only vNext or raw-complete portability. |
| `python/workspace_state_snapshot.py:25–30` | Append-only recovery table ordinals; canonical additions require recovery changes. |

Historical tools/metadata_qualification/REPORT.md reports gains in 14 paired backend million-replay cases on different before/after commits. One million metadata epochs replay 2,781 originals; these are not independent acquisitions. Historical global-page warm median 20.85ms, missing-value page 2329.34ms, sidecar build about 119.8s and steady base+sidecar about 8.303GB do not qualify this commit, full UI, native writes, ingestion or export. Two facet pairs were censored. Retain receipts as history, not current speed claims.

## Public contract and complete metadata access

All metadata fields, including rare, protocol-specific and export-only fields, must be discoverable and queryable. Tiers govern speed, never access. Waveform sample bytes remain behind lazy raw readers; metadata describing them is still discoverable. Define type-appropriate operators for scalars, exact integers/decimals, arrays, objects and nested paths. Long/deep metadata must have a bounded, cancellable evaluation path, not silent exclusion.

Build an independent inventory from retained canonical metadata, including paths currently excluded by discovery. Registry records stable field ID/path, scope, type, unit, provenance, available operators and extraction coverage. Separate `complete`, `pending`, `failed/incomplete` coverage from acceleration state. A query may return a correct slower result, or an explicit pending/incomplete error when complete evaluation is unavailable. It may never turn missing index/extraction into zero matches. An empty result requires complete coverage for the requested scope/revision. Cancellation is not a completed result. Demotion removes acceleration only; metadata and field visibility persist.

Existing eligible-field tests are useful but insufficient: add independent rare/deep/long/tick/export metadata truth and expected discovery/query outcomes. Preserve legacy null exactly; do not infer that it means the kit's not_recorded status. Changing discovery must not silently change scientific fingerprints or invalidate approvals solely because more fields become searchable.

The kit is agent-ready as a reviewed draft mapping target, not an implemented production receiver. Verified source inspection: schema declares its draft version and disallows unknown structural properties; validator checks deterministic UUID mapping, declared field IDs/types/scopes/units, links and present-null rejection. It does not prove origin, units, live conflicts or receiving-side compatibility. Any coding agent should map source fields/types/units/UUID relationships into this contract and report unmapped fields; it must never write internal index tables.

Preserve native UUIDs or the kit's persistent authority namespace + UUIDv5 encoding. Labels, filenames and mutable JSON are not identity. Keep logical source, metadata revision, raw byte identity and transport checksum separate. Keep canonical numeric legacy IDs internal. Validate ancestry/source/protocol links and polymorphic annotation targets even where SQL FKs exist. Omission is not deletion; zero/false/empty string differ from missing. Units remain explicit (unknown null, dimensionless `1`); no implicit pA/nA conversion. Large exact integers/seed values and decimals use the kit's exact string encodings. Do not assign UTC to naïve source timestamps.

Version public schema, producer/adapter, metadata revision/fingerprint, physical schema, cache generation, raw verification and export independently. Preview binds normalized payload and expected catalog/tag generations; apply revalidates under locks, commits canonical entities/revisions/audit, then publishes a sealed projection. Exact replay is idempotent; same revision/different content and changed ancestry conflict. A failed projection after canonical commit is rebuild-needed, not a fictitious rollback. MySQL DDL can implicitly commit: migrations stay outside scientific import transactions. [MySQL transaction boundary](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)

Current 16MiB/10k-epoch bundle limits remain. Million-scale ingestion needs explicit self-contained shards/job atomicity or a separately versioned streaming contract; this review does not change v1 limits.

## H5 convergence, portability and migration

Add an explicit metadata registry/revision boundary beside legacy acquisition tables, preserving H5 Source keys and audited public-to-legacy aliases. H5-first/JSON-first orders must converge to identical public identities, tags and frozen membership or a visible conflict. Never invent raw assets or H5 rows for metadata-only sources. Metadata browsing/tags/frozen selections can become available without traces; raw-dependent QC/reconstruction/approval stays unavailable until verified required inputs exist.

Use the existing shared-H5 resolver design. Logical source, raw `(SHA256,size)`, project attachment and within-file stream path are distinct. Incoming locators/hashes are unverified claims, not read authority. Attach verifies bytes, acquisition/stream mapping, rate/count/units and bounded samples. Legacy data_file consumers receive a verified filesystem path, not an asset URI; filename fallback must not select another revision. Relinking changes resolution, not scientific identity. Byte dedup never merges provenance or independent registrations. Hardlinks share mutation, symlinks may retarget, clones complicate allocated accounting. No automatic asset deletion based on one project's references; disconnected copies, backups and leases matter.

Future migration: approved isolated live-schema inventory, backup/restore proof, additive registry/read compatibility and aliases, recovery coverage, versioned export readers, then importer/binding. No startup auto-migration. Old v2 exports remain readable; new metadata-capable exports separate logical source/revision from optional raw hash/path, retain field status/units/provenance and exact frozen annotations/membership. Old apps reject unsupported versions clearly.

Roundtrip oracle: bundle -> canonical -> export -> fresh receiving catalog, compare exact UUIDs/links/types/units/status/precision/arrays/provenance/revisions/frozen snapshots. Ignore only explicitly defined transport envelope differences. Existing SQLite v2 frozen-record roundtrip remains a separate supported seam. Raw-complete portability requires reopen with original root absent and synthetic sample verification; reference-only metadata exports cannot claim this. Recovery must restore canonical state without derived indexes and preserve frozen membership.

## Workload-driven acceleration proposal

Application-managed disposable SQLite sidecars are the preferred experiment. MySQL/DataJoint and canonical metadata remain unchanged. SQLite automatic indexes last one statement; they are not persistent self-tuning. [SQLite optimizer](https://www.sqlite.org/optoverview.html#autoindex)

Distinguish three candidates: (1) index existing complete field/value relationships, (2) typed/materialized extraction when repeated decoding costs dominate, (3) revision-keyed UUID result cache for repeated identical predicates. Generic EAV reverse indexes already exist; adding per-field indexes without measured advantage wastes resources. Result caches require normalized predicate/scope/order plus metadata/source/binding and relevant annotation generations; full-detail/export still loads exact versioned metadata. Never reuse stale UUID membership because counts happen to match.

Collect local bounded telemetry: logical user action ID, normalized pattern/field IDs/operator/type, scope/selectivity, observed cost and rows/bytes examined, repeat frequency and generation. Count genuine actions separately from UI refetches/retries/prefetch. Avoid retaining private literal values when hashes/shape suffice. Instrumentation itself needs a measured overhead budget.

Candidate benefit over a declared horizon = expected repeated query savings minus build, validation, refresh, storage, telemetry and contention costs. This is a proposal, not a calibrated formula. Evaluate interacting patterns/orderings, not only single fields. Require measured evidence, conservative estimates, minimum accumulated benefit, promotion/demotion hysteresis, cooldown, bounded simultaneous builds and disk/RAM/CPU quotas. Manual pins must fit budgets or explicitly fail admission; cannot silently evict required data. Under pressure evict optional acceleration/cache, never metadata. One-off rare queries stay available through complete fallback.

Construct a versioned candidate generation off the reader path; bind source/schema/extractor generations, validate complete coverage and exact oracle equivalence, then atomically publish. Keep old readers pinned until safe cleanup. Cancellation/crash/source change discards candidate or leaves it unpublished; complete fallback remains usable. Never publish a partially populated field as complete. Demotion switches routing before retiring acceleration. Durable publication/rename/receipt behavior requires fault tests; an atomic pointer alone is not a durability proof.

Partial indexes only apply when the query implies their predicate; expression indexes require matching expressions and deterministic functions. They are candidates, not blanket speed promises. [Partial indexes](https://www.sqlite.org/partialindex.html), [expression indexes](https://www.sqlite.org/expridx.html). Statistics changes and ANALYZE must be versioned/measured with the candidate; use features supported by the actual linked runtime. [ANALYZE](https://www.sqlite.org/lang_analyze.html)

SQLite serializes writers; WAL permits reader/writer overlap but does not create multiple writers. Long readers/checkpoints and background builds can contend. Verify the actual linked SQLite version/build and supported concurrency behavior before implementation; historical runtime strings are insufficient. No WAL/concurrency configuration change is proposed now. [Isolation](https://www.sqlite.org/isolation.html), [WAL](https://www.sqlite.org/wal.html)

Physical-design research supports joint workload/cost-aware consideration of indexes and materializations, not an engine-specific guarantee here. [Agrawal, Chaudhuri and Narasayya, 2000](https://www.vldb.org/conf/2000/P496.pdf). Continuous tuning research explicitly considers transition costs, workload change and oscillation; these motivate hysteresis and total-workload accounting rather than repeated build/drop on every slow query. Its results do not validate DISCO's proposed policy. [Continuous tuning research](https://www.microsoft.com/en-us/research/wp-content/uploads/2007/01/continuous.pdf)

## Single registry and fixed core cases

Infrastructure owner owns `benchmarks/registry.json`, `tools/benchmark.py run/compare/gate` and docs on `codex/versioned-core-benchmarks`. The following are proposed requirements, not a second registry or implemented cases. Reuse metadata_qualification CoreAdapter/NativeAdapter/Truth and existing E01 action IDs. Correctness preflight runs outside timed operations. SQL doubles and unittest duration are not native database latency.

Each registry case needs version, fixture/semantic seal, independent expected output, exact implementation/runtime/settings, dimensions/selectivity, timing boundary, warm/setup policy, authority/resources, raw samples, wall/CPU/RSS/temp/persistent bytes, correctness and passed/failed/capped/unrun/unsupported status. Changed timing/data/result scope requires a new case version.

Fixed core proposal: existing 12-epoch semantic truth plus separate deterministic 10k-epoch fixture: 100 cells, 5 protocols, 1000 blocks, 20 sources, 40 fields, specified missing/null distribution, chronology ties, repeated labels, low/high-cardinality values. Freeze exact assignments and counts; seed alone is insufficient. Add an independent complete-field fixture with rare protocol fields, >32-item arrays, >1024-character values, deep paths, precise ticks, empty branches and export-only metadata. Never replace real-derived stress truth with this synthetic microfixture.

| Proposed cases | Operation and oracle |
|---|---|
| db.typed.page.scope | First/next/deep pages 60, global/cell/block/protocol/source intersections; exact DTO/order/full cursor walk. E01-05/06 backend proxies. |
| db.typed.filter.matrix | eq/range/all/any/not/array/null/missing; exact 0,1,1%,50%,100% matches; count+page distinct from page-only. E01-09. |
| db.typed.facets.requested | Count-only, two facets and all facets separate; exact buckets/missing/truncation; no zero placeholder. |
| db.typed.membership.exact | Full streamed UUIDs and list path separately; independent complete set/count/order digest; duplicate scopes and intersections. |
| db.detail.decode / db.cells.next60 | Full detail including nonqueryable retained leaves; grouped next60 cell count proxy. E01-01/07, not full UI qualification. |
| db.typed.build | Base -> sidecar -> verified open, including proof/index/ANALYZE cost; base construction separately measured. |
| db.frozen.capture.verify | Capture/subset/verify; live query changes never change frozen members; stale fingerprints/duplicates reject. |
| db.export.sqlite.roundtrip | v2 build, integrity/FK checks, every frozen record exact comparison, file bytes/decode time. No raw-complete claim. |
| db.tags.ten | Opt-in disposable native SQL revision preflight/write/trigger/generation/recovery/readback; inherited/direct and one/all-author variants. E01-08. |
| db.h5.ingest.stages | <=10MiB synthetic H5 hash/parse/validate/commit/publication/replay; phase times and exact identities/units. Native SQL requires later authority. |
| contract.json.validate | Existing draft structural/semantic validation and rejection, input bytes/time/RSS; not importer speed. |
| db.fields.complete/fallback/incomplete | Independent complete inventory; unindexed/promoted/demoted equality; partial extraction returns explicit incomplete, never empty. Current implementation gap. |
| db.adaptive.workload | Static, instrumented-fixed, adaptive and manually tuned arms; identical fixtures/actions/cold-warm policy; charge all maintenance. Unsupported until implemented. |
| db.adaptive.shift-budget | Hot A->B, rare export, updates, refetch dedup, hysteresis/cooldown/pins and budget pressure; no lost access. |
| db.adaptive.publish-fault | Cancel/crash/source revision during build, partial-field refusal, reader leases, recovery/fallback correctness. |
| contract.metadata.import-roundtrip / asset.resolve.transfer | Both import orders, revision/replay/conflicts, metadata-only no raw reads, portable transfer. Unsupported until receiver/export/resolver exists. |

Reuse test_workspace_sqlite/MatlabExportTests package fixtures and recipe tests, import identity/check fixtures and service_checks/integrated_service fault seams. Extract helpers through owner rather than timing unittest setup. Existing 164 eligible-field truth cannot serve as complete-field oracle. E01-02/03/04 remain UI/client cases; backend proxies never close full rendered action gates.

## Separate stress and adaptive comparison

Only after parent release, run serially on disposable suite-owned catalogs. Ladder 10k/100k/300k/1M; record source/cell/block/stream counts independently. Preserve sealed whole-block real-derived replay and label supplementary synthetic stress. Fields 20/140/500; present density 10/55/95%; dictionary cardinality 2/100/10k/~N; arrays 0/8/64/1024; shared/unique objects; exact wide numbers. 1M*500*95% means 475M links and may be refused by resource preflight, never silently reduced.

Selectivity 0/1/0.01%/1%/10%/50%/100%; correlated conjuncts/overlapping OR; balanced and 80%-hot hierarchy; empty branches; chronology ties; page positions start/50%/99%, sizes 1/60/100. Facets 0/2/all. Tags 0/1/10/100 per target, profiles 1/10/100, tagged targets 1%/50%; stay within mutation limits. Frozen export sizes 10/1k/all. Ingest fresh/replay/subset/revision/conflict and shards 100/1k/10k within byte limits.

Use a fixed temporal workload: warm-up/training, stable A, shifted B, rare/export field sweep, metadata/tag updates, budget pressure, return to A. Compare static baseline, identical instrumented-fixed (telemetry overhead), adaptive and manually tuned configurations selected without test-phase hindsight. Optional hindsight oracle must be labeled separately. Disable or identically configure result caches across index arms, then run a separate cache arm. Match process/filesystem cache conditions; first query is not proof of cold OS cache.

Report cumulative user latency plus telemetry/build/validation/refresh/demotion costs, break-even action count, worst observed pauses, errors/timeouts, access completeness, promotions/churn, resource peaks and query plans. Keep every exact UUID/order/type/null/missing/unit/tag/frozen oracle equal, including rare never-promoted fields. Source/annotation changes invalidate relevant witnesses even when membership is unchanged. A faster wrong/partial result fails.

Measure canonical MySQL, base/index/proofs/import JSON/recovery, TEMP/WAL/staging and old+new generations; distinguish length/allocated bytes and hardlink/clone accounting. Sampled high-water is a lower bound. Reused-H5 replay metadata/raw ratios are not real million-acquisition efficiency. Do not execute the full Cartesian product: freeze baseline ladder, single-variable adversarial points and selected costly interactions.

## Budgets and remaining gates

No speed targets are validated or approved. Discussion proposals only: 10k warm page/detail median 100ms; 1M page without broad summaries 250ms; broad two-facet completion 5s; native tag-ten median 500ms; preserved-replay sidecar build 180s/1GiB. Calibrate on a named machine with raw samples; no p95/p99 claims from five samples. No absolute ingest/export or universal bytes/epoch target yet. Proposed regression review flag >20% AND >10ms paired median, not an automatic uncalibrated release gate. Adaptive net savings must include all costs; minimum benefit/hysteresis/overhead budgets remain to be measured and approved.

Historical safety caps (45s/sample, 1GiB RSS and disk/RAM floors) are resource limits, not success SLOs. Do not relax them automatically. Censored runs remain incomplete. Complete compatibility, extraction coverage and exact preservation are mandatory regardless of speed.

Integration follow-up: owner reconciles final registry identifiers and parent integrates this local document through the documentation owner. Future evidence requires separately authorized native schema/index inventory, current-commit timings, full-field fallback, ingestion/recovery, UI actions, metadata receiver/vNext roundtrip and resolver transfer. No production or adaptive implementation is included.
