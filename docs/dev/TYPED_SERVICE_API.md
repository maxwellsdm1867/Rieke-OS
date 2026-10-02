# Typed metadata service integration contract

This isolated integration keeps the native SQLite metadata/detail model, complete
discovered fields, recorded identities, source eligibility and annotation owners.
It adds a verified typed sidecar and additive HTTP operations. Backend experiment
timings are not UI SLOs. Existing preview, revision/save, run, catalog, tree,
epoch/detail and export response contracts remain available.

## Field definitions

`GET /api/explore/field-registry` takes no query parameters and returns:

```json
{
  "fields": [{"id":"parameters/example","label":"Example","category":"Parameters","path":"parameters.example","types":["number"],"types_scope":"registered_sources","operators":["eq","ne","in","not_in","gt","gte","lt","lte","exists","missing","is_null"]}],
  "tree_fields": [{"id":"cell","label":"Cell","category":"Recording","path":"cell_uuid"}],
  "operators": ["eq","ne","in","not_in","contains","gt","gte","lt","lte","exists","missing","is_null"],
  "predicate_version": 1,
  "generation": {},
  "source_scope": {},
  "summary_available": false
}
```

The example is schematic; every eligible discovered field is returned, with
available native grouping hints and definitions. Annotation fields keep their
explicit protocol/shared ownership and array/string element types. `tree_fields`
also retains structural and derived joint definitions. Joint components are
queried separately for summaries. No distributions, counts, choices or examples
are returned. Production reads publication-time schema/proofs; the no-index
fixture/general fallback may discover definitions from native values.

## Requested summaries and exact counts

`POST /api/explore/summaries` accepts a bounded JSON object:

```json
{
  "predicate": {"all":[]},
  "summary_fields": ["parameters/example"],
  "scope": {"cell_uuid":"00000000-0000-0000-0000-000000000001"},
  "filters": {},
  "generation": {}
}
```

`predicate` and `summary_fields` are required. Optional `protocol_uuid` identifies
an existing **workspace**, never an acquisition protocol label. Optional scope
keys are recorded `cell_uuid`, `block_uuid`, `group_uuid`; they are conjunctive.
Filters are the existing `epoch_uuid`, `cell_uuid`, `cell_type`, `group_label`,
`tag`, `tagged`, `tag_predicate` grammar. No epoch ID list is accepted.
`generation`, when supplied, is the latest exact registry token. Duplicate or
unknown summary fields and unsupported scope/filter fields are rejected.
`summary_fields: []` requests only an independently exact matched count.

Submission returns HTTP 202 with `request_id`, `status: pending`, the
**context-specific** `generation`, and `summary_fields`. Poll
`GET /api/explore/summaries/<request_id>`. Every retained status keeps that request
ID and context token. Status is `pending`, `ready`, `cancelled`, `stale` or `failed`.
Only ready supplies:

```json
{
  "result": {
    "matched_count": 1,
    "summaries": {
      "parameters/example": {
        "values": [{"value":0,"type":"number","count":1}],
        "present_count":1,
        "missing_count":0,
        "values_truncated":false
      }
    }
  }
}
```

Buckets retain native numeric/Boolean/array/null equality, exact counts and first
chronological occurrence order. At most 60 distinct buckets are returned; a
truncated result does not establish a distinct count. Unrequested or unavailable
summaries never mean zero. Empty matched scopes have exact zero counts and empty
buckets. `POST /api/explore/summaries/<request_id>/cancel` accepts `{}` and removes
any ready result as well as cancelling pending work. There is one aggregate
worker, at most eight retained requests, and a 2 MiB budget per ready result.
Terminal requests are evicted for admission; IDs expire across server restart.
Capacity refusal is HTTP 429. Registry-token mismatch is HTTP 409 with
`status: stale`, current registry generation and an error.

Metadata-only queries run on independent SQLite connections outside the native
database/navigation lock. SQL progress checks observe cancellation. Annotation
and unsupported/custom policy work retains the authoritative general path and
native serialization. That fallback can still block navigation and allocate
full membership; broad/million-scale annotation performance is **unqualified**.

