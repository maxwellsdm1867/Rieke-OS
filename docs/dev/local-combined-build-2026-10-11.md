# Combined local Disco build — October 11, 2026

Current installed source: `ebb257d9fd4814794f09bd9e60e76b68333e438d`.
The bounded inventory/shutdown follow-up and installed-profile limitation are
recorded at the end of this document; the earlier 942015b results are historical.

The user requested one local build containing the current icon, selection,
alignment and protocol changes, tracked in Git. The owning checkout is
`/Users/maxwellsdm/.codex/worktrees/full-epoch-qc/Rieke-OS`, branch
`codex/next-version-integration`. The historical primary checkout is not the build
source. GitHub main was verified as `035e295` before integration.

## Integrated source

- `ba16611`: UI-wide fill-only selection, theme contrast, retinal cell icons,
  aligned overview/data-store counts and compact trace controls, including the
  earlier combined updater/navigation work.
- `c4034a1`, merged with ancestry retained in `3f392ef`: collapsible protocol
  sidebar sections; UUID-preserving rename; explicitly reviewed multi-acquisition
  pinned datasets; exact all-member compatibility for updates/exports.

The mixed-protocol workflow never silently trims a selection to fit a destination.
Recorded cell and protocol identity, frozen membership and existing provenance
remain authoritative. Native project data is not a build input.

## Packaging integration correction

The protocol change modifies `validate_protocol_definition` and
`evaluate_protocol_file` in `recording_workspace.py`. The package's byte-pinned
external-loader boundary had not been rebound by that feature commit. Inspection
of the full diff and AST comparison confirms those are the only changed top-level
functions; `load_parser` is unchanged. The source hash is explicitly rebound to
`7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139`.
The allowed loader call list, file allowlist and refusal rules are unchanged.

## Local artifact and evidence

The local candidate retains version 0.1.10 and is distinguished by its exact Git
source commit and artifact digest. This is not a public release or signed/notarized
promotion. The user authorized replacement of the installed local app. The verified bundle
was installed on 2026-10-11; the preceding app bundle is retained for rollback.
Scientific projects and recordings were not build inputs or replacement targets.

The existing pinned runtime is staged into an independent APFS copy, then the
normal runtime refresh/build, manifests, native imports and package integrity
checks bind it to the current source. Build/test receipts remain under
`benchmarks/results/local-combined-3f392ef/`; final artifact metadata is saved
separately after verification. Historical feature receipts remain attributed to
their original commits, including prior timing-review flags.

## Final source, validation and installation

The application is built from clean source `942015be17dfbdc12fe88acf44942774f8f94cad`.
This documentation follows that source and does not change the packaged bytes.

- Artifact directory: `/Users/maxwellsdm/Documents/Codex/Disco-local-2026-10-11-942015b/`.
- Installed app: `/Users/maxwellsdm/Applications/Disco.app`, local 0.1.10.
- Whole-bundle SHA256: `e093173f7f26dd5ed0c3c813f726f9b6cd165856140fc4e74a17c1132eb197a4`.
- Runtime manifest SHA256: `cb3bb7e139222745f74b9e56e109265d6d90245bbe72c8a7cfb156288c9d7e93`.
- ASAR SHA256: `f4b6ab7680b4c867ff8402b2a7de20546f1c94f39abccb2b9a45071d22085cf4`.
- Rollback app: `/Users/maxwellsdm/Applications/.Rieke OS.previous.app`, source
  `31182a40c22da05f904dda6979ac6bcf0d4996b0`. The older rollback bundle was moved to
  `preexisting-rollback.app` within the artifact directory before installation.

The artifact directory contains `build-receipt.json`, `prior-app-identity.json`,
`install-receipt.json`, and `validation-summary.json`. The normal whole-bundle
installer verified the source and staged copy, installed-manifest identity,
compatible formats, process absence, signature policy and final activation. Quit
used the ordinary application action; the backend registry cleared before install.

Validation: 1,046 frontend checks passed; 70 scoped backend checks passed and the
12 suggestion tests passed after correcting their invocation import path; 325
desktop checks passed with one skipped. Architecture and exact-source core gate
passed. Six packaged native smoke checks passed in an isolated profile, including
project creation, orderly exit and automatic project reopening. A static audit of
813 Mach-O binaries found no known blockers; it does not qualify macOS 14 runtime
behavior. Initial failed invocations and successful retries are retained.

