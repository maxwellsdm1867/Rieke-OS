# CI lifecycle research — 2026-10-14

Recommendation: shorten the current full comparison by removing orchestration waste first. Keep exact correctness, million-row workloads, both baseline comparisons, and release qualification. A separate fast iteration tier is useful, but moving full performance checks to nightly changes when regressions are caught; it is not equivalent protection on every commit.

This is research and a proposal, not an implemented policy. Inspected checkout: `d61e53971d61594d834800aafe23bff840dfb1e0`. No workflows or benchmark code were changed. The newer performance/publication PRs may have different baseline SHAs; reconcile those before implementation.

## What other projects actually do

* CPython's normal test workflow runs on PRs and main/release pushes. It detects change categories, cancels superseded runs, fans out independent jobs, and collects them in a required final status. This is concrete precedent for orchestration and affected-category selection, not evidence that a tiny smoke suite replaces broad correctness. [CPython workflow](https://github.com/python/cpython/blob/main/.github/workflows/build.yml)
* CPython also runs strenuous platform buildbots. Some expensive reference-leak builds run periodically because they take hours; maintainers can request buildbots on a PR. Thus some assurance is deliberately later or on demand, with failures still owned and investigated. [CPython buildbot lifecycle](https://devguide.python.org/testing/buildbots/index.html)
* Faster CPython exposes separate benchmark dispatch with an optional merge-base comparison and retains raw results, distributions, and comparisons to reference releases. Its runner infrastructure supports dedicated self-hosted machines. This separates performance investigation from the ordinary test loop. [Benchmark usage](https://github.com/faster-cpython/benchmarking-public), [runner infrastructure](https://github.com/faster-cpython/bench_runner)
* Their published A/A experiment found shared-cloud noise materially larger than controlled-machine noise and recommends remeasuring base with head on shared runners. Those particular numeric error rates are **not** Disco error bars, but the experiment directly argues against replacing today's matched baseline with yesterday's hosted-runner timing. [Faster CPython A/A investigation](https://github.com/faster-cpython/ideas/issues/480)

## Disco's measured budget

The completed [run 38530930681](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/38530930681) took 1,190 seconds. Its locally retained timing reconstruction is `/Users/maxwellsdm/Documents/Codex/disco-recipe-copy-measurements-2026-10-14/ci-runtime-breakdown.json`.

| Work | Observed time |
| --- | ---: |
| Checkout and dependencies | 46 s |
| Harness validation | 20 s |
| Worktrees and three small compatibility runs | 27 s |
| Three backend suites | 776 s |
| Candidate core | 30 s |
| Three browser suites | 283 s |
| Comparisons, upload, cleanup | about 4 s |

Within backend time, fixture construction is 218 seconds and measured operations are 524 seconds; they are components, not additional time. Across versions the tree family totals 253 seconds and typed-query family 515 seconds. This is repeated workload cost, not principally npm installation or a remote database connection.

The checked-out [everyday workflow](../../.github/workflows/everyday-million.yml) serializes every family and version on one runner and lacks concurrency cancellation. [Workspace CI](../../.github/workflows/workspace-ci.yml) already cancels superseded PR runs and performs some category selection. The [benchmark contract](benchmarks.md#required-everyday-query-check-after-every-app-update) explicitly requires matched baseline/candidate checks after every app iteration. Altering frequency or scope therefore requires an explicit contract change, not merely editing YAML.

## Recommended order

1. **Cancel superseded PR runs.** Scope the key to workflow and PR; preserve deliberately requested exact-source qualification runs. This saves wasted work and queue time, not the duration of one uninterrupted run. A canceled revision has no passing receipt. GitHub supports workflow/job concurrency and cancellation; workflow-specific keys avoid canceling unrelated work. [GitHub concurrency](https://docs.github.com/en/actions/using-jobs/using-concurrency)
2. **Parallelize families on separate runners, keep source comparisons together.** One job measures tree for pinned/previous/candidate serially; another does typed queries for all three; another does browser workflows for all three. Do not put candidate on one host and baseline on another or run competing benchmark processes on one host. Aggregate all required receipts and fail on missing, canceled, invalid, or regressed lanes. Existing comparison/receipt code needs inspection and possibly a lane-aware contract before this works. The observed slowest family is 8.6 minutes; a roughly 10–12 minute total is an arithmetic planning estimate, **not a measured promise**, including provisioning/validation. Runner minutes may increase because setup is duplicated. CPU isolation matters for reproducible timing. [pyperf system guidance](https://pyperf.readthedocs.io/en/latest/system.html)
3. **Deduplicate identical source identities.** The existing workflow deduplicates previous=pinned for browser runs but still repeats the backend run. One receipt can satisfy both comparison roles only when full source SHA, harness, dependencies, fixture, runtime and measurement contract are identical. Do not deduplicate merely because two branches have similar names or similar results.
4. **Consider immutable fixture reuse after profiling copy cost.** Cache a verified disposable seed, keyed by generator/fixture/schema/index/runtime compatibility, and create isolated writable copies. Validate identity and integrity before use; miss or mismatch rebuilds. Keep a fresh-build check for generator/index/migration changes and preserve cold/warm semantics. A cache cannot bypass candidate index-building code if that is under test. Maximum recoverable backend setup in this run is 3.6 minutes before transfer/copy/verification; after family parallelization, savings on the critical typed lane are about 3.45 minutes at most. Dependency caching alone attacks only part of the 46-second setup. GitHub caches are immutable per key and allow partial restores, so a benchmark seed must reject incompatible fallback restores. [GitHub caching semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)

## Optional lifecycle change after those improvements

| Stage | Proposed responsibility | Limitation |
| --- | --- | --- |
| Every active edit / PR update | Existing correctness/build/architecture checks; candidate million-row exact-result/refusal checks; browser action smoke; targeted tests for the changed owner | A single candidate run does not establish a small timing regression against a baseline |
| Merge-ready revision | Full matched million-row comparison, all families, both references, current harness | Must bind to the actual tested source; a later source change invalidates the receipt |
| Periodic main audit | Full correctness, broad performance history, slow/native/leak cases selected by contract | Detects problems later; requires an owner and a halt/fix policy |
| Publication | Exact clean candidate plus native/artifact/data-integrity qualification | A Linux million-row pass is not installed-app/native qualification |

This tiering is a design option, not a recommendation to silently weaken the existing every-iteration rule. The strongest initial option is retaining full scope while reducing wall time through family parallelism. If faster preliminary feedback is desired, expose it separately from full qualification. Preserve deterministic tests for the actual regression mechanisms (unnecessary scope rebuilds, invalidation, recipe mutation/isolation); timing alone is a noisy oracle.

If affected-test selection expands, use explicit dependency ownership, fail unknown paths into full checks, and require full coverage for schema/runtime/shared cache/GC/harness/workflow changes. Keep a final required status that validates intentional skips. GitHub warns that whole-workflow path filtering can leave required checks pending. [Trigger/filter semantics](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)

Do not solve the latency by weakening thresholds, deleting worst-case million-value cases, treating one sample as equivalent to repeated measurements, caching green verdicts across sources, or moving everything to nightly without acknowledging delayed detection. Validate an orchestration change with identical-source A/A runs and a retained known regression: it should remain comparable in the former and still flag the latter. Report both critical-path elapsed time and total runner minutes, plus cache hit/miss and canceled-run counts.

## Independent suite audit and staged implementation recommendation

A separate read-only suite audit confirmed that the two large suites are not
substitutes. The backend exercises real million-row SQLite typed readers; the
browser fixture substitutes index admission/projection and uses a 20,000-member
protocol within a million-row project, while checking real route/component,
Workbench, selection and trace completion. Both sets of correctness oracles remain.

Start with a smaller orchestration change: keep the complete backend suite together
on one runner and run the complete browser suite on another. Each runs all three
source versions serially. This preserves existing per-family receipt formats and
projects **14–15 minutes** total from the measured critical path. It is an estimate,
not a completed benchmark. Standard correctness already reports in about six minutes
in parallel. Cancellation of superseded PR runs and exact-SHA deduplication add
savings only when their conditions occur.

The more ambitious **10–12 minute** estimate above additionally separates tree and
typed-query workers. Current backend receipts require both lanes and compare a
single environment including host identity, so this needs an explicitly versioned
per-lane provenance/aggregation design. It cannot be implemented merely by merging
JSON from different machines. Missing or failed lanes must fail the aggregate gate.

A rapid-iteration policy can keep standard correctness on every push and require
full matched current-head performance before merge/publication, with early explicit
performance runs for relevant edits. This changes detection timing on intermediate
pushes; a correctness-only pass must say performance is pending/unqualified. A ready
PR flag alone is not a scheduling design—subsequent pushes to a ready PR must either
rerun full qualification or invalidate its previous pass until explicitly rerun.
Unknown/shared/harness changes should retain conservative coverage.

Retain both a fixed reviewed baseline (cumulative regression detection) and a
previous accepted source (change attribution). Automatically advancing the only
baseline on every push could allow a sequence of subthreshold slowdowns to accumulate.
A fixture cache also needs source-owned schema, CORE_COLUMNS, equality encoding,
decoding and generation fingerprints, not merely a dataset filename. Building a
cached fixture through one version and silently using it for another may hide the
very compatibility problem being tested. Fresh-build coverage remains separate.

No scheduling, coverage, threshold, receipt or publication policy changed in this
research task. Validation for an implementation should include identical-source
A/A behavior, a known retained regression, missing-lane refusal, exact-source gate
checks, and elapsed/runner-minute measurements. Existing failure receipts stay intact.

## Accepted implementation follow-up

The user subsequently approved the three initial scheduling improvements:
automatic superseded-PR cancellation, exact-SHA reuse within a run, and complete
backend/browser families on separate runners. The `benchmark_ci.py` orchestration
and updated workflow implement those changes with a final fail-closed aggregate.
Tree and typed-query workers remain together, and all source roles, cases, samples,
thresholds and publication requirements remain. Independent review and executable
small-fixture scheduling/refusal tests cover the new orchestration. Real CI timing
and cancellation evidence are recorded in the implementation PR after execution.
Further per-lane splitting, fixture caching, and changes to test frequency remain
proposals; the 10–12 minute estimate is not claimed as achieved by this change.