## Bounded native row pages

`POST /api/explore/page` requires `predicate`, accepts the same protocol/filter/
structural context plus `limit` (1–100, default 60) and an opaque `cursor`. It
returns `{rows, cursor, generation, limit}`. Rows are unchanged native DTOs.
It deliberately does not compute counts or field distributions. Use a count-only
summary request when needed. The HMAC continuation binds native chronology rank,
canonical context and exact generation. General fallback cursors also bind exact
authoritative filtered membership. Query/generation mismatch is HTTP 409; altered
or malformed cursors are rejected. Direct rank integers are not public cursors.

This route does **not** supply the legacy MatchingEpochs tree revision, cell
aggregates, anchored/ordinal/previous pages or run attribution. It is not a safe
drop-in replacement for that component. No interim flat-results UX is approved.
The compatible follow-on must share row/cell/tree authority, preserve exact native
cell DTOs with bounded continuation, anchor/ordinal/previous navigation and
independent counts, and retain explicit run/save/export membership/attribution.
Legacy preview/run still materialize complete membership as their contracts
require; current ordinary UI row loading has not yet adopted the new route.

## Authority and lifecycle

Generation contains `metadata` (native index generation), `typed` (sidecar proof),
`source` (query eligibility), `annotation`, `publication` (session/publication
nonce), and optional-context `binding`. Registry/page common witnesses are
metadata/typed/source/publication. Protocol and annotation scopes may add different
binding/annotation witnesses. Submission compares the exact latest registry
token, then acknowledges its context token; later polls compare that acknowledged
token exactly. Never compare a registry token wholesale with a scoped job token.
Successful unchanged-index refresh also changes publication and discards cached
tree navigation references. Failed verification preserves old rows, typed owner,
cache and nonce, while the existing `_loaded` safety gate requires recovery.

New source queries exclude query-excluded source registrations. Protocol context
uses authoritative current/frozen workspace membership, including sources
excluded from **new** source queries, matching existing protocol tree behavior.
Frozen UUID membership is streamed into SQLite TEMP relations, not transported
in request ID lists. TEMP population and legacy recipe hydration are still work
proportional to the explicit frozen universe; no million-scale bound is claimed.

Sidecars are staged under `cache/typed-metadata`, built/opened against a fully
verified native index, verified before publication, and rechecked against source
signatures after construction. Native and typed reader leases retain old assets
while readers use them; obsolete assets use existing bounded reclamation. Failed
sidecar preparation never replaces published service state. Startup/build seal
verification is separately recorded in refresh metrics, not warm query time.
Thread-owned `open_verified` readers reuse a live proof without rehashing the
entire sidecar. Source/annotation authority is fenced before and after results.

## Isolated qualification seam

Use the existing `test_workspace_api.WorkspaceAPITests` fixture or `create_app`
dependency injection with disposable rows/details and SQL doubles. Manager is
`app.extensions['metadata_summary_jobs']`. Set `manager.autostart = False` before
submission, then call `manager.drive_worker()` to process deterministically.
Calculation faults can be injected with `patch.object(manager, '_calculate',
side_effect=...)`; source/publication/annotation provider changes test generation
faults. No production fault endpoint exists. `WorkspaceService.explore_page` and
`explore_field_registry` provide read adapter seams. Cancellation/progress tests
can patch committed typed reader methods without modifying scientific predicates.

Focused checks cover the full service lifecycle, exact native/typed DTO and
predicate ordering, missing/null/unrequested summaries, custom policy fallback,
source exclusion versus frozen membership, generation/query/tamper cursor faults,
annotation invalidation, cancelled/failed/stale refusal, concurrent navigation,
successful/failed refresh and old reader leases. The snapshot excludes six MAT
fixtures; these checks create their own tiny H5/SQLite/SQL-double fixtures and do
not restore or qualify those missing inputs. Million-real-replay/storage, native
MySQL, rendered everyday actions, dense real annotations, waveforms/stimulus
reconstruction/export and packaging remain separate integration gates.
