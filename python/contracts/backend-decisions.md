# Decisions ownership at current paths

Status: preparation only; existing flat modules remain the caller interface.
Detailed contracts remain in the [ledger](../../docs/architecture/core-module-ledger.json):
`shared-annotations`, `author-identity-preferences`, `annotation-group-authority`,
`protocol-curation`, and `external-tag-receipts`.

`workspace_annotations.SharedAnnotations` owns authored tag transactions and
changed-only audit. Author UUID is attribution, not authenticated actor identity.
`workspace_author_preferences` owns OS-user roster and selection, resolving the
preference path per call. Project SQL registration may precede preference-file
failure; selecting an author does not rewrite history. Separate roster/selection
reads are not a coherent snapshot.

`workspace_annotation_groups` owns supported-size frozen group commands, exact
operation identity and durable actor/request receipts, including no-ops. A retry
must retain the same request identity; inverse facts cover changed members and
must not rerun a changed query. Admission limits are not streaming guarantees.
`workspace_curation` owns versioned project curation and frozen reference records.
A metadata fingerprint change makes old approval unreviewed; revision conflicts
must expose current state. Acquisition data and raw recordings are immutable.

`workspace_external_tags.ExternalTags.receive` owns immutable message identity
and receipt replay. An identical message returns its existing receipt without
another annotation command; changed content under the same UUID is rejected.
Export identity, registered target identity and source hash must all agree.
The annotation command owns commit/audit; receipt-file publication may fail after
commit. A sidecar does not mutate the frozen export. File-claimed authors remain
claims. `workspace_tag_exchange` validates additive tag interchange; selection
masks never become authored tags.

Proposed locality: preserve separate modules under `disco/decisions`, using the
existing path companion's names. Annotation preparation/checkpoints, protocol
reads, shared/native tag lookup, vocabulary, explorer revisions and undo are
adjacent owners, not permission to combine their authority or alter scientific
witnesses. Review that closure before moving. Keep-current is preferable to an
import-only facade or a universal command object that hides partial commits.
B's package adoption, exact profile/catalog ownership, dynamic loaders and all
caller imports must be settled before runtime relocation.

[Isolated receipt examples](../tests/test_backend_decisions_public.py) exercise
the public receive interface using inert annotations and an owned temporary
folder. They cover replay/refusal only, not first delivery, SQL commit, native
lookup, author-file failure, source freshness or cross-process durability.
