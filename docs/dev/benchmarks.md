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

The core receipt schema is unchanged. Registry suite version 1.0.7 added the separate everyday-million and
workflow-million tracks 1.0.8 adds the diagnostic route-million track and 1.0.9 the diagnostic
workflow-app track; core cases and sampling are unchanged, but
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

The required workflow compares the same fixed fixture and fifteen real user-action
variants across implementations, using ordinary elapsed time and exact correctness
checks. Three ordinary samples produce each action median; action totals and the
trace-readiness endpoints determine performance review. The default runtime compiles
the exact owned shell with production React and retains the existing Vite API
proxy. `--runtime development --profile` is an optional diagnostic for investigating
a result; development receipts cannot qualify the production gate. Module timing never gates the ordinary
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
cases to the fixed fifteen-variant suite below. Additional presentations, split
operations, selection gestures, predicate distributions, preparation invalidation
and trace cache/supersession/scroll cases remain unmeasured. These gaps do not block
comparison or optimization of measured actions. Trace readiness must identify the
correct epoch/stream and requested window; a previous epoch's trace cannot qualify.

Each action receipt preserves ordinary elapsed samples, exact correctness/readiness
checks, cold/warm state, request count, fixture/source identity and raw evidence.
Compare only matching fixtures, protocol sizes, runtimes and harnesses with each
source identified. A loading indicator or stale result cannot finish an action.

Use `--runtime development --profile` only when stage/module evidence would help
explain a result. Its
separate instrumented pass can report backend cProfile and React costs; these are
diagnostics, not required comparison fields or additional performance gates. Keep
profile overhead separate from ordinary action samples. Backend work is nested
inside transport latency and parallel work overlaps, so do not sum those durations
into action wall time. DOM/RAF readiness and canvas calls do not prove compositor
paint. Unmeasured native/seal/recovery boundaries remain explicit; profiling cannot
supply missing qualification.

### Run the end-to-end core workflow

`tools/benchmark_workflow.py` runs an owned Flask fixture, actual product React
components in an owned browser, and a request ledger. Explicit
`--runtime development --profile` adds diagnostic module profiling. It writes
`receipt.json`, `workflow.html`, `workflow.md`, and raw browser/server evidence.
The current core measures fifteen variants: main open/return, Edit Tree open,
cell expansion, next epoch page, split removal, incoming select/deselect,
cell-equality predicate search, fresh Workbench preparation, receipt replay, prepared return, and lazy trace
inspection plus frozen Workbench 300,000- and 1,000,000-sample Whole traces. The latter validates all consecutive bounded windows (20,000 or 100,000 samples each; opt-in batches at most 500,000 samples), every ramp sample, exact source and scoped request identity, and final draw/DOM readiness. Existing thirteen variants remain present. Workflow fixture v4 and suite 1.0.7 intentionally require matched fresh receipts; historical v2/v3 receipts are not comparable. Full App navigation, additional split operations, range/queued
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

`compare` flags a median over the larger of baseline +25%, +5 ms or one 60 Hz
display frame (+16.7 ms, plus 1 ms timer margin). Browser timings resolve to whole
frames, so a short action moving from two frames (33.3 ms) to three (50.0 ms) is
within measurement resolution; two extra frames are still flagged.

Use `--runtime development --profile` for a separate diagnostic run when
investigating a result. Production React does not provide ordinary Profiler
callbacks, so `--profile` with the default production runtime fails before setup.
Development runs retain their actual React profiling data but are marked
`diagnostic` and refused by the qualification loader and comparison command.
`--module-timing` remains available in production: its custom request header and
backend spans are independent of React Profiler.

The production build writes the unchanged `fixtureSource(meta)` shell, with a
separate attestation module, into an owned output directory. It does not mount the
full App or substitute `src/main.jsx`. The same Vite HTTP server and API proxy
serve only allowlisted compiled assets; development transforms/client scripts are
not exposed. Build-only source/dependency symlinks are removed on success and
failure. Each sample attests production React, exact fixture hash and loaded local
assets before and after its actions. Bundle/fixture hashes are source-specific
provenance, outside the equality-compared browser environment.

This is a prospective runtime change motivated by observed development-only
owner-stack quota resets and associated CPU work. Historical development failures
remain attributed to their original harness; they are not relabeled or waived.
Fresh complete pinned, previous and candidate runs under this production harness
are required. All fifteen variants, three ordinary samples, scientific oracles,
request capture and the 25 percent/5 ms comparison policy remain unchanged.
Production mode does not remove frame scheduling variance or qualify native
package performance.

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

