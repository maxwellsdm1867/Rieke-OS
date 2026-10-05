# Desktop close coordination

DraftBarrier correlates renderer draft acknowledgments. QuitCoordinator bounds
explicit exit while preserving unconfirmed cleanup. They retain separate existing
interfaces; Electron composition remains in [main](../main.cjs).
See [local instructions](AGENTS.md), [desktop navigation](../AGENTS.md), the
[owner ledger](../../docs/architecture/core-module-ledger.md),
[executable catalog](../../docs/architecture/adopted-port-checks.json),
[P07 adoption](../../docs/architecture/0.1.8-first-port-slices.md#project-runtime-lifecycle-obligations)
and [explicit Quit contract](../../docs/dev/DESKTOP_QUIT_COORDINATION.md).

| Public entry | Caller contract | Errors and ordering |
| --- | --- | --- |
| `draft-barrier.cjs`: `DraftBarrier` | Construct with optional timeout/send adapter; `prepare(windows,{timeout})`; `acknowledge(payload,window)`; default 10,000 ms. | Exact request/window and payload checks. Malformed acknowledgments throw TypeError; unmatched acknowledgments throw Error. Destroyed/unavailable renderer, failed send, negative/missing acknowledgment return ready:false with retained-view warning. No backend authority inferred. |
| `quit-coordinator.cjs`: `QuitCoordinator` | Inject prepareDrafts, cleanup, exit, optional publish/deadlines; `quit()` coalesces calls. Default total 35,000 ms, drafts 5,000 ms. | Drafts precede cleanup using remaining budget. Failures/timeouts become recovery warnings; explicit exit ready:true is distinct from clean, services_closed and drafts_saved. |
| `quit-coordinator.cjs`: `bounded` | `bounded(action,milliseconds,reason)` races the action against a timeout. | Timeout returns ready:false, reason, timedOut:true; action rejection remains rejection; timers clear on settlement. |

Main's `prepareQuit` stays strict: every draft acknowledgment then positive drain
before replacement. `orderlyQuit` owns finite explicit exit and verification/startup
cancellation. A Quit receipt may retain recovery; it is not a clean-stop receipt.
No IPC, persistence, process ownership, readiness or security behavior changes.

DraftBarrier's only import is Node crypto; QuitCoordinator imports nothing.
Dependencies arrive through the existing constructor seams. `pending`, timers and
other state remain conventional implementation details; an existing test inspects
pending and this is not JavaScript-enforced privacy. No empty private directory or
new re-export layer is introduced.

## Executable local examples

The [public example file](tests/public-examples.test.cjs) is runnable source, not
pseudocode. It demonstrates exact-window rejection followed by an accepted draft
acknowledgment, finite/coalesced explicit Quit with recovery warnings, and both
success and timeout call shapes for exported `bounded`. It imports only the two
public entries and uses controlled adapters without Electron or native services.
From this directory:

```sh
node --test tests/public-examples.test.cjs
node --test tests/*.test.cjs
```

From repository root, run the source-only packaging check and main composition
contracts with existing frontend parser dependencies:

```sh
node --test desktop/tests/close-packaging.test.cjs desktop/tests/main-quit-recovery.test.cjs desktop/tests/main-startup-restoration.test.cjs desktop/tests/verification-recovery.test.cjs
python3 -B -m unittest python.tests.test_architecture_guard python.tests.test_desktop_release_plan
python tools/architecture_guard.py check
python tools/architecture_guard.py plan --base <pre-change-ancestor>
python tools/architecture_guard.py test --base <pre-change-ancestor> --language desktop
python -B tools/desktop_application_profile.py --root .
```

The catalog maps these close tests alongside existing P07 contracts. npm's explicit
root test patterns also include `close/tests/*.test.cjs`; guard path validation
admits this direct test directory narrowly. Release planning excludes this test
root but still classifies production by basename. Cross-owner tests stay in the
root tests directory; final-app E2E stays separate.

## Packaging and qualification

`package.json` adds the two exact close CJS paths; root `*.cjs` alone does not
include nested files. The source packaging test validates default and inherited
preview exact allowlists, excludes tests/broad patterns, stages the declared app
files, and resolves literal local requires in main and the two moved entries using the
existing parser. Other desktop module internals are outside this check. Negative fixtures cover either missing entry, either configuration's
accidental test inclusion, stale main import and missing staged dependency. It
never executes main, builds/signs an app, or launches Electron.

This limited source check is not actual builder-selected/as-built ASAR evidence.
Python source-profile closure audits a different runtime and cannot prove CJS
inclusion. Final assembled app inclusion, packaged UI/IPC, real child/native exit
and normal teardown remain separate final-app E2E/native gates on the exact
candidate. VM fixtures and source guards cannot satisfy them.

[Benchmarks](../../docs/dev/benchmarks.md) and the existing
[registry](../../benchmarks/registry.json) remain authoritative. No dedicated
startup/close benchmark or speed improvement is claimed. Native navigation is an
unsupported requirement, not a passing benchmark. Read the
[compatibility matrix](../../docs/dev/macos-compatibility.md) before native packaging.
