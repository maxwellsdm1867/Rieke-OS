# Rieke OS — local React app

This is the first working React application, backed by the imported RetinAnalysis
DataJoint catalog. It uses real recordings; the earlier conversation sketch is
separate and contains example data.

For workspace initialization, launching from your research folder, and the file
layout, see the [Rieke Lab OS quick start](../docs/RIEKE_OS_QUICK_START.md).

## Fresh-clone setup

Use the complete development source on `codex/rieke-native-e2e`:

```sh
git clone --branch codex/rieke-native-e2e https://github.com/maxwellsdm1867/epicTreeGUI.git
cd epicTreeGUI
```

The public `master` branch still contains the legacy MATLAB application.
The review branch is source for development, not a stable signed app release.

The current bundled native database runs on **Apple Silicon macOS**. Linux and
Windows do not yet have validated native runtime packages. The separate MATLAB
EpicTreeGUI has its own platform requirements. Source setup needs:

- Git, including access to the public RetinAnalysis GitHub repository.
- Python 3.10+ to run the standard-library bootstrap script, and `uv` on PATH.
  Setup uses uv to obtain the pinned **Python 3.11.13** runtime independently of
  your system Python. Install uv following https://docs.astral.sh/uv/.
- Node **20.19+ on 20.x, or 22.12+** and npm.
- A C++ compiler: Xcode Command Line Tools on macOS. RetinAnalysis's vision-utils package
  compiles Cython/C++ extensions.

New projects require neither Docker nor a separately installed MySQL server.
Setup installs a private, pinned MySQL server/client with the app. A signed macOS
`.app` containing Python and all dependencies is not yet built; these instructions
describe source setup, not a finished desktop installer.

From the repository root:

```sh
python3 rieke.py setup
python3 rieke.py doctor
python3 rieke.py launch
```

Setup obtains the exact public RetinAnalysis revision declared in
[`workspace-source.json`](../python/workspace-source.json), initializes its pinned
recursive submodule, and installs its full runtime plus the workspace dependencies
from [`workspace-runtime.lock`](../python/workspace-runtime.lock). The lock pins
registry package versions and distribution hashes; local source builds use the
pinned source and locked build tools. `npm ci` uses the frontend lockfile. Setup
also builds React and checks that the installed RetinAnalysis package and selected
parser checkout have the same origin. No SQL connection or H5 import occurs.
It also verifies the package hashes in
[`workspace-mysql-runtime.json`](../python/workspace-mysql-runtime.json) and installs
MySQL **8.4.2**, its client and dump tool into `.rieke-runtime/mysql`. Native
packages are linked into that private prefix, with local macOS signatures repaired
after relocation. No system service, global database or user MySQL installation
is created. Release artifacts include these package archives for offline native
database installation; the other source-setup dependencies still need downloads.

All dependencies and a small generated compatibility configuration live in the
ignored **`.rieke-runtime/`** folder. The compatibility paths are empty upstream
configuration directories, **not a shared recording database**. Project paths are
supplied explicitly by the app. Setup never copies your personal config, H5 files,
credentials, or another project's catalog. A failed installation does not publish
an installed-runtime receipt; correct the reported cause and rerun setup. Existing
checkout modifications are rejected, not reset. Do not edit the managed parser
checkout or put project data inside `.rieke-runtime/`.

The source pin is public commit `5dc9018ff754e1a01f60d929ceaf4e7f40815e70`.
The previously used local audit commit `cea6a9628fc8a5b3338d6ea5960f7c2587bb8a41`
is not published upstream; its parser, schema, population adapter, lazy database
adapter, package initializer, dependency specification and submodule revision
match the public parent. It is accepted only as an explicit local override.

The first install downloads a substantial scientific dependency set, including
PyTorch, because upstream RetinAnalysis imports it eagerly. Internet access and
several GB of free disk are needed. Package hashes and source revisions are
pinned; compiled binaries remain platform/toolchain dependent. The fresh setup
has been exercised on Apple Silicon macOS. Linux's Python source path is not a
promise of a supported bundled database; that platform remains unvalidated. MATLAB is
optional for this app and needed only to run the exported EpicTree GUI.

For an explicit existing clean checkout at an accepted revision:

```sh
python3 rieke.py setup --retinanalysis /absolute/path/to/retinanalysis
```

