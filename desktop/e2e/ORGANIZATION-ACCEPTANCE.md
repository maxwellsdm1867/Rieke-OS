# Organization acceptance: parent gate before execution

This is a narrow actual packaged UI/native correctness harness, not a benchmark,
installer test or release qualification. The implementation is initially
**syntax-checked only**. No fixture generation, parser/native imports, app launch,
native tests or runtime provisioning are authorized merely by this file existing.
Parent reviews exact source, scripts, fixture/schema, runtime, app bytes and quiet
window before each execution stage. Preserve failed/unrun evidence.

Start with root AGENTS and `docs/dev/releasing-rieke-os.md`,
`docs/dev/macos-compatibility.md` and existing ownership rules. Do not change
product runtime, source profile, guard catalog, security policy or cleanup logic
to make this harness pass. No paused legacy/Ovation/newH5port/nativeexport donor,
fixture, database or experiment may be used. No real projects, installed apps,
new accounts, publication, installation or downloads.

## Files and interfaces

- `tools/organization_e2e_fixture.py`: fresh donor-free 63-epoch H5 plus independent
  oracle, direct raw verification and real pinned-parser preflight. Scientific
  imports happen only during its explicit main invocation. It creates no project
  or database. Output directory is exclusive and retained even on failure.
- `organization-acceptance.e2e.cjs`: reviewed exact package gate, owned clone,
  rendered workflow and normal quit/reopen. Only native project-folder chooser
  return values and download destinations are scoped by the controller.
- `organization-owned-launcher.cjs`: owned spawn and public custom CDP transport,
  exact root-owned loopback listener proof, bounded main inspector adapter and
  socket-only disconnect. No Playwright process launcher or signal fallback.
- `organization-ownership.cjs`: bundled psutil read-only PID/creation time,
  actual child environment, process-tree/socket/port evidence. No signal/stop API.
- `tools/organization_e2e_readback.py`: independent read-only SQLite/MAT/H5 oracle;
  no application imports, server connection, scientific mutation or cached parser
  output injection.

All executable paths must be selected explicitly by parent. Use existing pinned
dependencies only; missing dependencies are blockers. The fixture parser imports
`h5py`, NumPy, SciPy, `bin2py` and matplotlib; availability in the approved Python
environment remains a preflight requirement. No stub import or runtime fallback.

After source review and authorization to generate this fresh fixture:

```sh
<approved-python-3.11.13> -B tools/organization_e2e_fixture.py \
  --output-dir <new-owned-absolute-fixture-directory> \
  --namespace <new-uuid> \
  --parser-source <owned-pinned-parser>/src/retinanalysis/utils/parse_data.py
```

This command is **not** a syntax check: it generates and parses H5 and must not
run before the parent gate. Pinned parser SHA-256 is
`0d63fa4df6e087cda60fd85305ea3c4a7d287949abab325b9f1dd2e5f12779d2` at commit
`5dc9018ff754e1a01f60d929ceaf4e7f40815e70`. A changed parser requires deliberate
schema/review rebinding; do not replace the hash to silence a failure. Oracle is
written before H5. Its values are `ordinal + sample_index / 256` and all identities
derive from its new namespace. The expected raw parser experiment UUID is the
animal UUID; native import must emit exactly `experiment_identity_restored` with
the oracle's distinct animal/root UUIDs. Unknown parser/native warnings fail.

Then parent binds final clean source and packaging checks to the exact final
candidate and prepares an external JSON execution gate:

```json
{
  "format": "disco-organization-execution-gate",
  "version": 1,
  "status": "passed",
  "parent_review": "approved",
  "quiet_window_reference": "concrete reviewed window reference",
  "valid_until": "actual future ISO UTC deadline",
  "candidate_commit": "final clean source commit",
  "candidate_bundle": "/canonical/owned/build/Disco.app",
  "bundle_inventory_sha256": "inventory(root).sha256",
  "packaged_parser_relative": "actual relative parser source path within bundle",
  "fixture_receipt_sha256": "SHA256 of fixture-receipt.json",
  "local_author": "select-existing-default",
  "extra_environment_keys": [],
  "harness_files": {
    "desktop/e2e/organization-acceptance.e2e.cjs": "SHA256",
    "desktop/e2e/organization-ownership.cjs": "SHA256",
    "desktop/e2e/organization-owned-launcher.cjs": "SHA256",
    "tools/organization_e2e_fixture.py": "SHA256",
    "tools/organization_e2e_readback.py": "SHA256",
    "desktop/e2e/ORGANIZATION-ACCEPTANCE.md": "SHA256"
  },
  "launcher_dependencies": {
    "lib/coreBundle.js": "549070af3acabb3efcc4f55bfe6210f9f7c2fcf633cf7eaa59bfe60719969171",
    "types/types.d.ts": "2806f6d7810fba0306066d500cd716a6d1128d90af2c3cf71723e3ea0a8904c4"
  },
  "evidence": {
    "mapped_checks": {"status":"passed","candidate_commit":"same commit","path":"/owned/receipt","sha256":"SHA256"},
    "source_closure": {"status":"passed","candidate_commit":"same commit","path":"/owned/receipt","sha256":"SHA256"},
    "assembled_closure": {"status":"passed","candidate_commit":"same commit","path":"/owned/receipt","sha256":"SHA256"},
    "native_audit": {"status":"passed","candidate_commit":"same commit","path":"/owned/receipt","sha256":"SHA256"},
    "relocated_imports": {"status":"passed","candidate_commit":"same commit","path":"/owned/receipt","sha256":"SHA256"}
  }
}
```

