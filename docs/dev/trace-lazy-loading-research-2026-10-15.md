# Trace loading strategies and the 50 ms target

Research date: 2026-10-14 (America/Los_Angeles); evidence timestamps use UTC. The contiguous-read and retained-cache experiments below have now been measured. Their results favor bounded preparation over further first-pass API tuning; process parallelism remains unmeasured. Do not implement display caches, sidecars or preprocessing in this investigation.

## What the measurements establish

Nine serial measurements after a full warmup reduced one-million-sample read plus encoding from **252.889 to 162.434 ms**. H5 slicing still takes **152.875 ms**; binary encoding takes **0.925 ms**. Every payload matched the independent expected 8,000,000 bytes, including signed zero. The owned fixture uses gzip level 4, 64-record chunks and compound `<f8 quantity + S10 units`; this means 15,625 chunks and 18 MB of uncompressed compound records for one million samples. These are calculations from the recorded layout, not measurements of disk traffic. [Measurement conditions and medians](../../../evidence/direct-recovery/million-loading/README.md), [fixture](../../../evidence/direct-recovery/million-loading/fixture.json), [candidate rows and exact source hashes](../../../evidence/direct-recovery/million-loading/candidate.json).

This is **OS-warm, reopened-handle loading**, with no HTTP, native SQL scope, browser decode or drawing. It is not cold storage performance or complete display latency. Stage medians are independent. The target remains **under 50 ms from intent to complete correct display of the entire one-million-sample interval**, with exact raw samples available; showing a partial trace sooner does not meet it. The measured loading path alone misses that target by over threefold. The earlier 300k native measurement is a different workload.

Keep four conditions separate: first uncached access (cache state must be documented, not assumed from a fresh process); OS-warm with reopened dataset; retained HDF5 dataset; decoded-array revisit/prefetch hit. Only the second has the measurements above.

## Ranked experiments without prepared data

