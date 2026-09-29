# Import progress and recovery

The import monitor stays above the main page content, including after navigation.
It distinguishes file transfer, duplicate checking, parsing, metadata validation,
catalog writes, workspace refresh, and saved-protocol query checks. The import
workbench retains the attempt history and diagnostic evidence.

## What the indicators mean

- Upload progress counts bytes sent by the browser. Transfer completion does not
  establish that the server accepted the import or committed any records.
- File verification counts bytes read; metadata validation counts epochs checked.
  Percentages apply to that stage only.
- The inherited Symphony parser does not report granular completion. Its stage
  remains indeterminate, with elapsed time and the last real progress update.
- A monitor heartbeat only proves the status service responded. It does not prove
  the parser advanced. Long stages and network failures are separate states.
- Progress polling reads small job files without acquiring the SQL database lock
  or loading raw traces. Stage writes are throttled and atomically replaced.

## Failure and commit evidence

Known failure before commit, successful commit with follow-up warnings, and an
interrupted attempt with unknown commit state are distinct outcomes. Commit
evidence remains true through later file or log failures. A missing terminal
receipt after a process interruption never establishes rollback.

Restarted services retain interrupted jobs and reconciliation guidance. A live
orphan import child conservatively blocks another import. Corrupt job records
produce diagnostic rows without hiding healthy history; locks are released on
error paths. Missing or corrupt progress files do not silently convert an import
to success. SQL audit-write failures are visible in the local job record.

Refresh status only retries a read. It never retries the import mutation. For an
unknown outcome, inspect Data stores and the job diagnostics before submitting
again. Query-refresh failures after a confirmed import can be revisited using
the protocol's Refresh & compare action.

## Validation

`python/verify_import_progress.py` ran the actual legacy parser in parse-only mode
against the September 23 recording. It reported 5 cells, 690 epochs, 1,308 response
pointers, and 690 stimulus pointers in approximately 11.5 seconds. The observed
epoch counters advanced monotonically to 690/690. Source size, modification time,
and SHA-256 were unchanged. No SQL records were written by this verification.

A disposable malformed H5 produced a nonzero exit and a saved error type, stage,
message, and traceback path. See `import_progress_validation.json` for the proof.

Final checks: 284 Python tests, 92 frontend tests, and the production build passed.
The live UI showed checksum progress, skipped the already-imported September 23
recording, and kept its status visible on the project overview. Stopping and
restarting the idle local server demonstrated connection-loss messaging, retention
of the confirmed result, and automatic restoration of the overview and history.
The catalog remains at 8 cells, 1,776 epochs, and 2 source files. The duplicate
attempt was logged; no protocol suggestions were applied by these checks.

The jobs monitor bounds each request to 8 seconds and schedules the next poll
after settlement. File uploads stop after 60 seconds without transfer or response
progress, preserving uncertain acceptance rather than assuming rollback. Recovery
refreshes workspace reads without submitting any import again.

Adversarial tests use temporary files and SQL doubles for source changes, missing
sources, duplicate and concurrent requests, corrupt receipts, malformed HTTP
requests, audit failures, restart recovery, and disk-write failures before and
after commit. These tests do not claim to reproduce a real machine power loss.
