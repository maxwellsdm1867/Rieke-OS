# Rieke Lab OS quick start

Install and open an empty project without any recording. For the import and
export steps, have one original Symphony `.h5` or `.hdf5` recording ready. You will create a
project, inspect a cell, save inclusion decisions, download an export, and reopen
your work. If someone gives you existing selections, ask for the recording **and**
the matching selection/tag files; the H5 alone does not contain another Rieke OS
project's curation history.

## 1. Download, install, and start

Download [the whole app from main](https://github.com/maxwellsdm1867/Rieke-OS/archive/refs/heads/main.zip),
or choose **Source code (zip)** on the
[latest release](https://github.com/maxwellsdm1867/Rieke-OS/releases/latest).
Extract the entire archive into a permanent application folder. This includes the
browser app and optional MATLAB companion; no separate repository is required.
In Terminal, change to the extracted folder (typing `cd ` and dragging the folder into Terminal supplies its
path), then run:

```sh
sh install.sh
sh start.sh
```

Wait for installation to finish successfully before running `sh start.sh`.
Using `sh` works even if the ZIP extractor did not preserve executable permissions.
For AI-assisted setup, copy the [LLM setup prompt](LLM_SETUP.md).

Keep the terminal open and visit **http://127.0.0.1:8766** in your browser.
Installation requires internet, several GB of disk space, and on macOS Apple's
Command Line Tools (`xcode-select --install` if missing). The installer manages
Python, Node, the parser, and native MySQL; Docker is not needed for new projects.
Apple Silicon macOS is the tested platform. Other supported installer targets
are experimental; Windows is unsupported. See [system requirements](../README.md#system-requirements).

## 2. Choose a workspace and create a project

1. In **Workspace root**, choose **Choose folder** if the folder shown is not the
   one you want. Enter an absolute path such as
   `/Users/yourname/Documents/RiekeLabWorkspace`, then **Use this workspace**.
   Choose a folder outside the application folder. This is the parent folder for
   all your projects, not an individual project folder.
2. Choose **Add project**, enter a name such as `First cell`, and leave the
   optional project folder blank. Choose **Create & open project**.
3. Wait while the project database starts. The project opens at its own local
   browser address. Choose or create your author profile when prompted; this
   identifies who adds or imports tags. Browsing does not require an author.

**Check:** Project overview shows your project name and zero imported epochs.
The **First recording? Start here** panel repeats the basic workflow in the app.

### Find or open an existing project folder

Inside a project, choose **Project folder** under **Project record** in
the sidebar. If the sidebar is hidden, use **Show sidebar** first. The dialog
shows the current project's full root path and offers **View project files**.

To switch to an existing project elsewhere, paste its absolute folder path into
**Existing project folder**, then choose **Open project folder**. Select the
folder containing `project.json` and `catalog.json`, not the parent workspace.
The app validates those manifests and opens that project's own service; an
invalid or missing folder is rejected without creating a project there.

This selects an existing project in its original location. It does not move the
current project, relocate databases, or import an arbitrary data folder. To
create a new project, use **Add project** instead.

## 3. Import your recording

Use an **original Symphony recording H5**. A legacy `.auisql.h5` file is a
flattened stream cache, not an interchangeable Symphony recording; those cache
files cannot be imported through this workflow. If your cell folder contains
both, choose the original Symphony files. Import separate recordings one at a
time and check each result.

1. Choose **Add data store** on Project overview, or **Data stores → Add H5**.
2. Choose **Choose H5 file** (or drag the H5 into the upload area). This copies
   the recording into the project's `raw-uploads` folder. Alternatively, enter
   an absolute local path and choose **Import from path**; that references the
   original recording, so its drive must remain connected and the path unchanged.
3. Wait for the import job to finish. Upload completion is only the first stage;
   parsing, validation, and catalog registration must also finish. Check
   **Import history** for the result and any warnings.
4. Return to **Project overview**. Check that the expected cells and epochs are
   present. **Data stores** shows the source path and availability.

**Check:** Open an experimental protocol, or expand **QC & typing** for typing
recordings. Choose **Inspect epochs**, expand the date/cell list, and click an
individual epoch. Confirm that a response trace loads. Do this before curating a
large dataset. If no trace loads, verify the source is available in Data stores.

## 4. Select epochs and save your work

In the protocol's **Inspect epochs** view:

- Click an epoch to focus its trace. **Include focused epoch** / **Exclude focused
  epoch** saves that inclusion decision immediately for this protocol.
- Check multiple epochs to target a bulk action, then choose Include, Exclude,
  or **Tag selected epochs**. Read the action's epoch count before applying it.
- Choose **Tags** to add shared cell/epoch tags. Select the intended scope,
  choose an author under **Tag tools** if needed, then **Add tag**. Dataset-only tags belong to this protocol selection.
- Review markers are optional. You can export included epochs without marking
  them reviewed.

**Checkboxes are action targets, not export membership.** Clearing checkboxes or
focusing another cell does not undo saved inclusion decisions. Protocol export
uses its saved query, active filters, and inclusion decisions. The export dialog
shows the scope and count before saving.

For a reusable metadata search, choose **Search predicate**, run a predicate,
then **More → Save query preset** in the results. A preset reruns the method on
current project data. **Save selection revision** records the matching epoch
identities at that moment. Neither action alone updates a protocol's working
dataset. See [search presets](SEARCH_PRESETS.md) for the distinction.

## 5. Bring existing tags or selections (optional)

Import the H5 recording first. These files serve different purposes:

| You have | Where to use it | What it restores |
| --- | --- | --- |
| Rieke or Samarjit tag JSON | Inspect epochs → Tags → Tag tools → Import tags | Shared cell/epoch tags matched by UUID. Choose an author, review the preview, then import. |
| Rieke selection-mask JSON | Inspect epochs → More → Selection masks → Import JSON mask | Inclusion decisions for the **entire matching protocol query**, including hidden cells. Protocol UUID, source revisions, and exact membership must match. |
| EpicTree UGM v1.1 (`.ugm`) | Selection masks → Import MATLAB UGM | Inclusion decisions for a matching **completed MATLAB export already recorded in this project**. Choose the export if automatic matching is ambiguous. |
| Exported query-preset JSON | Search predicate → Import query | A query draft to review, run, and save against this project's recordings; it does not copy past membership. |

Use **Tags → Tag tools → Export tags** to download existing shared tags.

To make a Rieke selection mask, use **Save JSON mask** beside the import control.
Tags and review markers are separate from inclusion masks. An arbitrary MATLAB
selection, a `.mat` file, a reference export JSON, or a project folder is not an
interchangeable mask. Mask import is not a general cross-project migration tool.
If a file is rejected, keep the original and read the error; do not rewrite UUIDs
to force a match. Ask the sender for the correct export and recording provenance.

## 6. Export and share a selection

1. In the protocol, choose **Export**. For a first export choose **Wheeler SQL
   database**, which creates a queryable SQLite file. **EpicTreeGUI** creates a
   MATLAB bundle; **Advanced formats → Reference JSON** saves a reference package.
2. Name the export. Keep **Included epochs (no review requirement)** unless you
   deliberately want only reviewed epochs.
3. Check **Export scope** and **Ready to export**. The focused cell and action
   checkboxes do not narrow this scope. Apply protocol filters or build a
   separate search if you need a smaller selection.
4. Choose **Save & export … epochs**, wait for success, then use the download
   link. Find the saved artifact again in **Export log**.

**Check:** The export log shows the expected name, format, and epoch count.
Exports preserve metadata and source references; they do not bundle the raw H5
waveforms. A collaborator who needs traces also needs access to the original
recordings. Sharing the application repository does not share project data.

## 7. Close and reopen

After saving, close the browser tab. On your next visit run `sh start.sh` (no reinstall needed) from the
application folder, open **http://127.0.0.1:8766**, and select the same workspace
and project. Confirm your tags, inclusion decisions, project saved searches, and
Export log remain available. Recent unsaved searches and navigation shortcuts
are browser-local conveniences, so save important queries explicitly.

Ctrl-C stops the chooser terminal; previously opened project servers and native
databases may keep running and are reused. It is not an all-services shutdown.
Keep both the application installation and the workspace in their original
locations. A project folder or live MySQL directory copy is not a supported
migration or backup method.

## If a step fails

- **`install.sh` or `start.sh` is missing:** change into the extracted Rieke-OS
  folder. Download the whole archive, not individual files or the older
  `epicTreeGUI` repository.
- **Installation fails:** resolve the reported requirement, then rerun
  `sh install.sh`. Run `.rieke-runtime/venv/bin/python rieke.py doctor` from the
  application folder to check the installed environment.
- **Launcher address is busy:** use `sh start.sh --port 8870`, then open
  `http://127.0.0.1:8870`.
- **Import fails or reports a warning:** expand its **Import history** entry and
  **Import evidence & diagnostic details**. Check whether catalog commit is
  confirmed before retrying. Duplicate H5 contents are recognized even if renamed.
- **Wrong workspace or no projects:** use **Choose folder** at the launcher and
  select the parent of the project's folder. Changing roots does not move data.
- **Mask rejected:** check the file type and matching rules in step 5. A new
  project does not inherit the old project's export history.

When requesting help, include the failed step, visible error, application
version, and operating system. Keep database credentials out of shared reports.

## Optional: launch from the workspace folder

To initialize a workspace from Terminal instead of the browser:

```sh
.rieke-runtime/venv/bin/python rieke.py init "$HOME/Documents/RiekeLabWorkspace"
```

`init` creates a workspace marker and launch script without downloading anything
or starting services. It preserves existing files and refuses to overwrite its
marker or launcher. Then launch explicitly:

```sh
sh "/path/to/Rieke-OS/start.sh" --workspace "$HOME/Documents/RiekeLabWorkspace"
```

An explicit `--workspace` requires an initialized folder. With no flag, the app
can discover a workspace marker above the current directory or reuse the last
workspace selected in the launcher.

## Where files live

```text
Application checkout/
  rieke.py                    setup, doctor, init, launch
  .rieke-runtime/             installed Python, parser, runtime configuration
  workspace-app/dist/        built browser application

RiekeLabWorkspace/
  .rieke-workspace.json       workspace identity/version marker
  rieke-workspace.py          entry point linked to the application checkout
  .rieke-os.json              last-opened project preference (created on use)
  project-name-<id>/
    project.json             project identity
    catalog.json             database reference
    storage.json             managed directory contract
    database/                service configuration and persistent MySQL files
    protocols/               saved protocol queries
    imports/                 parsed metadata and source references
    raw-uploads/             recordings uploaded through the browser
    query-snapshots/          frozen query baselines
    exports/                 exported data/reference packages
    logs/                    import, application, error and storage logs
    cache/                   rebuildable derived indexes
    backups/                 reserved location for verified backups
```

Path-based imports reference original recordings in place; browser uploads keep
copies in `raw-uploads`. Keep referenced external drives available. The `backups`
folder does not itself create backups. A running MySQL directory is not a valid
file-copy backup, and moving projects is not yet a supported migration flow.
See [storage and migration details](../README.md#your-files).

If the application checkout moves, reinstall it, then update `application` in `rieke-workspace.py`.
Do not move project folders to repair an application path. For dependency errors,
run `/path/to/Rieke-OS/.rieke-runtime/venv/bin/python /path/to/Rieke-OS/rieke.py doctor`; rerun `sh install.sh` to repair the
managed runtime. When upgrading while an older project server is running, restart
your computer before reopening projects with the updated app. Closing a browser
tab alone does not stop its background server or database. If the chooser port is occupied, choose another with `--port`.

## Workspace and author selection in the app

The launcher displays the full **Workspace root**. Choose **Choose folder** and
enter an absolute path, then **Use this workspace**. A new root receives the
workspace marker and launch script. A valid existing root is reused and its
immediate project folders are discovered without replacing their manifests or
files. Select the parent workspace, not the folder containing an individual
`project.json`. New project folders remain separate children of that root.
The chooser rejects folders inside an existing project or workspace; select the
existing workspace root instead. Spaces and Unicode characters are supported.
A rejected choice leaves the current root and its files unchanged.

Keep these three locations distinct:

| Location | Example | Purpose |
| --- | --- | --- |
| Application | `~/Applications/Rieke-OS` | Code and installed tools; reinstall if moved |
| Workspace root | `~/Documents/RiekeLabWorkspace` | Parent of project folders and their databases |
| Original recordings | Any accessible recording folder | Referenced by absolute path; browser uploads instead copy into the project's `raw-uploads` folder |

Path imports require an absolute file path (or a `~/...` path); they never resolve
relative to the server's working directory. The project file browser cannot
traverse outside the project or browse native MySQL data. Upload and export
folders cannot be redirected through symbolic links.

Do not rename, move or copy imported project folders as a migration method.
Internal metadata, source and saved-export references include absolute paths.
A copied project must not attach to the original project's database, even if its
IDs match. Restore the original location if a project was moved; use a separate
new project and explicit imports/exports for a separate catalog. There is no
automatic project relocation tool. If a saved workspace disappears, reconnect
its drive or restore its location; startup will not silently recreate it. You can
explicitly select another initialized workspace with `sh start.sh --workspace /absolute/path/to/workspace`.


The last root chosen in the UI is recorded locally in
`.rieke-runtime/workspace-selection.json`; it is used on subsequent launches
unless an explicit `--workspace`, discovered workspace marker, or environment
root takes precedence. Root selection does not relocate an existing project,
move its database, or copy its recordings.

After opening a project, the author picker offers existing profiles or creation
of a named profile. The OS username is a suggestion, not automatic consent to
attribute tags to that name. Choose an author before adding or importing tags;
browsing and exporting existing tags do not require that choice. The selected
profile UUID is remembered per project in this browser, while the profiles,
authored tags and audit history live in the project database. The profile
button in the bottom-left rail changes the active author. A different browser
must choose an author again; it cannot silently inherit another person's choice.
