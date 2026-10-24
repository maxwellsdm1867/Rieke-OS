Unsigned Apple silicon testing release. Not production-qualified.

DISCO 0.2.1 brings the current combined UI and navigation improvements into one downloadable app.

- Views and trees prepare automatically when opened, including predicate results and incoming Workbench views.
- App Updates sits beside Appearance in the sidebar, with a download indicator and a simpler status dialog.
- Epoch lists use cell-type icons; View tree returns to the originating Epochs or Split tree view. Redundant cell-selection checkboxes are removed while tagging and epoch controls remain available.
- Group tagging accepts current prepared tree revisions instead of incorrectly asking for a reload.
- Protocol overviews use clearer dataset labels with less explanatory text. Cell QC headers have consistent spacing, and the duplicate top-right Appearance control is removed.
- Scrollbars appear during scrolling where appropriate without shifting trace geometry. System appearance is the default; the Fred update indicator uses the approved palette.
- Overview cell counts use a generic ganglion-cell icon. Parasol icons have a larger filled nucleus detail, with no additional inner ring.

This release preserves the existing import review, explicit merge, Undo, recorded metadata, export, and project storage behavior. It includes the tree and recorded-field split improvements from 0.1.24.

Publication requires successful exact-source full regression and million-row comparisons plus the complete selected desktop candidate checks. Local native checks and user confirmation of the repaired matching-epoch tag preview are narrower evidence; they do not substitute for the package checks.

This uses the existing unsigned Apple silicon testing download and update channel. It is not Developer ID signed or notarized. macOS 14 and later are the deployment target; macOS 14 runtime support remains unqualified and Intel is unsupported.
