# GitHub unsigned desktop testing releases

The testing distribution is explicit in `desktop/distribution.json`. It uses the
public `maxwellsdm1867/Rieke-OS` repository and remains separate from Developer ID
signed production installation and updates.

Users download the complete Apple Silicon DMG from a release asset link, open
Rieke OS, and click **Install and Open**. The app copies its complete private
runtime to the current user's Applications folder. No Terminal, Docker, Python,
Node, or external MySQL setup is required. An unsigned download may require
macOS **Privacy & Security → Open Anyway** approval before it can run.
The app has a structurally verified local ad-hoc bundle seal, which needs no
certificate and provides no Apple developer identity. The installer retains quarantine attributes and does not bypass Gatekeeper.

In the app, **Release / Publish** displays a newer available version. Metadata
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

Each testing release includes `desktop-release.json`, the DMG, complete app ZIP,
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
