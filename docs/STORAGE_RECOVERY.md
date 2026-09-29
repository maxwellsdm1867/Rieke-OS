# Local storage and recovery

The H5 recordings contain the signals. MySQL holds imported metadata and current
app state. The app does not need a database action trail to recover tags, saved
queries, layouts, or inclusion decisions.

## What is saved

`app-state.json` is an atomic current-state snapshot. It includes:

- Project settings and protocol configuration files.
- Named predicates/presets, layouts, and the latest run of each distinct query
  (predicate, splits, run time, source identities, and query/metadata versions).
- Current annotation profiles, sparse cell/epoch tags, and curation decisions.
- Current pinned queries with source H5 checksums, metadata checksums, version
  information, and a digest of the expected result. Recoverable pins do not
  enumerate all epochs: recovery reruns their predicates and verifies the digest.
- Existing export records and their immutable recipes. Export artifacts and H5
  recordings remain separate files and must also be retained.

An existing frozen subset that a saved predicate cannot reproduce retains its
explicit membership. It is never silently widened on recovery. UUIDs remain
necessary for explicitly tagged/edited cells and epochs.

Successful API writes update the snapshot; unchanged state does not rewrite it.
Startup and successful writes create one write-once SQLite snapshot per active
UTC day under `backups/app-state/YYYY-MM-DD.sqlite`. A day without running the app
has no scheduled backup. These daily files record the first captured state that
day; `app-state.json` holds the latest successful capture. No H5 data or derived
metadata caches are copied into them.

Routine query runs, tag/curation edits, layout saves, and preset saves no longer
append action events. Each distinct query has a current/latest-run record, not a
record per execution. Existing history and scientific import/export/external
exchange receipts remain available. Explicit export/version workflows remain
unchanged.

## Recovery

A normal process crash needs no manual restore: committed current state remains
in MySQL. Redo logging, durable commits, and doublewrite protection remain on.

To recover missing settings or roll back to a state snapshot, stop the **project
app server** first, leaving its database available. From the application checkout:

```sh
PYTHONPATH=python .rieke-runtime/venv/bin/python python/workspace_state_snapshot.py \
  --project-dir /path/to/project \
  --restore /path/to/project/backups/app-state/YYYY-MM-DD.sqlite
```

The same command accepts `app-state.json`. Restore refuses a running app, a
foreign project, changed source/metadata identities, corrupted SQLite snapshots,
or a pinned query whose reconstructed result differs. It saves the immediate
pre-restore configuration under `backups/app-state/before-restore-*.json`, changes
SQL state transactionally, and restores configuration files if an ordinary error
occurs. An interrupted restore leaves a marker that prevents app startup until
offline recovery is completed. Restart the app afterwards. Keep the original recordings, parsed imports,
project/catalog files, database credentials, and export artifacts available.

These are **app-state backups**, not a substitute for recording storage or a full
SQL backup. If the database itself is lost, restore a verified SQL backup (or
rebuild/import the matching source metadata and initialized app schema), then
apply the current state snapshot. The restore command does not initialize or
adopt orphaned database files.

## Database defaults

Private local databases use 64 MiB of reusable redo space and a 128 MiB buffer
pool. Binary logging is disabled because the app does not implement replication
or binary-log point-in-time recovery. These settings do not disable durable
commits or application persistence. External database services are not retuned
automatically. Existing Docker containers need an explicit, backed-up migration;
new managed Docker databases and new/restarted bundled native databases use the
local profile.

Never delete `ib_logfile*` or copy a running MySQL directory to shrink/backup it.
MySQL must checkpoint and resize its own redo files during a clean restart.

## Verified SRM migration, 2026-09-29

The SRM database directory fell from 4.16 GiB to about 168 MiB. All 6,830 rows in
33 tables matched before/after checksums. The compressed full SQL backup is
about 1.3 MiB and was restored into a separate server with every row verified.
A second isolated recovery test removed annotations, layouts, and presets,
restored them from the state file, and regenerated all five SRM pins from queries.
The current snapshot is approximately 526 KiB including seven existing export
records; configuration/query/edit state excluding export recipes is about 31 KiB.

Checks and the full SQL backup are in the SRM project's
`backups/storage-optimization-20260929/`; the applied Docker configuration is
`database/local-mysql.cnf` (also installed in its container's
`/etc/mysql/conf.d/rieke-local.cnf`).
