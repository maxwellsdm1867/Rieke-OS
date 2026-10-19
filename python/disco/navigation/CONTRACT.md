# Navigation contract

These named modules retain their existing interfaces and authority.

| Task | Start here |
| --- | --- |
| Validate/evaluate bounded typed source predicates | [predicates.py](predicates.py) |
| Discover metadata and form typed grouping keys | [tree.py](tree.py) |
| Preview exact source membership and inspect anchored epochs | [matching_epochs.py](matching_epochs.py) |
| Resolve ordered native tag membership and cell inheritance | [native_tag_filter.py](native_tag_filter.py) |
| Compose protocol-scoped annotation predicates | [tag_predicates.py](tag_predicates.py) |
| Save versioned query methods and last-run metadata | [search_presets.py](search_presets.py) |
| Save a versioned protocol arrangement | [tree_layouts.py](tree_layouts.py) |
| Read bounded revision-checked pages and anchors | [tree_pages.py](tree_pages.py) |

Predicates distinguish missing from null, Boolean from numeric values, and exact
numeric equality. Validation bounds literal depth, predicate depth, node count
and choices. Unknown fields and unsupported operators fail closed. Grouping uses
opaque escaped field names and exact typed ordering; it does not select membership
or read waveforms. Scalar built-in groupings treat both `None` and absence as
the legacy missing branch; dynamic explicit null and joint component presence
remain distinct. Saved methods and layouts retain optimistic versions and do
not replace immutable applied-query, source or native revision authority.

Tree pages retain captured WorkspaceService/ExplorerHistory method identity,
structural-reader checks, override fallback, graph budgets and response-end
attestation. Do not recreate classes or move captures. The cross-authority
[protocol-state owner](../../workspace_protocol_state.py) stays flat; exact types,
method checks, selected-membership proof and transaction/response scopes matter.
Native filter suggestions deliberately import native_tag_lookup inside the
operation. Keep annotation locks and caller database/registration lock ownership.

From the repository root, this existing public suite exercises pure typed
predicate and tree-catalog outcomes without SQL or scientific libraries:

```sh
PYTHONPATH=python python3 -B -m unittest -v disco.navigation.tests.test_workspace_predicates
```

Its truth tables cover missing/null, Boolean/number discrimination, nested
composition, choice bounds and resource refusal. This is not permission to run
central tree canonical-sort or native-filter suites: they import service/scientific
fixtures. Native triggers, HTTP, H5, trace/export and application qualification
remain deferred. Relocation changes source witnesses where source bytes change;
no cache identity or performance preservation is claimed.

