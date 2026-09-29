# Source-first recording workflow

Status: source mapping and implementation audit, 2026-09-27. The source-predicate → saved candidate → compare → apply-to-protocol bridge is implemented; shared source annotations and downstream adapters remain proposed. This document distinguishes implemented behavior from the next design. It does not change acquisition data or databases. Evidence comes from local source inspection; historical README dataset counts are not newly verified database measurements.

## Intended workflow

Start with the source DataJoint catalog of ingested recordings. Browse/filter its metadata, inspect raw epochs on demand, add shared annotations, and select an analysis cohort. Save the cohort as a reusable query with explicit selection decisions. An optional tree organizes that query's results. Freeze exact membership when exporting to Wheeler, MATLAB, RetinAnalysis, or another analysis consumer.

A named analysis grouping may be called a “protocol” in the UI, but it is not the acquisition protocol class recorded by Symphony. It can span acquisition protocols. Internally use distinct concepts:

- **Acquisition protocol:** original rig class, such as `VariableMeanNoiseCurInject`.
- **Saved cohort/query:** user-defined set of source epochs selected by typed predicates and explicit decisions.
- **Tree view:** ordered grouping fields over those epochs, independent of inclusion.
- **Dataset revision:** immutable evaluated membership plus provenance and artifact references.

## Confirmed reusable source database

RetinAnalysis already defines the acquisition hierarchy; do not create a competing acquisition database.

| Existing entity | Confirmed implementation | Reuse |
| --- | --- | --- |
| Experiment | `/Users/maxwellsdm/Documents/GitHub/retinanalysis/src/retinanalysis/config/schema.py:55` | Original `h5_uuid`, metadata/attributes, `meta_file`, raw `data_file`, `tags_file`, project/rig facts |
| Animal, Preparation, Cell | same file:81,104,124 | Existing parent links, experiment links, source UUIDs and typed/source JSON metadata |
| EpochGroup | same file:141 | Original group label/properties/timing; its protocol can be `no_group_protocol` when blocks differ |
| EpochBlock | same file:222 | Acquisition protocol FK, parameters, original UUID and timing |
| Epoch | same file:244 | Original UUID, parent block, parameters, properties, attributes and timing |
| Response and Stimulus | same file:262,280 | Device name, stream UUID and `h5path` inside the experiment's H5; response sample-rate fields |
| Acquisition Protocol | same file:41 | Rig protocol class name lookup, not an analysis cohort |
| Tags | same file:294 | Shared object annotations described below |

Numeric database row IDs are internal foreign-key machinery. `h5_uuid` survives row renumbering, but the inspected schema does not declare it unique. Retain the importer's explicit uniqueness/membership validation. Portable source references should carry catalog identity, source checksum/revision, object kind and original UUID; file location alone is not identity.

The existing parser/population path is reusable:

- `retinanalysis/src/retinanalysis/utils/parse_data.py:1077`: `Symphony2Reader`; `read_write(datajoint=True)` writes the metadata staging representation.
- `retinanalysis/src/retinanalysis/utils/database_pop.py:235`: maps parsed source fields into schema tuples.
- The same file:658 stores the H5 path on Experiment and descends through the acquisition hierarchy.
- The same file:434,449 stores response/stimulus H5 locators.
- The same file:698 still contains a placeholder auto-parser for missing JSON. Rieke OS's explicit parse/validate/import orchestration correctly fills this gap while reusing the parser and population functions.

JSON parser output and a metadata read cache can remain implementation details. They should not make users export/reimport data merely to begin inspecting or selecting catalog epochs.

## Existing shared tags: semantics and limitations

`retinanalysis/config/schema.py:294` defines `Tags` with:

- auto-increment `tag_id`;
- `h5_uuid` of the annotated H5 object;
- experiment FK plus `table_name` and `table_id` identifying its current catalog row;
- `user: varchar(63)`, documented as any profile/name string;
- `tag: varchar(255)`, whose comment describes a historical comma-separated format.

