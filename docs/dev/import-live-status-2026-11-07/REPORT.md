# Import and interaction regression investigation — 2026-11-07

Starting installed source: `deb76e619ec5276fa4de745f34bedbf7026196df`, DISCO 0.2.10.
The shared primary checkout is historical. GitHub main was independently read as
`1c3f657883343f7b87d4b345404cfb1b9f4e8b37`; it is not the installed app baseline.

## Observed import behavior

The native Import page showed one queued file and historical completed jobs, with
no newly created backend import job. Clicking Refresh jobs released the queue.
The resulting job `722436f8-d0ed-4764-bbec-19fb11ff63b0` imported
`2026-11-04_F.h5`; its progress receipt confirmed catalog commit with 744 epochs,
2 cells, 967 responses and 744 stimuli. Native history showed the validation
stage and real counters. No restart or source modification caused this recovery.

The precise transient renderer state before that refresh was not captured. A
code-level vulnerability consistent with the symptom was reproduced separately:
a monitor transport that never settles after abort leaves loading true forever,
which stops both polling and queued submission. The timeout now retires loading
itself, retaining confirmed history and fencing late responses. Enqueue requests
a fresh job observation before starting; status distinguishes this check from
active import. Unknown POST acceptance is never automatically retried.

The queue/monitor implementation and six-second notification dismissal predate
0.2.10 (their logic is unchanged since the September 30 packaging source apart
from module paths). The disappearing toast is not evidence of a recent removal.
Active transfer, accepted-receipt waiting and job stage/counters now have a
persistent live display; terminal notices retain expiry behavior.

## Focused evidence

`import-tests.log`: 27 checks passed, including abort-ignoring transport recovery,
replacement/late-response fencing, fresh admission, serial batch completion,
no retry of uncertain uploads, active status longevity and bounded actual counters.
This is source-level evidence, not native or release qualification.

## Final local verification

Installed local 0.2.11 at `~/Applications/Disco.app` uses clean source
`70a9bdb30a87167f1b764041f23c8ba3fcd4eac5`. The running managed generation is
`fb2d12438adc2d7e8d519fe7e06d4e48ccbec393c498c424e655aea4c6b3d793`.
See [the compact qualification receipt](local-0.2.11-qualification.json).
The documentation commit containing this final receipt does not change the app.

Full frontend (1,626), desktop (441), and scoped backend (88) tests passed, as did
the architecture guard and fixed core execution/source gate. Both serial actual-
million comparisons passed with no review flags, against the pinned regression
baseline and the previously installed 0.2.10 source using the same current harness.
The core receipt explicitly remains `release_qualified=false` with an uncalibrated
performance budget; this is a local tested installation, not release promotion.

The complete assembled bundle passed strict/deep ad-hoc signature verification
and testing-bundle validation. Static audit examined 815 native binaries with no
known blockers. Fresh-HOME relocated runtime checks passed for Python 3.11.13,
DataJoint 2.2.2, parser imports and MySQL 8.4.2 with resource hashes unchanged.
This does not qualify macOS 14 execution, Intel, notarization or clean-machine use.

Both old sessions exited through ordinary Quit; no scientific process was killed.
The new app restored Pulse family Inspect at epoch 477 of 505, with the 60,000-
sample trace and preexisting exclusion intact. Sidebar visibility was restored
manually. The supported runtime manager and complete-bundle installer retained
the verified 0.2.10 rollback. An initial activation correctly refused an expired
process-bound preparation; renewing staging within the activating process passed.

Raw JSON and logs remain under
`benchmarks/results/import-ui-20261107-70a9bdb/`, including the initial desktop
fixture-Python failure and its fully passing corrected rerun.

## Local version reservation

The combined fix reserves **0.2.11 for a local, unpublished build**. Live GitHub
refs checked on November 7 include `desktop-test-v0.2.10` at the installed source
and no 0.2.11 tag. No tag or release is being published by this task.

Runtime generation activation rejects equal-version/different-byte applications,
and its supported version grammar does not accept local/prerelease suffixes.
Consequently the repaired application cannot safely be installed as another
0.2.10. Any future official 0.2.11 must use this exact qualified source/artifact,
or choose a later version; do not replace the local generation with different
bytes under the same version. The exact installation/source identity is recorded in the compact receipt above.

## Coordinated repair scope

- Import monitoring/progress: parent branch, independent hook/authority review.
- Epoch range/Command selection and restored counted bulk controls: separate
  `epoch-multiselect-fix` worktree, independent stale-origin and bulk-write review.
- Action-triggered protocol inventory, immutable rename publication, retained
  Search preview renewal and unchanged compare/apply authority: separate
  `protocol-state-refresh` worktree using Astra high, independent authority review.

The merged Search component preserves both action-driven preview renewal and
single-gesture local inclusion undo. Combined lifecycle and import checks passed
(31 checks); preview and retained-control checks also passed. See the adjacent
selection and protocol-state-refresh evidence directories for their focused runs.

Native checks so far on the combined source with Electron 44.9.2 verified:
existing pinned update 63→61 epochs, first→Shift30 plus Command toggles,
exact 30-UUID exclusion/reinclusion, and exact 30-UUID tag add/removal, with other 31
rows unchanged. Arrow navigation and Light/Dark/Fred selection fill passed.
Search local batch inclusion/Undo and split-tree gestures passed. Workbench
explicit selection remained separate from highlights; incoming exclusion and tag
add/removal affected only selected UUIDs and left the entire Main receipt unchanged.
A uniquely named synthetic import started without Refresh jobs and committed 63
epochs; review opened automatically. A same-name/different-acquisition fixture was
correctly refused without adding records, exercising visible stop feedback. Live
progress remained visible at 9 seconds. Rename immediately updated sidebar/breadcrumb;
returning to Search loaded 122 current matches without manual metadata refresh.
Final packaged verification and restoration are recorded above.

An early generic Electron test target had unreliable focus/targeting. Its backend
was drained and stopped with clean database shutdown before switching to a uniquely
identified owned test shell. No user research project was used for these checks.

## Cleanup and retained work

Removed 30 inspected task-owned artifacts after orderly test shutdown and saving
raw evidence: copied native test app/runtime, synthetic projects and imports,
packaging outputs, disposable Node runtime and helper files. The standard cleanup
sweep completed with no queued leftovers. Three managed worktrees were archived.
The protocol-state-refresh worktree remains because the archive service reports
another active task still uses it; its shared frontend dependency target is retained.
Parent source and evidence remain on `codex/import-live-status`. No push or release
was performed. The verified previous 0.2.10 app/runtime remains for recovery.

Available space changed from 194,400,000 KiB before packaging to 194,745,812 KiB
after cleanup (+345,812 KiB, approximately 338 MiB). This is a net filesystem
observation across packaging/cleanup, not isolated deletion savings on APFS.
