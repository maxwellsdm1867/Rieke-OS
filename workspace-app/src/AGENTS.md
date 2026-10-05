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

Other frontend owners retain their existing named files pending the organization
worklist; each ledger record need not become a separate module. See the
[architecture map](../../ARCHITECTURE.md) for other adopted interfaces.

Run `npm test` from `workspace-app` for recursive `.test.js` discovery with the
React preload, or use a module's explicit command. Do not import test support into
production. The [catalog](../../docs/architecture/adopted-port-checks.json) guards
public entry/import rules; run `python3 -B tools/architecture_guard.py check
--language javascript` from the repository root. Tests and the guard require
`RIEKE_TEST_DOM_MODULE` to be unset. No native qualification follows from these
frontend checks.
