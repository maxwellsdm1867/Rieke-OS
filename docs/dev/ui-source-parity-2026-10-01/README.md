# Latest local UI parity

The missing palette was a source omission. Native E2E served the live canonical
`5712d1b` React entrypoint, not stale `dist` or the installed 0.1.5 package.
The current theme and UI source was uncommitted in the separate local
`codex/disco-appearance-themes` worktree at `/private/tmp/disco-appearance-preview`,
based on `a8fac2c`. The original epicTreeGUI source at `9602ab5` has no themes;
its current UI bytes are unchanged since the approved `f03577e` snapshot.
All original dirty source remains untouched. `SOURCE_PROVENANCE.json` records
current source hashes, before/after parity and the complete reconciled UI seal.

## Production feature inventory

| Feature | Latest local source and reconciled behavior |
|---|---|
| Palette entry | Lower-left rail button above the profile, plus header/launcher appearance access |
| Themes | System, Light, Dark slate, and Fred purple; server persistence, cached initial render, system changes and legacy icon-only migration |
| Theme failure handling | Failed save restores previous theme; saved theme survives a separate Dock-icon failure |
| Styling | Theme variables across navigation, stores, import, dialogs, trees, tags and metadata; enlarged icons and accessible focus/contrast |
| Scientific plots | Palette-aware charts, canvas trace/axes/grid/cursor colors, repaint on theme change; recorded signal values unchanged |
| Protocol rule | Separate protocol membership, visible browsing scope and marked-for-export counts; technical predicate remains available |
| Export subset | Independent export filters retained across navigation; browsing filters do not silently restrict an export |
| Refresh | Full frozen protocol refresh with empty view filters; exact change counts and explicit no-change message |
| Inclusion language | Export marks are distinguished from visible recordings and protocol criteria |
| Provenance/UI polish | Source identifiers remain in technical details; concise user-facing cells/project labels |
| Desktop identity | Disco product/helper names agree; existing app ID, profile and Rieke OS executable path remain compatible |
| Typed summaries | Canonical projectId threading, Inspector frozen protocol/filter context, Search predicate context and preferences retained |

The reviewer found an empty-OR display regression in the local proposal:
`any:[]` now says **No project recordings**, while `all:[]` says **All project
recordings**. Nested NOT retains its operand's meaning. A render test covers
these cases. The requested-summary retained-response cap now counts UTF-8 bytes,
so multibyte scientific values cannot evade its 2 MiB budget. A regression test
checks equal-length ASCII versus multibyte results in native and typed paths.

The old epicTreeGUI-versus-canonical differences also include newer canonical
undo, source availability, Cell QC preparation/observations, App Updates,
project transfer/navigation and native API behavior. Those canonical features
remain. Older source deletions and MATLAB GUI additions are not overlaid.
Browser/project/appearance demo scaffolding is excluded; the production entry
does not import the sample `window.fetch` override.

## Render gate and test limits

The live-Vite visual fixture executes the actual production `main.jsx` and
`App.jsx`. Its synthetic API responses are confined to the isolated test browser
in `desktop/e2e/ui-source-parity.e2e.cjs`; it is not native scientific E2E or a
performance baseline. The included screenshots contain only this synthetic UI.
The user's Library screenshot was inspected locally and is not published.

The rendered checks cover the rail palette, four choices, dark Data stores
controls, reload persistence, Fred/Light icons, System/device updates, keyboard
radios and failed-save rollback. The dark palette is `#111522` background,
`#edf1fa` text and `#a5b6ff` accent, matching the inspected reference's palette.

Frontend tests and the complete backend regression suite are run with an
isolated `RIEKE_PREFERENCES_DIR`. Loopback fixture tests require ordinary local
socket access. Restricted runs failed on real-home creation locks and then
loopback binding; these were environment failures, not silently waived tests.
Native MySQL/import/scale checks still require explicit opt-in. No Docker,
native benchmark, installed-app restart or desktop package build ran here.

## Matched native before/after source

For the next native measurements, keep this **same complete UI** in both arms.
The AFTER arm uses the reconciled optimized backend. A separately pinned local
`codex/disco-ui-parity-native-baseline-20261002` branch restores only
`workspace_service.py`, `workspace_disk_index.py` and `workspace_tree_pages.py`
from canonical pre-typed `a8fac2c`, while keeping the same current appearance
and API boundary. The current boundary has a native EAV fallback when no
`typed_index` is published. A publication token/cache-release bridge preserves
the newer API's refresh fencing; it introduces no typed projection or optimized
catalog query. The baseline is a native compatibility control, not a claimed
historical app build or measured performance result.

Both arms must validate the native scientific corpus, source eligibility,
predicate/detail/export contracts, preferences and rendered UI before timing.
No demo response override belongs in either arm. Record exact source/corpus
seals and run identical actions serially. Historical million results remain
pinned to `e6c996a` and are not relabeled as measurements of this consolidation.
