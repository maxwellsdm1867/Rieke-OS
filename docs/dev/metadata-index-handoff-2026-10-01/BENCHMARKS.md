# Metadata benchmark evidence through 2026-10-01

See also the [improvement traceability ledger](IMPROVEMENTS.md) for exact
implementation mechanisms, safety fixes, source pointers and requirement mapping.

The required future scale/regression corpus is the **sealed million-record replay
of actual mounted data** described in section 6, not the fixed-schema synthetic
million in section 3. Speed comparisons must include the [storage benchmark](STORAGE.md):
added index bytes, total metadata bytes, normalized growth and ratios to raw
recordings with an explicit physical/projected denominator.

The strongest current result is an **all-140-field SQLite candidate with bounded pages, structural-scope queries and requested summaries**. Reducing the indexed field set to 28 did not improve speed convincingly. This is a prototype decision: the running app has not received the million-row or priority-model changes. The reports below represent different workloads and cannot be combined into one end-to-end speedup.

## Current requested-summary UI workload

The current frontend removes the normal **Summarize all metadata fields** action.
Predicate-dialog **Preview matches** explicitly uses the existing `/explore/run`
contract with `catalog_summary:false`; native cell/epoch count receipts and
active/pinned field summaries remain available. Complete registry discovery,
raw detail, exports and reconstruction do not depend on distribution requests.
Complete catalogs and derived layout suggestions remain an explicit advanced
operation, scoped to the requested view.

Apply the same revised UI to both native comparison arms. Record exact predicate,
source/frozen-protocol scope, requested fields, count receipt and rendered
completion. Historical all-140-field summary/catalog measurements remain
**legacy full-distribution diagnostics**, not ordinary current UI actions.
Advanced layout suggestion measurements are separately opt-in. Fewer requested
facets are a workflow change; retain equal-output paired engine comparisons and
do not transfer diagnostic timings to current-workflow latency claims.

## Original nine-action baseline and continuity

Historical measurements used 100,000 **synthetic** epochs, production-built React components, genuine Flask/native MySQL routes and the sealed SQLite metadata index. A component shell was used, not full installed-App/Electron startup. The initial browser actions had three samples; later browser comparisons had five. Tagging and filter preview below are API measurements, not browser paint.

| Everyday action | Historical reference | Optimized 100k | Synthetic 1m SQLite / DuckDB |
|---|---:|---:|---:|
| Select epoch and display metadata | 96 ms | 96.2 ms | 93.7 / 92.5 ms |
| Search selected metadata | 32 ms | 32.1 ms | 32.7 / 32.4 ms |
| Reopen cached cell | 65 ms | 66.4 ms | 66.2 / 65.4 ms |
| Scroll loaded rows | 33 ms | 32.7 ms | 31.4 / 32.3 ms |
| Expand unloaded cell | 2.48 s | 101.5 ms | 100.3 / 100.1 ms |
| Expand unloaded block | 2.40 s | 100.6 ms | 99.1 / 98.9 ms |
| Load next 60 cells | 2.14 s | 93.0 ms | 92.7 / 109.0 ms |
| Tag ten epochs, including revision preflight | 52 ms | 25.4 ms | 21.3 ms native MySQL; no separate DuckDB writer |
| Preview metadata filter, full scoped catalog | 3.90 s | 2.054 s | **Unqualified in both engines** |

The synthetic million browser used the unchanged shared components with an **experimental HTTP readmodel**, not the complete production service. Its annotation test used one native MySQL writer and a sparse 1,000-epoch annotation seed. It does not replace the separate dense-tag controls. Browser timings include automation dispatch/actionability and two observation frames; scroll was programmatic. Cached search/reopen/scroll issue no database request. Differences near the observation floor do not demonstrate engine superiority.

**None of these nine complete UI/API actions was rerun against the later real-record million replay or priority experiment.** Those experiments add backend evidence below. Retain this table as the UI/annotation regression checklist.

Sources: [original report](evidence/disco-everyday-benchmark/REPORT.md), [optimized candidate](evidence/disco-performance-evals/evals/CANDIDATE-RESULTS.md), [million scorecard receipt](evidence/disco-duckdb-million-evals/evals/browser/scorecard.json), [explicit qualification gaps](evidence/disco-duckdb-million-evals/evals/QUALIFICATION.json).

## 1. September 30 baseline: find the expensive stages

