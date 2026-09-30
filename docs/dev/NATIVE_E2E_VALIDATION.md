# Native project end-to-end validation

Validated on macOS Apple Silicon, 29 September 2026.

## User journey

1. Start Rieke OS and create a project from the project chooser.
2. Import an H5 recording. Native projects retain a copy inside their folder.
3. Inspect a trace, select an author and save an epoch tag.
4. Close the project. Wait for the closed-project confirmation before copying.
5. Copy the entire project folder using the file manager.
6. Choose **Open project** and select the copied folder. Recordings, metadata,
   tags and protocols load together; no archive is needed.
7. Export selected epochs to SQLite and MATLAB.

The real browser run imported 3 cells, 1,915 epochs, 2,190 responses and 1,915
stimuli. The copied folder reopened independently beside the original with its
saved tag and waveform intact. Both export formats completed for 1,640 epochs.
Unchanged generated MATLAB scripts reconstructed 3 ordered leaves and all 1,640
UUIDs; two 6,000-sample traces at 10 kHz matched direct H5 reads exactly. Shuffled
selection masks, saved masks, all-excluded selections and invalid mappings were
checked. Original recording files were not modified.

## Automated checks

- Python workspace suite: 587 tests passed with native MySQL and native transfer
  integration enabled; no skips.
- Frontend suite: 205 tests passed; production build passed.
- MATLAB: 23 function tests plus portable-tag and native-GUI tag scripts passed.
- Private runtime provisioning: a second installation from the verified package
  cache produced working MySQL 8.4.2 server, client and dump tools.
- Release metadata validation and whitespace checks passed.

Reproduce the backend suite after setup:

```sh
RIEKE_TEST_NATIVE_MYSQL=1 RIEKE_TEST_NATIVE_TRANSFER=1 PYTHONPATH=python \
  .rieke-runtime/venv/bin/python -m unittest discover -s python/tests -p 'test_*workspace*.py'
cd workspace-app
npm test
npm run build
```

## Defects caught and fixed

The real journey caught cross-process shutdown waiting on a non-child zombie,
copied projects being hidden because their scientific UUIDs matched, stale
sender server records, unstable reopened browser origins, and obsolete default
export grouping fields. Regression coverage accompanies those fixes. The MATLAB tree now retains readable row heights and
scrolls expanded epoch lists. Copy
recovery also checks recording hashes, export dependencies and clean shutdown;
unknown-machine dirty copies are rejected.

The project chooser, folder controls and files page were visually inspected in
the real app. The files page groups recordings, imports, exports, saved work and
app storage with consistent icons. Close returns to the chooser with copying
instructions and a copyable folder path.

## Boundaries

Actual folder transfer was tested between two folders on one Mac. Cross-machine
ownership and path conditions have automated coverage, but physical transfers
to a second computer or another OS were not performed. The retained database is
DataJoint/MySQL; SQLite exports and disposable indexes are separate concerns.

The source application runs without Docker using its private runtime. A signed
standalone app installer has not been produced. Automatic release checks and
notifications are implemented; no stable signed release or trusted production
signing key has been published. Release staging/activation tests do not establish
that a public update can already be installed.

## Import and selection follow-up

The project rail's plus opens both New project and Open project. New project
accepts an absolute root folder and creates a new isolated child folder; existing
nonempty folders are never overwritten. A browser-created project under a second
root imported the same real H5 fixture and automatically opened the review dialog.
It showed +1 recording, +3 cells, +1,915 epochs, +2,190 responses and +1,915 stimuli,
separately from source totals, plus the verified managed-copy confirmation.

New imports (including path imports) always use a checksum-verified project copy.
Regression tests remove the original and read a waveform from the managed copy.
Only completed verified imports offer original-removal guidance. Old linked files
and duplicates do not receive that confirmation.

