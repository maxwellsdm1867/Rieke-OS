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

`useProjectData.js` separates shell rendering from scientific activation. It
requests activation after paint, retains the restored route, and presents load
failure/retry through `ui/ProjectWelcome.jsx`. Passive scientific resources wait
for activation. Project management and the existing unmount owner remain usable.
App suppresses the chooser while the existing one-shot startup restoration is
pending; missing or changed projects retain the chooser's recovery path.

`useProjectPresentation.js` reads the optional `/project/presentation` shell snapshot before scientific activation. `validProjectPresentation` requires exact UUID/path and the versioned display-only envelope. Missing, invalid, failed or superseded reads never block opening. App shows the snapshot only in an inert Overview with no scientific callbacks or recording-size read; canonical data replaces it in the same component. It never hydrates protocol witnesses or mutation authority. `useProjectPresentation.test.js` covers identity and late responses.

Native project selection uses `activateProject` without waiting for draft flushing because the document stays alive. Browser navigation still flushes before replacing the document. Target unmount uses prepare/confirm/cancel bridge calls for the exact UUID/path; checkpoint guards remain active until confirmed closure or cancellation.

Native project selection first asks the authenticated desktop owner to activate
an exact retained UUID/path. A successful hit performs no folder inspection/open
requests. Only an explicit miss uses the existing inspection/restore/migration
path; refusal or malformed replies surface an error and do not fall back. Older
desktop bridges and ordinary browser navigation retain their existing behavior.
The native owner revalidates live backend and caller identity; the renderer does
not supply a cached URL or restore scientific authority. App composition cases
live in `presentationSessionsApp.test.js`.

Project setup stays mounted while an open is pending, refused, or handed to a
restore/migration chooser. App closes the originating setup only after project
selection completes successfully, including a retained desktop activation. This
also completes create-and-open before returning to the originating retained view;
`presentationSessionsApp.test.js` exercises both setup callbacks and failures.