This still installs into **this clone's new venv**, preserving existing Python
environments and any existing RetinAnalysis configuration. The submodule must
already be initialized for an explicit checkout. Advanced environment overrides
remain `RECORDING_PYTHON` and `RETINANALYSIS_DIR`; `doctor` checks their origin and
DataJoint compatibility. `python3 rieke.py doctor --json` reports app readiness
separately from bundled native MySQL readiness; it never starts a database or
modifies projects. Managed releases launch the Python service and prebuilt UI
without Node/npm or Git commands; development launch still builds the frontend.

## Start and project storage

After setup, `python3 rieke.py launch` or `npm start` from this directory builds
React and starts the local chooser at http://127.0.0.1:8766. The chooser works
with **zero projects**: confirm the **Workspace root**, choose **New project**, enter a name and optional empty
folder, then open it. No H5 file is required. An empty overview offers Add data
store later. The far-left project icons switch projects; **+** creates another.
The chooser remembers the last opened project without bypassing selection.

Projects default to `~/Documents/RecordingWorkspace`, independently of the code.
Use **Choose folder** in the launcher to enter an absolute workspace path. It
initializes an unused root or discovers projects in a valid existing root,
preserving existing files. This choice is remembered for subsequent launches.
You can also choose a root during setup with `--managed-root /absolute/project/root`,
or override it at launch with `RECORDING_WORKSPACE_ROOT`. Legacy
`RECORDING_PROJECT_DIR` selects its parent when no root is configured.
Creating a project writes a unique identity, catalog reference and managed
folders for database storage, raw uploads, protocols, imports, snapshots,
exports, logs, derived caches and backups. Nonempty folders are never replaced.

Opening a project asks you to choose or create a **Tag author**. Browsing works
without choosing, but adding or importing tags requires an explicit profile.
The browser remembers that choice per project; author identities, tags and audit
records are stored in the project database. Use the profile icon at the bottom
of the project rail to change authors.

Opening a new project prepares an isolated native DataJoint/MySQL database with
private random credentials, a loopback-only port and persistent files under
`<project>/database/mysql`. The executable belongs to the app; the scientific
database and managed files belong to the project. Native startup validates
process ownership and does not use a database found on PATH.
DataJoint tables are provisioned by the existing schema
and workspace adapters, including [saved query methods](../docs/SEARCH_PRESETS.md).
No original H5, memberships, annotations or SQL rows are copied from another
project. Large first-time index rebuilds have a bounded five-minute app startup
allowance, separate from database startup. Failures retain files and diagnostics.

**Legacy Docker projects:** existing Docker-backed projects retain their explicit
configuration and ownership checks. They still need their original compatible
Docker environment until migrated. The historical `datajoint/mysql:8.0` service
image is not digest-locked. Opening a legacy project does not automatically
convert or overwrite it; use an explicit verified transfer/migration to native
storage. This legacy compatibility does not make Docker a new-project dependency.

Keep the terminal running. Ctrl-C stops the chooser; already opened project
servers/databases can remain available and are reused. Every project runs in a
separate process/loopback port because DataJoint connection state is global.
For a native project, **Project folder → Close project** drains active requests
and shuts down its database cleanly. Wait for confirmation before copying or
moving its folder; closing a browser tab or stopping only the chooser is insufficient.

For frontend development, `npm run dev` proxies `/api` to port8766. For direct
project API development, launch `python/workspace_api.py` using the installed
runtime with explicit `--project-dir`, `--retinanalysis`, and `--port`. Direct
`recording_workspace.py` imports use the project's declared connection provider.
Native projects resolve their private runtime and credentials from the project;
legacy Docker projects retain their catalog container or explicit `--container`.
There is no lab-specific fallback database.

## What travels with the repository

Git packages the app, schema/adapter definitions, source/dependency pins and
initialization code. It does **not** package research projects, database credentials,
installed environments, SQL contents or H5 recordings. Saved query JSON can be
shared as a method, but references a project's fields/protocol identities;
it is not a portable copy of the project's data.

For a **native project using the same bundled MySQL runtime**, close the project
cleanly in the app, then copy or move its entire folder. The receiving user opens
the folder with **Open project** in their own application. The app verifies project
and recording identities and updates current project-contained paths, including
import metadata and database source locators. Scientific UUIDs remain stable;
historical audit payloads and immutable exports retain their original evidence.
Relocation was exercised with a real 1,915-epoch project, including opening the
original and its copy independently. Copies do not synchronize later changes.

Recordings imported by path may be outside the project. A plain folder copy does
not include them; those linked paths must remain accessible and match their
recorded checksums. **Prepare to share** optionally creates a separate logical
transfer package, with an option to include linked recordings, and verifies its
database restore. This is useful for a recipient without access to your drives.
Live database directories must never be copied as a transfer or backup. The
plain-folder contract requires a clean close and the same supported runtime;
it is not a cross-version MySQL migration mechanism.

