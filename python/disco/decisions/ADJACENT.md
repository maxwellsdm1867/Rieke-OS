# Adjacent decision owners

This extends the authored-decision contract without combining command authority.
All leaves are substantive public named modules; the initializer remains inert.

| Task | Start here |
| --- | --- |
| Save/restore explicitly sealed shared-tag checkpoints | [annotation_checkpoint.py](annotation_checkpoint.py) |
| Prepare discardable indexes at existing lifecycle boundaries | [annotation_preparation.py](annotation_preparation.py) |
| Count dataset tags across protocol epoch unions | [curation_vocabulary.py](curation_vocabulary.py) |
| Apply immutable source-query/tree revisions transactionally, including membership-delta revisions | [explorer.py](explorer.py) |
| Maintain exact native trigger-backed lookup | [native_tag_lookup.py](native_tag_lookup.py) |
| Build disposable token-fenced SQLite membership/aggregates | [shared_tag_index.py](shared_tag_index.py) |
| Lazily count distinct shared annotation targets | [shared_vocabulary.py](shared_vocabulary.py) |
| Return bounded response-only inverse facts | [undo.py](undo.py) |

Canonical annotation JSON remains authoritative. Preparation retains source links,
fresh native authority, failure cleanup and unsupported-policy results; it does
not rewrite canonical annotations. Applied queries are distinct from preview,
saved methods and frozen exports. Working indexes remain discardable and preserve
source-token fencing, exact text semantics, locks, callbacks and transactions.

Preserve the initialization cycle: shared_tag_index imports shared_vocabulary
inside its operation, shared_vocabulary imports curation_vocabulary inside its
operation, and curation_vocabulary imports shared_tag_index at module scope.
Autocomplete counts distinct kind/target pairs with exact author UUID winners
and deterministic casefold/tie ordering. Undo supplies bounded inverse facts,
not a persisted journal or permission to replay writes.

Checkpoint `_contract()` hashes actual annotations, shared_tag_index,
shared_vocabulary, annotation_preparation and checkpoint source files in that
order using the existing basename-to-content-hash dictionary algorithm. New leaf
basenames and changed source bytes conservatively invalidate old checkpoints.
Restore compares exact recorded source/proof with fresh source/proof before
creating a working index or opening saved SQLite. Rejection preserves old receipt
bytes and does not automatically rebuild, reseal or emulate old keys. Saving a
new checkpoint still requires current prepared state and fresh canonical proof.
Integration of the other annotations/metadata moves can invalidate the contract
again; compute the integrated hash from actual files, never relabel old evidence.

Run the bounded public examples separately from repository root:

```sh
PYTHONPATH=python python3 -B -m unittest -v disco.decisions.tests.test_workspace_undo
python3 -I -B python/disco/decisions/tests/test_checkpoint_refusal_public.py
```

The isolated restore example loads owned source bytes with strict upstream
stand-ins and forbids scientific imports, recording operations and SQLite open.
It proves stale-contract orchestration/refusal and unchanged receipt bytes only.
It does not prove native freshness, a successful checkpoint rebuild, SQL durability
or app/HTTP behavior. Existing central native/preparation suites remain deferred.
The retained [protocol-state owner](../../workspace_protocol_state.py) spans
WorkspaceService, CurationStore, SharedAnnotations, ExplorerHistory and native
reader authority and therefore remains at its existing path.

Explorer recipe reads retain detached output graphs. Exact plain membership
lists containing only string `uuid` and `metadata_hash` values use shallow member
copies seeded into the ordinary deep-copy memo; nested extras and aliases retain
deep-copy behavior. Custom member shapes use the existing full deep copy. `get`
still fetches and verifies the stored recipe and summary on every call, including
after an earlier successful read. Binding cache lifetime and storage admission
are unchanged. The compact explorer suite covers output isolation, aliases,
custom nested members, later corruption and deletion with SQL doubles; it does
not qualify native deserialization, durability or workflow performance.

`is_canonical_binding_reader(provider)` identifies only the original
`ExplorerHistory` binding implementation and its captured reader methods.
Instance/class overrides and subclasses return false. The boolean permits
query-result construction to read a known read-only binding before copying
retained original fields; it confers no membership, recipe or freshness authority.
Every actual binding read and existing scope validation still runs.

