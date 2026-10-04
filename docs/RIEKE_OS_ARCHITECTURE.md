# Disco application boundary

For the implemented module map and proposed stable behavioral ports, start at
[ARCHITECTURE.md](../ARCHITECTURE.md). This document owns the application and
distribution boundary.

Disco is an independent application for organizing recordings, browsing
metadata and waveforms, tagging cells and epochs, saving queries and selections,
and exporting reproducible data. Its canonical source and releases are in
[maxwellsdm1867/Rieke-OS](https://github.com/maxwellsdm1867/Rieke-OS).

| Directory | Responsibility |
| --- | --- |
| `desktop/` | Electron windows, private backend ownership, folder dialogs, installation and GitHub updates |
| `workspace-app/` | Browser interface, waveform inspection, searches, curation and export controls |
| `python/` | Recording import, native project database, queries, annotations, recovery, sharing and data export |
| `tools/` | Application assembly, runtime audits, tests and release qualification |
| `docs/` | Disco workflows, architecture and release procedures |

EpicTreeGUI is a separate MATLAB application in
[maxwellsdm1867/epicTreeGUI](https://github.com/maxwellsdm1867/epicTreeGUI).
Its MATLAB GUI, plots, stimulus helpers, launchers, installers, examples and
MATLAB tests are not part of Disco source releases or packaged applications.
The original EpicTreeGUI repository retains that code.

The reviewed `desktop/application-profile.json` explicitly lists the Python
application modules that may enter a desktop package. The build checks local
import closure before copying them. Artifact audits check the same profile and
reject MATLAB GUI resources or legacy interactive modules. The source-release
check rejects excluded paths so a future source archive cannot accidentally
reintroduce the companion application.

MATLAB remains a data-export destination. Python and SciPy produce
`recordings.mat` with acquisition identities, metadata, grouping, frozen
annotations and query provenance. Waveforms remain in the original H5 files;
the MAT data contains the corresponding file/dataset references and source
checksums. Standard MATLAB `load` and `h5read` can consume the export in a user's
analysis script. The export contains no GUI, plotting commands, launcher or
interactive selection mask. Creating it requires no MATLAB installation.

Disco keeps its own web waveform viewer, grouping and selection controls.
Portable JSON masks and authored tag JSON are independent data interchange
formats. Historical exports and their recorded provenance remain readable;
removing an interactive feature does not rewrite recordings, old exports or
scientific decisions.
