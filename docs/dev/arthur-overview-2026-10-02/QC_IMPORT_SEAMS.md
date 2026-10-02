# Read-only QC/import association findings

Inspected from candidate `6dc6e888e992ea931c8972ead94036bea7091736` and the existing project's stored protocol manifests / imported epoch indexes. No source recording, live database, import policy, inclusion mask, recipe, binding or export was changed. Imported index files can include retained revisions; their summed counts are not authoritative current project counts.

## Exact available identities

| Display name | Recorded acquisition Protocol ID |
|---|---|
| ExpandingSpots | `edu.washington.riekelab.turner.protocols.ExpandingSpots` |
| SplitFieldCentering | `edu.washington.riekelab.turner.protocols.SplitFieldCentering` |
| SingleSpot | `edu.washington.riekelab.protocols.SingleSpot` |
| VariableMeanNoiseCurInject | `edu.washington.riekelab.chris.protocols.VariableMeanNoiseCurInject` |
| VariableHistoryNoiseCurInject | `edu.washington.riekelab.chris.protocols.VariableHistoryNoiseCurInject` |

`protocolOverviewModel.js:isTypingProtocol` classifies terminal names SingleSpot, ExpandingSpots and SplitFieldCentering as QC/typing (case-insensitive and removing spaces for display classification). This is a presentation classifier, not an acquisition identity validator. “Typing spot” is not a recorded protocol name in the inspected corpus; SingleSpot is the available candidate, and Arthur should confirm it is intended.

`workspace_qc.py:FAMILIES` recognizes exact terminal names:

- expanding_spots: ExpandingSpots
- split_field: SplitFieldCentering
- single_spot: SingleSpot
- current_step: CurrentStep, CurrentPulse, CurrentInjectionStep
- current_noise: VariableMeanNoiseCurInject, VariableHistoryNoiseCurInject
- other: remaining recorded protocols

The CurrentStep/CurrentPulse/CurrentInjectionStep names are supported family contracts, not observations of those recordings in this project.

## Existing association and import contracts

`CellQC.rows(cell_uuid)` validates the UUID against `service.cells` and retrieves all main-catalog rows with that exact cell UUID. QC overview reports `scope: main_catalog_same_cell_uuid`, including epochs outside working sets and local inclusion masks. Its family summaries retain the full recorded protocol names. The UI can already navigate from a source cell to Cell QC. A repeated Cell1 label/date is not evidence to associate distinct UUIDs; source/session identity and any biological correspondence must remain explicit.

`workspace_protocol_state.py:cell_ids` derives distinct cell UUIDs from working epoch membership. This offers a join seam for displaying supporting QC context alongside a pinned protocol without modifying its member epoch UUIDs.

`workspace_suggestions.py:freeze_baselines` preserves exact starter membership as a binding before import. `rerun` reruns frozen recipes after successful catalog refresh, creates immutable candidate revisions and pending suggestions, and records `working_dataset_membership_changed: false`. The UI review/approval flow applies changes separately. `workspace_api.py` then prepares source-scoped supporting voltage estimates; preparation does not classify a cell's scientific quality.

`workspace_protocol_identity.py:protocol_compatibility` compares every proposed member against the destination's exact recorded acquisition Protocol ID. Updates and pinned exports reject mixed or empty membership. `create_pinned_protocol` requires one exact recorded Protocol ID. Adding spot/centering epochs to an experimental working set would violate this contract; automatic context linkage is a separate concern.

## Recommended design, pending clarification

Expose a **QC & typing for these cells** context panel on a pinned protocol: derive its cells from current exact working membership, join catalog QC families by the same cell UUID, and show recorded protocol identity, source availability, and support counts. After H5 import, refreshed same-UUID context can appear automatically while experimental working membership remains frozen and pending candidates remain reviewable. Use source/revision-aware cached or bounded requests, not global field-summary fanout. Keep support selections independently inspectable; label their scope and inclusion clearly.

Clarify whether Arthur wants (1) automatically visible same-cell context only, (2) independently pinned QC working selections, or (3) a new explicit combined export format containing scientific data plus QC support. Also confirm SingleSpot and whether “QC” includes current-step/current-noise families. The third option requires an explicit format/policy decision; it cannot silently broaden existing pinned membership or exports. Newly imported records with a different cell UUID require reviewed correspondence evidence rather than name matching.
