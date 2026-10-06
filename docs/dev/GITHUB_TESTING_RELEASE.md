# GitHub unsigned desktop testing releases

The testing distribution is explicit in `desktop/distribution.json`. It uses the
public `maxwellsdm1867/Rieke-OS` repository and remains separate from Developer ID
signed production installation and updates.

## Current 0.1.8 manual testing download

[Disco 0.1.8 testing release](https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.1.8)
contains the existing `Disco-0.1.8-tree-counts-arm64.zip`, its checksums and the
[package record](local-package-0.1.8.json). Extract the ZIP, quit any running Disco
instance, then open `Disco.app` and use **Install and Open** if prompted. The ZIP
bundles Python and native MySQL. macOS may require **Privacy & Security → Open Anyway**.

This is a manual download from clean source `60f9567ced676bf6c1db181166f2693304592768`.
It has no `desktop-release.json` or automatic-update feed, so **App Updates** does
not offer this archive. The existing 0.1.5 release assets remain unchanged.
The runtime was checked on macOS 27.0.1 arm64; macOS 14 runtime behavior, Developer
ID signing/notarization and complete production release qualification remain open.
Intel is unsupported. See the [package handoff](navigation-package.md) for checks
and the exact attribution of prior evidence.

## Releases with an installer and update descriptor

The 0.1.5 testing release provides the complete Apple Silicon DMG. Users open
Disco, and click **Install and Open**. The app copies its complete private
runtime to the current user's Applications folder. No Terminal, Docker, Python,
Node, or external MySQL setup is required. An unsigned download may require
macOS **Privacy & Security → Open Anyway** approval before it can run.
The app has a structurally verified local ad-hoc bundle seal, which needs no
certificate and provides no Apple developer identity. The installer retains quarantine attributes and does not bypass Gatekeeper.

In the app, **App Updates** displays a newer available version. Metadata
checks run at startup and about once an hour; **Check for updates** also runs on
request. A notice never starts a download. Users choose **Download update**, then
**Restart to update** once the archive and app resources have been verified.
Active imports, unsaved drafts, and scientific services can defer the restart.
An ordinary Quit does not install a testing update.

Testing updates trust the official repository over HTTPS and compare the exact
archive, shell, runtime manifest, resource inventory, version, architecture,
macOS minimum, and database/workspace formats. These checks do not establish an
Apple Developer ID signature. The current trusted app validates the download;
downloaded Python or app code is not executed during validation. A dedicated
current-app helper waits for actual process exit, retains the prior bundle, and
installs only to the same user-owned app path. Scientific projects stay in their
selected folders.

An updater-enabled testing release includes `desktop-release.json`, the DMG, complete app ZIP,
checksums, and local qualification receipts. Its tag starts with
`desktop-test-v`, it is labeled **unsigned testing**, and it is a prerelease so it
does not replace the existing stable source release. Never overwrite published
assets under an existing version. A failed or interrupted download can be
retried; incompatible or changed candidates must remain uninstalled.

Production signing/notarization and a clean-machine test are separate open
qualification requirements. The testing release must not be presented as a
signed production release.

For a future signed production release, commit and review `channel: signed` in
`desktop/distribution.json` before building with signing credentials. The signed
CI job rejects the unsigned testing policy. Changing certificates alone does not
change the app’s installation/update trust policy.
