# Group tagging and prepared tree revision audit

Baseline: local DISCO 0.1.24 source `1442947750ef2fd650ca95fd39f55c53cca7e393`.
GitHub main was independently observed at `5b0730ed17016259272f6ca0203c97a2ab0c7485`;
the fix intentionally preserves the current combined local build as its base.

## Reproduced failure

In the native installed app, opening the 2026-10-12 Cell2 group (103 matching
epochs) and clicking **Tag matching epochs** immediately showed “Curation changed;
reload before saving or exporting.” Reopening the group reproduced it before any
tag input or write. No scientific tags or recordings were changed during diagnosis.

Prepared protocol pages use `PreparedNavigation.revision` (version 3), while
`AnnotationGroups.preview` compared that client token with the version-1 membership
hash returned by `TreePages._scope`. Equal membership therefore failed admission.
The generic `RevisionConflict` text obscured the actual tree-revision mismatch.

## Repair

Group preview reads the same prepared authority as the page, limited to the exact
service owner and canonical pager. It retains the existing bounded canonical
target resolver and memory limits; opening and closing prepared verification
fence that resolution. The returned preview token matches the displayed tree.
Canonical/custom/copied services retain their existing policy. Neither disabling
revision checks nor automatically rebuilding a potentially different group is
part of the repair.

Missing/stale prepared state raises `PreparationRequired`. Navigation catches
that exception locally, but the group route previously had no such handler;
introducing prepared reads without handling it would produce an unrelated server
error. The group preview route now converts it to the existing HTTP 409 conflict
contract with a group-specific reopen instruction. This applies only before a
save operation exists; uncertain saves keep their original recovery semantics.

## Revision-consumer audit

| Consumer | Finding |
| --- | --- |
| Tree pages, anchors and ancestor batches | Already read prepared revisions and verify the prepared snapshot; batches route through the same page implementation. |
| Bounded tree selection | Already uses the service-owned prepared revision and closing verification; keeps its 1,000-epoch selection limit. |
| Group tag preview | Fixed incompatible prepared/legacy comparison; keeps the independent 10,000-project-epoch admission and larger server group support. |
| Source-predicate previews and matching-epoch pages | Use source scope (`protocol_uuid=None`); prepared navigation intentionally preserves the canonical version-2/legacy token. No protocol version-3 comparison found. |
| Saved search preview metadata | Carries source-preview tokens; no protocol prepared-token comparison found. |
| Incoming/copied Workbench services | Must not borrow live prepared authority. Group UI still explicitly excludes Incoming group tags; copied-service regression rejects a live token. |
| Group apply, replay and undo | Use frozen targets, native generation vectors, source/binding seals, expected author revisions and operation receipts. They do not compare tree-page hashes; checks retained. |

Actual later edits, source changes, author/profile mismatch, expired previews,
membership changes and uncertain-save recovery remain separate legitimate refusal
paths. Fixing the false preview conflict does not authorize removing those checks.

## Validation boundary

New disposable-fixture cases cover prepared protocol revisions, exact cell-branch
membership, 1,857-target apply and changed-only undo, source-scope compatibility,
stale tokens, a generation change during capture, copied service isolation, and
HTTP missing-preparation handling. Existing group, prepared-navigation, tree,
annotation-batch and recovery suites remain applicable. Focused source receipts
are retained in `/private/tmp/disco-curation-fix-evidence`.

Native verification of the corrected combined app and final core/million checks
belong to the combined-build owner after integration. This audit is not a claim
of native SQL durability, final build qualification, publication, or performance.
