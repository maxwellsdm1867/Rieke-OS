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
