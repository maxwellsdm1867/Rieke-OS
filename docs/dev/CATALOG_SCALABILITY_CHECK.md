# Catalog scalability check

Measured locally with disposable, in-memory synthetic metadata: one protocol,
100 epochs per cell, 20 per block, and 50 discovered fields. No H5 samples,
DataJoint connection, production edits, or browser timing were involved.

| Epochs | Field catalog before | Field catalog after | Predicate choices before | Predicate choices after |
| --- | ---: | ---: | ---: | ---: |
| 10,000 | 2.8747 s | 0.6281 s | 1.5357 s | 0.3726 s |
| 50,000 | 16.1626 s | 3.5375 s | 7.4252 s | 1.6936 s |

These are individual runs, not statistical performance guarantees. The
before/after runs used the same inputs and checked exact field catalog,
per-epoch values, predicate choices, and rendered tree equality. The raw run
record is `/tmp/rieke-catalog-parity-benchmark.json` for this development session.

Changes resolve escaped field paths and labels once per catalog build, stop
within-cell variation checks after a positive proof, and use bounded typed
hash buckets for predicate choices. A 4,096-entry scalar JSON-key cache avoids
repeated serialization. It preserves tree distinctions between integer/float
JSON, Boolean values, strings, null, and signed zero. Predicate equality still
merges numerically equal integers/floats while keeping Boolean values distinct.
Known but absent fields remain in the schema. Tests also retain the exact
pre-change catalog fixture hash and compare choice counts with the old linear
algorithm, including truncation and nested typed values.

## Remaining limits

This change does **not** make tree transport lazy. The 50,000-epoch
date/cell/block tree still serialized to **14,846,420 bytes**, unchanged from
before. The wire representation includes every branch, leaf UUID, and leaf
epoch object; a predicate preview additionally carries exact membership and
fingerprints. High-cardinality split fields can create many more branches.
Browser paging of visible rows does not bound backend construction or payload
size. A future compact/lazy representation must retain exact epoch identities,
typed branch paths, shared cell focus, and explicit complete membership for
saved revisions. No claim of 50,000-epoch browser responsiveness follows from
these backend measurements.
