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

## Pending coordinated checks

Native candidate verification, combined selection/protocol changes, exact-source
core and matched million-row regression checks are pending. The installed app has
not been replaced. Test artifacts and final source identity will be recorded here
before completion.

## Local version reservation

The combined fix reserves **0.2.11 for a local, unpublished build**. Live GitHub
refs checked on November 7 include `desktop-test-v0.2.10` at the installed source
and no 0.2.11 tag. No tag or release is being published by this task.

Runtime generation activation rejects equal-version/different-byte applications,
and its supported version grammar does not accept local/prerelease suffixes.
Consequently the repaired application cannot safely be installed as another
0.2.10. Any future official 0.2.11 must use this exact qualified source/artifact,
or choose a later version; do not replace the local generation with different
bytes under the same version. Final installation/source receipts remain pending.

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
exact30-UUID exclusion/reinclusion, and exact30-UUID tag add/removal, with other31
rows unchanged. Arrow navigation and Light/Dark/Fred selection fill passed.
Search/Workbench/import and final packaged verification remain pending.

An early generic Electron test target had unreliable focus/targeting. Its backend
was drained and stopped with clean database shutdown before switching to a uniquely
identified owned test shell. No user research project was used for these checks.
