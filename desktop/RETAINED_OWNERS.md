# Retained startup and state owners

These owners remain at their existing paths after source review. Start from
[desktop navigation](AGENTS.md); startup preference and draft storage have their
own contracts. This guide covers the remaining startup/state owners, not installation.

| Owner and public entry | Why retain this path and interface |
| --- | --- |
| Root supervisor: [ServiceSupervisor](supervisor.cjs) | Already a deep module: explicit resources/profile/version plus injected process and request adapters hide bind proof, readiness, recovery and root-mediated child authorization. Moving it into `runtime/` adds no leverage and forces changes to main, startup, draft/update atomicJSON consumers and packaging. Keep `atomicJSON` here; a forwarding facade would add another interface without hiding knowledge. |
| Backend admission: [DesktopBoundary](../python/workspace_desktop.py) | WSGI admission, control requests and response lifetime share the root/child executable entry with DesktopServices. This is a distinct authority, not an Electron supervisor implementation detail. |
| Project processes: [DesktopServices](../python/workspace_desktop.py) | Owns project child startup, exact process identity, database-operation records and all-child shutdown. The packaged `runtime/application/python/workspace_desktop.py` entry is passed to Python and participates in prior-process proof; moving this Python executable is not a useful folder-only change. |
| Restoration: [main.registerIPC](main.cjs), renderer `startupRestore` | Main composes saved preference, exact project authorization, accepted open, cancellation and final navigation. Moving direct child HTTP into a wrapper would leave identity/cleanup knowledge with callers. A future root-mediated cancellation operation needs separate JS/Python contract review. |
| Profile/path policy: [configureBranding](branding.cjs), [localPreview](local-preview.cjs), [require_external_data_path](../python/workspace_desktop_paths.py) | Shared policy spans Electron startup, isolated preview and Python mutable-data callers. It is not subordinate to startup preference. Existing entry/config paths stay stable. |
| Location index: [workspace_startup_registry](../python/workspace_startup_registry.py) | Existing bounded preference/index owner serves launcher inventory and project transfer. Moving it under Electron startup would obscure Python callers and imply runtime authority it does not have. |

## Design assessment and progressive disclosure

Use the owner table to choose the entry, then read only its contract below and its
linked examples. These decisions follow the installed Codebase Design/Deepening
and Improve Codebase Architecture guidance: clarity means callers need less
knowledge, not fewer exports or fewer lines.

The deletion test favors retaining these owners. Removing ServiceSupervisor moves
manifest/bind/recovery/control knowledge into main and other callers; it does not
remove that knowledge. Removing DesktopServices or DesktopBoundary redistributes
process and admission obligations among HTTP/native callers. Removing the index or
path-policy module repeats preference validation and resource protection across
launcher/transfer callers. Conversely, adding a forwarding runtime facade or merely
moving restoration HTTP leaves the same knowledge with main and adds navigation.
Branding is deliberately small policy used during composition; inventing a profile
manager around it would make callers learn an additional interface without hiding
more obligations. KEEP is a locality decision, not a claim that every current
interface is optimal or that native proof has been requalified.

| Dependency category | Existing seam and appropriate evidence |
| --- | --- |
| In-process | Health comparisons, manifest checks, branding sequence and index ordering are exercised through their owner interfaces. No new adapter is needed. |
| Local-substitutable | Filesystem paths/manifests use owned temporary fixtures; preview accepts filesystem and Electron app stand-ins. This checks decisions, not filesystem durability or real Electron initialization. |
| Remote but owned | Root/child desktop HTTP belongs to this application. ServiceSupervisor already accepts a request adapter; injected responses check transport admission. Existing restoration handler examples use fake owned transport. A new startup-cancel port must hide proof and cleanup knowledge and needs separate contract review. |
| True external | OS process inspection, native database/process behavior and Electron/macOS integration cannot be certified by those local stand-ins. Existing injection keeps selected decisions testable; host/native qualification stays separate. |

There is no replaced shallow module in this KEEP change, so existing contract tests
remain. The three small public examples add executable discovery of resource,
transport and preview obligations without creating new runtime seams. In particular,
the transport example supplies synthetic post-bind state through existing instance
properties; it does not execute or claim coverage of the bind handshake. The existing
supervisor startup/inspection suites retain that separate responsibility.

## Root and child contract

Construct `ServiceSupervisor` with explicit `resourcesPath`, `userData` and
`appVersion`; optional `spawnProcess`, `request`, `inspectProcess` and
`recoverProcess` adapters are existing seams. `loadManifest()` binds platform,
architecture, app version, source, workspace formats and database compatibility.
It resolves the executable and entry beneath the supplied runtime resources;
source-file location and PATH do not select the backend. `start()` requires a
private stdout bind receipt before sending a capability, then exact root health.
Startup/drain defaults are 90000/30000 milliseconds. Python's helper startup
budget defaults to 300 seconds; these are separate contracts.

