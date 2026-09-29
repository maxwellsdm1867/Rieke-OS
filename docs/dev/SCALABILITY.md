# Large-project performance

The target workload is tens of thousands of epochs. A responsive interface must
not depend on rendering every epoch or rereading every H5 on each interaction.
Synthetic measurements are kept separate from research-data validation and from
browser responsiveness claims.

## Implemented architecture

The service now maintains a **disposable, sealed SQLite metadata index** under
`cache/metadata/<generation>.sqlite`. DataJoint registrations, validated metadata
manifests, raw H5 files, and saved dataset revisions remain authoritative. The
index does not change the Wheeler export schema or scientific selections.

- A generation binds the project, source registration/manifest, metadata checksum,
  filesystem signatures, and index/tree/predicate implementation checksums.
  Unchanged generations reuse the current index or reopen a matching disk index
  after restart. Reopen verifies its SHA256 seal, format, project, generation,
  completeness, and SQLite integrity before use.
- Detailed epoch metadata is compressed in SQLite and loaded through a bounded,
  thread-safe cache. Warm restart obtains lightweight source rows and fingerprints
  directly from the verified index, decoding only one epoch per cell for cell
  descriptors. It does not first deserialize every source's complete JSON
  projection. Lightweight rows, cell summaries, and some membership lists still
  occupy memory.
- Typed values are stored once per field/value combination, with epoch links.
  Predicate matching uses the existing typed comparison rules over distinct
  values; booleans, numbers, strings, arrays, absent fields, and recorded nulls
  retain their semantics. Tree grouping retains exact recorded JSON identities.
  Catalog summaries and predicate choices persist in the sealed index. Tree-page
  requests project only fields needed for the requested branch.
- The Inspector and Explorer use server-paged trees: grouped counts and opaque
  branch paths are fetched on demand, and epoch leaves are paginated. An anchor
  request can locate an epoch outside the visible page. Revision checks prevent
  mixing pages or previews from different scopes. Grouping and navigation never
  alter dataset membership.
- Explorer requests compact previews and revision summaries. Full epoch/diff
  arrays remain server-side; navigation snapshots retain conditions, grouping,
  counts, focus, and revision IDs rather than copying full membership arrays.
  The legacy complete-tree/full-recipe APIs remain available to other consumers.
- Project/protocol cell counts aggregate epochs in one pass. Large curation reads
  avoid an OR expression containing every epoch identity. Lossless HTTP gzip
  remains available for JSON; it is separate from server paging.
- Predicate drafts stay local until Preview. Search/tree requests debounce and
  obsolete requests are aborted. Trace gestures redraw locally and request a
  bounded sample window on release. Raw waveform samples remain lazy.

The final combined verification for this implementation passed **348 Python tests,
107 frontend tests, and the production frontend build**. These checks establish
contracts and regressions; they are not a 50,000-epoch browser latency guarantee.

## Current disk-index benchmark

The exact measurements are in [DISK_METADATA_INDEX_BENCHMARK.json](DISK_METADATA_INDEX_BENCHMARK.json).
Reproduce them with [benchmark_disk_metadata_index.py](benchmark_disk_metadata_index.py),
which generates disposable metadata and writes only a temporary derived index:

```sh
PYTHONPATH=python python docs/dev/benchmark_disk_metadata_index.py 50000 140
```

| Operation | 50,000 epochs × 140 fields |
| --- | ---: |
| Cold index build, including catalog construction | 63.37 s |
| SHA-verified reopen and cached catalog | 1.60 s |
| Three-column tree projection | 0.495 s |
| Typed predicate matching | 0.105 s |
| Index file | 238.0 MB |
| Peak process resident memory | 158.1 MB |

This fixture lazily generates parameter metadata. Peak memory includes its
lightweight input rows and a retained three-column projection. It is **not the
same workload** as the earlier eager 140-field service fixture below, so the
memory numbers do not establish a direct before/after app-memory ratio. These
are metadata-only process measurements, not live SQL/H5/browser end-to-end
measurements. The captured benchmark predates the final lazy source-projection
and cached-length changes; those changes have separate parity/concurrency tests.

## Historical benchmark method and results

