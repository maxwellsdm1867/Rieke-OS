# Sharing projects and receiving updates

## Choose the project folder itself

The **+** in the left project rail opens a popup over the current workspace.
Choose either project action inside it. The workspace remains visible; **×**
or **Escape** closes the popup and returns focus to **+**. Creating a new
project from the welcome screen also opens a popup.

Every project location field has **Browse…**. Choose folders using the local
folder picker; paths remain editable. New projects can use an existing empty
folder or a named new folder inside a chosen location. Move, share and restore
destinations ask for a new folder name. Browsing only selects a path; it does not
create or modify files. Cancel the folder picker to return to setup unchanged.

New project setup ends with **Cancel** and **Create & open**. **Cancel** closes
the popup and returns to the visible workspace.

The left sidebar has two project actions:

- **Add new project** opens an existing working project or a portable copy someone
  gave you. Selecting a prepared copy checks its inventory and opens the restore
  form automatically; choose a new local project folder, restore, then open it.
- **Start a brand new project** asks for a name and an empty folder and creates
  the project manifests and managed storage. Opening initializes its database.

New project asks for a name and one **Project folder**. That exact folder is the
project root: it can be anywhere writable, outside the application code. Choose a
new or empty folder; existing project folders should be opened instead. No extra
parent workspace or generated subfolder is required.

For example, name a new project **Spike response study** and choose a new or
empty folder named **Spike response study** in your own research location.
Matching names make the folder easier to recognize later. The project name is
shown in the app; the folder name can differ, and neither name is its unique
identity. A project's name can change without moving its files.

When reopening or receiving that project, select the **Spike response study**
folder itself. Its project files and contents should be directly inside it.
Choose its top folder rather than the research folder above it or an `imports`,
`database` or other folder inside it. The app checks the files to identify the
project, so a renamed folder can still be recognized.

Open project checks the identity manifests, storage layout and database files
before starting the project, then checks recording dependencies during opening.
It opens the folder in place. The preferred projects location is optional.

Created, restored and successfully opened project roots are remembered in a
local user-profile index, so projects on other drives or outside the preferred
location remain in the chooser after closing or restarting. The index contains
folder references and display identities; the project files stay in their
chosen location. An unavailable drive leaves an unavailable project entry.

Choose the top folder containing `project.json` and `catalog.json`, or the top
folder of a received portable copy. If you choose a project subfolder, the app
suggests its nearest valid project root. If you choose a parent, it lists valid
immediate child roots. Select **Use this folder**, then open or check that folder.
Several matches remain separate choices; the app does not open one automatically.
Nearby-folder discovery is bounded and read-only; it does not scan a whole drive.

To organize a closed native project, expand **Optional: move to a preferred
location**, select **Move this folder before opening**, and review the new exact
destination. The app moves the whole folder without overwriting an existing
folder, then opens it. In-app moves currently stay on one filesystem; for another
disk, close the project, copy its whole folder with the file manager, and open the
copy before removing the old folder.


## Automatic update availability

Rieke OS checks the official GitHub release channel when you open the app, every
15 minutes while the page is visible, and when you return after that interval.
No button press is required. A newer release highlights **Release / Publish**
with a persistent **Update** badge in the project sidebar and project chooser.
There is no toast, system notification, or automatically opened dialog. Opening
and closing the panel leaves the badge available until a successful check shows
there is no newer release.

Open **Release / Publish** for installed version, last check, release notes, and
an optional manual retry. The panel distinguishes **Up to date**, **No release
published**, and **Update check unavailable**. An offline check does not count as
up to date or erase an update already discovered during this app-service session;
the panel explains when a refresh failed. Manual retries bypass the automatic
check cache.

Managed installations with the official trusted signing key automatically
download and verify a new release in the background. The download prepares a
separate installation; it does not replace the running app or modify projects.
The badge changes to **Ready** once preparation completes. Close Rieke OS and all
project services, then launch normally through the stable manager or a workspace
launcher created by the managed app. That launch applies the prepared update.
If another service is still open, the current version continues to run.
Incompatible database versions are refused. Automatic shutdown/restart from the
browser is not implemented. Development checkouts can check for releases but
cannot install them in place.

