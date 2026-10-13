# Populated native retention audit

`populated-retention.dev.cjs` is a separate candidate-only click-through audit of
real Electron `main.cjs`, WebContentsView, renderer, importer, native database,
and H5 trace routes. It does not replace `retained-projects.dev.cjs`, the empty
A/B/A and restart qualification, or either fixed million-epoch gate.

Run only after the coordinator supplies a clean candidate commit and clears the
shared machine for serial execution. Stage that exact source with
`tools/stage_retention_desktop.py`; never point the driver at an installed app.

```
node desktop/e2e/populated-retention.dev.cjs \
  --source-root /absolute/frozen/source \
  --desktop-root /absolute/owned/stage/desktop \
  --dependency-root /absolute/matching/desktop \
  --commit FULL_CLEAN_COMMIT \
  --output /absolute/new/output-directory
```

The driver verifies source cleanliness, commit, staged desktop bytes and runtime
manifest. It creates its own temporary HOME, preference directory, project
index, application state and two empty native projects. Its child environment
is constructed explicitly, without inheriting app overrides or user project
paths. All import inputs and managed recordings must stay inside that HOME.
No external recording path is accepted.

The helper reuses the existing `tools/organization_e2e_fixture.py` generator
functions to construct a 63-epoch, two-cell, single-response recording. Before
freezing that base, it supplies deterministic `dataFileName` block metadata that
the pinned PATCH parser records without reading external binaries. The unchanged
common raw and strict parser preflight oracles then validate the completed base.
Both the metadata additions and common generator hash are recorded.
`seed-dual-response-fixture.py` copies that frozen owned recording, preserves the
original hash and adds Amp2 with unique deterministic UUIDs and values
`1000 + epoch ordinal + sample index / 128`. Amp1 remains
`epoch ordinal + sample index / 256`. Both are 256 samples at 10 kHz in pA.
Every value, stream UUID, label, unit, count and parser response mapping is
checked before the derived file is imported. Both parser logs are captured, and
any warning, error or traceback fails preflight. The canonical raw oracle remains
unchanged. A separate parser-path projection is declared from the generator’s
known animal/experiment hard link before parsing. Every canonical and alias
stream group and data dataset must have identical H5 object IDs. Both oracle
projections and hashes are saved; expectations are never copied from parser
output. The common generator and its
oracle are unchanged; derived hashes and an expanded oracle are recorded.

The audit uses actual UI clicks to import through the H5 file chooser, review
import, open project and protocol overviews, expand the epoch tree, inspect a
trace, expose metadata, set a sample window and cursor, select Amp2 → Amp1 →
Amp2, scroll, visit Workbench, return through history, and switch to the second
project and back. It verifies the renderer's actual trace responses against the
analytic oracle and checks the displayed cursor. A supplemental bounded backend
read verifies 127 exact samples; it is recorded separately from renderer reads.

Warm returns must retain Inspector and canvas DOM, scroll, trace window and
selected channel. An ordinary Quit checkpoints state; a fresh process must
restore the protocol inspection, sample window and Amp2 selection while retaining
all 63 epochs, two cells and original source hashes. The driver then quits
orderly again. Screenshots, elapsed action observations, requests, failures,
fixture identity and cleanup outcomes are written to `receipt.json` and sibling
PNGs. A nonzero result must be inspected before any subsequent qualification.

This is a small synthetic candidate audit, not a baseline speed comparison,
large recording benchmark, scientific analysis qualification, or packaged release
qualification. Browser audit comparisons, fixed gates and the mandatory empty
native lifecycle run retain their separate attribution.

The shared test helper `retention-native-support.cjs` pairs Playwright pages with
attached WebContentsViews by CDP target ID and Electron webContents ID, rather
than matching URLs. Timeout evidence records attached views, page identities,
visible labels and text. Failure receipts are written before cleanup. Fallback
Quit is bounded; a forced signal is permitted only to the exact launched Electron
process after the owned backend registry shows no services or database operations.
A forced exit is recorded as cleanup, never counted as successful ordinary Quit.
