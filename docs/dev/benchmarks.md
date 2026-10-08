# Fixed version-attached benchmark suite

The single registry is [benchmarks/registry.json](../../benchmarks/registry.json).
The runner is [tools/benchmark.py](../../tools/benchmark.py). It writes
`benchmark.json`, `benchmark.md`, raw subrunner outputs and correctness logs into
a new, never-overwritten output directory. These artifacts are associated with
exact source commit/tree, dirty state before and after, release/database versions,
schema format versions and implementation source hashes, suite source hashes, fixture version/seal, OS, hardware,
Python/SQLite/Node versions and frontend dependency lock. Never copy the result to
another commit and call it current. A documentation commit also changes HEAD.

## Run and compare

Reference backend profile: **CPython 3.11.13** and the fully pinned
[requirements-py311.txt](../../benchmarks/requirements-py311.txt). Create an owned
benchmark environment; do not upgrade the user's application runtime. With `uv`
available, a fresh checkout can use:

```sh
uv venv --python 3.11.13 .rieke-runtime/benchmark-python
uv pip install --python .rieke-runtime/benchmark-python/bin/python -r benchmarks/requirements-py311.txt
npm ci --prefix workspace-app
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark.py run --output benchmarks/results/unique-run
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark.py gate benchmarks/results/unique-run/benchmark.json \
  --commit "$(git rev-parse HEAD)" --app-version "$(node -p "require('./rieke-release.json').version")"
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark.py compare baseline/benchmark.json \
  benchmarks/results/unique-run/benchmark.json --output comparison.md
```

The local diagnostic runs used **Node 24.13.0**; select that exact version to
reproduce their runtime profile. CI retains its existing **Node 22.12.0** profile;
those results are not comparable to the local Node 24 profile. `npm ci` uses the
committed frontend lock. Both candidate workflows now install the same dedicated
Python benchmark environment from the pinned requirements, including SciPy 1.17.1.
If `uv` is unavailable, provision CPython 3.11.13 explicitly, create its venv and
use that venv's `python -m pip install -r benchmarks/requirements-py311.txt`.
Do not substitute an unversioned system Python and call the result equivalent.

`run` returns nonzero for missing/failed/invalid core cases. Correctness failures,
skips, timeouts and missing samples cannot produce a green receipt. Dirty local
runs remain useful but cannot pass the clean-commit gate or comparison. `compare`
returns nonzero with reasons if suite, fixture, schema format versions or environment differ,
including an OS upgrade. The gate independently resolves the expected commit
and reconstructs tree, release metadata, schema versions and source hashes from
Git objects. Matching start/end declarations alone are insufficient. Comparison
also verifies both recorded commits; keep the necessary Git history available.
Suite provenance reads the exact revision's runner path recipe without executing
historical Python. New runners declare literal recipe version 1; the four reviewed
legacy runner blobs are accepted by exact source hash, including the original
recipe without pinned requirements. Unknown legacy bytes, malformed declarations,
missing files and symlink inputs fail closed. Navigation tests may use explicit
nested paths; execution and hashing share those declarations. Historical support
files come from that commit's Git tree, not the current checkout.
Schema source paths are also read from that revision's literal `SCHEMA_FILES`
declaration. Earlier runners without it retain their original flat schema paths
and receipt keys; current runners use the metadata package paths. Neither lookup
imports historical code or rewrites an existing receipt.

The core receipt schema is unchanged. Registry suite version 1.0.5 includes the separate everyday-million and
workflow-million tracks; core cases and sampling are unchanged, but
the registry edit intentionally changes the core suite fingerprint. Retain older
receipts as historical evidence and establish a matched current-suite baseline.
A test relocation changes path keys
and therefore suite identity. Reconstructing an old receipt's original digest does
not make it current or comparable to a different suite; comparison still requires
full suite equality and the gate still checks the current working suite. Preserve
original receipts rather than renaming their paths or rewriting their hashes.

CPU identity, positive logical CPU count and numeric positive RAM size must be
known for gate/comparison qualification. Matching `unavailable` values are not
hardware equivalence. Sandbox-denied hardware reads yield diagnostic-only evidence;
use an appropriately permitted read-only execution context for a fresh run, never
retrofit facts into a previous receipt. There is no comparison against pre-macOS-27.0.1 results
without an explicit noncomparable label. No arbitrary speed threshold is supplied:
four raw samples and medians are observations, not percentiles or a speed guarantee.
Calibrated budgets need reviewed repeated evidence and a future versioned policy.

