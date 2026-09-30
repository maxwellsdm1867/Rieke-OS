# Automatic external tag return

Status: initial receiving path implemented. Implementation details below supersede the earlier proposal where noted.

## Decision

Keep shared project annotations as the authoritative tag store. The receiving service scans registered export folders for external tag additions. Each export carries its own writable annotation return area beside its frozen database. No separate project inbox location needs to be supplied to Wheeler, and the user never reimports the dataset.

```text
project/exports/<export_uuid>/
    recordings.sqlite             frozen recording metadata
    annotation-return.json        format, identities, relative return path
    annotations/
        incoming/<message_uuid>.json
        receipts/<message_uuid>.json
```

Wheeler reads the exported database, obtains exact epoch/cell UUIDs, and writes a tag message into that export's `annotations/incoming` directory. The project service discovers it, commits tags to the existing DataJoint annotation store, and updates the UI. A helper can make this a single `tag(target_uuid, tag, author)` operation for any external service; implemented by `workspace_external_tags.submit_tags` and its CLI.

The SQLite file remains a frozen scientific handoff. Its current annotation tables are export-time snapshots, protected by mutation triggers; the export download route also verifies the saved artifact checksum. Modifying that file would invalidate the artifact check. A writable sidecar therefore gives the actor a place to tag the exported data while preserving the existing export contract. The sidecar can be attached to SQLite for analysis if needed, but JSON additions are sufficient for the initial receiver. Do not scan arbitrary changes in frozen tag tables or import the old snapshot as new assertions.

## Receiving-end experience

- Opening a project page automatically POSTs a scan of its registered export return directories.
- Reloading the page scans again. The External tags control also offers Check for tags and shows scan state.
- While a project page is visible, a sequential three-second poll picks up additions without user action; returning to the page checks immediately. Scan bounded return directories, not all recordings or arbitrary SQL files; a filesystem watcher can reduce latency but is not the correctness mechanism.
- The epoch's ordinary Tags area gains the tag with Wheeler attribution. Existing direct/inherited scope and query fields remain in use. A publication-specific count of tagged child epochs is a future UI extension.
- Existing tag search and author filters work after ingestion. The External tags control shows a received count; expanding it shows recent authors, counts, and receipt times. Normal success does not open a dialog.
- The External tags control lists each return location, last checked time, pending/error count, and a “Check for tags” retry. Missing folders are shown as unavailable, never interpreted as tag deletions.

Only a folder visible to the receiving machine can be scanned. The default is the app-managed export folder Wheeler opens in place. If Wheeler works on a copy elsewhere, deliver/synchronize its complete annotation messages into the original project export return folder. Registering arbitrary alternate folders is not implemented. A remote copy cannot communicate changes without a shared path, file transfer, or API. Do not synchronize a live writable SQLite database through a file-sync service; complete immutable JSON messages work better for that case.

## What already exists

- `python/workspace_annotations.py`: project-scoped `SharedAnnotation` records keyed by target kind, target UUID, and author profile UUID; revisions, locking, transactional audit, batch reads, and tag suggestions.
- `python/workspace_tag_exchange.py`: portable `rieke-tag-exchange` v1 JSON; exact UUID/source checks; additive import preview/apply; author attribution. Repeated additions do not duplicate tags.
- `python/workspace_sqlite.py`: exported `epoch_uuid`, `cell_uuid`, `project_uuid`, `export_uuid`, and source hashes; frozen `shared_annotations` and `annotation_revisions`. Exported `epoch_tags` instead means protocol curation.
- `python/workspace_tag_predicates.py`: query fields for direct cell tags, direct epoch tags, effective tags, and authors.
- Web components already distinguish direct epoch tags from inherited cell tags. UI saves invoke local refresh callbacks. There is no project-wide external annotation change observer in the inspected frontend.

Today a service can use the existing HTTP preview/apply endpoints, but the portable-file workflow requires explicit import and the open UI has no automatic notification path.

## Implemented transaction and discovery

Both SQLite export paths create `annotation-return.json` and `annotations/incoming`. Existing registered SQLite exports receive these sidecars on first scan. The manifest lists exact targets and source hashes and supplies a message example; it is a convenience for writers, not the receiver's authority. The receiver validates membership against the database's registered export recipe and current acquisition identity registry.

