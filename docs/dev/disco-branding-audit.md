# Disco migration audit — draft, not release qualification

Issue #20 is **incomplete**. The source implements a bridge client, but the repository has not been renamed and an installed Rieke OS 0.1.0 upgrade has not been qualified. Do not close the issue or rename the repository based on these checks.

Disco is the application name. About introduces **Data Inspection, Selection, Comparison Operations**, with **A Rieke Lab OS** as supporting attribution. Startup, recovery, menus, quit, update screens, web titles, and current documentation use Disco. The disco ball remains the default; the classic emblem is an optional choice from About.

## Reference audit

The [complete reference inventory](disco-branding-reference-inventory.json) records the before inventory (120 files, 394 matching lines), the disposition of each original hit, and a post-edit scan. Changed line numbers are not interpreted as identity changes. Historical reports, scientific/MATLAB references, and compatibility values are deliberately distinguished from current product copy. Additional audit/evidence documents add intentional historical mentions after that scan.

| Retained category | Reason |
| --- | --- |
| `org.riekeos.desktop` | Stable bundle/signing/installation identity; changing it can disconnect the existing updater. |
| Electron `Rieke OS` profile selection before `Disco` display naming | Captures the established user-data path, then restores it after setting the display name. Explicitly supplied profile paths also remain intact. Existing drafts, preferences, icon choice, and update receipts are reused. |
| `.rieke-runtime`, `.rieke-os`, existing storage keys and `rieke-*` document formats | Existing installations/projects and scientific identities continue using their established locations/contracts. No new browser caching, database, or global save mechanism was added. |
| `Rieke OS.app`, `Contents/MacOS/Rieke OS`, `Rieke-OS-<version>-arm64.zip` | Existing installers/updaters validate exact bundle, executable, and archive layouts. `CFBundleDisplayName`/`CFBundleName` become Disco while these paths remain migration aliases. Finder/executable branding therefore still needs a later qualified alias/layout migration. |
| Signed/testing descriptor `repository: maxwellsdm1867/Rieke-OS` and source `rieke-release.json.repository` | Legacy consumers enforce this provenance. Additive `canonical_repository` identifies Disco without invalidating the old wire contract. |
| Legacy repository URLs | The bridge accepts only the two owned repository identities. New feeds prefer Disco and fall back to the exact Rieke-OS endpoint only on canonical HTTP 404. Authentication, server, parse, and integrity failures never trigger an expanded trust fallback. |
| Historical documentation, fixtures, earlier release evidence, scientific/MATLAB code | Recorded history and unrelated scientific names must not be rewritten as though earlier releases were called Disco. Existing documentation filenames remain compatible links. |
| Git remote | Remains the real Rieke-OS remote until the authorized repository rename is performed and continuity is verified. |

There is no application service worker, IndexedDB database, or web-app install manifest in the inspected web source. Existing local/session storage keys and loopback routes, origins, CORS/CSP policy, and scientific API paths stay stable. The favicon asset filename remains a compatible URL; its pixels are the disco ball. Shared project formats and user-assigned project names are unchanged.

## Updater and publishing bridge

The desktop testing client now accepts both exact owned API/asset paths, including redirects between them, and validates returned asset URLs for either identity. Signed desktop discovery retries the legacy GitHub feed only for a structured canonical 404. The source manager similarly accepts either official release URL, artifact URL, installation identity, and signed provenance; it prefers the canonical feed and retries only a 404.

Hosted release workflows resolve the actual approved `GITHUB_REPOSITORY` for bridge publication before the rename. Baseline checks still require the checkout origin to match the selected owned repository and retain clean-checkout/exact-tag checks. Once renamed, the same hosted jobs resolve Disco. Foreign repositories are rejected. No release was published by this audit.

An authenticated read of `repos/maxwellsdm1867/disco` returned HTTP 404 on September 30, 2026. The existing Rieke-OS `desktop-test-v0.1.3` release endpoint returned its old-name release URL and expected DMG/ZIP/descriptor assets successfully. This establishes that the intended destination was not available through that account at the check time; it is not a completed reservation or rename. Canonical download/support/issue links therefore remain pending destination verification.

## Verification and limits

- Desktop regression suite: 82 tests passed, including real disposable Electron tests and new profile preservation, feed fallback, asset alias, and foreign-origin rejection cases.
- Focused Python release/update/runtime checks: 37 tests passed, one optional runtime integration skipped. After merging current main, the full Python suite passed 1,106 tests with 33 optional skips.
- After merging current main, all 335 frontend tests and the Vite build passed. Generated `index.html` uses Disco; existing favicon URLs point to the default disco-ball assets.
- [Archived source-manager evidence](disco-legacy-discovery-evidence.json) executes `python/workspace_updates.py` from reported source commit `61f9e44c98fa541d670ecb78c35b3389ee2c1b7c` with an in-memory Disco release response. That old manager returns `error` because its official release URL check requires Rieke-OS. No network, installation, or scientific project was changed in this reproduction.
- The reported commit has no `desktop/` source tree. Its manifest source commit alone therefore does not establish the exact installed desktop updater implementation. Old desktop redirect compatibility remains unproven; the pre-bridge source updater also has a strict single-repository redirect policy.
- Browser fresh/existing-session Chrome smoke, generated signed/unsigned installed artifacts, first-open installer labels, restart/recovery behavior, sharing/receiving a project, and actual installed 0.1.0 upgrade/profile continuity have **not** been qualified by this audit.
- `packaging/verify_workflows.py` cannot currently start: its pre-existing import of absent `workspace_native_database` raises `ModuleNotFoundError`. This unrelated workflow harness defect is recorded rather than treated as successful qualification.

## Required order before completion

1. Choose a new version newer than supported installed releases; do not overwrite an existing published version or tag. Publish the verified bridge under the still-existing Rieke-OS repository, retaining old descriptor and bundle/archive contracts. Qualify actual installed 0.1.0 discovery/download/restart and existing project/profile state using disposable test copies.
2. Qualify package/browser smoke and address visible legacy bundle/executable aliases. Keep compatibility layouts until the installed bridge can accept the qualified replacement layout.
3. Recheck target availability, rename the existing repository in place, update applicable local remotes, and verify issue/PR/history continuity, old-link redirects, hosted actions, project-site URLs if present, and every canonical download/support/update destination.
4. Re-run both fresh and existing Chrome sessions and the complete signed/unsigned upgrade path after the rename. Record exact artifact hashes and results before closing #20.

User projects, scientific identities, and existing export artifacts must retain their original names and meaning throughout these steps.