**Legacy Docker migration** remains explicit. Keep the original container,
credentials and owned storage intact until a logical transfer to a fresh native
project has been verified. A Docker data directory copied to another machine is
not automatically adopted as a native project. Derived caches and process records
are local runtime state, not scientific authority. See
[workspace sharing and updates](../docs/WORKSPACE_SHARING_AND_UPDATES.md) for the
current user workflow and its limits.

The older `python/workspace-requirements.txt` is an add-on for an already complete
RetinAnalysis environment; it is **not** the fresh-clone installation entry point.
Use `workspace-runtime.lock` through `rieke.py setup` for the full backend.

## Working slice

- Project overview with real cell/protocol counts, metadata, source filenames
  and database activity.
- Saved acquisition-protocol queries, compact cells grouped by type, original
  source-group filters, and refresh comparisons. Group labels are not inferred
  drug phases.
- Paged epoch inspection, expandable metadata trees with typed ordered splits,
  device selection and full-rate raw response windows. Metadata scrolls in its
  own resizable pane beside the trace. Hiding navigation does not change scientific selection.
- Protocol-scoped tags, inclusion and optional epoch review markers. Current state
  and before/after audit records commit together in DataJoint.
- H5 path import or local browser upload with a background parser job. Path
  import keeps the original file in place; browser upload stores a local copy in
  the project's `raw-uploads/` directory. The existing importer performs parsing,
  validation, source registration and duplicate detection.
- JSON reference exports with saved query, filters, tree settings, review policy,
  exact epoch membership, metadata and source pointers. Export records and
  completion events are persisted together; checksums are checked on download.
  Reuse restores the recipe against the current catalog without changing the
  earlier artifact. A changed query definition is rejected instead of silently
  using a different predicate.

Exports support a queryable Wheeler SQLite snapshot and an EpicTree MATLAB
bundle, with reference JSON retained under Advanced. These exports use lazy H5
pointers, so original recordings must remain accessible. Nested All/Any/None
predicates, project creation and switching, direct matching-epoch inspection,
and one-off saved-selection exports are implemented. User-created protocol
workspaces, figure analysis and desktop packaging remain future work. The recording-workspace SQLite schema does not fabricate or replace fitted
SRM/VMN analysis results.

## Reuse and boundaries

`python/workspace_api.py` is the loopback HTTP adapter. `workspace_service.py`
uses the existing `recording_workspace.py` evaluator, RetinAnalysis schema,
validated parser output and source H5 pointers. `workspace_recipes.py` supplies
query/export snapshots and EpicTree's ordered-field grouping model.
`workspace_curation.py` adds only bookkeeping tables in `recording_workspace`;
it does not edit acquisition rows or raw recordings.

The React inspection structure adapts the existing web app's ResultsViewer,
ResultsTree and Information interaction model: focus is separate from bulk
targets, inclusion and review; device selection drives visualization; metadata
is available with the trace. Its hardcoded API URLs, global server query state
and older DataJoint adapter were not copied into the new server. This application
keeps the same scientific parser/schema foundation while replacing the shell
and orchestration.

## Speed and correctness

The initial service validation verifies source checksums, metadata and database
membership before exposing the workspace. Warm requests use a metadata read
model; traces are read only on selection in windows of at most 100,000 samples.
No downsampling or smoothing is performed. Epoch pages are bounded, tree branches
mount on expansion, leaf lists page at 60, and superseded frontend requests are
aborted. Sequential inspection crosses metadata-page boundaries automatically. Export and approval revalidate the source before publication.

Measured locally on the 2026-09-24 recording: initial validation about 4.5 s,
warm HTTP overview about 73 ms, protocol about 14 ms and epoch page about 11 ms.
A 20,000-sample backend trace read took about 5–8 ms. These are local observations,
not a guarantee for NAS storage or larger projects, and predate the disk-index
implementation. The current service uses a sealed, disposable SQLite metadata
index, lazy detail decoding, and server-paged trees. Unchanged generations reopen
from disk; changed generations still require a complete blocking index rebuild.
Explorer responses and navigation snapshots retain compact counts/revision IDs.
See [SCALABILITY.md](../docs/dev/SCALABILITY.md) for current measurements and limits.

Every write requires current revision expectations. Unknown filters fail closed;
changed source bytes, source UUIDs, sample rates, units and invalid trace values
raise visible errors. Imported data is included by default with no review marker. Review is optional. Curation remains scoped to
the protocol and source/metadata fingerprint. Protocol refresh creates a new
baseline if the fingerprint format changes, avoiding false data-change claims.