Protocol review supports independent approval, guarded Approve All, inspection,
and dismissal without approval. Analysis inclusion defaults on. Its per-row toggle
updates the existing protocol mask without deleting or hiding the recording.
Epoch selection uses row highlighting, Ctrl/Command-click and Shift-click; the
redundant selection checkbox is removed and row labels display only the number.
The browser verified exclusion with the waveform still visible. The updated
backend suite passed 593 tests with native integration enabled, and 209 frontend
tests plus production build passed.


## Exact project folders

The creation form now uses one exact project folder rather than requiring a
parent root plus managed child. The browser created and opened a native project
directly at the selected path. Explicit read-only preflight rejects missing or
inconsistent manifests, storage layout and initialized database files.

The browser also moved the populated 1,915-epoch fixture into the preferred
projects location using the optional Move & open control. In-app relocation
requires a closed native project and an unused destination on the same
filesystem; atomic exclusive rename prevents destination overwrite. Cross-volume
moves leave the source untouched and direct the user to copy/open via their file
manager. Existing root/directory API parameters remain for compatibility.


## Quiet import notifications

Routine import status now appears as a compact upper-right notification. Normal
notices expire after six seconds and attention notices after ten; hover/focus
pauses expiry. Clicking View details opens the import workbench. Existing history
is not replayed as new notifications after reload. Completion no longer opens a
modal automatically; the review dialog is available explicitly from Review import.
The browser verified a real duplicate import notification and automatic expiry,
with no persistent header bar or automatic review dialog. App updates now appear
quietly as a persistent Update badge in Release / Publish, without a toast.

## Quiet updates and publication audit — 2026-09-29

- Checked both live GitHub repositories. The development checkout's updater
  pointed at epicTreeGUI, whose release channel is empty. Rieke-OS is the actual
  public distribution, with stable source releases through v0.1.2 and one source
  installation verification workflow. Corrected discovery and release URLs to
  Rieke-OS; a fresh backend check returns `update_available`, available `0.1.2`,
  and `can_stage: false` for this development checkout.
- Browser preview with simulated update responses verified the persistent
  Update/Ready row, no update toast or automatic dialog, opening/closing the
  panel without dismissing availability, retaining the known update after a
  failed refresh, and clearing it after a successful up-to-date response.
  [Simulated Ready preview](quiet-update-ready-preview.jpg).
- 50 relevant updater, route, workspace installation and bootstrap tests pass;
  frontend logic tests and production build pass. The manager subprocess test
  uses minimal fixture applications to exercise real interprocess locks and
  next-launch selection. It verifies deferral while another holder is open,
  activation after closure, retention of the previous release, and preservation
  of preferences. It is not a real old-to-new production application upgrade.
- Prepared a tag-triggered signed build and protected publication job; its
  publication condition allows only Rieke-OS. No workflow was dispatched and no
  release was published. The updater and workflow still need to be carried into
  the public distribution, with signing configured and real upgrade validation.
- The one-click desktop installer remains unfinished. Existing source releases
  bootstrap development tools and dependencies; they are not offline prebuilt
  applications. MATLAB is required only for the optional EpicTreeGUI workflow,
  not core app launch, import, or updating.

## Pinned query approval demonstration

A synthetic H5 fixture derived from the read-only test recording (fresh, disjoint
UUIDs and explicit Synthetic demo cell labels) added 3 cells and 9 epochs to the
disposable project. Automatic saved-query reruns produced three candidates:
Variable Mean Noise +3 epochs, Expanding Spots +3 epochs, and unpinned Single Spot
+3 epochs. The overall protocol-type delta was correctly zero for known names.

The browser approved Variable Mean Noise individually (1,640 to 1,643 epochs),
then Approve All updated only the remaining pinned Expanding Spots dataset (255
to 258 epochs). Single Spot remained pending. Both pinned sidebar entries stayed
in place; no file export was generated. Cards now show cells, epochs and compact
before/after bars, with affected cells and navigation inside collapsed Details.
Approve All remains visible in the review header while scrolling.

