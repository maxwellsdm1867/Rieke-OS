# Isolated CI frame-scheduling diagnostic

This branch is disposable diagnostic infrastructure. **Never merge its replacement
`everyday-million.yml` into main or the release branch.** Release application source
remains clean `61881e87e2fe07f1d317ec92e42827243cfec9fa`; pinned comparison source is
`4de896f2e0b4ea966b5a428c3d2314f93fba935f`. Both are separate immutable worktrees.
The workflow checkout supplies only the diagnostic harness.

The registered workflow path is reused only so manual dispatch on this branch is
possible. It has no PR/push trigger, inputs, aggregate, publication, or qualification
artifact. It runs one macos-15 job with a 15-minute wall limit and one separately hosted
Linux candidate-only attribution job with a 20-minute limit. Approval of this diff
is separate from push/dispatch. No automatic retries are configured.

## Predeclared measurements

Two pairs, sequential, maximum 12 samples total. Each pair uses the unchanged
B0,C0,C1,B1,B2,C2 order, including both first traces. Each role owns one independent
persistent browser; each sample gets its normal fresh context.

1. A/A: final618 in both roles; baseline-role browser launches first.
2. Baseline/final: pinned4de versus final618; candidate browser launches first.

The second pair reverses the browser launch slot relative to both failed CI runs.
It is **not a same-process source crossover**. That remaining confound limits causal
claims. No warmup omission, added sleep, browser flags, source modification, fixture
change or threshold change is permitted. Exact source/dependency identities, all
six geometry/cursor oracles, request counts and cleanup contracts remain enforced.

## Instrumentation and evidence

The original `armAction`, `geometryReadiness`, exact scientific oracles and Python
validators/comparator are unchanged. A passive wrapper records existing RAF callback
entry/exit, scheduled time, frame timestamp, action identity and visibility/focus;
it schedules no additional callbacks. The original readiness function runs once,
then the wrapper records request/control/draw/status/width predicates. These duplicate
predicate reads introduce explicit diagnostic overhead and may cause layout work.
Caps per page: 512 callback events, 128 readiness snapshots, 64 visibility entries,
128 longtask entries. Failures retain partial logging. No CDP profiling or counters
are added to this experiment; GPU/OS CPU time remains unmeasured. Actual process
spawn arguments and PIDs are retained from the existing browser owner.

Both arms explicitly declare `timing_mode: diagnostic`. The unchanged qualification
comparator must refuse them. The workflow checks that exact refusal after separately
validating complete correct clean-source receipts and the original paired ownership
contract. `diagnostic-result.json` reports scientific correctness and completion;
it does not report a release timing pass. Timing endpoints remain available in raw
receipts. The artifact is named `trace-frame-DIAGNOSTIC-ONLY-*`, never a standard
proof/family/aggregate name. Hashes, branch/commit, fixed protocol and limits are
written before dependencies/builds/sampling.

The existing fixture/server/browser owner handles orderly failures and signals;
its tests cover detached browser cleanup and source-startup failure. A failed
correctness, infrastructure, source integrity or cleanup check stops the schedule.
The workflow preserves compact evidence with `if: always()`. A hard runner/job
termination can still prevent upload, which remains missing evidence rather than
success. Runner-owned generated data disappears with the job; no real project or
installed application is touched.

## Predeclared interpretation

- If identical final-source roles differ, source alone cannot explain that pair;
  inspect role/PID/launch slot and callback cadence.
- If the reversed-launch pair makes baseline slow, launch/process scheduling gains
  support. If delay follows candidate, inspect the recorded predicate/task phase.
- Timely callbacks with false predicates point to concrete readiness work. Missing
  callbacks after a ready draw with no longtask support scheduling/graphics
  starvation, but do not identify its OS/GPU cause.
- No reproduction leaves the original two CI failures unresolved. It does not
  authorize another automatic qualification rerun or waive the release gate.

Local validation: 169 lightweight Node logger/scheduler/oracle checks and 18 existing
Python receipt/refusal/lifetime checks passed. Workflow YAML, all shell blocks and
embedded Python parse. These checks did not launch browsers, servers or benchmark
builds while the separate million-row worker was active.

## Separately approved Linux attribution job

The second job checks out exact 618 as the application in a separate worktree.
The diagnostic branch supplies the existing harness with a passive GC observer
added only to `benchmarks/workflow/backend_timing.py`; all benchmark commands,
source code, fixture definitions, action order and comparison policies stay fixed.
It runs the existing 1M/20k workflow once with explicit `--runtime development
--profile`: three ordinary DEVELOPMENT samples followed by one profiling pass,
not production timing. GNU timeout sends SIGINT after 12 minutes with 30 seconds
to run the existing owner cleanup before force termination; overall job cap is
20 minutes. This is backend/module CPU attribution only. No comparisons, repeated
backend family, retries, upscaling or production-latency claims are authorized.
The separate `linux-development-DIAGNOSTIC-ONLY-*` artifact retains raw action,
request, module/profile and environment receipts/logs, including partial failure.
Generated runtime/dist/H5/database bytes are omitted from uploads. This job does
not use the modified macOS trace harness. The harness commit and GC observer hash
are recorded separately from the immutable application source.

The passive GC callback records each collection's generation, start/stop wall
time, collector-thread CPU and process CPU for every request active at collection
start. It names the collecting thread so other-thread GC cannot be confused with
the HTTP thread's CPU. Each request stores at most 64 detailed intervals plus
uncapped scalar generation totals and dropped counts; O(1) `gc.get_count()` and
`gc.get_freeze_count()` snapshots accompany request wall/thread/process CPU.
No `gc.collect`, enable/disable/freeze/unfreeze/threshold mutation or `get_objects`
walk is performed. Callback errors and collections still active at request finish
are explicit missing-attribution evidence. The existing install/restore owner
registers/removes only its callback, preserving others; teardown retires request
ownership. GC totals overlap request totals and concurrent requests, so they must
not be added together. Six small tests cover intervals, cross-thread attribution,
caps, pending/error evidence, teardown and callback/policy preservation.
