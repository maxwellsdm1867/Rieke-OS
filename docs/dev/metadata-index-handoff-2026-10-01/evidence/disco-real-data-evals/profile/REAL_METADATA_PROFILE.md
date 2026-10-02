# Actual mounted Disco metadata profile

The installed project's current generations contain **2,781 real epochs**, **13 cells**, **165 blocks** (165 nonempty and 0 empty), **24 groups**, **5 protocols**, and **3 active sources**. No new epochs or metadata values were generated. This is an inventory at the actual mounted volume, not a million-epoch qualification.

## Real protocol mix

| Protocol | Epochs |
|---|---:|
| edu.washington.riekelab.turner.protocols.ExpandingSpots | 1,857 |
| edu.washington.riekelab.chris.protocols.VariableMeanNoiseCurInject | 540 |
| edu.washington.riekelab.chris.protocols.VariableHistoryNoiseCurInject | 309 |
| edu.washington.riekelab.turner.protocols.SplitFieldCentering | 52 |
| edu.washington.riekelab.protocols.SingleSpot | 23 |

## Actual metadata workload

- Mounted SQLite has **140 query fields**, **10,756 exact typed distinct field/value pairs**, and **214,451 epoch/field links**.
- Query fields per epoch: median **74**, minimum **72**, maximum **101**.
- Reconstructed full detail JSON: median **38,357 bytes**, p95 **163,972 bytes**, maximum **163,972 bytes**. This includes shared ancestor metadata reconstructed for each epoch; it excludes waveform samples.
- Epoch row JSON: median **3,230 bytes**.
- Epochs per cell: median **92**, range **33–687**.
- Epochs per block: median **5**, range **1–601**.

The 187 MB reconstructed sum repeats the same ancestor metadata once per epoch. **164.7 MB** of that sum comes from repeated block `frameTimesMs` arrays. Actual deduplicated storage has **202 unique ancestors**, totaling **706,121 uncompressed bytes** and **98,589 compressed bytes**. The 2,781 stored compressed inline detail/reference blobs total **4,131,887 bytes**. This reconstructed JSON size must not be extrapolated as physical database storage at one million epochs. SQLite rows, indexes, and field/value links have separate storage costs.

The JSON companion inventories all **140 native query fields** and **340 decoded detail leaf paths**, with path, type, missing/null counts, cardinality, frequency counts, JSON width, and array length. Of the query fields, **85** have missing values in some epochs and **10** contain explicit nulls. `parameters/useRandomSeed` mixes real and integer representations across protocols. The decoded metadata includes **13 paths with integers above JavaScript’s exact numeric range**, mostly .NET timestamp ticks; these paths are absent from the query index. Raw field values are excluded.

The native query catalog deliberately omits some oversized arrays: block `frameTimesMs` is present in every full decoded detail but is query-indexed for only **483** epochs. Full metadata preservation and query eligibility are separate contracts.

## Source handling and reproducibility

There are four import directories but three selected projection generations. The two September 24 epoch-index files are byte-identical and both contain 1,086 epochs. They must not be counted twice when sizing the mounted dataset. Current projection generation selection and exact mounted SQLite epoch membership establish the actual 2,781-epoch volume.

Only read-only file operations and an immutable, query-only SQLite connection were used. No application service, import, migration, refresh, cache publication, or cache lease was invoked. SHA256 seals were checked for all selected source projections. Generation manifests, projections, mounted SQLite, and examined import files were unchanged before and after inspection.

The read-only helper `real_projection_loader.load_real_projections()` returns actual rows, losslessly reconstructed details, cells, sources, and hash evidence for isolated comparisons. Any future million-epoch expansion should clone whole real acquisition hierarchies and label the result as scaled real data; repeating existing data preserves its observed mix but does not prove behavior for unseen metadata diversity.

## Native block reconciliation

A subsequent read-only native LEFT JOIN confirmed **168 registered blocks = 165 nonempty blocks + three zero-epoch blocks**, all three in source experiment 4 / VariableHistoryNoiseCurInject. The selected projection/raw hierarchies represent the 165 nonempty blocks. This reconciles the counts without treating registration-only empty blocks as recording epochs. Evidence is in ../native/block-reconciliation.json.
