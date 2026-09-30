# Rieke OS release operations

The updater is a foundation for signed application releases, not `git pull`.
Development checkouts can check the official GitHub release channel but cannot
install into themselves. A missing GitHub release is reported as unavailable.

## Publication to update discovery

The application checks `https://api.github.com/repos/maxwellsdm1867/Rieke-OS/releases/latest`.
PyPI and TestPyPI are not update sources. A Git push, version tag, or Actions
candidate artifact alone does not make an update visible to users. The candidate
must be promoted to a published stable GitHub Release with its signed manifest
and matching platform bundle attached. Publish it as the latest release only
after the validation gates below pass; drafts and prereleases are excluded.

The app checks on startup, every 15 minutes while visible, and on return after
that interval. A newer stable version highlights Release / Publish with an Update
badge, without a toast or automatically opened dialog. Clicking it shows release
notes and download progress. Trusted managed installations automatically download
and verify the update. Transient check
failures retain an already discovered update and explain the failure inside the
panel. After the chooser and all project services have closed, the next launch
through the stable manager activates the prepared release. A busy installation
continues using its current version; updates never force-close another service.

There are two distinct repositories, as checked on 2026-09-29:

| Repository | Current publication state |
| --- | --- |
| `maxwellsdm1867/epicTreeGUI` (this development checkout) | Regression and signed-candidate workflows; no tags or releases, no configured environments or repository Actions secrets visible to this account. The previous updater incorrectly checked this empty release channel. |
| `maxwellsdm1867/Rieke-OS` (public app distribution) | Stable versions through `v0.1.2`, with a source ZIP and SHA256SUMS. Its sole workflow verifies source installation. It has no updater module, signed update manifest, or prebuilt desktop installer. |

This change points discovery, release links and future signed artifact URLs at
Rieke-OS. The updater, metadata, UI and release workflow must be carried into that
distribution before its users receive them. The publication job runs only in
Rieke-OS, so a development tag cannot accidentally publish in epicTreeGUI. This
checkout has no `release-signing-public.pem`; production signing and publication
protection still need configuration.

## One-click distribution target

The current [Electron production specification](../design/electron-production-spec.md)
selects a complete signed Electron app, bundled Python/MySQL and electron-updater
as its sole desktop update authority. The [earlier gap map](../design/one-click-installer.md)
preserves the audit and comparison of alternatives. The Python manager
and source artifact described below remain the existing development mechanism.
See the [primary-source review](INSTALLER_PRIMARY_SOURCE_REVIEW.md) for packaging
and signing constraints. No desktop artifact was built during that planning pass.

Users should download a self-contained desktop installer from GitHub Releases,
open it once, and thereafter launch the installed app normally. The installer
must contain Python and its locked packages, the pinned parser and compiled
utilities, the built React assets, the private MySQL runtime, and the Electron
lifetime owner/updater. The RSA manager/key below belong to source installations,
not a second desktop updater. Setup must run offline without Git, uv,
Node/npm, a compiler, Homebrew, Docker, or an existing Python installation.

The current source artifact does not satisfy that contract: its Python runtime
is created on the user's computer, and its editable parser/venv paths cannot
simply be copied to another machine. The remaining packaging work is a relocatable
Python runtime with resolved parser imports, offline native-runtime preparation,
a native app entry point, and a signed/notarized macOS installer. Developer ID
signing/notarization credentials are separate from the updater's RSA signing key.
Validate the final installer on a clean machine without development tools and
exercise a real old-to-new automatic update before advertising one-click install.
Apple Silicon macOS is the only currently validated native artifact platform.

### MATLAB is optional

The web app does not launch MATLAB or require a MATLAB license/runtime. Its
Python backend writes `.mat` exports with NumPy/SciPy and reads `.ugm` masks.
MATLAB is needed only by users who choose to open the EpicTreeGUI export in
MATLAB. Core install, launch, import, browsing, tags, query, and update validation
must run without MATLAB. Licensed MATLAB validation belongs to the optional
EpicTreeGUI interoperability claim, rather than a prerequisite for installing or
shipping the core app. Continue running Python export/mask compatibility tests
in the normal suite.

## Implemented contracts

- `rieke-release.json`, frontend package version and npm lockfile version agree.
- `python/workspace_updates.py` checks the official stable channel, caches checks
  for 15 minutes, and preserves the running app on offline/server failures.
