# GitHub desktop installation and update patterns

Reviewed 2026-09-29 against project source and official framework documentation.
Pinned commits make the inspected implementations reproducible; live feeds and
release URLs can change. These are comparative findings, not implementations
already added to Rieke OS.

## The reusable pattern

GitHub serves distinct jobs: source control, CI execution, downloadable Release
assets, and optionally a static update feed. The installed **client updater**
reads metadata, chooses a compatible version, verifies its artifact and controls
installation. Users do not clone/pull the source repository. A successful CI
build artifact is not automatically a public, trusted update.

## Two concrete native macOS examples

### Rectangle uses Sparkle and GitHub Releases

At commit `c0ae7f87abe66f66b2857fbd4ad19ef802a9b43a`, Rectangle embeds
`https://rectangleapp.com/downloads/updates.xml` and a Sparkle EdDSA public key in
its [Info.plist](https://github.com/rxhanson/Rectangle/blob/c0ae7f87abe66f66b2857fbd4ad19ef802a9b43a/Rectangle/Info.plist).
Its native [AppDelegate](https://github.com/rxhanson/Rectangle/blob/c0ae7f87abe66f66b2857fbd4ad19ef802a9b43a/Rectangle/AppDelegate.swift)
constructs `SPUStandardUpdaterController`, exposes manual checks and supports
gentle scheduled reminders.

The [live appcast](https://rectangleapp.com/downloads/updates.xml) contains
version/build metadata, exact file lengths and EdDSA signatures. Its current
full update points to the [v2.0.2 GitHub DMG](https://github.com/rxhanson/Rectangle/releases/tag/v2.0.2),
with optional signed deltas also hosted as Release assets. The feed host and
artifact host are independent; Sparkle does not infer metadata from a Git tag.

Its visible [build workflow](https://github.com/rxhanson/Rectangle/blob/c0ae7f87abe66f66b2857fbd4ad19ef802a9b43a/.github/workflows/build.yml)
archives the app, signs ad-hoc, creates a DMG and uploads an Actions artifact.
It does **not** show the production Developer ID/notarization/feed-publication
pipeline. Copying that workflow alone would not reproduce its public updater.

**Applicable lesson:** Adopt the feed-to-signed-complete-app pattern and native
update-state ownership. The existing React release panel can remain the visible
interface. Do not copy Rectangle's user-notification policy as Rieke OS's policy.

### MonitorControl uses signed GitHub downloads and explicit channels

At commit `84ac2d72bfb53b653536e484946f6ed027e4229c`, MonitorControl embeds
`https://monitorcontrol.app/appcast2.xml` and an EdDSA public key in its
[Info.plist](https://github.com/MonitorControl/MonitorControl/blob/84ac2d72bfb53b653536e484946f6ed027e4229c/MonitorControl/Info.plist).
Its [AppDelegate](https://github.com/MonitorControl/MonitorControl/blob/84ac2d72bfb53b653536e484946f6ed027e4229c/MonitorControl/Support/AppDelegate.swift)
creates and starts a Sparkle controller. Its
[UpdaterDelegate](https://github.com/MonitorControl/MonitorControl/blob/84ac2d72bfb53b653536e484946f6ed027e4229c/MonitorControl/Support/UpdaterDelegate.swift)
selects the beta channel only when the corresponding preference is enabled.

The [live feed](https://monitorcontrol.app/appcast2.xml) encloses the exact
version-specific GitHub URL for the [v4.4.0 DMG](https://github.com/MonitorControl/MonitorControl/releases/tag/v4.4.0),
its EdDSA signature and length (20,391,423 bytes, matching the Release asset
observed during review). No production release workflow was present in the
inspected repository tree; publication mechanics beyond these artifacts are
not established by this inspection.

**Applicable lesson:** Separate stable and beta selection explicitly and keep
artifact URLs bound to specific releases. Neither example implies their
application code, dependency choices or release scripts should be copied wholesale.

## Cross-platform frameworks

| Approach | GitHub role | Installed client mechanism | Fit for this app |
| --- | --- | --- | --- |
| Native shell + Sparkle | Releases hold signed app archives; a static host supplies appcast XML | Sparkle verifies and replaces the complete app | Evaluated native macOS alternative |
| Tauri updater | Releases hold updater archives/signatures and optionally `latest.json` | Tauri plugin checks, downloads and installs | Credible if a cross-platform webview shell becomes a requirement |
| Electron + electron-updater | GitHub provider discovers Release metadata/artifacts | electron-updater manages download/install state | Credible if Electron is otherwise wanted; it adds its own runtime |
| Electron Forge + update-electron-app | Releases hold binaries; `update.electronjs.org` supplies a feed | Electron/Squirrel consumes that service | Demonstrates GitHub-based delivery with an additional service |

Tauri's [official updater guide](https://v2.tauri.app/plugin/updater/) documents
mandatory artifact signatures, a bundled public key and the static endpoint
`https://github.com/user/repo/releases/latest/download/latest.json`. Each
platform entry requires its artifact URL and signature. The application calls
the updater API; the existence of metadata does not define check scheduling or
safe worker shutdown. [Tauri Action](https://github.com/tauri-apps/tauri-action)
builds/publishes assets and generates that JSON. It explicitly warns that
latest-download artifact URLs can fail when other releases lack updater bundles.

Tauri supports [external binaries](https://v2.tauri.app/develop/sidecar/), with
architecture-specific filenames. **Inference:** Python and MySQL could be
bundled sidecars while retaining React, but their portable dependency closure,
signing and orderly lifetime still require engineering. Switching to Tauri is
not necessary to solve GitHub hosting.

[electron-builder's official update guide](https://www.electron.build/docs/features/auto-update/)
supports a GitHub Releases provider, generates internal `app-update.yml`, and
emits availability/progress/downloaded events suitable for custom UI. Automatic
download is configurable; the notification convenience API is unnecessary for
a quiet badge. macOS uses Squirrel.Mac's native staged update/relaunch behavior;
Windows/Linux installer details differ. It also requires signed macOS apps and
the corresponding ZIP update target. **Inference:** Electron could retain the
React UI and packaged Python workers, but it is a product-shell decision rather
than a prerequisite for automatic updates.

As a real third example, Electron Fiddle at
`a63225b53664fd750828c29aa35de4b4d0eb0b28`
[publishes through Forge's GitHub publisher](https://github.com/electron/fiddle/blob/a63225b53664fd750828c29aa35de4b4d0eb0b28/forge.config.ts)
and [initializes update-electron-app](https://github.com/electron/fiddle/blob/a63225b53664fd750828c29aa35de4b4d0eb0b28/src/main/update.ts)
with `electron/fiddle`, a one-hour interval and ten-second startup delay.
[Electron's tutorial](https://www.electronjs.org/docs/latest/tutorial/updates)
explains the default `update.electronjs.org` service and restart dialog. This
is neither GitHub-only hosting nor the requested quiet UX by default.

## Proposed GitHub deployment for Rieke OS

Use GitHub Releases for immutable, version-specific DMG/ZIP assets. Publish the
Sparkle appcast at a stable GitHub Pages URL, or a protected branch's raw URL.
[GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
is a static hosting service, so a separate update server is unnecessary for this
basic channel. The raw-branch option is an engineering choice to validate, not
a guarantee of freshness or response headers. Use the raw file rather than a
GitHub HTML file view.

GitHub [documents latest-release asset links](https://docs.github.com/en/repositories/releasing-projects-on-github/linking-to-releases),
but such a redirect is not an update manifest. Every promoted release must have
the correct metadata asset if using that pattern. Prefer version-specific
artifact URLs within a stable feed. Test redirects, content type, cache headers,
stale-feed responses, offline behavior and publication races from the installed
client; no promise of instant delivery follows from hosting on GitHub.

The release sequence should be: build/relocate dependencies; sign and notarize;
package preserving symlinks; generate signatures/feed; upload all assets; verify
public URLs and signatures; publish the stable feed last. Sparkle's
[publication guide](https://sparkle-project.org/documentation/publishing/)
specifies complete app archives, symlink preservation and signature metadata.

**Selected direction:** Following the user's preference, retain React and
Python/MySQL, add an Electron lifetime owner, and use electron-builder and
electron-updater with the direct GitHub provider. The
[production specification](../design/electron-production-spec.md) defines that
contract. This replaces the bespoke source updater for desktop activation; no
Sparkle updater runs alongside it. The largest remaining gaps are the sealed
portable runtime and worker shutdown contract, not GitHub hosting.