Run the relevant tests from the repository root:

```sh
PYTHONPATH=python .rieke-runtime/venv/bin/python \
  -m unittest discover -s python/tests -p 'test_*workspace*.py' -v
```

The backend tests include HTTP scope/review failures, frozen exports, stale revisions,
audit rollback, parser safeguards and exact trace reads. A separate real MySQL
probe verified curation, dataset and event inserts/reads inside a deliberately
rolled-back transaction; no fixture records or approvals were retained.


Scientific UX refinement: a separate agent reviewed the interface and verified
screenshot. Block folders now display recorded block times; epochs have stable
within-block chronological ordinals. Focus-only tag removal cannot inherit bulk
targets, and persistent scope labels distinguish bulk actions from export
membership. Export Control previews eligible/held counts and blocks empty output.
Source context retains raw group/solution values and exposes full ancestry.
Browser metadata preserves integers beyond JavaScript's exact numeric range as
strings, so acquisition ticks are never silently rounded in the inspector.
Run `npm test` here for the two curation-target scope regressions. See
[`SCIENTIFIC_UX_REVIEW.md`](../docs/dev/SCIENTIFIC_UX_REVIEW.md) for findings.


## Managed project files and action history

The active MySQL files now live under
`~/Documents/RecordingWorkspace/RetinaSRM/database/mysql`, separate from the
application source. `storage.json` records the directory layout; `catalog.json`
records database references rather than holding the scientific records itself.
Use **Project files** to inspect protocol definitions, parsed metadata,
query snapshots, exports, logs, uploaded recordings and external H5 references.
The inventory is paged and does not read waveform data. MySQL's live files are
not exposed through the file browser.

Historical Docker storage migration: this earlier move was checked against all
156 cold files and every row of 23 SQL
tables. `database/runtime.json` and `logs/storage/` record the validation and
rollback container. The old stopped container and original cold directory were
retained for rollback. These records describe the legacy Docker migration, not a
requirement for new native projects. `backups/app-state/` contains automatic daily app-state snapshots; full database backups
remain explicit operations. Parser jobs live in `logs/imports`, app jobs and the
rotating server log in `logs/app-jobs`, and incidents in `logs/errors`. Historical
`jobs/` references remain valid through a compatibility symlink.

**Activity & logs** reads the project-scoped SQL `Event` table with 50-row pages,
action filters, search within the displayed page, and lazy event details. New
import, curation, query-refresh and export events record operation identity,
application/runtime/contract versions and source-code hashes. Import events
also record the parser hashes from their manifest. Curation has before/after
values and query context; export events link to the immutable recipe and
artifact checksums. Legacy events remain explicitly marked: current versions
are never retroactively attributed to old work. Actor attribution is the local
server OS user, not a multi-user authentication system. Code hashes describe
source files on disk at event time; restart the app after changing Python code.

Repeated successful export or refresh events in the loaded page can suggest
opening the same protocol or saved export recipe for review. Suggestions never
apply tags, approve data or publish exports automatically. Browsing raw traces
is a read and does not produce a data-edit audit event. Source cell metadata is
still read-only; no cell-edit function is presented as implemented.

The inspector puts the raw trace ahead of curation and metadata, and exposes
import/export navigation, bulk tag addition/removal and selection-mask files.
The mask is `recording-selection-mask` version 1 JSON containing the protocol,
source revisions and an inclusion Boolean for every epoch in the full query.
Import requires exact current membership and source hashes, plus a current
query revision. All inclusion changes and the audit event commit together;
tags and approvals are preserved. A mask from before adding new recordings
must be reconciled explicitly, not silently applied as a partial mask. This is
not the legacy UGM/MAT format. See the function parity inventory for remaining
integration work.


## Visual tree builder

**Split tree** uses an expandable hierarchy with connected, indented branches.
Each branch shows its split field, value and epoch count; expand through the
configured levels to reach epoch leaves. Selecting an epoch keeps the tree next
to its trace. **Columns** remains available as a second presentation for tree
design. Each presentation remembers its position. Branches are fetched on demand
in pages of 60, with a bounded 24-page cache, rather than loading the whole tree.


In **Inspect & select → Split tree**, Arrange tree replaces the typed split list.
Choose a quick layout or search for a recorded field. Autocomplete searches names,
source paths and sample values, with Recording, Parameters and Conditions tabs.
Move levels up/down or remove them; the tree previews automatically after 250 ms.
Each step reports the number of resulting groups. Flat list removes grouping.

