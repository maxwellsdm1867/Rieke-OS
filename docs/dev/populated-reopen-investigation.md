# Populated session reopen: preparation and exact existing metric

Base documentation/source tree: `ddf4787662c964914f8b074a575e22207a7c2a66`; tested lazy runtime: `5310eb6c2047ba026dbe9242af9b41f6b50c3694`; shipping base: `ad52bcf9a1b3f80a302bac19fc94a53f0ed0a776`. Isolated branch: `diagnostic/populated-reopen-cache`. No installed application or real project changed.

## What the previous 50 seconds measured

The ABBA controller creates a fresh profile and empty native project for every sample, opens it, imports the synthetic H5, polls completion, queries overview, then validates 127 exact HTTP samples. Thus launch-to-result means **fresh launch + new database/project + first import + HTTP trace**, not populated reopen, one trace query, or chart paint. Baseline/lazy means were 49.826/49.578 seconds. Import request-to-result was 13.425/13.663 seconds and still includes the complete import job and overview. Project selection-to-authority was 22.365/23.502 seconds. No populated reopen or already-running trace-return latency can be inferred from these rows.

Raw evidence: `lazy-root-owned/evidence/abba-1/comparison.json` and `analysis.json` relative to task-10. Controller: `tools/diagnose_lazy_run.cjs`. Each scenario also opens a second empty project after the first result; its verification is not on the first-result critical path. Root and first-project full package checks are on that path, each about 10–11 seconds. Scientific cache changes cannot remove those checks under the current integrity policy.

## Existing reuse and restoration, source audit

- `python/recording_workspace.py:425`: persistent parser output has source, metadata and parser checksums and completion state checks. Reopen does not require reimporting the recording.
- `python/workspace_service.py:455`: persistent source projections and typed SQLite indexes are reopened by generation. Keys include project identity, source/catalog and metadata identity, file signatures and implementation contracts. A matching generation avoids H5 metadata reconstruction. Actual hit/miss behavior still needs a populated native measurement.
- `python/workspace_service.py:310`: an in-process source digest result is reused only for its exact path/device/inode/size/mtime/ctime tuple; a first trace in a fresh process may hash the H5. Each trace still checks H5 identities, units, bounds and post-read file signature. Do not extend this to an unverified persistent stat-only receipt.
- `workspace-app/src/resourceCache.js`: bounded in-memory epoch/trace cache, 64 entries/12 MiB/30 seconds, keyed by request and revision. It does not survive Quit. Navigation/search cache separately has project/path activation and actor fences. Neither is a persisted scientific authority.
- `workspace-app/src/useDesktopDraft.js`: existing drafts autosave every three seconds and flush on navigation/Quit. `App.jsx:189` saves route, per-route/protocol sessions, last explorer/store sessions. Tree snapshot code preserves expansion/page/scroll presentation without epoch payloads.
- `desktop/draft-store.cjs`: bounded, owned, atomic-replacement draft files; unreadable state requires explicit recovery. Keys are project UUID, not project path or actor; the envelope is version 1, not an app/schema compatibility contract. Copied projects with the same UUID and changed actors need explicit restoration scoping tests before expanding reuse.
- `python/workspace_startup_registry.py` already remembers the last project path/UUID. `desktop/main.cjs:147` starts the root and loads its chooser. `App.jsx` does not automatically reopen the remembered project. Saved view hydration starts only after the selected project service returns its registry identity. The existing remembered data is therefore not an early startup shell.

## First small correction prepared

The draft loader can finish after newer user navigation and overwrite that choice. The isolated correction captures the navigation key when loading and restores only if it remains current. A load generation also prevents an older retry from publishing over a newer load; closed project sessions cannot publish. This changes no scientific data, cache validation or process lifecycle. Five focused Node tests pass, including delayed load versus navigation, overlapping retries, close, unreadable-state preservation and serialized saves. Receipt: `benchmarks/results/reopen-preparation/draft-tests.log`. No Electron, Python or MySQL service was launched in this resumed turn.

## Next native measurement and implementation boundary

Prepare one owned populated fixture once, save a real inspected epoch/tree/scroll state, then ordinary Quit to zero. Measure (1) relaunch to populated project readiness and first exact trace; (2) chooser selection to the same; (3) already-running return to the same selection. Record first chart draw separately from HTTP completion, and existing derived-index reuse separately from package hashing, parser/probes, database recovery and service readiness. Preserve current package checks in every variant. No cold-cache or release-qualified claim.

Smallest restoration slice should consume the existing remembered project and presentation draft, with explicit chooser preference/cancel and a navigation-generation fence. Restore only compatible presentation state; obtain scientific values and action authority through the current service. Missing/moved project, changed H5, incompatible state, partial write, copied project/actor and cancelled old restore must fail or reset visibly without stale data, unsolicited project creation or abandoned owned services. A new trace cache is not justified before the populated baseline.

Runtime coordination is pending: the parent explicitly required a quiet-window request before timing. This turn's former parent-thread messaging tool is unavailable; a quiet-window question was submitted through the available input tool. No window grant has arrived yet, so native baseline/optimization/fault measurements are not claimed. All previously recorded cleanup receipts remain historical; no new owned app/service processes were started.
