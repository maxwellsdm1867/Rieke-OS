Unsigned Apple silicon testing release. Not production-qualified.

DISCO 0.2.3 keeps session conflicts local to the affected project folder.

- Open independent DISCO sessions for different project folders with **DISCO → New session** (Command-Shift-N). Each session has separate application state and backend ownership.
- An already-open project folder is refused with actionable guidance; other project folders remain available. Do not open the same folder in two versions simultaneously.
- If an earlier session cannot recover, use **Open another session** to open or create another project. The old recovery records remain preserved.
- **DISCO → Recover previous session** reopens a preserved session separately. Clean session restarts retain their own saved workspace.
- Ordinary Quit closes only that session. Updating or replacing the shared app still requires its running sessions to close.

Use **App Updates → Download update → Restart to update** in DISCO. Project folders remain separate from the app; reinstalling is not a way to close a running project service.

Release qualification and archive hashes are recorded in the attached qualification-summary.json, desktop-release.json and SHA256SUMS. Earlier development/native receipts remain attributed to their measured sources; they do not qualify this package by themselves.

This app is unsigned and unnotarized. Apple silicon only; Intel is unsupported. macOS 14+ is the deployment target, not a claim of runtime validation on every OS version. Scientific data, recordings, tags and export formats are unchanged by this release.
