# Export request and receipt presentation

This folder organizes frontend policy and presentation. Backend recipe, materialization
and publication owners remain separate; native export qualification is explicitly
deferred. No actual export/import workload or scientific artifact fixture belongs to
this organization lane.

| Task | Public entries |
| --- | --- |
| Format/receipt policy | `exportFormats.js` |
| Destination order and saved reuse | `exportProtocolTargets.js`, `exportReuse.js` |
| Incoming operation/receipt choreography | `workbenchExport.js` |
| Candidate/protocol/incoming dialogs | `ui/CandidateExportPanel.jsx`, `ui/ProtocolExportDialog.jsx`, `ui/IncomingExportDialog.jsx`, `ui/WorkbenchExportDialog.jsx` |
| Local destination and inclusion selection | `ui/LocalExportFolder.jsx`, `ui/ExportSelectionDialog.jsx`, `ui/SelectionMaskDialog.jsx` |
| Published history | `ui/ProtocolExports.jsx` |

All existing exports, props and callbacks remain public. New destinations default to
SQLite; legacy missing format retains reference JSON and the recognized legacy MAT
alias maps to data-only MAT. Unknown explicit formats remain visible for deliberate
selection rather than silently changing destination. UI labels distinguish saved
artifact kinds; they do not prove materialization or byte provenance.

Generic success requires the requested supported format, nonempty dataset/event/
download identifiers and positive safe epoch count. Incoming success additionally
requires exact operation identity, artifact hash, workbench-incoming scope and expected
new-member count. Candidate preview fences and accepted-export context stay distinct.
A committed acceptance is saved before requesting export context; export failure or
retry never repeats or rolls back that acceptance. An uncertain export retains the
same prepared body and operation UUID. Starting a deliberate new workflow archives
prior receipts rather than carrying their operation identities into a new request.

Saved candidate reuse opens immutable selection for review, not its synthetic scope
as a protocol. Incoming reuse opens the target protocol/workbench with exact saved
proposal and intent. Selection masks are inclusion presentation, not authored tags;
export does not create approval or replace main membership. Shared transport retains
close tracking, abort and partial-persistence semantics; cancellation is not rollback.

Deleting receipt/reuse policy spreads identity and success checks into dialogs.
Deleting incoming choreography spreads accepted-versus-exported state into callers.
Combining all formats, authoring and native publication behind a facade would force
simple label/read callers to learn unrelated transaction rules. This is source
organization for locality, not deeper authority or fewer capabilities. Pure receipt
policy is in-process, mounted UI is local-substitutable, and owned HTTP requests have
existing controlled adapters. Native SQL, H5 and format writers are separate evidence.

Existing public policy examples remain at root paths. From `workspace-app`:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/exportFormats.test.js src/exportProtocolTargets.test.js src/exportReuse.test.js src/workbenchExport.test.js
```

These use plain synthetic request/receipt values and injected requests, not exported
artifacts or actual backend export execution. `dataExportUi.test.js` and incoming
mounted workflow tests remain cross-owner detectors after import integration.
Qualification of actual native export, bytes, transaction durability, backend retry,
packaged downloads and performance remains deferred. No native/export claims follow
from moving this UI source or passing controlled public-interface examples.

Explicit export submissions start a file download after publication. Restoring or
viewing a saved receipt never starts a download. Download cancellation/failure
does not undo publication or acceptance; the receipt link retries the same file.
`downloadExport.js` owns the renderer download gesture; `ExportSaveLocation.jsx`
explains browser/native save locations. Electron's existing owned-session download
handler opens the native chooser at `app.getPath('downloads')` plus the sanitized
filename. The chooser shows the full destination and supports browsing; project
export storage and scientific receipt authority are unchanged.


## Linked internal export extension

The opt-in `linked-sqlite` format follows the [linked export contract](../../../docs/architecture/linked-sqlite-managed-recordings.md). Only this format omits duplicate full reference JSON staging. It delivers a compact SQLite database plus a standalone Python loader in a ZIP. Existing formats retain their staging and publication behavior. Selection, acceptance, and export receipts retain their existing authority.
