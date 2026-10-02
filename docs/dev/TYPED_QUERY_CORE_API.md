# Typed query core integration contract

Implemented in `python/workspace_typed_index.py` and `python/workspace_typed_query.py`
on the approved current-pipeline snapshot. This ports the full typed sidecar,
ID/rank-first paging, structurally scoped requested facets and correlated
EXISTS/NOT EXISTS membership from the October 1 experiments. It adds no dependency
and edits none of the existing catalog, tree, service/API or React modules.

## Construction and opening

```python
from workspace_typed_index import build, TypedMetadataIndex, QueryCancelled

receipt = build(source_db, target_db,
    max_seconds=300, min_free_gib=4, max_rss_gib=1,
    progress=None, expected_generation=None, expected_project_uuid=None,
    cancel_check=None)

reader = TypedMetadataIndex(target_db, source_path=None,
    expected_generation=None, expected_project_uuid=None, cancel_check=None)
worker = TypedMetadataIndex.open_verified(reader, cancel_check=event.is_set)
```

`source_db` must be the caller-verified, sealed, immutable **native metadata index**.
The native lifecycle owner must retain its reader lease while a typed reader is
open. Neither method performs native full-file SHA verification or creates that
lease: those remain mandatory service/lifecycle responsibilities. The constructor
does fully verify the typed sidecar's SHA seal by default. Construction writes only
a fresh sidecar and its `.sha256.json` seal; it does not publish it. Failures retain
an unsealed partial asset, which must not be published or opened.

`open_verified()` takes an existing live typed reader, not user-supplied signatures.
It creates an independent SQLite connection on the calling thread without hashing
the sidecar again. Source, sidecar and seal identities are checked before and after
opening against that reader's verified signatures. Each reader is thread-confined;
retain the original verified reader during clone creation. Do not interleave other
queries while a membership iterator is active on the same reader.

## Queries and outputs

```python
reader.field_registry()
# {fields: complete native definitions with observed types, operators,
#  predicate_version, limits, generation_token}; no distributions/choices

reader.count(predicate=None, scope=None)  # exact integer
reader.page(predicate=None, scope=None, cursor=None, limit=60)
# {rows: at most limit native DTOs, cursor: rank or None}

reader.summaries(predicate=None, scope=None, facet_fields=())
# {count: exact integer, facets: {field_id: summary}}; no row/detail decoding

reader.preview(predicate=None, scope=None, facet_fields=(), limit=60, cursor=None)
# {count, facets, rows, cursor}

reader.iter_membership(predicate=None, scope=None)  # chronological UUID iterator
reader.membership(predicate=None, scope=None)       # explicit eager compatibility
reader.groups(kind='cell', predicate=None, scope=None, cursor=None, limit=60)
# {groups: [{uuid, count}], cursor}; kind is cell or block
reader.detail(epoch_uuid)  # full detail via the unchanged native Decoder
reader.explain(predicate=None, scope=None)  # SQLite query-plan rows
```

Facets are keyed by native field ID and return `values: [{value, type, count}]`,
`present_count`, `missing_count`, and `values_truncated`. At most 60 distinct values
are returned, ordered by their first chronological occurrence. There is no
dataset-specific 140-field cap. Complete catalog/suggestion/layout computation
remains a different operation owned by the catalog worker; these facets do not
replace its derived joint fields.

Native `workspace_predicates.validate` and `matches` retain type, array,
missing/null and validation-error semantics. Build-time actual-value representatives
avoid decoding every UUID to validate a predicate. Direct core-field shortcuts
are enabled only after proving equality/presence/string kinds across the native
generation. Detail tables and original raw values remain in one read-only base.

## Conjunctive scope and application adapters

```python
scope = {
    'cell': recorded_cell_uuid,       # optional
    'block': recorded_block_uuid,     # optional
    'group': recorded_group_uuid,     # optional
    'protocol': acquisition_name,     # optional; not protocol-workspace UUID
    'sources': eligible_source_shas,  # optional iterable; empty means no sources
    'epoch_ids': frozen_uuid_iterator,# optional iterable; empty means no epochs
}
```

Every supplied entry is conjunctive. Sources are matched to authoritative native
`epochs.source_sha`. `epoch_ids` and sources stream through `executemany` into
disk-backed TEMP relations; duplicates are ignored and foreign IDs do not match.
No input iterable is materialized as a Python list. A direct UUID iterable may
also be supplied as `scope` for explicit frozen membership, but the dictionary
form allows combining it with structural scope and eligibility.

The **service adapter** owns protocol-workspace UUID/binding resolution, source
eligibility, existing filter-policy semantics, shared/inherited/direct annotations,
curation and generation authority. Translate scientific filters to the validated
predicate; compose workspace query membership with it, or supply an authoritative
frozen UUID iterator. Never substitute acquisition `protocol` for frozen
protocol-workspace membership. TEMP population is still work proportional to the
explicit universe: streaming removes a Python-list allocation, not that SQL cost.
Use reusable generation-bound adapters rather than repopulating huge scopes on
every ordinary action where an authoritative indexed alternative exists.

`generation`, `project_uuid`, and the opaque `generation_token` are exposed on the
reader. Public cursors must bind backend ranks to this token, canonical predicate,
scope, query policy and relevant annotation generation. Integer backend ranks are
not safe public cursors by themselves. The core checks file/signature changes
before and after queries; service code must separately fence native source and
annotation authority before response publication. Group queries contain nonempty
members only; the native hierarchy adapter must preserve empty branches.

## Cancellation and verification

`reader.cancel()` is safe to invoke from another thread and calls SQLite interrupt.
`set_cancel_callback(event.is_set)` installs cooperative SQL-progress checks;
`reset_cancel()` clears the reader's own cancellation flag. Clear any external
event separately. Cancellation raises `QueryCancelled`, never an empty-success
result. Use independent worker-owned readers for async operations. Build cancellation
uses `cancel_check` and raises a resource/cancellation `RuntimeError`; resource
limits and default verification remain enabled.

Focused tests use only newly created temporary metadata fixtures and independent
native values. They cover predicate/validation parity, mixed types and arrays,
null/missing, exact DTOs, all pages, groups, eligibility/frozen membership, native
details, requested facets, more than 140 discovered fields, seal/generation faults,
verified clone reuse, cancellation and interrupted-build behavior. They do not
qualify full million-row UI/HTTP/tagging behavior or replace the handoff scale and
storage gates.