Source `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`; Apple M1 Pro, 16 GiB RAM, macOS 14.2. Genuine uncached tree requests took seconds while raw indexed 60-row SQL took fractions of a millisecond. Full preview profiling identified catalog preparation. The original 100k metadata index took 25.7 s to construct, occupied 185 MB and reopened in 0.70 s; these exclude total app startup.

Initial 500k and million index builds stopped under the 240-second cap and produced no sealed index/action timings. The million stop reported 1,213 MiB worker RSS but was triggered by time, not a breached memory guard. These are failed bounded attempts, not proof of a database capacity limit. Legacy SQL-double API measurements are superseded by genuine native-route measurements.

Separate dense native annotations used three authors, five tags and two curation scopes; 18 correctness/source checks passed at 10k and 100k. First populated annotation preparation at 100k took 146.3 s and remains distinct from an ordinary reopen. Real temporary H5 controls measured warm 20,000-sample reads around 1.9–2.3 ms, with one initial full-file hash and correct same-size mutation rejection; they exclude HTTP, charts and cold NAS.

## 2. October 1: optimize the same 100k production paths

Source `eb1e73e2ea4af821ddc73b957568f13746dd9b8f`. Indexed tree grouping/paging reduced warm native tree pages to 14–16 ms and component expansion to about 100 ms. Initial API tree root still took 308 ms and initial component view 910 ms. Native/browser action coverage, correctness and the documented regression gate passed; no repeated-action median exceeded both 20% and 20 ms regression.

Full-catalog API preview improved **4.196 → 2.054 s** in the same-day pair. An independently paired lightweight `catalog_summary:false` preview was effectively unchanged, **586 → 578 ms**, with identical complete response hashes. The historical “contrast filter preview” action requested the full scoped catalog; ordinary MetadataExplorer already requested the lightweight variant. Neither result meets a 500 ms goal for that API path.

Dense tag and H5 replays passed their checks; first populated annotation preparation remained about 156 s. Worker RSS excludes MySQL/Chrome, and unpaired setup footprints are not whole-app memory improvements. See [final candidate report](evidence/disco-performance-evals/evals/CANDIDATE-RESULTS.md).

Fresh paired 100k index construction measured **27.13 → 24.10 seconds** and
sealed reopen **0.689 → 0.536 seconds**; database size and complete catalog
hashes match. Each is one setup observation. The final full-generation catalog
diagnostic measured **9.366 → 6.544 seconds**, with peak worker RSS
**400.84 → 410.64 MiB**. Its [exact receipt](implementation-snapshots/100k/candidate/docs/dev/performance-evals-2026-10-01/catalog/comparison-full-generation.json)
and baseline/candidate Python snapshots are now durable in this handoff.

## 3. Fixed-schema synthetic million: SQLite versus DuckDB

One shared synthetic CSV, one protocol and four scalar parameter dimensions fed configured typed models. Ten serialized-response samples and exact JSON hashes compared the engines; final SQLite timings use the Boolean-normalized receipt, not its abandoned first query attempt.

| Same backend operation | SQLite | DuckDB | SQLite covering-index adjustment |
|---|---:|---:|---:|
| First 60 epochs | 0.651 ms | 44.760 ms | 0.669 ms |
| Cell children | 0.185 ms | 2.521 ms | 0.175 ms |
| Count + 60 rows + two facets | 545.341 ms | 40.839 ms | 96.587 ms |
| Filtered seed facet, first 60 distinct values | 375.877 ms | 12.273 ms | 0.163 ms |

SQLite won small indexed requests; DuckDB won the initial broad facet plans. Specialized covering indexes fixed the measured SQLite table-lookup/grouping bottleneck, adding 69.2 MB and 6.62 s. That adjustment was backend-only and tied to these fields, not a universal arbitrary-metadata policy. Build/index/checkpoint cost was 18.82 s/945.3 MB for SQLite versus 5.24 s/150.5 MB for DuckDB; worker peak RSS was 195.4 versus 655.6 MiB. Shared CSV generation is excluded from both.

The unchanged production **16-field catalog stage** at 100k/20k matches measured **1.387 s SQLite versus 0.319 s DuckDB**, with complete equal hashes. Million DuckDB catalog recomputation took **3.455 s**, with about **1,476 MiB** sampled RSS; there was no same-scale SQLite control. This does not qualify the full native API preview or full million app.

Sources: [final engine report](evidence/disco-duckdb-million-evals/evals/RESULTS.md), [catalog control](evidence/disco-duckdb-million-evals/evals/readmodel/EAV-RESULTS.md).

## 4. Actual mounted data: 2,781 epochs and 140 indexed fields