- A managed installation has a stable `manager.py`, installed public signing key,
  independent `preferences/`, and immutable-per-version `releases/<version>/`.
- The signed manifest uses RSA PKCS#1 v1.5 with SHA-256 over the exact bytes of the
  base64-decoded `payload`; the envelope contains `algorithm`, `payload` and
  `signature`. The trusted key is installed out of band, never accepted from the
  release download. The manifest binds version, Git commit, platform, artifact
  URL, byte length, SHA-256 and database compatibility generation.
- Staging verifies signatures/hashes and archive paths before executing setup.
  It builds a separate locked runtime at its final release path, probes startup,
  and publishes a ready receipt. It never opens projects or starts databases.
  A failed stage leaves the active pointer untouched and preserves diagnostics.
- Staging uses a separate lock and can run while the app is open. Activation
  requires exclusive lifetime locks; managed chooser and detached project
  processes hold shared locks. Activation refuses incompatible database
  generations. App updates never perform implicit project migrations.
- Successful automatic checks start one background staging attempt per new
  version per service session. Failed downloads can be retried in the panel.
  Other services reuse only a completed receipt matching the signed manifest.
  The stable manager applies prepared updates on the next launch when all
  application locks are free. Workspace launchers created by a managed install
  point to that manager instead of pinning a particular release directory.
- Managed launch uses built frontend assets. Source/development launch still
  builds the frontend. Managed launch directly uses its Python service and needs
  no Node/npm, Git or Docker command. The previous version remains available for recovery.
- MySQL 8.4.2 server, client and dump tool are app-private. The Apple Silicon
  dependency closure and micromamba linker are SHA-256-pinned in
  `python/workspace-mysql-runtime.json`. Setup verifies package archives, links
  them offline into `.rieke-runtime/mysql`, repairs macOS ad-hoc signatures after
  prefix relocation and probes all three executables before recording readiness.
  No database, system service, PATH installation or Homebrew package is created.
- Release bundles include the verified native package archives, so native MySQL
  setup is offline at the destination and does not require user-installed MySQL.
  Archives retain upstream license/recipe metadata. Do not strip this metadata
  when distributing the bundled GPL MySQL and third-party dependencies.

The current artifact is a signed application source bundle, built UI and native
MySQL package archives. It is not yet a macOS `.app` or a fully bundled offline
Python runtime. Building/staging the Python and frontend portions still requires
Git, uv, Node/npm, a C++ compiler and access to pinned dependencies. Once prepared,
managed launch needs no frontend build tools, external MySQL or Docker. Packaging
the Python interpreter/dependencies and stable launcher into a signed/notarized
desktop bundle remains a distinct release-engineering step.

## Establish release trust

A maintainer must create an RSA release signing key in their chosen secret
management system and commit only its public PEM as `release-signing-public.pem`.
No private key or generated trust anchor is included by this change. Protect the
`release-signing` GitHub environment and set its `RELEASE_SIGNING_PRIVATE_KEY`
secret. Configure required reviewers on `release-publishing` to verify the
release-evidence gates below before public promotion. Review ownership and
rotation procedures before distributing the key.

Publish the current reviewed application source first. The source and parser
commit must be fetchable by a clean machine. The current dirty development tree
is intentionally rejected by the release packager.

## Candidate pipeline

PR CI runs frontend tests/build, Python workspace tests and coordinated-version
validation. A separate Apple Silicon job prepares the private native runtime,
checks full project readiness and runs real database lifecycle and transfer tests
without requiring a signing key or release tag. Pushing a `v<version>` tag
triggers `workspace-release-candidate.yml`, which checks out
the reviewed version tag, exercises setup and tests on Apple Silicon,
including real native MySQL lifecycle and native project transfer/copy tests,
builds a signed artifact and uploads it as a GitHub Actions artifact. After the
protected `release-publishing` environment approves promotion, a dependent job
publishes those exact artifacts as the latest stable GitHub Release. Manual
dispatch builds a candidate by default; its optional `publish` input requests
the same protected promotion. Existing release assets are never overwritten.

