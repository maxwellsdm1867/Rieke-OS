# Lazy chooser experiment: modest chooser/resource benefit, no demonstrated scientific speedup

Tested source: **`5310eb6c2047ba026dbe9242af9b41f6b50c3694`**, an isolated archive of base `ad52bcf9a1b3f80a302bac19fc94a53f0ed0a776`. The flag is default-off. The witness mechanism is absent. Full package verification is retained for every root and project child. No installed app, user project, package-owner checkout, credentials or release was modified.

The change skips root-only MySQL executable probes and parser initialization. Project Open still performs both before native project initialization and authoritative readiness. A necessary failure-path correction reports pre-database initialization failure through the existing private child pipe. Identity/stage validation plus observed exit authorize removal of only that spawned child record; a late validated receipt remains reconcilable. This does not claim clean database shutdown or relax later-init recovery.

## Counterbalanced result

Baseline–lazy–lazy–baseline ran **2026-10-04 01:55:48.043Z–02:00:52.741Z** on one owned diagnostic Disco.app, separate fresh profiles and identical synthetic inputs. All four passed. Means below are observations from two samples per mode, not calibrated release budgets or percentiles.

| Endpoint/resource | Baseline | Lazy | Interpretation |
|---|---:|---:|---|
| Launch → native window visible | 0.95 s | 1.10 s | Structural window, not usable data |
| Launch → genuinely usable chooser | 13.99 s | 12.36 s | 1.62 s earlier, about 12% |
| Launch → project authoritative interaction | 36.40 s | 35.91 s | 0.49 s difference |
| Project selected → authoritative interaction | 22.37 s | 23.50 s | 1.14 s longer in this sample |
| Launch → first exact scientific trace | 49.83 s | 49.58 s | Essentially unchanged in this sample |
| Selected → first exact trace | 35.79 s | 37.17 s | Necessary data-opening cost remains |
| Ordinary Quit → zero owned processes/sockets | 3.03 s | 3.11 s | No demonstrated quit improvement |
| Sampled root RSS before chooser | 197.5 MiB | 119.6 MiB | About 78 MiB lower sampled root RSS |
| Sampled cumulative owned-process CPU, complete two-project scenario | 70.38 s | 67.47 s | About 2.92 CPU seconds less observed |

Raw chooser / first-trace / Quit seconds in order:

- A0: 13.886 / 49.901 / 3.126
- B1: 11.857 / 49.886 / 2.852
- B2: 12.865 / 49.270 / 3.367
- A3: 14.084 / 49.751 / 2.930

Root parser initialization was 1.822 and 1.846 s in A, absent in B. Project parser initialization remained about 1.85–2.07 s in both. Every sample completed three full runtime passes (root plus two project children), approximately 10.01–11.04 s each. Full verification remains a dominant cost. The first scientific result is an authenticated HTTP trace with a 127-sample exact analytic oracle and UUID/rate/unit checks; renderer refresh is marked separately, not mislabeled as trace-chart first paint.

All four imports ended `complete`, `catalog_committed=true`, no warnings, with 3 cells/129 epochs. Two project services stayed isolated; the second was empty while the first retained 129 epochs. Native clean-shutdown records, absent runtime/socket files and zero owned executable-prefix processes were checked after every sample. Final manifest and ASAR hashes were unchanged and the H5/truth files matched their seal.

## Correctness and the preserved RED

The original deferred-failure test on `ee72155` exposed a real lifecycle gap: chooser worked and project error was visible, but a dead native-project child that failed before DB startup had no clean DB receipt. It remained recovery-required; Electron Quit exited with recovery pending and left the root Python chooser paused. The exact owned root was manually terminated with SIGTERM after authenticated session/executable/process-birth checks and verification that there was no DB or scientific worker. **This was manual diagnostic cleanup, not an automatic or graceful Quit pass.** Interruption records and RED evidence remain preserved.

The narrow private failure outcome fixes that case. The subsequent `0bb6479` correction passed its native test, but review found a late-reader race. Final `5310eb6` retains and reconciles late outcomes; six outcome tests include a deterministic reader delayed beyond the original wait, malformed/wrong-stage/wrong-identity rejection, and live/replaced process guards. All 31 existing desktop tests and one sampler lifecycle regression test pass with packaged Python 3.11.13 / Node 24.13.0. An initial suite invocation without PYTHONPATH failed import and is retained separately.

Final-source native deferred-failure test passed at **01:53:23.752Z**: chooser usable, project error visible, no project-ready state, no DB initialization, catalog unchanged, ordinary Quit → zero. This deliberately resealed a fault fixture that throws during parser initialization; it did not bypass integrity checks or claim to test native ABI corruption. Healthy source bytes and manifest were restored exactly before the successful real-UI scientific smoke (**01:53:51.030–01:55:14.939Z**) and ABBA. The independent reviewer gave a narrow source GO for `5310eb6` before timing; result review remains separate from production approval.

## Interpretation and next action

