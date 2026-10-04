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
| Sampled root peak before chooser (RSS) | 197.5 MiB | 119.6 MiB | About 78 MiB lower sampled root peak before chooser |
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

This supports a **modest earlier-chooser/lower-root-resource benefit**, not a meaningful demonstrated launch-to-science speedup. Do not expand the mechanism merely to obtain a larger number. Keep the minimal default-off candidate for independent result review; production adoption is a product decision about the earlier chooser and lower sampled root peak before chooser, followed by normal integration qualification. The source/private-pipe failure correction deserves its own lifecycle review even if deferral is declined.

The user's Excel analogy is appropriate at the workflow level: Microsoft documents workbook-corruption recovery when a workbook is opened, with a distinct Open and Repair path. That supports distinguishing application availability from data-opening/recovery; it does not establish Excel's internal startup implementation. [Microsoft workbook recovery](https://support.microsoft.com/en-us/excel/repair-a-corrupted-workbook). Deferring expensive setup to actual user actions follows [Electron performance guidance](https://www.electronjs.org/docs/latest/tutorial/performance).

Keep source-before/after-parse hashes, connected-database ownership, transactions, postcommit reconciliation, complete-generation publication, revision/freeze and export checks. Raw-copy durability, duplicate/postcommit recovery, complete metadata/missingness/precision coverage, actual parent death and earlier partial initialization remain separate audit/test work. The session-witness proposal remains held.

## Recommended package-verification ownership policy — proposed, not implemented

**Approve lightweight normal launches for qualified signed releases; retain full launch/project verification for unsigned previews.** This separates a stable, authenticated distribution from frequently rebuilt diagnostic artifacts. Do not use the experimental metadata witness as authority. The current candidate changes no verification policy.

| Boundary / owner | Qualified signed release | Unsigned preview |
|---|---|---|
| Build and staged install/update / packaging and updater | Require expected Developer ID team/application identity, notarization, verified nested signatures and complete resource coverage including external Python/MySQL. Authenticate the inventory through that signed artifact; verify exact inventory, containment, links and bytes before executing staged native import/ABI smoke. Packaging also qualifies scientific behavior and supported macOS versions. Enable both Electron ASAR integrity and OnlyLoadAppFromAsar fuses. Promote a complete version atomically only after owned sessions drain; retain the prior version. No in-place updates. | Full inventory/bytes/containment plus relocated import/ABI and scientific qualification. Record source/artifact digest and label explicitly unsigned. A colocated editable manifest establishes consistency only; it cannot authenticate its author. Manual complete replacement, no unsigned automatic updates. |
| Every ordinary launch / Electron supervisor | Lightweight version, platform/architecture, protocol, canonical runtime path and required-file checks; require a qualified installed version. An install receipt records state, not authentication. No whole-tree rehash and no scientific imports merely to list projects. Platform/ASAR enforcement stays enabled. | Keep existing full verification in each root and project startup. A future chooser with no scientific Python service can omit that root service entirely, but every scientific child still fully verifies. No receipt-based sharing. |
| Every project open / project service | Import required native/parser modules and prove actual MySQL/service readiness before scientific ready or writer admission. Keep project identity/locks, live process birth/executable/session binding, DB ownership/recovery, transactions and scientific generation checks. | Same checks, in addition to full package verification. |
| Explicit “Verify Installation” / diagnostic verifier | With owned scientific sessions closed, reauthenticate publisher/signatures and fully verify inventory, links and bytes; run separate bounded native capability diagnostics. Never silently bless a changed manifest. | Fully check consistency against the recorded build inventory; clearly report that publisher authenticity is unavailable. Obtain a trusted replacement to resolve uncertain provenance. |

The signed policy deliberately accepts **delayed detection of post-install changes to external interpreted resources**. Lightweight checks catch missing required files, incompatible versions/architecture, import/ABI failures and services that cannot become ready. They do not detect all dormant corruption, or a modified Python module that still imports and returns plausible results. Install-time full verification catches mismatches at installation; explicit full verification catches later byte/inventory differences at diagnosis, not continuously. Neither a one-time hash nor metadata scan removes check/use races. A same-user attacker able to replace app code and its verifier is outside this lightweight policy's assurance; signing does not make every Python read continuously authenticated. This is a consequential detection tradeoff for approval, not security equivalence. [Apple Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web), [Apple code/resource signing](https://developer.apple.com/library/archive/technotes/tn2206/_index.html), [Electron ASAR integrity](https://www.electronjs.org/docs/latest/tutorial/asar-integrity).

The unsigned default intentionally continues paying the measured roughly 10–11 s per full startup pass to detect ordinary local packaging drift before service admission. It still cannot detect a coordinated rewrite of both files and their editable manifest. A lightweight unsigned mode plus optional diagnostic would save repeated scans but lose that automatic drift detection; **do not adopt it by default**. Full checks here provide consistency, not publisher authenticity or proof that top-level imports executed only after verification.

On a known package mismatch, stop new scientific work and show **“Installation damaged or incompatible”** with Verify Installation, Replace/Reinstall and diagnostic details. Drain owned services gracefully; if cleanup fails, expose recovery-required and preserve ownership/journals. Never force-kill DB, delete project data, create an empty replacement DB, rebaseline the manifest or continue using mixed imported modules. Repair replaces only the complete application from a verified staged artifact (trusted manual build for preview), then starts a fresh session. Project recovery remains a separate workflow. If Electron cannot start, reinstall from the distribution channel is the repair path.

Smallest next slice is a reviewed signed-install validator and replacement transaction with corruption/interrupted-promotion tests; only after that qualifies should normal signed-launch hashing change. Acceptance must demonstrate altered/truncated/mixed staged bundles and wrong native architecture rejected, failed imports never ready, ordinary and aborted startup Quit → zero or explicit preserved recovery, exact scientific values retained, and real macOS 14 plus current-host coverage. Measure complete launch-to-first-result afterward; optional diagnostic duration is reported separately. No runtime/check removal is authorized by this proposal.

## Exact evidence and limits

Evidence root: `/Users/maxwellsdm/Documents/Codex/2026-10-03/task-10/lazy-root-owned/evidence/`.

- `preparation.json`, `healthy-preparation.json`, `failure-fixture*.json`: clone provenance, candidate/fault/restoration and harness hashes.
- `deferred-failure-1/`: preserved RED and `manual-cleanup.json`; `deferred-failure-2/` and `deferred-failure-3/`: correction/native passes.
- `outcome-unit-tests-v2.log`, `existing-desktop-tests-v2.log`, `sampler-tests-v2.log`: 6 + 31 + 1 tests, not combined with native case counts.
- `healthy-smoke-1/`: final-source UI/scientific smoke.
- `abba-1/comparison.json`, `analysis.json`, `final-verification.json`, `phases-*`: raw samples, derived metrics, fixture/job/hash checks and per-process phases. `abba-1.log` retains controller output.
- `host.json`: Apple M1 Pro, 10 logical CPUs, 16 GiB, macOS 27.0.1 build 26A434 arm64; Electron 44.5.0, Node 24.13.0, packaged Python 3.11.13/MySQL 8.4.2. No macOS 14 native-validation claim.

OS caches were uncontrolled; this was neither first install nor a cache-purged cold launch. CPU/RSS sampling can miss short-lived processes; summed RSS includes shared pages. The sampler now owns/cancels its timer and awaits in-flight work between variants, so previous variants do not multiply sampler load. Small-sample changes in project latency/aggregate RSS must not be attributed to a particular cache or scheduling mechanism without further evidence. No further runtime work is planned for this experiment.