These fields are review bindings, not a mechanism to manufacture authorization or
replace reading each underlying receipt. Evidence must genuinely be for the
candidate, and parent reviews completeness before populating the gate. Gate is
not checked in or auto-generated as approved. The exported inert `inventory`
helper hashes regular bytes, file modes, directory entries and internal links;
parent may use it for the exact candidate snapshot in a read-only packaging
preflight. It does not execute bundled programs. Existing runtime-manifest,
application-profile, ASAR closure and whole-native audit remain prerequisites.

After parent approval of the concrete package/fixture gate:

```sh
node desktop/e2e/organization-acceptance.e2e.cjs \
  --gate /absolute/reviewed-gate.json \
  --candidate-bundle /canonical/owned/build/Disco.app \
  --fixture-directory /canonical/owned/new-fixture \
  --output /canonical/owned/new-evidence-directory
```

Output must be outside the checkout and candidate bundle; it must not exist.
The source checkout must be clean at the same commit as the candidate. The
assembled bundle must include the exact parser source and bundled Python at
`Contents/Resources/runtime/python/bin/python3.11`. Node Playwright is pinned to
1.63.0; expected Electron is 44.5.0. Pin changes need reviewed rebinding.

## Workflow and authority checks

One fresh temp HOME clones app bytes under `home/Applications/Disco.app`, avoiding
the product bootstrap installer path. Allowlisted environment provides only OS
runtime paths, isolated HOME/userData/preferences/TMPDIR, locale and unchanged OS
USER/LOGNAME. No inherited API credentials, project roots, development paths or
test fixture reuse variables. Sandbox and CSP stay enabled. The ownership helper
checks **actual child** HOME and effective preferences (explicit path or the
backend’s production HOME/.rieke-os fallback); a mismatch or inaccessible evidence
fails, not a presumed pass. No full environment/command dump is emitted.

Create one real native project; select existing default local Tag author via UI;
no profile-creation request. This writes only disposable local attribution and
isolated preferences, not an external account. Import via actual file input,
verify managed copy and the one expected restoration warning, visit pages and
actual split tree, select epochs 60/61 across the 60-row page boundary, inspect
trace and compare response values against the analytic oracle. Require a fresh
renderer request in each session and cursor sample 17 with actual chart readouts
for index, time and response; supplemental controller API reads cannot qualify
rendering. Both selected
rows are verified on their respective pages; neither is assumed simultaneously
present in the DOM. Branch/revision and ordered native page identities are
checked. No React state injection.

Tag cell B's two-epoch group through group-preview/group-save, not ordinary
highlighted-epoch tagging. Read back both exact UUIDs/actor and one negative
control. Export **all 63 protocol recordings** through actual Wheeler SQLite and
MAT UI. Inspector highlighting does not control export membership. Read-only
readback checks exact identities, parameters, every sample/pointer, SQLite
integrity/foreign keys, SQLite/MAT group tags and MAT chronological sequence.
Enumerate the entire MAT hierarchy, rejecting unknown/duplicate identities and
all stimuli; verify associations, timestamps, source hash, sample counts and Hz
units in both formats. Root label/properties are checked in the native overview
source metadata and MAT experiment metadata; SQLite has no root metadata field.

Normal quit, new-session cold reopen of same UUID/path, tag/export/trace readback,
and final normal quit are mandatory. UI selectors are source-bound but unrun;
missing controls or contract changes fail and require reviewed source adjustment,
not silent alternate actions or fallback mocking. Actual macOS chooser UI is
not qualified by the owned return-path substitution.

## Teardown and failures

Ten-minute cooperative work budget and eleven-minute controller cap. Deadline
stops new steps; bounded operations unwind into normal quit. A total deadline
exits only the controller and explicitly records cleanup blocked/fixture retained.
The harness provides no signal/kill/application.close fallback. Pinned Playwright
launcher startup-failure behavior must also be reviewed before execution. No new writes or retries after
uncertain import/tag/export outcomes. Ordinary quit losing its IPC channel is
accepted only if actual exit 0 and full owned process/resource checks succeed.

