# Native SQL tag workflow validation

The final native SQL runs pass at 500 and 100,000 epochs using the same verified source snapshot. Exact-membership, author/revision, hierarchy, removal, recovery-mirror and native-index checks pass. Neither run calls the legacy SQLite tag membership or refresh path. At 100k, autocomplete now takes 21–26 ms, versus 3.3–3.7 seconds for a prefix and 11.2 seconds for an empty query before the compact dictionary.

Each fixture has three profiles, five seeded tags per annotation, cell annotations, and two independent protocol curation scopes. Canonical rows are bulk-seeded before normal application startup installs and backfills native tag structures. No triggers are disabled for timed operations. Five complete cycles read revisions and durably tag 10 epochs, read revisions and tag another 10 in another cell, then immediately filter the exact 20.

| Operation (median milliseconds) | 500 prior | 500 native | 100k prior | 100k native |
|---|---:|---:|---:|---:|
| First 10 epochs: durable POST | 15.2 | 20.5 | 17.6 | 20.7 |
| Next 10 epochs: durable POST | 13.4 | 20.0 | 16.2 | 24.3 |
| Filter after the two saves: exactly 20 epochs | 31.1 | 24.4 | 119.2 | 128.2 |
| Two revision reads + two saves + filter | 73.6 | 77.5 | 166.0 | 191.6 |
| One cell: durable POST | 6.7 | 8.3 | 7.8 | 8.0 |
| Cell filter: exactly 100 inherited epochs | 41.5 | 43.7 | 129.8 | 157.0 |
| Cell AND epoch filter: exactly 10 epochs | 17.4 | 22.3 | 106.2 | 115.2 |
| Cell save + cell filter | 48.1 | 51.8 | 137.8 | 165.0 |

The broader save/filter workflow has not become uniformly faster: its 100k median is 191.6 ms versus the prior 166.0 ms. The native point lookup is indexed, while other metadata and response work remains. The total uses paired per-cycle timings and includes both revision reads. POST timing ends after canonical MySQL save acknowledgment. The separately scheduled recovery mirror is flushed and checked after the operations. Timings include Flask HTTP client JSON decoding, not browser interaction or paint.

The first filter request after seeding took 33.1 ms at 500 epochs and 231.9 ms at 100k; the first full sequences took 117.0 and 331.8 ms. Native application startup performs its metadata preparation; the harness performs no preparatory tag query or SQLite tag checkpoint after seeding. These are not cold MySQL/OS-cache measurements. Five samples do not establish tail-latency guarantees.

## Index, persistence and correctness

The actual 20-epoch filter uses the persistent `by_tag` covering index with `ref` access and an estimate of 20 lookup rows at both scales. Both runs distinguish `QC` from `qc` and NFC `é` from decomposed `é`; they verify AND, OR, NOT, inherited cell membership, direct-only epoch scope, exact author chips and revisions. Cell tagging changes one canonical cell record and creates no child annotation copies; both protocol curation scopes remain unchanged.

A fresh Python lookup adapter reuses the persistent SQL table in the same server. Its exact-20 filter takes 26.9/120.2 ms at 500/100k. This is not a MySQL process restart. Initial preparation now measures normal startup on the populated canonical fixture, including native backfill, content proof and bounded protocol preparation. The raw receipt separately records total application startup and canonical fixture construction.

The populated migration cost is explicit: canonical seeding took 0.089/14.419 seconds at 500/100k; normal application startup took 1.003/144.543 seconds, including 0.436/128.952 seconds in native annotation preparation. At 100k this creates lookup/dictionary structures for 303,000 canonical shared-annotation records. Subsequent same-server preparation with a fresh lookup adapter reused those structures in 0.182 seconds; this does not measure a full desktop restart.

Both final backup receipts are `current`, with no pending/running work or error, and requested/completed sequence 34. The flushed recovery mirror matches all 63 tracked canonical records, including final removals. Both owned native servers stopped successfully.

## Autocomplete diagnostic

After the timed workflow, two calls use `q=gate&limit=12` and a third uses an empty query with `limit=12`. An independent seeded oracle verifies exact counts and profile authors for all returned tags. Each is one observation; first/repeated labels do not mean cold/warm storage.

| Scale | First gate-prefix ms | Repeated gate-prefix ms | Empty query ms |
|---|---:|---:|---:|
| 500 | 21.6 | 25.0 | 30.3 |
| 100,000 | 22.3 | 20.9 | 25.8 |

Autocomplete now queries the persisted compact dictionary with maintained distinct-target counts and stored Unicode fold keys. Profile references come from the compact author table; any membership reads are bounded `by_tag` winner seeks returning at most one row, followed by complete canonical primary-key reads. Harness gates reject membership aggregates and unbounded dictionary row fetches. An exact total may count matching compact dictionary entries. Actual SQL, returned row counts, per-statement timings and EXPLAIN output are preserved.

At 100k, prefix count/ranking uses `by_prefix` range access over three dictionary entries. Empty-query ranking uses `by_rank` with a 12-row limit; its exact total counts 41 compact dictionary entries. Membership winner reads use `by_tag` with project/tag/profile keys, backward index traversal and `LIMIT 1`; canonical author reads use the full primary key (length 331). There is no membership aggregation or unbounded dictionary fetch into Python.

| 100k request | Traced tag SQL statements | Combined tag SQL time | Slowest statement |
|---|---:|---:|---:|
| First gate prefix | 8 | 1.22 ms | 0.19 ms |
| Repeated gate prefix | 8 | 1.27 ms | 0.20 ms |
| Empty query | 29 | 4.28 ms | 0.31 ms |

## Reproducible evidence

- [Final 500-epoch receipt](native-tag-sequence-500.json) and [final 100,000-epoch receipt](native-tag-sequence-100000.json).
- [Prior SQLite 500-epoch receipt](tag-sequence-after-500.json) and [prior 100,000-epoch receipt](tag-sequence-after-100000.json).
- [Native harness](benchmark_native_tag_sequence.py), [machine-readable comparison](native-tag-sequence-results.json), and [source snapshot manifest](native-tag-source-snapshot.json).
- [Pre-dictionary baseline](native-tag-sequence-pre-dictionary-results.md): immutable-source correctness passed, but 100k prefix autocomplete took 3.3–3.7 seconds and empty autocomplete 11.2 seconds. The earlier [provisional report](native-tag-sequence-pre-autocompletefix-results.md) remains preserved with its source-change limitation.

The final runs used one private copy of Python/config, the three harness dependencies, frontend source/package metadata needed by audit fingerprints, and retinanalysis source. The existing pinned runtime binaries were reused. Copy-time source/copy hashes matched; every copied file remained unchanged through both final runs. Both receipts additionally attest identical before/after Python inventories, harness hashes and loaded-module paths. Concurrent edits in the working checkout do not alter this measured snapshot.

Native harness SHA-256: `26d058c7a3b9c5f67071e38d70df66a566b37cef7b543656b0bcb521c04df133`.

These receipts validate the stated workflow and checks; they do not certify a complete desktop release.