`retinanalysis/utils/database_pop.py:404` imports each supplied `(user, tag)` pair as a row, preserving the tag string verbatim. It is invoked for experiment, animal, preparation, cell, epoch group, epoch block and epoch. The inspected response/stimulus population functions do not invoke it. The tag dictionary is passed down the hierarchy, so import-file structure must follow the actual population contract rather than assuming every tag file is one flat mapping.

This is author attribution, not authentication or an access-control boundary. The table does not supply revision history, a uniqueness constraint on `(object, author, tag)`, or immutable audit events. Do not infer an exclusion rule or a scientific condition from an arbitrary tag. Do not merge another author's annotations when a user removes their own tag.

**Smallest next integration:** expose an object-annotation adapter over this existing Tags table; read source annotations in the project browser; make author/object scope explicit. Audit writes with the workspace Event mechanism. Preserve the existing raw tag representation until an explicit tokenization rule handles comma-separated legacy values. Use UUID plus resolved object kind/experiment to reconcile current numeric row references. Avoid a second independent source-tag store.

## What Rieke OS already implements correctly

- `python/recording_workspace.py`: reuses RetinAnalysis parsing/population; validates identities, parameters, source hashes and stream locators; records source revisions and import events in `recording_workspace` bookkeeping.
- `python/workspace_service.py`: metadata-first read model checked against source manifests and the DataJoint query; bounded response reads occur only on demand.
- `python/workspace_tree.py` and service tree methods: typed metadata grouping, explicit missing branches, original epoch membership preserved.
- `python/workspace_recipes.py`: query snapshots, immutable export recipes and exact membership; optional tree settings travel as a view.
- `python/workspace_curation.py`: revision-checked inclusion/tags/optional review with SQL events and completed export records.
- `python/workspace_audit.py`: versioned evidence envelope and read-only repeat suggestions.

The current source-first bridge extends these components:

1. `validate_protocol_definition()` / `evaluate_protocol_file()` still define acquisition-protocol starter workspaces. They are compatibility inputs, not the final bound dataset definition.
2. `python/workspace_predicates.py` evaluates a bounded typed metadata predicate over the validated source read model. This is not arbitrary SQL or a copy of the historical string-condition executor.
3. `python/workspace_explorer.py` stores immutable `ExplorerRevision` recipes and a project/protocol `ProtocolBinding` pointer. `workspace_service.query_result()` resolves the effective dataset; the API passes its exact scope to inspection, curation, masks and export.
4. The explorer's focused epoch panel is read-only. Its explicit **Apply to protocol** action binds the saved candidate to a working dataset, then opens that workspace for inclusion, tags and export. A separate wider-scope navigation is labeled explicitly.
5. Current `Curation` is keyed by `(project_uuid, protocol_uuid, epoch_uuid)` and stores both tags and inclusion. Those tags are local workspace annotations, not existing RetinAnalysis `Tags` rows. They must not be presented as already synchronized source annotations.
6. Current completed export is a frozen JSON reference package. A source-to-SRM SQLite or Wheeler-specific ingestion adapter is not implemented by that package.

## Remaining integration contract — shared annotations and analysis adapters

### Shared annotation versus analysis selection

Keep two operations distinct:

- **Annotate source object:** attach/remove an author-attributed tag on an existing source entity using the Tags adapter. Visible from every query containing that object.
- **Include in this cohort:** change a selection override keyed by saved cohort plus source epoch. Excluding an epoch from one analysis does not remove it from the source catalog or silently exclude it from another cohort. Review remains optional.

Retain existing protocol-scoped curation as legacy cohort-local state. Do not silently promote its tags to shared source tags or apply old exclusions globally. A versioned compatibility path can treat each existing protocol workspace as an initial saved cohort.

### Reusable typed query

The current implementation uses `ExplorerRevision` with a versioned typed predicate and separate `ProtocolBinding`; see the implementation appendix below. The following earlier *conceptual* cohort payload illustrates future shared-tag/selection integration. It is not the current API wire format, and its source-tag clause is not implemented:

