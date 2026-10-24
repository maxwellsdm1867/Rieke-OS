Unsigned Apple silicon testing release. Not production-qualified.

DISCO 0.2.1 brings the current combined UI and navigation improvements into one downloadable app.

- Views and trees prepare automatically when opened, including predicate results and incoming Workbench views.
- App Updates sits beside Appearance in the left sidebar. Its download icon lights up and shows a notification dot when an update is available; the notice stays visible until the app is current. Open it to download and restart through the simpler status dialog.
- Epoch lists use cell-type icons; View tree returns to the originating Epochs or Split tree view. Redundant cell-selection checkboxes are removed while tagging and epoch controls remain available.
- Group tagging accepts current prepared tree revisions instead of incorrectly asking for a reload.
- Protocol overviews use clearer dataset labels with less explanatory text. Cell QC headers have consistent spacing, and the duplicate top-right Appearance control is removed.
- Scrollbars appear during scrolling where appropriate without shifting trace geometry. System appearance is the default; the Fred update indicator uses the approved palette.
- Overview cell counts use a generic ganglion-cell icon. Parasol icons have a larger filled nucleus detail, with no additional inner ring.

This release preserves the existing import review, explicit merge, Undo, recorded metadata, export, and project storage behavior. It includes the tree and recorded-field split improvements from 0.1.24.

Validation: [exact-source full regression](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/40065147705) and [million-row comparisons](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/40065149560) passed. The [original candidate](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/40065147970) passed its smoke check. The same immutable archive passed all 20 packaged UI checks, database verification, native updater/rollback checks, and installer/runtime checks in [requalification](https://github.com/maxwellsdm1867/Rieke-OS/actions/runs/40067683798).

Publication exception: the repeated smoke checks launched the app successfully but their public GitHub release-feed requests received HTTP 403 with the anonymous API allowance exhausted. That requalification run is therefore not fully green. The original smoke result remains valid for these same app bytes, and a fresh update check in the installed app succeeded. The failed connectivity receipts are retained; they are not counted as passing checks.

Packaged source: `c989239c3bce301c46da35f74dad556e0fd3c7ea`. The release tag and archive identify that exact source; later test-harness and documentation commits do not change the app. Local native checks and confirmation of the repaired matching-epoch tag preview remain narrower evidence.

This uses the existing unsigned Apple silicon testing download and update channel. It is not Developer ID signed or notarized. macOS 14 and later are the deployment target; macOS 14 runtime support remains unqualified and Intel is unsupported.
