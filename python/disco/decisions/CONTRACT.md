# Authored decisions ownership

Status: mechanical package organization; the named substantive modules
retain their individual caller interfaces beneath `disco.decisions`.
Detailed contracts remain in the [ledger](../../../docs/architecture/core-module-ledger.json):
`shared-annotations`, `author-identity-preferences`, `annotation-group-authority`,
`protocol-curation`, and `external-tag-receipts`.

`disco.decisions.annotations.SharedAnnotations` owns authored tag transactions and
changed-only audit. Author UUID is attribution, not authenticated actor identity.
`disco.decisions.author_preferences` owns OS-user roster and selection, resolving the
preference path per call. Project SQL registration may precede preference-file
failure; selecting an author does not rewrite history. Separate roster/selection
reads are not a coherent snapshot.

`disco.decisions.annotation_groups` owns supported-size frozen group commands, exact
operation identity and durable actor/request receipts, including no-ops. A retry
must retain the same request identity; inverse facts cover changed members and
must not rerun a changed query. Admission limits are not streaming guarantees.
`disco.decisions.curation` owns versioned project curation and frozen reference records.
A metadata fingerprint change makes old approval unreviewed; revision conflicts
must expose current state. Acquisition data and raw recordings are immutable.
`CurationStore.update` writes only epochs whose persisted decision changes, in
batched multi-row statements inside its locked transaction; a no-op epoch keeps its
revision but its expected revision is still checked. `POST /api/protocols/<id>/curation`
returns a receipt read after commit under the same lock: `curation` (per-epoch state),
`query_revision` and `expected_binding_version` (current tokens), and
`curation_revisions` (new revision for each changed epoch only). The next write may
present these tokens without re-reading; every check stays server-side and stale
tokens get 409. Neither curation POST nor selection-mask import caps the epoch count.

`disco.decisions.external_tags.ExternalTags.receive` owns immutable message identity
and receipt replay. An identical message returns its existing receipt without
another annotation command; changed content under the same UUID is rejected.
Export identity, registered target identity and source hash must all agree.
The annotation command owns commit/audit; receipt-file publication may fail after
commit. A sidecar does not mutate the frozen export. File-claimed authors remain
claims. `disco.decisions.tag_exchange` validates additive tag interchange; selection
masks never become authored tags.

Public entries are `disco.decisions.annotations`, `author_preferences`,
`annotation_groups`, `curation`, `external_tags` and `tag_exchange`.
For example, `from disco.decisions.external_tags import ExternalTags` selects
receipt authority without loading annotations or curation. The inert package
initializer does not expose a facade or eager dependency graph.
[Adjacent decision owners](ADJACENT.md) documents annotation preparation/checkpoints,
curation vocabulary, explorer revisions, native/shared tag indexes, shared vocabulary
and undo under this package. Protocol-state proof retains its flat path. These
entries keep distinct authority; existing scientific witnesses require exact
relocation review and gain no new freshness or transaction semantics.

[Isolated receipt examples](../../tests/test_backend_decisions_public.py) exercise
the public receive interface using inert annotations and an owned temporary
folder. They cover replay/refusal only, not first delivery, SQL commit, native
lookup, author-file failure, source freshness or cross-process durability.

## Page-local export counts

Shared annotation reads with explicit target IDs remain restricted to those IDs
at every cardinality. `SharedAnnotations` hides the 250-target SQL batching inside
its read implementation; the legacy `selected_only` keyword remains accepted but
is no longer needed to prevent a broad read. Full snapshots explicitly omit IDs.
`for_epochs` reads only the requested epoch IDs and their inherited cell IDs,
preserving all author chips and revision maps. The nonindexed `summary` fallback
likewise queries only its supplied epochs/cells, including zero reads for an empty
scope. Generation-fenced indexed summary behavior is unchanged. These are read
projection changes, not new annotation authority or mutation batching rules.

`summary(rows, scope_token=...)` accepts an optional caller-proven identity of
`rows` (the overview passes the immutable publication serial). With the indexed
reader, an equal token reuses the materialized summary scope and its incremental
tag deltas without re-reading or re-validating every row; any other token, a
rebuilt index or the nonindexed fallback reads `rows` as before. `tagged_targets()`
returns the cell and epoch targets currently carrying a shared tag from the same
generation-fenced index (None without it); the overview derives per-protocol
shared-tag counts from it without re-scoping the summary per protocol.