```json
{
  "format": "recording-cohort",
  "version": 1,
  "cohort_uuid": "<stable UUID>",
  "project_uuid": "<existing project UUID>",
  "catalog_ref": "../catalog.json",
  "name": "Current-noise comparison",
  "query": {
    "version": 2,
    "all": [
      {"field": "cell.type", "operator": "eq", "value": "RGC\\ON-parasol"},
      {"field": "epoch.parameters.frequencyCutoff", "operator": "in", "value": [25, 100]},
      {"field": "source.tags", "operator": "contains", "value": "usable", "author": "<explicit author scope>"}
    ]
  },
  "selection_revision": "<cohort-local selection revision>",
  "view": {"group_by": ["date", "cell", "epoch.parameters.frequencyCutoff"]}
}
```

`view` is optional. The typed field registry should supply supported operators and value types; grouping availability alone does not imply that every field is safely queryable. Validate numeric comparisons, array equality, tag author scope, null versus missing and unsupported fields. Fail closed on unsupported predicates. A first implementation can support bounded `all`/`any`/`not`, `eq`/`in`/numeric comparisons and explicit `is_missing`; share the same evaluator contract between visual controls, saved queries and agent access.

Saving a live query does not freeze its future membership. An explicit selection of UUIDs can be a typed membership predicate or a cohort override; store which meaning the user chose. At export, record the evaluated query, source revisions, annotation/selection revision, exact epoch identities and fingerprints, optional tree order, adapter/code version and artifact checksum. Re-evaluation must show added/removed/changed members without modifying older exports.

### Source-first interaction

Project recordings → visual metadata filters → optional lazy epoch inspection/shared tagging → save query/cohort or explicit selection → optional tree view → export exact revision.

There is no required detour into a predefined acquisition-protocol workspace. Those existing pages remain convenient starter queries. One source epoch can appear in several saved cohorts and several exports without being copied in the main database.

## Existing SRM databases are downstream analysis products

Two related export generations exist locally; they should not be conflated.

### Earlier compact Kosmos package

- `/Users/maxwellsdm/Documents/GitHub/matlabPyrTools/retinaSRM/export_to_kosmos.m:46` traverses a legacy MATLAB tree by cell type/date/cell/seed/group/frequency/SD.
- The same file:92 and :514 chooses the SD child with the largest epoch-list count; this is an analysis selection policy, not neutral ingestion.
- The same file:532 now includes date in CSV filenames. The `kosmos_export/README.md` collision description refers to an older filename convention; do not treat it as a verified description of the current exporter.
- The same file:536 reads selected voltage and reconstructed current, adds a 90 Hz low-pass voltage, and writes trial samples.
- `retinaSRM/build_kosmos_db.py:129` builds the sample table from exported CSVs and filename/summary metadata.
- `retinaSRM/kosmos_export/build_kosmos_db_compact.py:44` normalizes conditions; raw samples reference condition IDs. This inspected compact schema does not preserve an original source epoch UUID column.

This is a handoff database containing selected/materialized traces and derived products, not a replacement for the acquisition catalog.

### Newer VMN database

- `retinaSRM/curreinjt_diff_mean_population.m:312` explicitly assigns `epoch_uid = ep.objectID`, an **Ovation object ID**.
- `retinaSRM/build_vmn_diff_mean_db.sh:56` defines per-epoch identity and condition/trial links; its slim raw-trace schema stores voltage samples, with timing/current reconstruction supported downstream.
- `retinaSRM/export_vmn_stim_params.m` and `retinaSRM/vmn_stimulus_python/vmn_stimulus.py` preserve/use per-epoch stimulus recipes.

Ovation `epoch_uid` (for example `x-coredata://.../Epoch/p768`) is a different identity namespace from Symphony `h5_uuid`. Do not equate them, strip a short suffix as a global identity, or invent correspondence. Reuse downstream table/analysis concepts with an explicit adapter and a namespaced identity map supported by evidence.

## Natural independent handoffs

