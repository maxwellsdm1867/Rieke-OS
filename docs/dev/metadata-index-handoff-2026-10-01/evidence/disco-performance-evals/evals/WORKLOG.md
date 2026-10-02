# Performance experiment work log

This work uses isolated branch `codex/performance-evals`, based on measured source `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`. First source candidate: `eb1e73e2ea4af821ddc73b957568f13746dd9b8f`. The original dirty checkout, running Disco project, installed app and shared database were not selected as experiment targets. All new database/browser processes and data are disposable, use separate ports/profiles and are stopped by their owning harness.

## Frozen evaluation contract

Historical raw receipts, SHA-256 manifest and metric IDs are in `baseline/`, `baseline-manifest.json` and `metrics-baseline.json`. Fresh same-day native and browser observations establish a paired baseline on this machine. API observations and browser completion remain different metrics. First use, steady state, initial metadata indexing, dense annotation migration and ordinary reopen are not conflated. Setup singleton results are descriptive; repeated-action median regressions require both a 20% relative and 20 ms absolute increase, with sample-count warnings. Correctness, source stability, native contract and zero legacy-oracle fallback are hard checks. New evaluations preserve the old operation IDs.

## Hypotheses and implementations

1. Tree scope preparation creates decorated copies and a full epoch-by-field projection for every navigation depth, then hashes full membership. Its large projections are often declined by the bounded cache. The first candidate borrows existing structural date/cell/block fields, uses the checked raw protocol membership reader and shares an exact scope across navigation depths. Group and summary caches have an explicit 16 KiB–4 MiB reservation charged to the existing 64 MiB scope budget. This remains Python grouping and retained basic rows, not database cursor paging.
2. Scoped catalog calculation repeats joins/statistics per field and reconstructs temporary ID scopes while comparing grouping suggestions. The first aggregate candidate computes field statistics and within-cell variation in batches and reuses canonical indexed JSON signatures on the same connection. Full-generation reads use a view over the ordered identity table instead of copying all IDs into a temporary table.
3. The first scoped aggregate plan still scans unrelated values. A scope-first CROSS JOIN was measured and kept for true subsets. For full generations the forced plan was about 5% slower than automatic planning, so the candidate retains the automatic plan there. Complete catalog hashes matched in every diagnostic iteration. Against original full-generation catalog code, final automatic aggregates improved 9.366 s to 6.544 s (three observations), with worker peak RSS increasing 400.84 to 410.64 MiB. Component receipts and limits are in `catalog/`.

No metadata format, acquisition data, SQL authority, scientific export contract or frontend production source was changed in this first source candidate. Arbitrary predicates, tag/joint/dynamic grouping and custom policy adapters retain the authoritative general path. Cursor paging, source-at-a-time imports and removal of retained full metadata rows remain future experiments.

## Review and adjustments before timing

Independent review identified three issues in the first tree candidate, all corrected before the candidate native/browser evaluation:

- Custom query/filter policies or mismatched binding-header providers could be bypassed. The structural path now verifies exact supported method/provider semantics; unproven policies use the uncached general reader. Tests cover bound subsets, changed membership and three custom policy wrappers.
- Lazy group summaries allocated after cache admission could escape the reservation. Summaries are now computed and charged before admission; an independent recursive allocation test checks the actual retained cache against the accounting.
- A structural scope could retain the entire previous row dictionary after refresh. Successful publication clears navigation scopes immediately, including unchanged-index refreshes. Failed integrity validation preserves the last published generation. Weak-reference tests check cache release.

Final integrated checks after these fixes: 196 Python tests passed in 6.630 s across tree pages, navigation lifetime, disk index/crash handling, catalogs/identity/collisions, predicates/combinations, compact explorer, layouts, protocol state, native tag filtering and refresh. Expected audit-failure injection logging and an existing export-file ResourceWarning appeared; the test run passed. The command/log is saved with experiment receipts. Whitespace validation passed.

## Harness repairs and interpretation

The older standalone native metadata harness used `RIEKE_USER_PREFERENCES_PATH`, which is not the product's actual preference-directory override. The fresh baseline only read settings, but project creation could leave an empty uniquely named creation lock in the default preference directory. No author settings, project index or user project contents were changed. All subsequent runners set actual `RIEKE_PREFERENCES_DIR` and `RIEKE_PROJECT_INDEX` to owned temporary paths as well. This limitation is recorded instead of claiming every historical filesystem access was confined.

Browser summary samples were sorted, so treating their first element as first-use latency would incorrectly report the minimum. The comparison now uses chronological raw measurements. Client-unloaded actions may see warm server caches; added disjoint-cell/block actions explicitly check branches not expanded by the native prelude.

The historical `api_contrast_filter_preview` requests `summary_only:true` with the default full scoped catalog. Actual MetadataExplorer filter/results flows already request `catalog_summary:false`; the expensive metric applies to full catalog/layout analysis. Its ID and request contract remain unchanged for regression comparisons. A lightweight-preview diagnostic is separate and cannot be substituted for the old full-catalog metric.

## Evaluation status

All native, browser, dense-tag and trace regression families completed and passed. RESULTS.md records the complete comparison, paired lightweight diagnostic and fresh index build. The failed initial 10k sandbox receipt was accidentally selected as the baseline by filename; the hard gate caught it, the successful permitted receipt replaced that selection, the failure was preserved separately, and manifests/metrics were regenerated. No candidate operation was changed to conceal a regression. Larger-scale capacity and fresh-index build qualification are not implied by the 100k navigation improvement.