Writers publish uniquely named complete JSON messages using an atomic rename or the provided helper (which uses a temporary file and an exclusive hard link). Each message contains a fresh UUID, export UUID, and an existing v1 tag-exchange document. All entries must name this project and provide matching source evidence. Profile names are attribution claims consistent with the existing local model; no authenticated remote actor boundary is implied.

`POST /api/annotations/scan` runs under the existing HTTP database lock and project annotation lock. It visits registered export folders only, rejects redirected folders/message symlinks, limits messages to 8 MiB, rotates through at most 100 messages per export per scan, and uses the existing bounded tag validation. Malformed messages report per-file errors without blocking other valid messages. Database failures abort the request and retry on a later poll.

Additions and a receipt are committed together by `SharedAnnotations.apply_batch`. Receipts use the existing transactional Event table, with action `external_annotation_received`, rather than introducing a second receipt database. The key is project plus message UUID; a content hash binds the entire message including its authors and export. Same ID/content returns the saved receipt; same ID/different content is rejected. Unchanged-only submissions also receive a committed receipt. The project lock serializes independent consumers. Files remain immutable and receipts are reconstructed after crashes, so deleting a file receipt cannot replay a previously removed tag.

Imported tags are additive. Missing tags/files never delete annotations. Existing explicit author-scoped annotation edits can remove tags; automated retraction commands are not part of this initial transport. Bad identities and missing targets are reported and retried without guessing matches.

## Implemented UI observation

`ExternalTagSync` starts a scan when a project page opens, polls sequentially every three seconds while visible, and checks on focus. Errors back off to 30 seconds. A manual Check for tags retries immediately. There is no background daemon: closed pages resume ingestion on reopen.

The receiver returns a compact checksum of annotation target/author revision columns. This detects changes across processes without loading tag text or requiring a schema migration. It still scans revision rows and receipt events; a persisted sequence and indexed receipt table would improve very large histories later. The response includes only the latest 20 receipts plus total counts.

On a changed revision (including the first scan), the UI invalidates epoch resource caches and advances its existing global resource revision, refreshing tags, summaries, vocabulary, and live queries. Late monitor responses after unmount are discarded and scans never overlap within one page. This uses existing view refresh behavior rather than introducing new selection semantics. Saved query evidence, pinned snapshots, and previous exports stay frozen.

## Scope and querying

For publication use, tag the exact epoch UUIDs actually used, for example `publication:paper-2026-01`. Record export/run/publication provenance with the import audit. Do not automatically tag the entire cell merely because one epoch was used: a cell tag inherits to every epoch of that cell, including later imports. The cell UI can instead show a derived summary such as “3 epochs used in paper-2026-01”; that summary must not become an inherited cell tag.

A genuine cell classification should target `cell_uuid`. It appears on that cell and as inherited metadata on its epochs across protocols. Actors can read current tags using existing `/api/annotations/read`, `/api/cells/<uuid>/annotations`, `/api/epochs/<uuid>/annotations`, and `/api/annotation-tags` endpoints, and use existing annotation predicate fields for search. Historical SQLite exports answer what was known at export time; they do not answer the current live state.

An optional HTTP submission endpoint can later feed the same ingest function and receipt ledger. It is a second transport, not a second tag system. Avoid direct actor writes to DataJoint tables, which bypass validation, audit, receipts, and revision notifications. Automatic synchronization across separate projects is also outside this initial design: delivery names one project explicitly, even if another contains the same acquisition UUIDs.

## Validation

`test_workspace_external_tags.py` exercises protocol SQLite export → actor helper → scan → current annotation API and tag query, unchanged artifact checksums, cell inheritance, unchanged receipts, restart recovery, replay after removal, transactional rollback on receipt failure, invalid identity/source isolation, changed-content rejection, missing folders, and existing-export sidecar creation. Candidate export tests verify their return manifest and exact subset.

Frontend tests cover reopen refresh, stable-revision suppression, changed revisions, overlapping scan prevention, unmount races, and error recovery. Related annotation/cache tests and the production frontend build validate integration. Automated tests use disposable database doubles and files. A subsequent live browser test used a separate native MySQL 8 instance with real DataJoint tables and transactions, the real Flask routes, and the production React build. It verified automatic epoch display and search, preserved drafts, reopen ingestion, cell inheritance, invalid-target isolation, receipt recovery from another process, replay after removal, and unchanged SQLite bytes. See `docs/dev/external_tag_live_validation.json` and `docs/dev/external-tag-live.png`. Acquisition metadata was generated for two test cells; the research database was untouched.
