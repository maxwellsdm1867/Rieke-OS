# Project storage and provisioning

These named modules organize existing owners; they do not introduce a combined
project manager or change the public capabilities. Start with the task below,
read the corresponding entry, then use its existing interface and examples.

| Task | Public entry and caller knowledge |
| --- | --- |
| Retain a recording | [recording_files.py](recording_files.py): `retain_recording(project_dir, source, expected_sha256)` returns a verified managed path; `recording_display_name` separates display identity from locator. |
| Manage project directories | [storage.py](storage.py): `managed_directory`, `initialize_layout`, log helpers and `ManagedStorage` own contained metadata-only inventory. Callers supply project and code roots explicitly. |
| Admit configured database | [project_database.py](project_database.py): `ensure_project_database(..., timeout=120)` validates project/catalog/provider identity before delegating to native or Docker ownership. `_run` remains used by portability; relocation does not make it private. |
| Inspect folders | [project_validation.py](project_validation.py) performs folder preflight; [folder_browser.py](folder_browser.py) lists bounded local directories and registers existing routes. Inspection is not database readiness. |
| Read project inventory | [project_inventory.py](project_inventory.py): `ProjectInventory.managed/current` reuse the retained discovery rules in a bounded read-only child. `pause/resume` control only those children; `ProjectInventoryUnavailable` is not an empty inventory. |
| Persist preferences | [project_preferences.py](project_preferences.py): `ProjectPreferences`, `PreferenceConflict`, validation and route registration own portable shortcuts, not scientific membership or device geometry. |
| Manage acquisitions | [datastores.py](datastores.py): `DataStores` separates freeze, archive and query eligibility. [datastore_deletion.py](datastore_deletion.py): `DataStoreDeletion` owns exact detachment and recoverable filesystem deletion. |
| Migrate legacy source | [migration.py](migration.py) performs explicit source inspection/snapshot/restore into a separate owned destination. It delegates to the retained portability/native owners; it does not adopt the source database. |

`recording_registry.library_directory` and `library_candidate` create/recover the
library only while the caller holds `recording_lock`. `library_identity`, `owner`
and `is_managed_source` distinguish library, legacy project and external paths.
`recording_location` / `relocated_library_recording` preserve identity across master
folder relocation. The receipt helpers in `recording_files` describe verified
storage separately from catalog completion; duplicate receipts verify bytes anew.

## Retention and storage

### Bounded project inventory

Project-list GETs and initial HTML inventories use one `ProjectInventory` per
Flask app. Reads are serialized, have a three-second deadline, and run only the
fixed packaged discovery entry with `-I -B`. The child receives the discovery
preference paths but no desktop capability or parser/database configuration.
It reuses `workspace_projects` identity, path, duplicate-copy, unmount and ordering
rules. Discovery imports no scientific writer; the startup registry's writer
import is deferred until its existing mutation function is actually called.

The fixed worker additionally refuses file mutation, process launch, sockets and
SQLite connections through a Python audit hook. This is defense in depth for
trusted packaged discovery code, not a general sandbox for arbitrary Python.
`process_factory` is a constructor test seam; remote callers cannot supply code,
commands, process IDs or a worker mode. Only this owner's exact `Popen` children
may be killed on timeout or pause. A child that cannot exit is retained in the
owner and prevents further spawning; no database process is cancelled.

The parent drains stdout and diagnostic stderr concurrently with bounded retained
buffers. A failed read carries a reason, elapsed milliseconds, last observed
operation/scope, an optional 16-hex SHA-256 prefix of the exact observed path,
and whether its owned worker was reaped or is still stopping. The API and local
warning log expose these fields, never raw paths, child stderr or credentials.
The path digest is correlation evidence, not project identity or an access grant.
Discovery-only audit events identify root validation, directory listing,
candidate inspection and registry/saved-project reads. They grant no write or
database authority. A timeout says discovery did not finish; it does not diagnose
macOS permissions or prove that an update caused the stall. The three-second
deadline and suppression of retries behind an unexited worker remain in force.

Explicit Quit pauses these readers before waiting for request completion. It
continues to wait for scientific writers, jobs, database operations and child
service receipts. Read cancellation grants none of those acknowledgements.
Ordinary resume can admit a fresh inventory after a cancelled read.