`python/benchmark_workspace_metadata.py` builds disposable 10,000- and
50,000-epoch catalogs with cells, blocks, protocols, typed parameters, and response
pointers. It measures overview, query, paged epochs, cold/warm tree discovery,
predicate fields, and filtered preview. It records payload sizes and process
resident memory. It reads no waveforms and performs no SQL/research mutations.

The initial 50,000-epoch fixture showed 22.11 s for cold tree/field discovery,
16.68 s for cold predicate field discovery, 0.49 s for a warm tree, and 27 ms for
a 100-epoch page. Its complete tree serialized to 18.43 MB. These measurements
identified field discovery, duplicate indexes, and full-tree transfer as the
first targets; they are not end-to-end UI timings.

Historical in-memory optimization results, using the same 50,000-epoch synthetic fixture:

| Operation | Before | After |
| --- | ---: | ---: |
| Cold project tree and field discovery | 22.11 s | 3.35 s |
| Cold predicate fields | 16.68 s | 0.89 s |
| Warm tree | 0.49 s | 0.42 s |
| Filtered preview | 3.26 s | 1.29 s |
| Resident memory after queries | 955 MiB | 701 MiB |

The 18.43 MB full tree compressed to approximately 1.20 MB in 36 ms. Synthetic
sequential UUIDs compress well; real recording identities will differ. The live
173-epoch history tree compressed from 73,183 to 11,829 bytes with exact decoded
JSON equality. Its real tree navigation and bounded raw traces were checked in
the browser. At that earlier checkpoint, 312 Python tests, 98 frontend tests, and the production build
passed. See the adjacent `scale_50000_*` and `live_scale_validation.json` files.

The first fixture had 37 discovered fields. A denser follow-up matched the real
project's **140 discovered fields** at 50,000 synthetic epochs:

| Operation | Dense fixture |
| --- | ---: |
| Overview | 0.42 s |
| 100-epoch page | 0.028 s |
| Cold tree/field discovery | 10.52 s |
| Warm tree | 0.48 s |
| Cold predicate fields | 5.76 s |
| Warm predicate fields | <0.001 s |
| Filtered preview | 4.03 s |
| Resident memory after queries | 1,345 MiB |

This process completed within an enforced 180-second timeout. Memory figures are
sampled measurements; no continuous memory kill limit was enforced. The field
density test demonstrates why warm latency alone is insufficient: startup,
complex previews, and memory remain material limits. `scale_50000_140fields.json`
contains the complete measurement. These are metadata-only process timings,
not a 50,000-epoch live SQL/H5/browser end-to-end certification.

## Remaining architectural limits

The SQLite index is disk-backed, but the complete system is not constant-memory.
Lightweight epoch rows, fingerprints, current protocol membership, and candidate
membership comparisons still scale with project size. Tree pages bound response
and browser rendering size; branch grouping can still scan the selected rows and
projected columns. Legacy full-tree/full-recipe callers can still request large
responses. Exact export membership remains in saved server-side revisions.

An unchanged generation is reused. A changed generation currently rebuilds the
**whole derived metadata index**, even when unchanged source projections can be
reused. Rebuilding only affected SQL index partitions is not implemented.
Compressed per-source projection caches also persist on disk and may be decoded
when a matching complete index is unavailable.

Initial index construction and changed-generation rebuilding still block the
service load/refresh path. The service records an indexing phase, but construction
is not yet a fully background, user-visible progress job. The 63-second cold
synthetic build is therefore a material first-load limitation, not a warm-latency
result to hide. Reopen also performs a full index checksum read.

Refresh publishes a complete validated generation or fails closed; an absent or
invalid disposable index can be rebuilt from verified inputs. It cannot silently
substitute stale scientific membership. Continue measuring cold startup,
changed-generation rebuilding, query complexity, disk size, and browser behavior
separately. No current result establishes that every operation is instantaneous
on a 50,000-epoch project.

Latest read-only production-project proof is in
[disk_index_live_validation.json](disk_index_live_validation.json): 1,776 epochs,
8 cells, and 2 sources. Restart succeeded with complete source-projection decoding
and H5 access deliberately blocked, with exact catalog and all typed-value parity
and unchanged fingerprints. Index reopen took 47 ms; total startup was 3.30 s
(including 2.72 s of SQL checks). Unchanged refresh took 415 ms, including 331 ms
of SQL checks. These are measurements of this project, not 50,000-epoch timings.
The test counts above describe the documented verification checkpoint.
