# Rieke OS desktop

This package contains the Electron shell for the existing scientific React app.
The first implementation targets macOS Apple Silicon. Its complete resource
closure currently requires a macOS 14.0 floor; support on that minimum still
needs real-device qualification. Other platforms are not advertised. The optional
debugpy PID attachment helper is excluded with provenance in the runtime receipt.

Native signing applies the existing `allow-jit` entitlement only to the bundled
Python executable. The signed scientific and JIT workflow remains unqualified
without Developer ID credentials and independent final-artifact evidence.

## Local build

Building requires Node/npm, Python 3.11 or newer for build tools, uv, the macOS
developer toolchain and network access. Running the assembled app uses only its
bundled interpreter, parser, MySQL and frontend. It never provisions dependencies
at launch.

The desktop app requires no Docker CLI, Docker Desktop or Docker daemon. Each
desktop project uses the native MySQL executable inside the app bundle, with its
database files outside the bundle in the project folder. Opening, creating,
importing, querying, exporting and reopening desktop projects work independently
of Docker.

An older project can still have its only database inside the previous source
installation's Docker container. Reading that existing database is a one-time
source migration option, not a desktop runtime requirement. Receive a portable
transfer prepared by the source installation instead when Docker is unavailable
on the destination. A completed desktop copy uses the bundled native database.

```sh
npm ci --prefix workspace-app
npm ci --prefix desktop
python3 tools/desktop_build_runtime.py
npm test --prefix desktop
python3 tools/desktop_runtime_manifest.py
CSC_IDENTITY_AUTO_DISCOVERY=false npm run dist --prefix desktop
```

The artifacts are in `desktop/dist`, including the complete
`mac-arm64/Rieke OS.app`, DMG, updater ZIP, blockmaps and `latest-mac.yml`.
Build caches and artifacts are ignored by Git. Parser and native dependency pins,
license inventory, source provenance and resource hashes are carried inside the
runtime; recordings, scientific projects and credentials are excluded.

For development against the assembled runtime, run `npm start --prefix desktop`.
For local icon-based testing, place the complete unsigned app at
`~/Applications/Rieke OS.app` without overwriting an existing installation.
The complete app at that fixed location runs independently of the checkout.
This build explicitly selects the `unsigned-testing` distribution. Its Install
and Open action verifies the complete app and installs a user-owned copy while
preserving macOS quarantine. Its GitHub checks show newer testing versions;
downloads and restart/install require the user's action. Ordinary Quit never
installs a testing update. See [the testing release workflow](../docs/dev/GITHUB_TESTING_RELEASE.md).

The default signed distribution still requires Developer ID verification for
installation and updates. Unsigned testing does not qualify that production path.

## Packaged end-to-end tests

After building, run the actual packaged UI and failure suites:

```sh
npm run test:e2e --prefix desktop
npm run test:e2e:startup-failure --prefix desktop
npm run test:e2e:updater --prefix desktop
```

The UI suite copies the complete packaged app into a fresh temporary HOME, uses
an isolated Electron user-data directory and creates disposable native projects.
It tests the real sandboxed React UI, durable saved views, project navigation,
duplicate launches, renderer recovery and orderly shutdown. Only native folder
chooser return values are stubbed. Set `RIEKE_E2E_H5` to a read-only source fixture
to also test real import activity and native close deferral; the suite copies it
before import, and CI runs without private recordings. The startup-failure suite
changes and reseals only its disposable app copy to test failed backend readiness.
These tests never open or close the user's installed app. If orderly shutdown
fails, the test preserves its isolated processes for investigation.

For an explicit no-Docker recording workflow check, run:

```sh
python3 tools/desktop_no_docker_smoke.py --recording /path/to/test-recording.h5
```