An unavailable inventory returns HTTP 503, and an initial HTML failure renders
an explicitly unavailable inventory with its page context. The chooser offers a
retry and never equates the failure with zero projects. The renderer cannot use
that fallback identity to activate project data. Launcher construction defers
root discovery/validation to the read worker; existing write owners still validate
destinations before mutation. Folder inspection and mutations are not generalized
into this worker.

Executable cases: `python/tests/test_workspace_project_inventory.py` uses actual
owned child processes, stalled reads, unchanged file snapshots and native-copy
identities; it proves cancellation does not override a scientific writer. The
mounted `workspace-app/src/projectInventoryRecovery.test.js` exercises the actual
App retry flow and verifies no scientific activation from an unavailable shell.

Retention resolves the existing source and verifies SHA-256 even for an already-managed
source. Real projects retain new bytes under the sibling `recordings/<sha256>/`
library, independent of the first importing project. Copy, verification and fsync
precede atomic directory publication; registry publication follows under the shared
lock. A complete checksum directory can be recovered after failed registry publication.
Failure removes only the unpublished staging copy. Legacy references stay in place;
external originals are never deleted by retention. See the [managed recording contract](../../../docs/architecture/linked-sqlite-managed-recordings.md#managed-recording-contract).
Legacy callers without project manifests keep UUID-directory contained-copy behavior under `raw-uploads`. There is no SQL
commit, scientific validation, cancellation token or hard-death cleanup guarantee.
Opaque byte-copy success neither proves catalog commit nor authorizes deleting an
original. Display name uses a valid independent filename or the locator basename.

`managed_directory` refuses symlink traversal and root escape before creation.
Storage layout keeps project and code roots disjoint. Mutable database files remain
owned by the database provider, not exposed as ordinary browser-managed files.
Metadata-only inventory does not read trace samples. Existing file/byte limits and
log categories remain defined in the public module; the project layout format and existing paths stay in place. The sibling library has a separate identity marker and version-2 recording registry.

## Database, acquisition and migration authority

Database admission distinguishes project UUID, optional instance UUID, provider,
container/runtime identity, exact storage location and process proof. Pending restore,
wrong identity, orphaned nonempty storage or foreign/unavailable provider refuses
attachment while preserving files. Docker admission retains the pinned image,
localhost binding and matching labels/mount; native delegation retains strict
process/server ownership. Timeout is bounded readiness, not a transaction rollback.
No new generic repository or in-memory adapter claims native provider equivalence.

DataStores freeze prevents registration changes; archive hides an inventory entry;
query exclusion affects future queries. None deletes source bytes or rewrites frozen
scientific membership. Deletion keeps its durable preparation/recovery and exact
source/record checks. Native transactions, audit events, filesystem cleanup and
partial success retain their existing order and separate owners. Refer to existing
[datastore tests](../../tests/test_workspace_datastores.py) and
[deletion tests](../../tests/test_workspace_datastore_deletion.py); these native
fixtures were not executed for source organization.

Migration preserves source read-only session inspection, provider/trigger checks,
logical dump verification and independent destination restoration. Portability jobs
may publish a verified destination before outer cleanup fails; failure is not proof
that nothing was created. Registry warnings do not undo verified transfer success.
Project UUID survives restoration, while runtime instance and credentials are fresh.
Renderer cancellation stops monitoring rather than the server operation. SQL/file
rebase uses its destination-bound recovery journal; historical events and immutable
export provenance do not get rewritten as current locators.

## Explicit retained paths

| Retained owner | Source-bound reason |
| --- | --- |
| [workspace_projects.py](../../workspace_projects.py) | `create_project` and `create_project_at` code-root defaults use `Path(__file__).resolve().parents[1]`; moving without revising this selects a different application root. Keep discovery/creation distinct from storage. |
| [workspace_project_servers.py](../../workspace_project_servers.py) | Child commands select sibling `workspace_api.py` and `workspace_updates.py` with `Path(__file__).with_name(...)`; this is executable identity, not a cosmetic import. |
| [workspace_project_unmount.py](../../workspace_project_unmount.py) | Exact owned command proof derives sibling `workspace_desktop.py`; a relocated lookup changes the proof. |
| [workspace_portability.py](../../workspace_portability.py) | Stable `__main__` CLI plus two physical code-root anchors feed layout/relocation. Keep its explicit prepare/restore/move ownership and CLI path. |
| [workspace_native_mysql.py](../../workspace_native_mysql.py) | Physical ROOT and native binary/process ownership stay with the stable runtime entry. |

No moved module contains a physical `__file__`, path-based sibling CLI or `__main__`
entry. Native process launch remains lazy where it was lazy. Python source and
provenance source lists use the new canonical imports/paths; historical receipts
retain their historical context. Retained owners can have their import paths updated
without moving their physical entry or changing code-root calculation.

## Why this factoring

Deleting retention/storage spreads checksum, containment and cleanup knowledge into
import/inventory/transfer callers. Deleting database admission spreads provider proof
into open/import/lifecycle callers. They earn their existing interfaces. Combining
these owners would force byte-copy callers to learn native runtime/transaction rules.
The packages improve locality and progressive discovery, not behavioral depth.
All existing capabilities remain; export count is not a measure of interface clarity.

Pure identity/validation is in-process. Temporary filesystem byte-copy tests provide
local-substitutable evidence. Native database, Docker, OS process and scientific H5
behavior are true external dependencies for this source-only lane and are not
qualified by those stand-ins. Owned HTTP transfer jobs remain remote but owned;
their current route/worker protocol is preserved, not replaced by a speculative port.

## Public examples and checks

Run only this bounded stdlib lane from the repository root:

```sh
python3 -I -B python/disco/projects/tests/test_public_examples.py
```

The examples import real named modules with a fail-fast `recording_workspace`
stand-in exposing only unused JSON writing, and block scientific/native imports.
They exercise verified opaque-byte retention, reuse revalidation, failed-copy cleanup,
symlink refusal, display-name independence and early database-admission refusal.
They do not create recording/export fixtures or validate real provider readiness.
Existing root tests retain their names and imports against the same public entries;
scientific/native/HTTP tests remain deferred. Package/profile/import closure is a
separate integration gate. No benchmark or release qualification is claimed.

## Project shell and deferred scientific services

`project_shell.create_project_shell` serves identity, navigation, appearance,
project management and frontend assets before SQL or scientific services start.
The renderer requests `/api/project/activate` after painting the restored shell.
Concurrent requests share initialization. Failure leaves the shell and explicit
retry available; data-dependent endpoints refuse access until ready.

The desktop entry retains session locks, identity and authenticated admission.
Its deferred builder retains storage/recovery checks and native ownership before
scientific use. A private session receipt changes durably from `unused` to
`database_attempted` before native effects. Only an exact unused session can exit
without a database shutdown receipt. All attempted database use retains the
existing clean-close/recovery obligations, including partial-build cleanup.
Unmount stays owned by `workspace_project_unmount` and `DesktopBoundary`.

The scientific application still performs its existing project-wide catalog
refresh when activated; this change does not claim bounded first-query cost.
Selected-cell QC preparation remains explicit; export storage is prepared during
validated export. The shell tests use temporary files and injected scientific
construction. Actual restoration, unmount and database shutdown require the
separate packaged Electron tests and timings.

## Protocol linked recording sizes

`DataStores.recording_sizes(source_sha256s)` projects filesystem availability
and size for admitted registered source identities, without enumerating epochs,
protocol memberships or exports. Missing, unreadable and changed-size files keep
the inventory's existing status meaning. The HTTP protocol owner derives source
identities from current effective membership and holds registration locks; no
caller-supplied path is accepted. Metadata/H5 contents are not read, copied or
modified. The full data-store inventory contract remains unchanged.

## Last-good overview presentation

`presentation_cache.save_overview` writes an optional latest overview after a
successful canonical read. `load_overview` serves only explicitly allowed display
fields through `/api/project/presentation`, including before scientific activation.
The envelope always says `presentation_only`; it supplies no query revision, lease,
mutation capability or readiness proof. A same-path database restore may leave old
display bytes, so canonical initialization and overview validation remain mandatory
on every restart before enabling any data-dependent action.

The disposable SQLite cache lives in desktop user state, outside project scientific
files, keyed by canonical project path plus validated manifest UUID. Reads create
nothing. Each project retains one snapshot capped at 4 MiB, with a 12 MiB file cap,
25 ms lock timeout, version and checksum checks. Corruption, lock contention, write
failure and unsupported project manifests are misses and never block normal work.
No source hashing, H5 reads or scientific-database opens are permitted here. The
cache is not copied into project exports, and deleting it loses no scientific state.
The focused cache/shell/API tests exercise process restart and failure fallback;
those tests do not qualify installed-app startup latency.
