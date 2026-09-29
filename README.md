# Rieke Lab OS

A local workspace for organizing, exploring, annotating, and exporting Rieke Lab
neurophysiology recordings. Browse Symphony H5 recordings, inspect epochs and
traces, save reproducible protocol selections, and hand data off to MATLAB or
SQLite-based analysis.

**Runs locally without Docker.** The installer downloads an application-local
Python environment, Node, compiler tools, the recording parser, and native MySQL.
Each project has its own database and files. MATLAB is optional and is needed
only for MATLAB analysis and the included EpicTreeGUI.

## Download the whole app

**[Download main as a ZIP](https://github.com/maxwellsdm1867/Rieke-OS/archive/refs/heads/main.zip)**
for the current application and documentation, or choose a version from
[Releases](https://github.com/maxwellsdm1867/Rieke-OS/releases/latest) and download
its **Source code (zip)**. Extract the entire archive before installing. GitHub's
**Code → Download ZIP** also downloads the current `main` branch.

This is the complete **Rieke OS browser application**, including its installer,
backend, browser interface, and optional MATLAB/EpicTreeGUI companion. You do not
need a separate EpicTreeGUI checkout. It is not a Matplotlib desktop application.
The package includes the code needed to install the app; the installer downloads
its dependencies. Your recordings and research projects are separate.

Prefer Git? Clone the same app:

```sh
git clone https://github.com/maxwellsdm1867/Rieke-OS.git
cd Rieke-OS
```

## Install and launch

1. Put the extracted application folder somewhere permanent, such as
   `~/Applications/Rieke-OS-main`. Keep research projects outside it.
2. Open Terminal and change into that folder. On macOS, type `cd `, drag the
   extracted folder into Terminal, and press Return. The folder must contain
   `install.sh` and `start.sh`.
3. Run installation, wait until it finishes successfully, then start the app:

   ```sh
   sh install.sh
   sh start.sh
   ```

4. Keep Terminal open and visit [Rieke OS locally](http://127.0.0.1:8766).
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

### System requirements

The first installation requires internet access, several GB of free disk, and
`curl` and `tar`. Allow additional disk space for recordings and project databases.
macOS needs Apple's Command Line Tools (`xcode-select --install`) for the SDK
used by the parser's native extension. Complete that installation before running
`install.sh`. You do not need to install Python, Node, MySQL, uv, or Docker
separately. Everything managed by the installer lives under `.rieke-runtime/`;
the app installer does not require administrator privileges or a system database
service. Apple's separate developer-tools installer may require authorization.

**Platform status:** tested end to end on Apple Silicon macOS. Installer targets
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

## What you can do

- Keep multiple recording projects with independent catalogs.
- Import and browse Symphony recordings, cells, protocols, epochs, and metadata.
- Build metadata predicates and rearrange hierarchical epoch trees.
- Inspect raw response traces lazily from original H5 files.
- Save protocol selections, revisions, inclusion decisions, and authored tags.
- Export reference JSON, queryable Wheeler SQLite snapshots, and MATLAB bundles.
- Use the bundled EpicTreeGUI for MATLAB analysis and UUID-based tag exchange.

See the [quick start](docs/RIEKE_OS_QUICK_START.md),
[workspace guide](workspace-app/README.md), [tagging guide](docs/TAGGING.md),
[search presets](docs/SEARCH_PRESETS.md), and
[MATLAB/EpicTreeGUI guide](EPIC_TREE_GUIDE.md).

## Your files

```text
Rieke-OS/                       Application source and managed runtime
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
It is not an authenticated internet service. Ctrl-C stops the project chooser;
opened project servers and databases remain available until stopped or rebooted.
Do not copy a running MySQL data directory as a backup. The `backups/` directory
is only reserved storage, not an automatic backup service.

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
queries, saved selections, tags, JSON and MATLAB masks, all three export formats,
source changes, and database restart persistence. It independently reads exported
files and compares trace and QC values with the original H5. It rejects Docker
invocations:

```sh
.rieke-runtime/venv/bin/python packaging/verify_workflows.py --source /path/to/recording.h5
```

The recording stays unchanged and is never included in a release. See
[packaging and validation](packaging/README.md) for the distribution boundaries
and verification receipt.

## Dependencies and license

Rieke Lab OS includes EpicTreeGUI under the [MIT license](LICENSE). The installer
fetches [RetinAnalysis](https://github.com/DRezeanu/retinanalysis), DataJoint,
MySQL, scientific Python libraries, and conda-forge tools under their respective
licenses. Third-party packages are installed separately, not relicensed as part
of this repository. Parser revisions and Python package hashes are pinned in
`python/workspace-source.json` and `python/workspace-runtime.lock`. The verified Apple Silicon native tool set is locked in
`packaging/native-osx-arm64.lock`; other targets resolve conda-forge packages.
The installed package receipt is under
`.rieke-runtime/native/conda-meta/`.