The real snapshot contains three sources, 13 nonempty cells, 140 stored fields, 214,451 epoch/value links and 202 shared metadata objects. Full production catalogs return 141 fields because they add a derived joint field. It preserves actual arrays, null/missing values, mixed numbers, details and ancestry. Native reconciliation distinguishes 165 nonempty blocks from three empty blocks. No invented scientific distributions were used.

Paired current-catalog recomputation: **global 663 ms SQLite / 628 ms DuckDB**, **largest cell 239 / 489 ms**, largest protocol 472 / 497 ms. SQLite won every measured filtered catalog; DuckDB's global advantage was about 5%. Bounded 60 rows took **1.233 / 5.123 ms** and full first-detail decoding **0.708 / 5.710 ms**. DuckDB's standalone membership scans were faster, but that did not translate into faster filtered catalog preparation. All seven tables, complete catalog/row/detail hashes and independent source-projection oracles passed.

This supports SQLite for the measured interactive workload, not an unconditional engine winner. The real DuckDB file was smaller, but its copy timing excluded the object-table phase and is not comparable to initial SQLite ingestion. [Real engine report](evidence/disco-real-data-evals/engines/REPORT.md), [qualification](evidence/disco-real-data-evals/QUALIFICATION.json).

## 5. Earlier typed/indexed SQLite pattern on those actual records

Final **v3** bounded preview returns exact count, first 60 chronological rows, cursor and two requested typed summaries, including JSON serialization. Twenty scenarios and complete pagination walks passed independent membership/DTO/facet/cursor oracles; eleven observations per case retained the first separately. Observed arrays, null/missing and mixed numeric types passed; real Boolean-field coverage is absent.

| Equal bounded payload | Current SQLite | Typed/indexed SQLite |
|---|---:|---:|
| Global | 33.15 ms | 5.44 ms |
| Largest cell / block | 18.62 / 18.76 ms | 4.85 / 3.53 ms |
| Numeric / array equality | 30.38 / 35.70 ms | 17.13 / 16.81 ms |
| Explicit 2,781-ID eligible list | 28.66 ms | 19.15 ms |

Build plus preservation checks took **1.35 s**, adding **5.45 MB**, with 64.6 MiB build RSS. The fix combines typed core columns, indexing, SQL counts and bounded reads; datatype declarations alone were not isolated. An empty-UUID regression in v1 was corrected; use final v3 receipts.

Adding typed tables did not make the unchanged full-catalog algorithm use them. Separate SQL batching preserved all 141 fields/suggestions/layout and improved global **685 → 519 ms**, cell **234 → 122 ms**. These are different operations from the 5 ms bounded preview. [Final report](evidence/disco-real-typed-sqlite-evals/RESULTS.md), [v3 receipt](evidence/disco-real-typed-sqlite-evals/evals/v3/receipt.json).

## 6. Million-row replay of real records

Exactly one million epochs: **359 full replicas plus a 1,621-epoch whole-block tail** of the actual 2,781 records. Namespaced identities retain scientific values, arrays, missing/null and hierarchy. Value cardinalities and times repeat; this is not a million independent recordings, readable new waveform sources or complete native-import/fingerprint qualification.

The shared native base is **7.196 GB**; the typed sidecar adds **1.107 GB**. Core/dictionary/index construction took **50.57 s**; exhaustive proof/ANALYZE/checks brought total sidecar construction to **218.51 s**. Base construction itself was **420.35 s** and is separate. Native full-file verification/open took **69.65 s**, excluded from warm queries. These preparation costs must remain visible.

| Equal backend work | Current native query path | Final typed candidate |
|---|---:|---:|
| Global exact count + first 60 rows | 13.22 s | 18.25 ms |
| Cell / block count + rows | 13.69 / 14.08 s | 1.58 / 1.60 ms |
| Numeric / array equality + rows | 14.40 / 14.89 s | 833 / 865 ms |
| Compound AND / missing-field query | 14.97 / 15.30 s | 1.71 / 2.27 s |
| Cell / block preview with two facets | 13.58 / 14.23 s | 4.13 / 3.77 ms |
| Global / protocol two-facet preview | 45 s cap; incomplete | 3.18 / 3.19 s |

The current comparator uses unchanged production query methods with a compact UUID/rank cache instead of eager million-row JSON startup. Native MySQL eligibility, HTTP, annotation state and UI are excluded. Completed equal-payload comparisons passed hashes; independent lineage/value oracles qualified all twelve candidate scenarios, including those without completed native timing. A timeout is not an equivalence pass.

