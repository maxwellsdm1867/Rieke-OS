# Installation and rollback: retained root owners

The installation runtime stays at its existing desktop root paths. This is an
explicit organization decision: spawned helper filenames are installed contracts,
and moving them would add parser, staged layout and native ASAR qualification
work without enough benefit for this release. Keeping update-recovery alone in a
new folder would separate it from the helper it launches. No forwarding facade,
new runtime folder, parser exception or package pattern is introduced.

Start with [desktop guidance](AGENTS.md), [updates](updates/README.md),
[close coordination](close/README.md) and [integrity](integrity/README.md).

| Root owner | Public contract and dependency boundary |
| --- | --- |
| [bootstrap.cjs](bootstrap.cjs) | APP_ID, enclosingApp, signatureIdentity, assertNotRunning, compatibleManifest, installCompleteBundle, readBundleManifest, bundleDigest, verifyTestingBundle, quarantinePreserved. Shared whole-bundle identity/copy policy serves main, integrity, sealing, update helpers and tooling. |
| [install-name.cjs](install-name.cjs) | assertInstallNameCompatible and assertBundleDestination preserve canonical executable/destination names. Shared by bootstrap, resource/update validation and both recovery paths. |
| [update-recovery.cjs](update-recovery.cjs) | verifyPriorBundle, retainPriorBundle, restorePriorBundle. Signature/compatibility checks precede drain; only ready===true may spawn root recovery-install.cjs. The spawn event precedes authorizeQuit/app.quit. Spawn acknowledgement is not complete installation or process-exit proof. |
| [testing-install.cjs](testing-install.cjs) | processCreationIdentity, applyTestingInstall, launchTestingInstall, restoreTestingPriorBundle, sha256, bundleDigest. Owned private receipts bind app/path/PID/creation/checksums. The root helper must acknowledge its own PID, current parent PID, target version and archive before returning ready; application replacement waits for the exact current process to disappear and revalidates bytes. |
| [recovery-install.cjs](recovery-install.cjs) | Dedicated main CLI, invoked only as the installed app-owned helper. Validates existing destination/signatures and waits for existing PID-liveness protocol, then installs and requests normal macOS launch. It has no testing creation-time/readiness-packet protocol. Do not invoke main in a unit fixture. |

Shared root physical-fs preserves physical ASAR bytes; updater-validation preserves
resource/version validation; supervisor.atomicJSON is the existing signed receipt
writer. Node path/os/crypto/child_process/fs adapters retain current behavior.
Security, signing, quarantine, bundle names and user profile/project locations are
unchanged. Verification does not reseal changed data or grant scientific readiness.

## Installed path and readiness distinctions

Signed restoration joins `__dirname/recovery-install.cjs`. Testing launch joins
`__dirname/testing-install.cjs` and checks `__filename` lies within the exact
installed bundle. Root shared bootstrap, updater-validation, physical-fs and
install-name remain beside the installed testing helper. These filenames are
asserted by the public examples; no directory migration is implied.

Signed `restorePriorBundle({app,manifest,prepareQuit,authorizeQuit,run,spawnHelper})`
returns the deferred prepareQuit result unchanged; after validated prior bundle,
ready drain and successful spawn it returns `{ready:true,restoring:true}`. Spawn
errors reject and grant no quit authority. The separately executed signed CLI's
PID-liveness wait is weaker than the testing creation identity protocol; preserve
that distinction instead of claiming equivalent proofs.

Testing `launchTestingInstall({receiptPath,currentExecutable,currentPid,run,
spawnHelper,readyTimeoutMs})` validates current parent identity and helper origin,
then waits for a matching readiness line. Spawn alone cannot resolve it. Failure
or timeout rejects without signaling the current app. On success it returns
`{ready:true,helperPid,resultPath}`. `applyTestingInstall` publishes readiness,
checks exact parent identity until disappearance, and rechecks cached bytes before
replacement. A changed creation time after readiness is still a rejection.
Partial/failed installation and rollback remain existing recovery outcomes, not
permission to alter scientific data or macOS approval.

## Executable public examples and limits

[installation-keep-public.test.cjs](tests/installation-keep-public.test.cjs) uses
actual public functions and fresh inert owned files. Its command adapter recognizes
only explicit fixture commands and rejects everything else; it never delegates
to execFile. Its spawn adapter returns inert EventEmitter/stream objects, asserts
exact root helper arguments and rejects signals. The staged testing helper is an
unchanged source copy inside an owned fake app.asar directory, preserving the real
origin check and root-relative dependencies. It is not a real ASAR or installed app.

Examples prove deferred/spawn-failed signed recovery grants no authority, signed
spawn acknowledgement precedes quit, testing spawn is insufficient until a matching
readiness packet, and testing creation identity mismatch rejects both before launch
and after readiness. Injected signature/Plist/identity responses exercise orchestration;
they do not validate real signatures, host tools, process identity or native exits.
Recovery CLI main remains source-only, never invoked.

From repository root:

```sh
node --test desktop/tests/installation-keep-public.test.cjs
```

Do not run `desktop/tests/testing-install.test.cjs` broadly as a source check: it
contains actual Electron/ASAR, installed interpreter and host command paths.
Original bootstrap/install-name/quarantine and E2E evidence keep their own scopes.
Parent owns mapping this one controlled example file, navigation and finite ledger
keep decisions. Full final installed-helper execution, signature/quarantine,
physical ASAR, normal replacement/rollback/reopen and scientific app acceptance
remain separately reviewed gates. Read [macOS policy](../docs/dev/macos-compatibility.md),
[benchmarks](../docs/dev/benchmarks.md) and [registry](../benchmarks/registry.json).
No performance, power-loss, native compatibility or release qualification follows.

## Updater failure recovery audit (2026-10-09)

Complete-bundle replacement now restores the retained app when verification of
its replacement fails after activation, including the final signature check. A
failed first installation removes the rejected canonical destination. Failure to
publish the testing rollback receipt is covered by the same restoration path as
launch refusal. These are exception-recovery guarantees, not power-loss recovery.

Testing helper results record bounded failure message/code/stderr and phase,
along with completed phase durations. Helper startup failures surface the private
result's reason to the caller. Successful `Installed` still means that macOS
accepted the launch request (`launch_requested: true`); it does not prove the new
process reached application readiness. Automatic early-crash rollback and durable
crash-recoverable transaction journals remain open work.

Archive SHA256 and SHA512 are computed in one file traversal. An adjacent duplicate
unsigned source signature check is removed; validation after drain/parent exit
and of the copied staging bundle remains required. Timing observations and native
qualification limits belong in the separate updater audit evidence.

`bundleDigest(bundle, {runtimeManifest, runtimeManifestSha256})` optionally checks
runtime resources against the same canonical records that produce the unchanged
whole-bundle checksum. Both the parsed manifest and the captured manifest hash
must match the supplied raw-byte hash. Exact resource inventory, content, size,
permissions and runtime-contained link targets are still checked. Unsigned
candidate/source/staging checks use this shared scan; signed resource verification
is unchanged. After actual parent exit the helper retains the current-app digest
from its resource-validated scan, avoiding an adjacent second whole-app read.
The initial application audit and macOS signature checks remain separate checks.
