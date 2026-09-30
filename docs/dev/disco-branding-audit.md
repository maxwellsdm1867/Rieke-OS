# Disco application branding audit

The scientist narrowed issue #20 on September 30, 2026 to the application name. **Disco** is the product name; **maxwellsdm1867/Rieke-OS** remains the repository. Repository renaming and executable, bundle-path or release-archive renaming are outside this scope. Existing installation/profile identifiers and filenames are retained deliberately. This audit records source verification; it does not qualify a published release or an actual installed 0.1.0 upgrade.

Disco is the application name. About introduces **Data Inspection, Selection, Comparison Operations**, with **A Rieke Lab OS** as supporting attribution. Startup, recovery, menus, quit, update screens, web titles, and current documentation use Disco. The disco ball remains the default; the classic emblem is an optional choice from About.

## Reference audit

The [complete reference inventory](disco-branding-reference-inventory.json) records the before inventory (120 files, 394 matching lines), the disposition of each original hit, and a post-edit scan. Changed line numbers are not interpreted as identity changes. Historical reports, scientific/MATLAB references, and compatibility values are deliberately distinguished from current product copy. Additional audit/evidence documents add intentional historical mentions after that scan.

| Retained category | Reason |
| --- | --- |
| `org.riekeos.desktop` | Stable bundle/signing/installation identity; changing it can disconnect the existing updater. |
| Electron `Rieke OS` profile selection before `Disco` display naming | Captures the established user-data path, then restores it after setting the display name. Explicitly supplied profile paths also remain intact. Existing drafts, preferences, icon choice, and update receipts are reused. |
| `.rieke-runtime`, `.rieke-os`, existing storage keys and `rieke-*` document formats | Existing installations/projects and scientific identities continue using their established locations/contracts. No new browser caching, database, or global save mechanism was added. |
| `Rieke OS.app`, `Contents/MacOS/Rieke OS`, `Rieke-OS-<version>-arm64.zip` | Existing installers/updaters validate exact bundle, executable, and archive layouts. `CFBundleDisplayName`/`CFBundleName` become Disco while these paths remain migration aliases. These identity-bearing filenames remain deliberately unchanged under the application-only scope. |
| Signed/testing descriptor `repository: maxwellsdm1867/Rieke-OS` and source `rieke-release.json.repository` | The repository remains Rieke-OS. Release provenance and any additive `canonical_repository` field identify that actual repository. |
| Repository URLs | Rieke-OS is the operational default for discovery, support, downloads and publication. The existing bounded parser support for both owned repository identities does not change that default or authorize foreign repositories. |
| Historical documentation, fixtures, earlier release evidence, scientific/MATLAB code | Recorded history and unrelated scientific names must not be rewritten as though earlier releases were called Disco. Existing documentation filenames remain compatible links. |
| Git remote | Remains the real Rieke-OS remote. No repository rename is planned for this issue. |

There is no application service worker, IndexedDB database, or web-app install manifest in the inspected web source. Existing local/session storage keys and loopback routes, origins, CORS/CSP policy, and scientific API paths stay stable. A host-only notification session cookie retains at most 12 display claims across localhost ports; it has no Max-Age or Expires and contains no update authority or scientific state. Existing per-origin session storage remains the fallback. The favicon asset filename remains a compatible URL; its pixels are the disco ball. Shared project formats and user-assigned project names are unchanged.

## Updates and publishing

Signed desktop, testing desktop and source update discovery use the existing Rieke-OS feed directly. Release-tool defaults and distribution/provenance metadata identify Rieke-OS. Support/download links, package metadata and local Git remotes remain valid without a repository migration. The owned-repository URL/provenance checks continue rejecting foreign repositories; clean-checkout, exact-tag and asset-integrity checks remain required.

Hosted release workflows resolve the actual approved `GITHUB_REPOSITORY`. The current repository remains Rieke-OS. No release was published by this audit.

