# Current-state backup owners

Start with [the contract](CONTRACT.md). Import the substantive module that owns
the operation; the package initializer is inert. Scheduling, native capture,
local mirror storage and snapshot composition retain separate authorities.
Snapshot composition retains its documented executable path at
[`workspace_state_snapshot.py`](../../workspace_state_snapshot.py).
HTTP mutation completion remains [disco.recovery](../recovery/AGENTS.md).

The [isolated examples](tests/test_backend_recovery_public.py) exercise
public scheduler and snapshot calls without a worker, application or database.
Do not infer native capture/durability qualification from their result.
