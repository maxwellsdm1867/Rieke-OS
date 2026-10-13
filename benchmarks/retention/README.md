# Retained UI diagnostics

This diagnostic mounts the **actual App** and navigates through its public
controls. The fixed `workflow-million` harness deliberately mounts/unmounts
Inspector itself and cannot measure a change to App's retained route owner.
Neither diagnostic replaces the fixed correctness/million suite.

Run serially with the same harness, dependency locks and runtime, against an
immutable integrated baseline and a frozen candidate:

```sh
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark_retention.py \
  --source-root /absolute/source/checkout --samples 3 \
  --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --output /absolute/new/output
```

Add `--expect-retained` for the candidate. This requires identical Inspector and
trace canvas nodes after returning through App history and Protocol tabs. All
runs require the expanded fixture branch and selected trace window to restore,
and retain actual request ledgers. A new document also restores a real
DraftStore snapshot with matching project and protocol identity. Candidate runs
add the actual SQLite presentation-cache path: first a successful canonical
overview writes the snapshot, then a new document displays it while an explicit
fixture activation barrier holds scientific readiness. No canonical overview or
data-store reads may start before readiness, the cached overview must be inert,
and the canonical result must replace values in the same overview DOM node.

The runner always starts its own 1,000-epoch Flask fixture. No arbitrary backend
URL or user-project argument exists. `/projects` is an explicit shell inventory
double; `/project/activate` is a held fixture admission response. Other scientific
requests run actual routes over the existing workflow SQL/index/admission
doubles. The renderer's draft bridge calls the actual DraftStore on a fresh
owned output directory, without Electron IPC. Startup/draft/cache failures remain
failures, not missing samples silently dropped from a median.

All three identical warm navigation samples finish before the separate cold
restoration check. `warm_navigation` and `restoration` have independent statuses
in the browser receipt. A failing historical restore leaves all warm samples
available but still fails the overall command; continuing to the candidate
requires explicit review of that retained failure. Candidate restoration must
pass. No failed cold observation becomes a passing overall receipt.

Receipts bind source-start/end file hashes, harness files, runtime versions,
fixture identity, raw requests and cleanup. Browser numbers are ordinary
click-handler-to-correct-DOM/two-RAF observations in development React, not native
compositor presentation. Saved-display timing is a new-document diagnostic with
held activation, not a real cold native process measurement. The observed
1,000-epoch fixture is too small to qualify million-scale performance.

## Native project retention

`desktop/e2e/retained-projects.dev.cjs` exercises the actual current `main.cjs`
under development Electron. It requires a **separately staged desktop tree**
with an exact clean runtime manifest. Do not point it at an installed app or
reuse a stale build as the candidate. Reuse matching runtime dependencies by
copying/cloning them into the owned staging tree, then use the established
`tools/desktop_build_runtime.py --refresh-application --output <staged/runtime>`
to refresh actual application/frontend bytes and manifests after freezing source.
Do not edit manifest source identity by hand.

`tools/stage_retention_desktop.py` performs that staging using an APFS clone,
checks the Python/MySQL/desktop dependency policies, copies tracked desktop files,
invokes the existing refresh builder, and refuses a dirty or mismatched receipt:

```sh
.rieke-runtime/benchmark-python/bin/python -B tools/stage_retention_desktop.py \
  --source-root /absolute/frozen/source \
  --runtime-source /absolute/owned/build/runtime \
  --dependency-root /absolute/matching/desktop
```

It prints a staging receipt and path under a fresh `disco-retention-stage-*`
temporary directory. It does not install or launch the app. This step builds the
frontend and refreshes an owned runtime, so coordinate load before running it.

```sh
node desktop/e2e/retained-projects.dev.cjs \
  --source-root /absolute/frozen/source \
  --desktop-root /absolute/owned/staged/desktop \
  --dependency-root /absolute/matching/desktop \
  --commit EXACT_CLEAN_COMMIT \
  --output /absolute/new/native-output
```

The driver creates its own isolated HOME, profile, two empty native projects and
runtime processes. It verifies scope before UI interactions, enumerates actual
attached WebContentsViews rather than mistaking the host recovery webContents for
the scientific renderer, and checks A→B→A preserves document token, webContents
identity, Data stores view and nonzero visible bounds without rebuilding overview.
It records navigation events, request counts, elapsed samples and screenshots.
It then quits through the real draft barrier, verifies both project drafts and
native clean shutdown, and restarts the same owned profile to check exact saved
project/location restoration in a new document.

This native empty-project test proves lifecycle composition, not populated
scientific readiness or a universal switch latency. The full-App populated
browser fixture supplies separate trace and presentation checks. Development
Electron is not an installed-package release qualification.
