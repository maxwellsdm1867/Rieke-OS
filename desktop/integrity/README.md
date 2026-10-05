# Application integrity and recovery

[Verification](verify-application.cjs) audits immutable application bytes;
[recovery](verification-recovery.cjs) orders accepted work before presenting
failure. [Main](../main.cjs) retains admission, menu/windows, restoration and Quit
composition. See [local instructions](AGENTS.md) and [desktop navigation](../AGENTS.md).

| Public entry | Contract and errors |
| --- | --- |
| `verifyApplication({bundle,signed,run,signal,progress})` | Full inventory and compatibility audit followed by outer seal. Returns `{verified:true,publisherAuthenticated:Boolean(signed)}`. Unsigned seal success does not authenticate publisher. Invalid/mixed/corrupt inventory, seal failure or cancellation rejects; no reseal or user-data repair. |
| `runAuditCommand(command,args,{signal,timeout})` | Owns only its spawned read-only audit child. Default timeout120000ms; abort/timeout sends SIGTERM then SIGKILL after1000ms. Output is bounded; promise settles on child close, not abort alone. |
| `repairGuidance(bundle)` | Ordinary Quit and trusted reinstall instructions preserving project folders/settings. No repair action is executed. |
| `recoverVerificationFailure({blockNewWork,pause,saveDrafts,closeServices,showRecovery})` | Blocks synchronously, then awaits pause/drafts/services before recovery presentation. Separate pauseError, drafts and services retain partial failure. Callback admission/presentation exceptions propagate. |
| `cleanupAfterVerificationRecovery(result,retryCleanup)` | Only Boolean services.ready===true reuses the existing result. Otherwise calls retryCleanup; successful prior closure must not erase failed-draft receipts. |

Verifier imports Node path/child_process and root [physical filesystem](../physical-fs.cjs),
[resource validation](../updater-validation.cjs), [bundle manifest/identity](../bootstrap.cjs).
Recovery has no imports or mutable private owner state. Resources derive from the
explicit bundle argument. Readiness, canonical project identity and scientific
writer ownership remain [supervisor](../supervisor.cjs)/Python responsibilities;
[strict replacement and bounded Quit](../close/README.md) stay distinct.

Executable [public examples](tests/public-examples.test.cjs) show immediate block,
awaited cleanup, retained failed-draft receipt, exact Boolean readiness and
pre-aborted verification. [Original verifier tests](tests/verify-application.test.cjs)
use fresh synthetic inventory and injected seal calls, including corruption and
unsigned identity; their one actual disposable Node child checks audit cancellation.
[Recovery tests](tests/verification-recovery.test.cjs) retain the Quit seam.
These examples do not launch codesign, Electron or a scientific/native service.

From this folder: `node --test tests/*.test.cjs`. From repository root:

```sh
node --test desktop/integrity/tests/*.test.cjs desktop/tests/close-packaging.test.cjs desktop/tests/main-quit-recovery.test.cjs desktop/tests/main-startup-restoration.test.cjs
python3 -B -m unittest python.tests.test_architecture_guard python.tests.test_desktop_release_plan
```

The root packaging check asserts exact default/preview source entries and direct
staged require resolution for main plus six moved entries, with missing/stale and
broad test-inclusion faults. It does not build ASAR or audit every transitive module.
The [Python boundary tests](../../python/tests/test_desktop_verification_boundary.py)
separate lightweight launch readiness from explicit full byte auditing.

Parent integration updates [catalog](../../docs/architecture/adopted-port-checks.json),
[ledger](../../docs/architecture/core-module-ledger.md) and
[path companion](../../docs/architecture/core-module-paths.json); an old catalog
is not made runnable solely by these moves. Actual installed seal/signing, audit
cancellation and final packaged UI/native teardown remain separate acceptance.
[Benchmarks](../../docs/dev/benchmarks.md), [registry](../../benchmarks/registry.json)
and [macOS policy](../../docs/dev/macos-compatibility.md) retain qualification gates.
No owner benchmark exists; ui.native.navigation remains an unsupported release
requirement. No latency, power-loss or release improvement is claimed.
