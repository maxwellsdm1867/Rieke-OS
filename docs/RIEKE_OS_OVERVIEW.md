# What Rieke OS does

Rieke OS connects recorded electrophysiology data to the datasets a researcher
actually analyzes. Its main workflow is **import → find → inspect → curate →
export**. The browser app combines a recording catalog, metadata search, response
viewer, cell workbench and a record of selection decisions in one local project.
It is designed for Symphony H5 recordings, with particular support for retinal
cell and stimulus-protocol workflows.

A typical session starts with several recordings. You find the cells and trials
relevant to a question, inspect their metadata and responses, group them into a
useful tree, and record which epochs to keep. You can save the query for later,
maintain a named protocol dataset, and export a particular version for analysis.
The export records which epochs were included and which source files they came
from, so you can return to that selection after the project grows.

## The pieces of a project

| Concept | Meaning in the application |
| --- | --- |
| Workspace root | A folder containing separate project folders. Selecting another root changes the project list; it does not move data. |
| Project | An independent recording catalog, local MySQL database, source registrations, saved selections, annotations and export history. |
| Source recording | An original Symphony H5 file referenced by absolute path, or a copy uploaded into the project. Its metadata and acquisition identities are cataloged; response samples are read from H5 when needed. |
| Cell | The recorded cell identity, linked to its groups, acquisition blocks and epochs. The cell workbench gathers that cell's characterization recordings across protocols. |
| Epoch | One acquired trial, including its recorded parameters, properties and response/stimulus stream references. |
| Search preset | A reusable, versioned query: the conditions you want to apply to the current catalog. It can match a different set of epochs when the catalog changes. |
| Protocol working dataset | A saved epoch selection tied to one exact recorded acquisition protocol. A search can create or update this selection after the researcher reviews the change. |
| Export | A frozen handoff of a specific selection, query, metadata and source references. Reusing its settings prepares another export against the current project; the earlier artifact stays unchanged. |

A search can span multiple acquisition protocols. Creating or updating a pinned
protocol dataset requires a compatible selection from one recorded protocol;
the app shows the mismatch rather than relabeling the acquisition. Direct query
exports support a separate handoff without creating a pinned protocol dataset.

## Inspection and curation

The epoch browser separates the trial you are **looking at**, the checkboxes
selected for a **bulk action**, and the persisted **inclusion mask**. Focusing a
cell or checking a box does not silently redefine the full export selection.
The export dialog shows its query scope and eligible epoch count.

Response inspection reads bounded, full-rate windows from the selected H5
stream. Device selection, sample cursors, zooming and ordered metadata splits
help relate a response to its acquisition conditions. The browser cell workbench
organizes expanding-spot, split-field, single-spot, current-step and injected-noise
recordings where those protocols exist. It exposes recorded measurements and
supported response summaries, with explicit unavailable states for missing data.
Block-onset voltage estimates include their method and caveats; they are not an
automatic validated resting-voltage measurement or a cell-quality verdict.

Shared annotations attach to exact cell or epoch UUIDs and a local author
profile. A cell tag is inherited by its linked epochs. Dataset-specific tags and
inclusion decisions belong to the protocol working dataset. Review markers are
optional and affect export eligibility only when the reviewed-only policy is
chosen. Author profiles provide attribution on this computer, not authenticated
multi-user accounts.

## What an export contains

| Format | Use |
| --- | --- |
| SQLite | Query the selected cells, groups, blocks, epochs, parameters, annotations and H5 stream references using standard SQLite tools, including compatible Wheeler tools. |
| MATLAB data (.mat) | Load a standalone MAT data file with standard MATLAB `load`; inspect recorded metadata, frozen annotations/selection and provenance, and use lazy H5 references with `h5read`. No GUI or launcher is included. |
| Reference JSON | Inspect the frozen query, exact epoch membership, metadata and source pointers in a portable structured document. |

New download names use `Protocol_Name_YYYY-MM-DD.ext` by default and can be
customized. Each export has its own identity and checksum internally. These
exports retain references to waveform data: the original H5 recordings must
remain accessible. A SQLite export contains recording-workspace metadata, not
precomputed SRM fits or a replacement for a fitted-analysis database.

Supported UUID-based tag JSON and Recording Selection Mask v1 JSON can be
imported explicitly. Mask imports require the exact protocol membership and
source revisions. Historical MATLAB bundles remain readable as legacy artifacts;
new exports are data-only.

## Standalone Rieke OS application

The application is a React interface hosted by its local Python service and
DataJoint/MySQL catalog. The desktop app bundles its scientific runtime and owns
its service lifetime. Source setup remains an optional developer workflow. Both
provide Rieke OS web plotting and curation without a MATLAB installation.

EpicTreeGUI remains in its separate repository; its MATLAB GUI, plotting helpers,
launchers and UGM interaction are not part of this application. Figure linking
remains planned. Apple Silicon is the current desktop testing target; signed
production, independent clean-machine and other-platform qualification are
tracked separately in the release procedure.

## Where these behaviors live in the code

| Area | Main implementation |
| --- | --- |
| Workspace/project roots and startup | [installation](../python/workspace_installation.py), [project discovery](../python/workspace_projects.py), [native database](../python/workspace_native_database.py) |
| Recording import and validation | [recording workspace](../python/recording_workspace.py), [read service](../python/workspace_service.py) |
| Queries and saved working sets | [predicates](../python/workspace_predicates.py), [search presets](../python/workspace_search_presets.py), [query revisions](../python/workspace_explorer.py), [protocol identity](../python/workspace_protocol_identity.py) |
| Epoch browsing and traces | [Inspector](../workspace-app/src/components/Inspector.jsx), [metadata trees](../python/workspace_tree.py) |
| Cell characterization | [CellQC UI](../workspace-app/src/components/CellQC.jsx), [QC methods](../python/workspace_qc.py) |
| Curation and authored tags | [curation](../python/workspace_curation.py), [annotations](../python/workspace_annotations.py), [tag exchange](../python/workspace_tag_exchange.py) |
| Export provenance and formats | [recipes](../python/workspace_recipes.py), [SQLite](../python/workspace_sqlite.py), [MATLAB](../python/workspace_matlab.py), [query exports](../python/workspace_candidate_exports.py) |

Start with the [quick start](RIEKE_OS_QUICK_START.md) to install the app and work
through a real recording. The [validation ledger](dev/CLIENT_VALIDATION_MATRIX.md)
distinguishes exercised workflows from untested variants and scientific limits.
