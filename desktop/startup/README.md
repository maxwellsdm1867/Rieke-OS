# Startup presentation preference

[StartupSession](startup-session.cjs) remembers one compatible location and offers
it once. It does not open a project or establish scientific readiness.
[Main](../main.cjs) retains restoration, authorization, exact process/project
identity, cancellation and normal-quit composition. See [local instructions](AGENTS.md)
and [desktop navigation](../AGENTS.md).

| Public interface | Contract and errors |
| --- | --- |
| `new StartupSession(userData,compatibility)` | Uses `userData/startup-session.json`; moving source does not relocate preferences. Main supplies schema compatibility `view-v1`. |
| `load()` / `claim()` | Load accepts an owned regular nonsymlink file at most16384 bytes with compatible version1 schema. Unknown/corrupt/incompatible state stays intact. Main accepts the explicitly reviewed `0.1.8:view-v1` and `0.1.9:view-v1` predecessors without rewriting on load. Claim returns one compatible resume target or null and is consumed even when cancelled/no target. |
| `remember(projectId,projectPath,view)` | Requires non-launcher validated identity and normalized absolute path. Caps string view at80 characters; nonstring becomes overview. Preserves explicit chooser preference. Invalid session throws; persistence rejection propagates. |
| `choose()` / `resume()` | Change cancellation/preference and persist chooser/resume when state exists. Transient cancelled=true in main does not itself change next-launch preference. |
| `viewNamespace(projectId,projectPath,compatibility='view-v1')` | SHA-256 of exact identity/path/compatibility tuple. Checks absolute path but does not itself canonicalize it; main supplies the canonical recorded path. Different path or compatibility gets a different namespace. |
| `valid(value,compatibility)` | Returns Boolean for supported comparisons or can throw through invalid project validation. Preserve Boolean-or-throws behavior; this is not an all-input no-throw validator. |

The existing save chain serializes snapshots through supervisor.atomicJSON, which
uses exclusive temporary creation, file sync, rename and directory sync. Ordinary
filesystem tests are not power-loss qualification. Node facilities imported by
supervisor do not start a service just by importing atomicJSON. No helper extraction,
transport seam or persisted schema change was introduced.

value, target and cancelled are existing conventional instance properties used by
main; they are not language-private. Remembered location cannot bypass authorization
or exact UUID/path and PID/creation-time checks. A cancelled startup must not navigate
late or certify unconfirmed cleanup. Strict replacement and bounded explicit Quit
remain separate [close contracts](../close/README.md).

## Public examples and verification

The [executable public examples](tests/public-examples.test.cjs) use an owned temporary
profile, synthetic UUID/path and the real public entry. They demonstrate one-shot
claim, chooser/resume persistence, namespace differences, exported validation and
preservation of corrupt preference bytes. The [original tests](tests/startup-session.test.cjs)
remain byte-identical and retain transient-cancellation versus chooser coverage.
From this folder:

```sh
node --test tests/public-examples.test.cjs
node --test tests/*.test.cjs
```

From repository root, with existing provisioned parser dependencies:

```sh
node --test desktop/startup/tests/*.test.cjs desktop/tests/main-startup-restoration.test.cjs desktop/tests/close-packaging.test.cjs
python3 -B -m unittest python.tests.test_architecture_guard python.tests.test_desktop_release_plan
```

The retained main restoration test imports this real entry and invokes registered
handlers with fake Electron/transport. Its QuitCoordinator interception remains at
the adopted close path. No mocked StartupSession replaces the entry.

The root-owned [catalog](../../docs/architecture/adopted-port-checks.json),
[adoption record](../../docs/architecture/0.1.8-first-port-slices.md),
[ledger](../../docs/architecture/core-module-ledger.md) and
[path companion](../../docs/architecture/core-module-paths.json) record integrated
mappings; parent serializes these updates with other module moves. During branch
review an old catalog cannot be treated as a runnable final mapping.

The shared root packaging check explicitly stages this entry and resolves its
`../security.cjs` and `../supervisor.cjs` dependencies alongside main and other
adopted entries. Exact inclusion/test-exclusion/stale-path faults are source checks,
not builder-selected ASAR or transitive/native qualification. Final assembled-app
E2E, actual IPC/native exit and filesystem crash evidence remain separate.

[Benchmarks](../../docs/dev/benchmarks.md), the [registry](../../benchmarks/registry.json),
[explicit Quit contract](../../docs/dev/DESKTOP_QUIT_COORDINATION.md) and
[compatibility policy](../../docs/dev/macos-compatibility.md) remain authoritative.
No startup latency, memory/disk or release-support improvement is claimed.

Native first navigation now claims the remembered target in main immediately
after authenticated root readiness and calls the same restore/authorization/
cancellation path used by IPC. It loads the project as the first application
document. The private resume endpoint refuses an explicitly unmounted identity;
ordinary explicit open retains its existing behavior. Failure falls back to the
chooser only when root health confirms no retained project child, and exposes
the failure once to the renderer. An uncertain child remains a recovery error.

The opt-in `DISCO_STARTUP_DIAGNOSTIC=1` reports a project-navigation paint marker
on the owned main-process stdout. It observes an enabled current-project button
after two animation frames following document load. It grants no readiness or
write authority and runs no observer in ordinary launches. The native timing
runner starts the executable normally and attaches CDP only after this marker,
so debugger/observer initialization cannot stall the startup being measured.
Raw debugger-inclusive timings from the functional runner remain separate.

### Compatible application updates

`VIEW_COMPATIBILITY` and `compatibleViews` declare the current presentation schema
and its explicit predecessor allowlist. App versions alone no longer invalidate
presentation state. Main retains UUID + canonical path isolation and reuses the
first existing scoped draft in current, 0.1.9, then 0.1.8 order. Existing unreadable
bytes still require explicit recovery; they never fall through to an older view.
Concurrent requests share the same selected DraftStore and its recovery state.
New scopes use `view-v1`; reused legacy scopes keep their location. An unknown
schema remains incompatible. Chooser preference survives a compatible update.
The saved route and presentation return on project reentry; neither scientific
results nor action consent become authoritative through this restoration.

Updater notifications publish only while the scientific UI is running, so late
update-check results cannot replace startup or recovery guidance.
