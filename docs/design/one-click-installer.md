# Rieke OS one click installer plan

Architecture status: the user has selected Electron. The
[Electron production specification](electron-production-spec.md) is now the
implementation authority. This earlier plan preserves the source audit, example
systems and initial gap analysis; its AppKit/Sparkle proposal is superseded.

Reviewed 2026-09-29. This plan covers installation and automatic updates for the
public Rieke OS app. It is based on the current public distribution, the
development updater, and a [review of primary documentation](../dev/INSTALLER_PRIMARY_SOURCE_REVIEW.md).
It proposes implementation work; it does not claim that a desktop installer has
been built or that the proposed update path has passed validation.

The recommended first release is a complete macOS Apple Silicon app, built on
GitHub, installed into a user-owned application directory, and updated as a whole
signed app. Users should not need Terminal, Python, Node, Git, a compiler,
Homebrew, Docker, or MATLAB. A native launcher should own all local services so
an update can wait for an orderly app shutdown.

## Installation and update experience

The user downloads one installer from GitHub Releases, opens it, and chooses
**Install and Open**. The proposed default destination is
`~/Applications/Rieke OS.app`, which the current user can update without needing
administrator access. The installer copies the complete app and opens it. Normal
macOS download and first-open interactions still apply; one click describes the
installer's action, not the entire download and operating-system flow.

The app opens the existing browser interface after its local service is ready.
Projects remain in folders chosen by the user. Subsequent launches use the same
app icon. Available updates download in the background and appear in
**Release / Publish** as **Update** and then **Ready**. Ordinary updates should
produce no toast, system notification, or automatically opened dialog. When the
user quits and all workers have closed cleanly, the updater installs the prepared
version; the next launch uses it. Active scientific work must not be interrupted
to satisfy an update schedule.

First scope assumption: Apple Silicon Macs. Intel Macs and Windows require their
own build and native integration evidence before support is advertised. MATLAB
is optional and used only to open the EpicTreeGUI export; Python writes the MAT
files and reads selection masks without running MATLAB.

## What the inspection found

