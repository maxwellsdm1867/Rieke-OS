# Close coordination

Read the [public contracts and executable examples](README.md),
[desktop navigation](../AGENTS.md), and authoritative
[explicit Quit contract](../../docs/dev/DESKTOP_QUIT_COORDINATION.md).

Public entries are [DraftBarrier](draft-barrier.cjs) and
[QuitCoordinator / bounded](quit-coordinator.cjs). Preserve these existing named
exports; no aggregate facade is needed. DraftBarrier may import only `node:crypto`;
QuitCoordinator has no imports. The catalog enforces these direct dependencies.
State is implementation-private by convention; `pending` is not language-private.

Keep tests at these public seams in `tests/`. Composition tests remain in
`../tests/` because they exercise actual main handlers with Electron/transport
doubles. `../tests/close-packaging.test.cjs` checks exact default/preview source
allowlists and staged local resolution, not actual builder or native behavior.

Contract changes require the existing P07 review/adoption update. Preserve strict
replacement in main's prepareQuit and bounded explicit Quit in orderlyQuit;
never make an exit imply clean drafts or process stop. Keep all security,
readiness, cancellation, identity and process authority unchanged.