The Python and Node workers are serial and capped at 180 seconds each. The runner
kills only its own worker process group on timeout. Database files live in an owned
temporary directory, removed by the worker on normal exit. A killed worker may
leave a `rieke-core-benchmark-*` temporary directory; cleanup is unconfirmed and
that receipt fails. The renderer harness does not connect to a live backend.
Core measured wall time is recorded in every receipt; a verified runtime will be
added below after the first successful post-update execution.

Historical integrated development smoke: **13.1 seconds** on macOS 27.0.1 arm64,
Python 3.11.13, Node 24.13.0. This dirty-source run verifies bounded runtime only;
it is not a clean release receipt or calibrated latency baseline. The owned local
benchmark environment used SciPy 1.17.1 because the pre-update shared SciPy native
binary failed to load. Actual Python package versions are captured per run; the
shared application runtime was not modified. The subsequent abff764 runs took
11.13 and 10.43 seconds, but both recorded CPU/RAM as unavailable. Independent
review rejected their qualified comparison. Preserve their raw evidence as
**diagnostic only**; their prior gate result/comparison is superseded. Fresh
permitted-read runs on the corrected commit are required for qualification.

## End-to-end benchmark workflow and module attribution

The required workflow compares the same fixed fixture and thirteen real user-action
variants across implementations, using ordinary elapsed time and exact correctness
checks. Three ordinary samples produce each action median; action totals and the
trace-readiness endpoints determine performance review. `--profile` is an optional
diagnostic for investigating a result. Module timing never gates the ordinary
comparison or blocks optimization. The existing 34-case query suite remains
supporting evidence, not a substitute for action timing.

Historical local runs at source `7ddab479c8d8196118551c78d992dba2deb92726` validated the thirteen cases with a one-million
project and 20,000-epoch active protocol. Their module-profile flags varied; those
flags are historical diagnostic findings, not failed ordinary action totals. They
do not qualify later source revisions or the default million-member active protocol.

The headline boundary is user intent to the correct, current, usable rendered result, including the explicitly requested click-to-trace appearance measurement. Backend request-to-response is a nested measurement. Edit Tree means opening the editor, changing its splits/grouping, and selection/deselection. No passing end-to-end receipt may be inferred from a query-only receipt.

| Action | Headline result | Owners available for optional diagnosis |
| --- | --- | --- |
| Open a protocol view; return to it | Correct current content and usable controls, cold and warm separately | workspace navigation, Inspector, resource/cache lifetime, protocol admission, page reads, React publication |
| Open Edit Tree | Current root branches, counts and controls visible and usable | Inspector/tree presentation, saved layout, initial tree request, scope admission, grouping, response validation, rendering |
| Change tree splits/grouping | Correct regrouped tree and counts visible after adding, removing or reordering a split | protocol-tree-layout, typed-query split definitions, membership reuse/invalidation, metadata projection, grouping, tree-ancestors validation, rendering |
| Expand a tree cell; move to next page | Exact branch/epoch page visible under the current revision | tree-browser, tree-ancestors orchestration/validation, API transport, witnessed tree route, TreePages scope/grouping/projection, JSON encoding, publication |
| Expand cell list; load another page | Exact bounded continuation visible | epoch-browser page read/coalescing, WorkspaceService epoch page, protocol membership, curation/export/annotation decoration, publication |
| Reveal an epoch/ancestor path | Correct UUID visible at the correct offset with current ancestors | column/hierarchy orchestration, target/ancestor requests, scope proof, anchor lookup, grouping, ancestor admission, layout |
| Inspect an epoch | Current requested metadata usable; trace readiness recorded separately | useEpochInspection, metadata/trace cache, epoch API, details, protocol/annotation/export work, cell-count scan, trace decode/draw when applicable |
| Tree selection/deselection | Exact selected UUIDs and current selection summary reflected in the UI | gesture/highlighting, tree-selection or incoming selection queue, bounded membership resolution, freshness checks, selection state, count/type summary, rendering |
| Search with a predicate | Exact current matching results and counts visible after submitting/changing the predicate | typed-query editor, predicate validation/compilation, scope admission, metadata/index query, requested counts, pagination, frontend admission, rendering |
| Prepare Workbench | Frozen proposed cohort prepared and ready to inspect, with correct counts and current authority | preparation request, source/protocol discovery, membership comparison, recipe construction/storage, opening/closing checks, frozen context, initial review reads, rendering |
| Open/return to incoming Workbench | Current frozen cohort ready for browsing; record reuse versus required preparation | queue, preparation reuse/invalidation, frozen context, opening authority, frozen service, tree/list reads, closing authority, renderer admission |
| Click epoch to show its lazy-loaded trace | First correct visible trace, then complete requested visible trace window; two elapsed endpoints from the same click | focus/selection, lazy-load scheduling, cache/coalescing, request admission, source verification, bounded waveform read, decode/transfer, frontend validation, trace drawing/frame observation |