Ownership proof records PID plus creation time, executable, parent and session,
project path/UUID, actual environment containment and owned listeners/sockets.
The observer excludes itself, anchors the root creation time before environment
inspection, and skips ticks while a bounded probe is pending. Probe timeout does
not signal the helper. Ordinary quit is attempted even when evidence gathering
failed; launch without an available renderer uses the production app.quit path. Normal teardown additionally checks no root service
record, empty/removed userData/backend/desktop-services.json child registry, native owner clean_shutdown, matching project
path and removed native-runtime record. Lock files are not removed to force a
pass; directory contents remain for review. Inaccessible process/socket metadata,
deferred quit, lingering owned children, reused-port ambiguity or surviving socket
files fail cleanup and preserve the fixture. Parent handles any subsequent normal
recovery; never retry by launching another instance.

One existing native-runtime exception is explicit: MySQL uses a short socket
directory `/tmp/rieke-mysql-<uid>-<token>` on macOS. The observer verifies token
derivation from this exact project path and descriptor instance UUID, current UID,
0700 directory mode, runtime project identity and recorded PID/creation time. It
accepts only that socket and its canonical `/private/tmp` spelling, never a broad
temporary-directory prefix. It reads only owned service/runtime descriptors, not
native-credentials.json. Socket files must disappear on normal shutdown; the
empty private socket directory may remain as production normally leaves it.

Receipt is private: it includes synthetic project paths, process metadata and
screenshots. OS display name is not intentionally included in the structured
author receipt, but UI screenshots may display it. Share only sanitized summaries.
Each step starts unrun, moves through running to passed/failed; aggregate pass
requires every required step and zero observed renderer failures. On failure,
subsequent checks stay unrun and cleanup has a separate result. Full bundle/source
inventory must remain identical after both quits. Successful cleanup never turns
a failed workflow into passed.

## Permitted source-only validation before execution gate

```sh
node --check desktop/e2e/organization-acceptance.e2e.cjs
node --check desktop/e2e/organization-ownership.cjs
python3 -B - <<'PY'
import ast
from pathlib import Path
for name in ('tools/organization_e2e_fixture.py', 'tools/organization_e2e_readback.py'):
    ast.parse(Path(name).read_text(), filename=name)
PY
```

These checks do not establish parser compatibility, SQL population, GUI selectors,
native import compatibility, process ownership observability or orderly shutdown.
No broad existing packaged/scientific E2E entrypoint is required or authorized.

## Source review status

Independent review corrections are source-only. The actual export radio comes
from ProtocolExports and says “Wheeler SQL database”; the initial contrary
exportFormats-based observation was withdrawn. No runtime pass is implied.
Existing desktop dependency package versions and Electron executable presence
were observed in the owned stable-ports checkout, but integrity and usability
remain unqualified. The pinned Python runtime location remains unresolved.
Recheck gate expiry, clean commit, harness/oracle/receipt hashes before launch,
readback and final immutability. Long operation limits use remaining work time.

## Historical launcher finding and retained execution HOLD

The harness now fails closed at preflight. Read-only review of pinned Playwright
1.63.0 coreBundle.js (SHA256
`549070af3acabb3efcc4f55bfe6210f9f7c2fcf633cf7eaa59bfe60719969171`)
found Electron startup catch calling kill(), which sends SIGKILL to the process
group. This violates the authorized no-force-kill boundary. A parent gate cannot
silently waive it. Replace the launcher with an independently reviewed owned
spawn/attach architecture before removing the unconditional preflight HOLD. No
launch or failure-path experiment has been run. Other harness source checks do
not qualify this unresolved dependency behavior.

## Replacement launcher implementation (still blocked)

The reviewed replacement design is implemented in organization-owned-launcher.
It does not call Electron.launch or any browser launch API. Node24.13.0 spawns the
owned bundle with loopback inspector/CDP ports chosen by the application; both
exact URL host-and-port pairs must belong to the anchored root before either
attach. IPv4 and IPv6 listeners are not interchangeable; exit checks probe the
same observed addresses. A public
custom ConnectOverCDPTransport closes only its owned client socket, and
noDefaults avoids default context overrides. Target/window identity is mapped
through the native BrowserWindow and actual CDP target before selecting a page.

Main evaluation binds an explicit default context and invalidates it on context
replacement/destruction. Raw app lines and endpoint capabilities are not retained;
only line byte counts, endpoint hashes and ports are recorded. Unsupported or
ambiguous endpoints fail without connecting. No broad host discovery occurs. Observation errors stop new work admissions,
while ordinary quit remains independent of observation health. If normal quit
fails with an owned process retained, the controller hard cap and non-forwarding
signal handlers remain active; no child pipe closure is used to force cleanup.
Transport guards refuse app-close/crash/target-create and certificate-relaxation
commands. Ordinary quit may close the inspector socket to release debugger exit
waiting; socket disconnection alone never qualifies app shutdown.

The unconditional preflight HOLD remains pending exact independent source review
and parent runtime/package approval. The stopped historical snapshot is retained
externally. No helper/app/native execution was performed during implementation.
Pin both reviewed Playwright-core source hashes in the external gate, and bind
the new helper alongside all existing harness source files. Any changed runtime
or dependency pin needs deliberate review, never automatic hash replacement.