`CurationStore.export_link_counts(epoch_ids)` returns a fresh UUID-to-integer map
for the caller's requested page UUIDs, including zero for unexported epochs.
It uses the same project-scoped export-index signature polling, recipe validation
and rebuild behavior as `export_memberships()` and `epoch_exports()`. It does not
copy or expose the stored links. Existing full-membership and per-epoch public
snapshots remain deeply detached. The epoch-page HTTP owner supplies already
admitted UUIDs and retains its opening/closing authority checks; counts confer no
membership or action authority. Injected stores overriding `export_memberships()`
retain their snapshot-based policy; adapters without the count accessor also use
the existing snapshot path. Header polling and cold index reconstruction still
scale with the project's export revisions/memberships.

The existing curation and API integration suites cover bounded lookups, page-only
projection, exact counts, cross-protocol additions, removal, corrupt recipe refusal
and public snapshot mutation isolation using transactional doubles. They do not
qualify native SQL durability or packaged performance.

## Optional epoch annotation display count

`GET /api/epochs/<uuid>/annotations` retains its existing full response by
default. A single `include_cell_epoch_count=false` omits only the display count
and avoids enumerating registered project epochs; `true` retains the current
exact project-wide cell count under the same lock. Other query parameters,
repeated options and values other than `true`/`false` are refused. The registered
epoch lookup, inherited/direct tags and author revisions are unchanged. The
count neither defines cell membership nor authorizes annotation writes.

The native annotation editor omits this count while it is hidden and requests
it for Whole cell display when absent. Supplied request owners retain their
existing URL contract. Mounted tests cover pending/stale reads and exact cell
UUID/revision writes; backend tests cover no-enumeration reads and full counts
after registration, deletion and cell-link changes. These fixtures do not
qualify native SQL durability.

Completed dataset publication retains the exact sealed export recipe through
`workspace_authored_json.write_row`. It admits only the declared plain
`DatasetRevision` schema and complete primary key for native typed JSON writes,
then verifies exact readback before audit/publication in the existing transaction.
Custom writers still execute their own methods and must preserve exact JSON.
Existing recipe seals, curation/source/binding checks, artifact identity and export
index verification are unchanged; no acquisition representation tolerance applies.
Focused publication/readback and lossy-writer rollback examples are in
`python/tests/test_workspace_authored_json.py`; native evidence and its limits are
in `docs/dev/h5-conversion-audit-2026-10-09.md`.

## Protocol-local export status for overview reuse

`CurationStore.protocol_export_status(protocol_uuid, epoch_ids)` returns the
intersection of requested UUIDs with that protocol's saved exports, plus the
immutable export-header signature. Its index polls and verifies only records
restricted by project and protocol, using the existing recipe validation and
identity checks. At most eight protocol indexes are retained. Project-wide
history and per-epoch readers retain their existing full-index semantics. The
status set and signature confer no export/mutation authority.

## Per-tag added times

`shared_annotation_tag` (declared beside `shared_annotation`) holds one row per
current target/author/tag: `tag_sha256` key, exact `tag`, `added_at` (UTC),
`added_revision` and `time_source` (`recorded`, `audit_event`, `approximate`).
`_apply_batch_locked` writes it in the same transaction as the unchanged `tags`
JSON, so single edits, undo, group commands, external receipts and tag exchange
all record times; removing a tag deletes its row and re-adding records the new
commit time. Chips (`read_targets`, `for_epochs`, receipts, page rows) carry
`added_at`/`time_source`; a missing row, a row whose `added_revision` exceeds the
author revision, or an absent tag falls back to the row's `updated_at` marked
`approximate`. Exports keep projecting their existing chip keys.

`disco.decisions.tag_times.reconcile` runs at app bootstrap only when a project
has annotations and no time rows (first migration, or after an offline app-state
restore, which clears the project's time rows). It replays
`shared_annotations_updated` before/after lists along a contiguous per-target
revision chain ending in the current tags; other times use `updated_at` marked
approximate. The table is not in generation triggers or recovery snapshots: its
rows change only with a watched `shared_annotation` change (or at that bootstrap
before generation authority starts), and readers revalidate rows against the
current tags/revision. Tag-time filters (`annotations/{cell,epoch,effective}/tag_times`
`contains {tag, after, before}`, half-open UTC window) live in
`disco.navigation.tag_time_filter`; indexed filtering keeps opening/closing
generation checks and otherwise defers to the canonical chip reader.
Tests: `python/tests/test_workspace_tag_times.py`.
