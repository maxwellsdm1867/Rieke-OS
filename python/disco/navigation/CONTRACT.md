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
remain distinct. Predicate contract version 2 applies the same meaning to
predicates, the typed index and joint keys: a built-in field (`BASE_FIELDS`)
recorded as `None` is absent, so `missing`/`exists`/`ne`/`not_in`/`is_null` count it
exactly as the tree's "Not recorded" branch; recorded dynamic nulls stay values.
Stored version-1 work whose result could differ (`reinterpretation_required`) is
never reinterpreted: saved selections refuse "Check for updates" and export reuse
until their search is re-run; import suggestions and source-eligibility propagation
skip them with the visible reason "Saved selection uses the old 'missing' meaning;
re-run it."; old-contract search-preset runs are reported as superseded instead of
current. Frozen export snapshots of source predicates record
`predicate_contract_version`; reuse refuses an older affected contract. The change rebuilds disposable metadata indexes once. Saved methods and layouts retain optimistic versions and do
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

Native refresh prepares the metadata-derived tag witnesses before exposing its
new frozen publication: the exact fingerprint-universe digest, registered cell
links hash prefix, cell membership and per-source cardinalities. Requests reuse
these structures only while both captured immutable maps are the same objects;
a mutable/custom publication keeps the conservative fallback. Canonical evidence
bytes and live annotation-generation checks are unchanged. Mixed-query run totals
use exact source cardinalities instead of constructing sorted eligible rows.
Preparation is publication work, recorded separately from request timing by the
route fixture; it is not a claim that import/startup became constant-time.

## Counted previews and publication revisions

A project-scope predicate tree over a frozen publication (`publication_serial`:
rows, cells, protocols and fingerprints are deep-frozen and every republish
advances the serial) is identified by version-2 `selection_revision`:
predicate, filters, splits, annotation evidence, source scope and the
publication identity (serial, native index generation, typed generation). No
member is hashed. Frozen maps refuse in-place mutation, so an unchanged
identity proves unchanged membership. Shared-tag filters, replaced membership
policies, non-canonical indexes and unfrozen adapters keep the version-1
membership hash. Protocol trees are unchanged.

`POST /api/explore/preview` with `summary_only: true`, `catalog_summary: false`
and no `baseline_revision_uuid`/`focused_uuid` is counted: one typed `COUNT`
over the active sources (the whole typed table when no source is excluded; the eligible total is memoized per publication and
source scope) and the version-2 revision, with no ID collection or membership
list. Annotation predicates and anything else outside that contract use the
exact path. Results that freeze membership (run, revisions, exports, baseline
diffs) keep the exact membership. Coverage:
`python/tests/test_workspace_counted_preview.py`.

## Query runs and inspection pages

Over a frozen publication with the typed index, a metadata predicate's query
run (`POST /api/explore/run` with `catalog_summary: false`) records its counts
without listing matches: the matched count (exact per-value sums for
single-field predicates, otherwise one typed `COUNT`), the distinct cell count
and the version-2 tree revision. Inspection pages (`POST /api/explore/epochs`)
first check the revision, then read one typed window ordered by the inspection
chronology `chronology_rank` (date, time of day of `start_time`, UUID: exactly
`tree_pages._chronology`), with the total, anchor position (a count of earlier
matches) and the cell list (per-cell counts in order of first appearance)
computed in SQL. A single-field predicate (any AND/OR/NOT over one field, at most
20,000 distinct values) takes its total, cell list and distinct-cell count from
sealed per-(field, value), per-(field, value, cell) and per-(field, cell missing)
aggregates (O(values x cells), never O(matches)). Totals and cell lists are kept
per (revision, predicate, cell filter); later pages are keyset seeks from the
previous page's last inspection rank (O(page)). Results equal the exact scope reader; annotation predicates,
unfrozen adapters and replaced policies use the exact path. A run does not
freeze membership; revisions and exports keep exact membership. Coverage:
`python/tests/test_workspace_query_run.py`.

### Pending counts and the paged cell list

A multi-field predicate's run and pages answer at once without its totals:
`matched_count`/`total`, `last_run.epoch_count`/`cell_count` and the page cell
list are `null`, with `counts: {status: "pending", request_id}` (and
`cells_pending: true` on pages that asked for cells). One server-owned job per
(revision, predicate) counts them exactly on the summary worker under the same
generation fence; `GET /api/explore/summaries/<request_id>` returns
`{matched_count, cell_count}` when ready, and later pages then carry the exact
total and cell list with `counts.status: "ready"`. `has_more` is always exact
(one extra row is read). Single-field predicates answer their counts at once.

`POST /api/explore/epochs` pages the cell list with `cells_limit` (1–1000) and
`cells_after` (cells already received, default 0): the response carries `cells`
(that window, in first-appearance order), `cells_total` and `cells_next` (the
next `cells_after`, or `null` at the end). Without `cells_limit` the full list
is returned as before.

### Predicates with annotation leaves

Runs and inspection pages of predicates with tag leaves (protocol curation
tags, shared/effective tags, tag times, alone or with metadata leaves) take the
match from the generation's tag states (`match_predicate` over the cached
eligible universe). The tree revision binds the annotation evidence revision and
the frozen publication. Per revision the matches are kept once in inspection
chronology with their cell list: totals are sizes, pages are slices, anchors and
cell filters index the kept list. Results equal the exact scope reader
(`python/tests/test_workspace_query_run.py`).
Predicates mixing tag leaves with recorded-metadata leaves answer runs and pages
at once like other multi-field predicates: pages walk the eligible inspection
chronology in bounded chunks matched by the canonical matcher (tag leaves from
the tag states, metadata leaves from the typed index over the chunk) and resume
from each page's kept position; totals and the cell list come from a pending
counts job that runs the full match.

## Background mixed-query counts

`TagPredicates.snapshot_matcher` captures the validated AST, frozen row mapping,
copy-on-write tag-state entry and validated canonical tag-time records while the
caller holds the database lock. Its evaluator uses only these inputs and a leased
worker-owned typed reader; it never calls live annotation or service readers. The
live and captured paths share exact Boolean set semantics and metadata validation.
Custom time stores without the canonical time table retain the conservative live
locked fallback; display chip timestamps are not substituted for recorded times.

Mixed-count jobs release the navigation lock before broad membership evaluation,
chronology sorting and distinct-cell counting. Existing SummaryJobs opening and
closing generation fences remain required; source/tag mutation or cancellation
cannot publish a result. See test_workspace_query_run's held-worker navigation,
source-staleness and exact tag/time/source-scope parity checks.

`tag_predicates.prepare_publication` lazily imports the retained
`workspace_service.publication_serial` witness to admit only the canonical frozen
read model before precomputing metadata-derived tag lookup maps. This narrow
reverse dependency reuses the existing publication proof; it neither constructs a
second authority token nor changes mutable/custom fallback admission.
The named `prepare_publication(service)` entry is public for the retained service
and its synthetic route fixture; `_Publication` remains private. Regression tests
observe the returned prepared witness rather than importing its private class.

Mixed result pages seek the sealed typed index's inspection-chronology ranks in
bounded windows. Their continuation is the last accepted rank; cell pages add
the direct cell scope before seeking. Active-source eligibility is checked within
each window, preserving exact matches without constructing a project-wide UUID
list or sorting it on a first page. Explicit uncached offset/anchor searches may
visit preceding matches; sparse predicates may visit multiple windows.
