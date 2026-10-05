# Renderer draft storage

[DraftStore](draft-store.cjs) persists a bounded renderer view and preserves
unreadable state until explicit recovery. Its supplied directory is independent
of this source location. [Main](../main.cjs) retains authenticated origin/project
scope and constructs project-specific namespaces; this module is not an IPC or
process owner. See [local instructions](AGENTS.md) and
[desktop navigation](../AGENTS.md).

| Public interface | Contract and errors |
| --- | --- |
| `new DraftStore(userData)` | Uses `userData/drafts`; main supplies launcher userData or its canonical UUID/path/compatibility namespace. No directory migration. |
| `load(projectId)` | Validates identity. Returns null for absent file, exact version-1 draft, or a version-1 unreadable recovery marker. Wrong-owner, symlink, oversized, malformed/mismatched and unreadable state require recovery. |
| `save({projectId,value})` | Exact two-key envelope; value is a matching `rieke-renderer-draft` version1 object with a nonarray object value. Loads prior state before writing; pending recovery refuses overwrite. Returns `{saved:true}` only after temporary-file rename. Validation and filesystem errors propagate. |
| `reset(projectId)` | Requires verified pending recovery. Renames original to `<id>.corrupt-<uuid>.json`, clears pending recovery and returns `{reset:true}`. Never follows/removes a symlink target. |
| `validStoredDraft(value,projectId)` | Existing envelope structural/identity predicate. It is not origin admission or scientific validity. |
| `MAX_DRAFT_BYTES` | 2 MiB; serialized saves and existing file size remain bounded. |

Directory creation requests 0700 and temporary files use exclusive create mode0600.
A temporary write then rename is atomic replacement, not a database transaction or
power-loss fsync guarantee. The renderer owns save serialization; no new lock,
retry policy or storage abstraction was added. Pending state is conventional
implementation state, not JavaScript-enforced privacy.

Main's scopedDraftStore binds a current authenticated window origin to project
UUID, canonical path and app-version:view-v1 namespace. Identical UUIDs at different
paths must not borrow saved views. This owner does not derive that trust itself.
Saving a view occurs before StartupSession.remember in main; that ordering remains
unchanged. Strict replacement and bounded explicit Quit remain distinct
[close coordination](../close/README.md) obligations.

## Public examples and verification

The executable [public examples](tests/public-examples.test.cjs) use only this
entry and fresh disposable temporary directories. They demonstrate absence,
validated roundtrip, unreadable-byte refusal, explicit preserved reset and reuse.
The [original contracts](tests/draft-store.test.cjs) retain mismatched/oversized and
symlink target preservation coverage unchanged. From this folder:

```sh
node --test tests/public-examples.test.cjs
node --test tests/*.test.cjs
```

From repository root with existing frontend parser dependencies:

```sh
node --test desktop/drafts/tests/*.test.cjs desktop/startup/tests/*.test.cjs desktop/tests/close-packaging.test.cjs desktop/tests/main-startup-restoration.test.cjs
python3 -B -m unittest python.tests.test_architecture_guard python.tests.test_desktop_release_plan
```

The root-owned [P07 catalog](../../docs/architecture/adopted-port-checks.json),
[adoption record](../../docs/architecture/0.1.8-first-port-slices.md),
[ledger](../../docs/architecture/core-module-ledger.md) and
[path companion](../../docs/architecture/core-module-paths.json) record integrated
mappings. During branch review the parent integrates those mappings separately;
local source moves alone do not make an old catalog runnable.

The existing root packaging check now covers main plus nine adopted nested entries,
including this owner's `../security.cjs`. It checks exact default/preview source
allowlists, excludes tests, and exercises stale/missing-path faults in an owned
staged tree. It does not build/run Electron, parse every transitive module, or
prove actual ASAR inclusion. Original tests use local filesystem behavior, not
native persistence/crash qualification; direct registered scopedDraftStore
composition remains a coverage gap. Final assembled-app E2E is separate.

[Benchmark guide](../../docs/dev/benchmarks.md), [registry](../../benchmarks/registry.json),
[explicit Quit contract](../../docs/dev/DESKTOP_QUIT_COORDINATION.md) and
[compatibility matrix](../../docs/dev/macos-compatibility.md) retain existing gates.
No draft latency/memory/disk or power-loss improvement is measured here.

The nine-entry source check distinguishes eight direct main imports from the
testing coordinator’s sibling validator; it is not a complete transitive audit.