The public repository is
[`maxwellsdm1867/Rieke-OS`](https://github.com/maxwellsdm1867/Rieke-OS).
Its inspected main commit and clean local checkout were
`f52312f06a651500ea3e121feaebd118201d0f7b`. The development checkout is the separate
epicTreeGUI repository at `47f87f9f1adc373523869ac624c35fdfe566b4e9`, with uncommitted
changes. These are different application states; development behavior is not
evidence of what public users already have.

| Area | Published Rieke OS | Development checkout |
| --- | --- | --- |
| Release | [v0.1.2](https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/v0.1.2), with a 1,463,427-byte source ZIP and SHA256SUMS | Coordinated metadata still says 0.1.0. Discovery now points to Rieke-OS. |
| Installation | [install.sh](https://github.com/maxwellsdm1867/Rieke-OS/blob/f52312f06a651500ea3e121feaebd118201d0f7b/install.sh) downloads local tooling and dependencies and compiles/builds the app | Setup likewise builds Python/parser/frontend; managed launch can use prebuilt frontend assets. |
| Launch | [start.sh](https://github.com/maxwellsdm1867/Rieke-OS/blob/f52312f06a651500ea3e121feaebd118201d0f7b/start.sh) requires a terminal and installed runtime | Python manager and chooser; no native desktop entry point. |
| Automatic updates | No updater module or signed desktop update assets | Quiet badge, automatic source staging, and next-launch activation exist locally. Staging still executes setup. |
| CI | [verify.yml](https://github.com/maxwellsdm1867/Rieke-OS/blob/f52312f06a651500ea3e121feaebd118201d0f7b/.github/workflows/verify.yml) verifies a fresh source installation | Signed source-candidate workflow and a proposed tag/publication job; these have not been carried into the public repo. |
| Release protection | GitHub API returned no configured environments and no repository Actions secret names visible to this account | No distributed trusted key in this checkout. A workflow environment name alone does not establish reviewer protection. |

The development runtime measured approximately 1.3 GB for the Python venv,
302 MB for linked MySQL, and 45 MB for native package archives. These are local
disk measurements, not the size of a finished app or download. The interpreter
is an absolute symlink into the developer's uv installation, and the editable
parser `.pth` contains an absolute checkout path. Copying this directory would
not establish a portable app.

## Existing GitHub distribution patterns

GitHub can host the source, run the build, and serve the installer/update assets.
The installed application still needs a desktop updater to select its platform,
verify the downloaded package, and coordinate replacement. GitHub's automatic
Source code ZIP is not a prebuilt installer, and a successful release upload
does not by itself update users' computers.

| Pattern | GitHub's role and client behavior | Implication for Rieke OS |
| --- | --- | --- |
| Native macOS with Sparkle | Complete app archives live in Releases; a static appcast links to exact archives/signatures. Sparkle runs in the app. | Proposed Mac-first route. GitHub can host the static feed too; no custom update server is necessary. |
| Tauri with its updater plugin | Actions builds app/update artifacts; a static `latest.json` asset in Releases supplies platform URLs and signatures. The installed plugin checks it. | Strong alternative if Windows/Linux are immediate targets. Existing React can remain the frontend and Python can be packaged as a sidecar. |
| Electron with electron-builder/electron-updater | The builder publishes installers and `latest*.yml` metadata to its GitHub provider; the app's updater reads the metadata and fetches binaries. | Established cross-platform path. Requires an Electron shell and a packaged Python/MySQL runtime; the updater does not remove backend packaging work. |
| Electron Forge with update-electron-app | Forge publishes to Releases; Electron's hosted update service translates release assets into a client feed. | GitHub-based, but uses an additional hosted service. This is a distinct route from electron-builder's direct GitHub provider. |

Sources: [Sparkle publication](https://sparkle-project.org/documentation/),
[Tauri GitHub pipeline](https://v2.tauri.app/distribute/pipelines/github/),
[Tauri static updater](https://v2.tauri.app/plugin/updater/),
[Tauri Python sidecars](https://v2.tauri.app/develop/sidecar/),
[electron-builder updater](https://github.com/electron-userland/electron-builder/blob/master/website/docs/features/auto-update.md),
[Electron Forge publishing tutorial](https://www.electronjs.org/docs/latest/tutorial/tutorial-publishing-updating).

Rectangle and MonitorControl are directly verified native Mac examples. Their
app configurations embed Sparkle feed URLs and EdDSA public keys, and their live
feeds point to signed version-specific DMGs in GitHub Releases.
[Rectangle configuration](https://github.com/rxhanson/Rectangle/blob/c0ae7f87abe66f66b2857fbd4ad19ef802a9b43a/Rectangle/Info.plist),
[Rectangle feed](https://rectangleapp.com/downloads/updates.xml),
[MonitorControl configuration](https://github.com/MonitorControl/MonitorControl/blob/84ac2d72bfb53b653536e484946f6ed027e4229c/MonitorControl/Info.plist),
[MonitorControl feed](https://monitorcontrol.app/appcast2.xml).
These examples show GitHub serving app binaries while separate static URLs serve
update metadata. Rieke OS can host its static feed on GitHub too. The inspected
Rectangle public build workflow only produces an ad-hoc signed Actions artifact;
it does not establish how its production signing/publication is automated.

One directly inspected application is Electron Fiddle. Its
[Forge configuration](https://github.com/electron/fiddle/blob/a63225b53664fd750828c29aa35de4b4d0eb0b28/forge.config.ts)
publishes to `electron/fiddle` on GitHub, and its
[updater code](https://github.com/electron/fiddle/blob/a63225b53664fd750828c29aa35de4b4d0eb0b28/src/main/update.ts)
starts `update-electron-app` after a startup delay, configured for hourly checks.
That demonstrates the connection between a release publisher and installed
clients; it does not establish that Fiddle's notification or shutdown behavior
matches our quiet-update and scientific-worker requirements.

Use an existing framework's artifact generator, metadata format, signature
verification and installer. Build our own app/service lifecycle adapter and
compatibility rules. Neither a GitHub provider nor a sidecar configuration
automatically drains our detached Python/MySQL workers, preserves browser
drafts, or qualifies a database-version change. Do not use notification-producing
sample APIs as the product behavior when routine updates should stay quiet.

The desktop shell decision is conditional on platforms: AppKit/Sparkle is the
recommended first route for the current Mac-first scope. If Windows must ship
alongside macOS, evaluate Tauri before implementing I05 and I08. Electron is an
alternative when its Chromium/Node desktop environment is specifically useful.
These alternatives can reuse React and Python, but embedded webviews introduce
different origins, download/dialog behavior and process ownership that must be
tested. Framework selection does not change the I02/I03 runtime experiment.

The [GitHub desktop update comparison](../dev/GITHUB_DESKTOP_UPDATE_PATTERNS.md)
records the exact application sources, feed examples, and framework contracts.

## Proposed architecture

Use a small Swift/AppKit application to provide the app icon, launch readiness,
duplicate-launch handling, Quit, service ownership, and updater integration.
Keep React as the product interface in the browser. This does not require
rewriting the scientific application in Swift or adding Electron.

Bundle a pinned standalone Python interpreter, installed dependency wheels,
the pinned parser and compiled utilities, built React assets, and a relocatable
private MySQL server/client/dump dependency closure. Complete binary relocation
and configuration of executable paths during the build. Sign the final code,
notarize the product, and leave its contents read-only at runtime. Apple's
signature seals the app's resources and nested code; current destination-side
conda linking and ad-hoc signing cannot be used inside that sealed product.
[Apple code-signing rules](https://developer.apple.com/library/archive/technotes/tn2206/_index.html).

Proposed ownership layout:

```text
~/Applications/Rieke OS.app/       signed code and immutable resources
~/Library/Application Support/RiekeOS/  preferences, service registry, update state
~/Library/Caches/RiekeOS/          disposable runtime caches
~/Library/Logs/RiekeOS/            application and installer diagnostics
<user-selected project>/          catalog, SQL data, credentials, H5 references, exports
```

The native launcher resolves resources from its actual bundle location and
invokes its bundled interpreter by absolute path. Python bytecode, parser
configuration and temporary files must go outside the bundle or be disabled.
`doctor` validates the packaged layout and signed build receipts, rather than
requiring a Git checkout, editable package location, or Node installation.

The default packaging approach is a standalone interpreter with preinstalled
packages and a parser wheel. PyInstaller `onedir` workers are a fallback to
evaluate if that layout fails; a choice between these approaches must be based
on the relocation/import experiment, not an assumption that either handles
dynamic parser imports and native MySQL automatically.

### One desktop updater

**Recommendation:** use Sparkle for complete signed app updates. The native app
owns update state; React displays it through a local bridge. Disable the Python
manager's staging/activation routes in desktop builds. Its useful existing
tests become requirements for the new path, not proof that Sparkle preserves
those behaviors automatically. Source installations may retain a separate
explicitly identified updater if we choose to support them.

This changes the earlier source-updater direction: a shipped app should download
prebuilt software, not run `rieke.py setup` on the user's computer. The current
manager also lacks an independent bundled bootstrap interpreter, uses an RSA
manifest instead of Sparkle's EdDSA/appcast contract, reads downloads into memory,
limits artifacts to 512 MiB/extraction to 2 GiB, and rejects every symbolic link.
That extractor is unsuitable for a normal Sparkle framework bundle, whose
symlinks and executable permissions must be preserved.
[Current manager](../../python/workspace_updates.py),
[Sparkle setup](https://sparkle-project.org/documentation/).

Sparkle's automatic checks and automatic downloads need explicit configuration;
they are not silent defaults. Its scheduled-check minimum is one hour. Proposed
desktop policy: a startup check when appropriate and hourly automatic checks,
with the UI text updated accordingly. The current 15-minute development watcher
must not remain as an independent download/install authority. If 15-minute
discovery becomes a hard requirement, assess that separately before committing
to this updater policy.
[Sparkle customization](https://sparkle-project.org/documentation/customization/).

Keep ordinary updates pending until orderly app quit, including the framework's
impatient-update behavior. A custom Sparkle user driver cannot merely hide all
UI: automatic-update settings provide silent installation, and manual actions
or necessary authorization still need a conforming interface. A user-owned app
location reduces authorization requirements; managed Macs may impose other
policies. Verify these cases in the product rather than promise that all updates
can always be invisible.
[Sparkle user-interface contract](https://sparkle-project.org/documentation/custom-user-interfaces/).

## Gap map and implementation order

All entries below are open for the desktop product, even where a useful source
implementation exists. IDs are implementation work packages, not filed issues.

| ID | Gap and concrete work | Depends on | Completion evidence |
| --- | --- | --- | --- |
| I01 | Establish Rieke-OS as the public build authority; selectively reconcile the development changes and coordinate app, npm, bundle and tag versions. | None | A clean reviewed public commit reproduces the chosen feature baseline and version checks. No wholesale replacement of the independently validated public app. |
| I02 | Build a portable Python layout and noneditable parser wheel; include compiled utilities and data files; adapt parser configuration and readiness probes. | I01 | Copy to a different user/path and run all imports/parser work offline with no external interpreter or checkout. |
| I03 | Prepare the complete private MySQL runtime in CI; resolve runtime load paths, plugins, TLS/share resources and licenses before signing. | I01 | Server/client/dump, actual import and dump/restore work after relocation, with no system MySQL or post-install code rewriting. |
| I04 | Move all mutable preferences, caches, compatibility configuration and receipts out of app code. Preserve user-selected project locations. | I02, I03 | Read-only app works; launch, imports and quit leave its signature valid. |
| I05 | Add native lifetime owner, readiness checks, occupied-port handling and a bundled production WSGI server on loopback; retain project origins where possible. | I02, I04 | Double-click launch reaches the UI once; duplicate launch reuses the right instance; failures are visible without Terminal. |
| I06 | Coordinate every chooser/project service, inbox/import, export/transfer and database during Quit; preserve browser drafts and acknowledge shutdown. | I05 | Busy work defers Quit/update; all admitted requests drain and all owned databases close cleanly before native termination. |
| I07 | Package the complete app and a small Install and Open helper into a downloadable installer. Copy to a permanent user-owned location without downloading dependencies. | I03–I05 | Fresh standard user installs offline using the native action and launches without developer tools. |
| I08 | Integrate Sparkle as the sole desktop updater, signed appcast, compatibility filtering and React Update/Ready state. | I05, I06 | Real older app downloads a complete update quietly; it stays pending during work and installs only after safe quit. |
| I09 | Configure Developer ID signing, hardened runtime, notarization and Sparkle EdDSA signing; verify the complete nested-code closure. | I02–I07 | Browser-downloaded artifact passes Gatekeeper/notarization checks and still verifies after real use. |
| I10 | Replace the source-candidate publication path with a prebuilt desktop pipeline; publish versioned assets before advertising them in the stable feed. | I08, I09 | Tag produces the exact tested/notarized installer and update archive; failed jobs never advance the stable feed. |
| I11 | Provide crash/startup recovery and previous-version restoration within the same updater authority. Port database-generation restrictions. | I06, I08 | Failed new startup can recover without losing data; incompatible schema or MySQL formats never silently activate or downgrade. |
| I12 | Migrate existing v0.1.2 source users through one explicit desktop install, preserving projects/preferences and retiring old launch paths safely. | I06–I08, I11 | A real existing project reopens with the same source references, tags, queries and export history after old services stop. |
| I13 | Run the full clean-machine and multiple-client qualification below, then publish the installer. | I07–I12 | Recorded passing evidence for the actual final artifact, not just a source build or mocked update. |

Critical path: **I01 → I02/I03 → I04 → I05/I06 → I07/I08 → I09/I10 → I11/I12 → I13**.
Signing account preparation can start earlier, but final code is signed only
after relocation and bundle assembly. Recovery and compatibility design should
be specified before I08, even though their full tests depend on it.

### Why shutdown is a first release requirement

The development [project lifecycle](../../python/workspace_lifecycle.py) already
drains requests and refuses closure while imports are active. Extend that
contract to every service and work type, and make the native app own the registry
and final acknowledgement. The chooser currently has no equivalent coordinated
native Quit. Published Rieke-OS documents that Ctrl-C stops the chooser while
previously opened project services and databases may remain running.
[Published shutdown behavior](https://github.com/maxwellsdm1867/Rieke-OS/blob/f52312f06a651500ea3e121feaebd118201d0f7b/docs/RIEKE_OS_QUICK_START.md).

Sparkle may install when the native app terminates. Therefore it is insufficient
to say an update waits until the app closes while detached workers keep using
the old runtime. Reject or postpone native termination until all workers have
acknowledged closure. After a crash, reconcile recorded processes before allowing
replacement. App file locks alone do not automatically constrain Sparkle.
[Sparkle termination contract](https://sparkle-project.org/documentation/api-reference/Protocols/SPUUpdaterDelegate.html).

## GitHub release pipeline

Proposed stable pipeline in Rieke-OS:

```mermaid
flowchart LR
  A[Push reviewed version tag] --> B[Tests and version checks]
  B --> C[Build portable Python and MySQL]
  C --> D[Assemble native app and installer]
  D --> E[Sign and notarize]
  E --> F[Qualify exact final artifacts]
  F --> G[Publish versioned GitHub Release assets]
  G --> H[Advance signed stable appcast]
  H --> I[Clients download quietly]
  I --> J[Install after acknowledged app quit]
```

Keep the source installer as a developer fallback, clearly separate from the
desktop download. A branch push runs regression CI; a stable version tag declares
release intent. No user's installed app executes `git pull` or tracks arbitrary
branch commits.

Publish two product assets: the initial installer and a whole-app update archive
containing only the installed app. Build both from the same signed app. Generate
Sparkle signatures/appcast from the final archive bytes, after any packaging or
stapling changes. The existing RSA source manifest does not substitute for this
appcast.

Use GitHub Release URLs for versioned binaries. Proposed feed location is a
stable HTTPS URL in the same repository, initially a raw `updates/stable`
appcast branch, updated by CI after assets exist. Validate GitHub redirects,
cache behavior, feed signatures, compatibility filtering and roll-forward
ordering with an actual client. GitHub Pages is an alternative feed host, not a
prerequisite for a separate backend service.

The feed must never point at an unpublished/missing asset. Retrying publication
must recover the same artifact hashes, not overwrite a public release with
different bytes. Serialize promotions across versions so an older build finishing
late cannot replace the newer stable feed. No version is advertised before its
operating-system, architecture and database-compatibility checks pass. Schema
changes require a separate tested backup/migration/recovery path.

Configure GitHub environments explicitly where approvals are wanted; the field
in a workflow does not itself enable reviewers. Credentials needed are Developer
ID certificate/private key, notarization authentication, and the Sparkle update
signing key. These are separate from the current RSA source signing key.
Keep secrets in the selected secret system, expose them only to signing jobs,
and test restoration/rotation procedures. They were not created or changed by
this planning pass.

## Qualification before the public installer

| Scenario | Required result |
| --- | --- |
| Clean supported Mac, standard user, no development tools, network disabled after download | Install and first project creation/import work using only the artifact and OS facilities. A GitHub runner with development tools hidden from PATH is useful, but not sufficient proof. |
| Downloaded/quarantined app, alternate user, spaces/Unicode and moved application path | Native launch, Python imports and MySQL paths work; bundle signature remains valid. No quarantine removal workaround. |
| Real original H5 and existing source-user project | Import, browse trace, tag, save query, export, restart, and dump/restore retain original identities and source checksums. Validation data is supplied separately from the app. |
| Old-to-new release on two independent clients | Both discover/download the same published version; one busy client stays on its old version while the idle client updates. Their projects/settings remain independent. |
| Active import, inbox ingestion, transfer/export, open second project and unsaved browser draft | Safe quit is postponed or drafts are preserved; no worker is killed to make an update succeed. All owned services acknowledge shutdown before installation. |
| Offline server, invalid signature, wrong platform, truncated download, disk-full and permissions failure | Current app remains usable; incomplete updates are not activated. Necessary action is available in the release panel. |
| New version fails startup or uses incompatible project/MySQL formats | Recovery restores compatible app behavior without silently migrating or downgrading data. Previous-app retention alone does not count as tested recovery. |
| No MATLAB installation | All core installation, launch, data and update scenarios pass. Optional MATLAB GUI interoperability has its own validation claim. |

Test the exact notarized installer and archive that will be published. Preserve
machine/platform, versions, artifact hashes and pass/fail receipts. Neither the
current unit tests nor dummy-process manager tests establish these product gates.
Keep private recording data and credentials out of public release artifacts and
validation logs.

## Decisions and next executable experiment

Proposed defaults are Apple Silicon macOS first, a user-owned app location,
Sparkle as the sole desktop updater, hourly scheduled checks, and separate
project storage. Still decide the minimum macOS version, whether Intel/Windows
are required for the first release, who owns the signing identities, and the
publication approval policy before claiming support.

Start with **I01 and the I02/I03 relocation experiment**, not the installer UI.
Produce a prebuilt payload from a clean reviewed application baseline, move it
to a different path, use a minimal environment with dependency downloads disabled,
and exercise real parser imports plus MySQL import/dump/restore. Record every
runtime access outside the payload and user data directories. No source venv
copy, editable install, external executable, or destination-side code rewrite
may be necessary for that pass.

If this experiment fails, fix the packaging closure or evaluate the documented
PyInstaller fallback before building the native installer. If it passes, add the
read-only bundle configuration, lifetime owner and installer. This order turns
the largest unknown into a concrete pass/fail result before investing in the
download and launch interface.
