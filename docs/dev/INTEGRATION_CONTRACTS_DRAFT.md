# Integration contracts — discussion draft

Status: proposed contracts, not implemented endpoints or a schema migration.
Date: 2026-09-27.
Companion: [workflow evidence and design](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/docs/dev/UNIFIED_WORKSPACE_DESIGN.md).

## User journey and ownership

Import → map/parse into the project catalog → visually inspect, tag and select → save/update a queryable dataset → optionally export for another tool.

The split tree is a primary inspection interface. It can be reconstructed from a saved grouping recipe, but downstream consumers do not need a tree object or the GUI. An export's membership belongs to a dataset revision, not to the current screen's expanded branches or focused row.

Confirmed navigation: project overview with distinct cells and protocol coverage → protocol overview with its cells → recording inspection. The project's underlying catalog need not be exposed as database administration. Protocol-specific exports may be separate databases, while shared identities support navigation from one cell's noise recording to its receptive-field data.

Confirmed integration direction: reuse RetinAnalysis's current DataJoint 2.2.2 schema/query/parser infrastructure. The app manages routine import/parse/inspection operations so users need not open scripts. Preserve independent handoffs through the database and documented exports. See [schema reuse design](/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/docs/dev/DATAJOINT_HANDOFF_SCHEMA_DRAFT.md).

Protocol navigation means user-defined workspaces (initially VMN and current injection across frequency cutoffs), each linking presets, datasets and figures. Preserve the acquisition protocol name separately as source metadata. A workspace can match multiple acquisition protocol versions using an explicit saved rule. Linked receptive-field information is a measurement/figure, not necessarily another workspace. Shared recorded-cell identities support navigation between both workspaces and linked measurements.

| Stage | Owns | Must not silently decide |
|---|---|---|
| Source registration | Asset identity, format, locations, availability | Scientific inclusion, cell classification |
| Parsing/mapping | Source facts, normalized fields, mapping rules, warnings | Whether a trial is scientifically usable |
| Visual curation | Dataset scope, inclusion overrides, reasons, reviewed state | Changing original source metadata or raw samples |
| Dataset publication | Exact membership, compatibility profile, manifest and files | An implicit “most repeats” selection rule |
| Downstream analysis | Versioned computations and result artifacts | Reinterpreting source identity or modifying a published input revision |

## Identity and version rules

Use an internal stable identity plus explicit source-identity mappings. A source identity has `(namespace, source_asset_id, object_id)`; the namespace identifies Symphony, Ovation, or a particular legacy export profile. A source asset's location may change without changing its identity. Record file fingerprints separately from paths.

- Preserve Symphony `h5_uuid` and Ovation `epoch_uid` verbatim. Do not equate them without evidence.
- A compact SQLite trial initially has an identity scoped to the registered database version plus `(condition_id, trial_number)`. Mark its raw-source mapping as unresolved until established. This is a valid exported-trial identity, not an invented acquisition UUID.
- Do not derive stable cell identity from mutable cell type, date formatting, or `Cell1` alone. Keep corrected classifications and original labels as versioned metadata.
- For unidentifiable/missing source IDs, record explicit local identity and provenance limitations. Do not claim cross-export equivalence.
- `epochIndex`, tree node IDs, display paths, and SQLite rowids are local locators. They are not portable scientific identities.
- A metadata revision references a parser run and mapping-rule version. Re-parsing produces a new revision with an explicit correspondence report; it does not overwrite the historical interpretation.
- A dataset revision references exact epoch/stream identities and input revisions. Re-running its saved query can create a new revision; it cannot silently expand an already-published revision.

## Boundary A: parsed-recording package

Minimum contract:

| Record | Required information |
|---|---|
| Package | Contract name/version, package ID, producer/version, created time |
| Sources | Asset IDs, format, fingerprint status, available locations |
| Acquisition entities | Stable local ID, source identity, entity type, explicit parent relationships |
| Metadata | Original names/values, typed normalized fields, units, scope and provenance |
| Epochs | Identity, acquisition relationships, timing, protocol identity when known |
| Streams | Epoch, device, units, sample rate/timebase, sample count, storage locator |
| Stimulus recipes | Generator identity/version, all required parameters, seed, units; reconstruction support status |
| Validation | Per-entity errors/warnings, unsupported fields, unresolved identities, source availability |

Preserve block and epoch parameter values separately and record the effective-value rule (the existing Symphony parser applies epoch overrides). A mapping editor should show source field → proposed canonical field → converted value, with a sample and affected-record count. Preview before applying a mapping revision. Preserve unknown fields rather than discarding them.

Package readers need no DataJoint installation. A DataJoint ingest adapter can consume the same package as a local catalog adapter. Importing an existing protocol SQLite dataset enters here with an explicit profile and provenance limitations; it need not be exported back to MAT first.