This real run caught a DataJoint lineage mismatch in the new protocol-type count.
The fix restricts by project experiment keys rather than joining unrelated integer
lineages; a real native-MySQL regression reproduces that schema distinction.
The final backend suite passed 617 tests with native integration enabled;
211 frontend tests and the production build passed. The unsuccessful test attempt
remains in demo history; it added no source records and the retry completed with
no warnings.

### Single managed H5 folder and storage totals (2026-09-29)

- Full native backend suite: 628 tests passed; frontend: 211 tests passed and production build succeeded. Datastore size tests also passed (15).
- Closed/reopened the native demo project, then copied a fresh synthetic H5 directly into `raw-uploads`. The watcher automatically imported it after settling: one recording, three cells, nine epochs, zero new protocol types. Three saved-query proposals were created without approval.
- Verified the job's retained path equals the dropped path, exactly one matching managed H5 exists, and `original_removal_safe` is false for this in-place recording. Sidebar pinned protocols displayed pending +3-cell updates.
- Browser confirmed Import H5s and Open H5 folder controls. Data stores showed 268.4 MB H5, 23.4 MB parsed metadata, 291.8 MB combined, with per-recording metadata sizes. These totals exclude MySQL, caches, exports, logs and unregistered files; unavailable sizes are marked partial.

### Automatic completion review (2026-09-29)

Successful import completion now opens the global Review imported data dialog from any workspace page. Existing history on page load does not reopen it. Verified with a fresh synthetic watched-folder import while on Data stores: dialog appeared without clicking, showing +1 recording/+3 cells/+9 epochs and two pinned protocol proposals with Approve All. Proposals remain pending for user inspection. Frontend 211 tests and production build passed.

### Combined import control and multi-file selection (2026-09-29)

Removed the duplicate Import progress toolbar button. Import H5s now changes to Importing H5s while work is active and opens the same import/history page. File selection and drop accept multiple H5s, queued at app scope, with only one submitted import at a time. Upload uncertainty or failed imports stop the queue; no automatic POST retries occur. Keep the tab open for browser-held pending files.

Browser file chooser confirmed multiple selection. Submitted a new synthetic H5 followed by an existing H5: first completed at 18:51:28 UTC, second started at 18:51:28.919 UTC and was skipped as duplicate. Review appeared after the queue drained, preserving the successful import review despite the last file being a duplicate. Frontend 211 tests and production build passed.

## Project portability audit (2026-09-29)

- Added explicit **Add new project** and **Start a brand new project** actions in
  the left sidebar. The first recognizes an ordinary project or a received
  transfer, and automatically shows the verified-copy restore form. The second
  creates the selected exact project folder and its managed storage/database.
- The browser created a disposable native project, imported a read-only real
  Symphony recording (5 cells, 690 epochs), closed it, prepared a checked copy,
  added that received copy through the ordinary project action, restored it into
  a fresh folder and opened its overview and protocols. Both sidebar actions and
  the verified restore confirmation were visually checked.
  [Recipient restore](portable-project-restore-e2e.png) and
  [recipient sidebar](portable-project-sidebar-e2e.png).
- A production API integration test saved two named predicate versions, a query
  run, an explorer baseline, authored tags, review/inclusion decisions, a tree
  layout, recent-search shortcuts, protocol pins and a failed-job record. It
  prepared a transfer, removed the entire disposable donor, restored to a fresh
  runtime, then compared the actual recipient API responses and 16 waveform
  samples. The recipient overview also opened successfully.
- Packages now preserve durable import/app-job/error/storage history, portable
  search/navigation preferences and every SQL table. Each new package records
  table columns, row counts and content checksums; restore compares these before
  updating current file locators. H5 files with external dependencies and damaged
  preferences are rejected before a recipient database is started.
- Native tests also exercise both never-opened and opened/closed empty projects,
  independently restored copies, donor recording removal, safe rejection of
  missing identity in populated projects and failed restore cleanup.