Before promoting the candidate to a stable GitHub Release, require recorded
passing evidence for real MySQL/DataJoint import/edit/export/restart, complete
workspace transfer to a different path and machine, previous-to-current update
and recovery, and active-worker shutdown. Licensed MATLAB handoff regressions are
required when advertising the optional EpicTreeGUI interoperability feature;
MATLAB is not a core app dependency.
Mocked/unit-only tests do not satisfy those gates. A missing runner is not a pass.
Only upload the exact signed artifact and `rieke-release-manifest.json` under its
matching `v<version>` GitHub Release tag. Linux is not an advertised artifact yet.

## Managed installation and applying an update

After distributing the trusted public key with a reviewed application, initialize
an empty installation folder:

```sh
python3 python/workspace_updates.py --installation /path/to/RiekeOS init
python3 /path/to/RiekeOS/manager.py --installation /path/to/RiekeOS stage
python3 /path/to/RiekeOS/manager.py --installation /path/to/RiekeOS activate
python3 /path/to/RiekeOS/manager.py --installation /path/to/RiekeOS launch
```

The managed app automatically stages a new signed update while running. Close all
chooser and project-service processes, then launch normally through `manager.py`
or a workspace launcher created by the managed app. It applies the prepared
version before starting the chooser. No check/download/apply command is needed
for subsequent updates. Existing manager copies and old workspace launchers must
be upgraded once to gain this behavior; they are not rewritten in place by these
source changes.

For diagnostics, an explicit wait-and-apply command remains available:

```sh
python3 /path/to/RiekeOS/manager.py --installation /path/to/RiekeOS activate-and-launch
```

This waits at most five minutes for processes to release their locks, switches
the active release atomically, and launches it. It never force-kills workers.
Closing a browser tab alone does not stop a project service.

Fully automatic **Restart and update** still needs a coordinated request drain,
unsaved-draft preservation and shutdown acknowledgement from every project
service. The UI must not present this as implemented. Incompatible database
updates likewise stay disabled until verified backup/migration/recovery exists.
Key rotation and automatic recovery from post-activation startup failure are
also not implemented; the previous release is retained, not silently restored.


## Electron desktop qualification

The Electron candidate uses bundled Python, parser and native MySQL. Normal
launch, project creation, import and browsing require no Docker, external MySQL,
Node or MATLAB. An older Docker-backed source project is inspected before any
desktop service is started. Create a desktop copy in a new folder explicitly;
the one-time source snapshot may read an already-running source Docker database.
It never starts, stops or executes commands in Docker. Alternatively, prepare a
portable copy with the source installation and receive it in the desktop app.
The original source project is never silently converted in place.

After packaging, run these suites against the packaged candidate:

```sh
npm test --prefix desktop
npm test --prefix workspace-app
npm run test:e2e:updater --prefix desktop
npm run test:e2e --prefix desktop
npm run test:e2e:startup-failure --prefix desktop
python3 tools/desktop_artifact_e2e.py --installed 'desktop/dist/mac-arm64/Rieke OS.app'
```

The UI suite launches only scratch copies with isolated HOME and user data. It
keeps Electron sandbox and CSP enabled and tests the real packaged ASAR. OS
folder chooser return values are the explicit stubbed boundary. Set
`RIEKE_E2E_H5` to a private local recording to additionally test real active
import shutdown deferral. The scientific suite checks exact H5 sample values,
annotations, masks, query membership, downloaded JSON/SQLite/MAT exports,
restart and transfer through actual native services:

```sh
python3 tools/desktop_scientific_e2e.py --recording /absolute/path/to/fixture.h5
python3 tools/desktop_artifact_e2e.py --installed 'desktop/dist/mac-arm64/Rieke OS.app' --recording /absolute/path/to/fixture.h5
```

Private recordings remain local and must never be attached to public evidence
or build resources. Receipts bind checks to the packaged runtime manifest and
artifact hashes. A failed receipt is retained as evidence, then the final suite
is repeated after fixes. The candidate workflow runs updater transport faults,
packaged UI and extracted-installer audits before inventorying a successful
candidate, and uploads failure evidence separately.

The updater suite exercises the pinned library and real Electron HTTP transport
against a private fixture server. It covers malformed and unavailable metadata,
version rejection, checksum mismatch, interrupted downloads, unwritable cache
and unsigned candidates without authorizing a native installer. These checks
do not qualify signed Squirrel installation, notarization, cross-machine
Gatekeeper, or previous-to-current recovery. Those remain release gates when
Developer ID credentials and a second clean machine are available. Unsigned
local packages keep update installation disabled.
