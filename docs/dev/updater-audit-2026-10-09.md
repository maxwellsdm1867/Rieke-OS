# In-app updater audit, October 9, 2026

## Finding

The unsigned-testing updater has a reproducible multi-minute validation cost and
inadequate failure reporting. A retained real 0.1.9 app successfully installed the
earlier-published 0.1.10 bytes (source `0aeced7`) in an isolated native helper replay, taking 250.819 seconds;
100.520 seconds elapsed before the original process exited. Native copying itself
took 9.484 seconds. This successful replay does not identify the cause of the
user's earlier failed attempt.

The installed user app already reports 0.1.10 because a prior session manually
replaced it. That manual replacement is not evidence of updater success. The
prior failed helper receipt contains only a generic Deferred error, so an exact
copy/process/disk failure cannot be recovered from it. An earlier rejection did
identify changed files in the old runtime; retaining exact inventory checks is
necessary to avoid silently treating those changed bytes as a verified rollback.

## Changes

- Compute archive SHA256 and SHA512 together, reading the archive once per check.
- Validate runtime resources and compute the whole-bundle digest from the same
  canonical inventory. Bind the parsed manifest and its captured raw hash; retain
  exact resource membership, content, sizes, permissions and link confinement.
  Preserve the existing digest format and every lifecycle/copy boundary.
- Reuse the current-app digest produced by the post-exit validated inventory when
  recording the previous app. Do not reuse evidence from before process exit.
- Remove the adjacent duplicate unsigned source signature verification. Keep
  source, staged-copy and final-destination signature checks, quarantine and
  running-process refusal.
- Restore the old app if final verification fails after activating its replacement;
  include rollback-receipt publication failure in activation recovery.
- Preserve bounded private error/phase/code/stderr and timing evidence. Report
  actual retained locations if recovery itself fails. Clear stale helper results
  before a new handoff.
- Persist a private display-only operation pointer. Failed/restored outcomes remain
  visible after restart and ordinary update checks. Reject foreign, linked,
  exposed, oversized or malformed records. No receipt grants installation authority.

## Evidence and reproducibility

The matched helper replay completed in **152.938 seconds** with the repair versus
**250.819 seconds** originally (39.0% shorter in this single local observation).
Parent readiness/exit took 62.887 versus 100.520 seconds. This measures the helper
boundary only: coordinator checks, service drain, download and extraction are not
included. Both destination and retained prior digests were independently checked.
The target payload was identical for these two runs; OS cache state was uncontrolled.

A fresh GitHub check found that public 0.1.10 assets were replaced at 20:32 UTC on
October 9 without changing the version. The current source is `31182a4`; ZIP SHA256
is `4a04b4a60d61df30a0553d6a2cc96f45fc824c5a8bdb4e3f0ae7e2b9e3948bdc`, and
its descriptor SHA256 is `1d86f4e0685d4d4772241c96f6dff219bcc0c679a6dae1f9bc630224825e5fd4`.
The earlier ZIP used by the matched timing replay is
`f45024ba91a2a9b69a821d1c8b7cdd7fb5c0cff8e67692c4eb969cbd32d4347b`.
The original packaged 0.1.9 helper also installed those current-publication bytes
successfully in 319.951 seconds, with 121.291 seconds before parent exit and 9.274
seconds of copying. That independent functional replay is separate from the matched
earlier-payload timing comparison.

Replacing assets under the same version can invalidate a prepared cache and force
a fresh download; the existing checksum checks correctly reject stale bytes. The
original reported failure predates this replacement, so it is not assigned this
cause. Future changed bytes should receive a new version rather than replacing
an already offered release.

The work starts from GitHub main `035e295ba01e648005dde24fc4cdbbc4dab412e4`.
Native measurements, scripts, exact source hashes, per-command logs and results
are retained in `benchmarks/results/updater-audit-native/` in this checkout. The
native evidence README identifies the actual bundle commits and test seams.

The helper replay uses actual retained 0.1.9 and the published 0.1.10 bundle,
actual Electron/Python identity and process-exit checks, real signatures, native
copying and exact retained/destination digests. The `open` boundary is intercepted
so installation and launch request can be tested without accessing a user project.
A separate isolated GUI startup check covers the projects screen and orderly quit.
Candidate source overlays are explicitly identified by hashes; they are not
published/resealed application packages. OS file caches are uncontrolled, and
single-run timing comparisons are diagnostic observations, not latency guarantees.

An owned live process was correctly rejected by the running-app check. Reopening
an app during copying is a viable rejection path, but is not established as the
cause of the original incident. Original app/profile/project files are not used
as destructive fixtures.

Scoped regression commands (from repository root):

```sh
node --test desktop/updates/tests/testing-updater.test.cjs desktop/updates/tests/public-examples.test.cjs desktop/updates/tests/updater.test.cjs desktop/tests/testing-install.test.cjs desktop/tests/bootstrap.test.cjs desktop/tests/bootstrap-install.test.cjs desktop/tests/bootstrap-digest.test.cjs desktop/tests/installation-keep-public.test.cjs
```

The frontend update policy/lifecycle command is documented in
`workspace-app/src/app-updates/AGENTS.md`. Required core and matched million-row
query regression receipts are separate from native updater evidence. Consult the
actual receipts for their outcome; a source test does not qualify installation.

## Remaining qualification limits

The subsequent un-intercepted native relaunch test exposed a separate concrete
failure: the Node-mode helper passed `ELECTRON_RUN_AS_NODE=1` through macOS `open`
to the updated app. The installed host's `open(1)` explicitly documents inherited
environment variables. Normal and rollback launches now remove this helper-only
flag from their child environment. This explains a launch failure after a successful
replacement; it does not recover the cause of the original generic Deferred receipt.

- A successful macOS launch request is not an expected-build startup acknowledgment.
  Automatic rollback after a subsequent startup crash remains unimplemented.
- Exception recovery is stronger, but the installation lock is still not a durable
  power-loss/crash-recovery transaction journal.
- The original failing 0.1.9 application variant is not identical to the replay's
  entire prior bundle, although the packaged updater/helper modules are identical.
- A shipped 0.1.9/0.1.10 app runs its embedded old updater until replaced. Source
  fixes alone cannot retroactively change the updater performing that first hop.
- This branch is an unreleased repair; it does not replace public 0.1.10 assets or
  establish signed/notarized, clean-machine, Intel or broad macOS compatibility.
