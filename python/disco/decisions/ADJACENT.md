# Adjacent decision owners

This extends the authored-decision contract without combining command authority.
All leaves are substantive public named modules; the initializer remains inert.

| Task | Start here |
| --- | --- |
| Save/restore explicitly sealed shared-tag checkpoints | [annotation_checkpoint.py](annotation_checkpoint.py) |
| Prepare discardable indexes at existing lifecycle boundaries | [annotation_preparation.py](annotation_preparation.py) |
| Count dataset tags across protocol epoch unions | [curation_vocabulary.py](curation_vocabulary.py) |
| Apply immutable source-query/tree revisions transactionally | [explorer.py](explorer.py) |
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