- Browser pinning and running a History noise search wrote both choices into
  `protocols/ui-state/project-preferences.json` (72 epochs, 2 cells). Failed old
  browser-preference migration preserves its cache across refresh until a save
  succeeds; stale incoming/browser values and concurrent changes have coverage.
- Final backend workspace suite: **705 tests passed**, with native MySQL,
  native transfer and production API portability gates enabled; no skips.
  Frontend: **251 tests passed** and production build passed. Whitespace checks
  passed. Original recordings and research projects were not modified.

Reproduce the full backend checks with a suitable real Symphony fixture:

```sh
RIEKE_TEST_NATIVE_MYSQL=1 RIEKE_TEST_NATIVE_TRANSFER=1 \
RIEKE_TEST_PORTABLE_APP=1 RIEKE_PORTABILITY_H5=/absolute/path/to/recording.h5 \
PYTHONPATH=python .rieke-runtime/venv/bin/python -m unittest discover \
  -s python/tests -p 'test_*workspace*.py'
```

These checks use fresh folders, credentials and native runtimes on one Apple
Silicon Mac. A physical second-computer or other-platform transfer remains
unverified. Restart existing app services to load the new backend before using
the rebuilt interface.

### Project UI design follow-up

The chooser now uses two icon-led action cards, a six-icon project contents
graphic, compact folder names and a collapsed preferred-location control.
The closed-project notice is a compact status row. The project dialog uses
**Open / Share / Receive** tabs and shows one task at a time, including concise
file verification and restore results. Native sharing shows the close action
before destination fields. Keyboard tab navigation and accessible control names
are preserved.

The real received-copy flow was exercised again through the redesigned dialog.
Frontend: 251 tests passed and production build passed. Narrow layouts were
visually checked; the closed-notice dismiss/copy controls stay on the same row.

Final browser checks also covered invalid-folder rejection and refusal to
restore into an existing destination. SHA-256 comparisons confirmed that the
existing project's manifest, catalog, database credentials and guard file were
unchanged. The new-project form created all managed folders, opened the empty
production overview, and closed cleanly. Design screenshots are saved as
`portable-project-chooser-design.png`, `portable-project-share-design.png` and
`portable-project-restore-e2e.png` alongside this report.

### Project roots anywhere and nearby-folder suggestions

Project creation, open, verified restore and relocation now remember exact
project roots in a local user-profile index. Inventories retain roots outside
the preferred location across closing and launcher restart, preserve independent
native copies by path, and show unavailable external drives. Exact creation and
opening do not write app registry or lock files into the project's parent.
Prepared transfer folders are excluded from live-project discovery.

Folder inspection proposes the nearest fully validated containing root for
a nested selection, or valid immediate children for a parent selection. Searches
are bounded to eight ancestors and 128 immediate entries; no recursive drive
scan, runtime start or automatic candidate selection occurs. The UI lists each
candidate with **Use this folder**, followed by an explicit Open or Check action.

The production service flow opened an external project after detecting its root
from `imports/`, closed its database cleanly and retained that exact root in the
launcher inventory. Receipt: `project-root-location-verification.json`.
Final full native backend suite: **803 tests passed**; frontend: **266 tests
passed** and production build passed. Live browser automation was unavailable
for a visual recheck of the new suggestion cards; API and frontend logic checks
passed. Refresh the preview after restarting its service to load the changes.

### Final review before push

The browser connection recovered for the final UI review. Naming guidance and
the matching name/folder preview, Back and Escape, parent and nested folder
suggestions, explicit candidate selection and prepared-copy detection all passed.
Editing a received path clears its earlier verification. Current screenshots:
`portable-project-naming-design.jpg`, `portable-project-root-suggestions.jpg`
and `portable-project-receive-verified.jpg`.

Review fixes reject missing package metadata even when a checksum is null,
serialize managed and exact creation of the same folder, reapply sidebar move
intent after a preference conflict, preserve completed operations when saving
the local project index fails, and keep malformed old browser shortcuts from
crashing the search screen. The original browser cache is retained until a
successful save. Regression tests cover each failure.

