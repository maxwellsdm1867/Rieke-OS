> **Disco 0.1.10 · Mac desktop testing build:** [Download the Apple silicon ZIP](https://github.com/maxwellsdm1867/Rieke-OS/releases/download/desktop-test-v0.1.10/Disco-0.1.10-arm64.zip) · [Prerelease details and checksums](https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.1.10). Extract the ZIP, quit Disco, replace your existing **Disco.app** with the extracted app, and reopen it. Existing project folders remain separate and can be reopened. Python and native MySQL are bundled; no Docker or Terminal setup is needed. Use manual replacement for this prerelease; the in-app updater is under investigation. This build is unsigned and unnotarized, so macOS may require **Privacy & Security → Open Anyway**. It targets macOS 14+, but runtime checks were on macOS 27.0.1; macOS 14 runtime support is unqualified and Intel is unsupported. This is a manual testing download, not a stable release.

# Disco

Data Inspection, Selection, Comparison Operations · A Rieke Lab OS

The application is named Disco. Source, releases, updates and support remain in the existing `maxwellsdm1867/Rieke-OS` repository.

**Disco is a local research workspace for Symphony electrophysiology recordings.**
It turns a folder of H5 files into an organized project where you can find cells
and trials, inspect recorded responses, decide which epochs belong in an analysis,
and export that exact selection with its metadata and history.

The app is designed around retinal physiology workflows: a cell can have
characterization recordings, several acquisition protocols, and many repeated
trials. Disco keeps those relationships visible while you move between a
project overview, a cell's recordings, a metadata search, and individual traces.
An **epoch** is one recorded trial; a **protocol** is the acquisition procedure
recorded in the source file.

Your project saves the work around the recordings: searches, named working
datasets, cell and epoch tags, inclusion decisions, and exports. Original H5
files retain the waveform samples. The app catalogs their metadata and reads
response windows on demand, keeping each displayed trace and exported epoch
linked to its source identity.

**It runs locally as a Mac desktop app or from source in a browser, with a separate
local database for each project.** The desktop build bundles its runtime; the source
installer manages the required tools. New projects need no Docker, LLM account, or
API key. MATLAB data export uses managed Python and SciPy.

## From recordings to an analysis dataset

| Your task | What Disco provides |
| --- | --- |
| Organize recordings | Import original Symphony H5 files by path or upload; browse dates, cells, acquisition protocols, blocks and epochs in a project catalog. |
| Find the relevant trials | Search recorded metadata and authored tags with nested conditions; save reusable searches and inspect the matching epochs. |
| Inspect a cell | Open full-rate response windows, choose a recorded device, zoom to samples, and review trial metadata. The cell workbench brings its characterization recordings together across protocols. |
| Arrange an experiment | Group epochs into trees using recorded fields such as date, cell, block or stimulus parameters. Save a named protocol working dataset from a compatible selection. |
| Record scientific decisions | Tag a whole cell or individual epochs with an author name; include or exclude epochs for a working dataset. Review markers are optional. |
| Keep a selection reproducible | Review additions and removals before updating a working dataset. Save exports with the query, exact epoch identities, inclusion decisions, annotations and source checksums. |
| Continue analysis | Download a queryable SQLite database, MATLAB data (.mat), or reference JSON. Portable tag and selection JSON can be imported into the workspace. |

For example, you can import recordings from several days, find one recorded
protocol in cells of interest, split its trials by a stimulus parameter, inspect
responses, exclude unsuitable epochs, and export the retained dataset. Later,
you can rerun the search or compare new recordings with the saved working set;
earlier exports keep their original membership.

The browser's cell workbench includes recorded temperature/resistance metadata,
condition-response summaries, and block-onset voltage estimates for supported
protocol families. These displays retain their source and method information;
missing measurements remain unavailable, and voltage estimates are labeled as
estimates. Cell typing and scientific interpretation remain the researcher's
responsibility.

Read the [product and data-model overview](docs/RIEKE_OS_OVERVIEW.md) for how
projects, searches, working datasets, annotations and exports fit together.

## What is in the 0.1.10 testing build

This build combines complete Workbench selections and source-specific merge controls
with the H5 precision fixes and exact saved-filter, recipe, snapshot and transfer
JSON transport. Highlighted rows in the Workbench Epochs view now use the same blue
fill as Split tree; selected-for-merge rows retain their separate green state.

The current ZIP is built from clean source
[`31182a4`](https://github.com/maxwellsdm1867/Rieke-OS/commit/31182a40c22da05f904dda6979ac6bcf0d4996b0).
The [release notes and exact-byte metadata](https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.1.10)
identify the current build, checksums, validation and remaining updater limits.
If you downloaded 0.1.10 before the highlight correction, download the current ZIP
again; its displayed version remains 0.1.10.

Earlier [0.1.8 package history](docs/dev/navigation-package.md) and its
[package record](docs/dev/local-package-0.1.8.json) remain historical evidence,
not the identity of the current download.

## Working on the code

The code is organized around **deep modules**: small interfaces that hide substantial
behavior, with the public contract and focused tests beside the implementation.
For example, tree-selection readers own ordered bounded reads, presentation sessions
own route snapshots, and group-save sessions own exact retry identity and recovery.
Scientific authority stays with the relevant command, catalog or source owner.
Folder moves improve discoverability; they do not by themselves prove new depth or
better performance.

Start with [implemented module interfaces](ARCHITECTURE.md#deep-modules-in-the-current-source),
the [physical module guide](ARCHITECTURE.md#module-guide), and
[repository instructions](AGENTS.md). Follow [frontend navigation](workspace-app/src/AGENTS.md),
[desktop navigation](desktop/AGENTS.md), [backend navigation](python/AGENTS.md),
or [tooling navigation](tools/AGENTS.md) for the area you are changing. Local guides
own the detailed contract, executable examples and scoped checks.

The [module ledger](docs/architecture/core-module-ledger.md) and its
[frontend](docs/architecture/core-module-ledger.md#frontend-finite-abc-current-path-composition)
and [backend](docs/architecture/core-module-ledger.md#backend-finite-current-path-composition)
path records separate implemented organization, retained owners and proposals.
Their earlier source and test receipts remain historical evidence; use the
[current release metadata](https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.1.10) for the downloadable build.
The broader [stable-ports design](docs/architecture/stable-ports.md) remains a
proposal beyond the explicitly adopted slices.

## Source download (developer workflow)

**[Download main as a ZIP](https://github.com/maxwellsdm1867/Rieke-OS/archive/refs/heads/main.zip)**
for the current application and documentation, or choose a version from
[Releases](https://github.com/maxwellsdm1867/Rieke-OS/releases) and download
its **Source code (zip)**. Extract the entire archive before installing. GitHub's
**Code → Download ZIP** also downloads the current `main` branch.

This is the complete **Disco browser application**, including its installer,
backend and browser interface. Its application code is independent of EpicTreeGUI.
MATLAB plotting, interactive GUI code and launchers are not included.
The package includes the code needed to install the app; the installer downloads
its dependencies. Your recordings and research projects are separate.

Prefer Git? Clone the same app:

```sh
git clone https://github.com/maxwellsdm1867/Rieke-OS.git disco
cd disco
```

## Install and launch

For the complete Mac app, use the 0.1.10 ZIP and installation steps described above.
The following commands apply only to a source checkout.

1. Put the extracted application folder somewhere permanent, such as
   `~/Applications/disco-main`. Keep research projects outside it.
2. Open Terminal and change into that folder. On macOS, type `cd `, drag the
   extracted folder into Terminal, and press Return. The folder must contain
   `install.sh` and `start.sh`.
3. Run installation, wait until it finishes successfully, then start the app:

   ```sh
   sh install.sh
   sh start.sh
   ```

4. Keep Terminal open and visit [Disco locally](http://127.0.0.1:8766).
   Choose a workspace folder, select **Add project**, and open the project.
   Use **Add data store** when you are ready to import a Symphony H5 recording.
   You can create and open an empty project without a recording.

Using `sh` also works if your ZIP extractor did not preserve executable file
permissions. Git users can use `./install.sh` and `./start.sh` instead.

**Next time:** return to the same application folder and run `sh start.sh`.
Select the same workspace and project. You do not need to reinstall each time.

For the full first-recording walkthrough, follow the
[quick start](docs/RIEKE_OS_QUICK_START.md). For help from an AI coding assistant,
copy the [LLM installation prompt](docs/LLM_SETUP.md).

### Source-install requirements

The first installation requires internet access, several GB of free disk, and
`curl` and `tar`. Allow additional disk space for recordings and project databases.
macOS needs Apple's Command Line Tools (`xcode-select --install`) for the SDK
used by the parser's native extension. Complete that installation before running
`install.sh`. You do not need to install Python, Node, MySQL, uv, or Docker
separately. Everything managed by the installer lives under `.rieke-runtime/`;
the app installer does not require administrator privileges or a system database
service. Apple's separate developer-tools installer may require authorization.

**Source-installer platform status:** tested end to end on Apple silicon macOS. Installer targets
also exist for Intel macOS and x86_64/ARM64 Linux, but those platforms are
experimental until independently tested. Windows is not currently supported.
MATLAB is optional and needed only for MATLAB analysis. No LLM or API key is
required to run the app.

This is a source distribution with an automated installer, not a signed desktop
app or an offline installer. Subsequent launches use the installed runtime and
built browser app. Keep the installation in its original location; reinstall
from a fresh copy if you move it.

### If setup or launch fails

Run these commands from the application folder:

```sh
# Check an installed runtime without importing recordings or starting a database.
.rieke-runtime/venv/bin/python rieke.py doctor --json

# If the default launcher port is already in use:
sh start.sh --port 8870
```

For the second command, open [port 8870](http://127.0.0.1:8870).
If the managed Python does not yet exist, installation has not completed: address
the install error and rerun `sh install.sh`. See
[troubleshooting](docs/RIEKE_OS_QUICK_START.md#if-a-step-fails) for import and
workspace issues. Keep the exact error when asking for help.

## Workflow guides

- [First recording through first export](docs/RIEKE_OS_QUICK_START.md)
- [Tags, authors and scope](docs/TAGGING.md)
- [Reusable searches](docs/SEARCH_PRESETS.md)
- [Browser workspace reference](workspace-app/README.md)
- [Application architecture](ARCHITECTURE.md)

## Your files

```text
disco/                       Application source and managed runtime
  .rieke-runtime/               Downloaded tools, parser, Python, and configuration
  workspace-app/dist/           Built browser interface

Your workspace/                 Separate folder you choose in the app
  project-name-<id>/
    project.json                Project identity
    catalog.json                Database reference (no password)
    database/mysql/             This project's native MySQL data
    database/native.json        Local private database credentials (mode 0600)
    imports/                    Parsed metadata and source references
    raw-uploads/                Copies uploaded through the browser
    protocols/                  Saved protocol definitions
    exports/                    Versioned exports
    logs/                       Import and application diagnostics
```

Path imports reference original H5 recordings; keep those files available and
unchanged. Browser uploads copy recordings into the project. Sharing this
repository shares application code, not your projects, recordings, annotations,
or database credentials. Export the intended scientific selection separately.

The app binds only to `127.0.0.1` and is intended for a single user's computer.
It is not an authenticated internet service. In the source/browser workflow, Ctrl-C
stops the project chooser; opened project servers and databases remain available
until stopped or rebooted. The desktop app coordinates its owned processes through
its Quit workflow.
Do not copy a running MySQL data directory as a backup. Current app state is saved to `app-state.json` with daily SQLite state snapshots
in `backups/app-state/`. These do not copy recordings or the live database. See
[storage and recovery](docs/STORAGE_RECOVERY.md).

Existing Docker-backed projects retain their original backend and still require
Docker. They are not automatically migrated or replaced. New projects use native
MySQL. Import recordings into a new project to begin a separate native catalog;
this does not transfer old tags or revision history.

## Development and verification

```sh
.rieke-runtime/venv/bin/python rieke.py doctor
PYTHONPATH=python .rieke-runtime/venv/bin/python -m unittest discover -s python/tests
PATH="$PWD/.rieke-runtime/native/bin:$PATH" npm --prefix workspace-app test
PATH="$PWD/.rieke-runtime/native/bin:$PATH" npm --prefix workspace-app run build
```

The full integration check creates an isolated project and tests real H5 import,
queries, saved selections, tags, portable JSON selection masks, all three export formats,
source changes, and database restart persistence. It independently reads exported
files and compares trace and QC values with the original H5. It rejects Docker
invocations:

```sh
.rieke-runtime/venv/bin/python packaging/verify_workflows.py --source /path/to/recording.h5
```

The recording stays unchanged and is never included in a release. See
[packaging and validation](packaging/README.md) for the distribution boundaries
and verification receipt.

## Metadata handoff contract (draft)

The [reviewed metadata bundle handoff kit](contracts/metadata-bundle/v1-draft/README.md)
provides the public `1.0.0-draft.1` schema, mapping guidance, synthetic examples
and offline validation tools. **The application does not accept this bundle.**
Its source catalog records the pinned `fafb826` comparison and installed
RetinAnalysis evidence; it does not certify live database or current-main compatibility.

## Dependencies and license

Disco application source is available under the [MIT license](LICENSE). The installer
fetches [RetinAnalysis](https://github.com/DRezeanu/retinanalysis), DataJoint,
MySQL, scientific Python libraries, and conda-forge tools under their respective
licenses. Third-party packages are installed separately, not relicensed as part
of this repository. Parser revisions and Python package hashes are pinned in
`python/workspace-source.json` and `python/workspace-runtime.lock`. The verified Apple Silicon native tool set is locked in
`packaging/native-osx-arm64.lock`; other targets resolve conda-forge packages.
The installed package receipt is under
`.rieke-runtime/native/conda-meta/`.

### Versioned benchmarks

Run and compare the fixed frontend/database core using
[the benchmark guide](docs/dev/benchmarks.md). The
[case registry](benchmarks/registry.json) records supported cases and open gates;
[AGENTS.md](AGENTS.md) gives fresh coding agents the entry point. Release promotion
requires exact-commit benchmark evidence; native qualification gaps remain visible.
