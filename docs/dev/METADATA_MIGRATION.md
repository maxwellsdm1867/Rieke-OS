# Canonical DISCO metadata migration

The development repository is [maxwellsdm1867/Rieke-OS](https://github.com/maxwellsdm1867/Rieke-OS),
on branch `codex/disco-metadata-migration-20261002`. Its parent is canonical
`a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`. This migration retains newer Rieke-OS
source eligibility, undo/selection controls, project navigation and persistence
semantics, and adds the tested catalog batching, navigation cache safeguards,
complete typed SQLite query core, service generation/lifecycle APIs and requested
summary UI. The source snapshot's unrelated older changes, deletion of newer API
routes, desktop/release changes, MATLAB binaries and old GUI baggage were excluded.

`METADATA_MIGRATION_PROVENANCE.json` records original source commits and hashes.
The private source-snapshot ancestry is deliberately excluded from the public
branch; canonical ancestry remains intact. Original local checkouts, recordings,
databases, MAT fixtures and evidence were not modified.

## Read and develop here

- [Metadata requirements](../design/metadata-query-requirements.md)
- [Priority proposal](metadata-priorities-2026-10-01.md)
- [Preserved benchmark ledger](metadata-index-handoff-2026-10-01/BENCHMARKS.md)
- [Typed query API](TYPED_QUERY_CORE_API.md), [service API](TYPED_SERVICE_API.md)
- [Requested summaries](../../workspace-app/REQUESTED_SUMMARIES.md)
- [Independent qualification report](../../tools/metadata_qualification/REPORT.md)

The 9 navigation / 7 scientific / 41 protocol-specific / 83 on-demand tiers are
proposed policy. All eligible paths remain queryable. Reliable per-person query
and split logging remains proposed: `CurationStore._event` suppresses routine
layout/query/preset events. Summary preferences use browser-local
project/protocol/view keys, without a person key. This migration adds no telemetry.

## Docker-free workflow

Use the pinned native setup in [workspace-app/README.md](../../workspace-app/README.md):
from the repository root run `python3 rieke.py setup`, then `python3 rieke.py doctor`.
Setup installs the isolated `.rieke-runtime` Python/MySQL runtime; it does not need
Docker. `python3 rieke.py launch` is an explicit later step and starts the app.
Keep native scientific project directories and recording inputs outside the repo.
The migration itself neither started the active app nor rebuilt its private runtime.

For focused tests, set `RIEKE_PYTHON` to an existing approved native runtime Python
or this checkout's `.rieke-runtime/venv/bin/python`. The migration used an existing
runtime externally, read-only, while executing canonical source in this repository.

```sh
PYTHONPATH=python:python/tests "$RIEKE_PYTHON" -B -m pytest -q -p no:cacheprovider \
  python/tests/test_workspace_catalog_batching.py \
  python/tests/test_workspace_tree_navigation_cache.py \
  python/tests/test_workspace_typed_index.py \
  python/tests/test_workspace_explore_queries.py \
  python/tests/test_workspace_disk_index.py \
  python/tests/test_workspace_api.py python/tests/test_workspace_tree.py
"$RIEKE_PYTHON" -B -m unittest discover -s tools/metadata_qualification -p 'test_*.py'
cd workspace-app
npm ci --ignore-scripts
npm test
npm run build
```

The inherited native SQL tests require explicit `RIEKE_TEST_NATIVE_MYSQL` opt-in;
skips do not prove credentials are missing. No Docker/native SQL or heavy million
benchmark ran during migration. Historical real-million backend observations
qualify their recorded original commits, not this reconciled canonical branch.
Full native source-authority replay, complete rendered E2E, waveform/export and
stimulus reconstruction gates remain open. Namespaced experimental replay source
IDs/fingerprints do not become production eligibility; no browser bypass was added.

## Public evidence copies

The repository is public. Personal saved-query/layout history, actor/timestamp
records and raw HTTP-log details were removed from the public usage audit. Local
home paths, native project labels, recording names and observed UUIDs are redacted
or consistently pseudonymized. Observed example values in archived catalog JSON
are withheld; counts, timings, scopes, storage costs, status and limitations remain.
Frozen hand-authored development fixtures retain their synthetic identities/seals.
No recording payloads, scientific binary fixtures, databases, credentials, personal
cover letters or raw personal logs are included.

`METADATA_MIGRATION_PROVENANCE.json` retains **original-copy** SHA256 values.
Historical archive manifests describe original bytes. They must not be used to
validate changed public copies. `PUBLIC-COPY-SHA256.json` separately validates the
published archive and qualification copies. The immutable originals remain local.
Historical scripts/receipts contain placeholder local paths and are source evidence,
not commands to run blindly against a live project.
