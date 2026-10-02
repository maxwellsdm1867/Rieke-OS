# DISCO metadata qualification and fresh real-million before/after report

The sealed real-record million replay completed 14 equal-payload paired backend cases. 2 additional receipts are incomplete/censored; they remain separate from successful comparisons. All results are backend observations. The complete nine everyday UI/API actions remain unqualified on the integrated real-million application.

## Target, corpus and measurement contract

- Before: application snapshot `f03577e650ce5f604e9585f5bee983ef01bccad3`, unchanged native SQLite match/values/detail code.
- After: combined committed integration `e6c996a10afa819bb944135e58a593867d344a76`; complete 140-field typed SQLite sidecar attached to the same native metadata base.
- Corpus: exactly 1,000,000 metadata epochs, 140 eligible fields, 77,107,863 epoch-field links; 359 copies of 2,781 actual recorded epochs plus a 1,621-epoch whole-block tail. It is not one million independent acquisitions or new readable recording files.
- Original source SHA-256: `0427f38b01fad730941c3161d67a4fd6ae75988344527648cc066771b983147e`.
- Million replay SHA-256: `7e03e05e97885505f227e1b0938b34f303229db90ddcdd1f7e40f40d6b55e2b6`.
- Metadata generation: `ecc7b07cff319076486899a8521f18b8131fbb2662b68f38027697ab6ec148d0`.
- Project: `f75a7799-a728-5220-8f20-bfa4e7dffcb1`.
- Fresh candidate SQLite SHA-256: `8844b0245c146d5abc4d6848fb7fee2cb7e6c5053b6a7e7a43c8d094eb71c0aa`; candidate generation token `c954dc4dd53ddb6188669b5867358340961555769637791747629c738df86e65`.
- Replay construction retains seven native tables and production indices but uses experimental fingerprints, omits upfront full-field catalogs and preserves copied source-path provenance. It is not a published native project with one million readable new H5 traces; source/annotation authority is checked separately on isolated small service fixtures.
- Each main arm returns exact count, first 60 chronological native row DTOs, continuation rank and only requested facet fields, including JSON serialization. Source truth is standard-library code over the sealed original records; optimized predicate compilation is not the oracle.
- Every million acquisition UUID and chronology rank was checked against recorded dates/timestamps and the preserved namespace. Every selected member was checked against independent original-source predicate truth; lineage-weighted counts establish completeness. Complete serialized payloads must match the independent expected SHA-256 in every accepted sample.
- Five samples per complete arm, alternating before/after order; first is the first observed operation in a prepared process, warm median uses samples 2–5, max uses all five. No p95/p99 claim. Processes and filesystem caches are warm; no cache flush or installed-App startup is represented.
- Main caps: 45 seconds per sample, 1 GiB process peak RSS, 4 GiB free-disk floor, 768 MiB available-RAM floor. Watchdog polls RSS every 50 ms and RAM/disk every 2 seconds; bounded polling overshoot is possible. Worker setup has a 180-second hard deadline.
- Native warm reader is initialized after complete corpus seal/count/generation verification, without writing a retained-corpus reader lease. It uses unchanged production match/values methods and a compact proven UUID/rank map. Eager full-app row startup, native source publication and HTTP transport are excluded.
- Runtime: Python 3.11.13, SQLite 3.50.4, macOS arm64. Full source/runner hashes, runtime strings and raw traces are retained in machine-readable receipts. Per-case RSS includes both arms and oracle setup; it is not isolated arm RSS.

## Fresh paired page and requested-facet observations

Times are milliseconds in **first / warm median / maximum** order. An incomplete row contains only its observed completed samples; its statistics cannot establish a paired improvement. Requested-facet cases request `parameters/useRandomSeed` and `parameters/currentSpotSize` only.