| Stage | Durable output | Next consumer |
| --- | --- | --- |
| Ingest and validate | Source catalog rows + manifest, source hash, parser version, raw locators | Visual catalog, RetinAnalysis, agent query service |
| Annotate and select | Shared object annotations + saved typed cohort query + selection revision | Any visual view or analysis planner |
| Freeze | Exact dataset membership, source/metadata/annotation provenance, optional view | Export adapters and Wheeler |
| Materialize or analyze | Reference JSON, explicit SQLite/array package, or analysis result with source identity map | SRM, MATLAB/Python, Wheeler |
| Return results | Versioned analysis run/artifacts linked to the dataset revision | Project overview and further investigation |

The immediate architectural change is therefore the query/annotation/cohort boundary in front of the existing catalog. Replacing the source schema or making the tree the prerequisite for a cohort would add another representation boundary rather than remove one.

## Clarification: reuse the DataJoint results tree as the inspection interface

The tree **can and should remain an inspection interface**. “Optional tree” in the proposed contract means the custom grouping recipe or serialized tree artifact is optional; it does not mean inspection must leave the tree, or that the tree may only be a static preview. A source hierarchy beside metadata and a device trace viewer is already an established implementation in Samarjit's DataJoint application.

### Confirmed existing interaction and functions

Paths below are relative to `/Users/maxwellsdm/Documents/GitHub/datajoint/next-app/`.

| Step | Existing code | Actual behavior |
| --- | --- | --- |
| Filter source records | `api/helpers/query.py:128` `process_query`, :149 `create_query`; `api/app.py:336` execute-query route | Applies conditions through source tables, returns a DataJoint relation |
| Render acquisition hierarchy | `api/helpers/query.py:160` `generate_tree` | Experiment → Animal → Preparation → Cell → EpochGroup → EpochBlock → Epoch; node level/row ID, labels, protocol and authored tags; optional hidden levels |
| Optionally include full objects | same file:209 `generate_object_tree`, or `generate_tree(include_meta=True)` | Adds object metadata and epoch response/stimulus records; does not load their waveforms |
| Focus a source node | `src/app/components/results/ResultsTree.js` `updateItems` and `handleFocus` | Generates node keys from experiment/level/row ID; clicking sends object level and row ID to its parent |
| Fetch node metadata | `src/app/components/ResultsViewer.js` `displayInfo` / `getFocusedData`; `api/helpers/query.py:257` `get_metadata_helper` | Loads selected source object's metadata into the adjacent information/JSON panels |
| Discover available visualizations | `src/app/components/results/Information.js` `fetchOptions`; `api/helpers/query.py:260` `get_options` | Patch epoch: response/stimulus devices with H5 locators. MEA block: available sorting algorithm outputs |
| Display selected device | `Information.js` `fetchImage` / `handleOptionChange`; `api/helpers/query.py:314` `get_trace_binary`; `api/app.py:528` | On-demand server-rendered trace PNG from H5; MEA has a separate spike-histogram renderer |
| Show source tags | `src/app/components/results/CustomTreeItem.js` | Displays annotation text with author alongside the object level/protocol |
| Export an optional tree artifact | `ResultsViewer.js` `handleDownload`; `api/app.py:362` `download_thread` | Serializes the current query's tree, optionally restoring hidden levels and adding metadata |

There is no literal `fetchData` function in the inspected results implementation. The concrete hooks are `getFocusedData`, `fetchOptions`, `fetchImage`, `get_options`, `get_data_generic` and `get_trace_binary`.

### Lowest-risk reuse seam

Use the existing **catalog, query-to-source-hierarchy projection, object metadata lookup and device-discovery semantics** behind the current Rieke OS UI. Adapt them to a request-scoped service rather than requiring the separate old Flask app to hold the active query globally.

The default flow is:

**Source filters → matching epoch relation → canonical acquisition hierarchy → focus node/epoch → metadata + device trace.**

Offer **custom field grouping** as another view over the same epoch membership: date/cell/block/parameters/conditions. Keep a separate “Arrange tree” configuration mode with the existing hierarchy preview; return to the focused tree-and-trace inspector when inspecting. Both views retain the same stable source references and cohort selection state. A group click can display metadata and a membership summary; an epoch/device focus loads a bounded raw trace. Neither operation needs an export.