### Full-App decoupling variants (diagnostic `--suite app`)

`tools/benchmark_workflow.py run --suite app` uses the same runner, owned server,
production build, raf-aligned click observer, two-frame readiness gate and
request correlation as the fixed core. The browser loads the real product
bootstrap (`src/main.jsx`), so the App's own change wiring
(`useWorkspaceChanges`, typed events where a source has them, the merge-undo
controller, focus/visibility listeners and retained tab panels) decides what
each action re-reads. Only the launcher project inventory and a stored tag author
are owned doubles, added by `server.py --suite app`. The core server and its
fifteen variants are unchanged.

Per sample, after untimed setup (open the protocol's Inspect tab and focus epoch
2, which has no streams), the suite measures:

- `curation.toggle` ×3: the focused row's include toggle, with exact `aria-pressed` state and a completed `POST …/curation`
- `epoch.step`: Next epoch after those curation writes, and again after `tag.add` (adding an epoch tag); readiness is the focused row label and the epoch counter
- `view.tab_return`: Overview, then back to Inspect, with nothing changed
- `focus.return`: a synthetic hidden→visible `visibilitychange`, `blur` and `focus` while Edit Tree shows an explicit Cell 1 path; `path_kept` is recorded but does not gate readiness
- `workbench.merge_all`: the Overview "Hold to merge all" gesture (the one-second hold is inside the elapsed time) through the merge receipt toast
- `workbench.undo`: through "Merge undone"

Every action reports elapsed time, in-action requests and bytes (from
`Content-Length`), cancelled reads (`AbortError`, recorded and not counted as
failures), and requests started within a fixed 1.5 s quiet window after
readiness. Periodic App pollers are listed by path and counted separately in
`trailing_foreground_counts`. `--smoke` uses 2,000 epochs. The track has its own
registry entry (`workflow-app`, fixture `workflow-owned-v4+app-v1`); receipts
compare only with the same suite, and it is not part of the required CI families.

## Harness compatibility before expensive comparisons

CI first runs `tools/benchmark_workflow.py run --smoke` for the pinned, previous
and candidate sources with the same harness and locked browser dependencies.
All fifteen actions use a 1,000-row owned fixture and 30-second action/setup
waits. A failed compatibility check stops the expensive lane with retained
failure receipts; a passing check is diagnostic only. Full million-row results
and unchanged comparison thresholds remain required.

The trace adapter supports historical dropdowns and current single-stream labels
or pressed stream buttons. Single-stream identity is bound to the independent
fixture descriptor inventory, never guessed from the latest response. Both
canvas observation and visible readiness use this adapter. The existing
`benchmarks/workflow/browser-readiness.test.mjs` fault tests cover incompatible
controls, wrong identities/values, incomplete windows and stale drawings.

Manual dispatch may supply a full `candidate_sha` to check immutable application
source with the workflow's harness, along with `baseline_sha` for its previous
comparison. Pinned source stays fixed; receipts record both app and harness
identities. See [the CI failure audit](ci-failure-audit-2026-10-13.md) for the
observed failures, fixes and qualification boundaries.

## Required everyday query check after every app update

After **every application update and each implementation iteration**, run the
existing fixed core correctness suite above and the separate `everyday-million`
query track below. This is a development regression requirement, including updates
whose intended effect is not performance. Product optimization does not justify
skipping either check. Missing, failed, partial or incomparable evidence is not a
green iteration. The [everyday-million workflow](../../.github/workflows/everyday-million.yml)
enforces this query track on pull requests and pushes to `main`/`master`, except
committed comparisons containing only Markdown files. Those still validate
catalog references; code, configuration, unknown and harness paths retain the full
track. Manual dispatch always runs it, including exact-source release checks.
It also runs the fixed core and complements workspace correctness. Publication
requires successful exact-source stress comparisons in addition to, never instead
of, the existing native/artifact release qualification.

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

The everyday-million workflow resolves its pinned, previous and candidate source
SHAs once, then runs the complete backend and browser families on separate Ubuntu
runners. Within each family, distinct sources run serially with one current harness
and pinned runtime; baseline and candidate timings never come from different hosts.
The backend retains both tree and typed-query lanes. The browser family also runs
candidate fixed-core correctness with Node 22.12.0 and the committed frontend lock.
All cases, samples, exact-result/refusal checks and comparison thresholds remain.

