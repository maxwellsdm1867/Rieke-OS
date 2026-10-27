# Unsigned runtime generations

Opening a testing build opens the application. It does not require an installer
page or closure of another session. A runtime update chooses the version for
future sessions; existing sessions continue using their original physical files.
Project-folder ownership remains enforced by the backend's existing locks.

## Owners and public operations

`entry.cjs` performs preview admission first. Development, preview and signed
packages retain their existing startup composition. An unsigned packaged entry
either consumes a managed session admission before Electron ready, or acts as a
front door: stage a downloaded build if necessary, resolve current, reserve a
session and request its launch. Front doors use a private temporary Chromium
profile. `main.startDesktop(context)` composes the scientific application only
after admission; main still owns windows, drafts, startup and service closure.
Front-door profiles live in the private store and are collected only after their
owner and Chromium helpers exit. Deleting them during Electron's `will-quit`
event can race late Chromium writes and must not be used as a shutdown hook.

`runtime-generations.cjs` exports `RuntimeGenerations`, `admitRuntime` and
`runtimeStore`. The store's intent operations are:

| Operation | Result and authority |
| --- | --- |
| `stage(source, expected)` | Verify the complete app seal, runtime inventory, compatible platform and bundle digest; copy and verify a physical generation; return a pinned prepared generation. Update callers supply the expected bundle/manifest hashes and target version from the validated download. |
| `activate(generation)` | Atomically select a compatible newest version for future sessions. Does not drain projects, replace a running bundle, launch a process or authorize Quit. Equal versions with different contents are refused. |
| `prepareLaunch(options)` / `launch(options)` | Reserve an exact generation/profile/intent before native spawn. Ordinary new sessions select current; recovery and restart can pin an exact generation. LaunchServices acceptance is not scientific readiness. |
| `restartAfterExit(generation, profile)` | Bind a separate helper to the initiating PID, creation time and executable. A matching helper readiness packet permits the caller's normal Quit; the helper launches only after that exact process exits. |
| `restorePrevious()` | Validate the retained previous generation and change current only if its revision is unchanged. No flat-bundle replacement helper is used. |
| `maintain()` | Refresh the Applications front door when safe, then collect unreferenced generations. Failure is nonblocking and never grants project/process authority. |

`runtime-store.py` is private transaction machinery, read from ASAR and executed
with the bundled Python using `-I -B -c`. The Python process both owns the kernel
`flock` and performs each small mutation. There is no separately running lock
guardian whose death could leave an unlocked writer continuing its work.
Expensive bundle verification/copy occurs outside these transactions. Publication,
current-pointer changes, reservations, admission and retirement share the lock.
Records are written through fsynced temporary files and atomic replacement.

`generation-restart.cjs` is the installed, detached exact-session handoff helper.
It does not replace apps or signal scientific processes. Unclaimed handoffs pin
their target until their bounded lifetime expires. Claimed handoffs retain the
target while the exact helper remains alive, until helper exit or atomic transfer
to a launch reservation.

## Physical and lifetime invariants

Each generation is a complete bundle at
`~/Library/Application Support/Rieke OS/application-versions/unsigned-testing/darwin-arm64/generations/<bundle-digest>/Disco.app`.
Electron, Python, MySQL, libraries and lazy imports use that real path. Changing
current never renames or overwrites it. The global store is independent of the
per-session profile selected before Electron ready.

Launch reservations become PID/creation-time leases atomically. The final chosen
profile is bound before backend startup. A missing token on an ordinary managed
bundle launch routes through current; an invalid supplied token is rejected.
Uncertain launch requests retain their reservation until admission or expiry.

Collection protects current, previous, preparations, maintenance, pending
handoffs, live/uncertain admissions and pinned Dock targets. It requires a complete
process snapshot and no executable/command or open Electron framework referencing
the generation. A clean GUI close is not sufficient on its own. Crashed GUI leases
can retire only after their exact process and all generation executables are gone;
this retires application bytes, not scientific recovery records. Unknown evidence
retains files without blocking a new version. Project data is never collected.
The backend's existing external-data guard also protects the entire managed
application store and canonical/previous front-door bundles when running from a
generation, so creating projects or exports cannot modify another version's files.

## Migration and warning semantics

An older flat installation may still be serving lazy imports from the Applications
path. The new version starts independently while that canonical copy stays in
place. Background promotion checks for its live processes cheaply before a full
copy, and the legacy installer repeats strict checks immediately before mutation.
The retained `.Rieke OS.previous.app` is also protected against live use.

The warning describes the limited consequence: the new version is usable, while
the Applications entry may still open the previous version until automatic
promotion can finish. It must not tell users to close unrelated sessions or remove
locks as a prerequisite to using the new version.

Update activation precedes the initiating session's drain. If that session cannot
save/close safely, a fresh chooser opens in the activated version and the original
session remains available for recovery. Cancellation prevents the fallback launch.
Successful exact-session transfer still requires its own draft/service barrier.

Rollback history begins with generation-capable releases. A legacy 0.2.2 bundle
cannot simply be relocated into this layout: its own startup logic would treat
that path as an installer. Signed distribution remains on its separate existing
installation path; this change does not qualify signed updates or Intel support.

## Checks and qualification

`tests/runtime-generations.test.cjs` uses inert bundles, real private filesystem
transactions and injected bundle validation/copy. It covers concurrent activation,
copy publication, hash substitution, immutable old bytes, revision-bound rollback
and corrupt-pointer preservation. `updates/tests/testing-updater.test.cjs` covers
activation before drain, local transfer refusal/exception and flat-helper exclusion.
The exact packaging allowlist includes `runtime-store.py`.

These tests do not establish native launch, process inspection, Dock behavior,
quarantine or scientific readiness. Native evidence must use the packaged entry
and retain source/hash attribution. Scientific E2E fixtures reserve real admissions
before Playwright launches the physical runtime; installer/front-door qualification
is separate. Required core and million-row comparisons still follow native workflow
verification, and release publication still requires the exact clean candidate.