| Case | Matches | Before ms | After ms | Samples B/A | Equality/status | Process RSS MiB |
|---|---:|---:|---:|---:|---|---:|
| largest_cell page | 687 | 13,448.68/13,637.90/13,758.23 | 6.52/2.59/35.39 | 5/5 | equal, passed | 404.0 |
| largest_block page | 601 | 13,765.94/13,455.86/13,765.94 | 8.03/2.00/28.84 | 5/5 | equal, passed | 408.6 |
| compound_all page | 416,035 | 14,320.01/14,323.14/14,446.64 | 1,639.70/1,789.41/1,946.97 | 5/5 | equal, passed | 579.8 |
| array_eq page | 668,034 | 16,012.97/15,030.16/16,012.97 | 1,053.09/1,157.85/1,401.23 | 5/5 | equal, passed | 438.4 |
| array_contains page | 668,034 | 14,444.59/14,435.65/14,885.31 | 1,176.97/1,328.38/1,633.42 | 5/5 | equal, passed | 427.0 |
| number_eq page | 654,751 | 14,663.22/14,499.97/15,078.81 | 1,488.77/1,140.75/1,488.77 | 5/5 | equal, passed | 441.6 |
| recorded_null page | 305,041 | 14,198.91/13,929.94/15,689.44 | 788.25/731.67/1,079.99 | 5/5 | equal, passed | 372.6 |
| missing page | 331,966 | 14,405.02/14,363.97/15,285.97 | 2,466.44/2,329.34/2,817.96 | 5/5 | equal, passed | 418.4 |
| mixed_types page | 248,194 | 14,079.39/13,857.10/14,315.75 | 477.89/384.98/613.03 | 5/5 | equal, passed | 333.4 |
| compound_any page | 688,138 | 14,658.03/15,001.46/17,005.57 | 1,848.50/1,779.25/2,134.66 | 5/5 | equal, passed | 475.8 |
| largest_protocol page | 668,034 | 14,920.31/14,766.33/15,967.65 | 87.30/70.20/87.30 | 5/5 | equal, passed | 496.7 |
| global page | 1,000,000 | 12,693.55/12,338.16/12,693.55 | 33.12/20.85/33.12 | 5/5 | equal, passed | 341.0 |
| largest_cell facets | 687 | 13,685.68/13,594.28/13,685.68 | 6.12/4.66/6.12 | 5/5 | equal, passed | 376.3 |
| largest_block facets | 601 | 13,770.31/13,703.55/13,837.71 | 5.45/4.20/5.96 | 5/5 | equal, passed | 373.7 |
| largest_protocol facets | 668,034 | —/—/— | 4,470.47/3,308.73/4,470.47 | 0/5 | incomplete; TimeoutError('45s sample cap') | 414.4 |
| global facets | 1,000,000 | —/—/— | 4,484.06/3,295.19/4,484.06 | 0/5 | incomplete; TimeoutError('45s sample cap') | 363.2 |

Raw sample arrays, exact DTO/facet/cursor payload hashes, input signatures, source-generation checks, failure traces and independently accepted typed samples from censored pairs are in `receipts/million/`. Capped native arms and after-only samples are not folded into speedups. A count/first-60 proxy does not replace full legacy MatchingEpochs, full-catalog preview or tree navigation.

## Additional backend controls

Both controls completed five samples per arm with exact expected payload equality and generation fences. Combined control-process peak RSS: **92.44 MiB**. These controls enforce 45-second samples and a 1-GiB RSS watchdog; their caps exclude the main workers' RAM/free-disk floors.

| Control | Before first/warm/max ms | After first/warm/max ms | Status |
|---|---:|---:|---|
| next60_cell_counts | 10,075.46/10,142.36/10,336.53 | 5.74/1.52/5.74 | complete |
| three_full_details | 3.16/2.92/3.16 | 11.60/2.89/11.60 | complete |

The cell control compares the minimal second 60-cell UUID/count projection with unchanged native SQLite grouping, not the full native tree route, labels, anchors or rendered UI. Independent source lineage supplies exact cell counts. The detail control compares three fully decoded native detail DTOs; the before cache was primed to freeze native truth. It does not read waveforms or reconstruct stimuli.

## Independent correctness and fault gates

- Frozen hand-authored 12-epoch truth covers 164 eligible native fields, including 145 previously unseen parameter fields, complete row/detail DTOs, bool/number distinctions, unsafe integers, heterogeneous arrays, explicit null versus missing and escaped metadata paths.
- Native and typed small readers each passed 22,253 predicate/scope membership comparisons, exact rejection checks, all-page cursor walks, exact facets, complete DTOs and native detail reconstruction. Immutable truth does not call optimized helpers.
- Integrated service: 6 independent tests passed against the exact after commit; 8,092 predicate/global-cell-block-group page comparisons, eight exact HTTP validation errors, opaque full-pagination checks, query/publication/source/tamper cursor faults, pending/ready cancellation, read failures and generation changes before calculation/publication/after ready.
- All 164 native registry types and full/requested/count-only facets passed. Registry admission may legitimately enrich scoped binding/annotation context; the pending job token must then remain exact. Source exclusion affects new queries while original protocol and frozen custom membership remain authoritative.
- Isolated tag-ten, inherited/direct tag ownership, edit/export/import, stale revision rollback and annotation generation changes passed on native annotation code with transactional SQL doubles. Protocol curation remains distinct from shared tags. These checks are not native MySQL concurrency or million-tag benchmarks.
- Implementation-owner aggregate evidence: backend 255 tests run (250 passed, 5 opt-in native MySQL tests skipped); frontend 347/347 passed. These are supporting integration checks, not fresh rendered million-row measurements.
- No independent production correctness mismatch was discovered. Native/custom annotation fallback remains serialized and unqualified at broad scale. Empty source-hierarchy branches without epochs need an independent native hierarchy fixture; zero-match pages do not close that gate.