An **inspection tree** is a live or cached presentation over the current query. A **tree export** is a saved serialization of that presentation, potentially with metadata references. A **dataset export** freezes selected epoch membership for downstream analysis. These are separate actions: a user may export a cohort without a tree artifact, inspect through a tree without exporting anything, or save a tree recipe without materializing traces.

### Specific gotchas to handle while adapting, not copy unchanged

1. **Request context:** `query.py:34` holds module-global database/user/query state; `fill_tables` only assigns database/user when absent. `api/app.py` also holds global active query/excluded levels. Bind catalog/project/actor/query per request or saved cohort so another session cannot silently change the inspected/exported data.
2. **Epoch-grain membership:** `process_query` joins down through Response and returns a response relation. That can omit epochs without response rows and repeat epochs across devices; `generate_tree` uses unique ancestor IDs to reconstruct the display. Start the new cohort contract from explicit epoch identities, attaching devices afterward. Do not redefine a source cohort as “epochs that happen to have a selected response.”
3. **Database work:** `generate_tree` repeatedly fetches IDs, object rows and tags at each node; `include_meta=True` refetches object metadata. Reuse the projection contract but batch metadata reads or page children. Keep H5 waveforms out of hierarchy generation.
4. **Typed filters:** `process_condition` accepts condition strings, and tag restrictions are projected through numeric row IDs. Route the new visual query builder through the typed, validated predicate adapter described above; preserve project/object scope and stable UUID references.
5. **Device reads:** `get_options` returns client-visible H5 paths and `get_trace_binary` reads an entire device trace into a PNG plotted against sample index. Retain the current Rieke OS server-side UUID/locator validation and bounded sample-window endpoint, calibrated time/units, and interactive display. Some stimulus objects have parameters but no stored waveform; expose that as reconstruction availability, not an empty “raw stimulus” plot.
6. **Incomplete generic helper:** `get_data_generic(:296)` checks capitalized `Stimulus`/`Response`, whereas `helpers/utils.py:99` builds lowercase table-map keys. Its parent restrictions also differ from the explicit dictionary restrictions used by the current service. It is not a drop-in validated data adapter.
7. **Frontend stale focus:** old metadata/options/image requests have no abort or focus-generation guard; a slower prior request can populate the panel after focus changes. `Information` also retains an earlier image when a device has no visualization. Preserve the current abortable resource lifecycle and clear device/trace state when focus changes.
8. **Author scope:** old `query.py:357` `add_tags` attaches the global user; `delete_tags(:371)` does not restrict by author. Do not inherit that deletion behavior when exposing shared annotations. Selecting a parent for a tag and including all its descendant epochs are different operations and must be labeled separately.
9. **Export completion:** old download route returns after starting a background thread; failure is printed to the console. Keep Rieke OS's explicit job/artifact completion and checksum registration. “Raw tree” there means tree JSON, not raw voltage samples.

No source database, UI, or scientific code was modified for this appendix. The next implementation can preserve the current tree inspector and add a canonical source-hierarchy adapter without undoing the custom tree builder or forcing inspection into a separate non-tree workflow.

## Predicate-first explorer: Samarjit semantics and compatibility boundaries

Confirmed source UI references under `/Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/setup/`:

- `QueryContainer.js:93` `handleAfterEffects` composes table-specific query groups and an optional exclusion-tag predicate; `handleAddQuery(:174)` saves the editor's query object.
- `LogicBlock.js:87` `sendUp` maps visual All/Any/None controls to `AND`/`OR`/`NOT` arrays. Nested logical blocks and condition rows are created separately.
- `CondBlock.js:132` `sendUp` builds a condition string from a source/table field, operator and value, or a manually supplied JSON subfield/type. Each row has a Save action and an unsaved-changes indication.
- `SetUpStepper.js` submits the query to the execute endpoint separately from building it.
- Backend `api/helpers/query.py:105` `process_condition`, :111 `apply_conditions`, and :128 `process_query` turn that representation into restrictions and source hierarchy joins.

