# Recording workspace — integration and UI design handoff

2026-09-27. Scope: codebase audit, integration design and interactive UI concept. No production application, database migration or scientific recomputation was performed.

## Recommended direction

Build one local React app around the existing RetinAnalysis parser/schema and the existing DataJoint web app's query, inspection, tagging and export behavior. A scientist selects an H5 file in a project; a background job parses and indexes it, records provenance, refreshes saved queries and presents new matches for review. The scientist can inspect and tag epochs, save a curated dataset in DataJoint, or hand it to another tool through a documented export.

The project database is the shared catalog. User-defined protocol workspaces organize overlapping subsets of recorded cells, queries, datasets and figures. Initial workspaces are variable-mean noise current injection and current injection across frequency cutoffs. A receptive-field figure is linked context for a cell, not automatically another protocol workspace. A split tree is a grouping of query results and never a required database format.

## Read the design

| Document | Covers |
|---|---|
| [Workflow map and evidence](UNIFIED_WORKSPACE_DESIGN.md) | Actual parallel routes, visual-selection implementations, source evidence, current gaps, lazy loading and integration risks |
| [DataJoint schema reuse](DATAJOINT_HANDOFF_SCHEMA_DRAFT.md) | Existing schema and pointers, 2.2.2/0.14.x differences, minimal additions, source versions, project membership and MATLAB handoff |
| [Integration contracts](INTEGRATION_CONTRACTS_DRAFT.md) | Stable identities, parsed packages, query/split operations, curation, revisions, export profiles, trace reads and future validation cases |
| [React workspace plan](REACT_WORKSPACE_PLAN.md) | Existing components to reuse, navigation, visible metadata, state ownership, presets/review and one-launch local operation |
| [Domain vocabulary](../../CONTEXT.md) | Acquisition hierarchy, user-defined protocol workspace, cell identity, split tree, inclusion, review and figures |

The conversation's interactive sketch is stored at `/Users/maxwellsdm/.codex/visualizations/2026/09/27/01a0e3c1-f067-7783-b12b-8ad71ea4dc0f/recording-workspace.html`. It is disposable design material, not a second frontend. All records, timestamps, traces and figures are illustrative. The app implementation should be React, reusing the inspected frontend where appropriate.

## Decisions incorporated from the walkthrough

- Project home shows distinct imported cells, protocol coverage, review indicators, linked figures and import activity. Counts across protocol workspaces can overlap.
- Metadata is visible immediately: project/source/import summary above, full metadata below; epoch metadata follows the trace and changes with focus.
- Protocol cells use a compact list of cell name/number, recording date and type tag. Expanding a row opens detailed coverage, epoch counts, duration and inspection controls. Stable cell/trial UUIDs are available in details.
- Group that list by cell type and provide phase/drug filters at epoch scope. Per-protocol import/query/tree/export actions remain prominent. Refresh comparisons visualize added, changed and no-longer-matching records before updating a dataset.
- Landscape desktop layout is fixed: persistent navigation, compact horizontal lists and independently scrolling tree/inspection/content panes. Narrow windows must not dictate a portrait-first app.
- The linked DataJoint React web app supplies the core query/filter/visualize/select/export interaction. Overviews surround it and show completed dataset saves/exports with exact counts and history.
- Automatic activity history lives in the database, including tag/inclusion before-and-after values, actors, timestamps, changed/targeted counts and export outcomes. Editable notes/corrections retain original events.
- Docker is permitted as an internal packaging choice if it simplifies operation. One-launch use without recurring manual service setup remains the requirement.
- Import is selecting/dropping an H5 file. RetinAnalysis handles parsing and loading; intermediate JSON and service startup are not recurring manual tasks.
- Raw files can remain in place. Stable asset/version identity is separate from filesystem location; streams point to a source version and H5 dataset path.
- New matching recordings enter a review queue. Saved queries refresh without reparsing unchanged sources. Source changes and new parser/mapping versions remain distinguishable.
- Focus, bulk-tagging targets, inclusion and review are separate states. A tree split or related figure does not change dataset membership.
- Dataset publication freezes exact membership and provenance. The live query can discover new records without modifying previously published results.
- Save in DataJoint is a normal destination. External scripts can query the catalog or read a portable package. EpicTree is optional.
- Tagging, masks, devices, query conditions and export options come from the existing web app. Time cropping is not part of the current requirement.
- Metadata queries, paged trees, visible-row rendering, windowed full-rate waveform reads, bounded caches and background jobs are the speed strategy. This has not been benchmarked.