Fields include recording date, stable cell/block/group identities, cell type,
recorded group label, block start time, epoch parameters and nested cell/group/block
or epoch properties. Available fields come from validated metadata. Large vectors
are omitted from the field picker; waveforms are never read to build a tree.
Missing fields remain visible and are distinct from explicitly recorded null,
empty arrays, string values and numeric values. Recorded labels such as NBQX5um
are never converted into inferred treatment stages.

Presets adapt to actual fields: date → cell → block; date → cutoff → cell;
cell → cutoff → current SD → block; spot size or history-noise layouts when
those fields are present. Up to eight levels are allowed. Field/value summaries
are cached per verified metadata generation and retained on unchanged refresh.
Visible branches and leaf
lists page in batches of 60. Previewing or rearranging never changes the query,
inclusion, tags or dataset membership. Exports retain the ordered field IDs and
a versioned tree-view description with field labels and source paths.

## Optional review and export connections

The default export contains included epochs with no review requirement. A
reviewed-only filter remains available when deliberately selected, and reuse of
an existing export retains that export's saved policy. Review markers are tucked
under optional inspection controls. Project/protocol/cell overviews emphasize
inclusion and saved-export membership rather than review obligations.

Each focused epoch shows its main catalog, protocol query and completed exports
that actually contain it. Membership comes from frozen output membership, never
from a broader generating-query snapshot. Downloads reference the immutable
artifact. A saved output whose metadata fingerprint differs from the current
epoch is labeled as a different metadata revision. Tags remain protocol-scoped,
independent of review and inclusion, with before/after SQL audit records.


## Metadata discovery and tree design

**Explore recordings** starts from the main project catalog, including recordings
not assigned to any saved protocol workspace. No protocol name is required.
An acquisition protocol is a source metadata field; a protocol workspace is a
saved query. A tree simply groups the current scope by ordered metadata fields.

The field picker offers suggestions based on actual recorded variation, with
example values and missing-value counts. Constants, near-unique fields and random
seed identities remain searchable but are not promoted. Duplicate value columns
are suppressed in suggestions. “Protocol settings” is the user-facing category
for epoch parameters. Suggestions never infer drugs, treatments or scientific
intent, and never change the query or tags automatically.

Tree design uses its own interactive hierarchy preview. Click a group to see its
next split, distribution, unique cells and recorded duration. Global scope counts
stay visible. Raw traces do not load merely because a group is opened. An explicit
inspection action opens an epoch separately; the chosen epoch can then be handed
to the matching tagging/export workspace without losing its identity. When several
workspaces match, the user chooses one. No match is silently invented.

The app's display title is **Rieke OS**. Scientific source names, stable project
identities, managed storage paths and historical audit records keep their existing
values.

### Protocol sidebar preferences

Use the sliders button beside **Protocols** to pin shortcuts, move them up/down
within a section, or tuck them into **Typing & backtracking**. Single Spot,
Expanding Spots and Split Field Centering start in that collapsed section.
Preferences are saved per project UUID in browser local storage on this device;
they do not alter query definitions, database records or the full project overview.
New protocols appear automatically. Browser storage failures retain session-only
preferences with an explicit notice.

### Predicate-first exploration and revision history

**Search predicate** starts with a metadata predicate, before showing a tree.
Conditions support nested ALL/ANY groups and explicit NOT, typed equality and
membership, numeric comparisons, text/array containment, and separate missing
and recorded-null checks. **Search predicate** on a protocol page seeds its
saved acquisition-protocol condition and active cell/group filters.

Previewing and **View matching epochs** are read-only. The matching-results view
pages the exact predicate selection chronologically, with cell/date/acquisition
protocol context, selected-epoch metadata and lazy raw traces. Page and anchor
requests carry the preview revision; a changed source or queried tag annotation
requires refreshing the preview before inspection can continue.

**Save selection** (or **Save & continue** in the filter editor) saves a project-scoped SQL
`ExplorerRevision` and master-log event in one transaction, with the complete
predicate, exact epoch membership and metadata fingerprints, source references,
tree field order, code provenance and a content checksum. The app exposes no
update/delete operation for these records; database administrators still control
the underlying SQL storage. Later tree arrangements are saved as new revisions.
History restores an old recipe as a draft for explicit re-evaluation against the
current catalog, preserving the old record.

Predicate fields combine validated source metadata with explicitly named
**Tags · protocol name** annotation fields. This does not claim parity with
Samarjit's shared `Tags` table or merge annotations across workspaces.

