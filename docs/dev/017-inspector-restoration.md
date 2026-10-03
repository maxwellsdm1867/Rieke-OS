# 0.1.7 bounded Inspector restoration slice

Implementation branch: `codex/017-within-project-navigation`, based on clean `491afa578988ba9686d02d4560808a9bd6304aa2`. Initial slice: `68ed8d3b25a5345bacad910e115922e5da3672a0`; the subsequent repair removes error-state frame polling and cancels pending restoration on outside-pane navigation intent. Tracks restoration #47, bounds #50 and qualification #51 under #46.

## Behavior and boundaries

Inspector sessions retain date/cell expansion, per-cell page offsets and achieved list scroll. Filters and exact display focus remain in the existing session path. Each list snapshot holds at most 128 date labels and 128 cell UUIDs with bounded label lengths and matching offsets; it contains no epoch rows, membership, selection/mutation receipts, traces or raw H5. This bounds the new per-snapshot hints, not total application heap or all existing route sessions.

Hints restore only for the matching project/protocol/filter presentation scope. Normal Protocol presentation scope does not include actor or binding generation: these are disposable hints, never read or mutation authority. Fresh parent epoch/cell receipts still gate interaction. Restored cells request their pages through the existing uncached API and current query revision. Pagination clamps to current cell counts; this does **not** locate an exact focused UUID after membership has shifted. Do not claim complete changed-membership focus restoration, same-cell reveal, or new bulk-selection persistence.

Scroll restoration waits for fresh parent membership, all mounted child pages and two ready layout frames. Pending/error states sleep under a DOM observer and wake on readiness changes/retry; they do not perpetually poll frames. Pointer, wheel, touch, key, collapse, scope changes, focused UUID changes and explicit Inspector navigation intents cancel old restoration. The explicit counter includes same-target focus, Prev/Next and parent keyboard navigation. Completion/cancel/unmount disconnect observers and cancel frames. Existing mutation fences and frozen contexts are unchanged.

## Evidence

- Regression first failed on baseline when a date/cell opened at page 61 remounted closed; it passes after restoration wiring.
- Error-state regression first failed because one RAF remained queued indefinitely; the repaired helper has zero queued work while waiting.
- Delayed-page regression first failed because the prior 180 px scroll applied after a new same-target intent; the repaired mounted component keeps the newer intent.
- Mounted tests cover protocol/filter scope changes, outside-pane navigation, deferred pages, cancellation, error/retry and unmount. A real jsdom MutationObserver test covers wait/retry and effect cleanup/replay. Existing stale-response and scientific action tests remain in the full frontend suite.
- Repaired slice: full frontend suite passed **607/607**; production build passed (existing large-chunk advisory only).
- Production build uses `npm run build -- --configLoader runner` so the shared read-only dependency link is not used for Vite configuration temporary writes.
- Independent interim native App run on the initial slice, one sample per variant: baseline loses achieved 180 px, both branches and visible selection; candidate retains them after current membership, settled layout and 500 ms. Exact stream unchanged on both. This is interim correctness evidence, not a speed claim or final qualification of the repaired commit.

Independent raw evidence: `/Users/maxwellsdm/Documents/Codex/2026-10-03/task/research-017/comparison/interim-private.json`; cleanup receipt: `interim-cleanup.json`. Final repaired-commit qualification is owned by the separate benchmark/review tasks.

## Read reuse remains a separate adapter

No new read payload cache is enabled. Audit of `workspace_tree_pages.selection_revision` shows ordinary Protocol tree revision covers binding/member fingerprints/filter/splits but not all annotation state or backend incarnation. Epoch leaves also include shared annotations. Future reuse must be allowlisted, fully keyed and validated against current authority/incarnation; initial anchor/root validation, summary submit/poll, selection/tag/range reads and raw H5 must not silently become cache hits. Do not transplant the GlobalSearch 30-second rule into these paths. Identity/reuse work is tracked in #48/#49.

No installed app, released worktree or live 5175/8768 service was changed. Implementation tests start no persistent services; generated test artifacts and dependency links are excluded from commits. No push, deployment, merge, issue publication or user scientific write was performed by this task.
