# Renderer draft storage

Read the [public contract and executable examples](README.md),
[desktop navigation](../AGENTS.md), and adopted
[P07 lifecycle obligations](../../docs/architecture/0.1.8-first-port-slices.md#project-runtime-lifecycle-obligations).

The public entry is [draft-store.cjs](draft-store.cjs), retaining DraftStore,
validStoredDraft and MAX_DRAFT_BYTES. Keep tests at that seam under `tests/`.
Dependencies are Node fs/promises, path, crypto and root security.cjs; no Electron,
process authority, database or new facade. Main owns authenticated window/project
scope; this owner only persists the validated envelope in its supplied directory.

Preserve absent versus unreadable state, pending recovery refusal, explicit archive
reset, owned nonsymlink paths, exclusive temporary creation and existing schemas.
Properties such as pending are conventional implementation state, not private
language fields. A saved view grants no scientific readiness, mutation receipt or
power-loss durability claim. Do not widen security policy while reorganizing.
