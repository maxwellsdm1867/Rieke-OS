# Mounted native database workload, 2026-10-01

Inspected the currently mounted LOCAL_NATIVE_PROJECT project (f75a7799-a728-5220-8f20-bfa4e7dffcb1), native MySQL 8.4.2 at localhost port 53812. Used raw PyMySQL, a read-only consistent snapshot, a 3-second session SELECT limit, and a 60-second process cap. No DataJoint/bootstrap imports, database writes, schema changes, app reload, trace reads, native database copying, or synthetic data. Credentials stayed in memory. Individual annotation text, tag values, author names, and profile names were not exported.

The final aggregate inspection completed in approximately 0.25 seconds after authentication. Query elapsed values are inspection diagnostics, not controlled performance benchmarks.

## Exact scientific coverage

| Native source experiment ID | Epochs | Cells | Blocks |
|---|---:|---:|---:|
| 3 | 690 | 5 | 37 |
| 4 | 1,005 | 5 | 67 |
| 5 | 1,086 | 3 | 64 |
| Total | 2,781 | 13 | 168 |

There are 24 epoch groups, 4,713 response stream registrations, and 2,781 stimulus registrations. 849 epochs have one response stream; 1,932 have two. All three registered source manifests have status `validated`, review status `unreviewed`; their declared counts match exact native coverage. Full source identities and hash mapping are in schema-profile.json for reconciliation with projections.

| Protocol | Epochs | Blocks |
|---|---:|---:|
| ExpandingSpots | 1,857 | 14 |
| VariableMeanNoiseCurInject | 540 | 22 |
| VariableHistoryNoiseCurInject | 309 | 84 |
| SplitFieldCentering | 52 | 25 |
| SingleSpot | 23 | 23 |

The sixth protocol entry `no_group_protocol` has 19 epoch groups but zero directly associated epoch blocks and therefore zero epochs when protocols are attributed through epoch blocks. Group-level protocol attribution must not replace block-level protocol attribution. Cells contain 33–687 epochs each. The data are unevenly distributed across protocols and cells.

A follow-up read-only LEFT JOIN reconciliation proves that the 168 registered native blocks contain **165 nonempty blocks and three blocks with zero epochs**. All three empty blocks belong to experiment 4 and VariableHistoryNoiseCurInject (native block IDs 150, 151, 168). Sources 3 and 5 have 37 and 64 nonempty blocks respectively; source 4 has 67 registered and 64 nonempty blocks. All blocks belong to registered source experiments. This explains why epoch-derived projection/raw hierarchy coverage reports 165 blocks while native table registration reports 168. Exact UUIDs and aggregate evidence are in `block-reconciliation.json`.

## Metadata shape

Native epoch parameters have **68 distinct keys**, with **22–47 present per epoch** (mean 26.5581), averaging 690.72 bytes and reaching 1,219 bytes. This is substantially richer than a four-field fixture. Presence varies by protocol; missing fields must remain missing rather than be treated as null or zero.

The field/type pairs include 49 DOUBLE, 6 INTEGER, 6 STRING, 7 ARRAY, and 1 NULL. There are 69 pairs for 68 keys because `useRandomSeed` is INTEGER in one protocol and DOUBLE in another. Arrays include 2-element coordinates and histories, and a 13-element `spotSizes` array. A faithful comparison must preserve arrays, explicit null, missing keys, and equivalent integer/double filter semantics.

The highest-cardinality parameters are `seed` (391 values in 540 epochs), `targetSeed` (309/309), and `history1Seed`/`history2Seed` (292/292). Common lower-cardinality but varying fields include `currentSpotSize` (13 values), `centerOffset` (14 arrays), `currentSD` (10 values), and `history1` (15 arrays). Many always-present rig settings are constant. A useful filter/facet suite should include common constant fields, protocol-specific missing fields, arrays, low-cardinality numeric settings, and unique seeds.

Epoch properties include `bathTemperature` and `frameTimesMs`. `frameTimesMs` is explicitly null for 849 epochs and an array for 1,932, reaching 148 elements / 1,116 bytes. A full metadata preview can process substantially more content than a count and bounded page. No waveform samples were read.

## Actual annotation load

There are three annotation profiles and exactly **one canonical shared_annotation row**, on an epoch, with zero tags. Canonical curation has zero rows. Legacy scientific tags, shared-tag dictionary, lookup, and indexed author tables have zero rows. The mounted data do not currently supply a dense annotation/tag workload; this inspection cannot validate that gap. There are seven saved dataset revisions and 62 explorer revisions, with five protocol workspaces.

## Consequences for experiments

1. Use these three actual source projections for SQLite/DuckDB comparisons, preserving the native source/cell/block/protocol relationships and all observed metadata types.
2. Verify query-result equivalence and preview field catalogs against the 2,781 real epochs before reporting timings.
3. Separate real-data measurements at actual size from any enlarged replay of real records. The mounted project does not contain one million epochs; an enlarged replay would be a derived scale workload and must be labeled as such.
4. Do not infer million-epoch qualification, dense-tag qualification, or SQLite/DuckDB superiority from these inspection diagnostics.

Detailed aggregates and exact source identities: `schema-profile.json`. Reproducible read-only inspection: `inspect_native.py`.
