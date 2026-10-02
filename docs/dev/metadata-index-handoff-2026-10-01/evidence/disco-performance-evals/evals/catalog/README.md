# Scoped catalog experiment

The baseline is commit `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`.
The current native 100,000-epoch contrast preview took about 3.90 seconds. Its
complete scoped catalog retains exact per-field statistics and suggestions; it
must not substitute registered/global statistics for the selected scope.

The first candidate changes only reads of the existing immutable SQLite format:

* Unrestricted connections use an ordered view of the existing epoch identity
  index instead of inserting every epoch into a temporary scope table. Explicit
  scopes still retain first-occurrence order and ignore duplicates/unknown IDs.
* Scoped value statistics and within-cell variation are each aggregated together
  instead of issuing a separate aggregate query for every metadata field. True
  subsets drive indexed epoch lookups; a full generation keeps SQLite's automatic
  join order because forcing scope-first was slightly slower in that case.
* Suggestions reuse that scope connection and the exact canonical stored JSON
  strings. Previously each suggested column built another temporary scope and
  decoded then encoded its values. Existing joint projections are reused.

No public API fields, saved membership, fingerprints, revision rules, index
format, acquisition data, annotation storage or UI behavior change.

## Reproduce the microbenchmark

Run serially outside the native/browser evaluation window. Use the baseline's
already sealed synthetic index; no index rebuild is included in these timings.

```sh
PYTHONDONTWRITEBYTECODE=1 python -B docs/dev/performance-evals-2026-10-01/catalog/compare_catalog.py \
  --index /private/tmp/disco-everyday-bench-20261001/metadata/100000/index.sqlite \
  --output docs/dev/performance-evals-2026-10-01/catalog/comparison.json
```

The script reads the baseline implementation with `git show` into a disposable
module, opens the same verified generation for each implementation, measures one
first and three warm observations, and requires the complete catalog and exact
predicate result JSON hashes to match. This is a component microbenchmark,
excluding HTTP serialization, MySQL, saved membership construction and browser
rendering. The native and browser evaluation receipts remain the end-user gate.

## Scientific contract checks

The focused existing suites and two added tests passed (65 tests): disk index,
catalog optimization, predicates, combinations, compact explorer, catalog
identity and catalog collision. New coverage compares complete catalogs and
predicate catalogs to the independent in-memory implementation for reordered
scopes, duplicates/foreign IDs, empty scopes, Unicode, integer/float/boolean
representations, missing versus recorded null, aliases, coincident protocol
axes, history/generic joint fields and missing cell identities. Existing tests
retain checksum refusal, immutable generation identity, lazy details, concurrent
readers and bounded choice behavior.

## Measured iterations

These serial observations reused the exact same 185 MB sealed 100k index. A
contrast predicate selected 20,000 epochs. Each main microcomparison took one
first and three warm observations; medians below use the three warm samples.
No native or browser benchmark ran concurrently. These small samples describe
this machine and fixture, not a general p95 or a million-epoch qualification.

| Micro action | Baseline | First aggregate candidate | Scope-first subset candidate |
| --- | ---: | ---: | ---: |
| Complete selected catalog | 3.347 s / 3.290 s¹ | 2.388 s | 1.350 s |
| Exact contrast predicate match | 344 ms / 328 ms¹ | 214 ms | 204 ms |

¹ Baseline was rerun independently in each comparison. Complete catalog and
predicate result hashes were identical in both iterations. Receipts are
`comparison-aggregate-first.json` and `comparison-scope-first.json`; their module
hashes identify each measured candidate before the final plan-selection rule.

The first aggregate candidate still let SQLite scan the complete reverse-value
index, probing membership for every relation. Explicit `CROSS JOIN` made scope
drive epoch lookups and reduced the selected catalog median by about 59% against
its paired baseline. Removing unrestricted temporary scope copies reduced
predicate matching by about 38% without changing matching logic.

The additional plan check used two observations per variant, including one warm
observation, and required complete hash parity:

| Explicit scope | Automatic aggregate plan, warm | Forced scope-first, warm |
| --- | ---: | ---: |
| 60 epochs | 277.5 ms | 2.9 ms |
| Entire 100k generation | 6.571 s | 6.904 s |

The full-generation forced plan was about 5% slower in this narrow diagnostic;
the final implementation uses automatic join order whenever actual selected
count equals the immutable generation count. This preserves the fast subset
plan and avoids that observed full-generation penalty. Its SQL and JSON contract
are otherwise unchanged. The final native/browser measurements must evaluate
that complete candidate; the microcomparison's 1.35-second catalog still misses
the intended sub-250-ms preview interaction target.

`scope-plan-check.json` preserves the plan observations. To reproduce the two
forced variants from the current source without editing production files:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B docs/dev/performance-evals-2026-10-01/catalog/check_scope_plan.py \
  --index /private/tmp/disco-everyday-bench-20261001/metadata/100000/index.sqlite \
  --output docs/dev/performance-evals-2026-10-01/catalog/scope-plan-check-repeat.json
```

The owned diagnostic process has a 90-second cap. No source, user profile or
acquisition data is written, and all readers close when the test completes.

## Original versus final full-generation read

The plan-choice check above was followed by a comparison of the original
implementation against the final candidate on all 100,000 selected epochs.
Independent owned Python workers ran serially on the same sealed generation,
with one first and two warm observations per implementation. The complete JSON
hash matched: `2eb40ffbb36a8d58962611aaf3e8d0bee4adaa84271b5dd0989a56b7ff50c65f`.

| Full selected catalog metric | Original a8fa | Final candidate |
| --- | ---: | ---: |
| First observation | 9.653 s | 6.583 s |
| Two-observation warm median | 9.366 s | 6.544 s |
| Maximum warm observation | 9.583 s | 6.588 s |
| Whole-worker peak RSS | 400.84 MiB | 410.64 MiB |

The final full-scope read improved by about 30%, with a modest observed peak
memory tradeoff of 9.80 MiB (2.4%). Peak RSS uses the operating system's
whole-process maximum, including imports and verified index opening; separate
workers prevent the first implementation's allocations from contaminating the
second peak. Post-action RSS samples were much smaller and varied because
macOS may compress/page memory; they are preserved separately, not presented as
the peak. Three total observations are insufficient for a tail-latency claim.

This test computes the full scoped catalog with registered known-field templates.
It does **not** time an index build or recompute the unscoped persisted catalog
during sealing. Those remain separate evaluation requirements before claiming
no regressions in import/build performance.

Receipt: `comparison-full-generation.json`. Reproduce with a parent deadline of
90 seconds across the two owned worker processes:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B docs/dev/performance-evals-2026-10-01/catalog/compare_full_catalog.py \
  --index /private/tmp/disco-everyday-bench-20261001/metadata/100000/index.sqlite \
  --output docs/dev/performance-evals-2026-10-01/catalog/comparison-full-generation-repeat.json
```