## Build, verification and startup

Fresh typed sidecar build plus subsequent verified open took **119.761 s**; core build reported 118.579 s. Peak build RSS was **214.58 MiB**. The existing native metadata base was shared, not copied. The build passed the 300-second, 1-GiB RSS and 4-GiB free-disk caps.

Full original/replay SHA, count and generation verification ran separately in **9.374 s**. New sidecar verified open after build took **0.544 s**, with warm filesystem caches. Native full-app startup, cold reopen, refresh under readers and restart remain unrun.

Build phase observations (seconds): core_extract_seconds 23.570, chronology_assign_seconds 8.176, dictionary_extract_seconds 5.314, indexes_seconds 13.730, core_equality_proof_seconds 59.468, analyze_seconds 1.862, quick_check_and_counts_seconds 6.458.

The original build script declared an available-RAM floor in its receipt but did not enforce that floor during build; time/RSS/free disk were enforced. Main timing workers enforce all four declared resource controls. The earlier experimental build timing is historical, not a controlled before/after build pair.

## Storage: total metadata and incremental optimization

| Asset or accounting scope | Exact file bytes | Decimal GB |
|---|---:|---:|
| native_base | 7,195,836,416 | 7.195836 |
| retained_experimental_sidecar | 1,107,034,112 | 1.107034 |
| new_candidate_sidecar | 1,107,034,112 | 1.107034 |
| Steady native base + new sidecar | 8,302,870,528 | 8.302871 |
| Steady SQLite + required proof files | 8,302,870,991 | 8.302871 |
| Observed coexistence: native + old + new | 9,409,904,640 | 9.409905 |
| Sampled rebuild high-water lower bound | 9,409,905,160 | 9.409905 |

Steady SQLite allocated filesystem bytes: **8,303,910,912**. Required native and candidate proof files add 463 file bytes, tracked separately from the common SQLite-only ratio numerator. The new sidecar is **+0 file bytes** versus the preserved complete experimental sidecar; this is no measured storage saving. Its complete generation/project/seal proof is fresh.

Steady total: **8,302.87 bytes/epoch** and **107.679 bytes/epoch-field link**. Added index: **1,107.03 bytes/epoch**, **14.357 bytes/link**, and **15.384%** of the native metadata base.

Rebuild samples every 250 ms included native base, retained old sidecar, candidate staging and linked temporary files; observed high-water file length **9,409,905,160 bytes** and allocated bytes **9,410,990,080** are lower bounds. Unlinked OS temporary pages can be missed. Free disk after build: **30,523,592,704 bytes**. Reader-safe old-generation cleanup was not performed or qualified.

### Stored native columns and component pages

| Component | Records | Stored column bytes | Average bytes/record |
|---|---:|---:|---:|
| epochs.row_json | 1,000,000 | 2,946,465,752 | 2946.47 |
| epochs.detail_blob | 1,000,000 | 1,592,616,218 | 1592.62 |
| metadata_objects.payload | 72,720 | 35,497,604 | 488.14 |
| field_values.value_json | 1,081,653 | 41,000,580 | 37.91 |
| sources.source_json | 1,080 | 1,486,080 | 1376.00 |

Stored column bytes are encoded payload, not page or filesystem usage. The following largest page components expose relation/core/index overhead; complete dbstat payload/unused/page breakdowns and schema row counts are in `receipts/million/storage.json`.

| Database component | Used page bytes | Payload bytes | Unused page bytes |
|---|---:|---:|---:|
| native_base: epochs | 4,880,719,872 | 4,751,081,970 | 109,661,753 |
| native_base: epoch_values | 1,054,748,672 | 724,066,365 | 96,268,638 |
| native_base: values_reverse | 959,799,296 | 724,066,365 | 1,597,434 |
| native_base: epochs_source | 74,518,528 | 70,967,105 | 333,111 |
| native_base: sqlite_autoindex_field_values_1 | 58,134,528 | 48,623,204 | 6,096,046 |
| native_base: field_values | 52,355,072 | 45,408,142 | 253,530 |
| native_base: metadata_objects | 51,740,672 | 46,110,044 | 4,926,382 |
| native_base: sqlite_autoindex_epochs_1 | 50,552,832 | 41,967,105 | 5,437,627 |
| native_base: sqlite_autoindex_metadata_objects_1 | 10,887,168 | 8,252,505 | 2,384,611 |
| native_base: sources | 2,224,128 | 1,560,600 | 648,570 |
| new_candidate_sidecar: typed_core | 410,632,192 | 384,335,770 | 17,611,567 |
| new_candidate_sidecar: typed_values | 158,367,744 | 149,078,394 | 1,082,693 |
| new_candidate_sidecar: typed_chronology | 83,714,048 | 79,967,105 | 501,691 |
| new_candidate_sidecar: typed_protocol_children | 72,396,800 | 68,948,676 | 236,028 |
| new_candidate_sidecar: typed_equality | 69,267,456 | 64,852,222 | 967,389 |
| new_candidate_sidecar: typed_text | 62,402,560 | 58,310,598 | 664,187 |
| new_candidate_sidecar: typed_block_children | 49,348,608 | 45,934,210 | 269,826 |
| new_candidate_sidecar: typed_group_children | 49,340,416 | 45,934,210 | 261,658 |
| new_candidate_sidecar: typed_cell_children | 49,336,320 | 45,934,210 | 257,574 |
| new_candidate_sidecar: typed_uuid | 45,543,424 | 41,967,105 | 442,895 |

