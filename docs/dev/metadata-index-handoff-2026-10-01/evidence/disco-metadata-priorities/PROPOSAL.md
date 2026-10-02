# Metadata priorities and lazy scientific detail

2026-10-01. Research and draft field policy only; no app, source database, annotations, dependency version, or query behavior changed. The one-million experiment has completed. This proposal uses its real metadata inventory and official database documentation.

The app should offer a small, fast scientific selection model and fetch complete scientific detail for the operation that needs it. A field's scientific importance, frequency of filtering, indexing, default display, and default aggregation are different decisions. Preserve all source information. Compute only requested summaries in the active scope.

## Scientific model

| Role | Proposed examples | Read/query behavior |
|---|---|---|
| Identity and navigation | Stable source/experiment/cell/group/block/epoch keys, cell label/type, recording date/time, protocol | Small page projection with indexed relationships and stable ordering; labels/type never replace identity |
| Common experimental selection | Bath temperature, recording technique, explicit clamp mode, pipette/amplifier offsets, internal/external additions, pipette solution, scoped tags | Fast condition queries when the actual values are available; keep ownership, units and acquisition context |
| Protocol-specific selection | Visual intensity/contrast/spot size/position; current mean/SD/frequency cutoff; history/target settings/control/segment duration | Active protocol presets choose relevant fields and indexes; users can pin additional fields |
| Reconstruction dependencies | Full parameters, exact seeds/timing, generator identity/version, device state/calibration, frame geometry, refresh/sample rates, recorded timing/data references | Load the full protocol dependency bundle when reconstructing/inspecting a stimulus; no default aggregation merely because the field is essential |
| Other inspection/provenance | Rig, institution, notes, rendering settings, detailed frame arrays | Fetch selected detail or requested columns; preserve advanced queries for all 140 currently eligible fields |

The roles overlap. Frame size or rig calibration can be indispensable for a visual reconstruction even when rarely used to select epochs. Seeds can be useful filters for repeated stimuli. A saved protocol preset should be able to promote these fields without a new source format. A protocol dependency manifest must determine reconstruction requirements; this draft's field-name heuristics are not a complete reconstruction specification.

The user confirmed that the offset example means **pipette/amplifier offsets**. The observed `parameters/centerOffset` is a visual position offset and must remain a separate concept. Recording technique (for example, a method of recording) and electrical clamp mode may also be different concepts. Numeric protocol `controlMode` must not be interpreted as current/voltage clamp from its name or observed 0/1 values.

## What exists in the actual mounted cache

The inventory contains 2,781 real epochs, 140 stored eligible query fields, and 340 decoded detail leaf paths. Draft classification covers every query field exactly once: **9 common navigation paths, 7 common scientific paths, 41 protocol-specific paths, and 83 on-demand paths**. These are source-path counts, not distinct concepts: many epoch and block parameter paths overlap. The normal bounded row's existing display labels/source references remain useful even when a duplicate raw label path is on demand.

Common navigation paths: `epoch`, `date`, `cell`, `block`, `block time`, `cell type`, `group label`, `group`, `protocol`. Preserve source revision/experiment and other recorded ancestry links beyond these nine UI field IDs.

Common scientific paths:

- `properties/bathTemperature`
- `metadata/cell/properties/type`
- `metadata/group/properties/externalSolutionAdditions`
- `metadata/group/properties/internalSolutionAdditions`
- `metadata/group/properties/pipetteSolution`
- `metadata/group/properties/recordingTechnique`
- `metadata/group/properties/seriesResistanceCompensation`

The last field is an amplifier compensation setting, not a measured series-resistance value. Recorded type and a scientist's curated cell classification must retain their provenance.

Actual cache evidence:

- Bath temperature is populated and has 36 distinct values. It belongs to epoch properties and must not be assumed constant for a whole cell.
- `recordingTechnique`, internal solution additions and pipette solution are null throughout this mounted cache. External additions is the literal string `[]` (not a JSON array or null), and series-resistance compensation is integer `0` throughout. Preserve those different states. The scientific priority of all these fields remains high; this sample does not establish performance across diverse populated-condition values.
- No pipette/amplifier-offset field was identified in either this 140-field index or the 340-path cached detail inventory. This does not establish that the original acquisition/device records lack it. Audit the source reader and recorded device state before deciding whether ingestion/backfill is needed. Do not synthesize a value or substitute visual offset.
- Visual `centerOffset` has 14 distinct recorded values. Rig is one repeated value here; this supports a lower default summary priority, not permanently disabling rig queries.
- Existing `workspace_tree.py` already has protocol grouping presets and a technical-field list. That is a useful starting point, but it currently classifies center offset, control mode, gains and seeds mostly through presentation rules. It does not implement independent indexing/loading/facet policies. Scientific dependency/meaning must take precedence over blanket field-name rules.

## Why linked schemas help

