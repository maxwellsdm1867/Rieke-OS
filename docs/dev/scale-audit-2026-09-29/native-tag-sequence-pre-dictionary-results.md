# Native SQL tag workflow validation

The final native SQL runs pass at 500 and 100,000 epochs using the same verified source snapshot. Exact-membership, author/revision, hierarchy, removal, recovery-mirror and native-index checks pass. Neither run calls the legacy SQLite tag membership or refresh path.

Performance is mixed. The 500-epoch two-save/filter sequence improves from 73.6 to 69.3 ms, while the 100k sequence measures 203.0 ms versus the prior 166.0 ms. At 100k, prefix autocomplete still takes 3.3–3.7 seconds and an empty query takes 11.2 seconds. Passing correctness checks does not establish that the responsiveness work is complete.

Each fixture has three profiles, five seeded tags per annotation, cell annotations, and two independent protocol curation scopes. Five complete cycles read revisions and durably tag 10 epochs, read revisions and tag another 10 in another cell, then immediately filter the exact 20.

| Operation (median milliseconds) | 500 prior | 500 native | 100k prior | 100k native |
|---|---:|---:|---:|---:|
| First 10 epochs: durable POST | 15.2 | 17.7 | 17.6 | 25.0 |
| Next 10 epochs: durable POST | 13.4 | 16.9 | 16.2 | 23.9 |
| Filter after the two saves: exactly 20 epochs | 31.1 | 23.2 | 119.2 | 126.0 |
| Two revision reads + two saves + filter | 73.6 | 69.3 | 166.0 | 203.0 |
| One cell: durable POST | 6.7 | 7.5 | 7.8 | 8.8 |
| Cell filter: exactly 100 inherited epochs | 41.5 | 38.8 | 129.8 | 160.0 |
| Cell AND epoch filter: exactly 10 epochs | 17.4 | 18.3 | 106.2 | 124.8 |
| Cell save + cell filter | 48.1 | 46.3 | 137.8 | 168.2 |

The total uses paired per-cycle timings and includes both revision reads. POST timing ends after canonical MySQL save acknowledgment. The separately scheduled recovery mirror is flushed and checked after the operations. Timings include Flask HTTP client JSON decoding, not browser interaction or paint.

The first filter request after seeding took 27.2 ms at 500 epochs and 227.2 ms at 100k; the first full sequences took 92.9 and 327.7 ms. Native application startup performs its metadata preparation; the harness performs no preparatory tag query or SQLite tag checkpoint after seeding. These are not cold MySQL/OS-cache measurements. Five samples do not establish tail-latency guarantees.

## Index, persistence and correctness

The actual 20-epoch filter uses the persistent `by_tag` covering index with `ref` access and an estimate of 20 lookup rows at both scales. Both runs distinguish `QC` from `qc` and NFC `é` from decomposed `é`; they verify AND, OR, NOT, inherited cell membership, direct-only epoch scope, exact author chips and revisions. Cell tagging changes one canonical cell record and creates no child annotation copies; both protocol curation scopes remain unchanged.

A fresh Python lookup adapter reuses the persistent SQL table in the same server. Its exact-20 filter takes 20.7/138.5 ms at 500/100k. This is not a MySQL process restart. Initial preparation timing in the raw receipts precedes annotation seeding and is not a populated legacy-database migration benchmark.

Both final backup receipts are `current`, with no pending/running work or error, and requested/completed sequence 34. The flushed recovery mirror matches all 63 tracked canonical records, including final removals. Both owned native servers stopped successfully.

## Autocomplete diagnostic

After the timed workflow, two calls use `q=gate&limit=12` and a third uses an empty query with `limit=12`. An independent seeded oracle verifies exact counts and profile authors for all returned tags. Each is one observation; first/repeated labels do not mean cold/warm storage.

| Scale | First gate-prefix ms | Repeated gate-prefix ms | Empty query ms |
|---|---:|---:|---:|
| 500 | 23.3 | 29.4 | 33.3 |
| 100,000 | 3740.4 | 3255.9 | 11217.5 |

The final query shape reads the tag dictionary through `by_tag`, filters the dictionary with the existing Unicode casefold prefix semantics, counts matching memberships through `by_tag`, and reads the chosen authors through complete literal canonical keys. The empty query still counts the complete vocabulary. Actual SQL, per-statement timings and EXPLAIN output are in each receipt.

The 100k optimizer chooses a covering project-prefix scan for the dictionary (`by_tag`, `ref`, 827,077 estimated rows), not a loose distinct-tag scan. That query takes 3.0–3.5 seconds and dominates prefix autocomplete. The bounded prefix count and winning-position queries each take roughly 0.1 second; complete primary-key author reads take less than 1 ms (`PRIMARY`, key length 331, three chosen rows). For the empty query, counts and winning positions additionally take about 4.1 seconds each. No manual `ANALYZE` or other query-plan preparation was added to this benchmark.

| Scale/request | SQL statement durations (ms, execution order) |
|---|---|
| 500 / cold | 1.9 / 0.5 / 0.8 / 0.3 |
| 500 / warm | 1.9 / 0.5 / 0.7 / 0.2 |
| 500 / empty | 1.9 / 5.2 / 6.0 / 0.3 |
| 100,000 / cold | 3526.6 / 84.4 / 102.4 / 0.4 |
| 100,000 / warm | 3035.7 / 93.4 / 101.8 / 0.4 |
| 100,000 / empty | 2991.6 / 4095.7 / 4103.2 / 0.6 |

## Reproducible evidence

- [Final 500-epoch receipt](native-tag-sequence-pre-dictionary-500.json) and [final 100,000-epoch receipt](native-tag-sequence-pre-dictionary-100000.json).
- [Prior SQLite 500-epoch receipt](tag-sequence-after-500.json) and [prior 100,000-epoch receipt](tag-sequence-after-100000.json).
- [Native harness](benchmark_native_tag_sequence.py), [machine-readable comparison](native-tag-sequence-pre-dictionary-results.json), and [source snapshot manifest](native-tag-source-pre-dictionary-snapshot.json).
- [Preserved provisional pre-autocomplete-fix report](native-tag-sequence-pre-autocompletefix-results.md): 100k correctness passed, but concurrent source edits invalidated its overall receipt; its gate-prefix autocomplete took 9–10 seconds.

The final runs used one private copy of Python/config, the three harness dependencies, frontend source/package metadata needed by audit fingerprints, and retinanalysis source. The existing pinned runtime binaries were reused. Copy-time source/copy hashes matched; every copied file remained unchanged through both final runs. Both receipts additionally attest identical before/after Python inventories, harness hashes and loaded-module paths. Concurrent edits in the working checkout do not alter this measured snapshot.

Native harness SHA-256: `468173271c08020e7e1a7ce8b0fcdfc59693be0f9e3699a8caec342b2e77affd`.

These receipts validate the stated workflow and checks; they do not certify a complete desktop release.
