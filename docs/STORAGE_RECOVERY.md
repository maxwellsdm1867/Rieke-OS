# Local storage and recovery

The H5 recordings contain the signals. MySQL holds imported metadata and current
app state. The app does not need a database action trail to recover tags, saved
queries, layouts, or inclusion decisions.

## What is saved

`app-state.json` locates the compact current-state recovery database under
`backups/app-state/current-<identity>.sqlite`. Together they protect:

- Project settings and protocol configuration files.
- Named predicates/presets, layouts, and the latest run of each distinct query
  (predicate, splits, run time, source identities, and query/metadata versions).
- Current annotation profiles, cell/epoch tags, and curation decisions, including
  densely tagged datasets with several tags and authors per target.
- Current pinned queries with source H5 checksums, metadata checksums, version
  information, and their exact frozen epoch membership and metadata fingerprints.
- Existing export records and their immutable recipes. Export artifacts and H5
  recordings remain separate files and must also be retained.

Tag associations use target and profile UUIDs; display names do not establish
identity. New backups retain explicit frozen membership, so later tag edits
cannot change a pin during recovery. Older query-based backups remain readable
and must reproduce their recorded membership digest before restore succeeds.

Direct cell/epoch tag edits commit their current rows and an append-only change
event together in MySQL. The API acknowledges that database commit immediately;
it does not wait for a separate recovery copy or a page refresh. A burst of tag
edits queues one background recovery capture after one second of inactivity,
with a five-second maximum scheduling delay while edits continue. Lock contention
or a failed capture can extend that delay. The response and `/api/backup/status`
report pending, running, current, or degraded backup state. Normal database crash
recovery still preserves acknowledged commits; loss of the database before the
independent capture finishes can lose those newest edits from the recovery copy.
Clean project close forces the recovery capture and refuses to finish if it fails.

On supported native databases, a verified change tracker copies only changed
records into that recovery database. Rows and the coverage watermark commit
together. An unknown change gap, changed schema/server identity, or unsupported
database requires a full current-state capture. Other successful mutations still
wait for the recovery write; a failed write returns `507` with `saved: true` and
must not be blindly replayed as a new edit.

Startup and recovery captures also create a write-once checkpoint for the active
UTC day under `backups/app-state/checkpoint-v2-YYYY-MM-DD.sqlite`. It records the
first capture that day; the current recovery database holds the latest capture.
No background schedule runs on inactive days. New checkpoint history keeps at
most two checkpoints within a combined 128 MiB budget, except that the newest
checkpoint is retained even if it alone exceeds that budget. Current state is
always retained. Old-format backups and explicit before-restore copies are
preserved separately. H5 signals and derived metadata indexes are not copied
into these app-state files.

The JSON pointer alone is not a standalone backup. Keep it with its referenced
SQLite file, or use a sealed daily checkpoint for an independent app-state copy.
Use the complete project transfer workflow to include recordings and exports.

Shared cell/epoch tag batches append one event containing their before/after
values in the same transaction as the edit. Routine query runs, curation edits,
layout saves, and preset saves retain current state without a new event for each
operation. Each distinct query has a current/latest-run record. Existing history
and scientific import/export/external exchange receipts remain available. The
app-state mirror restores current state, not the append-only event history; a
full SQL backup includes that history.

Ordinary shared-tag filtering uses a persistent MySQL lookup. Existing projects
build it once during preparation; database triggers maintain changed memberships
in the same transaction as each canonical tag edit, including external SQL
writes. Clean reopen reuses it after checking fresh canonical content, the
lookup table identity, and its schema and triggers. Missing triggers, replaced
tables, or an unclean checkpoint cause validation or rebuilding before reuse.
The autocomplete dictionary keeps current tag names, distinct-target usage
counts, and author references. Prefix keys use Python's exact Unicode casefold
semantics and are computed once for each new name. Database triggers maintain
counts with the same transaction as the tag edit, including external SQL writes.
These tables are rebuildable indexes, not additional canonical annotation copies.
There is no full SQLite tag-cache build on the ordinary native filtering path.
Full aggregate views and unsupported database contracts retain their existing
canonical/derived readers. Cell tags remain one cell record per author, joined
to their child epochs by UUID. Durable SQL autosave remains enabled.

## Recovery

A normal process crash needs no manual restore: committed current state remains
in MySQL. Redo logging, durable commits, and doublewrite protection remain on.

To recover missing settings or roll back to a state snapshot, stop the **project
app server** first, leaving its database available. From the application checkout:

```sh
PYTHONPATH=python .rieke-runtime/venv/bin/python python/workspace_state_snapshot.py \
  --project-dir /path/to/project \
  --restore /path/to/project/backups/app-state/checkpoint-v2-YYYY-MM-DD.sqlite
```

The same command accepts `app-state.json` with its referenced database, or older
JSON/SQLite snapshots. Restore refuses a running app, a
foreign project, changed source/metadata identities, corrupted SQLite snapshots,
or an older pinned query whose reconstructed result differs. It saves the immediate
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