All three matched million-row runs passed exact-result/refusal checks. Against the
pinned `34ce2e0` baseline, the initial cell-opening median triggered review
(1,167.88 → 1,545.56 ms); it cleared on repeat (988.18 → 989.47 ms). The repeat's
peak typed-worker RSS was 2,973,679,616 bytes, narrowly above its 2,947,547,136-byte
threshold. The initial memory comparison passed. The matched immediately previous
`ba16611` comparison passed every threshold, including RSS (2,775,597,056 →
2,291,482,624 bytes). These varying results do not establish a new regression or
clear the pinned review; the overall pinned comparison remains **review required**.
This is a local testing installation, not a green performance or release claim.

Raw results are retained under `benchmarks/results/local-combined-3f392ef/` and
`benchmarks/results/local-combined-942015b-{pinned,pinned-repeat,previous}/`.
No public release assets or GitHub branches were updated by this installation.

## Installed-profile startup limitation

Whole-bundle replacement succeeded, but the installed-profile UI did **not** reach
the project chooser. Its authenticated root health reported ready and the exact
942015b identity, with zero project services; the first chooser document stalled.
A process sample found one request thread blocked in `sorted` → `os.listdir` →
`__opendir2` → `open`, consistent with project-directory enumeration. The normal
Quit deadline retained the root ownership record with `drafts_saved: true` and
`Accepted operations remain active`; a normal restart reached recovery after
cleanup timed out. No backend was forcibly terminated, no ownership record was
removed, and no scientific project data was altered to clear this condition.

System Settings displayed Disco's Documents permission enabled. A pending macOS
folder-access dialog is a hypothesis, not a verified diagnosis; the computer-use
provider refuses access to UserNotificationCenter. The user was asked to check
for a system dialog. The process sample is retained in the artifact directory.
The new installed bundle and both earlier app bundles are retained. Installation
success does not establish installed-profile readiness; that check remains open.

### Shutdown investigation after the user's correction

Compared both retained physical app bundles, not just Git history. The old
31182a4 and new 942015b bundles have **identical bytes** for `main.cjs`,
`supervisor.cjs`, `close/quit-coordinator.cjs`, `close/draft-barrier.cjs`,
`workspace_desktop.py`, `workspace_launcher.py`, `workspace_frontend.py`, and
`workspace_projects.py`. Git also reports no differences for these owners.
There was no shutdown/launcher/project-listing implementation change in this
integration.

A controlled event-held directory-listing request reproduced the same behavior
with each packaged Python owner: Quit returns 409 while that request is unfinished,
then returns 200 after the read is released. No project/database was opened in
that experiment. The existing 31 desktop close/startup checks and 17 backend
boundary checks passed. This verifies the shutdown consequence, not the cause of
the live OS directory stall.

Both bundled interpreters, launched by the terminal, enumerated the real managed
root in under 60 ms (three entries). The app-owned process instead stalled in
`os.listdir`/`open`; its retained record and zero registered project/database
operations explain why an ordinary restart waits for cleanup. The chooser injects
its project inventory into the initial HTML, so that read can block the first UI
document. All GET requests remain admitted until completion because some routes
write caches; shutdown does not infer that an uncompleted GET is safe to kill.

The ad-hoc designated code requirement changed with the bundle:
old `a71d422658ce4178727318df5c3924e213da7d07`, new
`6f5029eda1a0f4e690197f2c34bb478720526f9b`. That makes stale OS authorization a
hypothesis worth testing, not an established cause. Available TCC logs did not
establish a Documents denial or pending prompt; the specific read-only permission
database query was denied by macOS. No attempt was made to bypass that denial or
the computer-use provider's system-dialog restriction.

Evidence is retained in
`benchmarks/results/installed-shutdown-investigation-20261011/`, including both
reproductions, exact Python hashes, and scoped test logs. No production code,
shutdown policy, scientific project data or macOS permission was changed during
this investigation. Installed-profile startup is still unverified.


## Bounded inventory and shutdown follow-up

The user requested a fix after the directory-read/shutdown investigation.
`95fb0cc` moves read-only project discovery into one serialized, bounded child
owned by `ProjectInventory`. The worker uses the existing project identity rules,
has no desktop capability, and denies file mutation, process creation and
network/database access. Reads time out after three seconds; shutdown cancels
only this reader. Scientific writes and service cleanup retain their existing
admission, identity and recovery requirements. A failed listing renders a
retryable chooser, never an empty catalog or scientific readiness.
`ebb257d` corrects the native test's initial-refresh timing only; this is the
clean final packaged source, still local unsigned-testing version 0.1.10.

Validation:

- The implementation revision passed 1,048 frontend tests, 147 backend tests
  including one skip, 325 desktop passes including one additional skip, the
  final 60 project checks, architecture guard and desktop application profile.
