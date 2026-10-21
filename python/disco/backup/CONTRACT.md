# Current-state backup ownership

Status: mechanical package organization; no new facade. HTTP completion remains
owned by `disco.recovery`; backup modules do not import that package. Detailed authority contracts remain in the existing
[ledger](../../../docs/architecture/core-module-ledger.json) records
`backup-scheduling` and `recovery-store-authority`.

`disco.backup.backup_scheduler.BackupScheduler` runs the backup synchronously at
each commit point and on shutdown flush; it has no timer, delay, quiet period or
worker thread. `request`, `status`, `flush`, and `close` are the caller interface.
Capture runs under the supplied database lock; callers may already hold a
reentrant lock. `request` follows an already-committed edit, so its failure is
recorded (status `degraded`, still pending) and logged rather than raised; the
next request or flush retries. A failed flush propagates and leaves dirty work
visible. Close cannot report a clean stop after failed flush. A capture only
covers its initial sequence; a request during capture remains pending. SQL
commit success and backup success stay distinct.

Synchronous backup is affordable because the mirror is incremental: with a
continuous change feed, `workspace_state_snapshot.recovery_delta` writes only
the after-images and deletions of rows changed since the mirror's watermark,
for every mirrored table including Workbench, binding, revision and preset
tables. Two tables mirror a selection rather than all project rows and are
reselected only when one of their inputs changed: current preset versions, and
the explorer-revision dependency closure (recomputed from identity-only SQL
reads and diffed against the mirrored identities). Sources changing, a broken
feed or authority, or an unexpected key shape fall back to the full capture.
The mirror format is unchanged, so existing mirrors, checkpoints and v1
snapshots remain readable. The exact pre-membership `GROUP_TABLES` header used
by 0.1.20 is accepted alongside the older known table sets; unknown sets,
checksums, seals and identity mismatches remain failures. Adding the
`protocol_membership` schema requires a full capture before deltas resume.
That capture updates the current mirror in place; it does not keep an alternate
old-version pointer. Existing immutable daily checkpoints remain unchanged,
but are subject to their ordinary retention. Older apps cannot read a new
18-table mirror: keep an independently verified pre-upgrade recovery copy before
live qualification and do not treat reopening an older app as a supported
rollback after the new schema is captured. Offline restore remains explicit.

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