Frozen workbench services may supply `tree_annotation_coverage(rows)` for exact
branch/ancestor buckets. TreePages forwards its display-only shared-tag counts;
it does not derive membership or approval. Ordinary navigation omits this field.
See the [workbench coverage contract](../workbench/CONTRACT.md#frozen-tree-tag-coverage).


Paged browsing opts into strictly boolean `counts_only: true`. Root, selection,
branch and ancestor summaries then contain epoch counts, with group totals in
`total`; full-bucket duration, distinct-cell and shared-tag coverage scans are
skipped. Legacy requests retain their full response. Mode-specific group caches
remain bounded; revisions, membership, labels and authority fences are unchanged.
The existing representative-only label renderer is retained. Live ancestor JSON
keys include the request mode, so full and count-only responses cannot collide.

`TreePages.selection(body, expected_count)` resolves one full split projection
and returns at most 1,000 exact UUIDs in the same typed DFS/leaf order as paging.
`column_pages(body, ancestor_offsets)` reuses one target projection for ancestor
prefixes within a caller-guarded response. Neither operation creates a cross-request
cache or authority lease. Canonical page/scope method identity is required; custom
overrides retain independent page calls. Ordinary `page` keeps its validation,
projection and return shape. Workbench retains opening and closing checks.
Executable equivalence and custom-reader examples are in
`python/tests/test_workspace_tree_pages.py`; frozen rejection tests remain in
`python/tests/test_workspace_workbench.py`.

Live `/tree-pages` accepts opt-in boolean `include_ancestors` and at most eight
null/integer `ancestor_offsets` in 0..10,000,000. Each page retains its 100-row
maximum. Eligible canonical witnessed reads advertise `tree_column_pages`; a
requested bundle uses `column_pages` inside the same opening/closing generation,
annotation locks and response-contract scope, attaching one identity to all pages.
Source, filtered, annotation/joint, unverifiable or overridden-pager live bundles
fail closed; ordinary reads retain their prior behavior and no generic retry
silently changes authority. Frozen custom-reader fallback is unchanged. Capability
is an optimization advertisement, not a lease. Tests in
`test_workspace_tree_read_identity.py` cover complete page equivalence, bounded
options, custom/ineligible rejection and closing-generation discard.

Catalog-known recorded `metadata/` split fields also qualify for the same live
response witness and batch, alongside built-ins, parameters and properties.
DiskMetadataIndex's sealed generation and source checks cover their recorded
projection; annotation-scope and joint/component fields remain excluded. This
adds no renderer cache permission: metadata parent bodies still fail the existing
reusableTreeBody admission policy and use fresh bundles even with retained geometry.

## Protocol-local navigation dependencies

Tree navigation may also reuse the exact owned Workbench frozen reader when the
requested protocol matches its header and canonical service methods are intact.
The frozen header includes a read-scope identity distinguishing pending membership
and selected views. Projection storage belongs to that frozen input; fresh service
adapters attach to it without retaining their context or annotation closures.
This is an explicit tree-only admission: `_structural_contract(service)` without
a frozen protocol still refuses that adapter for native typed/binding authority.
Custom policy, annotation filters and source-wide requests retain their existing
fallback. Cached computation never grants permission to publish a Workbench read.

An empty annotation-field snapshot returns the existing empty v1 evidence and
revision without reading definitions, fingerprints or registered rows. Nonempty
annotation snapshots retain their complete persisted evidence semantics.

An eligible protocol tree caches dependency fingerprints only for its complete
effective membership, including members hidden by ordinary filters. A warm hit
checks that cohort and one immutable binding header; it does not enumerate or
copy project-wide fingerprints. Cold scopes obtain the native frozen recipe.
Unbound membership order is still compared explicitly, member metadata changes
invalidate the projection, and custom readers retain their existing fallback.
The grouping reservation is proportional to scoped rows, bounded by the existing
cap. All retained dependency fingerprints count against the same cache budget.

Source discovery retains its project-wide witness while any source projection
remains cached. Source and protocol projections share the same 64 MiB, eight-entry
and two-million-value budgets; switching between them does not itself evict a
useful projection. LRU eviction charges the shared source witness once and releases
it with the last source entry. Protocol-only caches allocate no project witness,
and protocol hits never scan or compare it. An oversized source witness bypasses
source retention without discarding useful protocol projections.

Source requests compare the complete project witness and discard stale source
entries; protocol requests still validate their complete effective cohorts.
Published index/row generations invalidate all projections. Signature checks and
response-end authority fences are unchanged. This is O(membership) protocol
freshness and O(project) source freshness, not an unmaintained constant-time
revision promise. No metadata, recipe, tags, selection order or mutation
preconditions change.

The protocol-isolation, hidden-member filter, immutable-binding and file-change
cases are in `python/tests/test_workspace_tree_navigation_cache.py`.

## Exact persisted query literals

Saved preset predicates, version recipes and last-run results use the narrowly
admitted `workspace_authored_json.write_row` path. On canonical DataJoint tables,
it builds one typed JSON expression per field, preserving finite binary64 values
before the first write, then checks exact readback inside the caller's existing
transaction. Complete primary keys and declared plain scalar/JSON schemas are
required. Custom writers still run their own write methods and must preserve the
same exact JSON on readback. Failed readback rolls back with the surrounding audit.
No acquisition ULP allowance applies to authored predicates; query equality,
canonical query keys, version checks and live membership semantics are unchanged.
The shared expression's explicit depth/extra-parameter bounds fail before writing;
large float-free membership payloads retain the existing packet-size contract.

`python/tests/test_workspace_authored_json.py` exercises public preset save/read,
update/version, exact equality membership and lossy custom-writer rollback.
Native MySQL 8.4.2 API evidence is retained in the October 9 conversion audit;
these focused tests alone do not qualify native SQL or another database runtime.

## Predicate inspection trace descriptors

`POST /explore/epochs` includes each bounded row's recorded `streams` descriptors,
including an empty list when no streams exist, just as protocol inspection pages
do. These locators let the shared viewer fetch waveform samples independently of
Live metadata. Page construction does not load full epoch details or read H5;
waveforms retain the existing lazy trace endpoint and source checks. Predicate
membership, chronological paging, anchors and preview revision checks are unchanged.
Backend coverage lives in `test_workspace_matching_epochs.py`; shared-viewer
navigation and metadata-toggle coverage lives in `traceSurfaceIntegration.test.js`.

## Cell identity presentation

Cell-level tree branches carry optional recorded `cell_type` from the existing
representative rows. Paged branches and ancestors forward this display metadata.
No new lookup, scope scan, summary request or membership authority is introduced.
Other grouping levels do not gain cell identity metadata.

## Search predicate paths

Predicate meaning is unchanged; these are cost rules for the same results.

- **Tag states per generation.** `TagPredicates` keeps tag states and evidence
  per verified state generation, keyed by the predicate-catalog witness
  (`service._annotation_catalog_generation`: StateGenerationAuthority tokens for
  the shared scope and each referenced protocol's curation scope, native reader
  identities, publication, index/typed generations, source scope and row/cell
  identities). Tag-time fields use the shared token: their time rows are written
  in the same transaction as their tags. A hit reads only those tokens. A memo is
  stored only when the witness is unchanged after the build; an unavailable or
  replaced reader/authority recomputes exactly as before. Callers receive
  read-only state lookups and an independent deep copy of the evidence.
- **Per-value leaves.** A tag leaf is evaluated once per distinct saved tag array
  (plus once for the empty array), not once per epoch; set algebra combines them
  over the eligible universe. Shared states are built only for epochs with a
  direct record or a recorded cell. Evidence revisions stay byte-identical; the
  publication keeps the cell-link hash state so a shared write does not re-sort
  every epoch link.
- **Tag times.** With a time table, matches come from the per-tag time rows (cached
  per shared token). Without one, chips are read from scoped annotation records
  (approximate update time), never by hydrating every epoch.
- **Whole-catalog scope.** `WorkspaceService` keeps the unfiltered active-source
  rows in tree order per publication and source scope. Its ID tuple proves a scope
  is the whole eligible catalog: the typed reader then selects by source instead
  of admitting each identity, the native index matches without a scratch scope,
  and sparse tag results are ordered by the tree key instead of scanning every
  ID. A replaced `_filter_rows` policy still decides eligibility itself.
- **Catalog fields and summaries.** Annotation catalog fields and native summary
  buckets for tag fields come from the generation's distinct tag arrays (counts
  and first occurrence in scope order), with output identical to the shared
  index and the per-epoch construction. Protocol tag states read only saved
  decisions (`CurationStore.saved_states`); an absent epoch has the default
  state. Text whose JSON spelling could differ between Python and SQLite is
  answered by the shared index itself.
- **Shared writes.** The latest entry for a field set is patched from the shared
  change feed when the publication, protocol tokens and fields are unchanged,
  the entry carries the exact shared token it was built at, and the feed
  returns every changed record up to the current witness (at most 1000).
  Changed records are re-read by key and validated; affected epochs are
  recomputed and the evidence revision is rebuilt. Otherwise the entry is
  rebuilt; a witness that changes during the patch stores nothing.
- **Summary polls.** A pending poll is a status read and never waits behind the
  worker (which fences before and after calculating); it fences early only when
  the database lock is free. Ready results are always fenced.

Coverage: `python/tests/test_workspace_predicate_paths.py`.
