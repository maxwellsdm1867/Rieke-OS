# Rieke OS release operations

Build and publish from the dedicated `maxwellsdm1867/Rieke-OS` repository. The
original EpicTreeGUI repository retains its MATLAB application and documentation;
it is not a release source or update channel for Rieke OS.

Rieke OS retains Python/SciPy MAT data export. Its reviewed application closure
excludes MATLAB GUI/plotting programs, launchers, installers, UGM interactions
and their tests. Web plotting/curation, generic UUID tag JSON and Recording
Selection Mask v1 JSON remain supported. Historical export files stay readable.

## Reviewed source and application-profile gate

Use a clean canonical checkout at the reviewed commit. Include the scope/profile,
frontend, backend, tests and documentation in that commit before assembling the
runtime. Do not build a release by copying the mixed development checkout wholesale.

`desktop/application-profile.json` explicitly lists the permitted Python modules
and excluded source paths. `tools/desktop_application_profile.py` checks the Git
inventory, local import closure and packaged application inventory. Both
`tools/build_release.py` and `tools/desktop_release.py baseline` invoke the
source-inventory guard. `tools/desktop_build_runtime.py` copies the reviewed
allowlist; manifest generation audits the application closure again.

Run the read-only checks from the canonical repository root:

```sh
python3 - <<'PY'
from pathlib import Path
import subprocess, sys
sys.path.insert(0, 'tools')
from desktop_application_profile import load_profile, validate_release_source, validate_source_closure
root = Path.cwd()
paths = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
print(validate_release_source(root, [p for p in paths if p]))
validate_source_closure(root, load_profile(root / 'desktop/application-profile.json'))
assert not subprocess.check_output(['git', 'status', '--porcelain']).strip(), 'Reviewed source must be clean'
versions = [__import__('json').loads((root / p).read_text())['version'] for p in
            ['rieke-release.json', 'workspace-app/package.json', 'desktop/package.json']]
assert len(set(versions)) == 1, 'Coordinated application versions must agree'
PY
```

This validates scope and cleanliness; it does not prove repository identity or
scientific correctness. Check the remote/reviewed commit separately. Never force
or reuse a published version tag or overwrite published assets. Any production
source change after qualification requires a new snapshot and artifact tests.

For the signed candidate pipeline, the baseline command additionally requires
an exact reviewed `v<version>` tag at HEAD:

```sh
python3 tools/desktop_release.py baseline --tag v0.1.3 \
  --repository maxwellsdm1867/Rieke-OS --output /tmp/rieke-desktop-baseline.json
```

Use the version being released, not the example blindly. For an unsigned testing
release, create the reviewed local `desktop-test-v<version>` tag at HEAD and run:

```sh
python3 tools/desktop_release.py baseline-testing --tag desktop-test-v0.1.3 \
  --repository maxwellsdm1867/Rieke-OS --output desktop/build/desktop-baseline.json
```

Both baselines verify the actual Git origin, clean source profile and exact tag
commit. The testing baseline also requires the explicit unsigned distribution.
Pushing `desktop-test-v*` invokes the unsigned candidate CI path; pushing `v*`
invokes the signed path. Unsigned builds must not claim signed qualification.

## Clean build of the complete desktop app

Build on Apple Silicon macOS with the required Node/npm, uv, Python build tools,
macOS toolchain and network access. These are build requirements; end users of
the complete app do not provision dependencies. Install exact lockfiles:

```sh
npm ci --prefix workspace-app
npm test --prefix workspace-app
npm run build --prefix workspace-app
npm ci --prefix desktop
npm test --prefix desktop
python3 tools/desktop_build_runtime.py --skip-frontend
python3 tools/desktop_runtime_manifest.py
node - <<'NODE'
const fs = require('node:fs'), path = require('node:path');
const graceful = require.resolve('graceful-fs', {paths: [path.resolve('desktop')]});
fs.writeFileSync('desktop/build/packaging-fs.cjs',
  `require(${JSON.stringify(graceful)}).gracefulify(require('node:fs'));\n`);
NODE
NODE_OPTIONS="--require \"$PWD/desktop/build/packaging-fs.cjs\"" \
  CSC_IDENTITY_AUTO_DISCOVERY=false npm run dist --prefix desktop
```