From matching results, choose **Edit tree**, **Use in protocol**, or **Export
selection**. Saving a selection does not itself create a protocol or pin.
One-off export publishes the saved exact membership to Wheeler SQLite, an
EpicTree MATLAB bundle, or reference JSON. It includes all matching epochs with
no implicit protocol inclusion/review mask or merged tags. Explicit tag predicates
retain their protocol identity and selection-time evidence in the recipe. A stale
source, membership, fingerprint or queried annotation revision requires a new
saved selection before publication.

Use the target selector to compare a saved candidate with a protocol and apply
it explicitly. A SQL `ProtocolBinding` switches that protocol to the immutable
candidate revision; its overview, tree, masks, tagging scope and exports then use
the same epoch membership. The original protocol JSON remains a starter query;
the SQL binding and immutable revision are authoritative for an applied working
set. Exports preserve the effective predicate and binding version separately.

For an applied protocol, **Refresh & compare** reruns its predicate on the main
catalog and saves a proposed revision, without switching the working dataset.
**Review update** shows new/removed/changed epochs and cell/protocol/duration
summaries. Applying uses an optimistic version check, a database lock and one
transaction for the binding and audit event. Existing annotations remain attached
to epoch UUIDs; previous revisions and export artifacts stay intact. Unavailable
bound source epochs fail closed and require source recovery; source deletion is
not an app workflow.

The main actions are **Search predicate** (filter, compare and apply to a protocol)
and **Add data store** (import a recorded H5 file into the main project database).
They are grouped in the sidebar and available directly on the project overview.


## Infographic overview and scientific interaction polish

The project overview summarizes recording dates, unique source cells, recorded
epochs and protocol workspaces. Date bars and the cell-type distribution open a
filtered source-cell list. Coverage bars show each workspace against the source
epoch count; workspaces can overlap. Missing dates remain explicit, and any
missing duration makes a group's duration unknown rather than a partial total.
Linked figures are a clearly marked planned area, not yet an artifact-linking UI.

Trace inspection uses bounded full-rate windows of up to 20,000 samples. Drag to
zoom or switch to Pan; requests occur on release. Exact sample cursors, keyboard
navigation, readable physical axes and missing-value gaps preserve source meaning.
There is no waveform resampling. Selection-mask controls sit behind a disclosure.

Tree levels and protocol shortcuts support pointer dragging and keyboard movement.
Dragging changes presentation order only; sidebar preferences are device-local.
The field picker supports keyboard search in a viewport-bounded popup. See
`../docs/dev/UI_POLISH_AUDIT.md` for adversarial findings and browser verification.

## Data store management

**Data stores** is a primary sidebar destination beside Search predicate and
Activity & logs. It manages imported H5 registrations; Project files remains
the browser for the managed directory, database inventory and diagnostic files.
The Add data store page returns to this registry after an import.

Freezing locks registration controls, including list placement and query
participation. Protocol-scoped tags remain independent. **Archive/Restore** changes
list placement only; **Exclude/Include in queries** independently controls whether
fresh queries can select the store. No ingestion records or raw H5 files are deleted.

Existing protocol datasets retain membership until **Propagate changes → Apply
update** publishes a new revision. Earlier exports remain immutable. A working
dataset containing query-excluded sources cannot produce a new export until its
source changes are reconciled. Archived stores can still participate in queries;
query-excluded stores can remain visible in the current list.
Lifecycle operations retain actor, time, reason, version and before/after state in
the SQL action history. File modification, parser validation and source import
are distinct timestamps; an unavailable timestamp must remain unknown.


### Propagating source changes

Each H5 offers **Propagate changes**. The proposal reruns each related protocol's
complete saved query across query-included sources and shows added/removed/changed cells
and epochs. This can include other newly available source data. Apply updates one
protocol at a time; each candidate, dataset binding and audit evidence commits in
one transaction. A stale source scope, dataset version, metadata or curation
snapshot requires a fresh preview. Include/exclude and query publication share a
project eligibility lock. Source parsing stays asynchronous; imported sources
become visible to the API when the validated read model refreshes.

The source eligibility snapshot is retained with saved candidates and new export
recipes. Historical source queries without this snapshot must be reevaluated when
query exclusions exist. Unknown/missing metadata remains distinct from measured zero.
Legacy starter tree paths receive an explicit date/cell/block layout adaptation,
recorded with the new revision. The original starter definition is unchanged.

Before parsing a new import, existing starter protocol membership is frozen as
a baseline where needed. New matches are offered as persisted proposals; **Add**
applies one explicitly. Existing bound working datasets likewise retain membership
until a revision is applied. Query-excluded sources are skipped for fresh
exploration; earlier datasets and exports remain intact.


