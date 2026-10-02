# Paired engine control using actual mounted metadata

Both engines consumed the exact current sealed SQLite metadata from the mounted LOCAL_NATIVE_PROJECT project. No invented epochs, parameter distributions, or synthetic expansion were used. All writes stayed in the isolated private experiment directory.

The corpus contains 2,781 epochs, 13 nonempty cells, three source projections, 140 stored query fields, 10,756 distinct typed field/value records, 214,451 epoch/value links, and 202 shared metadata objects. Returned catalogs contain 141 fields because the production catalog adds a derived joint field.

## Complete catalog and JSON

Five warm repeats per case, median milliseconds. The same installed production catalog, grouping suggestions, and layout implementation ran on SQLite and DuckDB; only SQL dialect and connection adapters differed. Global measurements explicitly bypass the saved global catalog cache to measure recomputation. Filtered cases reuse the saved global field definitions. This is a catalog stage control, not an end-to-end app preview measurement.

| Real scope | Matching epochs | SQLite ms | DuckDB ms |
|---|---:|---:|---:|
| global | 2,781 | 662.94 | 628.34 |
| largest_protocol | 1,857 | 471.83 | 496.65 |
| largest_cell | 687 | 238.75 | 489.43 |
| numeric_value | 1,820 | 475.61 | 512.89 |
| text_value | 1,249 | 334.33 | 586.36 |
| missing_field | 924 | 374.53 | 516.42 |

DuckDB is about 5% faster for global catalog recomputation. SQLite wins every measured filtered catalog, including a roughly 2× advantage on the largest cell scope. All complete returned catalog hashes match exactly. Actual equality predicates used observed spotIntensity and cell label values; the missing-field scope used absent currentSpotSize. Scientific values and UUID lists are not retained in the report.

## Bounded controls

| Work, including JSON | SQLite ms | DuckDB ms |
|---|---:|---:|
| First 60 epoch rows | 1.233 | 5.123 |
| First epoch detail, full metadata decoding | 0.708 | 5.710 |

DuckDB wins the standalone complete-membership SQL scans in these cases: about 1.1–1.5 ms versus SQLite’s 1.9–4.8 ms. That advantage does not translate into a faster filtered catalog with the current application algorithm. The bounded row/detail controls return identical JSON hashes; full first-detail DTO also matches independent source-projection reconstruction.

## Fidelity and input integrity

All seven copied tables compare identically in count, row content, typed JSON, and blob hashes, including metadata_objects. The installed SQLite rows match every independently decoded active source-projection row; epoch membership is exactly equal. All six scopes have equal complete membership lists and complete catalog output hashes. Real array values, missing fields, nulls, mixed numeric types, inherited metadata, and stored metadata blobs remain present.

The supplemental oracle verifies the widest array represented in the native query catalog (frameTimesMs, 971 JSON bytes, seven matching epochs), typed values, and its complete epoch detail across both engines. Raw detail integers above JavaScript’s safe precision are preserved identically as Python integers and exact JSON; these tick leaves are not native query fields. The production query contract deliberately does not expose some oversized arrays, even though they remain in the full detail DTO.

The active projection manifest, all three source-projection hashes, the active metadata manifest, and mounted SQLite hash were verified unchanged after the run. Metadata extraction used private lazy projection decoders; the mounted app service and cache lease writers were never called. All production SQLite reads used mode=ro and immutable=1.

## Limits and conclusion

This real-data result supports SQLite for the existing interactive catalog and bounded browsing path. DuckDB’s strengths here are fast relation scans and a smaller derived file, rather than a consistently faster preview. The native complete catalog still costs hundreds of milliseconds on only 2,781 actual epochs, so its scaling and Python work need separate investigation before qualifying one million.

The SQLite file is 20,787,200 bytes; the experimental DuckDB copy is 12,333,056 bytes. The 0.425-second DuckDB copy timing excludes the separate object-table copy and is not comparable to initial SQLite import; initial real ingestion was not measured. Peak process RSS was 386,154,496 bytes (about 368 MiB), under the 512 MiB cap; the worker finished in 30.9 seconds under a 120-second cap. DuckDB used two threads and a 192 MiB query memory limit.

No one-million qualification, cold app startup, native preview endpoint, frontend rendering, production annotation workload, concurrency, or waveform I/O was measured. Five repeats and this 2,781-epoch corpus cannot establish a universal engine winner. Earlier four-field synthetic million-row results remain synthetic capacity controls and must not be presented as representative real-data evidence.

Aggregate receipts: receipt.json and complex-dto-receipt.json. Reproduction helpers: compare_real.py and validate_complex_dto.py. Databases themselves contain actual scientific data and stay private; they must not be copied to a public repository.
