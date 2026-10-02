# Required real-million corpus and metadata storage benchmark

User requirement, 2026-10-01: use the **million-epoch replay of actual recordings** for future scale/regression evaluations, and evaluate metadata/index size as well as latency. A mapping should remain compact relative to the represented data; a query speedup is insufficient if its metadata footprint grows disproportionately.

## Required corpus

Use the existing 2,781-real-epoch source and its exact million replay: 359 complete replicas plus the recorded 1,621-epoch tail comprising whole blocks. Preserve the namespace mapping, actual fields/value types, missing/null states, scientific distributions and independent oracle. The replay has 140 eligible fields and 77,107,863 epoch-field links. Scientific cardinalities repeat; namespaced acquisition identities are distinct.

- Source snapshot SHA-256: `0427f38b01fad730941c3161d67a4fd6ae75988344527648cc066771b983147e`.
- Million replay SHA-256: `7e03e05e97885505f227e1b0938b34f303229db90ddcdd1f7e40f40d6b55e2b6`.
- [Replay receipt](evidence/disco-real-million-evals/base.receipt.json) records the exact tail and counts; [construction script](evidence/disco-real-million-evals/replay_real.py) preserves how it was built.

Smaller real fixtures are useful for development and semantic checks. The earlier fixed-schema synthetic million is supplemental evidence and must not replace the required real-schema million gate. If a seal or source generation changes, rebuild paired before/after baselines instead of treating old timing/size values as comparable.

## Current measured reference

The machine-readable [storage baseline](STORAGE-BASELINE.json) computes ratios from the preserved build receipts, without building or querying a database again. Sizes here are recorded file lengths; decimal MB/GB are used. These are SQLite metadata assets, not raw waveform files or a complete canonical MySQL/project footprint.

| Asset | Original real 2,781 | Real-record replay 1,000,000 |
|---|---:|---:|
| Base metadata SQLite | 20.787 MB | 7.196 GB |
| Added typed tables/indexes | 5.448 MB | 1.107 GB |
| Base + typed assets | 26.235 MB | 8.303 GB |
| Added index / base metadata | 26.21% | 15.38% |
| Added bytes per epoch | 1,958.89 | 1,107.03 |
| Base + typed bytes per epoch | 9,433.61 | 8,302.87 |

Sources: [real build receipt](evidence/disco-real-typed-sqlite-evals/model/build-receipt.json), [million build receipt](evidence/disco-real-million-evals/typed/build-million.receipt.json).

The smaller experiment adds tables to a native clone; the million experiment attaches one native base plus a sidecar and omits upfront global catalog caches. Different packaging/sealing makes this pair a reference, not a controlled growth curve or proof of an optimal representation. Compare candidates on the same corpus and layout.

The million **15.38% is added-index/base-metadata overhead**. It is not metadata/raw-recording overhead. A follow-up inspection below now supplies actual H5 sizes and lineage-weighted response-payload projections. The complete canonical project metadata footprint and intermediate-scale growth curve remain unmeasured. The 7.196 GB metadata base itself must be included in future storage investigations; evaluating only the 1.107 GB optimization would conceal most of the cost.

The preferred 28 experiment's projected 30% auxiliary saving is not physical savings: it still attaches the complete index. Keep that rejected result separate from measured asset sizes.

## Actual recording sizes and million-record projection

Follow-up read-only inspection checked all three original H5 SHA-256 seals and
file signatures, then read dataset shapes/types/storage-allocation headers.
No waveform values were decoded and no source file was modified. Exact results
and limitations are in [RECORDING-STORAGE.json](RECORDING-STORAGE.json);
[measurement script](measure_recording_storage.py) is preserved.

| Actual original source | Epochs | H5 file size, decimal MB |
|---|---:|---:|
| source-a.h5 | 690 | 168.678 |
| source-b.h5 | 1,086 | 219.533 |
| source-c.h5 | 1,005 | 301.177 |
| Total | 2,781 | 689.388 |

The original complete typed SQLite assets total 26.235 MB, **3.81% of these
actual H5 file bytes**. This excludes canonical MySQL and other project state.

For the million replay's exact lineage:

| Size or ratio | Projection / measured metadata |
|---|---:|
| H5 recording-file footprint | Approximately 247.905 GB |
| Compressed response-dataset allocation | 131.953 GB projected |
| Logical response-dataset representation before compression | 606.528 GB projected |
| SQLite base + typed metadata | 8.303 GB measured |
| Recording files + SQLite metadata | Approximately 256.208 GB |
| SQLite metadata / projected H5 files | 3.35% |
| SQLite metadata / projected compressed response payload | 6.29% |
| Extra typed index / projected H5 files | 0.45% |

Response payloads are weighted by 359 full copies plus each actual epoch in the
recorded whole-block tail, using its stored H5 allocation. No stimulus datasets
were found in these sources; this does not imply stimulus reconstruction requires
no data. Logical response bytes include the compound quantity/unit representation,
not only numeric samples. Whole H5 files include container metadata, shared
resources and other acquisition content as well as compressed responses.

The full-file projection uses complete source files for 359 copies and a
per-source epoch-fraction approximation for the partial tail. It is an estimate
of equivalent recording storage for this mix, not newly generated H5 files or a
claim about every protocol. Raw data physically present in this experiment remain
the original 689.388 MB; the million dataset is a metadata stress replay.

## Required output for every candidate

Record exact bytes and scope/generation in a storage receipt alongside query timings:

1. **Physical assets:** base SQLite, added typed index, other persistent summaries/caches, canonical MySQL metadata where present, recovery state, retained generations, and totals without double-counting shared files. Report file length and allocated disk separately; identify free pages/slack when available.
2. **Component breakdown:** rows/DTO JSON, encoded detail, shared ancestors, field/value dictionaries, epoch-field mappings, core projections, chronology/parent/UUID indexes, aggregate caches and annotation mappings. Record row counts, distinct values and average sizes. This identifies duplicated strings/objects or index combinations rather than inferring waste from total size alone.
3. **Normalized costs:** total and added bytes/epoch; bytes/epoch-field link; added-index/base-metadata ratio; metadata/raw-recording ratio with an explicit numerator and denominator. Also report incremental bytes per newly imported epoch/source and per new field/value where that workload is tested.
4. **Lifecycle high-water:** maximum disk during construction/rebuild, staging and simultaneous old/new generations, then steady-state disk after reader-safe cleanup. Measure retained-cache/generation limits so repeated use does not accumulate unbounded mapping copies.
5. **Growth:** original real dataset plus deterministic, recorded intermediate replays (for example around 100k) and the required exact million. Retain field mix, source distribution and whole-block selection; report identity length, ancestry/value cardinality and compression/layout differences. Detect increasing bytes/epoch or relationship that lacks an explained schema/cardinality change.

Use the measured full-index candidate as the speed/storage comparator. Storage increases require a documented reason and paired benefit, with the exact added bytes and growth impact visible. Avoid creating every field combination as a separate index, copying full parent objects or inherited tags into every epoch, caching full membership for every query, or retaining unlimited generations. Keep full scientific fidelity; do not discard metadata to improve a ratio.

## Raw-recording denominator must be honest

Report these separately:

- **Actual source/project ratio:** count distinct accessible original recording files once, verify source identity, and report their actual physical bytes alongside metadata for that same original dataset. Where practical, distinguish waveform/stimulus payload from container metadata.
- **Replay stress footprint:** report the actual million metadata bytes and any physically present recording bytes. The replay references reused original recordings; it does not create a million new H5 recordings. A metadata/reused-H5 ratio is a stress-fixture property, not a real million-acquisition product ratio.
- **Projected acquisition ratio, if needed:** derive a clearly labeled estimate from actual recorded response/stimulus payload sizes and exact replay lineage, including the partial tail. It is an estimate, not physical storage, and must not blindly multiply full source file sizes or claim new readable traces exist.

The user's storage objective is now a required integration/regression dimension. No arbitrary universal percentage cap is certified by today's data: establish the same-corpus total and incremental baselines, investigate disproportionate growth, and justify any storage tradeoff together with speed. The follow-up supplies source/projection ratios; the full canonical project footprint, controlled growth curve and lifecycle high-water measurements remain open.
