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
