# React workspace integration plan

Status: design and reuse plan, not production implementation. Updated 2026-09-27.

Implementation update: the first local React slice now lives in
[`workspace-app`](../../workspace-app/README.md). That README records what is
connected, how to launch it, measured timings and remaining integration work.
The design below remains the broader target, not a claim that every item ships.

## Product decisions captured

- One local app and launch point for routine use by the scientist and Fred.
- React frontend, using the existing Next.js/React web app as the UI implementation baseline.
- Landscape desktop layout is a fixed product requirement. Persistent navigation and coordinated panes remain within the app window; long content scrolls inside its pane instead of extending the entire app into a portrait page.
- Reuse RetinAnalysis's parser, DataJoint 2.2.2 schema/query utilities and analysis logic; reconcile the older web app's API differences.
- Project overview shows cells, user-defined protocol workspaces, review indicators, figures and activity.
- Initial workspaces: variable-mean noise current injection; current injection across frequency cutoffs.
- An acquisition protocol class/name remains source metadata. A user-defined protocol workspace links queries, datasets and figures and can match multiple acquisition variants.
- Drag/drop or select a recording/location; parse and index automatically with visible state; inspect epochs without manual script or MAT-export steps.
- Preserve web-app queries, tree selection, tagging, metadata/device inspection, masks and export choices. Time cropping is not a requested feature.
- Saved presets discover new matching data; unchanged files are not re-parsed merely to refresh a query. Newly imported cells/recordings can wait in a review queue.
- Final datasets may stay in DataJoint. MATLAB, EpicTree and portable packages remain optional handoffs.

## Navigation reference

