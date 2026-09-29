# Workflow function parity and integration inventory

Audit date: 2026-09-27. This is a source-code audit, not a claim of complete feature parity or successful MATLAB/browser execution.

## Implementation update

Since the initial audit below, the UI now has searchable metadata-field tree
building, ordered/reorderable levels, adaptive presets, typed parameter/condition
splits and live group counts. Missing versus recorded null/array/string/numeric
values remain distinct. Tree group and epoch rendering is paged. Review is now
optional: included epochs export by default, and each epoch shows its main catalog
and exact saved-export memberships. General query predicates, branch bulk selection
and legacy MAT/UGM compatibility remain separate gaps; the new tree builder groups
existing query results rather than changing that query.

## Evidence and scope

The requested [SamarjitK/datajoint repository](https://github.com/SamarjitK/datajoint) was opened and its published README read. It describes the database setup, data/metadata/tag directories, nested queries, results tree, device visualizations and tag synchronization. The detailed function inventory below follows the local implementation rather than relying on the README alone.

- DataJoint web checkout: `/Users/maxwellsdm/Documents/GitHub/datajoint`, clean at `4f961f416c1b1482880f34c20f2ba1b5b2875239` when inspected.
- EpicTreeGUI checkout: `/Users/maxwellsdm/Documents/GitHub/epicTreeGUI`, base `25bcf10f0f60f5bf6b2e1bf5357cbe9204ba25b7`, plus current uncommitted workspace implementation.
- Current UI: `workspace-app/src`; current adapters: `python/workspace_*.py` and `python/recording_workspace.py`.
- No recording, curation, mask, database or export was changed during this audit. Current code is being developed concurrently; references describe the inspected functions and may move as files are edited.

**Status vocabulary:** **Implemented** means present in the current source; **Partial** means a narrower implementation exists; **Missing** means no corresponding integrated action; **Library only** means an existing scientific function is callable from MATLAB but is not an integrated UI action. Presence is distinct from validation.

## Keep these meanings separate

| Concept | Existing semantics | Required meaning in the integrated app |
|---|---|---|
| Acquisition schema | DataJoint's Experiment → Animal → Preparation → Cell → EpochGroup → EpochBlock → Epoch → Response/Stimulus records describe acquisition facts. | One main project catalog with stable source identities. Creating a protocol workspace must not duplicate the recording into a separate source database. |
| Saved protocol query | Upstream query objects select records through predicates at multiple hierarchy levels. Current `.protocol.json` files use a much narrower exact acquisition-protocol predicate. | A versioned definition referencing the main catalog. A user-defined protocol can eventually span acquisition classes and conditions; that is not the same as a schema table or a tree node. |
| Source metadata / tags | H5 properties, keywords, type labels, group labels and acquisition parameters are observations from the source. Upstream `Tags` is a separate SQL annotation table. | Preserve the original values and origin. Never silently convert a label such as `NBQX5um` or an empty solution field into a verified treatment phase. |
| Working selection | Web `ResultsTree.selectedItems` chooses objects for tag actions; focus independently chooses metadata/visualization. | Temporary, visible bulk-action targets. Checking these boxes does not include, approve or export epochs. |
| Inclusion | EpicTree `isSelected` drives selected-data extraction, masks and exported selection. The separate `singleEpoch` viewer also has `includeInAnalysis`. | A persistent Boolean inclusion decision, separate from temporary targets and scientific approval. UGM translation should map the appropriate persistent flag explicitly. |
| Approval | Legacy selection is not an explicit scientific approval workflow. | A separate reviewed state, bound to source/metadata revision. Importing inclusion masks must not approve epochs. |
| User annotation | Upstream tags include `(user, tag)` and an object level. Current curation stores a protocol/epoch tag list with actor provenance in events. | Do not claim per-user ownership, object-level tag parity or lab synchronization until those semantics are implemented. |
| Export revision | Legacy downloads generally use the current query; masks use source epoch UUIDs. | Preserve the generating query, filters, review policy, exact identities, source revisions and output checksum. Reusing the query evaluates current data; it does not rewrite the old export. |

## Import, schema and query functions

| Function and source | Read/write semantics | Current equivalent and integration location | Gap or constraint |
|---|---|---|---|
| Select/start/connect database; set username — [web API initialization][dj-init], [SetUser][dj-user] | Starts/stops configured Docker database and stores a process-global database/user. User determines tag attribution. | **Partial:** the local launcher connects the configured DataJoint runtime; Files & database displays its separate storage. Actor comes from the local account. Place additional project/runtime setup in Settings, outside daily import. | No integrated lab-user selector or multi-project database switcher. Avoid copying process-global user/query state into concurrent panes. |
| Add data / population — [web AddData][dj-add], [API worker][dj-pop] | Takes three directories: raw H5, pre-parsed metadata JSON, and tags JSON. Starts a background population thread. It does not turn the H5 file picker into a parser by itself. | **Implemented, streamlined:** [recording importer][rw-import] parses with RetinAnalysis, validates UUIDs/source paths/rates/parameters, imports metadata and creates durable jobs; current Import page takes H5 or a local path. | Preserve duplicate detection and explicit failed-job state. Do not replace the checked parser with ad hoc UI parsing. |
| Table/field introspection — [table_fields][dj-fields] | Reads DataJoint headings and classifies date/JSON/string/numeric fields for the condition editor. | **Missing UI:** metadata is visible but there is no schema-aware field picker. Add it to the protocol Query panel. | Schema display and queryable field registration are related but distinct. JSON keys need a known type and units; do not infer all strings as numeric. |
| Nested Boolean predicates — [CondBlock][dj-cond], [query evaluator][dj-query] | Numeric comparisons, string `like`/`not like`, JSON subfields, and tag predicates combine through AND/OR/NOT and hierarchy joins. | **Partial:** [protocol validator][rw-query] only accepts one exact `EpochBlock.protocol_name` equality. Current view filters are cell UUID/type and raw group label. | This is the largest query parity gap. Adapt the builder UI to a validated typed query AST and DataJoint 2.x evaluator; do not execute imported SQL condition strings. Preserve explicit missing values and logical grouping. |
| Named query save/load/delete — [QueryContainer][dj-presets], [saved_queries][dj-query-files] | Saves named query objects to `query.json`; loading populates controls. Deleting removes the named entry. | **Partial:** durable protocol definitions, query snapshots, refresh/compare, and export “Reuse query” exist. New definitions cannot yet be authored through a general query editor. | Add protocol creation, rename, edit and revision history. An edited definition must invalidate stale previews and require a fresh comparison. |
| Hide levels / hide excluded — [QueryContainer][dj-hide], [generate_tree][dj-tree] | Hidden levels are omitted from the returned display tree while their predicates still affect the query. “Hide excluded” adds an epoch tag predicate. | **Partial:** optional tree and ordered splits reorganize matching epochs; inclusion and review are explicit fields. | Preserve grouping-versus-membership separation. Upstream “hide excluded” checks tag **`exclude`**, while UGM import writes **`excluded`**; do not reproduce this mismatch. |
| Refresh after annotations / new import | Upstream reruns the query to see changed tags, which can alter matching results. | **Implemented:** refresh produces a saved query comparison and new current membership; exports remain frozen. Location: protocol header and activity. | Added/changed/removed counts need a navigable result set, not merely text. Metadata-only changes and new epochs of an existing cell must remain distinguishable. |

## Tree, focus, curation and metadata functions

| Function and source | Read/write semantics | Current equivalent and integration location | Gap or constraint |
|---|---|---|---|
| Build hierarchy with field paths — [buildTree][et-build] | Groups existing epoch objects by ordered key paths; does not create a new underlying scientific data source. | **Partial:** [workspace tree builder][rw-tree] accepts date/cell/cell type/block/group/protocol; Inspector has typed splits, chronological block/epoch labels and lazy DOM branches. | Broaden using an allowlisted field registry and actual unique values. Empty/unknown values must stay visible. Splits must never alter membership. |
| Functional and protocol-specific splitters — [buildTreeWithSplitters][et-splitters], [splitter library][et-domain-splits] | Functions derive group values: experiment date, cell type, keywords, holding signal, block start, contrasts, frequency, radius/diameter, etc. | **Missing:** only the six field splits above are integrated. Location: tree builder advanced fields. | Reuse tested scientific transformations through named/versioned adapters. Never evaluate arbitrary code typed into the UI. Fields such as radius and diameter require explicit transformation provenance. |
| Focus versus checkboxes — [ResultsTree][dj-focus], [EpicTree callbacks][et-focus] | Web focus fetches object metadata independently of tag targets. EpicTree node clicks often display the first descendant epoch; checks change `isSelected`. | **Partial:** React separates focused UUID from bulk target UUIDs and persistent inclusion. Folder clicks currently expand/collapse; only leaves focus an epoch. | Add a node summary/focus action with “show first epoch” explicitly labeled. A folder click must not masquerade as an average trace. |
| Select all / unselect / immediate children — [web selection helpers][dj-select], [EpicTree recursive selection][et-select] | Web selects all rendered hierarchy IDs or immediate child nodes for tag actions; EpicTree recursively changes inclusion flags. These are different operations. | **Partial:** React selects/clears the visible page, retains explicit targets with a persistent bulk banner, and can apply include/exclude separately. | Add scoped “select descendants” and “select all matching epochs” without silently targeting records outside the active query. Display the exact count and retain focus independently. |
| Example markers / node custom data — [onSetExample][et-example], [putCustom][et-custom] | EpicTree toggles node `isExample`; node custom metadata also stores analysis results. | **Missing:** no example flag, node result registry or linked figure store in the real React app. | Add explicit annotation/figure relations to stable identities, not ephemeral node paths that change after regrouping. |
| Add/remove tags — [web tag mutations][dj-tags], [current curation store][rw-curation] | Web writes tags for selected object IDs with user attribution; delete query does **not** restrict by user. | **Partial:** React supports durable epoch tags and explicit bulk add/remove; individual tag removal is focus-only. Location: directly below raw traces. | Source tags and annotations at cell/group/block levels are not equivalent to the current protocol/epoch tag list. Preserve authorship when adding hierarchy-wide annotations. Never copy the legacy unrestricted delete. |
| Push/pull/reset tags — [tag synchronization][dj-sync] | Push rewrites this user's tags in per-experiment JSON while retaining other users; Pull deletes/reimports other users' SQL tags; Reset deletes/reimports all users' SQL tags. | **Missing:** current tags are durable in the project database but have no legacy `/tags/` synchronization. | A replacement should be “Export annotations” and a previewed merge/reconcile operation with revision/conflict handling. Reset is not a harmless refresh. Log imported bundle hash and before/after deltas. |
| Persistent inclusion and explicit approval — [EpicTree selection API][et-selection-api], [singleEpoch toggles][et-single-flags] | Tree `isSelected` is used by analysis and UGM. `singleEpoch` modifies local `figData.epochs` flags; persistence back into the master tree must not be assumed solely from the checkbox. | **Implemented with distinct semantics:** SQL curation stores `included`, `review_state`, tags and revisions; temporary checkboxes remain separate. | Imported masks alter inclusion only. Branch approval needs a named scope and revision validation, not propagation based solely on visible tree structure. |
| Metadata details at all hierarchy levels — [get_metadata_helper][dj-metadata], [EpicTree epoch info][et-info] | Reads the currently focused object. EpicTree's main GUI has a compact summary; separate `singleEpoch` includes parameters and flags. | **Partial:** raw trace first, protocol parameters, epoch metadata, cell/group/block ancestry and source references exist in React. | Animal/preparation/experiment metadata and direct branch metadata focus are not yet full parity. Keep field origin visible rather than flattening colliding names. |
| Epoch stepping and keyboard navigation — [singleEpoch navigation][et-step], [graph keyboard handlers][et-keyboard] | MATLAB has previous/next/slider within its epoch list; tree arrows expand/collapse/move and checkbox shortcuts. | **Partial:** React has bounded previous/next within the loaded page and paged lists. Browser-native button/tab navigation exists. | Add keyboard shortcuts only with clear focused-pane scope. Tree rows need explicit keyboard tree behavior before claiming accessibility parity. |

## Visualization and scientific data access

| Function and source | Read/write semantics | Current equivalent and integration location | Gap or constraint |
|---|---|---|---|
| Device response/stimulus choices — [Information][dj-vis-ui], [get_options][dj-vis-options] | Reads Response and Stimulus records for PATCH epochs; fetches plots on demand. | **Partial:** current Inspector chooses one recorded response stream with its actual unit/rate. | Add recorded stimulus streams only when samples exist; distinguish them from reconstructed generators. Multiple devices should use separate unit-aware axes by default. |
| Raw response loading — [get_trace_binary][dj-vis-trace], [loadH5ResponseData][et-lazy] | Web reads a full dataset and renders a PNG against sample index; MATLAB reads H5 lazily. | **Implemented, changed renderer:** current [trace service][rw-trace] validates source pointers and returns bounded full-rate samples; Canvas displays time, units, rate and window controls. | “Full sample rate” describes sample fidelity, not whole-record loading. Retain source/H5 dataset identity and cancel stale requests. No smoothing or averaging in the raw view. |
| Multi-stream epoch display and stimulus timing — [singleEpoch.plotEpoch][et-single-plot] | Plots available response data for every stream; adds pre/stim onset/offset markers from parameters. | **Missing multi-stream/timing overlays:** current UI shows one response at a time and timing as metadata. | Restore device toggles/legend and unit-separated axes, with timing markers after ms→s conversion is validated. Do not imply that stimulus parameter duration is recorded waveform duration. |
| Node overlay / mean / SEM — [plotNodeData][et-overlay], [onAnalysisMeanTrace][et-mean] | Loads selected Amp1 epochs, overlays up to 20, or computes mean/SEM. GUI uses 10 kHz as a fallback when sample rate is absent. | **Missing integrated analysis:** raw Inspector has no node averages. | Add a separate analysis view with exact membership, stream, units, timebase and version. Reject missing rates rather than copying the fallback. Do not quietly average mixed lengths/rates/treatments. |
| MEA block histograms — [get_options/get_spikehist_binary][dj-mea] | Reads algorithm-specific spike data for an MEA block and renders histograms. | **Missing / outside current PATCH importer scope.** | Expose only after a tested MEA adapter and file-location contract exist. No placeholder button should imply support. |
| Stimulus reconstruction — [getStimulusByName][et-stimulus], [field mapper][et-map-streams] | Uses `stimulus_id` and parameters to invoke `epicStimulusGenerators` when samples are absent. | **Library only:** current UI retains metadata; it does not reconstruct stimuli. | A generated signal must be labeled reconstructed, with generator version/seed/parameters. Never present it as a recorded response. |
| Extended scientific functions — [analysis methods][et-analysis] | Existing MATLAB routines include `MeanSelectedNodes`, cycle-average response, linear filter/prediction, mean response trace, amplitude statistics, correlation filter and PSTH. | **Library only.** The `Response Amplitude` GUI menu itself is a placeholder, despite a separate library amplitude function. | Keep these callable through optional MATLAB/analysis adapters. Integrating the UI does not authorize replacing their scientific logic. Validate selected membership, units and timing before exposing each. |

## Masks, exports and handoffs

| Function and source | Read/write semantics | Current equivalent and integration location | Gap or constraint |
|---|---|---|---|
| Raw tree / metadata / all-level JSON download — [ResultsViewer download controls][dj-download-ui], [generate_tree][dj-tree] | Downloads displayed hierarchy, or writes a tree with metadata and optionally previously hidden levels. Hidden levels affect representation, not predicate semantics. | **Partial:** current reference package saves exact epochs, metadata, source pointers and recipe. Optional display-tree serialization is absent. | Keep a dataset export independent of whichever tree nodes happen to be expanded/hidden. A visual tree snapshot should be an explicitly separate profile. |
| Export DataJoint query to EpicTree MAT — [web MAT endpoint][dj-mat], [export_to_mat][et-export-mat] | Converts a full source hierarchy to MAT format 1.0, flattening Animal/Preparation into cell metadata. Saves stream H5 pointers rather than raw samples. Rejects MEA. | **Missing integrated MAT profile:** the reusable exporter exists locally but current React export is reference JSON. | Build the full canonical hierarchy from the frozen export UUID set, then adapt field names to the checked exporter. Do not feed the display tree when levels are hidden. Bind every output to the query/recipe revision and verify MATLAB loader compatibility. |
| Export selected MATLAB epochs — [onExportSelection][et-export-selected] | Saves a variable named `selectedEpochs` to MAT. | **Missing profile; distinct from the standard EpicTree MAT above.** | Do not label these two MAT formats interchangeably. The standard loader expects `format_version`, `experiments` and metadata. |
| Save/load UGM — [saveUserMetadata][et-ugm-save], [loadUserMetadata][et-ugm-load], [Python reader][et-ugm-read] | Saves MATLAB v7.3/HDF5 `ugm` version 1.1 containing selection bits and H5 UUIDs. Loads by UUID, not row order. MATLAB load leaves unmatched epochs selected. Python reader skips empty UUIDs and returns selected/excluded UUID lists. | **Partial:** new versioned JSON masks are implemented in the current Inspector/API. They are **not** UGM files. | UGM is a separate adapter. Require UUID uniqueness/validity, lengths, project/source mapping and an explicit new/unmatched epoch policy. Do not silently select unmatched new data or call it reviewed. |
| Import UGM into SQL — [web UGM endpoint][dj-ugm], [import_ugm_tags][dj-ugm-write] | Clears this user's `excluded` tags on referenced epochs, adds them to deselected epochs, and skips missing database UUIDs. | **Not integrated:** current [JSON mask API][rw-masks] requires exact protocol membership/source revisions and updates inclusion transactionally. | Translate UGM inclusion into the current `included` field rather than adopting magic tag names. Report incompatible/partial scope before any write. Preserve approval. |
| Save/reuse exports — [current recipe functions][rw-recipes], [current export API][rw-export] | Current implementation freezes query/membership, writes reference artifact and SQL dataset revision, then reloads saved settings through an explicit reuse endpoint. | **Implemented:** Export Control, Saved exports and “Reuse query”; direct Inspector navigation. | Reusing settings must check definition identity and source changes. Old artifact membership remains immutable. Show exact eligible count and active scope before saving. |
| Source path handoff | MAT responses hold `h5_file`/`h5_path`; JSON reference exports likewise depend on accessible originals. | **Implemented references; partial portability:** Files & database lists managed/external source paths and availability. | Reference exports are not self-contained copies of waveforms. Relocation should verify checksums and update locators through a logged operation. Do not silently rewrite or move external H5 files. |
| Logs and reproducibility | Legacy tag/selection changes largely rely on current SQL/files and console messages. | **Implemented:** paged SQL action history, lazy event details, recorded versions for new events, before/after curation, durable jobs and evidence-linked repeat suggestions. Legacy events explicitly lack code-version provenance. | Terminal import outcomes and transactional curation/export events are recorded; complete start/cancel lifecycle coverage remains partial. A request log alone does not prove that a scientific change committed. |

## Specific adapter hazards to resolve before claiming parity

1. **`exclude` versus `excluded`:** the query UI and UGM writer disagree. Inclusion should have one canonical Boolean and explicit legacy translations.
2. **User ownership:** legacy `delete_tags` restricts object/tag but not `user`; Pull/Reset delete before reload. Import these operations as safe versioned annotation merges, not direct helper calls.
3. **Displayed hierarchy versus export hierarchy:** `export_mat_file` passes `exclude_levels` to `generate_tree`, but `build_experiment` assumes Experiment → Animal → Preparation → Cell. Always reconstruct the canonical hierarchy for MAT output.
4. **Invented units/rates:** [build_response_struct][et-map-streams] defaults absent units to `mV`; EpicTree GUI plotting falls back to 10 kHz. The actual project contains pA, V and mV responses. Current verified H5 values must win; missing values should remain unknown or block a dependent export/analysis.
5. **Matrix compatibility:** [getResponseMatrix][et-response-matrix] checks equal sample counts, but uses the first epoch's sample rate and ignores subsequent rates. New aggregation must also validate rates, units and relevant conditions.
6. **UGM membership:** equal array lengths are not sufficient. The reader skips empty UUIDs; the SQL helper skips missing records; MATLAB auto-selects unmatched epochs. Current fail-closed source/membership checks are intentionally stricter.
7. **Ephemeral node paths:** regrouping changes nodes. Store annotations/figures against stable cell/epoch/dataset identities, with grouping as a view recipe.
8. **Shared mutable backend context:** upstream helper globals cache database, user and current query. A new panel must send project/protocol/revision explicitly rather than inheriting the last request's query.

## Prioritized integration sequence and completion checks

1. **Finish the direct inspection loop.** Raw trace first; tags/include/approve below it; import/export/mask actions in the Inspector; append domain and operation logs. Verify a failed or repeated mutation cannot be reported as a new successful scientific change. Verify individual tag removal ignores an unrelated bulk selection.
2. **Restore useful tree interactions.** Add scoped descendant/all-matching selection, branch metadata summaries, keyboard navigation and field-choice assistance. Verify grouping/expansion never changes the set of matching UUIDs; chronological labels remain stable under filtering.
3. **Implement the actual reusable Query workspace.** Reuse upstream condition/Boolean-editor ideas with a strict typed predicate format, schema field registry, metadata units and versioned protocol definitions. Test Boolean logic, null/empty fields, tag ownership and query refresh diffs against known SQL results. Do not present the current exact-protocol equality as a general query builder.
4. **Complete handoff adapters.** Reuse `export_mat.py`, `field_mapper.py`, `loadEpicTreeData.m` and `import_ugm.py` behind validated adapters. Golden tests must compare exact UUIDs, parent identities, source paths, sample rates, units, parameters and mask decisions through MAT/UGM round trips. Keep JSON reference packages available independently.
5. **Add scientific display parity in small verified steps.** Recorded multi-device traces and timing markers first; generator reconstruction and node summaries next. Derived means/SEM/filter/PSTH are separate opt-in analyses with frozen membership and method provenance. MEA stays unavailable until its backend contract is implemented.
6. **Add lab annotation sharing deliberately.** Model author/scope/source separately, export portable annotation bundles, preview conflicts and record merges. Retain database history rather than emulating a destructive reset button.

## Source references

[dj-init]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/app.py:62
[dj-user]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/setup/SetUser.js:1
[dj-add]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/setup/AddData.js:1
[dj-pop]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/app.py:221
[dj-fields]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:60
[dj-cond]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/setup/CondBlock.js:29
[dj-query]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:105
[dj-presets]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/setup/QueryContainer.js:165
[dj-query-files]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:83
[dj-hide]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/setup/QueryContainer.js:56
[dj-tree]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:160
[dj-focus]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/results/ResultsTree.js:89
[dj-select]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/results/ResultsTree.js:34
[dj-tags]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:357
[dj-sync]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:405
[dj-metadata]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:257
[dj-vis-ui]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/results/Information.js:20
[dj-vis-options]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:260
[dj-vis-trace]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:314
[dj-mea]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:330
[dj-download-ui]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/src/app/components/ResultsViewer.js:190
[dj-mat]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/app.py:393
[dj-ugm]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/app.py:436
[dj-ugm-write]: /Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/helpers/query.py:473
[et-build]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:226
[et-splitters]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:252
[et-domain-splits]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:2307
[et-focus]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/epicTreeGUI.m:463
[et-select]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/epicTreeGUI.m:545
[et-example]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/epicTreeGUI.m:533
[et-custom]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:739
[et-selection-api]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:1260
[et-single-flags]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/gui/singleEpoch.m:379
[et-info]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/epicTreeGUI.m:688
[et-step]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/gui/singleEpoch.m:332
[et-keyboard]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/gui/epicGraphicalTree.m:240
[et-single-plot]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/gui/singleEpoch.m:168
[et-lazy]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:4094
[et-overlay]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/epicTreeGUI.m:750
[et-mean]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/epicTreeGUI.m:642
[et-stimulus]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:2181
[et-analysis]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:2996
[et-map-streams]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/field_mapper.py:279
[et-export-mat]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/export_mat.py:50
[et-export-selected]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/epicTreeGUI.m:563
[et-ugm-save]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:1392
[et-ugm-load]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:1451
[et-ugm-read]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/import_ugm.py:15
[et-response-matrix]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/tree/epicTreeTools.m:3927
[rw-import]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/recording_workspace.py:68
[rw-query]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/recording_workspace.py:286
[rw-tree]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_recipes.py:162
[rw-curation]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_curation.py:172
[rw-trace]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_service.py:364
[rw-masks]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_api.py:237
[rw-recipes]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_recipes.py:99
[rw-export]: /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python/workspace_api.py:326