The push is prepared from a separate snapshot based on the current committed
code plus only the project portability changes and required dependencies.
Unrelated desktop, update, source-identity and performance edits are excluded.
The initial snapshot passed 693 backend tests with all native portability gates
enabled, 244 frontend tests and the production build. The final safeguards were
then incorporated and checked again before commit.

Final feature-only snapshot: **697 backend tests passed**, all native gates
enabled with no skips; **245 frontend tests passed** and production build passed.
Whitespace checks passed. The additional tests in the larger shared working
tree belong to other ongoing changes and are not part of this push.

### Project popup follow-up

The project rail **+** now opens a native modal chooser above the existing app.
Creation stays within that popup; the welcome screen also opens creation in a
modal. A live disposable workspace verified that its overview URL and contents
remain in place, **×** and **Escape** return focus to **+**, and forward/reverse
Tab stay inside the popup. No project files were created by this UI check.
Screenshots: `project-popup-over-workspace.jpg` and
`project-create-popup-over-workspace.jpg`. The feature-only frontend suite and
production build were checked again for this UI correction.

## Project folder browser and creation actions — 2026-09-29

Every editable project location now has Browse: creation, preferred location,
opening, moving, sharing and receiving. The browser fallback navigates immediate
folders with location shortcuts, parent navigation and explicit new-folder names.
It reads folder metadata only and never creates files. The optional desktop
chooser contract is covered by adapter tests; a native OS dialog was not exercised
in this browser validation.

A scoped checkout passed 253 frontend tests, the production build, 11 new folder
API tests and 10 existing open-folder tests. Folder tests include pagination,
permission errors, same-origin local access, missing destinations and occupied
folders containing only hidden entries or files.

Live browser validation confirmed the new-project popup has Cancel and Create &
open above the existing workspace. Escape from the nested folder browser preserved
the project name and folder value, kept setup open and returned focus to Browse.
[Creation popup](project-create-browse-cancel.jpg) and
[Folder navigator](project-browse-picker.jpg).

Main Cancel closed setup and restored focus to its sidebar opener at the same
overview URL. Tab/Shift+Tab remained in the nested picker. Choosing a proposed
new folder filled the form without creating that folder on disk.

Final audit regression: a missing proposed child inside an empty parent now stays
a new-folder proposal rather than selecting its parent. The API reports whether
the requested directory exists; the picker preserves the entered child name. A
live check returned the exact proposed child path, while its parent stayed empty
and the child was not created. Unfinished typed paths can still open Browse.
10 focused folder-client tests, 12 folder API tests and the scoped production
build pass. [Empty-parent check](project-browse-empty-parent-regression.jpg).

## Whole UI file and folder audit — 2026-09-29

Reviewed the entire component directory and App import/export pages, searching all
inputs, file-picker triggers, editable paths and copy-path actions.

| Flow | File or folder action |
| --- | --- |
| New project / preferred projects location | Browse folders |
| Open / move / share / receive project | Browse sources and destination folders |
| Recording import | Browse H5 files; multiple selection and drag/drop |
| Tag and saved-query import | Native JSON file picker buttons |
| Selection masks | Native UGM and JSON file picker buttons |
| Exports | Download buttons; Open exports folder for local handoff |
| Project files | In-app categories, folders and breadcrumbs |
| Tag author profile | Author list and name; preferences saved automatically |

The H5 chooser was a styled label around a hidden input, leaving it outside
keyboard navigation. It now uses a real Browse button with the same file filters,
multiple-file selection, queue behavior and disabled state. Cancel enqueues
nothing; resetting the input allows choosing the same recording again.

The local exports card previously offered only Copy folder path. Open exports
folder now opens this project's existing exports folder in the system file
manager. Its endpoint accepts an empty body only, verifies a local app request,
and rejects missing folders and symlinks. It cannot choose an arbitrary location.
Copies, exports and original recordings keep their current storage layout.