| Priority | Experiment and reason | First-load relevance; cost and falsification |
|---|---|---|
| 1 | Read the bounded million-record interval once, then validate and split its detached numeric buffer into wire windows. Compare slicing with a preallocated compound `read_direct` destination. h5py says `read_direct` can avoid a slicing intermediate and requires writable contiguous storage. | Could reduce call/allocation work on a miss, but still reads every compressed chunk. A full compound destination is 18 MB, plus the 8 MB numeric payload; measure peak memory as well as complete latency. Reject if exact units/float64 bytes or closing witnesses differ. [h5py dataset API](https://docs.h5py.org/en/stable/high/dataset.html#h5py.Dataset.read_direct) |
| 2 | Sweep raw chunk caching: disabled, default and explicitly sized `rdcc_nbytes`/`rdcc_nslots`, on identical reads. h5py exposes byte capacity, hash slots and eviction weighting; defaults depend on the HDF5 version. Record actual runtime settings. | A sequential first pass may benefit little from a larger cache; do not import spectacular gains from examples with different layouts. Test held-dataset revisits separately. Memory grows with each open dataset's cache. [h5py cache controls](https://docs.h5py.org/en/stable/high/file.html#chunk-cache), [HDF Group performance guide](https://support.hdfgroup.org/documentation/hdf5/latest/improve_compressed_perf.html) |
| 3 | Benchmark two and four persistent reader processes, each opening its own read-only handle and reading disjoint chunk-aligned ranges. h5py explicitly supports independent-process readers and cautions against opening then forking. | Potential first-request throughput improvement if chunk handling/decompression dominates; no promised speedup. Include queueing, process startup as a separate condition, IPC/copies, merge and final authority verification. More processes consume more memory and can contend for storage. [h5py process guidance](https://docs.h5py.org/en/stable/mpi.html) |
| 4 | Project compound fields only if correctness permits. `fields('quantity')` reads a field subset; `dataset[:]['quantity']` first reads all fields. | Lower application-buffer volume is possible; compressed chunks still require decompression. Disco must validate every unit, so quantity-only reading cannot silently replace the current contract; a separate unit pass may erase any gain. [h5py compound fields](https://docs.h5py.org/en/stable/high/dataset.html#reading-writing-data), [HDF5 compressed-chunk behavior](https://support.hdfgroup.org/documentation/hdf5/latest/improve_compressed_perf.html) |

The 64-record chunks are only 1,152 uncompressed bytes each. HDF Group identifies overhead from many small chunks, and explains that cached chunks are discarded when their dataset closes. Thus retaining only a filename or repeatedly reopening the dataset does not retain its decoded chunk cache. Holding a dataset could improve revisits, but must have a bounded handle/memory lifetime and revalidate source replacement; it cannot eliminate the first decompression pass. This is a proposed experiment, not an implemented cache. [HDF Group chunk/cache analysis](https://support.hdfgroup.org/documentation/hdf5/latest/improve_compressed_perf.html).

Do not spend time adding a pool of h5py reader **threads** for parallel reads: h5py's interpreter-wide `phil` lock serializes its API calls even across different files. Threads can pipeline HDF5 with non-HDF5 work, but the measured encoding stage is already below 1 ms. [h5py threading](https://docs.h5py.org/en/stable/threads.html).

## Strategies that move work before the click

**Decoded LRU and directional prefetch — proposal only.** A byte-budgeted least-recently-used store could retain exact numeric arrays; Python documents ordered-map LRU patterns. Budget actual buffers, including shared backing buffers, not just entry count: one million float64 values require 8 MB before metadata and temporary copies. Key by source identity, epoch, stream, range and conversion contract; reattest current frozen membership separately. A conservative navigation proposal is one next stream in the current direction, only after foreground work completes, evicting unused speculative data first. Hits can remove read/decode work; misses and unpredictable first selections cannot. [Python LRU recipes](https://docs.python.org/3/library/collections.html#ordereddict-examples-and-recipes).

Cancel obsolete fetches and reject stale completions by request identity. AbortSignal propagates cancellation to participating APIs; fetch defines response/body abort behavior. Neither specification proves that a running Python/HDF5 read stops when the browser aborts. Server work needs its own cooperative cancellation points; measure wasted bytes/CPU and foreground interference. [DOM cancellation](https://dom.spec.whatwg.org/#aborting-ongoing-activities), [Fetch abort](https://fetch.spec.whatwg.org/#abort-fetch). No prefetch/cache is implemented or selected here.

**Exact disk preparation — comparison only.** Rechunking or an uncompressed numeric sidecar could avoid the original tiny-gzip-chunk path, at the cost of an initial complete read/write and extra disk space. HDF5 documents repacking and chunk-layout tradeoffs; NumPy memory maps provide partial access to a suitable binary file, not direct decompression of arbitrary H5 datasets. An uncompressed numeric copy adds roughly 8 MB per million samples plus identity/units metadata. This would require a separately reviewed disposable-derived-data contract; original recordings remain authoritative. [HDF5 repacking discussion](https://support.hdfgroup.org/documentation/hdf5/latest/improve_compressed_perf.html), [NumPy memmap](https://numpy.org/doc/stable/reference/generated/numpy.memmap.html). No sidecar was created.

## Display-oriented alternatives are different objectives

A zoomed viewport can request only its exact interval using HDF5 hyperslab slicing. At whole-stream view, however, reading fewer samples without a precomputed summary cannot establish all extrema. M4 retains first/last/minimum/maximum per pixel column; its raster-equivalence argument has a particular rendering model, not a guarantee for Disco's antialiased Canvas. A multiresolution summary can answer display queries quickly **after preparation**, but still needs original values for exact cursor/zoom and independent gap/extrema validation. [h5py slicing](https://docs.h5py.org/en/stable/high/dataset.html#reading-writing-data), [M4 primary paper](https://www.vldb.org/pvldb/vol7/p797-jugel.pdf).

MinMaxLTTB accelerates representative point selection through MinMax preselection. It is display downsampling, not retention of every point in the plotted path or proof of identical pixels. A summary-only initial frame must be labeled separately from complete exact-sample availability. These strategies are not proposed for implementation under the current no-display-cache constraint. [MinMaxLTTB primary paper](https://arxiv.org/abs/2305.00332).

WebGL uploads buffers and issues drawing commands; it does not remove the preceding HDF5 read. With 152.9 ms spent slicing, faster drawing alone cannot make this measured path finish below 50 ms. GPU upload, display-coordinate conversion, context loss and final presentation also need measurement; preserve float64 raw data regardless of GPU display representation. [WebGL buffer and rendering API](https://registry.khronos.org/webgl/specs/latest/1.0/).

## Decision rule

Run experiments 1–2 on the owned gzip64 million-sample fixture, serially with matched current-source controls; keep failures and cache conditions. Require identical payload bytes, units, provenance, bounded memory, source-change refusal and no partial publication. Measure experiment 3 only if the first two leave decompression dominant. Then run the complete browser/native path with the same million-sample input. Record first post-stroke and second stable-frame observations separately; neither is a compositor-photon measurement. Do not claim the 50 ms target from an encoding microbenchmark, a cache hit, a 300k recording or an early partial paint.

## Measured follow-up: loading strategy comparison

The same owned million-sample fixture was used for nine serial samples per variant, validating every unit and all 8 MB of exact numeric values. OS cache was warm; no OS-cold claim is made.

| Strategy | Median read/check/encoding cost | Qualification |
| --- | ---: | --- |
| Ten bounded windows, one handle | 161.81 ms | First H5 pass, reopened handle |
| One full slice | 160.56 ms | First H5 pass, reopened handle |
| Preallocated compound read_direct | 153.76 ms | First H5 pass, reopened handle |
| Quantity and units in separate field reads | 330.87 ms | All-unit validation included |
| Retained default H5 cache | 161.68 ms | Subsequent read |
| Retained 32 MiB H5 cache | 30.93–32.63 ms | Subsequent read; first pass 160.80–192.14 ms |
| Decoded RAM buffer: copy, finite validation and raw encoding | 0.622 ms | Prepared-data operation only; excludes population, source/scope revalidation, HTTP and painting |

Raw evidence, including the slower first-pass cache result and cache-slot variants, is in [read-variants-summary.md](../../../evidence/direct-recovery/million-loading/read-variants-summary.md). These are proposed strategies, not implemented application caches. The 50 ms complete-display target is not established by any row.