Full canonical MySQL/project metadata, persistent summary-cache and annotation-map footprints are unmeasured, not zero. Incremental costs per newly imported epoch/source/new field/distinct value and a controlled original/intermediate/million common-layout growth curve are unrun. The historical original 2,781 clone and million sidecar have different layouts and cannot establish a controlled growth curve.

### Recording denominators

- Preserved original-source inspection: 689,388,110 actual H5 file bytes; original 2,781-epoch base + typed metadata 26,234,880 bytes, **3.8055%**. This run did not rehash or decode H5 files; its recording reference is explicitly retained historical evidence.
- Exact-lineage million projection: approximately 247,905,301,506 H5-container bytes, 131,953,484,228 compressed response-allocation bytes and 606,528,270,000 logical response bytes. Partial-tail H5 container size is prorated and approximate. No new million-epoch H5 recordings were created.
- Fresh measured million base + typed metadata / projected H5 = **3.3492%**; / projected compressed response allocation = **6.2923%**. Added index / projected H5 is about 0.4466%.
- Stress-fixture million metadata / reused original H5 bytes = **12.044×**. The scopes differ; this is a replay property and is not a real million-acquisition storage ratio.

## Required nine-action continuity ledger

Status below applies to the complete requested real-million action. Backend evidence does not change an unrun rendered action into a pass. Historical synthetic timings remain in the handoff, not fresh before/after samples.

| Action | Status | Fresh supporting evidence and remaining limit |
|---|---|---|
| Select epoch and display metadata | not_run | Small HTTP full-detail decoding passed; million three-detail control passed |
| Search selected metadata | not_run | Selected DTO preservation passed; client search timing unrun |
| Reopen cached cell | not_run | Historical cached path makes no database request; fresh rendered timing unrun |
| Scroll loaded rows | not_run | Historical cached path makes no database request; fresh rendered timing unrun |
| Expand unloaded cell | not_run | Largest-cell backend proxy passed; full tree DTO/anchor path unmeasured |
| Expand unloaded block | not_run | Largest-block backend proxy passed; full tree DTO/anchor path unmeasured |
| Load next 60 cells | not_run | Minimal UUID/count group control passed; full tree route/paint unmeasured |
| Tag ten epochs, including revision preflight | blocked | Small isolated tag/edit/export and revision-fault tests passed on transactional SQL doubles; isolated native MySQL million writer unavailable |
| Preview metadata filter, full scoped catalog | not_run | Small HTTP requested summaries passed; million requested two-facet backend results above; full global catalog unmeasured |

## Remaining gates and interpretation

The complete typed backend preserves the full scientific metadata model and passes the reported independent small-service and million-read comparisons. Completed same-payload backend pairs can demonstrate per-case speed gains under the recorded warm setup. They do not certify a UI SLO or qualify merging/installing the integration.

Open gates: all nine integrated real-million UI/API action measurements; unchanged eager/unbounded legacy MatchingEpochs and full tree/anchor contracts; empty native hierarchy branches; isolated native dense/concurrent annotation writes; cold startup/reopen/refresh/restart; full waveform/stimulus reconstruction and export; complete canonical project storage; incremental import and controlled growth; retained-generation cleanup.

Six MAT fixtures were excluded from the snapshot: `examples/data/sample_epochs.mat`, `tests/baselines/MeanSelectedNodes_baseline.mat`, `tests/baselines/getCycleAverageResponse_baseline.mat`, `tests/baselines/getLinearFilterAndPrediction_baseline.mat`, `tests/baselines/getMeanResponseTrace_baseline.mat`, `tests/baselines/getResponseAmplitudeStats_baseline.mat`. Their scientific comparisons are blocked until the original inputs are restored in an isolated test environment.

No live database writes, application restart/install, package build, external experiment, push, PR or merge was performed. All qualification changes live under `tools/metadata_qualification/` on the independent branch. Candidate SQLite data remain disposable local test artifacts; report, raw receipts and hashes are versioned.
