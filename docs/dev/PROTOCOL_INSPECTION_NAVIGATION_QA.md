# Protocol inspection navigation and tagging

Validated locally on 2026-09-27. The main user tab was left available; later
checks used a separate test tab to avoid interrupting active use.

## Interface changes

- Persistent Overview, Inspect, and Export navigation with icons, descriptions,
  and an explicit selected state.
- Tree overview and Epoch inspection are separate views. Back to tree overview
  restores the column path, page offsets, and scroll positions. A scoped explorer
  handoff also has a Back to filtered tree action.
- Restored the column tree presentation: each column identifies its split field,
  group count, epoch count, and selected branch. Requests are bounded to 60 entries
  per column; at most eight split columns plus one epoch column are retained.
  Restored ancestor pages use the same server revision as the selected page.
- Epoch inspection defaults to compact date/cell headers and flat chronological
  epoch rows, with collapsible cell sections and Up/Down navigation. Display
  labels do not merge different cell UUIDs. Small row checkboxes remain bulk-action
  selectors; they are not inclusion switches.
- Add a split opens the recommended fields and field search. User-facing controls
  say Edit tree, Tree editor, and Tree preview.
- Tag epoch opens/focuses a visible Add tag control. Tags stay visible above the
  right-hand Summary, Fields, and Connections sections. Field/value searching
  selects Fields automatically. Full source fields and copy controls remain.
- Saved project-tag suggestions support prefix matching and keyboard selection.
  Selecting a suggestion fills the input; Add tag performs the existing audited,
  revision-checked curation write. Removing a chip affects only the focused epoch.

## Verification

355 Python tests and 109 frontend tests passed, with a successful production
build. The audit fingerprint test passed separately after registering the new
interface source files. Tag tests include project isolation, validation, exact
spelling, add/remove behavior, rollback, caller-copy isolation, and cache expiry.

Live browser checks confirmed:

- Date → Cell → Epoch block → epoch produces four simultaneous columns.
- Selecting an epoch and returning restores all four columns and their ancestry.
- Switching to Export and back to Inspect preserves that tree location.
- Compact epoch selection and Up/Down navigation update the focused trace.
- Tag input arrow keys do not move the selected epoch.
- Tag control, empty suggestions state, and field/value metadata search work.
- Searching `frequencyCutoff = 100` displays four matching recorded fields.
- Add a split opens recommendations; searching `segment` finds matching fields.
- No application console errors were observed; unrelated extension errors remain.

There are currently no saved project curation tags in the live project. No test
tags were written into research data; nonempty suggestions and writes were tested
with disposable fixtures. Vocabulary contains currently saved curation tags, not
tags found only in removed historical audit entries. A two-second vocabulary
cache avoids repeated SQL scans while typing and invalidates immediately after
local successful tag edits.

No protocol membership, raw H5, mask, or existing export was changed in this pass.