Import jobs expose per-source states: registered, parsing, parsed-with-warnings, ready, failed, cancelled. Record progress and resumable checkpoints. A failure for one source does not present another source as failed or block browsing already-ready data. “Ready” means structurally usable, not scientifically reviewed.

## Boundary B: query and split-tree view

### Reusable presets and incremental discovery

The web app already implements saving/loading named query objects: [QueryContainer](/Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/setup/QueryContainer.js:148) calls helpers that persist them to [query.json](/Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:83). Reuse that query logic and import existing presets. The missing integrated behavior is project-scoped persistence, version/history, automatic discovery of new matching data and a durable review queue.

A preset is a reusable predicate over the current catalog. Store its project scope, owner/shared status, query version, field semantics and relevant display options. Current code saves `query_obj`; options such as `hideExclude` and hidden display levels are held separately and need deliberate persistence. The current UI's `exclude` tag filter and UGM import's `excluded` tag also need a compatibility mapping rather than two silently different meanings.

When an import completes, identify affected presets and compute added/removed/changed matches against the previous evaluation. Report new matching cells/recordings and put them in the review queue. Refreshing a query does not invoke the parser. Unchanged sources reuse prior parse results; a changed asset/parser/mapping version starts an explicit new parse run.

Persist each query evaluation with query version, catalog/source revisions, evaluation time, membership and relevant metadata versions. Compare epochs by stable identity: added/no-longer-matching describe membership; changed describes retained identities with changed metadata/source/curation context. Report these axes separately when they overlap. Include reasons (new source, corrected drug/type, changed predicate or selection policy) rather than conflating all changes with new cells. Diff summaries count distinct affected cells; their totals need not sum because categories may overlap. A removed match is not a deletion. Opening a diff never mutates published membership.

Cell-type grouping and control/drug/wash filtering use explicit metadata scope. Preserve phase independently from drug and concentration. In the actual VMN export, all condition groups say Control while 1,784 epochs explicitly record NBQX; a group name must not override epoch pharmacology. Empty additions mean no additions recorded, not proof of control or wash. Source values, mappings and manual corrections remain separately inspectable and versioned.

Review is scoped to a source/metadata revision and the affected cell/protocol/recording or epochs. Suggested states are unreviewed, in review, approved, and needs attention. The scientist can defer review without losing new matches. Updated source data does not inherit approval blindly; retain the prior decision and show which new version needs review. Generic tags remain available but structured review state should not depend on interpreting arbitrary tag strings.

Keep the live preset, its evaluated result, review state, and a published dataset revision distinct. A preset can discover new cells immediately; publication can apply a stated approval policy and freeze membership. The final dataset may be a DataJoint relation/revision queried directly, with no export file and no tree required. File packaging is an optional handoff. Log each preset evaluation and dataset update with its query/version and membership delta.

The service contract below is conceptual; names are examples rather than deployed APIs.

| Operation | Input | Result / invariant |
|---|---|---|
| List project summary | Project, catalog revision | Protocol/recording/curation counts with definitions and completeness; zero waveform reads |
| List protocol coverage | Project, protocol, catalog revision | Distinct recorded cells, recording counts and participation in related protocols; counts may overlap across protocols |
| Get related recordings | Stable recorded-cell identity, project scope | Other protocol recordings of that same cell, with source linkage, availability and unresolved-link status |
| Discover fields | Scope and protocol/profile | Available dimensions, types, units, valid operators, missingness and computed-field status |
| Preview dataset | Typed filter expression, catalog revision | Counts, stable query identity, compatibility warnings |
| Expand split branch | Query identity, ordered split recipe, branch predicates, cursor | One page of groups with counts and next cursor; no recursive whole-tree fetch |
| List epochs | Query/branch predicates, ordering, cursor | One page with stable identities and inclusion/review state |
| Explain membership | Dataset draft/revision, epoch | Query match, policy contribution, explicit decision and source revision |

Use typed field identifiers and values rather than accepting SQL fragments from UI controls or agent prompts. Support explicit missing-value groups. Distinguish unique biological cells, recordings, conditions, epochs and streams in all counts. Filters and split dimensions must use compatible units or show an explicit conversion.

The initial distinct-cell count refers to stable recorded-cell identities established by source metadata. Tracking one biological cell across recording sessions requires additional verified identity evidence. Date and short label alone may be insufficient. Protocol membership is many-to-many with cells and is derived from their acquisition records. A related recording can be opened for inspection without adding its epochs to the active curated dataset. Any cross-protocol quality rule is explicit and versioned; a missing RF recording is not automatically a failed cell.

Arbitrary MATLAB splitter functions remain possible through a computed-dimension adapter. Their outputs must be keyed by epoch identity and include code/input versions. Mark uncomputed dimensions as pending; do not execute expensive functions inside a tree expansion request.