This supports a **modest earlier-chooser/lower-root-resource benefit**, not a meaningful demonstrated launch-to-science speedup. Do not expand the mechanism merely to obtain a larger number. Keep the minimal default-off candidate for independent result review; production adoption is a product decision about the earlier chooser and reduced idle root footprint, followed by normal integration qualification. The source/private-pipe failure correction deserves its own lifecycle review even if deferral is declined.

The user's Excel analogy is appropriate at the workflow level: Microsoft documents workbook-corruption recovery when a workbook is opened, with a distinct Open and Repair path. That supports distinguishing application availability from data-opening/recovery; it does not establish Excel's internal startup implementation. [Microsoft workbook recovery](https://support.microsoft.com/en-us/excel/repair-a-corrupted-workbook). Deferring expensive setup to actual user actions follows [Electron performance guidance](https://www.electronjs.org/docs/latest/tutorial/performance).

Keep source-before/after-parse hashes, connected-database ownership, transactions, postcommit reconciliation, complete-generation publication, revision/freeze and export checks. Raw-copy durability, duplicate/postcommit recovery, complete metadata/missingness/precision coverage, actual parent death and earlier partial initialization remain separate audit/test work. The session-witness proposal remains held.

## Next step for the dominant repeated verification cost

Use deployment and capability boundaries, not another per-child witness protocol:

1. **Define distribution authority first.** Audit real Developer ID signing/notarization, nested native code, resource-envelope coverage, ASAR fuses and the external Python/MySQL tree. Gatekeeper/ASAR are not a blanket promise of continuous verification of Python data imports. The current unsigned preview manifest proves consistency against its colocated bytes, not publisher identity. Keep its existing full checks until an explicit, reviewed replacement policy exists. [Apple Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web), [Electron ASAR integrity](https://www.electronjs.org/docs/latest/tutorial/asar-integrity).
2. **Validate a complete version at installation/update.** Authenticate the artifact, verify its complete inventory/bytes and compatibility, run relocated native import/ABI/scientific smoke, then atomically promote a staged version. Preserve the old version and never update files beneath live sessions. Only then consider cheap normal-launch identity/version checks backed by actual platform/resource protection. If the external runtime remains mutable under the chosen threat model, install-time success alone is insufficient: retain verification before use. Signing and verification relocation need their own measured and fault-tested proposal; this experiment does not authorize them.
3. **Separately assess a lightweight chooser.** A chooser that lists projects without starting the scientific Python parent could avoid an entire redundant scientific-root pass while retaining complete project verification at Open. This is a larger ownership/registry refactor, not a flag to skip checks in the current root. First map the chooser's exact authority requirements and retain validated paths, project locks, child ownership and honest “project initializing” states. Measure chooser plus first project/trace and failure cleanup; do not equate shell availability with validated data.

Required proof before changing policy: interrupted/mixed-version updates never become active; altered/missing manifest/resources, link escape, wrong native architecture and failed relocation imports block scientific readiness; normal relaunch cannot attach to the wrong generation/PID/database; previous sessions cannot use an in-place modified runtime; rejected startup and recovery preserve exact values, IDs and accepted operations; Quit leaves no owned processes/sockets on success. Test the supported macOS range natively, preserve unsigned-versus-signed evidence separately, and profile complete launch-to-science/CPU/I/O before accepting a performance claim. None of these protections replaces source pre/post-parse hashes, SQL commit reconciliation or live generation/revision gates.

## Exact evidence and limits

Evidence root: `/Users/maxwellsdm/Documents/Codex/2026-10-03/task-10/lazy-root-owned/evidence/`.

- `preparation.json`, `healthy-preparation.json`, `failure-fixture*.json`: clone provenance, candidate/fault/restoration and harness hashes.
- `deferred-failure-1/`: preserved RED and `manual-cleanup.json`; `deferred-failure-2/` and `deferred-failure-3/`: correction/native passes.
- `outcome-unit-tests-v2.log`, `existing-desktop-tests-v2.log`, `sampler-tests-v2.log`: 6 + 31 + 1 tests, not combined with native case counts.
- `healthy-smoke-1/`: final-source UI/scientific smoke.
- `abba-1/comparison.json`, `analysis.json`, `final-verification.json`, `phases-*`: raw samples, derived metrics, fixture/job/hash checks and per-process phases. `abba-1.log` retains controller output.
- `host.json`: Apple M1 Pro, 10 logical CPUs, 16 GiB, macOS 27.0.1 build 26A434 arm64; Electron 44.5.0, Node 24.13.0, packaged Python 3.11.13/MySQL 8.4.2. No macOS 14 native-validation claim.

OS caches were uncontrolled; this was neither first install nor a cache-purged cold launch. CPU/RSS sampling can miss short-lived processes; summed RSS includes shared pages. The sampler now owns/cancels its timer and awaits in-flight work between variants, so previous variants do not multiply sampler load. Small-sample changes in project latency/aggregate RSS must not be attributed to a particular cache or scheduling mechanism without further evidence. No further runtime work is planned for this experiment.
