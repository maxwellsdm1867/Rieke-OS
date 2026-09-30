# Rieke OS installer source review

The later [Electron production specification](../design/electron-production-spec.md)
records the selected architecture. The Sparkle recommendation below was the
earlier alternative; the packaging, signing and service-lifetime constraints
remain relevant.

Reviewed 2026-09-29. Scope: Apple Silicon macOS, a local Python/Flask service,
React assets, private MySQL, and releases on GitHub. This is planning evidence;
no installer or signed update was built in this review.

## Recommended architecture

Use one immutable, Developer-ID-signed and notarized `Rieke OS.app`. A small
native AppKit launcher owns the app lifetime, starts the bundled Python services,
opens the local UI, and drains those services before quitting. Bundle the
prebuilt frontend, portable Python with installed packages/parser/utilities, and
the already-relocated MySQL dependency closure. Keep projects, SQL data,
configuration, logs, update caches and receipts outside the app bundle.

Use Sparkle as the **only desktop update authority**, replacing complete signed
app bundles. Adapt Release / Publish to display its state and open its controls.
Do not let the existing Python manager concurrently stage/activate desktop
code. Keep that manager only for explicitly separate source installations if
they remain supported.

This supersedes the current custom source-activation design for desktop builds;
it is a proposed change in update architecture, not functionality already shipped.

This recommendation follows Apple's sealed-bundle rules and Sparkle's existing
signed bundle-update machinery, rather than proving our bespoke source manager
into a new macOS installer/updater. The repository's existing project locks,
database-generation gates and staging tests remain useful specifications; they
are not automatically preserved by adopting Sparkle.

## Source facts and implications

### Signing and notarization