Slack documents a workspace switcher, navigation rail, sectioned sidebar and content view. Use this arrangement for project switching, protocol workspaces and scientific content. Its Activity view is a useful precedent for a consolidated action history. These are interaction references, not a request to build chat or reproduce Slack branding. [Sidebar reference](https://slack.com/help/articles/212596808-Adjust-your-sidebar-preferences), [Activity reference](https://slack.com/help/articles/46751260742035-Introducing-the-new-Activity-view-in-Slack/).

The project home should have visual protocol cards, distinct-cell/review indicators, cross-protocol coverage, linked-figure previews and an import timeline. Each timeline event answers: which file/source, when, who, how many new/matched/skipped cells or recordings, parse result, and affected presets. No guessed research metrics or quality scores are needed.

Metadata is visible by default, following the supplied existing-inspector screenshot. Project home shows source count, catalog and most recent import near the top, then a full metadata section in the normal scrolling page. In the recording inspector, retain a tree/list at the left, traces and device controls above, and a readable field/value table directly below. Selecting a cell or epoch updates this table; opening a separate dialog is unnecessary. Show scope and origin (project/source/cell/block/epoch), full field names, units and missing values. Avoid truncating long parameter names as the old table does. Large metadata collections can page or virtualize without delaying the initial summary.

The screenshot is an interaction reference, not a request to add time cropping. Preserve tags, inclusion masks and stream controls from the existing tools. Import's primary action is choosing an H5 file; RetinAnalysis parsing, internal JSON generation and population run behind one observable job. See the source-pointer extension in `DATAJOINT_HANDOFF_SCHEMA_DRAFT.md` for identity, relocation, duplicate detection and retry behavior.

### Protocol cell list and expanded details

The scientist revised the overview preference: default to a compact list with cell name/number, acquisition date and cell type. Expand a row to reveal a detailed cell card, counts, condition breakdown and inspection actions. Hide stable cell/epoch UUIDs in an expandable identifiers section. Add a session/recording qualifier when human-readable labels collide. The same label/type/UUID mapping is used in project coverage, expanded details, inspection, review and exports.

Expanded details show primary-protocol coverage (recorded out of the project's designated primary workspaces), distinct epoch count and total recorded duration in the current protocol scope. Expand conditions into cutoff → epoch count → recorded time, or mean/SD dimensions appropriate to VMN. Do not round or substitute an acquisition cutoff value such as 414 Hz with a preferred label. The current sketch uses illustrative cutoff values 25, 100, 200 and 414 Hz; it is not a claim about actual files.

Recorded duration means the sum of per-epoch recording durations, excluding inter-epoch gaps and counting each epoch once regardless of stream count. Derive it from an explicitly selected recording timebase/sample count; missing timebases are unknown, not zero. Keep stimulation time (from protocol timing) and session elapsed time separately named if shown. Counts/times must state whether they refer to all recorded, included or approved epochs. A cell-type tag change does not change identifiers or waveform cache keys.

### Cell-type groups, treatment filters and refreshed-query differences

The protocol overview groups the compact cell list by cell type. Clicking a type or choosing a phase/drug filter scopes the matching epochs and counts. Treatment belongs to epochs/blocks, not permanently to a cell: one cell may contribute control, drug and wash recordings. Show mixed treatment coverage on its row and retain the phase/drug distinction in the tree and export predicate. Keep unknown values visible; never infer a wash from absent drug metadata.

Each protocol exposes **Open query & inspection tree**, **Add recording**, **Refresh & compare**, and **Export control** directly. These actions wrap the existing web query/inspection backbone; the overview is not a substitute for that workspace. Imports register project sources once; their resulting epochs can match several protocol queries without copying the source into separate protocol databases.

After import, re-evaluate the same saved query and compare its stable-identity membership and relevant metadata revisions with its previous evaluation. Show added, changed and no-longer-matching epochs, affected cells and reasons. Added epochs from an existing cell are distinct from newly discovered cells. The user can inspect only new/changed matches, keep the previous dataset revision, or prepare a new revision in Export Control. A changed query definition is a separate comparison reason from newly imported data. Removed matches are not deleted sources.

The sketch demonstrates a named example comparison (3 cells/18 epochs → 5 cells/30 epochs, +12 added epochs from two cells). Changed/removed categories are interactive empty states in that fixture. It is not connected to actual import/query execution. Treatment and type fixtures are illustrative; the real VMN discrepancy is documented below and must drive the production adapter.

### Verified VMN drug-metadata discrepancy

Read-only queries of `kosmos_export/vmn_diff_mean.db` on 2026-09-27 found `conditions.epoch_group = Control` for all 168 conditions, but `epochs.external_solution_additions = [;NBQX (10uM);]` on 1,784 epochs across seven stored cell IDs. The remaining 1,520 epochs across six stored cell IDs have `[]`. The base cell-type categories are ON/OFF parasol and ON/OFF midget (stored with an `RGC\\` prefix). No inference of confirmed control or wash follows from `[]`.

This matches [VMN_DB_BRIEFER.md](/Users/maxwellsdm/Documents/GitHub/matlabPyrTools/retinaSRM/VMN_DB_BRIEFER.md:59). Prefer source-level pharmacology metadata to the inherited group label; retain both values and surface their disagreement. Drug name, concentration/unit, phase and annotation provenance need distinct fields/projections. Keep original strings and explicit missingness alongside normalized query values. Concentration normalization and actual trial-phase annotation require validation before scientific filtering.

## Reuse map

The existing web app is the **core interaction backbone**, not merely a source of visual inspiration. Keep QueryContainer's filtering/query semantics connected to ResultsViewer's ResultsTree, Information/device visualization, metadata, tag actions and export controls. The new project/protocol overview surrounds that workspace. Opening a protocol provides its summary and cell list; entering inspection lets the scientist filter and visually choose epochs/recordings for export. The scientist clarified that “apps” meant epochs/recordings, not an analysis-app launcher.

Export Control shows the active query/scope, inclusion decisions, review policy, resulting cell/epoch/duration counts and target dataset/database or file profile. On successful save/export, add the published revision/output to both protocol and project overviews and write the operation history. Failed or cancelled jobs belong in activity but must not appear as successfully exported datasets. The sketch demonstrates focused-cell versus protocol-wide VMN scope and frozen simulated membership. The full production query builder remains the existing reusable implementation, not the sketch's simplified controls.

| Existing component / logic | Role in the React app | Changes around it |
|---|---|---|
| `page.js`, `SetUpStepper` | Existing application shell and setup logic | Replace recurring setup wizard with persistent project navigation. Move database/user/path setup to onboarding/settings. |
| `AddData`, `AddDataSpinner` | Source selection and ingestion progress starting point | One recording/file/folder operation; invoke RetinAnalysis parsing before population; show durable per-source progress/errors in the app. |
| `QueryContainer`, `LogicBlock`, `CondBlock` | Nested conditions, saved query objects and field controls | Keep query-building behavior; add project/protocol preset scope, version/history, imported-query compatibility and new-match counts. |
| `ResultsTree`, `CustomTreeItem` | Hierarchical results, checkboxes, tags and focused item | Keep familiar actions; add lazy/paged branches and optional saved splits. Avoid loading the entire tree just to show a project. |
| `Information` | Device selection and visualization | Connect to bounded trace reads and persistent identity; add responsive plotting and request cancellation. |
| `ResultsViewer` | Metadata view, tags, downloads, MAT export and UGM import | Separate reusable panels/actions from page state; place actions with their actual dataset/project scope. |
| `helpers/query.py` | Query semantics, tag operations, export adapters | Adapt to the selected DataJoint version; eliminate global current-query/user assumptions in multi-pane operations. |
| RetinAnalysis schema and utilities | Canonical catalog, parser, source metadata and readers | One schema authority, reconciled stimulus metadata, incremental import jobs and versioned outputs. |
| EpicTree splitters/UGM | Grouping and epoch inclusion compatibility | Optional reader/tree adapter with stable identities; explicit selection scope. |
| RetinaSRM export profiles | Existing downstream datasets | Validate compatibility readers/exports and preserve corrections/source limitations. |

These names refer to inspected local source in `/Users/maxwellsdm/Documents/GitHub/datajoint/next-app` and the sibling repositories. The plan does not claim all existing components are immediately compatible with DataJoint 2.2.2.

## Proposed React component responsibilities

```text
WorkspaceShell
  ProjectSwitcher / NavigationRail
  ProjectSidebar
    ProtocolWorkspaces
    SavedQueries
    ReviewQueue
    Datasets / Figures / Activity
  MainWorkspace
    ProjectOverview
      ProjectMetadataSummary / MetadataTable
      ProtocolCards
      CellCoverage
      ReviewIndicators
      ImportTimeline
      FigurePreviews
    ProtocolWorkspace
      Coverage / Query / Cells / Dataset / Figures
    RecordingInspector
      OptionalSplitTree
      DeviceTracePanel
      MetadataPanel
      TagsAndInclusion
      RelatedRecordingsAndFigures
    ImportPanel / DatasetPanel / ActivityPanel
  ContextInspector (collapsible)
```

This is a conceptual decomposition. Reuse existing components where appropriate and avoid extracting tiny wrappers merely to match the diagram. Final panels and widgets should follow the walkthrough, not the file structure above.

## Landscape interaction layout

Design the primary experience for a wide desktop window. Keep the project rail/sidebar and page header anchored. Protocol cells appear as compact rows across the available workspace, expanding to details on demand. In inspection, the split tree and trace/metadata view sit beside each other; the tree and inspector scroll independently. Keep source identity and scope in the header when the user scrolls. Metadata remains visible by default beneath the trace and reachable without opening a modal. The optional right context pane and comparison pane consume horizontal workspace; allow resizing/collapsing panes and remember their widths.

Provide a persistent Hide sidebar / Show sidebar control in the top application bar. Hiding project navigation gives its width to the workspace; keep the restore control visible and remember the preference. This is independent of the inspection tree toggle and must preserve the active page, query, expanded rows, focus and curation.

Interactive controls must retain their roles across layout changes: a cell row expands its details, its inspection action opens the scoped cell, epoch focus loads its trace, checkboxes select targets for explicit tagging/inclusion actions, and details reveal stable identifiers. Resizing/collapsing a pane must not reparse sources, clear selection, change dataset scope or restart analysis. Narrow-window accommodations are secondary; do not optimize the primary product into a long portrait/mobile feed.

## State boundaries

- **Server data:** sources, acquisition facts, cell identities, import jobs, tags, review decisions, query definitions/evaluations, dataset revisions, figure provenance and export events.
- **Shared project context:** selected project, protocol workspace and active dataset draft. Changes are explicit and reflected in all panes.
- **Pane-local state:** focus, expanded branches, split recipe, chosen device, axes/window and comparison scope. A figure or another protocol can open without altering dataset membership.
- **Pending edits:** tag/inclusion decisions carry target scope and draft version; stale requests or failed saves remain visible. Widget state never becomes the sole copy of scientific curation.
- **Read caches:** metadata pages, trace windows and aggregates have revision-aware keys and bounded memory. Cache invalidation follows source or membership changes, not arbitrary React rerenders.

## Presets and review workflow

1. Save a project/protocol query once, using existing query controls.
2. Import another recording; the job records its source identity and parses only new/changed input.
3. Re-evaluate affected presets against the new catalog revision and record the delta.
4. Show new matching cells/recordings with unreviewed status. The user can inspect immediately or return later.
5. Tag/include/exclude and mark review/approval at an explicit scope and version.
6. Update the DataJoint dataset as a new revision; offer portable export when needed.
7. Record each operation and output in Activity, including failures and retries.

Review requirements are a visible dataset policy. The design must not silently omit new records or imply that default inclusion equals approval. A linked receptive-field figure provides context; whether it is sufficient evidence of cell quality remains the scientist's decision.

## Local operation

Keep project data/configuration persistent across app launches and manage the configured backend/worker lifecycle through one entry point. Ordinary import, parsing, querying, inspection and export must not require a terminal. Show actionable service/source errors in the app.

The desktop packaging mechanism remains open. The React UI can run in a desktop shell or as a locally served app; the choice must preserve local/NAS file access, background jobs, durable state and clean shutdown. No new shell framework or database has been installed in this task.

Docker is allowed if it simplifies reliable installation/operation; the scientist clarified that eliminating setup friction is the requirement, not forbidding Docker. RetinAnalysis's documented setup currently uses a DataJoint/MySQL container. Keep packaging behind the app launcher and never make the scientist run a container command for each import. Evaluate managed containers versus a native/local or existing lab database during packaging. Do not replace the selected DataJoint catalog with SQLite just to avoid a service.

## Current mockup and validation limits

The conversation sketch uses example cells, timestamps, imports, traces and figures; none are observations from the research databases. It demonstrates project/protocol navigation, tagging targets versus inclusion, review, optional tree grouping, linked figures, presets and save/export history. It does not parse files, access DataJoint, benchmark performance or validate scientific output.

The actual product implementation will be React. The HTML sketch is disposable design material and should not become a second frontend architecture.

## Before implementation

Use the reviewed design to choose a small end-to-end path: one real source → existing parser/schema → protocol overview → epoch inspection/tagging → query preset → new-source discovery/review → DataJoint dataset revision. Validate identifiers, membership, waveform fidelity and responsiveness before expanding protocol coverage. The supplied task currently covers mapping and design, not a production migration.
