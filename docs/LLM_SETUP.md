# Install Rieke OS with an AI assistant

Rieke OS runs without an LLM or API key. These instructions are for an optional
coding assistant helping you download, install, and launch the app on your own
computer. A chat-only assistant can guide you, but cannot verify local commands
or browser behavior itself.

## Copy this prompt

Replace the two folder placeholders, then give the prompt to your assistant:

```text
Help me download, install, and launch the complete Rieke OS application from
https://github.com/maxwellsdm1867/Rieke-OS/tree/main.

Application folder: <absolute path to a permanent application folder>
Research workspace: <absolute path to a separate project storage folder>

Read the repository's README.md and docs/RIEKE_OS_QUICK_START.md first.
This is the local browser app, with an optional MATLAB/EpicTreeGUI companion.
Do not substitute the older epicTreeGUI repository or a Matplotlib application.

1. Check my OS and architecture. Apple Silicon macOS is the verified platform;
   Intel macOS and x86_64/ARM64 Linux are experimental. Native Windows is not
   supported. Check curl and tar. On macOS, check Apple's Command Line Tools
   and guide me through xcode-select --install if needed. Wait for that separate
   installation to finish before proceeding.

2. Download and extract the entire main-branch ZIP, or clone the repository.
   Reuse an existing correct checkout if present; do not overwrite local work.
   Confirm install.sh, start.sh, rieke.py, packaging/, python/, and workspace-app/
   are together in the application folder. Do not assemble individual files.

3. From that folder run sh install.sh. This requires internet access and several
   GB of free space. It downloads the application-local tools, Python, parser,
   native MySQL, and browser dependencies. Allow it to finish and check its exit
   status. Do not install a system database, require Docker for a new project,
   replace dependency pins, or alter my existing research Python environment.
   Stop on failure, report the actual error, and resolve it before continuing.

4. From the same folder run:
   .rieke-runtime/venv/bin/python rieke.py doctor --json
   Check all required results. This probes dependencies; it does not prove that
   a project opened or a recording imported. If the managed Python is missing,
   setup has not completed; do not substitute an arbitrary Python environment.

5. Run sh start.sh and keep its terminal/session alive. Open
   http://127.0.0.1:8766 and verify the project chooser if browser access is
   available. If the port is busy, use sh start.sh --port 8870 and the matching
   URL. Report browser verification as unverified if you cannot inspect it.

6. Help me choose the separate workspace folder and use Add project to create
   and open an empty project. New projects use native MySQL without Docker.
   Reuse an existing project only if I identify it. Do not relocate databases,
   overwrite manifests, or migrate existing Docker-backed projects. Explain
   how to choose a tag author and use Add data store. Ask which recording I
   want before importing any H5 files; an empty project needs no sample data.

7. Give me the application path, workspace path, local URL, observed results,
   remaining errors, and exact cd plus sh start.sh commands to reopen later.
   Explain that Ctrl-C stops the chooser but opened project servers/databases
   can remain running. Keep recordings and database credentials out of reports.
```

## Download and setup references

- [Whole application ZIP from main](https://github.com/maxwellsdm1867/Rieke-OS/archive/refs/heads/main.zip)
- [Versioned releases](https://github.com/maxwellsdm1867/Rieke-OS/releases/latest)
- [Requirements and installation](../README.md#install-and-launch)
- [First recording, export, and troubleshooting](RIEKE_OS_QUICK_START.md)
- [Runtime and export details](../workspace-app/README.md)
- [MATLAB companion](../EPIC_TREE_GUIDE.md)

The ZIP includes the application source and installer, not installed dependencies,
recordings, or a scientific database. Installation downloads dependencies; it is
not an offline installation. Keep the application and project folders separate
and in their original locations after setup.

## What the assistant should verify

A useful completion report separates installation, doctor results, chooser
visibility, project opening, and recording import. A successful doctor result is
not a substitute for the later checks. Importing or inspecting recordings is
optional and should be marked unverified if no recording was supplied.

For an existing Docker-backed project, preserve its backend and explain that it
still requires Docker. Do not silently replace it with an empty native project.

For analysis, remember that MATLAB and SQLite exports contain source references,
not all raw waveform samples. Preserve original H5 files, UUIDs, checksums,
units, and sample rates. Never invent metadata or rewrite identities to force
an import. Derived analysis should remain separate from frozen exports.