Reuse the nested visual predicate editor, source-field discovery and explicit execute boundary. The historical backend is not a reliable reference implementation for Boolean algebra:

1. `apply_conditions` recursively extends child lists, so nested operator boundaries can be lost. For example, an OR child inside an AND parent is flattened into that parent's conjunction. Preserve typed AST nodes instead; test `A AND (B OR C)` independently from `(A AND B) OR C`.
2. The UI's “None” emits a `NOT` group, but the backend negates an `AndList`. “None of these” means `NOT(A OR B)`, not `NOT(A AND B)`. Prefer a clearly labeled unary NOT around one group, or define `none` explicitly with tests.
3. TAG leaves select objects for which a matching tag row exists. A tag inequality predicate is not the complement of tag equality: objects without tags have no matching row for either positive existence predicate. A negated equality can include untagged objects. Keep tag author/object scope explicit.
4. `hideExclude` injects an additional `NOT TAG='exclude'` at execution/composition time, while saved queries use the unmodified editor object. Do not inherit that hidden difference. Save/log the actual applied predicate, including any exclusion policy.
5. JSON subfields are typed manually and serialized into SQL-like strings; importing these old conditions into a typed query requires explicit parsing/validation, not executing a raw legacy condition string.

### Acceptance checks for the new explorer

These are requirements/review checks, not a claim that the implementation is complete:

- Draft edits and the last applied query are visibly distinct. Result counts, grouping, epoch focus, cohort save/export and history refer to the applied query until Execute succeeds.
- Incomplete/invalid conditions produce a clear error; they must not silently disappear or revert the entire query to all recordings.
- Boolean nodes preserve nesting, and empty-group semantics are explicit. Values remain typed: number `25` differs from string `"25"`, and Boolean `true` must not accidentally equal numeric `1`.
- A missing key, explicit JSON null, an empty array, and a literal string `"[]"` remain distinguishable. Ordinary comparisons must not invent values for missing fields. A `missing`/`exists` operation states exactly which category it tests.
- Filters change membership. Grouping only reorganizes those exact members, including missing-value branches. Metadata suggestions should be based on the relevant source/query scope, with that scope clear.
- Execution history records the actual AST/query version, source/catalog revision, count and preferably exact membership snapshot or deterministic membership digest. “Open past query” restores its predicate; re-executing against changed data is a new execution, not a claim that old results were reproduced.
- Handoff to inspection preserves the applied subset. Resolving only the acquisition-protocol name and opening all its epochs would widen the result silently. Carry the applied query/cohort identity or explicit evaluated membership, or clearly label an intentional wider-scope navigation.
- Visual checkbox targets, cohort inclusion, authored source annotations and optional review remain separate. Querying an annotation never implicitly changes it.

These checks preserve the user's intended flow: source database → visual predicate → inspected/annotated selected data → reusable cohort/query → optional grouped view or export. The tree remains a valid inspection interface throughout.

## Latest scope: apply a rerun to a protocol's working dataset

The intended handoff now includes an explicit **Apply to protocol** operation. A predicate result is not merely a read-only explorer snapshot or a link to a broader predefined page. The user reruns a source query, sees the difference, and applies the new exact dataset revision to a protocol workspace. That workspace's inspection, selection and export then use the applied dataset. Older revisions remain available.

### Implemented query and binding behavior

`python/workspace_predicates.py` supplies recursive typed `all`/`any`/unary `not` predicates and explicit missing/null comparisons. `python/workspace_explorer.py` records immutable ExplorerRevision recipes with typed predicate, exact UUID/fingerprint membership, source revisions, tree fields, parent/diff and checksum, transactionally with Event. `/api/explore/revisions` refreshes/validates source metadata and returns the exact evaluated preview used in the saved revision. `ProtocolBinding` points from project/protocol to an immutable revision with an optimistic version. API `compare_protocol_candidate()` computes the exact UUID/fingerprint difference; `apply_protocol_revision()` refreshes source metadata, checks the candidate and expected working token, and calls `ExplorerHistory.bind()` to switch the pointer and record its Event atomically. The advisory lock is shared with curation/export registration.