The acquisition hierarchy remains available as a saved view. Other split views can group the same membership by cell type → cell → protocol → mean → SD, for example. Reordering dimensions never changes inclusion by itself.

## Boundary C: curation and publication

Keep three states separate: focus, inclusion, and reviewed status. A scientist can inspect an epoch without excluding it, or include all epochs by policy while only some have been reviewed. Do not label default inclusion as manual review.

Draft structure: base query/revision, explicit selection policy, per-epoch overrides, author and decision history. The UI shows the current draft name and scope beside inclusion controls. A changed filter updates the view; adding/removing records from the draft is a distinct action.

Bulk inclusion/exclusion resolves the branch predicate against a specific revision and reports the affected membership/count. Collapsed or unloaded descendants are handled by the service, not by iterating only browser-visible rows. Use a draft version for writes; on a conflicting write, show the conflict and retain both users' pending work rather than silently overwriting it.

Publication resolves and freezes membership, records the source/mapping revisions and selection policy, validates the chosen export profile, and generates an artifact manifest. The preview shows included/excluded/unreviewed counts and any policy such as “SD with most repeats.” Report what the profile cannot preserve. Users can choose another profile or explicitly accept a documented compatibility limitation.

Legacy UGM can be imported as a selection decision set scoped to a chosen draft and identity mapping. Missing IDs are reported. Do not apply a global “excluded” tag without stating scope. UGM export remains a compatibility output and carries only what that format can express.

### Tagging and mask scope — clarification resolved

The scientist clarified that “cropping” referred to tagging and the existing web-app selection tools. Preserve that functionality; time cropping/sample-range editing is outside the current requirement. Whole-epoch masks are verified, and UGM should not be described as storing sample ranges.

Preserve the web application's multi-selection, select-all/select-children, add/remove user tags, metadata display, device visualization, query conditions, hidden hierarchy levels, and export-with-metadata/all-level options. The local checkout adds EpicTree MAT export and UGM import. Tag push/pull/reset behavior requires explicit scope and a recorded outcome in the unified UI. Export selection policy must distinguish the backend query from items highlighted for bulk tagging.

### Activity history and database updates

Every import, parse, mask/selection revision, dataset publication, export and failed attempt has an operation ID and recorded lifecycle. Show concise human-readable history in the UI and retain structured details for scripts.

Persist this history in database relations, not only text files, browser storage or a transient terminal. A mutation and its audit event commit together; for long export jobs, record requested/running/failed/completed lifecycle events with one operation identity and separate retry attempts. Completion follows artifact validation. Tag and inclusion events retain target UUIDs, prior/new values, actor, timestamp, scope and source/dataset versions. Distinguish targeted, actually changed, skipped and failed counts; applying an existing tag again is not another scientific change.

The scientist asked for a log that can be revisited and edited. Proposed behavior: allow editable notes and explicit corrections linked to events, retaining the original action and earlier annotation revisions. Record who corrected what and when. This permits useful bookkeeping edits without overwriting the evidence of what was imported, tagged or exported. Access and retention policy can be chosen during implementation; the activity view is a readable projection of these records.

Successful dataset/export records also appear in the project and protocol overviews, with destination, time, cell/epoch counts and a link to exact membership/history. Imported catalog counts and exported/curated counts are separate measures. Editing today's tags must not rewrite the membership or history of a prior published revision.

Record actor, start/end time, project, source asset/fingerprint, parser/mapping version, dataset/input revision, mask/selection revision, requested action, destination/profile, counts added/matched/skipped/excluded/failed, status, warnings/errors, output references and finalized checksums. Record retries as attempts of the same logical operation. Do not label an operation exported before the output has been validated and finalized.

Dropping a file starts an ingestion job; it does not silently change a previously published curated dataset. Newly parsed records appear in the project catalog as unreviewed. “Update dataset” creates a new revision with a membership/metadata diff; old revisions and exports retain their identities. An existing database adapter must explicitly distinguish adding new records from replacing or correcting old ones. Re-import deduplication uses source identity/version, not filename alone.

Self-contained here means one app owns the visible workflow and manages its configured backend/workers. Deployment packaging and shared-lab versus per-user catalog location remain design choices; no claim is made that a browser alone can access arbitrary local/NAS paths without a local service.

## Boundary D: portable dataset

A package has a manifest, metadata/dictionary, membership/provenance records, and either included waveform assets or declared external references. Optional analysis outputs do not prevent raw-data publication. Export profiles should declare capabilities rather than pretending every package has all fields.

Initial profiles to specify against current consumers:

| Profile | Preserve / expose | Compatibility requirement |
|---|---|---|
| Existing compact SRM | Conditions, explicit time and voltage/current columns, canonical identity corrections, analysis-table availability | Preserve canonical views and remediation semantics; document unresolved original epoch identity |
| Existing VMN | Conditions, full epoch identity, timing, stimulus recipes, voltage and sample order | Reader honors rowid ordering/epoch bounds for legacy files; do not assume current or cleaned voltage columns exist |
| New portable recording profile | Metadata + explicit epoch/stream/sample coordinates, waveform arrays or references | Full membership and version manifest, reader examples, no GUI/DataJoint/Wheeler runtime requirement |

Example manifest fields (illustrative placeholders, not real artifact IDs):

```json
{
  "contract": "curated-recording-package",
  "contract_version": "0.1-draft",
  "dataset_id": "example-dataset",
  "revision_id": "example-revision",
  "profile": "vmn-legacy-compatible",
  "membership_file": "membership.csv",
  "dictionary_file": "dictionary.json",
  "data_mode": "bundled",
  "assets": [{"path": "recordings.db", "sha256": "<computed-at-export>"}],
  "source_revisions": ["<registered-input-revision>"],
  "selection_policy": "<explicit-policy-and-version>",
  "producer": {"name": "<adapter>", "version": "<version>"},
  "limitations": []
}
```

Write to a staging destination, validate, then finalize the export. Failed/cancelled jobs leave no artifact labeled complete. Checksums describe finalized content. Repeated export of the same revision preserves membership and scientific values; timestamps/compression do not need to be byte-identical unless deterministic packaging is explicitly required.

## Boundary E: waveform and analysis access

Request: source revision, epoch ID, stream ID, sample interval `[start, stop)`, and optional explicitly named transform version. Result: exact sample coordinates/timebase, values, units, source identity, provenance and availability/error state. Keep raw, measured, reconstructed and processed signals distinguishable.

One response must never silently substitute another file/device, use another epoch's sample rate, or coerce unsupported variable-length trials into a common matrix. Aggregate requests declare alignment, units, sample-rate handling, membership revision and method. Full-rate raw inspection does not apply display smoothing or decimation.

Caches are bounded by bytes and keyed by all data-affecting inputs. Source/mapping/transform revisions invalidate the appropriate entries. Curation changes invalidate membership-derived summaries, not raw waveform bytes. A request token prevents late results from drawing in the wrong pane after rapid navigation. Duplicate in-flight requests may share work, but cancellation of one subscriber does not cancel remaining subscribers.

Analysis adapters consume a frozen dataset revision and return a run record: inputs, code/environment/parameter versions, status, logs, metrics and output assets. Existing MATLAB and RetinAnalysis code can be wrapped without rewriting their methods. Wheeler requests the same query/trace/analysis operations as any other client; its graph can link published artifact identities without becoming mandatory for browsing.

## Initial validation scenarios

1. Parse one Symphony source and compare normalized metadata, UUIDs and sampled waveform reads against its H5 source.
2. Load both existing SQLite profiles read-only; expose differences and unresolved identities without fabricating equivalence.
3. Expand a large group without reading traces or transferring all epoch metadata; verify bounded payload and rendered-row count.
4. Include/exclude a collapsed branch, reorder splits, reopen the draft and export; exact membership stays consistent.
5. Display epochs from two different source files, then navigate rapidly; every trace, unit and label remains attached to the correct identity.
6. Compare raw waveform samples before and after cache, packaging and reader round-trips; check sample ordering explicitly.
7. Publish raw-only data; absence of an SRM fit is visible and does not block another tool from reading the recordings.
8. Re-parse with changed mapping or add new recordings; existing published revisions retain their exact original membership and interpretation.
9. Import third-party metadata, export a dataset, then read it with a minimal standalone script without the app or DataJoint.
10. On local disk and NAS, measure cold/warm latency, memory, query counts, bytes and cancellation under large-project navigation. Set concrete performance budgets from those measurements.
11. Open noise and receptive-field recordings of the same verified cell; navigate back without losing scope, focus or unsaved curation. Confirm the project distinct-cell count counts this cell once.
12. Export two protocol datasets containing that cell; both retain the same source/cell linkage, while their independent epoch membership and curation revisions remain distinct.

## Implementation choices to validate after design

- Confirmed: project-level distinct cells and protocol coverage, then a protocol-level cell overview.
- The sketch places the optional split tree at the left of epoch inspection; validate its width and collapsed state on a real workload.
- Comparison panes are independent views with explicit optional links for axes/focus/filter controls; exact layout remains adjustable.
- The sketch demonstrates approved-only publication with an explicit choice to include unreviewed records. This is a proposed policy, not a scientifically mandated default.
- Start the proposed validation with Symphony H5 and VMN; select a concrete real source before executing it. Compact SRM and VMN export profiles both remain in scope.
- Desktop packaging, shared versus per-user DataJoint deployment, and storage format choices require implementation evaluation. Local app use and metadata browsing with an unavailable raw source are design requirements.

These are product/schema decisions to discuss; this draft does not settle them by implementation.