### Duplicate-aware import

Import jobs first stream a SHA-256 content check, then fetch authoritative Source
registrations. Identical contents are recognized across filenames and paths and
skip parsing/insertion; the existing registration's query exclusion, frozen state,
visibility and original raw-data pointer are preserved. A filename collision with
different bytes is a warning, not a duplicate match. Duplicate browser uploads
remove only the new staging copy; external/original files are never removed.

New-source insertion additionally rejects Cell, EpochGroup, EpochBlock and Epoch
UUID collisions before population inside the existing import lock/transaction.
Different bytes with an existing experiment identity still require reconciliation.
This does not deduplicate repeated scientific signals/trials or promise collision
checks for animal/preparation/stream identities. A duplicate whose original H5 is
missing remains registered and is not automatically relinked.

The visibility/eligibility schema migration preserves legacy archive exclusions
as explicit query exclusions, without rewriting scientific records or old logs.
It records migration evidence for legacy state rows and resumes safely after an
interruption. New registrations start query-included and visible.

### Rieke OS projects and MATLAB handoff

Rieke OS is the application. The current project is displayed as **Spike Response
Model** through `project.json.display_name`; its internal name, UUID, directory and
SQL catalog identity remain stable. Display-name edits append a project audit
event. The project rail and selector discover validated recording projects in
immediate sibling directories only. A different project opens in a separate
loopback Python process so DataJoint's process-global connection/schema state is
never swapped under an active tab. Server records live in
`logs/workspace-server.json`; verified project UUID health checks permit reuse.
A missing or unreachable project database produces a startup error and local log.

Protocol **Export control** supports:

- **Wheeler SQLite**: normalized, queryable cells, epochs, protocol settings,
  frozen tags and source/stream pointers, with recipe/query provenance, schema
  documentation and runnable SQL examples inside the database.
- **Reference JSON** (Advanced): exact predicate, membership, source revisions, metadata,
  curation and saved grouping for downstream database/analysis consumers.
- **MATLAB bundle**: a ZIP containing `recordings.mat`, `selection.ugm`,
  `launch_epictree.m`, both exact recipes, the reference JSON and a compatibility
  report. Run the launcher with EpicTreeGUI available. The MAT structure follows
  `loadEpicTreeData`/`buildTreeFromEpicData`; original H5 files supply traces lazily.
  Stable acquisition UUIDs survive export; numeric IDs are display ordinals.
  The launcher loads only the bundled mask, not an unrelated latest UGM.

Saved grouping fields map to explicit `workspaceGrouping.gNNN` paths, with a
field/label mapping in MAT metadata and the compatibility report. Typed values
remain distinguishable. Exact source metadata JSON preserves fields that MATLAB
cannot represent as ordinary struct names. Unsupported MEA data and flattening
collisions fail without registering a successful export. Animal/preparation
ancestors absent from the current service read model are not reconstructed.

In **Inspect & select → Selection masks → Import MATLAB UGM**, choose a returned
UUID-based `.ugm` version 1.1 and explicitly apply it. The server checks the saved
completed MATLAB artifact, exact export UUID set, recipe/source fingerprints and
current query/curation revisions. MATLAB drops custom provenance when re-saving;
when multiple exports have the same UUID set, choose the corresponding completed
export. The import changes only those epochs' inclusion decisions. Tags, review
state and epochs outside the exported subset remain unchanged. The SQL audit
records mask content hash, dataset/recipe/artifact identities and before/after
curation. Positional, duplicate, partial and stale masks are rejected.

The MATLAB reader now prefers each response's H5 pointer over a project fallback,
which prevents mixed-recording trees from reading another source at the same H5
path. `loadH5ResponseData(response, new_path)` still supports deliberate relocation.
Workspace response pointers include their source SHA-256. The MATLAB workspace
reader verifies the source before lazy access, caches verification only while the
file identity/signature remains unchanged, and rejects detected changes. This
workspace guard is separate from the legacy reader's behavior for older bundles.
Keep the original H5 files unchanged. Install `python/workspace-requirements.txt` in the
RetinAnalysis environment for the MATLAB v7.3 mask writer (`hdf5storage`).

### Predicate filtering

The filter editor uses compact field → comparison → value rows and nested
All/Any/None groups. None means NOT(ANY); a restored NOT(ALL) group remains
explicitly “Not all,” preserving the saved query's meaning. Recorded values and
field types guide inputs; advanced type/negation controls retain mixed-type
metadata support. Recording dates use exact ISO calendar dates. Raw acquisition
timestamps remain source strings rather than being silently converted to local
time or compared lexicographically.

