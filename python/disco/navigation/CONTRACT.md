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