The table maps action families and possible diagnostic owners; it does not add
cases to the fixed thirteen-variant suite below. Additional presentations, split
operations, selection gestures, predicate distributions, preparation invalidation
and trace cache/supersession/scroll cases remain unmeasured. These gaps do not block
comparison or optimization of measured actions. Trace readiness must identify the
correct epoch/stream and requested window; a previous epoch's trace cannot qualify.

Each action receipt preserves ordinary elapsed samples, exact correctness/readiness
checks, cold/warm state, request count, fixture/source identity and raw evidence.
Compare only matching fixtures, protocol sizes, runtimes and harnesses with each
source identified. A loading indicator or stale result cannot finish an action.

Use `--profile` only when stage/module evidence would help explain a result. Its
separate instrumented pass can report backend cProfile and React costs; these are
diagnostics, not required comparison fields or additional performance gates. Keep
profile overhead separate from ordinary action samples. Backend work is nested
inside transport latency and parallel work overlaps, so do not sum those durations
into action wall time. DOM/RAF readiness and canvas calls do not prove compositor
paint. Unmeasured native/seal/recovery boundaries remain explicit; profiling cannot
supply missing qualification.

### Run the end-to-end core workflow

`tools/benchmark_workflow.py` runs an owned Flask fixture, actual product React
components in an owned browser, and a request ledger. Optional `--profile` adds
module diagnostics. It writes
`receipt.json`, `workflow.html`, `workflow.md`, and raw browser/server evidence.
The current core measures thirteen variants: main open/return, Edit Tree open,
cell expansion, next epoch page, split removal, incoming select/deselect,
cell-equality predicate search, fresh Workbench preparation, receipt replay, prepared return, and lazy trace
inspection. Full App navigation, additional split operations, range/queued
selection, other predicate distributions, preparation invalidation and trace
supersession/scroll remain explicitly unmeasured; a core pass does not cover them.

Provision the pinned Python/Node runtime above and the committed frontend and
desktop dependency locks. Playwright comes from the desktop development dependencies.
On a new owned CI checkout use `npm ci --prefix desktop --ignore-scripts` and
`node desktop/node_modules/playwright/cli.js install --with-deps chromium`.
On a development machine, an explicitly supplied Chrome executable may be used;
its actual version is recorded and must match the comparison run.

```sh
# Small composition diagnostic: never qualifies as a million-epoch measurement.
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark_workflow.py run \
  --smoke --output benchmarks/results/workflow-smoke-unique
# Actual million epochs; three ordinary action samples, without profiling.
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark_workflow.py run \
  --source-root . --output benchmarks/results/workflow-candidate-unique
# Run the same current harness against a clean retained source checkout first.
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark_workflow.py run \
  --source-root /absolute/path/to/baseline --output benchmarks/results/workflow-baseline-unique
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark_workflow.py compare \
  benchmarks/results/workflow-baseline-unique/receipt.json \
  benchmarks/results/workflow-candidate-unique/receipt.json \
  --output benchmarks/results/workflow-comparison-unique.json
```

Add `--profile` to `run` for a separate diagnostic pass when investigating a
result; ordinary runs and comparisons do not require it.

For simple built-in operation timings, add `--module-timing` instead. This enables
module-local tic/toc during ordinary samples, without an extra phase or cProfile.
The existing benchmark request logger collects records via `X-Disco-Timing: 1`;
raw per-request records stay in `requests.jsonl`, and reports show inclusive
per-call medians and call counts. Nested calls overlap and are not additive.
Nineteen operations in seven modules currently cover metadata exploration, tree,
history, service, Workbench preparation/review and trace workers; this is not
all-module coverage. Timings are optional diagnostics, not performance gates.

