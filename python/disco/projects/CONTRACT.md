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
| Persist preferences | [project_preferences.py](project_preferences.py): `ProjectPreferences`, `PreferenceConflict`, validation and route registration own portable shortcuts, not scientific membership or device geometry. |
| Manage acquisitions | [datastores.py](datastores.py): `DataStores` separates freeze, archive and query eligibility. [datastore_deletion.py](datastore_deletion.py): `DataStoreDeletion` owns exact detachment and recoverable filesystem deletion. |
| Migrate legacy source | [migration.py](migration.py) performs explicit source inspection/snapshot/restore into a separate owned destination. It delegates to the retained portability/native owners; it does not adopt the source database. |

## Retention and storage

Retention resolves the existing source, verifies SHA-256 even for an already-managed
source, and otherwise copies into a fresh UUID directory under `raw-uploads` using
exclusive output creation. Verification failure removes only that new output and
directory before reraising; original source deletion remains the import caller's
policy. Repeating an external copy may allocate another directory. There is no SQL
commit, scientific validation, cancellation token or hard-death cleanup guarantee.
Opaque byte-copy success neither proves catalog commit nor authorizes deleting an
original. Display name uses a valid independent filename or the locator basename.

`managed_directory` refuses symlink traversal and root escape before creation.
Storage layout keeps project and code roots disjoint. Mutable database files remain
owned by the database provider, not exposed as ordinary browser-managed files.
Metadata-only inventory does not read trace samples. Existing file/byte limits and
log categories remain defined in the public module; no format or persisted path moves.

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
