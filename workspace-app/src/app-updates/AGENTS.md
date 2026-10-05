# App update presentation

[appUpdates.js](appUpdates.js) owns safe release links, notice/label merging, browser polling and
bounded discovery claims. [ui/AppUpdates.jsx](ui/AppUpdates.jsx) owns the visible update controls,
status subscription and explicit check/download/restart requests. Native signed
and unsigned-testing installation, validation, drain and Quit authority remain in
the desktop owners; the display is not an installer or readiness proof.

## Contracts and dependencies

Release links retain the approved GitHub repository/release path allowlist.
A failed refresh retains a previously discovered version; a successful response
replaces it, including withdrawal. Browser checks run initially and on the existing
15-minute visible interval; visibility events obey the same elapsed interval.
Cleanup removes timer/listener. Discovery keys include channel/version, with a
bounded host-only session cookie and per-origin storage fallback; they suppress
repeated display only, never grant update authority.

Desktop UI listens to existing bridge status and unsubscribes on unmount; source
mode uses the existing owned endpoints. Preserve alive/checking fences, explicit
unsigned-testing download, restart refusal, and download polling cleanup/errors.
A ready label never substitutes for installation or process-exit evidence.

Notice policy is in-process; browser timers/storage/status events are
local-substitutable; bridge/server operations are remote but owned. KEEP policy
and UI separate from desktop installation: merging them makes browser display
callers learn signed/testing receipt and stop rules. Existing timer/bridge stand-ins
provide the needed seam; no new update manager is introduced.

## Executable public examples

The colocated policy tests cover approved links, retained notices, polling cleanup
and display claims. The retained mounted test uses controlled bridge/fetch results
and exercises explicit actions without downloading or installing an application.

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/app-updates/appUpdates.test.js src/appUpdatesLifecycle.test.js
```

## Change and evidence procedure

Use the named file entries directly. Each keeps its existing exports and caller
contract; no barrel, forwarding layer or private demotion is introduced. The goal
is a clear interface with progressive disclosure of the responsibilities below,
not fewer exports or fewer lines. Co-location improves locality; moving these files
does not by itself establish deeper behavior or a performance improvement.

Read the relevant entry and executable public examples before editing. Preserve
identity, scientific meaning, errors, ordering and lifetime. Review any proposed
contract or runtime behavior change before implementation. Keep the existing tests
and their public interfaces; do not import test support into production. Root
integration owns catalog/ledger/navigation updates and aggregate frontend checks.
Run the listed commands from `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset,
only in the coordinated test lane. Native/packaged behavior, actual ingestion,
backend durability and performance remain separately qualified; these examples
use owned synthetic values and do not authorize deferred/native fixtures.
