# Rieke Lab OS quick start

Install the application once from its extracted source folder:

```sh
./install.sh
./start.sh
```

Open <http://127.0.0.1:8766>. Choose a workspace folder, add a project, and open it.
New projects use a private native MySQL database; Docker is not required.
See the [main README](../README.md) for system requirements and platform status.

For a workspace-local launch command, optionally initialize its parent folder:

```sh
.rieke-runtime/venv/bin/python rieke.py init "$HOME/Documents/RiekeLabWorkspace"
```

`init` creates a workspace marker and a small launch script. It downloads nothing,
starts no services, and leaves existing files in that folder intact. It refuses
to overwrite an existing marker or launch script. A workspace holds multiple
projects; initialize their parent folder, not an individual project's folder.
Workspace storage must be separate from the application checkout.

## Start from your workspace

```sh
cd "$HOME/Documents/RiekeLabWorkspace"
/path/to/Rieke-OS/start.sh --workspace "$PWD"
```

Keep that terminal open and visit <http://127.0.0.1:8766>. Choose **Add project**,
give it a name, then open it. Opening initializes that project's native database. Use **Add data store** to connect
recordings. Creating an empty project does not require a recording or Docker.

The launch script works from any current directory and handles spaces in paths.
You can also invoke the installed app from a workspace or any of its subfolders:

```sh
/path/to/Rieke-OS/start.sh
```

For explicit selection or a different chooser port:

```sh
/path/to/Rieke-OS/start.sh --workspace "$HOME/Documents/RiekeLabWorkspace" --port 8870
```

Selection order is `--workspace`, the nearest workspace marker above the current
directory, `RECORDING_WORKSPACE_ROOT`, the last root selected in the launcher, the root saved during setup, then the legacy
`RECORDING_PROJECT_DIR` parent or `~/Documents/RecordingWorkspace`. Explicit
`--workspace` requires an initialized folder. Existing unmarked installations can
continue using the environment variable or the setup configuration.

Ctrl-C stops the chooser. Opened project servers and native databases may keep
running and are reused on the next visit. This command is not an all-services
shutdown. Launch uses the installed dependencies and built browser app. This distribution
requires internet for installation; it is not an offline desktop installer.

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
run `/path/to/Rieke-OS/.rieke-runtime/venv/bin/python /path/to/Rieke-OS/rieke.py doctor`; rerun `./install.sh` to repair the
managed runtime. If the chooser port is occupied, choose another with `--port`.

## Workspace and author selection in the app

The launcher displays the full **Workspace root**. Choose **Choose folder** and
enter an absolute path, then **Use this workspace**. A new root receives the
workspace marker and launch script. A valid existing root is reused and its
immediate project folders are discovered without replacing their manifests or
files. Select the parent workspace, not the folder containing an individual
`project.json`. New project folders remain separate children of that root.

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
