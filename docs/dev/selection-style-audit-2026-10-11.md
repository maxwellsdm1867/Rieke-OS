# Selection styling audit — October 11, 2026

Integrated into the local 0.1.10 source checkout on `codex/updater-audit`, based
on `d658a7b`. Live GitHub main was verified as `035e295`. The installed application
reports packaged source `31182a4`; this source change alone does not update it.

| Surface | Change |
| --- | --- |
| Select Data / epoch list | Remove selected cell and active/selected epoch side stripes; retain blue fill. Replace the focused label outline with a background focus cue. |
| Epoch Workbench | Remove residual shared-tag and selected-row side shadows; preserve explicit green selection, tag badges and bold highlight labels. |
| Split Tree hierarchy | Remove selected branch/leaf side shadows and highlighted leaf outlines; retain fill and keyboard focus shading. Structural tree connector lines remain. |
| Edit Tree columns | Remove highlighted/focused epoch outlines and the redundant selected-epoch side border. Preserve green selection, blue highlight, and bold open-path labels. |
| Split combinations | Remove decorative thick side borders from rounded combination labels; keep their background. |

Selection gestures, UUID sets, scientific consent, tag state, read freshness and
mutation behavior are unchanged. Adjacent action controls keep their keyboard
focus rings. Row-label keyboard focus uses contrasting fill without a text box.

Verification: production frontend build and architecture guard passed. Existing
selection/lifecycle checks and required core/million-query runs are recorded in
`benchmarks/results/selection-style-*`. These are source checks, not native visual
or installed-package qualification.

## UI-wide rule and second sweep

The user broadened this from epoch selection to the whole UI. The current owner is
`codex/next-version-integration` at the `full-epoch-qc/Rieke-OS` checkout. This sweep
starts from combined local commit `7d0d8f2`; it preserves its alignment changes.
The rule is now in `workspace-app/src/AGENTS.md`.

Audited all 66 frontend CSS files, desktop recovery CSS, and inline frontend
JS/JSX border/shadow declarations. Removed remaining selection-specific border
colors, outlines and shadows in QC, export format choices, theme choices, project
files/folder tabs, annotation scope and branch controls, protocol tabs, tree/view
pickers, date/cell-type choices, predicate field/value options, search results,
trace mode buttons and Workbench controls. Removed decorative thick edges in
nested/negated predicates, refresh warnings and combined branch labels. Negation
keeps its explicit NOT control and uses header fill. QC selection now keeps the
same padding as unselected rows. Global hover no longer strengthens a border.

Existing neutral container borders and row/pane separators stay uniform. The
remaining narrow lines are structural hierarchy connectors, native control
indicators or drag insertion/resize affordances. None adds a rounded-card side
stripe to communicate selection. Keyboard-only focus indicators remain; export
choices now show their wrapper focus indicator only for keyboard focus, not
ordinary mouse selection. The import-toast wrapper no longer frames focused
child buttons.

Visual checks used actual ThemePicker and ExportDestination components plus
representative markup with product styles for QC, warnings, predicate groups,
field/value/split choices, project categories, cell types, search and tabs. Light
and dark captures and computed styles confirm fills, absent selection shadows,
uniform existing container borders and unchanged QC padding. Mouse selection and
keyboard radio navigation were checked separately. The production build passed.
This is a whole-source audit with representative visual checks, not an exhaustive
native walkthrough or an installed-app update.

Local visual evidence (including source hashes):
`/Users/maxwellsdm/.codex/visualizations/2026/10/11/01a12c3c-18e4-7403-bd40-707bf00df109/selection-styling/`.
The coordinating alignment chat owns final combined architecture/core/million
validation after this commit. Earlier benchmark timing flags remain attributed to
their original runs; no new performance or release qualification is claimed here.

## Highlight color verification

The user emphasized that selected items must keep visible highlight fills. Checked
27 representative Workbench, Select Data and Edit Tree row states across Light,
Dark and Fred. System preference resolves to the checked Light/Dark palettes.
Scientific Workbench selection remains green; transient highlights use the theme
accent (blue in Light/Dark, purple in Fred). Combined selection/highlighting keeps
its stronger green fill and label emphasis.

The existing mixed green fill exposed a muted-text contrast weakness for timestamps
and protocol names: 3.86:1 Light, 3.60:1 Dark and 4.20:1 Fred. Those two text elements
now use semantic secondary ink on combined selected/highlighted rows, giving 5.48:1,
5.44:1 and 5.78:1 respectively. No palette or selection-fill values changed. The
minimum label contrast measured across the 27 checked states is 4.66:1. Also removed
the redundant high-specificity global hover fill so it cannot override selected
fills; the original base hover rule remains. Build passed. These are scoped computed
color and visual checks, not a claim of complete accessibility qualification.

Evidence is `colors-before.json`, `colors-after.json`, `color-audit.json`, and
`colors.png` in the local visual-evidence directory above. The coordinating chat
will bind final regression results to the new commit, not the prior candidate.
