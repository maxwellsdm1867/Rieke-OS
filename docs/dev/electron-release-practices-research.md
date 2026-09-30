# Electron release practices: primary-source comparison

Research date: 2026-09-30. This is a bounded source inspection, not an audit of release executions or a measurement of elapsed release time. External implementation links are pinned to the inspected commit.

## Observed: Beekeeper Studio

Inspected commit: `e6c2fd8acf487dc4f48451488fa529f7ec78eb9f`. Its [recent releases](https://github.com/beekeeper-studio/beekeeper-studio/releases/tag/v6.1.2) show continuing maintenance.

- The [update manager](https://github.com/beekeeper-studio/beekeeper-studio/blob/e6c2fd8acf487dc4f48451488fa529f7ec78eb9f/apps/studio/src/background/update_manager.ts) imports `electron-updater`, disables automatic downloading, forwards update events to windows, and invokes `downloadUpdate()` / `quitAndInstall()` in response to IPC. It skips development, Snap, and non-AppImage Linux installations. Beta preference selects the beta/latest channel.
- The [builder configuration](https://github.com/beekeeper-studio/beekeeper-studio/blob/e6c2fd8acf487dc4f48451488fa529f7ec78eb9f/apps/studio/electron-builder-config.js) publishes to GitHub; macOS enables hardened runtime and notarization. The [release workflow](https://github.com/beekeeper-studio/beekeeper-studio/blob/e6c2fd8acf487dc4f48451488fa529f7ec78eb9f/.github/workflows/studio-publish.yml) runs on `v*` tags, creates a draft release, builds across OS/architecture combinations, and uploads assets. A final job merges Intel and ARM macOS update metadata into `latest-mac.yml`.
- [Publishing to other channels](https://github.com/beekeeper-studio/beekeeper-studio/blob/e6c2fd8acf487dc4f48451488fa529f7ec78eb9f/.github/workflows/release-published.yml) follows the GitHub release-published event; its comments explicitly describe the manual publish click as the gate. The [PR smoke workflow](https://github.com/beekeeper-studio/beekeeper-studio/blob/e6c2fd8acf487dc4f48451488fa529f7ec78eb9f/.github/workflows/e2e-smoke-test.yml) separately builds and runs Electron smoke tests on Linux, macOS, and Windows. This does not demonstrate testing every published installer or an installed-version upgrade on every release.

## Observed: Logseq

Inspected commit: `a538a9b60c95490c35bf278903e60f3a9f03a330`. The [release feed](https://github.com/logseq/logseq/releases) includes release `2.0.1` and a maintained nightly stream; that is evidence of activity, not a release-duration target.

- Its [updater implementation](https://github.com/logseq/logseq/blob/a538a9b60c95490c35bf278903e60f3a9f03a330/src/electron/electron/updater.cljs) imports `electron-updater`, selects architecture-specific channels on macOS/Windows, disables automatic installation on quit, and exposes checking, progress, downloaded, and error states. Production automatic checking can enable downloading; explicit IPC requests installation.
- Its [builder configuration](https://github.com/logseq/logseq/blob/a538a9b60c95490c35bf278903e60f3a9f03a330/resources/electron-builder.yml) selects GitHub `logseq/logseq` as publisher and macOS DMG plus ZIP targets.
- The [desktop release workflow](https://github.com/logseq/logseq/blob/a538a9b60c95490c35bf278903e60f3a9f03a330/.github/workflows/build-desktop-release.yml) offers manually dispatched beta, nightly, and non-release builds. Draft and prerelease inputs default to true. It compiles shared assets, checks required runtime files and CLI help, builds platform artifacts, and then aggregates installers, update YAML, blockmaps, and checksums into a release. The release job depends on the platform build jobs. The commented schedule is not evidence of an active scheduled trigger.

## Official contracts and limits

[electron-builder's updater documentation](https://www.electron.build/v26/docs/features/auto-update/) describes generated update metadata and GitHub Releases support, requires signing for macOS auto-update, and requires a macOS ZIP for Squirrel.Mac / `latest-mac.yml`. It recommends testing updates with the installed application. [Electron's update guide](https://www.electronjs.org/docs/latest/tutorial/updates) also documents the free `update.electronjs.org` path for eligible public-GitHub applications; this is a distinct option, not the implementation established for these two examples.

[GitHub Desktop's quality process](https://github.com/desktop/desktop/blob/development/docs/process/quality-process.md) allows the whole or a subsection of its testing manifest plus exploratory testing for a build. Its [packaging documentation](https://github.com/desktop/desktop/blob/development/docs/technical/packaging.md) describes S3/Central distribution, so it should not be presented as another GitHub Releases updater example. None of these sources establishes a universal testing suite, elapsed-time SLA, or that successful packaging alone qualifies a release.

## Local comparison and recommendation

The local [distribution configuration](../../desktop/distribution.json) selects `unsigned-testing`. The [testing updater](../../desktop/testing-updater.cjs) implements custom GitHub release discovery and download handling, while the [signed updater](../../desktop/updater.cjs) imports `electron-updater` alongside additional local validation. The [candidate workflow](../../.github/workflows/desktop-candidate.yml) already makes extended native update/restore/rollback and fault-injection qualification opt-in. These observations concern the inspected source, not proof of a successful run.

Recommendation, not an observed industry requirement: keep ordinary release checks proportional to the changed behavior, qualify installation/update behavior when its code or packaging assumptions change, and publish the same frozen artifact that passed the selected checks. Standard updater libraries can reduce custom transport/install machinery, but changing the unsigned distribution model and its guarantees requires an explicit design decision. Avoid rebuilding an unchanged candidate merely to repeat evidence already attached to its exact bytes.