## Natural handoffs

| Stop after | Handoff | Independent user can |
|---|---|---|
| Parse/map | Versioned metadata package plus source/stream references | Use another catalog or their own reader without adopting the app |
| Catalog/query | Documented scoped query or dataset revision with stable identities | Use Python/Wheeler or a compatible MATLAB reader without building a tree |
| Visual curation | Frozen membership, decisions, provenance and data dictionary | Continue analysis with their own code; rebuild a split tree if useful |
| Portable export | Explicit compact SRM, VMN or recording-package profile | Read without the UI, Wheeler or a running DataJoint service |
| Analysis | Input-revision/parameter/code record and output artifacts | Link figures back to the cells/dataset that produced them |

Reference-only exports require accessible source files. Bundled exports include the required waveform data. Existing compact SRM and VMN files have different schemas and cannot be treated as interchangeable. Preserve their corrections and provenance limitations rather than rebuilding them during integration.

## Design completion audit

The requirement here is a verified map and design, not working production ingestion. This table identifies the evidence and the boundary of each claim.

| Requested requirement | Current evidence | Result |
|---|---|---|
| Delegate codebase reading | Completed `workflow_audit` agent inventory and execution-path report, incorporated into workflow evidence index | Audit delivered; static inspection, not byte-by-byte or runtime certification |
| Map EpicTree, web DataJoint, RetinAnalysis and RetinaSRM | Current-route diagram, responsibility table and source links in workflow map | Documented separate routes and manual transitions |
| Inspect both named SQLite exports | Read-only schema/count queries reconfirmed 108 compact conditions and 168 VMN conditions; 13 base cell IDs in each | Profiles documented; no unsupported claim of 26 distinct biological cells |
| Explain identities and provenance | Identity rules, unresolved legacy mappings, source versions and correction limitations in contracts | Design covers source-to-export lineage |
| Reuse schema and science | Schema comparison and code/component reuse tables | RetinAnalysis 2.2.2 baseline; old web adapter compatibility work explicit |
| Simple H5 import with pointers | Source-pointer extension and import-job lifecycle | Existing fields reused; missing orchestration/versioning identified |
| User-defined protocol/project overview | React plan, vocabulary and updated interactive sketch | Both requested protocol workspaces represented; RF linked as a figure |
| Linked same-cell context | Recorded-cell identity rules and related-figure navigation | No joining solely on short cell label; view membership remains separate |
| Cell/trial UUIDs and useful cell details | Readable-label/UUID schema extension and expandable-list design | Mutable type tags separated from identity; counts/time/cutoff scope defined |
| Tree and visual selection | Three existing GUI roles traced; split/query/curation contracts and interactive tree | Optional grouping, tagging targets and inclusion distinguished |
| Tagging, masks and export choices | Existing web source/screenshots and capability list; mock interaction controls | Reuse preserved in design; no invented time-crop requirement |
| Presets, incremental updates and review | QueryContainer/query.json evidence; preset evaluation/review sequence | New matches and dataset revisions specified |
| Logs, counts and metadata visibility | Activity contract, source/import schema additions, overview/epoch tables | What/when/who/counts/version/outcome specified and visually represented |
| Natural independent handoffs | Five boundary contracts and handoff table above | App, DataJoint, tree and Wheeler not mandatory at every stage |
| Lazy loading and speed | Current loading audit, proposed paging/cache/window rules, validation scenarios | Strategy designed; latency and sample fidelity still require runtime tests |
| Slack-like React app design | Navigation reference, component/state reuse plan and interactive sketch | Concept refined through user feedback; packaging remains an implementation choice |
| Landscape desktop interaction | Fixed application frame, persistent navigation, compact lists and separate tree/inspector scroll areas | Desktop geometry verified in the sketch; production split-pane implementation remains future work |
| Keep work at design stage | Current epicTreeGUI status contains design documents plus pre-existing untracked Java artifacts; no tracked production edits | No migration or app implementation undertaken |

