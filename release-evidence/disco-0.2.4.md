Unsigned Apple silicon testing release. Not production-qualified.

DISCO 0.2.4 removes the installer-page detour and the app-wide requirement to close
other sessions before using a new version.

- Open **Disco.app** normally. First launch prepares the runtime automatically;
  subsequent launches reuse the selected version. No Install and Open page is needed.
- Existing sessions keep their original runtime while new sessions use the newer
  version. **DISCO → New session** opens a separate session with independent state.
- Different project folders can run independently. The same project folder remains
  exclusive, with a project-specific explanation if it is already open.
- **App Updates → Download update → Restart to update** prepares the new version
  before transferring the initiating session. If that session cannot close safely,
  the new version opens separately and the original session remains for recovery.
- Old runtime files stay available while their sessions or helpers need them. Cleanup
  removes unused versions while retaining the current and previous version for recovery.
- **Recover previous session** retains interrupted session records. Managed rollback
  changes the version for future sessions without replacing a running runtime.

During migration from an older flat installation, the new version can run while
the Applications entry still points to the older app. DISCO reports that limited
condition and refreshes the entry automatically once it is safe. Project folders,
recordings, tags and export formats stay separate from application files.

The attached qualification-summary.json, desktop-release.json and SHA256SUMS
identify the exact checked source and archives. Earlier development receipts and
synthetic prior/future-version fixtures do not qualify other published binaries.

This app is unsigned and unnotarized. Apple silicon only; Intel is unsupported.
macOS 14+ is the deployment target, not a claim of runtime validation on every OS
version. macOS may require **Privacy & Security → Open Anyway**. Signed updating,
universal macOS compatibility and broader unmeasured native workflows remain
outside this testing qualification.
