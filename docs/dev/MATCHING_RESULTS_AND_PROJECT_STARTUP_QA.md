# Matching results and project startup validation

Validated locally on 2026-09-27 using the existing Spike Response Model catalog.
The project remains 2 sources, 8 cells and 1,776 epochs. No protocol membership,
source eligibility, inclusion mask or scientific tag was changed in this pass.

## Search and inspect

The filter editor keeps a compact count preview. **View matching epochs** opens
a separate workbench: date/cell sections, flat chronological epoch rows with
acquisition protocol names, a raw trace pane and a separately scrolling metadata
pane. Results expose Save selection, Edit tree, Use in protocol and Export
selection. Both navigation panes resize; rows load in pages of 60, and traces
remain bounded, full-rate H5 reads rather than eagerly loaded project waveforms.

Browser checks on the real catalog:

- All-source predicate returns 1,776 epochs, with dates and cell identities.
- ArrowUp from the first row of page two selects result 60, not result 1.
- Leaving for Data stores and returning restores result 60 and the query.
- Restoring the saved history-noise predicate shows 173 matching epochs.
- Editing the tree and returning preserves the same predicate scope.
- The Add project action opens a named-project form with a managed-folder choice.
- No application console errors were observed (an unrelated browser extension
  reported connection errors).

Adversarial review caught and fixed an old-page selection race at pagination
boundaries and a key-order mismatch between restored and editor-built predicates.
Matching-page requests reject stale metadata, tag or source-eligibility revisions
with HTTP 409. Test coverage includes empty results, malformed requests, anchors
outside the predicate and exact chronological membership.

## Named one-off exports

Created `Variable history noise · standalone` through the results UI, saving
candidate `a4910b6c-5043-4f66-b2c1-f16eb0080a05`, then exported both formats:

- SQLite: `37c28a23-ba37-4945-af19-0b572243a0d5`
- EpicTree MATLAB: `3c829cb2-dadf-4c51-adfc-2222d705e259`

Each contains 173 epochs, 4 cells and 2 recording dates. No new protocol or pin
was created. These two useful verification exports and their immutable candidate
remain in project history. **Review & export again** reopens the saved candidate,
name and format; it does not submit another export. SQLite integrity, foreign
keys and a verified 128-sample H5 read passed; evidence is in
`oneoff_sqlite_validation.json`. Native MATLAB evidence is recorded separately.

Candidate exports include every matching epoch and do not implicitly combine
protocol masks or tags. Explicit tag predicates retain their exact protocol-scoped
annotation evidence. Normal protocol exports retain their existing mask policy.

## New project and source lifecycle

`workspace_startup_live_validation.json` records a real, disposable empty-project
launch, isolated database provisioning, reopening and launcher restart. The test
container and processes were stopped; test logs and files remain outside the repo.
The first real run exposed a missing Flask route argument; this was repaired and
covered by a regression test.

Source lifecycle and tag tests use disposable fixtures: archive hides a registry
entry, exclusion removes its epochs from future queries, freeze locks source
registration edits, and existing exports remain immutable. Annotation predicates
use a named protocol scope instead of mixing tags from unrelated workspaces.

## Expandable split tree

The split tree now defaults to an indented, connected hierarchy, keeping open
siblings visible. The column presentation remains available. Selecting an epoch
from tree design keeps the shared tree beside the trace rather than switching to
the flat epoch list. Navigation restores open paths and scroll positions. An
anchor receipt includes each ancestor's parent-page offset, so selected epochs
remain locatable beyond the first 60 sibling groups.

Browser checks verified date → cell → block → epoch expansion, two open date
siblings, selected-epoch navigation across blocks, Columns/Expandable tree
switching, and returning from design to trace inspection without losing the tree.
The tree pane opens wider and remains resizable; deep hierarchies scroll
horizontally without wrapping identifiers into unreadable fragments. Automatic
selection scrolling preserves the horizontal position and branch controls.

At most 24 pages are cached, 60 entries per page. Stale-revision requests fail
closed. Canceled branch requests do not leave permanently unloaded open branches.
Column UI code is loaded only when requested. Builds retain prior hashed assets
so an already open local tab can still load its column chunk after a rebuild.
