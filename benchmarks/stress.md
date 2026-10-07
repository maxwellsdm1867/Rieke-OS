# Separate stress track

The registered `everyday-million` query lane is required after every app update
and implementation iteration, alongside the unchanged fixed core correctness
cases. Follow the canonical [run and comparison workflow](../docs/dev/benchmarks.md#required-everyday-query-check-after-every-app-update): preserve a pinned
regression baseline and previous iteration, run matched baseline/candidate sources
serially with the current harness, and retain failed as well as passed evidence.
Missing, failed or incomparable runs cannot mark an iteration green. This is a
development requirement enforced by the [everyday-million workflow](../.github/workflows/everyday-million.yml)
on all pull requests and main/master pushes. The same job also runs fixed core
correctness and complements existing correctness CI; it does not change the release gate. See the canonical guide for baseline
selection, failure artifacts and CI limitations.

The lane uses actual million-record synthetic metadata fixtures with production
tree/query methods. Tree catalog admission is synthetic; typed SQLite relations
are in memory and bypass disk/seal admission. Setup and memory are reported apart
from query timing. It does not cover native/UI, lifecycle/recovery or release
qualification. Provisional comparison triggers require investigation, not a claim
of universal latency coverage. Registry configuration remains solely in
[registry.json](registry.json), under `stress_tracks.everyday-million`.

Other stress work remains separately coordinated and opt-in. Core is fixed and intentionally small. Do not increase its data volume or change
sampling silently. Use the existing `tools/metadata_qualification` scale tools and
qualification-plan action ledger for separate, explicitly coordinated stress runs.
`million_batch.py`, `million_controls.py`, `million_storage.py` and `timing.py`
already define capped serial workers and independent lineage/seal gates. Their
private corpus is not a reproducible public core fixture and is never auto-opened
by `tools/benchmark.py`. Read their README before any execution.

Required future distributions: 10k/50k/1m records, wide/rare fields, 0/1/1%/50%/all
matches, first/deep grouped pages, tags/frozen exports/import stages, source and
annotation revision changes, bounded memory, contention, startup/recovery, long
navigation loops. Record exact corpus and expected membership hashes, sample
method, assets, hardware, all cost phases and cleanup. Never extrapolate twelve
records into a scalability claim. See the database design note for adaptive-index
comparisons; adaptive indexing remains design only.
