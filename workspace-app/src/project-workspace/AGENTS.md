# Project workspace presentation

Choose the entry for the operation rather than learning one combined controller:

- [projectNavigation.js](projectNavigation.js) owns displayed project identity, ordering and bootstrap
  inventory. [ui/ProjectNavigator.jsx](ui/ProjectNavigator.jsx) exposes the navigator, rail and color helper.
- [startupRestore.js](startupRestore.js) exposes `createStartupRestore`; App and the desktop bridge
  retain launch/admission and project-child authority.
- [projectTransfer.js](projectTransfer.js) exposes inspection/open and verified prepare/restore/migrate
  monitoring. [ui/ProjectFolder.jsx](ui/ProjectFolder.jsx) composes that workflow and the explicit UI.
- [ui/ProjectOnboarding.jsx](ui/ProjectOnboarding.jsx) and [ui/ProjectSetupDialog.jsx](ui/ProjectSetupDialog.jsx) own project/workspace
  setup interaction. [ui/ProjectStartupError.jsx](ui/ProjectStartupError.jsx) and [ui/ProjectClosedNotice.jsx](ui/ProjectClosedNotice.jsx)
  present errors and closed-project state; they do not grant readiness.
- [ui/DataStores.jsx](ui/DataStores.jsx) presents registrations, versioned state actions and explicit
  deletion; [ui/ProjectFiles.jsx](ui/ProjectFiles.jsx) presents the project file inventory.
- [ui/ProjectUnmountDialog.jsx](ui/ProjectUnmountDialog.jsx) calls the existing shared unmount owner. Draft flush,
  uncertain close, stop receipts and server lifecycle remain outside this folder.

## Contracts and dependencies

A project path and UUID jointly distinguish current inventory, including copies
sharing UUIDs. Startup restore requires the saved exact available path/UUID and a
matching inspected project; migration refuses automatic restore. Supersede/cancel
and close retain their current bridge choreography. Main owns final launch and
accepted restore; a saved location restores neither results nor mutation authority.

Folder inspection can return choose-root, migrate, restore or open. Prepared
transfers never open as live projects. Local navigation permits HTTP(S) loopback
URLs without credentials. A completed transfer must affirm `verified === true`
and a nonblank destination; migration also affirms migrated and unchanged source.
Monitoring cancellation explicitly leaves possible server work running.

Store actions retain expected state version and recorded change receipts. Deletion
requires explicit confirmation/revision and `stage === 'completed'` before cache
invalidation and removal publication. UI labels and counts do not redefine UUIDs,
source SHA identities or scientific membership. File-browser reads do not mutate
recordings. Existing request, draft, clipboard and mounted lifetime behavior stays
in the same entries, including ProjectFolder abort and startup diagnostic copy
publication fences.

Identity/order helpers are in-process. DOM/clipboard/bridge stand-ins are
local-substitutable; the owned project/store endpoints are remote but owned.
The deletion test favors KEEP for the separate restore/transfer/unmount owners:
flattening them into the UI would repeat identity and verification knowledge;
one facade would make browsing callers learn transfer and child-stop contracts.
No new adapter is justified by this organization.

## Executable public examples

[projectNavigation.test.js](projectNavigation.test.js) covers copies sharing UUIDs, stable order and inventory;
[projectTransfer.test.js](projectTransfer.test.js) uses an injected request adapter to prove inspection and
verified output refusal. Existing startup/error/unmount tests remain cross-owner.

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/project-workspace/*.test.js src/startupRestore.test.js src/projectStartupError.test.js src/projectUnmount.test.js
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
