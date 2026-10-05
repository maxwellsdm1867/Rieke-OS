# Current-state backup ownership

Status: mechanical package organization; no new facade. HTTP completion remains
owned by `disco.recovery`; backup modules do not import that package. Detailed authority contracts remain in the existing
[ledger](../../../docs/architecture/core-module-ledger.json) records
`backup-scheduling` and `recovery-store-authority`.

`disco.backup.backup_scheduler.BackupScheduler` owns coalescing, retry and shutdown
flush. `request`, `status`, `flush`, and `close` are the caller interface. Capture
runs under the supplied database lock; callers may already hold a reentrant lock.
A failed flush propagates and leaves dirty work visible. Close cannot report a
clean stop after failed flush. A capture only covers its initial sequence;
a request during capture remains pending. Close does not join while a caller
might hold the database lock. SQL commit success and backup success stay distinct.

`disco.backup.recovery_generation.RecoveryGenerationAuthority` owns native clock,
trigger/schema/instance continuity and exact typed key coverage. Missing coverage
requires a full capture, never an empty successful delta. `disco.backup.recovery_store`
owns independent durable mirror rows, watermark, pointer and checkpoints;
`workspace_state_snapshot` owns capture/restore composition and old snapshot
reading. Pointer publication, SQLite commit and checkpoint failure are separate
facts; retain referenced and unreadable-pointer evidence. No facade may claim a
cross-resource rollback. Restore preserves frozen membership, source identities,
revision roots and explicit dependency ordering.

The three substantive modules live under inert `disco.backup`, keeping stdlib
scheduler/snapshot imports independent of Flask completion registration. Public
usage remains explicit: `from disco.backup.backup_scheduler import BackupScheduler`
and `from workspace_state_snapshot import save`. The native generation module
keeps its existing shared state-generation dependency outside this package.
The named module interface preserves required constants/helpers and caller
knowledge; export count is not a design target. Keep-current remained a valid
alternative, but placing contracts beside these related owners improves discovery.
No universal storage facade or cross-resource transaction is introduced.

The snapshot composition stays at [`workspace_state_snapshot.py`](../../workspace_state_snapshot.py).
Its `main()` and `if __name__ == '__main__'` entry support the documented direct
command in [storage recovery](../../../docs/STORAGE_RECOVERY.md#recovery):

```sh
PYTHONPATH=python .rieke-runtime/venv/bin/python python/workspace_state_snapshot.py \
  --project-dir /path/to/project \
  --restore /path/to/project/backups/app-state/checkpoint-v2-YYYY-MM-DD.sqlite
```

The executable imports `recording_workspace` inside `main()` and retains its
original command arguments and working source-root assumptions. Preserving this
caller interface earns KEEP more than moving the file earns folder locality.
There is no forwarding shim. Only its imports of relocated owners change; the
CLI and guide are not rewritten or executed by this organization work.

The isolated public examples are in
[the recovery characterization](tests/test_backend_recovery_public.py).
They replace worker startup with an inert test adapter and exercise public
scheduler calls, plus public snapshot functions. They establish neither worker
scheduling nor native capture, SQL durability, crash recovery or scientific
qualification. Existing full behavior tests remain in place and were not run as
part of this preparation.