DataJoint dependencies retain linked entity keys; projection selects columns while keeping keys; restriction selects matching entities. We can filter through relevant parent context and return a bounded epoch projection without retrieving every related attribute. This is the design principle to reuse, rather than a reason to migrate engines or assume every linked table must be read. [DataJoint dependencies](https://docs.datajoint.com/python-0.x/0.14/design/tables/dependencies/), [query operators](https://docs.datajoint.com/reference/operators/)

Keep cell properties at the cell, group solution context at its recorded group, common block settings at the block, and per-epoch temperature/parameters/overrides at the epoch. Existing immutable ancestor objects already avoid repeating full parent detail. A compact query projection may deliberately copy selected resolved values for speed, with explicit provenance and generation binding. Avoid copying every field into every default page.

Do not silently merge `parameters/spotIntensity` with `metadata/block/parameters/spotIntensity`. The former may describe a realized epoch while the latter describes a block setting. Alias equivalence, override precedence, explicit-null treatment and ownership must be proven from acquisition semantics. Follow exact keys through the recorded hierarchy; similar labels never establish identity. The hierarchy can coexist with other dependency links, such as device state and stimulus generator configuration.

## Proposed query routes

1. **Field registry:** Return names, recorded types, source paths, ownership, scientific role, unit status and protocol presets. No epoch scan or value distribution is required just to list available fields.
2. **Browse:** Return a bounded header page with stable cursor, core identity and selected columns. Load hierarchy children by indexed parent keys. Do not construct a Python list of every full metadata row first.
3. **Filter:** Evaluate identity/condition/protocol/tag criteria on the server through priority indexes and appropriate owners. Return the same matched epoch IDs as the general path. Cold fields remain available via advanced queries; filtering only the visible page is incorrect.
4. **Requested summaries:** Request value counts/ranges only for active dropdowns or grouping fields in the selected scope. Compute exact total counts separately when expensive. Show pending state rather than blocking the first visible page. An all-field catalog remains an explicit exact operation, not an implicit cost on every click.
5. **Inspection/reconstruction:** Fetch complete selected-epoch metadata and required ancestor/device/generator/calibration/timing/data references together, preserving raw values and source revision. Request only selected metadata columns in bulk when a table adds an extra column.

These are proposed service responsibilities, not newly shipped endpoints. Selecting fewer field names alone cannot fix the eager million-row JSON load: the implementation must actually avoid those reads and all-field aggregations.

SQLite covering indexes support narrow queries without fetching the main row. Multi-column index order should follow observed predicates and ordering. Partial indexes can limit optional-row indexing, but the generated predicate must match the index's eligibility rules. These patterns support the proposal; they do not predict a measured speedup or justify indexing every combination. [SQLite query planning](https://www.sqlite.org/queryplanner.html), [partial indexes](https://www.sqlite.org/partialindex.html)

The DataJoint fetch specification also distinguishes selected columns, bounded output and cursor iteration from loading everything into a list. Streaming all rows and returning just a page are different operations. Current documentation describes 2.x APIs; the app need not upgrade to use the design idea. [DataJoint fetch specification](https://docs.datajoint.com/reference/specs/fetch-api/)

## Tags and cache behavior

Keep the existing annotation model separate from immutable recording metadata. Shared cell tags inherit through cell UUIDs; shared epoch tags are direct; protocol/dataset curation is separate. Query the existing scoped annotation index, then combine it with scientific membership. Do not copy every cell tag into all descendant epoch records, or rebuild the recording projection for a tag edit. New group/block tag behavior is not implied by this proposal.

Metadata cache keys include source generation, field/projection policy version, query/scope, requested columns/summary fields, and relevant source eligibility. Tag-dependent queries also include annotation generation and protocol/dataset scope. Reclassifying a cell changes tag-dependent selections, not the original recorded cell identity/type. Parent context changes invalidate affected resolved projections.

Not fetched, fetched and absent, and fetched with explicit null remain distinct. An unloaded value cannot satisfy a missing-field predicate. Unavailable scientific input cannot become a default numeric zero. Show whether a summary is pending/stale; never substitute an unfiltered cached count for a filtered count.

## What the measurements do and do not establish

The completed million-epoch real-record replay demonstrated:

- Bounded global count/first-60 page: 13.22 s on the current query path versus 18.25 ms with the compact typed model.
- Selected-cell count/first-60/two summaries: 13.58 s versus 4.13 ms after fixing the scope's join order.
- Complete selected-cell 141-field catalog: 25.59 s versus 133.93 ms with the previously tested batching query, with identical output.
- Broad scientific filters still take about 0.8–2.3 s; global requested summaries about 3.2 s. The original uncached global full catalog hit the 1 GiB guard while loading wide rows.

This suggests that avoiding unnecessary broad reads and summaries matters at least as much as field ranking. A narrow priority index may reduce duplicate projections and accelerate scientific queries, but we have not measured its new build/storage/query costs yet. The existing 1.107 GB typed projection took 50.57 s for extraction/ranking/indexing and 218.51 s with validation. Much of that cost comes from one million core identities and their indexes; dropping cold field summaries does not eliminate it. Retaining full canonical data also does not automatically shrink the native 7.20 GB cache.

The replay repeats scientific cardinalities. It does not qualify new clamp/offset/solution values, full app UI timings, dense tag workloads, native H5 reconstruction or one million independent acquisitions.

## Next bounded evaluation

Reuse the sealed corpus and existing oracle. Compare the current native path, complete typed candidate and a priority projection. Keep all nine everyday actions visible, with explicit gaps.

- Record first visible page separately from exact count, requested summaries and full catalog.
- Test combinations actually requested: cell type + protocol, epoch bath-temperature ranges, scoped tags + experimental conditions, and protocol-specific stimulus settings. Use only actual recorded values; absent clamp/offset/solution values remain a coverage gap.
- Compare exact matched IDs, cursors, values, null/missing states and advanced queries on deferred fields. Keep raw detail and reconstruction dependencies byte/semantic equivalent; verify recorded stimulus data against reconstruction when dependencies are available.
- Measure build time, added storage, peak memory, cold/warm queries, tag edit/invalidation cost and rare-field first-use behavior. Preserve the previous measurements and report regressions.

The draft is a reviewable field policy, not a production whitelist. `FIELD-LIST.md` and `draft-field-policy.json` record all 140 source paths, actual presence/null/missing/type/cardinality evidence and tentative protocol packs. `primary-source-notes.md` contains the documentation review.
