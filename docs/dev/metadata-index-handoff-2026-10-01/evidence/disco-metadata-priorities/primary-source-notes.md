# Metadata priorities: primary-source notes

Research date: 2026-10-01. Documentation review only; no app, repository, mounted database, or benchmark was modified. The proposals below are architectural inferences, not measured performance claims. Five official pages were reviewed. Current DataJoint documentation describes 2.x APIs; the dependency page is explicitly version 0.14. These support design principles without implying an upgrade of the existing app.

## What the documentation establishes

DataJoint foreign keys carry entity keys and enforce referential integrity. Dependencies connect scientific context rather than forcing the application to retrieve every related attribute for every interaction. Its dependency graph is a DAG, so the model need not be a single tree. Preserve the actual relationships when producing a browsing hierarchy. [DataJoint dependencies, version 0.14](https://docs.datajoint.com/python-0.x/0.14/design/tables/dependencies/)

DataJoint restriction selects matching entities; projection selects attributes while retaining primary keys; joins compose related entities. These operations support filtering through cell or block context and returning only the identifiers and fields needed by a browser page. Current documentation also distinguishes optional extension from joins that require matches. Inference: optional descriptive records must not silently remove epochs from results. [DataJoint query operators](https://docs.datajoint.com/reference/operators/)

The DataJoint 2.0+ fetch specification supports specific columns, explicit ordering and limits, and cursor-based streaming. It distinguishes a full list in memory from iteration over a database cursor. Inference: returning a bounded page and fetching detail only for selected records is compatible with the relational design. Streaming many records is still different from fetching only a page; neither automatically eliminates the cost of an exact global count or aggregation. Verify the installed version before adopting API examples. [DataJoint fetch specification](https://docs.datajoint.com/reference/specs/fetch-api/)

SQLite multi-column indexes support several AND-connected conditions. A covering index includes the search and return columns, avoiding access to the main table for that query. Index column order affects search and ordering. SQLite uses statistics from ANALYZE when choosing between indexes. Inference: design a few indexes around observed browsing/filter patterns, with stable ordering and a small returned payload; do not index every possible combination of 140 attributes. This documentation does not establish a speedup for our workload. [SQLite query planner](https://www.sqlite.org/queryplanner.html)

SQLite partial indexes contain a selected subset of rows and can reduce index size. The query condition must imply the index condition; SQLite recognizes only certain forms, so superficially equivalent expressions may not use the index. A partial index predicate cannot refer to other tables or bound parameters. Inference: optional typed scientific columns or an explicitly maintained priority-field table may use selective indexing, but the generated queries must expose eligible predicates and their plans must be inspected. [SQLite partial indexes](https://www.sqlite.org/partialindex.html)

## Proposed read design

Separate four choices for each field: preserve it, index it, display it by default, and compute its summary by default. Those choices should be independent. A field can remain fully queryable without appearing in every page or having a million-epoch distribution recalculated on every click.

Maintain a small, versioned field policy with semantic field ID, source path, owning entity, type/units, inheritance rule, scientific role, indexing preference, default display, and default facet preference. Proposed roles:

| Role | Initial candidates | Read behavior |
|---|---|---|
| Identity and navigation | Experiment/source, cell, group, block, epoch IDs; recording time; cell identity/type | Small typed projection and indexed relationships |
| Frequent scientific selection | Protocol, clamp mode, temperature, internal solution/additions, relevant offsets, requested tags | Typed indexes where supported; summaries only for requested fields and scope |
| Reconstruction | Complete protocol parameters, seed, timing, calibration/configuration and referenced scientific objects required by the protocol | Preserve full fidelity; load the complete dependency bundle when reconstructing or inspecting a stimulus |
| Other detail | Rarely filtered rig/configuration fields, large frame arrays, descriptive attributes | Retrieve on selection; retain advanced filtering through the general metadata path |

These categories are proposals based on the user's scientific intent. Importance is protocol-specific: a frame or rig/calibration field might be essential to reconstruction even if it is rarely used to select recordings. Indexing rarity must never determine whether scientific information is retained. Some reconstruction fields can also belong to the frequent-filter group.

Store cell-level context once per cell and block-level settings once per block, linked to epochs. If a read projection copies resolved values onto epochs for speed, record the owner and override rule; regenerate or invalidate affected descendants when parent context changes. Do not assume temperature or clamp settings are constant across a whole cell without inspecting the actual ownership and changes.

Keep tags as scoped assignments: entity kind, entity ID, tag ID and revision. Define whether a cell/block/group tag applies to descendant epochs, whether direct and inherited matches differ, and how conflicts are represented. The query route should implement these rules explicitly rather than expanding every parent tag into a million persistent copies by default.

## Query and UI contracts

- A page returns bounded rows and stable cursor ordering. The UI requests only the active facet fields. Exact counts and facet distributions can be separate responses so they do not delay the first page.
- A field registry can expose all known names/types without calculating all their value distributions. “Show all metadata” for one epoch is a detail read; “summarize all metadata for a million epochs” is a distinct, expensive action.
- Advanced predicates on rare fields must evaluate against stored data or a built index. Filtering only the visible page would give an incorrect answer. Unknown fields and unsupported operators need explicit errors.
- Preserve three states: not fetched yet, fetched and absent, and fetched with explicit null. An unloaded value is never evidence for an “is missing” filter.
- Cache keys include source generation, projection/policy version, query/scope, requested fields and relevant annotation revision. A source change invalidates source-dependent data; a tag edit invalidates tag-dependent membership/counts. Never publish a new projection before its validation and generation binding pass.
- Mark stale, pending, sampled or approximate summaries explicitly. A cached unfiltered count cannot substitute for a filtered count. Full exact catalogs remain available as explicit/background work rather than disappearing.

## Experiment to qualify the proposal

Compare the current million replay, the complete typed model, and a narrow priority projection using identical predicates and outputs. Measure bounded page latency separately from requested facets and exact counts; report storage, build time, peak memory, update/invalidation cost and advanced rare-field latency. Preserve all original everyday benchmark rows. Verify exact matched epoch IDs, inheritance/scoped tag semantics, null/missing behavior and lossless reconstruction data against the source. A narrow default workflow can improve perceived responsiveness without making every global analysis faster; measure both claims separately.
