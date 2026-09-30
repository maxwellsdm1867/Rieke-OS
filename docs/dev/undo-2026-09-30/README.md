# Session undo validation — September 30, 2026

Undo is enabled after optimizing and measuring the ordinary save path. It reuses
normal annotation/curation transactions. Temporary search inclusion uses only the
original viewer's local state. The history holds at most 50 whole gestures and a
conservative 512 KiB accounting budget (four bytes per JSON code unit plus target/pattern overhead); it is never serialized to a UI draft,
SQL, an H5 file, recovery backup, transfer or export.

The inverse receipt stores shared change patterns once plus arrays of original
UUID, new revision, prior revision and pattern index. A normal 1,000-target tag
or mixed inclusion/tag gesture fits the budget. A gesture with unusually many
unique tag changes can exceed it: the receipt reports unavailable and the UI
clears prior history rather than undoing only part of a gesture. No-op or failed
writes do not become undo entries. Uncertain writes clear the stack and require
state refresh. Revision conflicts retain an honest error and do not replay an
inverse automatically.

## Real native MySQL measurements

`benchmark_native.py` initializes and shuts down an isolated temporary project
using the existing pinned private MySQL runtime. It does not touch a scientist's
project. The same mutation code runs with inverse receipts disabled/enabled;
200 pairs of single edits, 30 pairs of 500-target gestures and 20 pairs of
1,000-target gestures alternate in randomized, balanced order. Timings include
transaction work and response JSON serialization, without browser rendering or
HTTP transport. DataJoint 2.2.2 / Python 3.11 on this macOS arm64 workstation.

The saved results are in `native-balanced.json`; `native-interleaved.json` records
an earlier interleaved run. Baseline and enabled SQL counts are exactly equal.

| Gesture | Targets | Median off → on (ms) | P95 off → on (ms) | SQL calls per edit |
| --- | ---: | ---: | ---: | ---: |
| Shared tag | 1 | 4.769 → 4.785 | 5.589 → 5.865 | 10 |
| Shared tag | 500 | 191.996 → 193.504 | 205.309 → 216.330 | 1010 |
| Shared tag | 1000 | 366.183 → 365.828 | 415.392 → 417.961 | 2014 |
| Dataset tag + inclusion | 1 | 0.628 → 0.636 | 0.946 → 0.944 | 7 |
| Dataset tag + inclusion | 500 | 143.933 → 142.932 | 582.459 → 1557.882 | 1006 |
| Dataset tag + inclusion | 1000 | 243.739 → 246.366 | 287.240 → 268.437 | 2008 |

Median extra serialization at 1,000 targets was 0.345 ms for tags and 0.275 ms
for curation. Compact inverse content was about 53 KiB for 1,000 targets, around
227 bytes for a single shared-tag action, and 200 bytes for single curation.
Existing response bodies are larger because they contain ordinary authoritative
state. No new requests or SQL operations are added to the ordinary path.

Persistent scientific/audit row counts matched with receipts off and on. The
first sequential run compared exact persisted audit payload byte counts and
found them equal (1,095,718 bytes for 100 single tag edits plus warmup;
4,517,740 bytes for 20 500-target edits plus warmup). Later mixed runs assert
that scientific events contain no undo payload. Normal scientific audit growth
already exists; undo adds no separate journal or on-disk action history. Pressing
Undo intentionally makes a normal inverse mutation and its existing backup/audit
behavior.

There is measurable noise: the initial unbalanced 1,000-target tag run showed
+9.6% median latency; compact interleaving reversed that direction, and the
balanced repeat showed effectively unchanged median. Native durability and
scheduling pauses produced large tails in both modes, including the 500-target
curation outlier above. These runs do not establish zero cost or a universal tail
bound. The small median changes and equal operation counts support enabling the
bounded implementation; long-term native workload monitoring remains useful.

## Mounted UI and interaction checks

`benchmark_mounted.mjs` mounts actual App, Inspector and tag editor components
with controlled API fixtures. Baseline/on/on/baseline order, 30 rapid tags per
block, tests small and 100,000-epoch views. Results are in `mounted.json`.
The history subscription is isolated in `UndoControls`, so availability changes
do not render the whole scientific workspace.

| Mounted view | Off medians (ms) | On medians (ms) | Off P95 (ms) | On P95 (ms) |
| --- | --- | --- | --- | --- |
| 500 epochs | 5.747, 5.058 | 5.421, 4.910 | 8.703, 7.768 | 7.825, 7.394 |
| 100,000 epochs | 8.020, 7.996 | 7.637, 7.619 | 10.850, 10.737 | 11.063, 11.444 |

Every ordinary tag gesture makes exactly one annotation mutation and no extra
annotation read. This uses React TestRenderer, not native paint timing. A prior
concurrent run during heavy MySQL benchmarks had noisy 100,000-epoch tails;
after isolating button subscriptions and stopping concurrent load, reversed
order measurements showed no material ordinary interaction regression.

Automated tests cover original-target undo after epoch navigation; atomic mixed
inclusion and predating tags; cell inheritance and other authors; stale
revisions; no-op/failure handling; repeated shortcuts during an in-flight inverse;
project isolation; 10,000 edits under byte/action caps; and 1,000-target compact
admission. Electron uses only its native menu IPC; browser sessions use the DOM shortcut. Paired dispatch tests, including delayed DOM delivery after an inverse completes, preserve native
undo in unfinished text and choose exactly one scientific path after a committed
composer is cleared. Physical macOS Cmd+Z in the packaged app has not been
manually exercised. Existing exports remain immutable.

For controlled baseline measurement only, set the browser local-storage key
`rieke.undo.enabled` to `false` before mounting/reloading. Only this diagnostic
flag persists; action history never does.