The integrated candidate retains the reviewed heap-corrected pinned source
`a16c915f9730384af3285949bb962d12707ccf01`. For pull
requests, previous means the PR base SHA and candidate is GitHub's checked-out merge
commit; for pushes, previous means `event.before`. A first push whose before SHA is
all zeros falls back to the pin. Manual dispatch accepts an optional full
`baseline_sha`, defaulting to the harness's first parent, and an optional explicit
candidate SHA; it never silently changes the pin. An explicit candidate override
uses a diagnostic aggregate check name and cannot supply the normal current-head
qualification status.

Each family measures an identical source SHA once in that run. Candidate is the
canonical role if it shares a SHA with a baseline; otherwise pinned precedes
previous. Raw receipt directories are copied unchanged into their role aliases,
with the original source/provenance fields and matching byte digests. Both baseline
comparisons still run. This is same-run reuse under the same harness, fixture and
runtime, not reuse of an earlier run's timings or inferred tree equivalence.

Only automatic pull-request runs cancel earlier runs for the same PR. Push and
explicit manual qualification runs have distinct concurrency groups and are not
cancelled by later PR updates. Cancellation never supplies a passing receipt.

Both comparisons run even if an earlier measurement fails or flags a regression.
Browser compatibility checks precede large browser allocations; core and browser
measurements retain their failures independently. Each family uploads its raw
evidence, and the final aggregate requires both successful families, matching
source plans, unchanged alias bytes, all four passing comparisons and successful
core evidence. A missing, skipped, cancelled or failed family cannot qualify. Raw receipts,
logs, comparison JSON and selected source references upload with `always()` and
30-day retention, including failed runs. Preserve important baselines beyond the
artifact expiry in owned evidence storage. Each measurement family retains a 90-minute safety timeout; a timeout is
incomplete evidence, never a pass. Workflow presence does not configure
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

## Million-epoch backend route track (diagnostic)

`tools/benchmark_routes.py` measures request paths that the everyday query lanes
do not exercise: the production Flask routes, `WorkspaceService`,
`ProtocolStateReader`, `TreePages`, `CurationStore`, `SharedAnnotations` and the
Workbench pending pool, over the owned workflow fixture
(`benchmarks/workflow/server.py`) with its synthetic index replaced by a real
sealed `DiskMetadataIndex` and the typed sidecar that production refresh prepares
after sealing (`typed_lifecycle.prepare`). Request bodies mirror the UI: tree pages
send `counts_only`, explicit filters and 60-row pages; previews and runs send
`catalog_summary: false`. Full-statistics tree roots, catalog-summary previews and
the untyped explore-page fallback are separately named cases. The service runs as the exact `WorkspaceService` class (the
fixture subclass only overrode refresh and events, which stay counted doubles),
and its read model is published the way refresh publishes it: deep-frozen maps
via `publish_frozen` when the source revision has it, so publication-serial
fast paths engage. The production `StateGenerationAuthority` runs with its leaf
SQL replaced: schema attestation is a counted constant, and generation rows and
the `app_annotation_changes` feed are in-memory doubles that SQL-double writes
advance exactly as `trigger_manifest()` does (INSERT once, UPDATE twice, change
rows upserted at the final generation), so `shared_changes` returns real deltas.
The SQL double journals each transaction's own writes for rollback instead of
deep-copying every table, and the route fixture skips the browser preparation
reset snapshot; both previously doubled memory and write cost at a million
epochs. No H5 file may be
opened after fixture construction; traces are a separate path.

```sh
# Small composition check (seconds per case, never a million-row claim).
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark_routes.py run \
  --profile smoke --source-root . --output benchmarks/results/routes-smoke-unique
# Matched baseline then candidate at the registry default profiles.
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark_routes.py pair \
  --baseline-source /absolute/path/to/clean-baseline --source-root . \
  --output benchmarks/results/routes-pair-unique
```