No signed release or trusted production key has been published by this change.
Release workflows and signing setup must be configured before downloads become
available to users.

MATLAB is optional: the app runs without it. Only opening the EpicTreeGUI export
in MATLAB needs a MATLAB installation. The self-contained desktop installer is
still release-engineering work; the current source bundle requires setup tools.

## Open, move, or share a project folder

The main project catalog and user state remain MySQL/DataJoint. New projects use
an app-private MySQL 8.4 runtime; no Docker or system MySQL installation is needed.
SQLite continues to provide exports, rebuildable search indexes and daily state
snapshots. Raw recordings remain H5 files.

For ordinary movement between installations using the supported bundled runtime:

1. In **Project folder**, choose **Close project**. The app refuses while an import
   is active, drains requests, and closes its database cleanly.
2. Copy the entire project folder to the recipient or new location.
3. In the recipient's app, choose **Open project** and
   select that folder. No archive or prepared package is required.

The folder carries `project.json`, `catalog.json`, `storage.json`, database storage
and ownership files, retained recordings, imports, saved queries, and exports.
Opening recreates local runtime addresses, verifies project identity and recording
checksums, and rebases current file locations. Scientific UUIDs are preserved.
Closing a browser tab alone does not close a project database. Copying an open
MySQL data directory is unsupported; relocated folders marked unclean are refused.

Uploaded recordings are copied once into `raw-uploads` and verified by checksum
before parsing, so lazy traces use the project copy. **Open H5 folder** opens
that same directory. Drop new H5 files there to import automatically while the
project is open, after a five-second settling period; these import in place. After a successful import
confirms that verified copy, the original outside the project can be removed;
keep the managed copy in place. Older projects may still reference external recordings;
opening a moved folder reports missing dependencies rather than silently dropping
its data. Copies develop independently; this is not a synchronization or merge
mechanism. The direct-folder path is validated on Apple Silicon macOS with the
bundled MySQL version; it is not a promise of arbitrary MySQL-version or platform
interchange.

## Optional verified transfer and legacy projects

**Prepare to share** remains available when you want a separately verified copy
with a logical database backup and all registered recordings included. It tests a
restore before reporting success. After **Close project**, **Prepare portable
copy** opens sharing with that project's folder already selected. Give the entire
prepared folder to the recipient. Their **Add new project** action recognizes it
and restores it into a new folder with fresh native database credentials.
Existing projects are never overwritten.

The logical backup includes all acquisition and project database tables: saved
predicates and every preset version, query run records, explorer revisions and
bindings, tags and authors, review decisions, inclusion masks, tree layouts, source
state, exports and event history. New copies record table row counts and content
checksums; restoration compares every table before updating current file paths.
Existing transfer copies without this additional database inventory remain readable.

Recent search shortcuts and protocol pins/order are stored in
`protocols/ui-state/project-preferences.json`. The app migrates earlier browser
shortcuts when their project is opened, so these choices accompany subsequent
copies. Browser size, pane widths and the current user's author selection remain
local preferences. Durable import, app-job, error and storage history under
`logs/` is included; server process records and runtime logs are excluded.

Legacy Docker projects keep their original configuration and data. They are not
silently converted. Preparing a logical transfer from such a project still needs
its original database available; restoring that transfer creates a native project
that no longer needs Docker. Native-to-native transfers use the bundled server and
clients throughout.

Runtime logs, caches and existing backup directories are excluded from logical
transfers.
Historical export files retain their original bytes; external readers of old
exports may need embedded recording paths relinked. Interrupted logical restores
do not resume automatically; inspect the reported destination before retrying.
Plain-folder locator rebasing keeps a recovery journal and retries on the next open.

Restart an already-running development app to load these local-service changes,
then refresh its browser. A standalone signed desktop installer remains separate
release work; this implementation makes project storage independent of Docker.