Selecting narrow IDs before fetching native DTOs reduced compound-filter time **11.76 → 1.71 s**. Driving requested facets from the selected structural scope reduced cell preview **2.90 s → 4.13 ms**. Full 141-field selected-cell catalog batching separately improved **25.59 s → 133.93 ms**, with exact complete hashes. Original uncached global catalog hit the **1 GiB RSS guard**, not a completed latency. The experiment bypassed any persisted global catalog cache.

Typed cell-group pages took about 1.3–1.4 ms; cached details remained about 0.16–0.18 ms. Native empty-branch behavior and complete UI actions are still integration gates. DuckDB was **not tested on this million real-record replay**. [Final replay report](evidence/disco-real-million-evals/RESULTS.md), [aggregate receipts and limits](evidence/disco-real-million-evals/summary.json).

## 7. Priority-field A/B and the winning adjustment

Saved layouts/logs reveal 18 distinct underlying paths, with 72–101 fields available per protocol. Refreshes/automation, missing POST bodies and overwritten last-run history prevent an “80% of human operations” claim. The candidate combined observed fields and scientific priorities into 28 preferred paths while retaining lazy fallback for all others.

**Full140 versus Preferred28:** all 15 million-replay cases returned identical serialized payloads and independently expected match counts. Global page was **18.56 / 18.33 ms**, cell two-facet preview **4.04 / 3.91 ms**, ExpandingSpots summary **3.090 / 3.087 s**, history filter **45.36 / 44.46 ms**. No convincing common-action gain; several uncommon queries regressed, e.g. canvas **1.655 → 2.056 s**, seed **64.88 → 122.45 ms**. “Cold” labels mean uncommon-field cases, not cold filesystem measurements.

The 57 KB preferred file took 1.159 s but reused the complete prebuilt core/full sidecar. No physical storage was removed. A standalone reduced asset's roughly 30% auxiliary/4% total saving was an estimate, not a constructed artifact. Keep all 140 indexed fields.

**Full140 structural-scope fix:** scientific leaves now point-read within explicit cell/block/group scope instead of building global posting lists first. Same-payload interleaved measurements show NDF **1,624.7 → 5.79 ms**, lightPath **684.4 → 2.82 ms**, canvas **1,614.7 → 5.91 ms**, trial count **72.34 → 2.46 ms**, rig **1,631.9 → 5.63 ms**. Protocol/global SQL is unchanged. Fixture qualification passed 1,185 field predicates, five equivalent validation rejections, 15 compounds and all-field facets across structural scopes.

**Requested summaries:** for the same 687-epoch cell, all 140 facets took **167.46 ms**, four requested facets **6.59 ms**, rows only **1.53 ms**. Count, rows and cursor match, and every selected facet equals its full-result entry. This is deliberately less requested work, not an identical-payload engine speedup or the full 141-field suggestion/layout catalog. Global two facets still take about 3.2 s; the broad ExpandingSpots summary about 3.1 s.

Five interleaved samples per arm alternate order; warm medians use samples 2–5. A later summaries-harness API typo was corrected separately without replacing valid paired scope receipts. [Final priority report](evidence/disco-priority-benchmark-evals/RESULTS.md), [full/preferred A/B](evidence/disco-priority-benchmark-evals/evals/comparison.json), [scope/summaries receipts](evidence/disco-priority-benchmark-evals/evals/scoped-comparison.json), [fixture qualification](evidence/disco-priority-benchmark-evals/model/scoped-fixture-smoke.json).

## Remaining release gates

The evidence favors SQLite for bounded interactive reads and retaining all-field flexibility. DuckDB demonstrated useful broad-scan/build advantages on narrower synthetic schemas and some real scans; it has not been disproved for million-row real analytics. No whole-engine migration follows from these experiments.

Before production claims, qualify all nine original actions on the integrated real-schema path, cold/reopen startup and verification, native source eligibility/refresh and cursor binding, complete tree semantics, dense/concurrent tags and inheritance, full API preview, waveform reads and stimulus reconstruction/export. Broad counts/global summaries and eager global catalog memory remain unresolved. Scientific replay diversity and absent pipette/amplifier-offset capture remain data-coverage gaps. Small local sample counts establish directional medians, not reliable p95/p99.

Large scientific databases remain private temporary artifacts. Saved reports, scripts, hashes and raw receipts are evidence, not proof that `/private/tmp` databases will survive the next session. Reuse final receipts and frozen code identities; retain superseded failures for provenance without substituting them for final results. No benchmark was rerun during this consolidation.
