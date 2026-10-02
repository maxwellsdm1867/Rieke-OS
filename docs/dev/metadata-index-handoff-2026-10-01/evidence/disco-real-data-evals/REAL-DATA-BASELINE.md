# Real mounted data is the workload baseline

Inspected 2026-10-01T09:08:10.471420-07:00. Mounted project: LOCAL_NATIVE_PROJECT / Spike Response Model, installed app version 0.1.5 / source c438aad9. All inspections were read only; engine experiments wrote only private temporary copies. No invented or enlarged data was generated.

## Actual load

- 2,781 real epochs, three registered sources, 13 cells, 24 groups, five populated protocols.
- 168 native registered blocks:165 nonempty blocks represented in projections plus3 zero-epoch registrations (native LEFT JOIN confirmed).
- 68 epoch parameter keys,22–47 present per epoch;140 stored query fields, 72–101 present query fields per epoch;340 decoded detail leaf paths. The catalog adds one derived joint field to its returned 141 definitions.
- Missing keys, explicit nulls, arrays, mixed integer/float values, and large timestamp integers are observed. Existing query-field eligibility omits some oversized arrays; full detail preserves them.
- Uneven real grouping:33–687 epochs per cell and 1–601 epochs per nonempty block.
- Only one canonical annotation row, with zero tags; dense annotations are not part of the mounted workload.

These actual distributions replace the four-parameter regular synthetic fixture as the representative workload. Earlier million-row measurements remain controlled synthetic capacity experiments; they do not qualify this real metadata schema at one million.

## Real paired engine evidence

Exact sealed mountedSQLite was copied, all seven tables were copied to DuckDB, and the same installed production catalog algorithm ran on both. Five warm repetitions per scope include JSON serialization. Complete memberships, catalogs and typed metadata outputs match; mounted files/manifests were unchanged.

| Real scope / operation | SQLite | DuckDB |
|---|---:|---:|
| Full catalog recomputation, all 2,781 epochs |663ms|628ms|
| Full catalog, largest protocol, 1,857 epochs |472ms|497ms|
| Full catalog, largest cell, 687 epochs |239ms|489ms|
| Full catalog, observed numeric filter, 1,820 epochs |476ms|513ms|
| Full catalog, observed text filter, 1,249 epochs |334ms|586ms|
| Full catalog, missing-field filter, 924 epochs |375ms|516ms|
| First 60 real rows plus JSON |1.23ms|5.12ms|
| First full epoch detail, decode plus JSON |0.71ms|5.71ms|

DuckDB's small global-catalog and standalone membership-scan advantages do not carry through to the filtered catalog cases. SQLite remains the leading choice for the measured existing interactive metadata path. This is real data at actual size; it is not a million-epoch, browser, full preview API or startup qualification.

## Storage versus reconstruction

The mountedSQLite occupies 20.8 MB; the experimentalDuckDB copy 12.3 MB. Reconstructing every full detail repeats shared ancestor arrays and produces 187 MB of JSON, but the 202 unique ancestor objects occupy only98,589compressed bytes and epoch inline/reference blobs 4.13 MB. Preserve this actual ancestor deduplication when scaling; multiplying reconstructed JSON is not a physical-storage estimate. Array-heavy full detail still matters for application memory and serialization.

## Consequences for the million-epoch target

The mounted project contains 2,781 actual recordings, so a one-million run cannot be labeled one million actual mounted epochs. Any enlarged experiment must explicitly be a replay derived from real records, preserving the full field/type/presence model, protocol mix, uneven hierarchy, query eligibility and ancestor sharing. Repeated real records alone do not establish performance with newly growing seed/cardinality diversity. No enlarged fixture was generated in this inspection.

Next experiments should retain all nine everyday actions, use the real schema throughout, test continuation on the observed 601-epoch block, distinguish bounded filter results from all-field catalogs, and cover full application startup/refresh. Real arrays/null/mixed numeric types invalidate treating the earlier four-column typed prototype as a complete production representation. Real annotation sparsity should be retained for representative tests; denser tags belong to a separately labeled stress workload.

Detailed profiles: [metadata](profile/REAL_METADATA_PROFILE.md), [native tables](native/REPORT.md), [paired engine results](engines/REPORT.md). Aggregate receipts and reproducible inspection helpers are included. Actual database copies remain private under /private/tmp/disco-real-data-evals-20261001/engines; no native credentials or raw scientific database files were copied here or published to GitHub.