The earlier migration investigation found that the proposed `maxwellsdm1867/disco` endpoint returned HTTP 404 and that the archived 0.1.0 source manager rejected a Disco release URL. These are historical compatibility findings, not pending requirements to rename the repository. Keeping the real repository avoids introducing that migration into application naming.

## Verification and limits

- Desktop regression suite after safe-quit and undo integration: 98 run, 97 passed, one skipped, including real disposable Electron tests and new profile preservation, feed fallback, asset alias, and foreign-origin rejection cases.
- Focused Python release/update/runtime checks: 37 run, 36 passed, one optional runtime integration skipped. After safe-quit and undo integration, the full Python suite ran 1,120 tests: 1,087 passed and 33 optional tests skipped.
- After merging current main, all 354 frontend tests and the Vite build passed. Generated `index.html` uses Disco; existing favicon URLs point to the default disco-ball assets.
- [Archived source-manager evidence](disco-legacy-discovery-evidence.json) executes `python/workspace_updates.py` from reported source commit `61f9e44c98fa541d670ecb78c35b3389ee2c1b7c` with an in-memory Disco release response. That old manager returns `error` because its official release URL check requires Rieke-OS. No network, installation, or scientific project was changed in this reproduction.
- The reported commit has no `desktop/` source tree. Its manifest source commit alone therefore does not establish the exact installed desktop updater implementation. Old desktop redirect compatibility remains unproven; the pre-bridge source updater also has a strict single-repository redirect policy.
- Isolated real Google Chrome smoke passed across two different `127.0.0.1` ports: discovery claims returned true/false/false on sequential port navigation, a fresh browser context claimed independently, and the session cookie expiry was -1. The rendered launcher title was Disco; selecting both About icons updated the favicon. The apple-touch/default installation asset remained the disco ball. This uses mock API responses and does not qualify existing scientific projects. Reproduce with `npm --prefix desktop run test:e2e:branding` after building the frontend.
- Real existing-project Chrome profiles, generated signed/unsigned installed artifacts, first-open installer labels, production restart/recovery behavior, sharing/receiving a project, and actual installed 0.1.0 upgrade/profile continuity have **not** been qualified by this audit.
- Package qualification entrypoints were repaired to import `workspace_native_mysql.stop_native_database`; both `packaging/verify_workflows.py --help` and `packaging/verify_e2e.py --help` run successfully in the application venv. Their generated-page title assertions require Disco. This repairs the harness entrypoints and does not constitute an installed 0.1.0 upgrade qualification.

Application-only follow-up verification: 99 desktop tests run (98 passed, one skipped), 355 frontend tests passed, 39 focused Python update/release tests run (38 passed, one skipped), six additional feed/distribution tests passed, production build and release configuration validation passed. Regression cases verify direct Rieke-OS discovery with one request on success or 404/authentication/server failure, and checked-in source/distribution/descriptor provenance. Modified E2E scripts passed syntax checks; no actual installed upgrade is claimed.

## Release qualification limits

Repository migration and old-link redirect qualification are no longer required for issue #20. Future release publication still needs the normal signed/unsigned package and installed-upgrade qualification, using disposable test copies and recorded artifact hashes. Those release checks have not been claimed by this source audit. Existing bundle/executable/archive aliases remain supported rather than being renamed for this issue.

User projects, scientific identities, and existing export artifacts must retain their original names and meaning throughout these steps.

The issue #18 safe-quit implementation was merged while retaining the Disco profile/icon behavior. New closing/recovery copy and previously missed active Rieke Lab OS setup/installation/catalog titles were corrected to Disco; lab attribution remains supporting About copy.

Issue #19 UndoControls, scoped history, native Cmd+Z routing, and text undo were integrated alongside the Disco icon/profile APIs. Final integration checks above include these features. The application-only branding scope retains Rieke-OS as the repository. Actual installed 0.1.0 qualification remains separate release work.