Explorer revision publication uses `workspace_authored_json.write_row` for its
sealed recipe and summary fields. Canonical app-owned DataJoint schemas use
single-statement typed JSON expressions and exact readback inside the original
transaction, before audit/publication. Custom writers retain their methods and
must pass the same exact JSON readback. No stored hash is recomputed or weakened;
subsequent `get` verification and binding authority remain unchanged. This prevents
first-write database JSON rounding from breaking an otherwise valid recipe seal.
Public endpoint and rollback examples are in
`python/tests/test_workspace_authored_json.py`; pinned native evidence is recorded
in `docs/dev/h5-conversion-audit-2026-10-09.md`.

## Membership-delta revisions

A revision is either a full recipe (v1, unchanged; every existing revision stays
a valid root) or a membership delta (`storage: membership-delta-v1`). A delta
stores `parent_revision_uuid`, `parent_content_sha256`, `lineage_uuid` (its
full-recipe root), the exact `delta` (`added` members with fingerprints and
`removed` UUIDs), `epoch_count`, the predicate fields and, when present,
`predicate_version` inherited from the parent, plus `membership_hash`: an
order-independent multiset hash, the sum of SHA-256(uuid:fingerprint) terms
modulo 2**256, updated in O(delta) from the parent's. `content_sha256` seals the
whole stored delta, so it also seals the parent seal and the multiset hash.
`create_delta` writes one O(delta) row; only additive deltas are published today.

Reading: `header(revision)` verifies a row's seal (for a delta also its parent
link, disjointness of added/removed with the parent membership, the recomputed
multiset hash, lineage and count) and returns the recipe without members.
`members(revision)` returns a shared read-only UUID->fingerprint view; a delta
overlays its parent's view (flattened past a bounded depth). Verified seals and
views are reused within a process; each header read still checks the row
exists. A tampered row is refused by the first verification of that revision
in a process; a v1 root's members are re-hashed on that first verification.
`get(revision)` keeps its contract for every revision: it fetches and verifies
the named row and returns a detached full recipe whose `epochs` are the exact
sorted membership (for a delta, materialized from the verified chain).
`bind` reads headers only.

Lineage index: `protocol_membership(project_uuid, lineage_uuid, epoch_uuid,
added_revision_uuid -> metadata_hash, removed_revision_uuid)`. Binding a delta
inserts its added rows and marks its removed members in the bind transaction
(the first additive delta bound on a lineage backfills the chain once,
O(root); a removal on an unindexed lineage leaves it unindexed). A revision's
indexed membership is the rows added on its chain and not removed on it.
`retire_delta` removes an undone delta's rows with one DELETE inside the
caller's binding transaction. `verify_lineage` re-hashes the indexed
membership against the sealed multiset hash, and `verify_membership` re-hashes
a membership about to be used (and the index) against it. Both are O(members)
and run where membership becomes scientific truth: protocol export
materialization re-hashes the exported bound membership, and app-state capture
and restore re-hash every indexed lineage a binding uses
(`workspace_state_snapshot.verify_lineage_state`); any mismatch refuses.
Data-store deletion prunes a bound revision as a removed delta (O(removed)
membership probes and one delta row) when the canonical reader is in use. The table is registered
append-only in the recovery state (`workspace_state_snapshot.TABLES`,
`recovery_generation.TABLE_NAMES`, ordinal 19); compact/expand queries never
re-query a delta or a root that a delta builds on, because the chain seals that
root's exact identity. Injected (custom) revision storage declares no index.

`ExplorerHistory.prepared_delta(previous, current, limit=20000)` projects only an
already verified adjacent membership delta for prepared display owners. It
requires both retained headers, their matching sealed parent link and at most
20,000 changed members before probing either revision's project-scoped existence.
Missing headers, deleted rows, custom readers and missing inverse fingerprints
return `None`, requiring explicit preparation. Forward additions use the verified
delta; inverse additions use only point reads from an already retained parent
MemberView. Undo of a pure addition needs no membership view. This accessor never
hydrates a recipe, builds/flattens a MemberView, enumerates unchanged membership
or grants new scientific authority. Tests in `test_workspace_prepared_delta.py`
exercise normal forward/inverse results, more than eight member-cache entries,
missing headers, deletion, changed-reader fallback and overlay-depth boundaries.