A scoped checkout passed 255 frontend tests, 18 folder API tests, 10 existing
open-folder tests and the production build. File-picker controls for tags, queries
and masks already existed. Filename/path search filters and readonly diagnostic
paths do not prompt for a filesystem selection.

Live browser checks: Tab focused the H5 Browse button and Enter emitted a
multiple-file chooser event. No files were selected and import history remained
empty. Clicking Open exports folder completed without a visible error and
re-enabled the button; success requires the OS opener to exit successfully for
the fixed fixture exports path. The native computer-use service was unavailable
for Finder, so the Finder window itself was not visually inspected.
[H5 Browse](ui-browse-h5-audit.jpg) and
[Open exports folder](ui-open-exports-audit.jpg).


## Final unsigned Electron artifact validation — 2026-09-30 UTC

The final local DMG and ZIP passed the complete packaged checks. See
[the consolidated receipt](desktop-final-e2e-receipt.json) for exact artifact
hashes, the runtime manifest and per-suite evidence. The app contains 40,172
runtime resources and 798 native binaries.

- 955 Python tests passed; 15 optional tests skipped.
- 291 frontend and 27 desktop unit tests passed.
- 21 real packaged UI/lifecycle checks and a separate broken-backend startup
  case passed, including actual H5 import, bridge/native close deferral, draft
  recovery, rapid project handoff, cold restart and renderer crash recovery.
- 15 real scientific cases passed, including reference/SQLite/MAT numeric
  fidelity, native portability, a separate legacy copy and monitor crash with
  the importer retaining its project lease.
- Extracted DMG/ZIP resource and native audits, 23 rejection faults, isolated
  native restart/backup/restore and DMG-extracted recording workflow passed.
- 10 pinned updater transport scenarios passed with zero unhandled rejections
  and zero native installs, including a fresh-client retry after interruption.

All scientific test services exited cleanly. Original H5 and packaged resource
checksums stayed unchanged. Normal desktop operation requires no Docker. The
legacy-copy fixture used a test Unix inspection transport with real native SQL,
scientific data and history. No user source database or project was migrated.
Frozen historical exports retain their original pointers; a new migrated export
was separately verified against the copy’s H5 data.

The user’s older installed app was left running and was not replaced. The
reference bundle for the artifact audit was the built candidate; extracted DMG
and ZIP copies were tested at isolated paths. This is an unsigned dirty-source
local candidate. Signing/notarization, real signed old-to-new installation and
recovery, a second clean machine/different user and macOS 14.0 remain release
gates. No MATLAB engine was used; MAT structure and lazy numeric pointers were
checked with bundled SciPy and H5. Native chooser results were stubbed at the OS
dialog boundary. The receipts do not claim universal OS shutdown or power-loss
qualification.

The upper-right app icon update was rebuilt and rerun through the same packaged
UI, startup-failure, scientific and DMG/ZIP audits. The actual bundled purple R
loads at 48 px in the launcher and 32 px in the workspace. Native 1440 px and
960 px window checks confirm that the icon remains visible without overlapping
the toolbar. See the [workspace preview](desktop-ui-e2e/workspace-icon-1440.png)
and [narrow preview](desktop-ui-e2e/workspace-icon-960.png). The final consolidated
receipt records the refreshed artifact hashes; all five published files remained
unchanged during verification.

An additional [no-Docker recording workflow](desktop-no-docker-e2e.json) passed
against the same final packaged runtime. Separate negative controls rejected
three container command executions and two Docker socket connections before
host access. With a fresh HOME and restricted PATH, project creation, real H5
import, tags, query, reference export, reopen and orderly shutdown passed with
zero container command or non-MySQL Unix socket attempts. Packaged resources
remained unchanged; the user's Docker daemon and installed app were untouched.
This uses Python process/socket instrumentation and the exact bundled native
MySQL executable, rather than a kernel sandbox or clean-machine qualification.
