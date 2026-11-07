# Epoch selection continuity repair

Base: installed 0.2.10 source `deb76e619ec5276fa4de745f34bedbf7026196df`.

Reproduced on the unchanged source with real mounted components: plain-click a
row, let the parent temporarily gate actions during a same-membership navigation
read, then Shift-click another row. InspectionCellTree lost its anchor and selected
only the last row; PagedTree cleared the selection. Command/Ctrl also lost the
plain-click origin. Source history shows the reset predates 0.2.10, so this is a
confirmed current failure path, not proof of which recent release exposed it.

The patch separates the ordered-membership anchor identity from temporary action
availability. All existing aborts, stale-handler fences, fresh-receipt checks and
selection/highlight authority separation remain. Real source/revision/order/proof
identity changes clear the anchor. Command/Ctrl extension retains the preceding
plain-clicked Main epoch only with matching page revision, consistently in both
owners. Independent review found and verified closure of a stale-origin risk
before updating lifecycle receipts.

Validation: 39 mounted list/tree lifecycle tests, 89 navigation/shortcut/Inspector
authority tests, and 4 retained-lifetime receipt checks passed. Architecture guard
passed before receipt updates; no API or backend contract changed. Original-source
regressions failed with the expected wrong UUID selections before the fix.

Native current-app inspection was attempted read-only: Pulse family Inspect was
open; clicking an epoch via AX produced no observed navigation; subsequent UI
access returned noWindowsAvailable. This is not candidate native qualification.
No source app or installed runtime was changed. Native candidate click, Shift,
Command, arrows and selected/focused palette checks remain for coordinated
integration. Keyboard source is unchanged: ordinary Up/Down navigates; the
existing shortcut contract explicitly ignores Shift+Arrow. No claim of new
keyboard range extension is made.

No benchmark or release qualification is claimed. Parent integration owns native
verification first, then final combined-source core/everyday-million checks.
Only temporary test logs were created; retained logs here are compact evidence.
Existing dependency directory is referenced through a worktree-local symlink.