Default profiles are 1,000,000 project epochs with a 1,000,000-member protocol,
the same project with a 20,000-member protocol, and 100,000/100,000. Work that
scales with the target stays flat across the first two and grows only with the
protocol; work that grows from 100k to 1M with an unchanged target is project
scaling. Cases cover epoch detail inside the protocol, protocol pages, overview,
tree root/expand/next page/column batch/selection and a shared-tag filtered tree,
text search, a selective UUID-prefix lookup (one row) and an explicitly named
match-all prefix (linear by construction), predicate fields, explore page and preview for
equality, `ne`, `exists`/`missing` on a built-in and on a partly missing recorded
field, ranges, protocol tags, shared and effective tags, tag times and AND/OR,
explore run, summary jobs with polling, curation toggle (with and without its
batch read), curation and approval followed by the next epoch read, page and
tree reads, epoch tag writes followed by reads and overview, and the Workbench
queue, summary, merge-all (with paired undo), undo and the queue after undo.

Each case records one cold/first request and three warm requests, response bytes
and attestations per request, then one separate cProfile pass whose call counts
(SQLite statements, deep copies, predicate row evaluations, protocol-state
witness and metadata reads, refreshes, scope builds, SQL-double reads/writes and
transactions) never touch the timed samples. No production class method is
replaced, so identity-checked fast paths remain eligible. Receipts record the
load average before and after each profile and every 30 seconds during it.

`compare` flags medians and cold samples over the larger of baseline +25% or
+5 ms, lists count increases separately, and reports predicate-count changes on
`expected_by_contract` labels (the missing-value semantics of B11) as contract
changes rather than regressions. Fixture UUIDs are regenerated per run, so
response hashes are not compared. SQL doubles copy rows on every transaction and
scan linearly, so write latencies overstate native costs; use counts for writes.
This is synthetic route evidence, not native MySQL, HTTP transport, renderer or
release qualification, and it is not part of the required CI families.

`run` and `pair` wait for the shared stress lock instead of failing: they log
`waiting for stress lock held by …` every 30 seconds, record their own
pid/start/command in the lock file while they hold it (clearing it on exit), and
accept `--lock-timeout SECONDS`. The flock remains the only exclusion; the
other runners still take it without waiting.

Profiles marked `grouped` (1M/1M and `smoke-grouped`) run the registry
`case_groups` (explore/search, workbench, reads and decisions) in separate
worker processes with fresh fixtures, so each group stays under the 6 GiB cap
and reports its own peak RSS; base and candidate share the grouping.

Scaling evidence: run `--profile 10k-protocol-10k --profile 200k-protocol-200k
--profile 200k-protocol-10k`, then `tools/benchmark_routes.py scaling RECEIPT
--output scaling.json`. It reports per case the warm median and key counts at
both sizes, the 200k/10k ratio, the inferred class from the ratio exponent (≈1×
flat, ≈20× linear) and the project-only ratio (200k project, same 10k protocol).
The counting pass also records `sqlite.vm_steps` (SQLite virtual-machine steps
via a progress handler, a load-independent proxy for rows scanned and sorted),
so work done inside one SQL statement is visible. Everyday clicks are expected
flat; whole-project search predicates and exports (`scaling.linear_allowed`)
may be linear. `/api/explore/page` (`explore.page.*`, `explore.page_next.*`) is used only by
`tools/metadata_qualification`, not the UI, so it may be linear; its untyped tag-predicate
loop is a known qualification-tool cost. The UI result path (`explore.run.*`,
`explore.results_first/next.*`) is expected flat. The protocol-tag fixture seeds at least
121 tagged epochs at every size so its result pages are full. A flat-expected case that
grows in time or counts, or with project size alone, is flagged, as is any
superlinear case; the command exits 2 when anything is flagged.

At one million epochs the typed sidecar build exceeds its in-app RSS budget
unless the measured source includes #110 (`claude/typed-index-budget`). Build
1M candidate trees with #110 merged. A base that lacks it measures the untyped
explore fallback at 1M; say so beside any 1M base comparison rather than
treating the typed-path difference as the candidate's own gain.

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

The trace observer records completion of the actual Canvas stroke and the second
stable DOM/RAF observation before that observation's independent correctness
work. The receipt reports correctness validation after the observation separately.
First-observation validation can still delay the second RAF; this remains an
explicit observer overhead, and neither endpoint claims compositor presentation.
Binary bodies are independently decoded from the actual consumer's ArrayBuffer;
no cloned response is read and no product decoder supplies the oracle.

### Synthetic click phase

Both browser lanes use `raf-aligned-click-v1` for every measured synthetic click.
The page reserves the action, waits for a real animation-frame callback, rechecks
target connection, enabled state and action ownership, and stamps intent immediately
before `element.click()`. All synchronous handler work remains in elapsed time.
Scheduling wait is separately recorded; dispatch has a bounded 15-second timeout.
The dispatch frame cannot earn readiness credit. The existing exact readiness
oracle must succeed on two later distinct animation frames, and a pending or
incorrect observation resets its streak. Readiness keeps its existing timeout.

