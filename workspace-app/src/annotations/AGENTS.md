# Authored annotation presentation

Choose a named public entry; the folder is not a unified annotation command facade.
[Backend authored decisions](../../../docs/architecture/core-module-ledger.md) retain SQL,
audit, actor authorization and durable group receipts. The renderer preserves their
identity and partial-success facts; it does not create scientific membership.

| Responsibility | Public entries |
| --- | --- |
| Profile selection and chips | `annotationProfile.js`, `annotationTags.js`, `ui/AnnotationProfile.jsx`, `ui/AnnotationTags.jsx`, `ui/EpochTags.jsx`, `ui/AnnotationIndicator.jsx` |
| Confirmed display receipts | `annotationReceipts.js`, `useAnnotationReceipts.js` |
| Tag channel (pending + confirmed state, subscriptions) | `tagStore.js`, `useTagStore.js` |
| Exact tree/cell targets | `treeGroupTargets.js`, `treeGroupQueryTags.js`, `useTreeCellSelection.js`, `ui/TreeGroupTags.jsx` |
| Recovery and summaries | `ui/GroupAnnotationRecovery.jsx`, `ui/ProtocolTagSummary.jsx` |
| Tag exchange and monitoring | `tagExchange.js`, `externalTagMonitor.js`, `ui/TagExchangeControls.jsx`, `ui/TagExchangeDialog.jsx`, `ui/ExternalTagSync.jsx` |

Existing exports, props and callbacks remain public. Author UUID is attribution,
not proof of authenticated actor identity. Epoch/cell UUIDs, author revisions,
protocol/frozen candidate scope and query revision are distinct. Labels, row position,
and same-text tags never substitute for identity. Inherited cell tags and direct
epoch tags remain distinguishable; removing another author's chip is not silently
permitted. Tag text is not a scientific unit conversion or inclusion decision.

A verified annotation receipt can update displayed target facts, not invent a new
query/membership revision. Receipt limits remain 64 targets and 4 MiB estimated
payload; fast display requires the existing bounded shape. Exact bulk target
resolution refuses partial pages, duplicates, stale final scope or unsupported
candidate context rather than using global data. Group save/recovery remains the
separate [group-save owner](../group-save/AGENTS.md); supported-size group commands
and their durable operation identity are not ordinary many-request tag saves.

With the default request owner, epoch/selected-epoch annotation reads omit the
hidden whole-cell count. Whole cell scope requests the existing full read when
its inline count is absent. Supplied request owners keep their existing URLs.
Resource identity/revision and pending-read gates still protect editor writes;
the display count is not mutation authority.

Tab navigation waits for save and rechecks current editor scope before advancing.
Late responses after unmount/scope change cannot publish. External monitor scans
cannot overlap; errors retain known revision and back off. Receipt-file failure may
follow an already committed annotation transaction. `saved`/persistence outcomes and
uncertain group retries must remain visible; cancellation does not promise rollback.

The deletion test favors existing receipt/target/monitor interfaces: deleting them
spreads validation, frozen paging and lifetime knowledge across editors. Combining
profile, display receipts and command recovery would make simple chip callers learn
unrelated actor/transaction rules. This move improves locality, not behavioral depth.
Typed comparison is in-process; React/DOM and local selection are local-substitutable;
HTTP reads/commands are remote but owned with existing injected request adapters.
Backend SQL, native cleanup and external sidecar durability need separate evidence.

Executable public examples remain at their root test paths. From `workspace-app`:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/annotationTags.test.js src/externalTagMonitor.test.js src/treeGroupTargets.test.js
```

Mounted `treeCellTagWorkflow.test.js`, `treeGroupLifecycleWorkflow.test.js` and
`inspectorCurationLifecycle.test.js` retain cross-owner composition; run after the
integration owner has reconciled all moved callers. Tests preserve real entry points
and existing assertions. No import/export workload, scientific fixture, native
annotation transaction or performance qualification follows from this organization.

AnnotationTags resets local draft text when its epoch identity changes, not merely when Activity reconnects effects. Mutation scope/generation fences still reestablish on every reconnect. The existing nonempty unmount guard also prevents retained-view eviction of standalone CellQC tag text.

Inspect and Search editors consume shared annotations already present on their
admitted epoch rows, independently of the Live metadata setting. Frozen
Workbench uses the same Inspector path. Turning Live metadata off must not force
a second per-epoch annotation request or temporarily relock complete page-backed
controls during ordinary sibling navigation. Missing annotations, explicit
refresh, and required whole-cell counts keep their existing read/lock behavior;
per-author expected revisions and late-response scope fences remain unchanged.

Tags travel on their own channel (`tagStore.js`), not the App `revision` clock.
A single-target save calls `begin()` synchronously so the chip paints in the
click's frame (pending style), writes serially per target/author with the last
confirmed revision, then `confirm()`s in place or `fail()`s with rollback and the
draft restored. Pending operations are presentation only: never expected
revisions, never in exports or filters, never evicted. Confirmed epoch-only
receipts do not tick `useWorkspaceChanges`; tag-dependent results (filters,
legacy page tokens) renew once from `getConfirmedGeneration()` after a 75 ms idle
window, and summaries read that generation when they render. Bulk, undo and
external changes enter through `ingest()`/`invalidate()`. Store tests:
`tagStore.test.js`; mounted: `annotationReceiptWorkflow.test.js`.