The pinned `@electron/osx-sign` walker opens runtime files concurrently before
applying its signing exclusions. CI therefore preloads the lockfile's
`graceful-fs` adapter into the packaging process before the walker loads. The
adapter queues file-open retries when macOS reports `EMFILE` or `ENFILE`.
`NODE_OPTIONS` is scoped to each packaging command; application launches and
qualification tests use their normal filesystem implementation. The temporary
adapter stays outside the app. The local commands above place the equivalent
adapter in the ignored build directory; CI uses its runner temporary directory.

To verify a workflow-only correction against an existing immutable release tag,
dispatch `desktop-candidate.yml` from the corrected workflow ref and supply the
published tag as the `tag` input. The baseline still checks out and verifies that
exact tagged source. The candidate workflow only uploads Actions artifacts; it
does not replace published release assets or move the tag.

For a reviewed test-only correction, `qualification_ref` selects a separate
native-update test checkout under the ignored build directory. It defaults to
the application tag. The workflow verifies that its application implementation
helpers and dependency lock match the tagged source, then connects the test
checkout to the frozen candidate. Qualification receipts identify the test
revision separately from the application's source commit. Updating a test
deadline or diagnostics does not require moving a published tag or repackaging
the released app. The update interface and native helper have separate bounded
CI steps so a stuck test cannot run indefinitely.
Once packaging and inventory succeed, CI retains the exact candidate even if a
later qualification test fails. Such Actions artifacts remain unqualified; the
run must pass its required checks before promotion. Keeping the failed run's
candidate and diagnostics supports investigation without rebuilding new bytes.

`desktop-published-qualification.yml` can verify a published unsigned testing
release directly on a fresh macOS runner. Supply its immutable `tag` and the
reviewed `qualification_ref`. It checks the archive digest and extraction bounds,
recomputes the descriptor, verifies the complete runtime and native database,
then exercises update/restore/rollback and startup-failure handling. It downloads
the existing release bytes and never rebuilds or publishes an application.

`desktop/distribution.json` must explicitly select the reviewed trust channel.
The testing build has an ad-hoc structural seal; it has no Developer ID identity
or notarization. Signed native code is finalized before runtime hashes and the
outer app signature. Never modify resources after the final seal or reseal a
failed candidate to hide unexplained changes.

Outputs include `desktop/dist/mac-arm64/Rieke OS.app`, the complete DMG and app
ZIP, blockmaps/update metadata as applicable. The runtime contains its reviewed
application profile, pinned interpreter/parser/native dependencies, license
inventory, source provenance and byte hashes. It excludes user projects, raw
recordings and credentials. The declared macOS minimum is a compatibility bound;
minimum-device and clean-machine tests need independent evidence.

## Test the exact artifact bytes

Routine candidate builds run source/unit checks, packaging and artifact identity,
packaged UI/project workflows and orderly quit, explicit Install and Open, and
update availability/download checks. Keep these as the default release loop.
Do not rebuild the same application to repeat an already-passing check after a
test-only or documentation change.

Native update/restore/rollback, startup fault injection and exhaustive extracted
installer audits are an explicit second tier: dispatch the candidate workflow
with `extended_qualification=true` when the affected code changes or a specific
failure requires it. For frozen published bytes, use the separate manual
`desktop-published-qualification.yml` workflow. These deeper runs are not an
automatic prerequisite for every unsigned testing build; document any remaining
qualification limits. Signed production promotion still requires its complete
evidence and is not implied by passing the routine loop.

Run the routine checks against the frozen packaged candidate, with scratch
HOME/user data/projects:

```sh
npm run test:e2e:updater --prefix desktop
npm run test:e2e --prefix desktop
npm run test:e2e:bootstrap --prefix desktop
npm run test:e2e:github-updates --prefix desktop
```

Run the affected deeper checks when requested or justified by a change:

```sh
node desktop/e2e/testing-upgrade.e2e.cjs
npm run test:e2e:startup-failure --prefix desktop
python3 tools/desktop_artifact_e2e.py \
  --installed 'desktop/dist/mac-arm64/Rieke OS.app' \
  --output docs/dev/desktop-artifact-e2e.json
```