`api()` accepts only the exact root origin and `/api/desktop/[a-z-]+` routes after
bind proof. `authorizeProjectURL()` requires current root health, a bound child
record and root-mediated matching child proof before origin admission. Registry
paths stay under userData (`desktop-service.json`, `backend/desktop-services.json`).
Explicit-folder desktop opens read the selected manifests directly; managed-root
opens retain full inventory. Neither route bypasses child authorization.
PID, creation time, session, executable, UUID and canonical path serve different
proof obligations. A ready HTTP port alone proves none of them.

`drain()` is strict replacement: acknowledged drain still requires process exit,
and failure may resume admission. Explicit `quit()` retains pause on failure and
records uncertain cleanup. Do not convert a timeout, missing receipt, crash or
ambiguous native writer into clean closure. Atomic JSON uses exclusive temporary
creation, file sync, rename and directory sync; ordinary tests do not prove crash
durability. `availablePort()` and default process inspection invoke OS facilities;
importing the module does not invoke them.

DesktopBoundary accepts exact peer/Host/Origin and the appropriate token. The
renderer session and private control capability are not interchangeable. It counts
accepted requests through WSGI response completion, including GET projections;
asynchronous producers supply separate busy/pause callbacks. DesktopServices
rechecks executable and creation time before sending a private capability,
prepares all children before strict stop, and preserves uncertain writers.
Native operation and project session ownership remain Python responsibilities.

## Restoration, profile and location contract

Restoration consumes one saved target and rejects duplicate accepted opens. Main
checks UUID/canonical path and cancellation after asynchronous authorization and
before navigation. Changed identity requires authorized cleanup; cancellation
requires exact PID plus creation-time disappearance. Missing records or uncertain
cleanup retain recovery evidence. StartupSession preference grants no readiness.
`main.cjs`, `preload.cjs` and `security.cjs` remain stable composition/security paths.

`configureBranding(app)` selects the established Rieke OS userData before displaying
Disco; it does not migrate drafts or receipts. `localPreview()` returns null for
unmarked/nonpackaged contexts. A marked preview requires exact bundle/home/profile/
temporary paths, one explicit user-data argument, owned nonsymlink directories,
and a clean source-bound manifest. It returns frozen preview metadata or throws.
Run it before application-managed branding/lock/bootstrap writes; Electron may
already have initialized. Preview policy is not installation policy.

Python `require_external_data_path()` resolves paths before writes and rejects
app-contained mutable state or protected ancestors in desktop mode. Missing runtime
ownership rejects; outside desktop mode it returns the resolved path. It grants no
process or database ownership.

The location index resolves `RIEKE_PROJECT_INDEX`, then desktop user state preferences,
then `RIEKE_PREFERENCES_DIR` or home `.rieke-os`. Root preference v1 is bounded to
64 KiB; local project index v1 to 1 MiB and 1000 entries. UUID plus normalized path
preserve independent copies; ordering uses path rank, casefolded name, name, path.
Locks serialize updates; index replacement syncs its file, not its parent directory.
Unknown/corrupt state cannot authorize open or recovery. Unmount preference is not
shutdown proof. Completed transfer may retain `registry_warning` without undoing
verified transfer success.

## Executable examples and limits

[Public examples](tests/retained-owners-public-examples.test.cjs) import the real
retained entries. They use an owned temporary runtime/profile and injected transport,
Electron and filesystem adapters. They do not start a backend, bind a listener,
inspect host processes, send signals, launch Electron or install anything.
Run from repository root:

```sh
node --test desktop/tests/retained-owners-public-examples.test.cjs desktop/tests/main-startup-restoration.test.cjs desktop/tests/security.test.cjs
```

The existing main restoration tests exercise registered IPC handlers with fake
Electron/transport, retaining the real StartupSession. Python source review is
not Python runtime evidence. Existing `python/tests/test_workspace_desktop.py`,
`test_workspace_desktop_paths.py` and `test_workspace_startup_registry.py` remain
their respective detectors; they are not run by this Node lane. Likewise the broad
supervisor suite can bind sockets, local-preview tests can invoke host commands,
and supervisor-runtime-inspection is host-specific: run only with separate scope.

The parent serializes ledger/path-companion/catalog and navigation updates. These
keep decisions change neither public source paths nor packaging selection. No
native exit, ASAR inclusion, filesystem durability, benchmark improvement or release
qualification follows from this source/injected-test review.

## Clipboard copy permission

`security.allowClipboardWrite` admits only `clipboard-sanitized-write` from a
focused, live scientific window whose current main frame and requesting URL have
the same admitted loopback origin. Permission checks additionally bind the
requesting origin. Both Electron permission callbacks retain the integrity gate;
null contents, subframes, recovery/file pages, retired owners, clipboard reads
and all other permissions are denied. No clipboard IPC is exposed. Electron
44.5.0 does not provide a clipboard user-gesture flag here; this policy does not
claim gesture-only enforcement. Copy controls still call the browser API from
explicit clicks. `tests/security.test.cjs` exercises admission and denial cases;
actual packaged copy and clipboard-read refusal require separate native evidence.