- Final package: all 813 Mach-O files have no known static blockers; relocated
  scientific imports and manifest hashes before/after passed.
- Actual packaged denied-directory, explicit retry and ordinary Quit passed;
  the final denied-directory Quit took 738 ms. The real owned-child deadline,
  cancellation and mutation-denial checks also pass. The native fault fixture
  models denied access, not an uninterruptible kernel syscall.
- The original six-check packaged smoke passed after reclaiming disk space:
  launcher/version, update check, create/open, clean Quit, cold project reopen,
  clean final Quit, unchanged manifest and ASAR. Earlier failures are retained:
  the host was below the existing 4 GiB index-building reserve, with incomplete
  view acknowledgments during failed/pending activation. No reserve was lowered.
- Exact ebb257d fixed core and its clean-commit gate passed. The matched pinned
  34ce2e0 million-row comparison passed. Against previous 942015b, one initial
  deep-cells median triggered review (986.67 to 1776.93 ms) while file discovery
  and cleanup were also running. The controlled matched repeat passed with no
  timing/RSS flags; deep-cells was 987.74 to 996.09 ms. All exact-result/refusal
  checks passed in both runs. The flagged run is retained, not averaged away.

Evidence is under `benchmarks/results/inventory-fix-95fb0cc/` and
`benchmarks/results/inventory-fix-ebb257d-{core,pinned,previous,previous-repeat}/`.
These checks do not establish signed distribution, macOS 14 runtime support,
universal performance or broader scientific workflow/release qualification.

### Installation and remaining folder-access issue

The old blocked read eventually released. Its normal authenticated Quit and Stop
returned 200/202 and its process exited; no forced termination was required.
During replacement, integrity validation caught 79 bytecode caches regenerated
by diagnostic invocations of the installed interpreter without `-B`. Their
altered bytes were retained and the exact manifest-matching originals restored
from the verified 942015b archive. Replacement then revalidated the entire old
bundle as `e093173f7f26dd5ed0c3c813f726f9b6cd165856140fc4e74a17c1132eb197a4`.
No scientific project files were changed by this repair.

The final app was installed through `installCompleteBundle`, using a private
APFS-cloned candidate and the expected whole-bundle checksum. Installed source
is ebb257d; bundle SHA-256 is
`a2b04c25f04b597c88f90e313c572d28960da2459312a63df30a05b48b453d53`, manifest
SHA-256 `b75a3e35ef5a89d125ad7ec9fd09f15df0d65a26c1fcf5a97c4ec219ad46164f`.
Receipts and the verified artifact are in
`/Users/maxwellsdm/Documents/Codex/Disco-local-2026-10-11-ebb257d`.
The previous 942015b app is at `~/Applications/.Rieke OS.previous.app`; its exact
rollback receipt was updated. Older 31182a4 and the previously retained rollback
remain in the dated artifact folders. Quarantine/security policy was not bypassed.

In the real installed profile, the chooser now renders its retryable folder-read
error instead of hanging at Starting. Ordinary Command-Q leaves zero installed
processes, removes root ownership, and leaves zero project services/database
operations. Relaunch reaches the chooser again. This verifies the requested
shutdown behavior, but does **not** claim the real project inventory is available:
its app-context directory read still fails. The identical read-only worker run
from the terminal lists two projects in 205 ms. OS/app-context access remains an
unresolved cause; no privacy setting or original scientific project was changed.

### User-requested disk cleanup and export search

Removed ten inactive, retired test application bundles while retaining their
fixture projects/logs and source manifests. Because of shared APFS blocks this
reclaimed only about 294 MiB. Removed one duplicate 601 MiB installer archive and
an unused extracted 1.9 GiB updater candidate, reclaiming about 2.48 GiB. At the
user's further request, removed the remaining cached installer and its stale
prepared hint. Installed and rollback apps were preserved. Free space increased
from about 3.2 GiB to about 5.8 GiB; logical file sizes are not summed as physical
space savings.

Checked 51 indexed export roots and grouped/hashed 253 files over 1 MiB. Verified
Disco duplicate export files were roughly 3–12 MiB each, mostly in distinct old
project/test copies. No 2 GiB Disco export was verified. The home filename scan
was stopped during cloud-folder traversal; Trash/protected-folder access was
unavailable. Scientific exports were not deleted. The user explicitly excluded
`kosmos_export`; nothing there was changed and further work there stopped.
The cleanup receipts and a concise `cleanup-summary.json` are retained with the
build evidence. No GitHub branch or public release was changed.
