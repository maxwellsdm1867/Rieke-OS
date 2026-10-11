# Numeric and row alignment — October 11, 2026

The current local integration is `codex/next-version-integration` in the
`full-epoch-qc/Rieke-OS` checkout. Its prior source was `ffb4322`; selection styling
from the coordinated **Audit selection highlights** chat (`4e66228`) was
cherry-picked as `983311e` before these alignment changes. GitHub main was verified
as `035e295`. Package version remains 0.1.10; this does not update the installed app.

## Changes

- Overview recording dates share grid tracks across rows. Bar origin and available
  width no longer change with the count suffix. Numbers and cell/cells units have
  separate tracks. The existing narrow-panel rule still hides the bar.
- Cell-type summary rows share an intrinsic count track using CSS subgrid. Counts
  align right, names start at the same position, and the track grows for larger
  values. The shared identity component and accordion layout remain unchanged.
- Protocol Cells, Epochs and Recorded time columns align right; count rows use
  tabular numerals. Epoch bars retain their original percentage calculation.
- Data-store counts use right-aligned tabular numbers and separate unit tracks.
  Intrinsic numeric minimum widths prevent digit/unit overlap in a narrow table.

All changes are presentation-only. Source identities, counts, scientific meaning,
selection callbacks, import/deletion actions and unknown-value handling are retained.
The other chat's selection/tree CSS files were not edited by this change.

## Visual evidence

The real components were rendered against synthetic data in a copied-source Vite
fixture; the installed app and scientific projects were not used. Overview geometry
was checked at 360, 460, 620, 820 and 1100 px in light/dark. Cell-type names now share
one x coordinate (previously a 24.68 px discrepancy). Visible date bars share origin
and track width (previously an 8.70 px origin discrepancy at 820 px). Protocol count
columns compute to right alignment and tabular numerals. Data-store values 1, 12,
123, 87, 1,204 and 11,090 share a numeric right edge with a 5 px gap before units.
A 360 px cell-summary fixture additionally covers 1, 12 and 11,090 with a long name.

Screenshots and DOM geometry are retained in the originating chat's local
`alignment-fix` artifact directory. This is browser fixture evidence, not native
package qualification. The source-only audit risks in other dialogs remain outside
these four fixes.

## Required source checks

Run existing overview/cell presentation and selection lifecycle tests, the production
frontend build, and the architecture guard. Final clean-source fixed core and both
actual-million comparisons are stored under `benchmarks/results/alignment-*`.
Retain the pinned `34ce2e0` baseline and the clean previous integration `983311e`.
Results must be read from their receipts; this document is not a passing receipt.