This uses the packaged runtime with a fresh HOME and restricted PATH. It denies
container commands and non-MySQL Unix sockets before access, tests those denials
with separate negative controls, and then exercises native project creation,
recording import, tags, query, export, reopen and orderly shutdown. The source
recording is copied for import; the host Docker daemon and installed app are
untouched. This is process-level test instrumentation, not a kernel sandbox or
clean-machine qualification.

Receipts and screenshots go to `docs/dev/desktop-ui-e2e/`. The updater suite uses
the pinned real client with local HTTP transport faults. These unsigned local
tests do not qualify signed installation or signed old-to-new recovery.

## Ownership and shutdown

The Electron main process owns the private authenticated production Waitress
backend and all project services. A private child-pipe binding receipt precedes
the first authenticated HTTP request. The renderer is sandboxed, has no Node
integration and uses narrow validated top-frame IPC. Main injects per-session
headers only into verified owned origins; Python source update APIs are disabled
for desktop services.

Renderer drafts and outstanding preference writes must acknowledge persistence
before backend drain. Imports, inbox work, transfers, streaming responses and
other active writes defer closure. Every owned project/database service and the
root backend must acknowledge actual exit. Timeouts and crashes do not authorize
process termination or app replacement.

An older failed launcher can retain its idle root after rejecting a legacy
project. If recovery refuses Quit, preserve the installed bundle and service
registry for an ownership review. A controlled shutdown must first verify the
exact owned processes and confirm that no project service, database, import or
other writer is active; app replacement continues to refuse a live prior root.
Deleting registry files cannot establish that shutdown. The new launcher offers
legacy migration into a separate verified copy while preserving the source
project and its existing source application. This work's isolated tests leave
the user's older running installation unchanged.

## Signed releases

The public provider is explicitly `maxwellsdm1867/Rieke-OS`. Application,
frontend, and desktop metadata are coordinated at version 0.1.3. The current
`unsigned-testing` policy uses the separate `desktop-test-v0.1.3` prerelease;
it does not promote or replace the stable source release. Build from the exact
clean canonical source commit and qualify the resulting bytes before publishing.
`tools/desktop_release.py` separately rejects dirty, mismatched or foreign signed
production baselines and incomplete promotion.

The desktop candidate workflow builds exact tagged sources. Signing is performed
on the native closure before resealing the runtime manifest and signing the outer
bundle. Notarization follows. Configure protected `desktop-signing` secrets
`CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_API_KEY`, `APPLE_API_KEY_ID` and
`APPLE_API_ISSUER`; no credentials are included in the app. Configure required
reviewers for `desktop-publishing` in GitHub settings; YAML does not enable them.

Promotion takes an existing successful candidate run and reviewed qualification
JSON from `release-evidence/` on the default branch. Evidence uses format
`rieke-desktop-qualification`, version 1, exact application/source/platform
identity, the artifact inventory from `artifacts.json`, and an entry for every
R01–R12 requirement. Each entry requires `passed: true` and `receipts` containing
a description and SHA-256 of the real-artifact evidence. Unit-test counts do not
substitute for qualification. Use confidential-source-free receipts.

Promotion is serialized across versions. Existing release bytes cannot be
overwritten on retry. A complete draft becomes public without changing latest;
all public asset hashes are checked without authentication before stable/latest
is changed. An unsigned candidate must never be supplied as qualified evidence.
The legacy source-release workflow is manual and does not promote itself latest.

Updates download quietly, are checked about hourly with jitter and require exact
signature, version, platform, resource and data-format validation. A signed prior
app is retained before installation. Ready means those candidate checks passed;
native staging and startup health are separate. Only the coordinator invokes the
native installer after draft/drain acknowledgements. Recovery verifies the
retained signer and data contract and uses the same controlled installation code.

The production specification remains the acceptance authority:
[electron-production-spec.md](../docs/design/electron-production-spec.md).
Signing, notarization, clean-machine installation, source-user migration, full
fault-injection qualification and a real signed old-to-new update remain gates
until independently demonstrated with the final artifacts.
