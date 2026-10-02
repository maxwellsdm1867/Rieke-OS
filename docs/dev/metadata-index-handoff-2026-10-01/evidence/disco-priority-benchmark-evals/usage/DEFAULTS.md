# Evidence-based metadata summary defaults

Verified from the saved audit and the sealed real-data field-presence inventory, without new mounted/live database reads. This proposes requested summary fields, not a restricted query schema.

## Verified inventory

| Protocol | Real epochs | Available field paths |
|---|---:|---:|
| ExpandingSpots | 1,857 | 74 |
| VariableMeanNoiseCurInject | 540 | 75 |
| VariableHistoryNoiseCurInject | 309 | 101 |
| SplitFieldCentering | 52 | 80 |
| SingleSpot | 23 | 72 |

The counts sum to 2,781 epochs; the union is exactly 140 paths. Every saved presence count is an integer between 1 and its protocol's epoch count. Presence can include recorded null and does not establish useful variation or scientific completeness.

## Observed defaults

Keep a compact shared identity context: date, cell identity/type, block, group identity/label and protocol. Request full value distributions only for the fields needed by the visible view; identities and timestamps need pagination rather than enormous dropdowns.

| Protocol | Evidence | Proposed first summaries |
|---|---|---|
| ExpandingSpots | Saved date → cell → currentSpotSize layout | `parameters/currentSpotSize` |
| VariableHistoryNoiseCurInject | Saved joint-history layout; logged control/history/target/segment axes and NDF selection | `parameters/history1`, `parameters/history2`, `parameters/target`, `parameters/isControl`; add `segmentTime`, `frequencyCutoff`, `NDF` when those controls are visible |
| VariableMeanNoiseCurInject | Logged cutoff/current mean/current SD/useRandomSeed axes | `parameters/frequencyCutoff`, `parameters/currentMean`, `parameters/currentSD`; seed summary when requested |
| SingleSpot | Last-run predicate includes cell type; no protocol-parameter layout evidence | Identity context first; no evidence-based parameter default yet |
| SplitFieldCentering | No retained protocol-parameter layout evidence | Identity context first; no evidence-based parameter default yet |

The mean-noise **saved** layout uses joint(history1, history2, target), but none of those three fields occur in its real cached rows. Preserve that user-saved layout and its missing-field behavior; do not silently substitute a different tree. The proposed mean-noise summaries are supported separately by older logged layouts and actual available parameters.

Joint history summaries must retain exact array values, missing/null semantics and all three components. Joint identity cell/block remains a computed grouping. Prefer effective epoch parameter paths for new default controls; preserve explicit block-path queries and do not merge aliases without semantic verification.

## Scientific-priority additions, distinct from usage evidence

The scientist explicitly prioritizes bath temperature, clamp mode, pipette/amplifier offsets, pipette solution/internal and external solution additions, tags and experimental protocol conditions. These deserve fast access even though this small retained history does not establish their operation frequencies. NDF has direct logged selection evidence; lightPath is also scientifically requested and remains eligible.

Candidate spot-protocol additions: spot size/diameter, spot intensity and background intensity; visual center position when appropriate. Candidate SplitFieldCentering additions: contrast, rotation, temporal frequency, mask diameter and visual center position. Those are available protocol parameters and scientific hypotheses for defaults, not observed frequent queries.

The user's “offsets” means **pipette/amplifier offsets**, not visual stimulus position. No pipette/amplifier-offset field was identified in the cached 140-path inventory. `parameters/centerOffset` is visual geometry and must never be relabeled as the requested electrical offset. Missing capture needs investigation before promising that filter. `parameters/controlMode` is present only for the history-noise protocol; verify its source meaning before presenting it as a complete clamp-mode field.

## Full flexibility and background work

All 140 fields remain queryable. Selecting an uncommon field requests its summary through a separate, cancellable path; it can be slower without blocking navigation. Cache by exact metadata generation, scope/predicate and requested field set, and invalidate for source changes. Tags need their own annotation generation and target/profile semantics; do not cache them as immutable recording metadata or conflate cell-inherited tags with epoch tags.

Canvas size, trial/repeat/sample counts, sequence/shuffle and generator/version settings remain available for arbitrary queries, inspection, exports and stimulus reconstruction. Reconstruction must retrieve its complete dependency bundle regardless of default-summary membership. On-demand does not mean excluded or dropped.

Retain a full-field view and compare requested summaries exactly with the corresponding subset of full results. This history cannot establish “80% of operations”; defaults should be revised using measured costs and clearly attributed future observations.