Use `--browser-executable /absolute/path/to/chrome` when needed. Each source
checkout needs its own matching dependency resolution. Reusing installed modules
is allowed only after the corresponding package locks match; do not compare
baseline code silently linked against different frontend dependencies.

By default all one million project epochs belong to the active protocol: 999,900
main epochs and 100 pending incoming epochs across 10,000 cells. Use
`--protocol-epochs 20000` for the CI profile: the project still materializes one
million epochs, with 19,900 main, 100 incoming and 980,000 ambient epochs outside
the active protocol. Pass the same value to both comparison runs. Project size,
active-protocol size and pending-cohort size are recorded and checked separately;
a subset-protocol pass does not qualify a million-member active cohort. Two tiny
owned waveform ramps support trace validation.

Each fresh preparation sample resets the owned fixture to its verified
post-import snapshot outside the action clock, retaining warm metadata. Fresh
preparation must return HTTP 201; remounting and preparing again measures HTTP 200
receipt replay with the same operation and candidate. This is distinct from
backend reuse under a new operation, which has a separate contract test. The
prepared-return action retains the frontend session. Predicate editor setup waits
for initial summaries before measuring search. Neither preparation nor replay may
select or merge the proposed cohort. Transactional SQL, metadata-index admission and
projection, and source verification are explicit doubles; request composition,
predicate evaluation, frozen preparation, browsing, and UI controls run production
code. This is not native database, production-index, installed-package or raw-parser
qualification. Metadata-request H5 access fails; only the owned trace route may
open the owned waveform file, with access recorded per request.

Ordinary browser action time is the headline. Optional backend cProfile
function/module self-time, inclusive time, calls and React render durations remain
separate diagnostic evidence. Their variation or coverage changes do not fail the
ordinary comparison, and no profile calibration is required before optimization.

The runner owns all worker processes, enforces time/RSS limits, records cleanup,
and shares the query benchmark's serial lock. Failed readiness, missing actions,
wrong UUIDs/counts/trace windows, tampered evidence, mismatched runtimes and unknown
cleanup cannot qualify. Comparisons check ordinary action medians and trace
endpoints using provisional review thresholds; retain improvements as well as
regressions. Dirty-source runs remain development diagnostics; repeat the final
committed source before delivery.

## Required everyday query check after every app update

After **every application update and each implementation iteration**, run the
existing fixed core correctness suite above and the separate `everyday-million`
query track below. This is a development regression requirement, including updates
whose intended effect is not performance. Product optimization does not justify
skipping either check. Missing, failed, partial or incomparable evidence is not a
green iteration. The [everyday-million workflow](../../.github/workflows/everyday-million.yml)
enforces this query track on every pull request and push to `main`/`master`, with
no path filter. It also runs the fixed core and complements the existing workspace correctness
workflow; stress receipts remain separate from release-gate inputs.

The one registry remains [benchmarks/registry.json](../../benchmarks/registry.json),
under `stress_tracks.everyday-million`. The core remains small; do not substitute
the million-row track for its correctness or release checks. Use the pinned
Python environment above, without `-O`, and unset `RIEKE_TEST_DOM_MODULE`. Coordinate
machine load and run core and stress sequentially. The stress runner serializes
its own invocations across checkouts; its lock does not coordinate unrelated jobs.

Retain **two immutable source references**: the reviewed pinned regression baseline
and the immediately previous iteration. Never advance the pinned baseline merely
because a candidate is slower. Record both exact SHAs with retained results. Use
clean detached checkouts for these references; do not point at a moving development
checkout. A dirty candidate can provide diagnostic evidence, but rerun the final
committed candidate to associate the check with the delivered source. Do not edit
source or harness during a run.

From the candidate checkout, after provisioning the pinned environment, set the
two variables to the reviewed full commit SHAs. The following creates owned
baseline checkouts and unique result directories; all four stress runs use the
**same current harness and interpreter**, importing application code from the
specified source checkout:

```sh
(
set -e
# Supply real full SHAs before running this block.
: "${EVERYDAY_BASELINE_SHA:?Set the pinned regression baseline commit}"
: "${EVERYDAY_PREVIOUS_SHA:?Set the immediately previous iteration commit}"
unset RIEKE_TEST_DOM_MODULE
EVERYDAY_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
EVERYDAY_BASELINE_DIR="../disco-everyday-baseline-${EVERYDAY_RUN_ID}"
EVERYDAY_PREVIOUS_DIR="../disco-everyday-previous-${EVERYDAY_RUN_ID}"
git worktree add --detach "$EVERYDAY_BASELINE_DIR" "$EVERYDAY_BASELINE_SHA"
git worktree add --detach "$EVERYDAY_PREVIOUS_DIR" "$EVERYDAY_PREVIOUS_SHA"
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark.py run \
  --output "benchmarks/results/${EVERYDAY_RUN_ID}-core"
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark_everyday.py iteration \
  --baseline-source "$EVERYDAY_BASELINE_DIR" --source-root . \
  --output "benchmarks/results/${EVERYDAY_RUN_ID}-pinned"
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark_everyday.py iteration \
  --baseline-source "$EVERYDAY_PREVIOUS_DIR" --source-root . \
  --output "benchmarks/results/${EVERYDAY_RUN_ID}-previous"
)
```

Run each command only after the preceding command succeeds; retain and investigate
any nonzero result before continuing. On the first iteration the two baseline
references may be identical, so one matched iteration is sufficient. Each
`iteration` runs baseline then candidate, with tree then typed workers in each,
and writes `baseline/receipt.json`, `candidate/receipt.json`, raw lane JSON/logs
and `comparison.json`. Preserve the complete directories, including failures;
results under `benchmarks/results` are ignored by Git. Retain them as build/CI
artifacts or in an owned evidence directory, with the source references. Do not
commit a receipt into the commit it purports to measure. Existing baseline
checkouts may be reused if their clean state and exact SHAs are verified.

`run --source-root PATH --output NEW_DIRECTORY` measures one source for diagnosis.
`compare BASELINE_RECEIPT CANDIDATE_RECEIPT --output NEW_JSON` rechecks retained
worker evidence and requires the current harness/configuration and matching
recorded environment. Prefer `iteration` for new claims so both sources are
measured serially in the current environment. A harness, fixture, registry or
runtime change requires fresh matched measurements of both retained source
references and the candidate; never rewrite historical receipts to make them fit.

The comparison exits 2 for a provisional review trigger: query/setup medians over
the larger of baseline +25% or +5 ms, or peak worker RSS over the larger of +20%
or +64 MiB. Investigate and repeat a matched pair under controlled load; preserve
the flagged run. Do not average it away or silently replace the pinned baseline.
Exit 1 covers invalid, failed or incomparable evidence. Exit 0 means these fixed
cases passed their exact-result/refusal checks without crossing these triggers;
it is not proof that every everyday interaction avoids regressions.

### CI enforcement and retained baselines

The everyday-million workflow runs harness validation tests, then the original
pinned source `34ce2e06dec0e2886d5a2310f21e02cf818cb646`, previous source and candidate
serially using one current harness and pinned CPython environment on one Ubuntu
runner, then runs candidate fixed-core correctness with Node 22.12.0 and the
committed frontend lock. Candidate stress measurement is shared by both comparisons. For pull requests,
previous means the PR base SHA and candidate is GitHub's checked-out merge commit;
for pushes, previous means `event.before`. A first push whose before SHA is all
zeros explicitly falls back to the pinned source. Manual dispatch accepts an
optional full `baseline_sha` for the previous comparison, defaulting to the
candidate's first parent; it never silently changes the pinned regression SHA.

Both comparisons and the subsequent fixed core run execute even if an earlier
stress measurement/comparison fails or flags a regression. Any failed measurement,
invalid comparison or provisional regression trigger fails the job. Raw receipts,
logs, comparison JSON and selected source references upload with `always()` and
30-day retention, including failed runs. Preserve important baselines beyond the
artifact expiry in owned evidence storage. The job has a 30-minute timeout; a
timeout is incomplete evidence, never a pass. Workflow presence does not configure
GitHub branch protection: require this job in repository rules if merge blocking
is desired. CI Linux results do not compare to local macOS results or qualify the
installed native app. Runner image/runtime changes require fresh matched runs.

