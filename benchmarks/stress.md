# Separate stress track

Core is fixed and intentionally small. Do not increase its data volume or change
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