Field discovery now includes recorded experiment descriptions/properties and
cell/group/block/epoch labels, notes, comments, keywords and start/end times when
present, alongside epoch and block protocol settings. It reuses verified cached
metadata, without reading waveforms or changing existing metadata fingerprints.
Missing fields are not invented; recorded null and empty arrays stay distinct.
User-added tags remain protocol-scoped but are now available as typed predicate
fields: `curation/<protocol_uuid>/tags`, displayed as **Tags · protocol name**.
Use array containment for an individual tag. Untagged epochs have an empty array;
imported keyword fields remain separate. The same tag text in another workspace
never silently participates. Inclusion and review flags remain protocol inspection
decisions, not global source-predicate fields.

Saved tag-based selections retain queried protocol identities, annotation revisions
and tag evidence. Changing a queried annotation makes a candidate stale even if
its matching UUID set stays the same. Unrelated protocol annotations do not alter
that scope. Canonical recipes/exports keep the complete evidence; ordinary UI
responses carry revisions and counts. Applying the selection to a protocol is
separate from previewing, saving or making a one-off export.

### Standalone SQLite consumer

A Wheeler export uses `recording-workspace-sqlite` schema version 2 (the reader also supports version 1). Inspect
`documentation`, `example_queries` and `epoch_overview` with standard SQLite. It
has no dependency on the running Rieke OS server or DataJoint connection. For
example:

```sql
SELECT cell_label, recording_date, count(*) AS epochs
FROM epoch_overview GROUP BY cell_uuid ORDER BY recording_date, cell_label;
SELECT * FROM example_queries;
```

The checked local consumer also reads bounded raw traces:

```sh
python python/query_workspace_export.py /path/to/recordings.sqlite
python python/query_workspace_export.py /path/to/recordings.sqlite \
  --epoch EPOCH_UUID --stream STREAM_UUID --start 0 --count 20
```

It verifies the source SHA-256, acquisition/stream UUIDs, units, rate, sample count
and frozen metadata before returning samples, using the same trace reader as the
UI. `--source-file /new/path.h5` supports relocation only when bytes match the
recorded hash; `--expected-sha256 HASH` checks the SQLite artifact against its
saved revision. Use the existing RetinAnalysis Python environment for h5py/numpy.
The database contains source references, not sampled waveform rows or fitted
models; old Compact/SRM/VMN scripts need an explicit mapping to this schema.
Exported source tables reject accidental mutation. Derived analysis can live in
separate tables/databases, preserving the frozen query and membership.


For batch analysis, keep a reader session open. The source SHA is verified once
per unchanged source/path; a changed H5 or SQLite file invalidates the session.
Full-rate sample windows and a 32-record metadata cache keep memory bounded.

```python
from query_workspace_export import ExportReader
with ExportReader("recordings.sqlite") as reader:
    first = reader.read_trace(epoch_uuid, stream_uuid, start=0, count=20000)
    next_window = reader.read_trace(epoch_uuid, stream_uuid, start=20000, count=20000)
```

Schema 2 deduplicates exact typed parameter sets, keeps `epoch_parameters` as a
query-compatible view, and stores a lossless compressed audit copy in
`frozen_records`. Use `workspace_sqlite.load_frozen_record(connection, epoch_uuid)`
to read that copy across versions; schema 1's `epochs.record_json` column is not
present in version 2. `epochs.metadata_json` and source/stream metadata remain
plain JSON for SQL queries. The export includes full parameter values regardless
of the UI's suggestion-size limits. Cell dates come from cell start timestamps;
individual epoch start times and acquisition blocks remain separate.

These exports are recording snapshots. They do not reinterpret legacy
`conditions_canonical`, cleaned voltage, baseline estimates or SRM fits as raw
acquisition fields. A parameter set is not an inferred scientific condition;
analysis defines its own grouping and should preserve acquisition block identity.
Generated-stimulus metadata is preserved, including generator version and units,
but reconstruction requires an explicitly validated adapter. `read_trace` reads
recorded response streams only. See `docs/dev/SQLITE_HANDOFF_AUDIT.md` for the
comparison with the existing Compact and VMN databases.

### Current-state recovery

`app-state.json` points to a compact SQLite recovery database under
`backups/app-state/`, with limited daily checkpoint history. Verified tag edits
update changed records; frozen pins retain their exact membership. Ordinary
edits do not append a full action trail. See
[storage and recovery](../docs/STORAGE_RECOVERY.md) for backup contents, retention,
older-format compatibility, and the offline restore command.