## Verification record and limits

The final audit rechecked all 35 distinct absolute local file targets linked by the five design/vocabulary documents; every target exists. Repository HEADs at this audit: epicTreeGUI `25bcf10`, web datajoint `4f961f4`, retinanalysis `cea6a96`, and retinaSRM `0c8ac97a`. These identify checkout baselines; the audit reads working files and does not assert clean sibling repositories.

SQLite was opened with `mode=ro` and `PRAGMA query_only=ON`. The compact file has no `epochs` table and stores explicit time, raw/cleaned voltage and current in `raw_traces`; VMN has `epochs` and voltage-only `raw_traces`. No waveform tables were scanned for project counts.

The updated sketch passed JavaScript syntax and duplicate-ID checks. Browser inspection verified visible project metadata, navigation to Cell 2, switching epoch 1 to epoch 4 updating identity/current mean, optional tree visibility, and simulated import stages. No browser errors were reported in that check. This verifies those design interactions, not all production features, responsive sizes or scientific calculations.

During the earlier landscape refinement, a 1440 × 900 test viewport produced a 1406 × 738 app frame. The protocol content scrolled within its 571-pixel pane. In inspection, the tree and trace/metadata panes stayed side by side with independent 488-pixel scroll areas. Moving from epoch 1 to epoch 4 retained the example cell UUID and changed the example epoch UUID; readable date/cell labels stayed consistent. The scientist subsequently replaced default cards with compact expandable rows. These are synthetic UI checks, not validation of real UUID assignment or ingestion.

The list/export/log revision was checked in the browser: expand a dated cell row → inspect → select one epoch → add an example tag → exclude that epoch → export. Focused-cell counts became 5/6; protocol-wide scope showed 29/30 included, one excluded, 12 held by approval policy and 17 exportable epochs. A simulated database save appeared as revision 1 with 17 epochs in both protocol and project overviews. Activity retained timestamps, actor/project, tag `[] → [reviewed-example]`, inclusion `true → false` and structured export counts. JavaScript syntax and duplicate IDs passed; the browser reported no errors. These counts are fixture checks, not research data. Database-backed persistence and editable correction records remain implementation requirements; the sketch only keeps preview state.

The treatment/diff refinement was checked separately: ON parasol + Drug + NBQX filters returned two illustrative cells/nine matching epochs; opening the second cell showed only epochs 3–5 and Export Control retained that three-epoch predicate. Refresh & compare showed the named example evaluation transition (18 → 30 epochs, +12 added), with separate changed/removed categories and actions to inspect new matches or prepare another dataset revision. Existing saved preview membership stayed at 17 epochs. The actual VMN metadata audit independently confirmed 1,784 NBQX epochs and 1,520 empty-additions epochs despite all 168 condition groups being labeled Control; see the React plan for the exact field and interpretation limits.

Wheeler's graph was unavailable during its health check, so live graph provenance is unverified. DataJoint ingestion, schema migrations, MATLAB client compatibility, scientific outputs, multi-user writes, packaging and performance were not executed. The future validation cases in the contracts are acceptance criteria for implementation, not tests claimed to have passed.

## Implementation handoff

The design goal is delivered. Further layout refinement can continue against this baseline without treating the sketch as approved production behavior.

When implementation is requested, first choose a real Symphony H5 and deliver one end-to-end VMN slice: file selection → parser/population job → project/protocol metadata → raw epoch inspection → tags/inclusion/review → saved query → DataJoint dataset revision. Then add a second source to validate incremental discovery, identity-safe deduplication and retained review history. Validate both portable SQLite profiles and the optional EpicTree bridge separately.

Before lab distribution, decide desktop packaging and shared versus per-user catalog deployment; demonstrate one-launch operation, recovery from an interrupted import, verified source relocation, and performance on local/NAS storage. Existing research databases remain inputs to compatibility validation, not disposable migration targets.
