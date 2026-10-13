# Project switching and SRM loading in Disco 0.1.12

> Later baseline reconciliation: this design worktree is now `codex/ui-cache-design` at local UI base `386e72d`. The observations below retain their original installed-source attribution (`add33d1`); separate local branches are reconciled in `local-cache-baseline-audit.md`.

Investigation date: 2026-10-13. Investigation only; no application implementation, installation, or release change. User scientific records were not edited. Normal UI navigation and authenticated read requests were used to inspect the existing app; these observations are not benchmarks or release qualification.

## Findings

The user's channel-switching model fits this application. Already-open project backends survive a switch, but the current frontend document does not. Returning to a project rebuilds the React application and loses its live caches, then repeats discovery and summary requests. Keeping an already-open project view alive is the primary recommendation.

There is a separate cold-loading problem. The SRM service's retained initialization metrics report **44.152 seconds**, four rebuilt source projections, zero source-cache hits, and a rebuilt metadata index. The current project is now ready and visibly contains **4,899 epochs, 16 cells, and four H5 sources**. Its Variable History Noise protocol shows **411 epochs across 11 cells**. The user confirmed that data had returned.

The original empty display was not captured. The recorded initialization is concrete evidence of a long load and a plausible explanation for that display, not proof that a particular frontend error occurred. Older validation/ownership errors in the project log predate this run and must not be attributed to the current incident.

## Source identity

- Installed app: `/Users/maxwellsdm/Applications/Disco.app`, version 0.1.12, clean packaged source `add33d153ae8f533d5c4a68c50690764323c4336`, verified from the installed runtime manifest.
- Exact release-source checkout inspected: `/private/tmp/disco-release-0111-20261011`, branch `codex/release-0.1.12`, clean at `add33d1`. Its directory name is historical.
- Live GitHub main verified as `8cd61822aa78bf6e9d221c90fbae6a5c8a90f66a`. It does **not** contain the installed release commit. Main's README update does not make main the implementation baseline for 0.1.12.
- This documentation-only investigation uses an isolated worktree based on that live main. Application-source claims below refer to the installed release commit, not this worktree's application files.

## What a switch does

The following sequence is reconstructed from exact release source and native UI observation. No browser network waterfall or HAR was captured; request timings below are separate single-request diagnostics.

1. `selectProject` flushes the current desktop draft.
2. It POSTs `/projects/inspect-folder`, then `/projects/open-folder`.
3. The desktop service verifies the target. `DesktopServices.open` reuses an already-owned healthy child, so ordinary warm switching does not inherently restart Python/MySQL or reimport H5 data.
4. `window.location.assign` navigates to the target project's localhost origin. Desktop navigation authorization ultimately calls `window.loadURL`. The prior React document and in-memory state are replaced.
5. Serving `index.html` generates a project bootstrap. That calls current-project inventory, which starts a discovery subprocess and enumerates sibling folders plus remembered exact project folders.
6. The new React root also requests `/projects`. This repeats inventory. `projectReady` depends on this resource having no error and no `inventory_unavailable` flag.
7. If scientific data has not been activated, `/project/activate` constructs it. If already ready, activation is avoided, but the new frontend still requests `/overview`, `/protocol-suggestions`, `/workbench/summary`, and the selected view's resources.
8. `/overview` decorates project rows and summarizes each protocol; the HTTP route further enriches protocol membership/review/export counts. `/workbench/summary` visits every protocol and prepares its queue summary. These are substantive reads, not just returning a cached window.

Source anchors at installed commit:

- [Project selection and initial resources, App.jsx](https://github.com/maxwellsdm1867/Rieke-OS/blob/add33d153ae8f533d5c4a68c50690764323c4336/workspace-app/src/App.jsx)
- [Inspect/open sequence](https://github.com/maxwellsdm1867/Rieke-OS/blob/add33d153ae8f533d5c4a68c50690764323c4336/workspace-app/src/project-workspace/projectTransfer.js)
- [Desktop navigation and session ownership](https://github.com/maxwellsdm1867/Rieke-OS/blob/add33d153ae8f533d5c4a68c50690764323c4336/desktop/main.cjs)
- [Owned backend reuse, DesktopServices.open](https://github.com/maxwellsdm1867/Rieke-OS/blob/add33d153ae8f533d5c4a68c50690764323c4336/python/workspace_desktop.py)
- [Frontend bootstrap](https://github.com/maxwellsdm1867/Rieke-OS/blob/add33d153ae8f533d5c4a68c50690764323c4336/python/workspace_frontend.py), [project inventory subprocess](https://github.com/maxwellsdm1867/Rieke-OS/blob/add33d153ae8f533d5c4a68c50690764323c4336/python/disco/projects/project_inventory.py), [folder enumeration](https://github.com/maxwellsdm1867/Rieke-OS/blob/add33d153ae8f533d5c4a68c50690764323c4336/python/workspace_projects.py)
- [Overview construction](https://github.com/maxwellsdm1867/Rieke-OS/blob/add33d153ae8f533d5c4a68c50690764323c4336/python/workspace_service.py), [HTTP enrichment](https://github.com/maxwellsdm1867/Rieke-OS/blob/add33d153ae8f533d5c4a68c50690764323c4336/python/workspace_api.py), [Workbench summary](https://github.com/maxwellsdm1867/Rieke-OS/blob/add33d153ae8f533d5c4a68c50690764323c4336/python/disco/workbench/workbench.py)

## Observed request costs

Single serial reads against the existing, ready services, measured with `perf_counter` through complete response-body receipt. Milliseconds are rounded. These are neither medians nor additive click-to-ready timings; the frontend can issue requests concurrently and machine load was not controlled.

| Request | SRM ms | hahah ms | SRM response bytes |
| --- | ---: | ---: | ---: |
| GET `/api/projects` | 556 | 140 | 840 |
| GET `/api/overview` | 595 | 3,331 | 36,880 |
| GET `/api/protocol-suggestions` | 27 | 17 | 234,217 |
| GET `/api/workbench/summary` | 717 | 214 | 988 |

Both `/projects` results identified their correct project and reported `project_data.status=ready`. The coordinator's service registry retained both child processes, with distinct project paths and ports. Initial requests without the session header correctly returned 403; measured successful requests used the existing session's renderer credential without displaying or saving it.

The launcher `/api/projects` currently succeeds in about 170 ms. The release qualification record separately reports historical approximately three-second discovery timeouts; that failure was **not reproduced** here. A transient inventory error can gate `projectReady` even when the scientific backend is healthy, so discovery should not control visibility of an already-open view.

## SRM's recorded cold initialization

The read-only `/api/metadata/status` result retains the completed initialization at **2026-10-13 13:16:52 America/Los_Angeles**:

| Recorded phase | Time |
| --- | ---: |
| Full metadata refresh | 44.152 s |
| Source metadata rebuilding | 20.727 s |
| Metadata index handling/build | 9.669 s |
| SQL queries | 6.070 s |
| Typed metadata index | 0.375 s |

These phase measurements do not claim to partition every millisecond of total startup. There were four rebuilt sources, zero reused sources, 4,899 epochs, and five protocol records. Annotation preparation separately reports 0.683 s and reuse.

For comparison, hahah's retained earlier initialization reopened its metadata index and reused both sources, but still took 11.133 s, including 8.474 s in SQL queries. This is an earlier run on a different project, not a matched performance comparison.

Exact status responses are retained in [status-observations.json](project-switch-investigation-2026-10-13/status-observations.json).

## Why disk caches can be rebuilt

The current projection key includes source-record checksum, metadata checksum, physical-file signatures (path/device/inode/size/mtime/ctime), and a projection contract. The contract hashes the **entire contents** of `recording_workspace.py`, `projection_cache.py`, `metadata_objects.py`, and `workspace_service.py`. The metadata-index generation additionally hashes whole index/tree/predicate modules.

Thus, an application edit in an unrelated part of one of these broad modules can invalidate source projections or indexes even when recordings are unchanged. This is a confirmed broad invalidation mechanism. It is not proof of which key component changed for this particular SRM rebuild: the metrics record cache misses but not their specific reason, and the old disposable generations were reclaimed. Missing/invalid cache files or changed file signatures are other possible causes.

A future repair should use explicit, tested projection/index compatibility versions with narrower ownership. It must preserve source identity and checksum validation. Record cache-miss reasons so a future slow start can distinguish source changes, format changes, missing files, and invalid seals.

## Recommended change

Keep a small bounded set of live project views. For an already-open project, switch the retained view's visibility and focus. Keep its expanded tree, selected epoch, trace buffers, scroll, navigation and drafts. Reuse its existing backend. Do not replay document bootstrap, filesystem discovery, or project-wide summaries on the warm-switch critical path.

For Disco's separate localhost origins, a desktop-owned `WebContentsView` per warm project is the most direct design. It does require adapting desktop ownership, IPC/menu routing and close handling; it is not a one-line cache toggle. Use canonical project identity and backend instance identity, not port or project name alone. Pause unnecessary background view reads while leaving accepted scientific operations owned and running. Evict only safely saved inactive views, and distinguish an evicted project's reopen from a warm switch.

One additional existing behavior must change: `useOverviewCache` unconditionally refreshes every retained overview on focus, online, and becoming visible. Merely retaining a renderer would preserve the display but still trigger redundant work. Activation should compare a lightweight revision/generation token and refresh affected resources only when needed; overlapping focus/visibility events should share a single check. Scientific edits/exports retain their existing fresh authority checks.

See [primary-source comparison and lifecycle constraints](project-switching-primary-source-research.md), including VS Code's retained editor widgets and Electron's supported view APIs.

Implementation acceptance should use owned disposable projects: warm A→B→A retains the same document/view identity, starts no new project process, avoids bootstrap/discovery/overview reconstruction when unchanged, and restores the exact visible state. Measure ordinary click-to-correct-result latency separately for cold open and warm switch, plus memory and inactive request rate. Test changed revisions, project closure, backend restart, drafts, rapid switching, and renderer eviction. No improvement or correctness gate has yet been claimed.
