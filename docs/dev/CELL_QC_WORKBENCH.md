# Cell QC, search and navigation

Implemented 2026-09-27 in the local React workspace. QC is a read-only characterization workbench; it never changes protocol membership, curation, masks or source files.

## Navigation and finding data

- Persistent Back/Forward and protocol Overview / Inspect / Exports controls.
- Exact trial/cell UUIDs and safe prefixes in Search data (Cmd/Ctrl-K).
- Typed predicates such as `frequencyCutoff = 100`, `history1 = [0,675]`, and numeric comparisons. Numbers, strings and arrays retain their types and order.
- Effective `parameters/...` fields take precedence for unqualified parameter names. Full provenance field paths remain searchable; other ambiguities show selectable field-level alternatives.
- Focused metadata supports the same field/value pair syntax, with original API values available for copying.
- Cell QC can be opened from project/protocol cell lists or the focused epoch. Characterization recordings are linked by exact cell UUID across the main catalog, including epochs outside applied protocol memberships.

## Measurements now available

Recorded temperature range and chronological entries; measured resistance fields if present, kept distinct from amplifier compensation settings; detected characterization-protocol availability; lazy bounded raw traces; per-epoch recorded pre/stimulus-window mean and population SD; and bounded within-block condition comparisons with exact parameter grouping and sampled-trial coverage. Units come from the selected acquisition response stream. In the Sep23 Cell3 spot recordings, Amp1 is **pA**, not membrane voltage.

Condition summaries use up to three chronological trials per exact parameter dictionary and acquisition block, at most50 conditions and500,000 samples. These are descriptive recorded-response previews, not firing rates or fitted receptive fields. Complete stimulus timing must fit the bounded read; otherwise the statistic is marked unavailable instead of calculating a partial-window mean. Raw trace inspection uses the existing source-verified viewer with zoom/pan and bounded full-rate windows.

## Resting potential: code found, validation still required

Read-only Wheeler lookup found the canonical decision **F-447a4b02**: per-block baseline anchors and within-session pchip interpolation, not a single full-trace average. Code **S-464cfc16** is `retinaSRM/vbaseline_interp.m`; extraction **S-489e6b8b** is `compute_vrest_baseline_drift.m`. Historical interpolants **D-d5eba7fd** cover five older recordings; they are not valid for the September2026 cells. Unknown cells and out-of-range queries remain unavailable.

The bench provides separately labeled **block-onset voltage estimates** from the first chronological epoch of each eligible current-noise block (at least2epochs, recordedmV). It reports the1ms mean,0.5/2ms sensitivity, source hash, exact epoch/block/group identities and reference contamination flags. It does not fit or silently extrapolate a new validated resting-voltage curve. These estimates can be affected by stimulus onset, holding current and spikes; reference flags are not a cell-quality pass/fail judgment.

## Reconstruction gaps

- Existing `retinanalysis/classes/sc_pipeline.py:ExpandingSpotsPipeline` provides spike-count/spot-size analysis, but the spike-detector and acquisition-mode adapter must be validated before automatic QC use. It is marked **unvalidated adapter**, not missing code.
- No measured resistance fields were found in the current8cells. `seriesResistanceCompensation` is a setting, not a measured resistance.
- No current-step protocol was detected in these two files. SingleSpot/light-step, expanding spots and split-field recordings remain accessible where present.
- No automatic cell-type classification, RF fit, sensitivity score or arbitrary quality threshold is invented.

## Verification

257 Python tests and 76 frontend tests passed, along with the final production build. Live browser checks verified exact UUID navigation, typed numeric predicate preview433matches, focused array-pair metadata matching, and returning fromQC/data stores to the same selected epoch.

Independent raw-H5 arithmetic verified all39sampled trials across13spot conditions in Sep23Cell3: per-trial pre/stimulus means, deltas, aggregate response means, pA units and exact block/parameter grouping. See `cell_qc_validation.json`.

Live examples: Sep23Cell3 has92epochs,54expanding-spot trials,3split-field trials,2single-spot trials and33current-history-noise trials; recorded bath-temperature values range30.6–31.3 (unit not stored). The saved History working dataset remains173epochs; QC does not add the other characterization epochs to it.

Additional browser QA confirmed QC family/selected-trial restoration (SingleSpot NBQX epoch88af89c8-54bc-4527-aff6-9ff651676b59), typed draft value25/name restoration after leaving and Back, condition comparison rendering, and six block-onset anchors. Temporary UI test draft edits were reset without saving or applying them. Cell identity and Back controls remain pinned while scrolling the QC trace.
