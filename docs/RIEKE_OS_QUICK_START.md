# Rieke OS quick start

You can install and open an empty project before choosing a recording. For the
import and export steps, have an original Symphony `.h5` or `.hdf5` file ready.
Rieke OS provides its own plotting and curation interface; MATLAB is needed only
if you choose to analyze an exported MAT data file with MATLAB.

## 1. Download, install, and open

On [Rieke OS Releases](https://github.com/maxwellsdm1867/Rieke-OS/releases), choose
the Apple Silicon **unsigned testing** release and download its `.dmg` asset.
The desktop DMG contains the complete app and private Python/MySQL runtime;
GitHub's **Source code (zip)** is a separate developer download.

1. Open the DMG and open **Rieke OS** inside it.
2. If macOS blocks the trusted unsigned download, review **System Settings →
   Privacy & Security → Open Anyway**. This is a manual macOS approval; the
   installer preserves quarantine and does not bypass it.
3. Click **Install and Open**. Wait for the complete copy to finish. The installed
   app lives at `~/Applications/Rieke OS.app`; next time, open that app normally.

No Terminal, Docker, external Python, Node, or MySQL setup is required for the
packaged desktop app. Apple Silicon macOS is the supported testing target; the
bundle declares macOS 14.0 as its minimum, with minimum-version and independent
clean-machine qualification tracked separately. See [testing release details](dev/GITHUB_TESTING_RELEASE.md).

For source development instead, extract or clone the dedicated Rieke OS
repository and follow [source setup](../README.md#install-and-launch) or the
[LLM setup prompt](LLM_SETUP.md). Source setup needs build tools and network
access; it is not the desktop installation workflow.

## 2. Choose a project folder

1. On **Your projects**, choose **Start a brand new project** and enter its name.
2. Click **Browse…** next to the project folder. Select an empty folder, or select
   a parent folder and enter a new child-folder name in the confirmation dialog.
   Folder paths are shown read-only; no absolute path needs to be typed.
3. Click **Create & open** and wait for its private database to start. Choose or
   create an author profile when prompted to add or import tags.

Keep projects outside the application bundle. The optional preferred projects
folder is also selected with **Browse…**; projects can live elsewhere.

**Check:** Project overview shows the chosen name and zero imported epochs.

To open an existing project, choose **Add new project**, then **Browse…** to its
**top project folder**, containing `project.json` and `catalog.json`. Select the
project itself, not a parent workspace or an inner `database`/`imports` folder.
The app checks its identity before opening. For a legacy source project, review
**Create desktop copy** or receive a prepared portable copy; the original is
preserved. See [project sharing and updates](WORKSPACE_SHARING_AND_UPDATES.md).

## 3. Import an original recording

A legacy `.auisql.h5` cache is not an original Symphony recording.

1. Choose **Add data store** or **Data stores → Add H5**.
2. Choose **Browse H5 files**, or drag an original recording into the import area.
   The app creates a managed copy and verifies it before parsing. Keep the
   original until the import confirms success; retain the managed copy afterward.
3. Wait for **Import history** to show completion. Upload/copy completion alone
   does not mean parsing and catalog registration have finished.
4. Return to **Project overview** and check the cells and epochs. **Data stores**
   reports the source location and availability.

Open a protocol, choose **Open inspection** or **Browse epochs**, expand the date
and cell, and select an epoch. Confirm that a recorded response loads before
curating a larger selection. Missing source data remains an error rather than a
substituted waveform.

## 4. Inspect, tag, and choose inclusion

The web inspector plots recorded response windows and displays their metadata.
Selecting an epoch focuses its trace. Cell/epoch tags have author attribution;
protocol inclusion and review markers are separate decisions.

- Include or exclude an epoch for its protocol working dataset.
- Select multiple epochs for an explicit bulk action and check the count first.
- Use **Tags** and **Tag tools** to choose an author, add tags, or exchange JSON.
- Use **Search predicate** to find metadata/tag matches and save reusable searches.
  Saving a selection revision freezes membership; it does not update a protocol
  automatically. See [search presets](SEARCH_PRESETS.md).

Action targets and the focused cell do not define export membership. Export uses
its saved query, active filters, and inclusion policy. Review is optional unless
you deliberately select a reviewed-only export policy.

## 5. Exchange tags or inclusion JSON

Import the recording first, then use the matching identities:

| File | Control | Effect |
| --- | --- | --- |
| Rieke or supported Samarjit tag JSON | Tags → Tag tools → Import tags | Preview and explicitly add author-scoped cell/epoch tags by UUID. |
| Recording Selection Mask v1 JSON | More → Import mask file… → Import JSON mask | Restore inclusion for the entire matching protocol query; protocol UUID, source revisions and exact membership must match. |
| Query-preset JSON | Search predicate → Import query | Open a query draft for review and execution against the current project. |

**Save JSON mask** prepares an ordinary JSON download. Choose where to save it;
tags and review markers are not inclusion masks. MAT data files and historical
MATLAB UGM files are not supported mask imports. Do not rewrite UUIDs to force a
rejected file to match. See [tagging](TAGGING.md) for author/scope behavior.

## 6. Export data

1. Choose **Export** and select **Wheeler SQL database**, **MATLAB data (.mat)**,
   or **Advanced formats → Reference JSON**.
2. Optionally name the export. Keep **Included epochs (no review requirement)**
   unless reviewed-only membership is intended.
3. Review the displayed scope/count, then click **Save & export … epochs**.
4. Download the completed artifact. Existing exports remain immutable and appear
   in the project export log with their recipe and provenance.

MAT export is a standalone `recordings.mat` data file, readable with standard
MATLAB `load`. It contains recorded metadata, selection, annotations, provenance
and lazy H5 references for standard `h5read`; it includes no MATLAB plotting GUI,
launcher or interaction workflow. SQLite and reference JSON retain equivalent
frozen selection evidence. Keep referenced H5 recordings available.

Historical MATLAB bundles remain downloadable as **Legacy MATLAB bundle**.
Reusing their saved destination opens the current data-only MAT choice for an
explicit new export.

## 7. Close, reopen, and update

Use **Close project** before moving or copying its whole folder. Ordinary app
Quit preserves drafts and waits for scientific services; an active import can
defer closing. It never force-stops a writer. Reopen the installed app and select
your remembered project. See [storage and recovery](STORAGE_RECOVERY.md).

The unsigned testing app checks GitHub metadata at startup and about hourly.
**Release / Publish** shows an available version; choose **Download update**, then
**Restart to update** when ready. Ordinary Quit does not install a testing update.

## If a step fails

Keep the exact error and current project/source files. Retry startup from the
recovery page when appropriate. A busy-close message means current work must
finish. Missing/changed H5 data requires restoring the correct source rather
than accepting another file under the same name. A malformed saved view has an
explicit recovery choice that preserves its original bytes.

Do not delete a live database or copy an open MySQL data directory. For source
installation diagnostics, use the commands in [setup troubleshooting](../README.md#if-setup-or-launch-fails).
