# CI failure audit — 2026-10-13

Scope: the 75 most recent GitHub runs (2026-10-08 through the start of this audit),
the latest runs of every configured workflow, current `main` (`8cd6182`),
0.1.10–0.1.13 desktop candidates, and open PRs #64–#66 and #70. Original failed
runs and receipts remain failed; a later fix does not rewrite their evidence.
No app code or immutable release archive is changed by these CI repairs.

## Failure inventory

| Group | Evidence and diagnosis | Disposition |
| --- | --- | --- |
| Bundled runtime manifest | [0.1.13](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/38509543488), also [0.1.10](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/37987655542): isolated linked-export test starts Python with `-I` but no `-B`. `-I` ignores `PYTHONDONTWRITEBYTECODE`. On a disposable 0.1.13 interpreter the test passed while rewriting 43 stale `.pyc` files. | [PR #70](https://github.com/maxwellsdm1867/Rieke-OS/pull/70) adds `-B`. Eleven 0.1.13 linked-export tests and a direct replay of all 801 mapped backend tests passed with all 37,676 Python resources unchanged. Manifest refusal remains strict; the follow-up reports bounded added/removed/changed paths. |
| Contract-only frontend timeout | [Current main](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/38268308719) and [earlier main](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/37987690498) hit the guard's hard-coded 180-second worker deadline. Full frontend regression passes in the current PR. Large backend sets also approached/exceeded this deadline locally. | Mapped frontend/Python workers get a bounded 600-second deadline; desktop remains 180 seconds. Timeout remains failure and now retains partial test output, selected command and deadline. This is a test supervisor bound, not a benchmark performance threshold. |
| Temporary repository cleanup | [PR #65](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/38093374171) failed cleaning a benchmark fixture: `.git` became nonempty during recursive deletion. The log does not identify the writer. Fixture commits permitted detached Git maintenance. | Disable automatic maintenance/GC only in the two owned benchmark fixture repository families; keep cleanup errors fatal. The historical writer is not retroactively proven by this preventive change. |
| Stale waveform UI contract | [PR #66](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/38213781304) spent six 600-second waits across previous/candidate trace actions. Both readiness and canvas-stroke observation read `.value` from a control that became a div. | One fixture-bound adapter supports retained dropdowns, current label-only controls and UUID-bearing stream buttons. It refuses unknown/ambiguous controls. Exact action/epoch/stream, sample endpoints/count/rate/units, post-response drawing and two-frame checks remain. All 13 small-fixture actions pass on pinned source, current main, and immutable 0.1.13 source. See #67. |
| Earlier application ownership violation | [0.1.11 candidate](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/38209276440) rejected `TraceViewer` importing `resourceCache`. | Already repaired in `add33d1`, before 0.1.12. Preserve the boundary check and the ownership explanation in `predicate-trace-boundary.md`; do not widen allowlists. #68 tracks broader development-loop prevention. |
| Earlier desktop observer test cancellation | [0.1.12 candidate](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/38211317227) cancelled pending observer promises under Node 22. | Already repaired by test-only `6418220`. Current scoped desktop and native lifecycle jobs pass. Old tagged test sources remain unchanged. |
| Timing review — updater PR | [PR #64](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/37998127408): trace total 144.1 ms versus previous 112.2 ms, threshold 140.25 ms; first-visible endpoint also flagged. Query correctness and pinned workflow comparison passed. | Genuine review trigger, not a harness exception. Requires a fresh matched comparison; no relaxed threshold or averaged-away original result. |
| Timing review — test-only PR | [PR #70](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/38513802388): tree expansion 443.8 ms versus pinned 352.5 ms, threshold 440.625 ms. Previous-main workflow and both query comparisons passed. | Application files are unchanged from previous main. Preserve the flag and perform a matched repeat; source equivalence alone does not create a passing measurement. |
| Missing diagnostic artifact after earlier failure | Desktop candidates tried to upload core receipts even when tests failed before the core benchmark step. | Upload only if that step actually ran. Missing receipts after an attempted core run still fail. The originating test failure remains visible. |

`Verify source installation` last passed; the signed promotion and legacy manual
candidate workflows have no runs. The old published-package qualification run
was cancelled. Those are unexecuted/cancelled qualification scopes, not evidence
that current releases passed them. #69 is a native project-discovery issue, not
one of these CI failures, and is not closed by this audit.

## Evidence boundaries and follow-up

The local manifest reproduction used a disposable copy of packaged Python, not
the user's installed app. Its first three CI stages passed with no runtime
changes: 126 desktop tests (one local skip for unprovisioned parser source),
13 bootstrap tests, and 68 architecture tests. The fourth stage timed out at
180 seconds without resource changes. A retained direct replay then passed
801 tests in 175.8 seconds; that is separate evidence, not a green guard receipt.

The CI fixture-maintenance change updates the reviewed source-file hash for
`python/tests/test_benchmark.py`. Both dynamic-loader Call AST hashes and their
destinations were independently checked unchanged; loader authority is not
expanded.

The workflow now runs all thirteen actions on a 1,000-row diagnostic fixture
before allocating million-row projects, with 30-second action/setup waits.
Failures stop expensive measurement but are retained as failures. Small-fixture
results do not qualify scale or replace the thirteen measured actions. Normal
performance thresholds, pinned baseline and three-sample measurement remain.

Manual workflow dispatch accepts an optional full `candidate_sha` as well as the
existing `baseline_sha`. The workflow records harness and application revisions
separately, creates an isolated source worktree, and requires matching locked
browser dependencies. This permits new harness checks against an immutable
published source. It does not retag, rebuild, install or replace a release.
Fresh full workflow evidence and outstanding timing dispositions are recorded
in the follow-up PR/run receipts; this initial audit does not claim those
comparisons have completed.
