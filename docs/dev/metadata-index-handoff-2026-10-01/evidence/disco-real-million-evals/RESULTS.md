# Typed SQLite at one million epochs: real-record replay

The typed/indexed projection makes bounded browsing much faster at the one-million target. It uses the existing SQLite engine and native metadata, with no new TypeSQL library. The remaining slow operations are broad scientific filters, global field summaries, and the original eager all-field catalog. This is an isolated backend experiment; the installed app and working checkout were not changed.

## Dataset and provenance

- Exactly **1,000,000 epochs**, **140 stored query fields**, **77,107,863 EAV links**.
- Replay of **2,781 actual mounted epochs** from LOCAL_NATIVE_PROJECT: 359 complete acquisitions plus 1,621 epochs in ten complete recorded blocks. Cells, blocks, groups, source IDs and epoch IDs are mapped into independent acquisition namespaces.
- Real scientific values, null/missing distinctions, mixed numeric representations, arrays, protocol mixture, timestamps and ancestor objects are preserved. Scientific values and timestamps repeat; this does **not** test one million independent recordings or growing scientific-value cardinality.
- Original native filtering eligibility remains unchanged: 140 query fields are not all 340 raw detail paths. Oversized arrays and other excluded values stay available through native detail decoding.
- Base database: **7.20 GB**. Its experimental construction/seal took **420.35 s**. This corpus construction is separate from the incremental typed-index cost.
- The replay uses an experimental v2 fingerprint and omits the original upfront global catalog caches. Native v1 metadata hashes and DTO ownership/checksums are preserved. Replay IDs/paths do not identify newly acquired readable H5 traces. This is a metadata-query qualification, not a complete native acquisition/import qualification.

## Added cost

- Auxiliary typed database: **1.107 GB**, **15.4%** additional storage. The seven native tables stay in one shared immutable base; their size is not counted twice.
- Extracting core columns/dictionary, assigning chronological ranks and creating indexes: **50.57 s**.
- Total including exhaustive core-equality proofs, ANALYZE and integrity checks: **218.51 s**. Equality proofs alone were 154.03 s.
- Build peak RSS: **161.23 MB**. Final page comparison peak: **145.00 MB**. Final facet comparison peak: **193.61 MB**.
- The normal native full-file verification/open took **69.65 s**, separately from query timing. Subsequent native workers reused that proven generation and unchanged file signature. This startup cost remains relevant to production integration.

## Equal-output page comparison

Both arms return the **exact match count, the first 60 chronological native row DTOs, cursor and empty facets**. Every completed native payload hash equals the final candidate. Current means the unchanged production `DiskMetadataIndex.match`/query methods on this same million corpus, not the currently mounted 2,781-epoch app latency.

| Action: exact count + first 60 rows, no facets | Matched epochs | Current native path | Final typed path |
|---|---:|---:|---:|
| largest_cell | 687 | 13.69 s | 1.58 ms |
| largest_block | 601 | 14.08 s | 1.60 ms |
| compound_all | 416,035 | 14.97 s | 1.71 s |
| array_eq | 668,034 | 14.89 s | 865.07 ms |
| array_contains | 668,034 | Not timed | 844.32 ms |
| number_eq | 654,751 | 14.40 s | 833.37 ms |
| recorded_null | 305,041 | Not timed | 443.17 ms |
| missing | 331,966 | 15.30 s | 2.27 s |
| mixed_types | 248,194 | Not timed | 316.46 ms |
| compound_any | 688,138 | Not timed | 1.50 s |
| largest_protocol | 668,034 | 14.94 s | 54.87 ms |
| global | 1,000,000 | 13.22 s | 18.25 ms |

The native warm comparator uses a compact UUID-to-rank cache instead of the app's eager million-row JSON cache. It verifies chronology and excludes this cache's setup from query timing. This gives the current query path a viable warm comparator without claiming the full current app can start/render a million epochs within the experiment's memory budget. The current API's MySQL/source eligibility lookups, transport, waveform reads and UI rendering are excluded.

## Equal-output requested metadata summaries

These previews add precisely two real fields, `parameters/useRandomSeed` and `parameters/currentSpotSize`: semantic value counts, exact present/missing counts, chronological first representatives, 60-choice truncation flags, native rows and cursor. They are not the original 141-field filter-editor catalog.

| Same count/60-row/two-facet payload | Current native path | Typed v2 | Final typed v3 |
|---|---:|---:|---:|
| largest_cell | 13.58 s | 2.90 s | 4.13 ms |
| largest_block | 14.23 s | 2.88 s | 3.77 ms |
| largest_protocol | 45 s cap; no completed sample | 3.21 s | 3.19 s |
| global | 45 s cap; no completed sample | 3.18 s | 3.18 s |

The candidate's four facet results were independently reconstructed from **every selected epoch's real-source lineage and values**, including global and protocol-wide cases whose native comparison timed out. The completed cell/block native hashes match exactly. A timeout is a retained failure to complete within the budget, not an invented latency or output-equivalence pass.

## Bottlenecks and measured adjustments

1. The earlier typed `_page` joined wide native `row_json` before limiting broad results. The compound filter took **11.76 s**. Selecting and materializing narrow epoch IDs/ranks before retrieving at most 61 native DTOs reduced it to **1.71 s**, with identical payload hashes.
2. The facet plan scanned a project-wide field posting list even for one selected cell. A structurally bounded cell/block/group query now drives from its typed core index and point-reads each epoch's requested values. Cell preview fell from **2.90 s** to **4.13 ms**, with the same output hash. Global/protocol summaries retain the original aggregate plan and stayed near three seconds.
3. Broad scientific predicates still process hundreds of thousands of memberships. Final numeric/array filters are about 0.83–0.87 s; compound predicates about 1.5–1.7 s; the missing-field query about 2.27 s. Typed dictionaries alone do not make all such operations instant.