`workspace_service.query_result()` exposes the exact bound IDs, effective typed predicate, saved tree view, binding version and changed-metadata IDs. `capture_query()` records that effective predicate and binding separately from the acquisition starter query; export rejects changed bound metadata. Reusing an export checks the effective query checksum. Curation/mask/export writes recheck the binding version under the shared lock.

For an already bound workspace, `POST /api/protocols/<id>/refresh` reruns the saved predicate and records a new candidate without moving the binding. The UI's **Review update** opens that candidate; **Apply to protocol** performs the explicit switch. Older query revisions and completed exports remain unchanged. Protocol inspection initializes the saved candidate's tree fields; grouping itself does not select or discard epochs.

### Binding acceptance contract

1. Store a `ProtocolBinding` in workspace SQL, keyed by project and protocol workspace identity, pointing to an existing same-project ExplorerRevision. Include an optimistic binding revision. This is bookkeeping over the existing source database, not a copied acquisition schema.
2. Keep the source query definition, the rerun proposal, and the current applied dataset distinct. A rerun creates a candidate with added/removed/changed UUIDs; it does not automatically alter the current protocol dataset.
3. Apply checks the expected binding revision, candidate identity/project, and exact source membership/fingerprints, then switches the pointer and writes a before/after Event in one transaction. Retain the earlier immutable ExplorerRevision.
4. One effective-query resolver must drive every protocol consumer: counts, metadata filters, hierarchy/custom trees, epoch pages, lazy inspection membership checks, masks, curation, refresh comparison, and export. Never bind only the displayed tree while export still evaluates the old acquisition-protocol predicate.
5. Include the binding revision and ExplorerRevision UUID in `query_revision`, even when two revisions happen to have identical epoch sets. This prevents stale clients from overwriting a newer working-dataset choice.
6. Export records the actual bound typed predicate, dataset revision, selection revision and exact eligible membership. The old one-clause `validate_protocol_definition`/`capture_query` contract must not label newly bound members with the previous acquisition-protocol query.
7. Preserve protocol-local curation by stable UUID. Removed members retain historical decisions; newly added members receive the documented defaults. Inclusion in a prior export remains immutable. Optional review is not a prerequisite to applying or exporting a dataset.
8. Missing bound IDs or changed metadata cannot silently reduce membership, broaden to the source protocol, or fall back to the old query. Show the reason and the explicit rerun/reconciliation route. A frozen applied dataset is different from re-evaluating a saved live predicate.
9. The UI names the active protocol dataset and candidate distinctly. After successful Apply, inspect and export the bound dataset directly. The earlier warning-only “switch to a broader predefined workspace” is a temporary boundary, not the completed handoff.

### Audit evidence and limits

Static review confirms the effective-query path across protocol metadata/counts, filtering/tree results, protocol-scoped epoch access, curation, mask import, export and export reuse. The frontend keeps draft edits, saved membership and later previews distinct; applying is disabled for an unsaved tree or changed preview membership. Preview refresh uses the current cached catalog; saving or applying performs fresh source validation.

The parent reported an HTTP regression case: bind two epochs, add a new matching source epoch, refresh to a three-epoch candidate while the working dataset stays at two, then explicitly apply three while preserving the earlier revision. Backend tests also cover binding conflicts during curation/mask/export registration. These are test-fixture results, not edits to scientific recordings.

A final static audit flagged a separate reconciliation edge: when a formerly bound UUID is genuinely unavailable, the normal resolver fails closed, but refresh/compare initially reused that resolver and therefore blocked the reconciliation operation itself. This was reported to the backend owner for a dedicated frozen-binding comparison token; do not infer coverage of missing-source removal from the new-source addition test alone.

Remaining product boundaries are shared RetinAnalysis Tags parity, independent creation/naming of new cohort workspaces, a full canonical source-hierarchy presentation, and downstream analysis adapters. The current JSON export contains stable references and exact membership; it does not materialize a Wheeler/SRM analysis database or raw waveform package. No scientific database changes were performed for this audit.