### What actual one million means here

Each worker constructs **1,000,000 actual deterministic metadata records**, with
10,000 cells and 50,000 blocks. This is not extrapolation from a smaller fixture.
The tree lane invokes production WorkspaceService/TreePages methods for first and
repeated roots, next/deep pages, cell opening/scrolling, anchor and ancestor columns,
return navigation, split changes and bounded selection. Its admission/catalog is
synthetic and the service rows are constructed in memory. The typed lane populates
real million-row SQLite relations in memory and inherits production typed-query
methods for pages, explicit membership/source scopes, cell/block scopes, filters,
details, counts, groups and preview. Its disk ownership/seal admission is replaced.
These seams exclude production project loading, catalog discovery and index builds.

Coverage is deliberately narrow: one source/date/protocol/cell type, exactly 100
epochs per cell and 20 per block. The tree primarily splits by cell, with a
`date,cell,block` split-change case; recorded-metadata splits, a few very long
cells, missing typed values and joint distributions are absent. `typed.membership`
measures a page query supplied with a million-member scope, not the output of
`membership()`. Exact detail checks establish fixture consistency, not parser
qualification. Typed methods bypass HTTP and Workbench scope composition;
renderer queues, mutations, production builds/seals, recovery and native H5 are
outside this lane.

Expected UUIDs, rows, groups, counts, cursors and refusal behavior are checked
outside query timing. First tree root has one sample; subsequent operations have
three. Setup time and peak worker RSS are reported separately. Workers run serially
with 600-second and 4-GiB RSS limits; missing cases, wrong scale, failed oracles,
H5 access attempts and changed source/harness fail. Source hashes include tracked
and untracked application files. Environment matching is limited to the fields
recorded by this runner and does not establish identical machine load or thermals.

This is metadata-only **synthetic query stress evidence**. No waveform is read.
It does not qualify native SQL/disk behavior, HTTP, renderer paint, UI interaction,
startup, index build/sealing, mutation/recovery, import/export, packaged apps or
release promotion. The existing core and native release blockers remain intact.

## What the first slice measures

Six real SQLite operation cases reuse `tools/metadata_qualification` CoreAdapter
and sealed native truth. Exact source-derived results are checked before timing
and after each sample; the check itself is excluded. Four serial fresh-reader /
same-reader pairs measure detail, scoped first/deep page batches, filter batches,
exact membership batches and requested facets (two/all eligible fields). One
untimed smoke is excluded. Cold means a fresh typed reader, **not** dropped OS disk
cache, new native server or cold H5. Reader initialization and fixture construction
are separately reported setup work. Fixed small batches are not per-row timings.

Mounted App/Protocol/Inspector cases measure first mount and recent Overview →
Inspect return on a fixed 500-row mock API. Content and current-membership gates
are separate. Module transforms are excluded; React work and mock request handling
are included. One fresh-harness smoke is excluded, then four fresh harnesses.
Trace child rendering, native browser layout/scroll/paint, H5 and server latency
are absent. Polling granularity can affect short timings. This supplementary UI
measurement cannot fulfill `ui.native.navigation`.

Selected tests separately check scoped restoration, cache reuse/invalidation,
StrictMode, lazy trace context, current page membership/tag changes, frozen export,
real disposable SQLite roundtrip and small synthetic import identity/collision guards. Their total test
execution time is not application latency. Native SQL tag throughput, ingestion
throughput and waveform portability are not inferred from transactional doubles.

## Release integration and deliberate blockers

The desktop candidate workflow runs the core after its runtime/dependencies exist
and packages JSON/Markdown receipts. `tools/desktop_release.py promote` requires
those files and calls the exact-commit **release** gate before any publication
mutation. It also adds the validated report files to the published asset set.
Local test/dev commands are unaffected. Missing, dirty, stale or failed results
are rejected. Changing a report's top-level status cannot replace its case evidence.

The initial release gate intentionally refuses complete qualification because the
registry still lists native navigation, native tag latency and end-to-end ingest
throughput as unsupported. Resolve those with actual owned fixture adapters and
reviewed registry changes; do not remove the requirement merely to release.
The reusable [native observer](../../benchmarks/navigation-probe.mjs) has no launch
side effects; [its contract](../../benchmarks/NATIVE-CONTRACT.md) explains the
missing launcher, fixtures, independent authority, H5 and lifecycle checks.
Historical restoration results do not qualify a different commit or this suite.

