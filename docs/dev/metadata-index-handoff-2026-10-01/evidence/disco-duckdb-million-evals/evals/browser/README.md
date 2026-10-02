# One-million browser evals

This harness mounts the **unchanged production shared React PagedTree and MetadataPanel** in a minimal production-built Vite shell. Its API is an **experimental typed metadata readmodel bridge**; it is not current native Flask/MySQL application qualification. SQLite and DuckDB receive the same frontend, fixture and API contract.

The full nine-action scorecard is [../SCORECARD.md](../SCORECARD.md). Seven browser actions are required; tagging and full filter preview are separately measured backend actions. Their scope is never substituted with client-only timing or a lightweight preview.

## Measurement contract

- Five repetitions for all seven browser actions, five unopened disjoint branches, and one first component view.
- First observation and remaining warm observations are reported separately. Unloaded client branches can still use warm database/OS caches. We do not call these OS-cold storage measurements.
- Timing spans user action to observable completion plus two requestAnimationFrame callbacks. It includes HTTP, JSON decoding and React commit, but excludes full App startup, waveform reads, packaging and physical screen display.
- Every received tree response must have bounded pages, a stable valid revision, one-million membership, correct continuation flags and no duplicate epoch IDs.
- Rendered leaf UUIDs and order must match the response exactly. Backend independent fixture arithmetic checks establish semantic IDs/counts/order; response consistency alone is not an independent oracle.
- Any missing action, HTTP/React error, correctness failure or incomplete repetition fails the receipt.
- Use fresh owned headless Chrome, ephemeral local preview port and owned output directories. No shared browser profile or installed application data is used.

## Replay

```sh
python3 docs/dev/duckdb-million-evals-2026-10-01/browser/prepare_browser.py --source-root /private/tmp/disco-duckdb-million-20261001 --output-dir /private/tmp/disco-duckdb-million-runs-20261001/browser-shell --node-modules /PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/workspace-app/node_modules
DISCO_BROWSER_BUILD_ROOT=/private/tmp/disco-duckdb-million-runs-20261001/browser-shell node docs/dev/duckdb-million-evals-2026-10-01/browser/run-browser.mjs ENGINE-config.json http://127.0.0.1:OWNED_API_PORT ENGINE-browser.json 5
```

The config must contain engine (`sqlite` or `duckdb`), epochs (`1000000`), source_head, protocol_uuid, catalog, and explicit fixture/API scope. Source preparation byte-verifies every frontend file against a before/after SHA-256 inventory. Node and Playwright dependencies are read from the existing installation; frontend source is copied exactly into the owned shell. Production source is never edited by this harness.

## Current status

Both actual million-epoch typed engines passed all seven actions with five repetitions each, disjoint-branch controls and independent backend oracles. Source frontend snapshots remain byte-identical. All 36 tree page request/response pairs match exactly between engines. No React/HTTP errors. All owned Chrome, preview and API bridges stopped normally. The failed first bridge catalog-config attempt is preserved separately. Existing 100k source receipts are frozen in `frozen-scorecard.json`; final results are in `scorecard.json` and `../SCORECARD.md`.

## HTTP bridge

`bridge.py --engine ENGINE --database PATH --output-dir OWNED_DIR --epochs 1000000` opens only the supplied experimental projection and uses an ephemeral loopback port. `ready.json` supplies the actual origin and config path. The bridge implements the exact tree response structure needed by the unchanged component for the explicitly scoped protocol, empty filters and cell/block split sequence. It does not implement all production app endpoints.

Bounded keyset group/page queries translate offset continuation into the previously returned cursor. Parent hash lookup is limited to 512 seen branches; cursor lookup is limited to 512 entries. A 10,000-cell independent fixture identity oracle supplies expected UUIDs, counts and chronology; million-epoch rows are never copied into Python. Every HTTP tree/detail response checks this oracle, and the browser receipt saves all oracle results. Assertions are included in measured bridge time for both engines. Initial application/SQL caches are empty in a fresh bridge process; storage cache is not purged.

SQLite 1,000-epoch smoke check passed root cell counts, chronological blocks, epoch IDs and detail parameter equality. The readmodel's own paired engine tests independently cover block continuation and typed missing/null semantics.

`test_bridge.py` additionally passed 7,000-record bounded cell continuation, chronological blocks, exact epoch/detail identity, stale revision rejection and explicit unsupported-scope rejection. Both actual browser engines used original Python 3.11 runtime plus the isolated DuckDB dependency path `/private/tmp/disco-duckdb-deps-20261001`.
