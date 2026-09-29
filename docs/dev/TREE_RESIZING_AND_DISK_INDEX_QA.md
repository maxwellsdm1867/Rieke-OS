# Tree navigation and disk index validation

Validated on 2026-09-27 in the local Rieke OS app at port 8766.

## Live interaction checks

- Dragged the epoch pane from 270 to 423 pixels. Width survived reload.
- Dragged the metadata pane from 320 to 380 pixels; the trace remained visible.
- Resized the grouping pane with the keyboard from 423 to 433 pixels.
- Up/Down on the inspection toolbar selected adjacent epochs. Cross-page
  navigation passed in both directions, epoch 60 to 61 and back.
- Down in metadata search preserved the selected epoch.
- Page/document scroll remained zero while Down advanced epoch 1 to 2.
- Returning from inspection to tree design restored the dated branch.
- Suggested grouping separated date, cell type, cell, control state, combined
  History 1/History 2/Target, segment duration, and block. Joint values and branch
  counts were visible in the preview; no scientific membership was changed.
- A compact unfiltered predicate preview reported 1,776 epochs, eight cells,
  two dates, and five acquisition protocol IDs. Restoring the saved HistoryNoise
  query as a draft retained its original immutable revision.
- No application console errors were observed. Unrelated Chrome extension
  connection errors were present in the browser log.

## Automated and scientific checks

348 Python tests and 107 frontend tests pass; production build passes.
Malformed, excessively nested tree JSON returns 400 before selection work.
Stale page errors cannot cancel a newer navigation request. Tree restoration
retains only paths, offsets, and revision IDs, not full membership arrays.

`disk_index_live_validation.json` records exact catalog, typed-value and
fingerprint parity for the two-source project. Restart and refresh succeed with
full projection decoding and H5 reads prohibited. The final unchanged refresh
took 0.415 seconds; verified index reopening took 0.047 seconds, within a
3.30-second startup including SQL connection/query work.

See `DISK_METADATA_INDEX_BENCHMARK.json` for the separate 50,000-epoch synthetic
measurement and `SCALABILITY.md` for limitations. New index generations still
rebuild the entire derived index and block loading; this is not a certification
of end-to-end 50,000-epoch import/browser latency.

The live catalog retains two sources, eight cells, and 1,776 epochs. The History
Noise working dataset remains version 2 with 173 epochs in two existing exports.
No protocol proposals were applied and no exports were regenerated for this pass.
