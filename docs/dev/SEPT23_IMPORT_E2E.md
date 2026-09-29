# September 23 recording: real import → Add → exports

Verified on 2026-09-27 in the local Rieke OS / Spike Response Model project.

## User-visible path

1. Used **Data stores → Add H5 → Choose H5 file** to upload `/Users/maxwellsdm/Downloads/2026-09-23_F.h5` into managed storage.
2. Import completed with **5 cells / 690 epochs**, source validation and SHA256 registration. Main catalog now contains **8 cells / 1,776 epochs / 2 sources**.
3. Saved protocol queries ran automatically. History Noise offered **+2 cells / +72 epochs**. Mean Noise correctly offered no update. Supporting protocols have three pending proposals.
4. Clicked **Add matched data** once. History working dataset advanced from version 1 (101 epochs) to version 2 (**173 epochs / 4 cells**). The old immutable baseline remains available. Manual inspection is optional.
5. Created both exports from the protocol UI. Each saves its query, exact epoch membership, source hashes and provenance. HTTP download bytes match receipt hashes.
6. Submitted the same file by its original local path. It was recognized by contents and skipped before parsing; no duplicate rows, baselines or suggestions were created.

## Scientific and integrity checks

- Source SHA256: `63d48aeab9344cce6665a9a752f836a797d8c136211202482cce4f72f501003e`. Managed copy matches; original contents, size and modification time unchanged.
- History membership equals the exact raw-H5 UUID union: 101 existing + 72 new. Cell counts: Sep24 Cell1 49, Sep24 Cell3 52, Sep23 Cell3 33, Sep23 Cell5 39. Repeated cell numbers remain distinct by date and UUID.
- Both exports match those 173 UUIDs, per-epoch metadata fingerprints, saved query and source links. SQLite integrity and foreign-key checks pass.
- Response lengths: 165×200,000 + 7×100,000 + 1×400,000 samples = **34,100,000**, all 10 kHz/mV. No fixed-length stacking assumption.
- Fifteen beginning/middle/end windows across five representative trials match source H5 through the SQLite reader. Native MATLAB independently verifies both sources, controls, the long trial and mask round trip.
- Ran the exact emitted `launch_epictree.m` and `tree_layout.m` in MATLAB R2022a: valid visible GUI, **173 epochs / 45 chronological leaves**, friendly labels, shuffled UUID mask alignment, native save/reopen, all-excluded flags, fail-closed invalid mappings and sequences.
- Production SQL, local jobs, source manifest, candidate audit events, explicit Add and export records agree. Baseline History101 and Mean Noise520 stay intact.
- The raw H5 contains one empty block; existing RetinAnalysis deliberately skips empty blocks. Its 38 raw blocks yield37 nonempty catalog blocks; **all690epochs are preserved**.

## Responsiveness and regression checks

233 Python regressions and66 frontend tests passed, plus production build. The final frontend guard also detects a changed dataset binding even if counts happen to be identical, and requires the refreshed proposal to be seen before another Add.

Five sequential local warm reads measured median latency6.5ms for persisted suggestions,24.6ms for History summary,8.2ms for its tree and140.3ms for project overview. These are local backend timings at1,776epochs, not browser render measurements or evidence of large-dataset scaling. Traces are read on demand in bounded full-rate windows.

## Artifacts and limits

Export receipt paths and complete native proof are recorded in `SEPT23_IMPORT_E2E.json`. Supporting protocol proposals remain pending. Review markers and scientific inclusion decisions were not invented by this test.

The SQLite handoff is a queryable recording snapshot for Wheeler, not a precomputed SRM Compact/VMN fitted-analysis database. Both export formats retain H5 references, so waveform access requires those sources. Moving to another machine requires source-path resolution.

Repeat the independent source audit with `python/verify_sept23_handoffs.py`; it emits a native MATLAB validation script and changes only its new proof directory. The live research export masks were not altered by the native test: mask mutations ran in isolated bundle copies.