Bootstrap/GitHub-testing suites apply to the explicit unsigned-testing policy.
The full scientific branch additionally needs a private original recording:

```sh
RIEKE_E2E_H5=/absolute/path/to/fixture.h5 npm run test:e2e --prefix desktop
RIEKE_E2E_H5=/absolute/path/to/fixture.h5 npm run test:e2e:github-updates --prefix desktop
python3 tools/desktop_scientific_e2e.py --recording /absolute/path/to/fixture.h5
python3 tools/desktop_artifact_e2e.py \
  --installed 'desktop/dist/mac-arm64/Rieke OS.app' \
  --recording /absolute/path/to/fixture.h5
```

The suites preserve sandbox/CSP and test actual packaged UI, owned-service
startup, draft recovery, active-writer deferral, native close/restart and resource
immutability. Scientific tests read exact H5 sample values, query membership,
annotations, JSON/SQLite/MAT data and restart/transfer state. Test transport and
native picker/Launch Services dispatch are explicitly bounded fixture seams.
Quarantine-copy testing preserves attributes and does not execute or clear a
quarantined installed fixture; startup is tested separately with a never-quarantined
fixture. These tests do not automate macOS Open Anyway approval.

Receipts must identify source commit, ASAR hash, runtime-manifest hash and exact
DMG/ZIP hashes. Archive failures before rerunning. A unit pass, source-install
receipt or earlier package receipt cannot certify new bytes. Do not include
private recordings, scientific project files, credentials or raw path-bearing
receipts in public release assets. Publish reviewed aggregate evidence only.

## Unsigned GitHub testing publication

After the exact-byte checks pass, create the descriptor and inventory:

```sh
python3 tools/desktop_test_release.py \
  --app 'desktop/dist/mac-arm64/Rieke OS.app' \
  --archive desktop/dist/Rieke-OS-0.1.3-arm64.zip \
  --output desktop/dist/desktop-release.json
python3 tools/desktop_release.py inventory --output desktop/dist/artifacts.json
```

Replace the example version consistently. Publish the reviewed commit as a
**prerelease**, labeled **unsigned testing**, under `desktop-test-v<version>`.
Attach the exact DMG, complete ZIP, `desktop-release.json`, checksums and sanitized
qualification evidence. Check descriptor hashes against both the inspected app
and archived bytes, then read back the published assets to verify the same bytes.
A source ZIP, draft release, Git push or candidate Actions artifact alone is not
a discoverable complete testing update. Do not mark the testing prerelease as a
signed production/stable release or overwrite an existing release's assets.

Users open the DMG app and choose **Install and Open** for
`~/Applications/Rieke OS.app`. The installer verifies/copies the complete bundle
and preserves quarantine; initial macOS approval may require manual Open Anyway.
Thereafter the app checks official GitHub metadata at startup/about hourly and
shows the available version quietly. Users choose **Download update**, then
**Restart to update**. An ordinary Quit never installs a testing update. Drafts,
active imports and owned scientific services can defer restart without killing
writers. Candidate validation runs trusted current-app code, not downloaded code.

## Signed production and source-manager releases

For signed production, commit/review `channel: signed` before building. Configure
Developer ID/notarization credentials and protected publishing reviewers; a
certificate alone does not change the application trust policy. The signed CI
job rejects unsigned policy and checks codesign, Gatekeeper and stapling.
`desktop-promote.yml` requires a successful canonical candidate run plus reviewed
`release-evidence` covering R01–R12; it promotes those exact bytes through the
protected environment. Signed old-to-new installation, recovery, scientific/JIT
behavior and independent clean-machine qualification remain separate gates.

The Python source installer/manager has a separate RSA trust and lifetime-lock
contract. It may retain its source-development release workflow, but it is not a
second updater inside Electron. A source checkout cannot install updates into
itself. Do not describe its 15-minute polling or next-launch activation as the
unsigned desktop's hourly metadata/manual download/restart behavior.

See [testing-channel trust](GITHUB_TESTING_RELEASE.md),
[application architecture](../RIEKE_OS_ARCHITECTURE.md), and
[desktop build details](../../desktop/README.md). Historical planning documents
and old validation ledgers describe their recorded source/configuration only;
they do not enlarge the current application scope or certify this release.