**Fact:** Apple requires Developer ID signatures, hardened runtime and secure
timestamps for notarization, with valid signatures on distributed executables.
Its notary service supplies a ticket that can be stapled to the distributed
software. Current submission uses `notarytool`, not the retired `altool`
workflow. [Apple notarization requirements](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

**Fact:** Modern bundle signatures seal essentially all content. Apple says to
treat signed bundles as read-only, sign nested code before the enclosing bundle,
and put scripts/resources and executable code in appropriate locations.
Absolute links to libraries outside the bundle can fail Gatekeeper.
[Apple TN2206](https://developer.apple.com/library/archive/technotes/tn2206/_index.html).

**Implication:** First-launch `pip` installation, Python bytecode written inside
the bundle, frontend builds, conda prefix rewriting, ad-hoc re-signing and
receipts inside `Contents` are incompatible with the intended sealed product.
Finish code transformations in CI, then sign. Route bytecode/cache writes outside
the bundle or disable bytecode writes. Never use a local ad-hoc signature as the
distribution identity. Entitlements must be proven by the packaged imports and
subprocesses; avoid broad exceptions by default.

**Repository gap:** The custom source archive extractor rejects symlinks and
limits archives to 512 MiB compressed / 2 GiB extracted. It cannot be reused
unchanged for framework-containing `.app` bundles. Sparkle explicitly requires
packaging to preserve symlinks and executable permissions.
[Sparkle bundle integration](https://sparkle-project.org/documentation/).

### Relocation and downloaded-app behavior

**Fact:** App Translocation runs a downloaded app at a randomized path. Apple
does not document all trigger conditions and provides no supported detection
or way to recover the original path. Resources outside the bundle, found by
walking from its path, can break. Apple recommends making the app work while
translocated. [Apple DTS App Translocation Notes](https://developer.apple.com/forums/thread/724969).

**Implication:** Resolve packaged resources from the actual bundle, never the
shell's working directory or a build-time checkout. Test launch after browser
download, from Downloads, after moving the app, and with spaces/non-ASCII paths.
A supported install flow should put the app in a writable permanent location;
do not rely on deleting quarantine attributes or reconstructing original paths.

### Python packaging choices

**Fact:** `python-build-standalone` publishes portable distributions, including
`aarch64-apple-darwin`, with `install_only` archives for running Python. Its
current release home is Astral's GitHub repository. [Project running guide](https://gregoryszorc.com/docs/python-build-standalone/main/running.html).

**Fact:** Build-time absolute paths remain in configuration such as sysconfig
data/Makefiles; uv fixes these for its installed distributions. Portability of
the interpreter does not promise portability of packages installed beside it.
[Project behavior quirks](https://github.com/astral-sh/python-build-standalone/blob/main/docs/quirks.rst).

**Fact:** Python's ordinary virtual environments are not considered movable or
copyable; script shebangs contain absolute interpreter paths.
[Python venv documentation](https://docs.python.org/3/library/venv.html).

**Inference:** First choice is a pinned standalone interpreter with packages
installed at build time into a controlled private layout and launched by its
explicit bundled executable. Build a wheel for the pinned parser rather than
ship an editable install. Precompile its C/C++ utilities. Verify NumPy, SciPy,
HDF5/h5py and every native extension against the supported macOS baseline and
architecture. This remains a proof obligation, not a claim that copying today's
`.venv` will work.

**Alternative fact:** PyInstaller collects Python dependencies and supports
macOS signing identity and entitlement configuration. Binary-path rewriting
invalidates signatures, so binaries must be re-signed afterward. Its `onefile`
mode extracts a payload to a temporary directory and uses launcher/child
processes. [PyInstaller feature notes](https://pyinstaller.org/en/stable/feature-notes.html).

**Inference:** PyInstaller `onedir` workers inside the native app are a viable
fallback if the standalone layout proves costly. It still needs explicit
collection of dynamic parser imports, data files and native utilities. Avoid
`onefile` for long-lived detached project workers whose files must survive the
bootstrap process. Neither approach automatically bundles MySQL or supplies
app lifecycle/update coordination.

### MySQL relocation before signing

**Fact:** Oracle's macOS installer installs under `/usr/local`, offers launchd
support and does not permit changing the installation location.
[MySQL macOS package documentation](https://dev.mysql.com/doc/refman/8.4/en/macos-installation-pkg.html).

**Fact:** MySQL supports explicit `--basedir`/`--datadir` for manual data-directory
initialization. [MySQL initialization documentation](https://dev.mysql.com/doc/refman/8.4/en/data-directory-initialization.html).

**Repository evidence:** `python/workspace_mysql_runtime.py` currently links
conda packages at the destination prefix, changes Mach-O bytes and restores
ad-hoc signatures. This is useful for source installs but cannot run inside a
sealed desktop bundle.

**Inference/proof obligation:** Prepare MySQL, `mysql`, `mysqldump`, plugins,
OpenSSL and the complete dynamic-library closure in CI. Inspect dependencies
and use supported relative Mach-O load paths. Verify strings/config files that
encode the conda prefix and paths to plugin/share resources. Only then apply
Developer ID signatures to final bytes. Run server/client/dump after moving the
finished app to different users and paths; a successful `--version` probe alone
does not prove TLS, authentication plugins, import or backup. Keep each project's
datadir, sockets, error logs and credentials outside the app. Do not install
Oracle's system daemon as the app-private runtime strategy.

### Sparkle automatic update behavior

**Fact:** Sparkle checks are opt-in by default and normally show a permission
request on second launch. Set `SUEnableAutomaticChecks=YES` in `Info.plist` to
enable checks without that request. Set `SUAutomaticallyUpdate=YES` to enable
automatic download/install; its default is `NO`. Scheduled checks default to
one day with a minimum one-hour interval. A downloaded update may prompt after
the impatient interval (default one week), or need authorization.
[Sparkle customization](https://sparkle-project.org/documentation/customization/).

**Fact:** `willInstallUpdateOnQuit` is called when an automatic update is ready
for silent installation on quit. Returning `YES` takes control and stalls future
update cycles; its handler can install/relaunch without UI. In either case
Sparkle still attempts installation when the app terminates.
[Sparkle updater delegate](https://sparkle-project.org/documentation/api-reference/Protocols/SPUUpdaterDelegate.html).

**Fact:** A custom `SPUUserDriver` must present UI; it cannot simply suppress all
UI. Silent behavior comes from automatic-update configuration. Package updates
always require authorization, and app updates may require it on managed Macs or
for standard users in `/Applications`.
[Sparkle custom UI contract](https://sparkle-project.org/documentation/custom-user-interfaces/).

**Inference:** Prefer a user-owned installation such as `~/Applications` when
unprompted subsequent updates are a requirement. A standard DMG drag/install or
small installer still involves normal OS/download gestures; do not advertise a
literally single click or bypass macOS first-open prompts. Bridge update state
to the existing badge; retain a proper UI for manual actions and authorization.
Test the impatient/critical-update paths before claiming no unsolicited update
dialogs. Install on orderly app quit so the next ordinary launch uses the new
version; do not update beneath active workers.

**Fact:** Sparkle supports signed update archives and an appcast, uses an
embedded EdDSA public key, and supports multiple archive formats including DMG
and ZIP. [Sparkle setup and publication guide](https://sparkle-project.org/documentation/).

**Inference:** Publish complete notarized app archives as GitHub Release assets
and a stable appcast URL containing their exact URLs/signatures. Code signing,
notarization and Sparkle's EdDSA signing are separate trust tasks. A Git push
does not itself publish a valid update. Remove the desktop RSA-manager channel
as an activation authority rather than maintain two independent trust/update
pipelines for the same application.

### Process and service ownership

**Fact:** Python recommends fully qualified executable paths for subprocess
reliability. `start_new_session`/`process_group` manage POSIX sessions/groups;
they do not define application-level lifetime or request drainage.
[Python subprocess documentation](https://docs.python.org/3/library/subprocess.html).

**Fact:** Flask says not to use its development server in production.
[Flask server guidance](https://flask.palletsprojects.com/en/stable/server/).

**Inference:** Use a bundled production WSGI server on loopback, disable reload
mode, establish readiness before opening the browser, handle duplicate launches
and occupied ports, and let AppKit remain alive while any project service is
active. Closing a browser tab must not be treated as shutdown acknowledgement.
Stop accepting new work, preserve drafts, drain workers and shut down owned
MySQL servers before the app terminates. If shutdown cannot complete safely,
cancel termination and defer installation.

## Bespoke manager fallback

Retaining the existing manager is feasible only with additional work: give it
its own bundled bootstrap interpreter that remains available independently of
the active version; stage prebuilt artifacts without `setup` compilation;
handle final signing/notarization, launcher replacement, manager/key upgrades,
failure recovery and macOS authorization. The existing `sys.executable` and
`#!/usr/bin/env python3` entry points do not establish that stable offline
bootstrap contract. This route must also preserve bundle sealing by replacing
complete signed payloads rather than modifying their code. It has more
unimplemented desktop-specific responsibilities than the proposed Sparkle
route. This comparison is engineering judgment based on the source contracts,
not a completed packaging experiment.

## Evidence required before release

1. A moved, sealed app runs offline on a clean supported Apple Silicon Mac with
   no Python, uv, Git, Node, Homebrew, compiler, Docker or MATLAB dependency.
2. All compiled imports, parser utilities and real MySQL import/edit/export,
   restart and dump/restore work from the packaged layout.
3. Gatekeeper/notarization verification succeeds after a genuine browser
   download; startup leaves bundle signatures valid.
4. A real published old-to-new Sparkle update downloads quietly, waits for all
   workers, installs on quit and preserves project data/preferences.
5. Offline checks, corrupt signatures, interrupted download, disk-full, busy
   workers, permission failure and incompatible database versions defer safely.
6. Recovery and schema compatibility are tested explicitly; replacing an app
   binary is not permission to migrate or downgrade project databases.
