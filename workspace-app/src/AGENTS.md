# Frontend module navigation

Start in the module folder for the responsibility you are changing:

- [Presentation sessions](presentation/AGENTS.md): route snapshots, destination
  fallbacks, checkpoints and deletion pruning; public session factory and tests
  live together. App composes navigation, persistence and scientific owners.

- [Tree selection](tree-selection/AGENTS.md): ordered first-epoch and bounded
  range reads; callers retain gestures, cancellation ownership and publication.
- [Group save/recovery](group-save/AGENTS.md): exact retry identity, compact
  recovery and deferred preview release; preview, UI and undo remain callers.

- [Renderer view drafts](renderer-drafts/AGENTS.md): queued persistence, load recovery
  and React lifetime binding; native storage and shared lifecycle remain separate.

- [Protocol tree layout](protocol-tree-layout/AGENTS.md): versioned layout saves
  and the real React load/save lifetime; scientific grouping remains separate.

- [Workspace navigation](workspace-navigation/AGENTS.md): route/history identity and
  React navigation lifetime; restored views do not restore scientific consent.

- [Search activation](search-activation/AGENTS.md): bounded global-search reuse,
  App-shell activation and action-time freshness; typed metadata matching remains
  a named public entry.
- [Requested summaries](requested-summaries/AGENTS.md): requested-field policy,
  controller, React lifetime and submit/poll/cancel adapter; backend computation
  and scientific membership remain separate.
- [Attested tree ancestors](tree-ancestors/AGENTS.md): bounded nonterminal reuse,
  fresh witness leases, provider lifetime and column orchestration.
- [Typed query presentation](typed-query/AGENTS.md): typed predicate and split
  editors, registry identity and ordered joint recipes.
- [Incoming workbench](incoming-workbench/AGENTS.md): queue and frozen review
  presentation; command choreography and ephemeral consent retain separate entries.
- [Trace windows](traces/AGENTS.md): bounded recorded samples, inclusive time and
  missing-sample segmentation; resource/cache lifetime remains shared.

The remaining presentation owners are grouped by responsibility:

- Browsing and inspection: [epoch browser](epoch-browser/AGENTS.md),
  [tree browser](tree-browser/AGENTS.md), [cell QC](cell-qc/AGENTS.md) and
  [protocol overview](protocol-overview/AGENTS.md).
- Metadata and controls: [metadata explorer](metadata-explorer/AGENTS.md),
  [metadata refresh](metadata-refresh/AGENTS.md),
  [summary controls](summary-jobs/AGENTS.md) and
  [annotations](annotations/AGENTS.md).
- Project workflows: [project workspace](project-workspace/AGENTS.md),
  [recording import](recording-import/AGENTS.md), [exports](exports/AGENTS.md),
  [file picker](file-picker/AGENTS.md) and [undo](undo/AGENTS.md).
- Local preferences and application presentation:
  [project preferences](project-preferences/AGENTS.md),
  [appearance](appearance/AGENTS.md) and [app updates](app-updates/AGENTS.md).

These folders retain named public entries and existing authority boundaries. See
also the [architecture map](../../ARCHITECTURE.md).

Run `npm test` from `workspace-app` for recursive `.test.js` discovery with the
React preload, or use a module's explicit command. Do not import test support into
production. The [catalog](../../docs/architecture/adopted-port-checks.json) guards
public entry/import rules; run `python3 -B tools/architecture_guard.py check
--language javascript` from the repository root. Tests and the guard require
`RIEKE_TEST_DOM_MODULE` to be unset. No native qualification follows from these
frontend checks.
