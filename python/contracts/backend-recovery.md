# Recovery ownership at current paths

Status: preparation only; no package move or new public facade. The executable
completion policy remains owned by `workspace_mutation_outcomes` and its separate
B migration. Detailed authority contracts remain in the existing
[ledger](../../docs/architecture/core-module-ledger.json) records
`backup-scheduling` and `recovery-store-authority`.

`workspace_backup_scheduler.BackupScheduler` owns coalescing, retry and shutdown
flush. `request`, `status`, `flush`, and `close` are the caller interface. Capture
runs under the supplied database lock; callers may already hold a reentrant lock.
A failed flush propagates and leaves dirty work visible. Close cannot report a
clean stop after failed flush. A capture only covers its initial sequence;
a request during capture remains pending. Close does not join while a caller
might hold the database lock. SQL commit success and backup success stay distinct.

`workspace_recovery_generation.RecoveryGenerationAuthority` owns native clock,
trigger/schema/instance continuity and exact typed key coverage. Missing coverage
requires a full capture, never an empty successful delta. `workspace_recovery_store`
owns independent durable mirror rows, watermark, pointer and checkpoints;
`workspace_state_snapshot` owns capture/restore composition and old snapshot
reading. Pointer publication, SQLite commit and checkpoint failure are separate
facts; retain referenced and unreadable-pointer evidence. No facade may claim a
cross-resource rollback. Restore preserves frozen membership, source identities,
revision roots and explicit dependency ordering.

Proposed locality: `disco/recovery/{backup_scheduler,recovery_generation,
recovery_store,state_snapshot}.py`, alongside B's completion owner. Keep their
individual module interfaces and keep shared state-generation authority outside
this package. Retaining current paths is a valid alternative until exact importer,
CLI, dynamic-loader, packaged-profile and catalog closure is reviewed after B.
A universal storage facade would erase authority distinctions without leverage.

The isolated public examples are in
[the recovery characterization](../tests/test_backend_recovery_public.py).
They replace worker startup with an inert test adapter and exercise public
scheduler calls, plus public snapshot functions. They establish neither worker
scheduling nor native capture, SQL durability, crash recovery or scientific
qualification. Existing full behavior tests remain in place and were not run as
part of this preparation.