Retain reviewed run artifacts with each release, and link changed cases to the
release notes explaining addressed bottlenecks. Generated files are ignored under
`benchmarks/results`; attach CI artifacts before publication. Avoid committing a
receipt into the very source commit it claims to measure (a self-reference).

## Database and field-access design

[Database portability and benchmark spec](schema-portability-benchmark-spec.md)
contains the code-backed design and proposed stress/adaptive cases. Registry IDs
are authoritative; the note's proposed names are advisory. Universal field access,
slow correct fallback, extraction-incomplete status, generalized JSON import,
metadata-only export and Attach Traces remain explicit gaps. Current 164 eligible
fields are not all raw fields: depth/length/type discovery limits remain. Index
tiers may change speed, never whether scientific fields are accessible. No engine
replacement or adaptive implementation is part of this benchmark slice.

[Stress track](../../benchmarks/stress.md) stays separate from the fixed core;
its everyday-million lane is required after app updates as described above. Project/workspace
organization is a deferred follow-up; this work does not reorganize user projects.

Schema-changing work must bump the relevant FORMAT/SCHEMA_VERSION and fixture/suite semantics as appropriate. Implementation source hashes are provenance, not automatically schema incompatibility; ordinary query optimizations remain comparable when formats, fixtures, harness and environment match.

Legacy source-candidate diagnostics upload with `if: always()` before the complete release gate and signing. An expected unsupported-native failure therefore still preserves the run JSON, report and logs.

`RIEKE_TEST_DOM_MODULE` must be **unset** for benchmark runs (even an empty value is rejected). The runner refuses to launch any worker with that override and retains a failed diagnostic receipt. A dynamically imported external DOM module is not covered by the committed suite or installed-jsdom version and cannot silently qualify.


## React 19 and native research attachments

Suite 1.0.3 runs both frontend commands with the committed
`workspace-app/src/test-support/reactTestEnvironment.js` preload. Its exact bytes
are part of the suite hash; environment overrides remain prohibited.

Native research receipts remain attributed to the commit actually measured.
Create a separate attachment (never edit or retrofit the native receipt):

```sh
python tools/benchmark_native.py --evidence-root /owned/research \
  --measured-commit <full-measured-sha> --candidate-commit <full-candidate-sha> \
  --source-receipt source.json --report report.md --output native-attachment.json
python tools/benchmark_native.py --evidence-root /owned/research --verify native-attachment.json
```

The source receipt must contain its original `commit`. Every selected file is
hashed, path escapes and symlinks fail, and Git must show only the fixed list of
infrastructure/test/documentation changes between commits. The tool checks byte
integrity and restricted source equivalence, **not** scientific assertions in the
reports. The attachment is separate from the core receipt and has no power to
satisfy release requirements. Native tag latency, ingestion throughput and full
navigation qualification remain unsupported. Retain private ledgers privately;
explicitly select sanitized reports for any distributable attachment.

Packaged test launchers select the configured output beneath
`desktop/dist/mac-arm64`, verify the bundle/executable path, and clone it into the
owned test HOME. Pinned electron-builder gives `mac.executableName` precedence
over `executableName` and `productName`: the current configuration produces
`Disco.app`, with executable, internal name and displayed product name Disco. The launcher does not search
installed applications or fall back to a differently named bundle. This path check is not packaged-content qualification;
`verifyPackagedSource` and an explicitly coordinated package smoke remain required.

### Combined Workbench first-page evidence

The workflow readiness oracle accepts either the existing standalone epochs
response or the combined prepare/context response's `bootstrap.page`. Combined
pages must match the current action, prepared candidate and scope, project,
protocol, binding, generation and initial-page shape. Both forms retain the exact
ordered UUID/count oracle, rendered membership readiness and two RAF observations.
Captured requests remain actual transport requests; the harness creates no
synthetic epochs GET. The fixture and action inventory are unchanged.

This oracle change alters the harness hash. Rerun retained baseline, previous
version and candidate with the same updated harness before comparison; old
receipts remain attributed to their original harness. Lightweight refusal checks
remain in `node --test benchmarks/workflow/browser-readiness.test.mjs`.