The changes are query-only, preserve the existing predicate/DTO contract and require no additional database build or library. Final code is `typed/typed_bounded.py`; the earlier versions and all receipts are retained.

## Additional actions and the full catalog

| Additional backend action | Measurement |
|---|---:|
| first_60_cells | 1.42 ms |
| next_60_cells | 1.31 ms |
| blocks_in_loaded_cell | 0.50 ms |
| current_cached_detail | 0.18 ms |
| typed_detail | 0.16 ms |
| full_cell_catalog | 25.59 s; 141 fields / 687 epochs |

Original uncached global full-catalog attempt: **guard_stop**; reason **1 GiB peak RSS cap**; measured peak RSS **1093.26 MB**. It calls the unchanged native all-field catalog, including row loading, per-field summaries, derived joint fields, grouping suggestions and layout generation. The experiment intentionally had no persisted global catalog cache. Its result must not be presented as the speed of the cached production global catalog or the two-facet preview.

The previously tried batched full-catalog query was also retested, preserving all 141 fields, derived joint values, suggestions and layout: **25.59 s → 133.93 ms** for the same 687-epoch cell in the million-row database. All five optimized output hashes equal the native original. This is a separate SQL batching improvement; it does not require the typed tables and does not fix the global eager row load. Its exact earlier source and measurement are retained in `typed/prior_batched_workspace_disk_index.py` and `evals/batched-catalog.json`.

Typed tables are not yet wired into the original all-field catalog. Existing cached detail behavior should be retained; a typed projection does not require replacing the native decoder/cache. Nonempty metadata-derived groups are qualified here; complete native tree behavior, including empty branches, remains an integration check.

## All nine everyday actions retained

| All nine original everyday actions | Previously recorded UI median | Qualification in this experiment |
|---|---:|---|
| Select epoch and display metadata | 96 ms | Native detail/typed detail exactness and backend timings below; complete UI action not retimed. |
| Search selected metadata | 32 ms | Browser operation on loaded detail; no new million-scale UI timing. |
| Reopen cached cell | 65 ms | Cell backend count/page/two facets measured; browser cache action not retimed. |
| Scroll loaded rows | 33 ms | No database query; million-scale UI/frame-time regression remains unqualified. |
| Expand unloaded cell | 2.48 s | Cell page and block-group backend measured; mounted H5/MySQL eligibility and complete rendered action not retimed. |
| Expand unloaded block | 2.40 s | 601-epoch block page/two facets measured; complete rendered action not retimed. |
| Load next 60 cells | 2.14 s | Typed group page and next page measured and structurally checked; UI rendering not retimed. |
| Tag ten epochs | 52 ms | Not retimed. Real mount has one annotation row and zero tags. No canonical annotation writes or million-row tag claim. |
| Preview metadata filter | 3.90 s | Count/page and two requested facets measured separately. Complete 141-field cell catalog measured: original 25.59 s, earlier batching 134 ms. Global eager catalog hit memory cap; this remains separate from two facets. |

The screenshot medians are historical reference measurements, not rerun million-scale results. Backend equivalents are explicitly distinguished from complete everyday UI actions. No omitted UI/annotation action is silently marked passed.

## Correctness, limits and reproducibility

- Every returned member in all twelve million-scale predicate/scope scenarios was checked against independent Python truth from the actual 2,781-record EAV dataset and replay lineage. Exact expected counts establish completeness; ordered membership hashes are saved.
- All 5,562 two-copy fixture DTOs and EAV records were originally checked against recursive real-source rewrites using the native decoder. The final candidate passed 22 predicate checks, both chronological pages, details, complete metadata-derived group walks and all 140-field validation/error checks.
- Final selective facets passed 140 exact native comparisons spanning every query field across cell and block scopes. Earlier/final page and facet output hashes match wherever timings completed.
- Timings include JSON serialization. Candidate page measurements use five samples; facet measurements use three. Expensive native comparisons use two samples, except the cell page's five retained samples. A two-sample warm median is only one warm observation; these are directional local experiments, not robust p95/p99 estimates. First samples follow setup and are not cold-start UI measurements.
- Owned workers have time/RSS limits; resource-limited and manually interrupted exploration receipts remain visible. All measured arms ran serially. No live MySQL writes, app package rebuilds, or mounted recording modifications occurred.
- Full source/base checksums and before/after code/manifest identities are in `evals/preservation.json`. Scientific `.sqlite` files remain in the private temporary experiment folder and are not copied to this artifact or published to GitHub.
- Reproduction uses the repository's existing Python 3.11.13 / SQLite 3.50.4 runtime. Scripts retain exact source paths and command arguments in logs/receipts. Start with `replay_real.py`, `typed/build_sidecar.py`, `evals/compare_million.py`, and the independent oracle scripts; preserve the safeguards and shared immutable-source packaging.

## Decision

Keep SQLite and this compact typed projection as the candidate for bounded browsing; retain the previously tested batched query for full selected-cell catalogs. The measured upfront index cost buys substantial improvements in small selections and initial pages. Integrate it behind the existing API/DTOs in an isolated testing build, preserve current detail and annotation behavior, and qualify every everyday UI action before merging. Broad filter counts/global summaries should run separately from the initial visible page and can use generation-bound aggregate caches. The complete all-field catalog needs its own projection/cache strategy; this experiment does not establish that it is fast.

DuckDB was not retested on this million real-record corpus. The earlier smaller/synthetic engine comparisons cannot settle its performance here; this result establishes a strong SQLite path without requiring an engine migration.
