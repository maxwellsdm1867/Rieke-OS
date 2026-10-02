# Local DISCO Preview

The local preview uses version 0.1.6 and the established unsigned-testing policy.
It preserves the app/helper identifiers, workspace formats and database
compatibility. No tag, release, upload or notarization is needed for this flow.

Build only after the parent designates the final tested source commit and grants
the packaging slot. Use a clean isolated checkout, a separately copied runtime
whose dependency pins match that source, and a fresh renderer/application refresh:

```sh
python3 tools/desktop_build_runtime.py --refresh-application
python3 tools/desktop_runtime_manifest.py
cd desktop
CSC_IDENTITY_AUTO_DISCOVERY=false npm run pack:preview
```

Use the established graceful-fs preload from desktop-candidate.yml if packaging
needs the filesystem retry hook. `pack:preview` adds the boolean
`DiscoLocalPreview` and display label `DISCO Preview` to the outer Info.plist;
the internal CFBundleName stays Disco for native helper lookup. `pack`/`dist` remain unmarked. The
marker is included before the existing ad-hoc bundle seal. Verify the final
signature, runtime inventory, source commit and clean-source flag.

Assemble the portable preview folder using real directories owned by the user:

```text
DISCO Preview/
  Open DISCO Preview.command   # copy desktop/preview-launcher.command; executable
  home/
    Applications/Rieke OS.app # copy the complete newly packaged marked app
    .rieke-os/                # isolated author and appearance, created on use
  profile/                    # isolated Electron state and drafts
    backend/preferences/      # isolated project index and workspace selection
  tmp/                        # isolated temporary files
  projects/                   # consistent real-project copy supplied by E2E owner
```

Double-click **Open DISCO Preview.command**. It uses macOS built-ins and the
bundled executable, clears inherited environment overrides, and passes isolated
HOME, TMPDIR and --user-data-dir. No dev server, Node installation or source
Python is needed to launch. The terminal prints the full source SHA; the window
title shows DISCO Preview, version and short SHA; About shows the full SHA.

The early marked-preview guard rejects direct inner-app/Finder launches, moved
inner bundles, wrong profiles and redirected state before application-managed
branding/profile/single-instance/bootstrap writes. It does not claim to prevent
earlier Electron/macOS initialization effects. The preview never creates an
updater coordinator and blocks update/download/install/restore IPC. Retry
startup and orderly Quit remain available. Unmarked applications retain their
existing behavior.

Open only the consistent copied real project. Check its migration/mapping and
waveform/UI evidence, native datadir/socket ownership, then verify orderly quit
and unchanged installed 0.1.5/global preferences/original data. Unit checks of
the guard and launcher do not replace this final actual packaged smoke test.
The million-metadata scale fixture is separate backend evidence; a large native
recording duplication is not a release prerequisite.

The final E2E harness should call both exports from
`desktop/e2e/preview-assertions.cjs`: `verifyPackagedSource({bundle, source,
commit})` before launch and `assertTypedPublication({page, project, bundle})`
after opening the copied project. Store both return values in the smoke receipt.
The first checks every packaged Python module against clean final source and
manifest hashes. The second requires successful typed refresh/publication,
exercises the owned packaged field-registry/page endpoints, and matches their
typed token against the sealed published sidecar using bundled Python with
read-only SQLite. It does not create a sidecar or refresh the project itself.

macOS may require a security approval when opening a quarantined unsigned app
or downloaded launcher. Do not clear quarantine or bypass a prompt automatically;
coordinate with the parent if approval is required. Keep this folder in durable
local storage for Arthur, rather than under a temporary directory.