Receipts bind the dispatch protocol, frame timestamp, wait and observation clock
to each sample and reject missing, old or inconsistent evidence. Elapsed time and
ordering use only the recorded `performance.now()` samples. The RAF callback
argument identifies its rendering frame; it is not ordered against a separately
sampled `performance.now()` value. Run 38853576552 exposed a 0.1 ms difference
in the opposite order, and its failed receipt remains preserved. The correction
removes that unsupported cross-API ordering predicate without adding a tolerance,
changing elapsed values or changing the dispatch protocol. Finite nonnegative
frame identity and the page observer's two later distinct actual frames remain
required. See the [HTML rendering timestamp algorithm](https://html.spec.whatwg.org/multipage/webappapis.html#update-the-rendering)
and [High Resolution Time coarsening rules](https://www.w3.org/TR/hr-time-3/#sec-coarsen-time).
This controls the
synthetic input dispatch to an actual browser frame callback. Callback delivery can
lag its frame timestamp, so this does not guarantee a full frame budget or eliminate
scheduling variance. The fixed traced diagnostic did not demonstrate reduced
variation. It does not characterize arbitrary real-user input phases or promise
compositor presentation. Sample counts,
cold cases, exact membership/trace/cursor checks, median and maximum gates and
thresholds remain unchanged. Earlier failed receipts remain failed and attributed
to their original harness. A new matched ordinary run is required for qualification.

## Canonical prepared geometry lane

`tools/benchmark_prepared_geometry.py pair --baseline-source BASELINE --source-root CANDIDATE --output NEW_DIR`
uses the current committed harness against two explicit application checkouts. It
adds one separate three-sample prepared Workbench trace case; the fifteen existing
workflow variants and their baselines remain unchanged. The fixture has 1,000
synthetic metadata rows, a 200-epoch protocol and a real one-million-sample gzip64
H5 response (`quantity` little-endian f64, `units` S10). SQL tables are explicit
doubles. Source SHA verification, sealed metadata index, prepared capability,
DTM1 endpoint, production React and real Canvas paint run together.

The host smoke builds the same native C source with strict floating-point flags
and requires ABI 4 and actual native admission. Linux's host helper is not a
macOS release artifact; desktop deployment checks remain unchanged. The HTTP
server is threaded Werkzeug, not packaged Waitress. Setup warms owned files and
prepares metadata outside the trace clock. Both isolated source servers and both
production builds finish before two independent pinned Playwright Chromium headless-shell
browsers start, one per source. Six fresh browser contexts then run in the fixed order B0, C0, C1,
B1, B2, C2. Each source retains exactly three samples, including its first trace;
no warmup, outlier removal, retry, alternate browser or tolerance change is allowed.
Each context uses only its source's origin, production bundle, fixture and server;
its existing cumulative native admission counters remain source-local.

This controls build/browser startup and source ordering as measurement confounds while
preserving each source's independent first-trace browser graphics state.
Hosted diagnostics showed long idle RAF gaps in both unchanged baseline and
candidate, with compositor ticks continuing; full Chromium and headed alternatives
did not establish a fix. An earlier shared-browser diagnostic retained every sample but could give the
first source a unique graphics initialization cost; that protocol was rejected.
Interleaving independent browsers does not establish that hosted frame scheduling
is deterministic or replace an earlier failed gate. The paired protocol requires
fresh ordinary evidence; the earlier serial receipts remain historical evidence.

The pair receipt binds a fresh pair ID, both source commit/tree/file digests, the
identical browser version and distinct source-owned browser instances, exact completed order and each source's sample ordinal and
execution index. Missing, duplicated, reordered, mixed-pair or changed-source
samples fail comparison. Builds unlink their owned `src`/`node_modules` symlinks
before source-end attestation and upload, without changing the linked sources.
Timeout/cancellation preserves partial receipts and closes both owned servers and
the browser, including its separate POSIX process group. Compact proof uploads
precede larger raw artifacts. The standalone `run` command remains diagnostic;
its unpaired receipts cannot qualify the canonical comparison.

Ordinary runs, including the three-sample CI lane, send no trace timing header.
For a separate diagnostic run, `PREPARED_GEOMETRY_TIMING=1` enables
`X-Disco-Trace-Timing: 1` and records the existing display responses' `Server-Timing`
headers by exact action and URL. It does not read an extra body or issue an extra
request. The browser environment records `timing_mode` as `ordinary` or
`diagnostic`; comparisons reject different modes along with other environment
mismatches. Preserve diagnostic receipts separately from ordinary latency claims.
The receipt records post-stroke, first RAF and second RAF observations, not
compositor presentation. The page arms its observer before click intent and
requires two distinct actual RAF callbacks with the existing geometry-ready
condition. It closes request capture and timestamps completion in that second
callback. Driver retrieval only reads the completed result; its lag is recorded
separately under `observer`. Delayed retrieval cannot add time or observations.
This changes the earlier driver-started polling contract, so historical receipts
must be retained and compared only under their original harness; qualification
requires fresh matched measurements. Frame scheduling delays can still occur. An independent scalar oracle verifies every selected
source index and f64 point byte, whole-source statistics and actual Canvas path
coordinates after observation. The matched lightweight observer records Canvas
path coordinates in both runs.
The exact cursor then demands one 20,000-sample raw tile and checks every value
against the source and the rendered readout. No whole raw waveform request is
allowed during initial display. Missing prerequisites, fallback geometry,
incomplete samples and cleanup failures are failures.

`pair` writes `baseline/receipt.json`, `candidate/receipt.json` and
`comparison.json` under its output. `compare BASELINE/receipt.json CANDIDATE/receipt.json --output comparison.json`
recomputes the same paired comparison. It requires clean unchanged sources, the
same complete paired protocol, ordinary timing, identical harness, dependencies, fixture and
environment. Two matching diagnostic timing modes still cannot qualify. Locked dependencies use the existing workflow identity: only the
root application version is omitted so a version bump can be compared with its
predecessor; transitive versions, integrity fields and Python requirements remain
exact. Raw lockfile hashes are also retained in each receipt. It applies the existing workflow policy (greater of 25% or 5 ms)
to median and maximum post-stroke, first-RAF and second-RAF observations. One slow
sample therefore cannot be hidden by an unchanged median. Fault tests cover a
single slow sample, first-frame-only regressions and missing foreground evidence.
There is no universal 50 ms CI target: hosted hardware and browser observations
are distinct from the installed application's native measurements.

Both Linux and the required `macOS foreground trace regression` job compare the
verified fix `4de896f2e0b4ea966b5a428c3d2314f93fba935f` with the resolved candidate,
in the fixed paired order on each host using the same current harness. This deliberately tightens
the trace baseline from the older, slower a25b437 implementation; it does not
change the pinned million-query or fifteen legacy workflow baselines. The v2
fixture additionally requires explicit foreground admission and counts actual
foreground native-entry calls with zero default-entry calls. Removing the route
flag, reverting the native dispatch or falling back fails correctness independently
of timing. Both receipts must contain that execution evidence.

The macOS job runs the candidate's native worker-QoS and prepared-admission tests,
including a deterministic test that fails if the worker priority request is
removed, verifies no caller/background promotion, and checks exact decoding when
the priority request fails. Candidate overrides use their own immutable source
and retain the workflow's diagnostic-only aggregate name. The normal required
aggregate fails when the macOS job fails, is cancelled or is skipped. Every job
preserves logs and partial receipts on failure. Compact same-run/attempt trace
receipts and the comparison are uploaded separately for the bounded publication
checker; the full trace diagnostics remain in their own retained artifact. Linux
geometry follows the same split: byte-identical compact receipts stay with the
browser family, and full geometry fixtures/build diagnostics upload separately.
Publication recomputes this same comparison through the geometry runner
(importable as `tools.benchmark_prepared_geometry`); both package and direct-script
imports use the same reviewed `benchmark_workflow` policy owner.

Three-sample maxima are a tail-sensitive smoke check, not a universal tail bound.
The deterministic worker/admission checks protect the specific scheduling fix;
the exact geometry, cursor and request-count oracles protect against the earlier
sequential raw-request regression. This lane uses SQL doubles and host-compiled
helpers, not native MySQL, packaged Waitress or compositor instrumentation, and
does not grant release qualification. Local standalone diagnostics may select
an explicit executable with `PREPARED_GEOMETRY_BROWSER`; paired qualification
rejects an executable override and requires the lock-pinned Playwright Chromium
headless-shell distribution. The two browser identities must be distinct and
share that pinned launch configuration and version.
