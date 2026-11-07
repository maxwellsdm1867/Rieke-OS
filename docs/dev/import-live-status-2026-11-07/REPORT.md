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
