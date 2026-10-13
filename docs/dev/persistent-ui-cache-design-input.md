# Persistent UI cache: design input

2026-10-13. Investigation and proposed interfaces only; no application implementation, benchmark, migration, or user-project modification.

## Verified existing boundaries

Source inspected in `/Users/maxwellsdm/.codex/worktrees/full-epoch-qc/Rieke-OS` at the requested `386e72d` baseline. The inspected `desktop/drafts/draft-store.cjs`, `workspace-app/src/renderer-drafts/`, and `workspace-app/src/resourceCache.js` have no diff against installed release source `add33d1`. Other local branches, including startup `86e395a` and managed-library `4a9d247`, are separate work and must be reconciled before implementation; this design does not assume they are integrated.

- [Native DraftStore](../../desktop/drafts/draft-store.cjs) already writes versioned JSON with a 2 MiB bound, exclusive temporary creation, private ownership checks, and replacement by rename. It refuses to overwrite unreadable state; explicit recovery preserves original bytes. Its [contract](../../desktop/drafts/README.md) explicitly distinguishes atomic replacement from power-loss durability.
- [Renderer draft session](../../workspace-app/src/renderer-drafts/desktopDraftSession.js) serializes saves, waits for load, guards navigation intent, and distinguishes recovery identity from presentation restoration. The [owner contract](../../workspace-app/src/renderer-drafts/AGENTS.md) binds idle autosave to a three-second cadence. Saved hints are not mutation consent.
- [Desktop main](../../desktop/main.cjs) authenticates sender origin/project and scopes saved views by project UUID, canonical project path, and compatibility. [Startup session](../../desktop/startup/startup-session.cjs) uses stable `view-v1` compatibility with explicit legacy candidates. An existing corrupt candidate is not bypassed to silently start fresh.
- [Epoch resource cache](../../workspace-app/src/resourceCache.js) is memory-only, with 128 entries, 32 MiB estimated bytes, and 30-second TTL. Exact path/revision keys, request generations, annotation invalidation, and prefetch reservations already exist.
- [Workspace metadata refresh](../../python/workspace_service.py) already reopens generation-addressed SQLite indexes under `project/cache/metadata/`. Generation incorporates source identities, validated metadata, input signatures, and implementation contracts. [DiskMetadataIndex](../../python/disco/metadata/disk_index.py) builds a temporary database with metadata, seals its hash, publishes database and seal, and validates both on opening. Writer coordination and reader leases already protect immutable generations. Do not serialize the entire metadata index again as frontend JSON.

These relative source links name owners common to the repository. The parent subsequently moved this documentation worktree onto `codex/ui-cache-design` based on the same `386e72d` UI source. The independently developing release, startup, and library deltas still require explicit integration before a combined implementation can be qualified.

## Storage decision

Use three layers with deliberately different failure policies:

| Layer | Storage and lifetime | Contents |
| --- | --- | --- |
| Live view | Existing React state plus retained project document; bounded working set | DOM, scroll, transient controls, already-rendered traces, request deduplication |
| User state | Keep the native versioned JSON draft owner; durable local app-support location | View/recipe hints, unsaved user input, pending-operation recovery identity |
| Disposable resource cache | Reuse existing backend SQLite metadata indexes; add a separate indexed SQLite response store only for measured repeat reads | Bounded successful summary/page responses and selected expensive trace windows |

The live view gives fast in-session returns with no disk read on a healthy warm switch. JSON state restores where the user was after restart. Disk resources avoid repeating expensive reads after renderer/process loss. None eliminates the need to start a backend or establish current scientific authority after restart.

Choose JSON for the small, whole-document user snapshot because there is already an owner and recovery contract. Do not put drafts in a general cache database or subject them to TTL/LRU. Choose SQLite for many independently keyed disposable records because entries can be updated/evicted transactionally without rewriting a growing JSON file. If measured repeat-read costs justify it, name this separate store `resource-cache.sqlite`; never add mutable response tables to a sealed metadata index or duplicate its full metadata. Keep raw H5 authoritative and avoid caching every trace by default. For an initial candidate, store bounded trace payloads as BLOBs in the same response-cache transaction; external blob files and manifests add publication complexity without measured need.

Apple distinguishes app-support data from recreatable caches; caches can be deleted. That supports keeping user state and reconstructable resources in separate roots. [Apple file-system guidance](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html). Proposed new response-cache root: a private local OS cache directory for Disco, with one namespace per canonical project binding; retain existing project metadata-cache ownership. This avoids adding portable UI caches to scientific recordings or silently changing existing cache placement. Export/share need not include recreatable UI responses.

## Proposed identities and interfaces

The names below are a reviewable design, not existing APIs:

```text
ProjectBinding = {projectUuid, canonicalPath, catalogIdentity}
RuntimeIdentity = {projectBinding, backendInstanceId}
ResourceKey = {
  resourceContract, projectBinding, kind, normalizedParameters,
  sourceIdentities, scopeIdentity, dependencyRevisions
}
StoredResource = {
  cacheSchema, keyHash, encodedKey, payloadCodec, payloadBytes,
  payloadHash, createdAt, expiresAt, lastUsedAt, byteCount
}

PersistentResources.readMany(binding, keys, byteLimit)
  -> [{key, payload, provenance, state: 'needs-validation'}]
PersistentResources.publishValidated(binding, resourceBatch, revisionReceipt)
PersistentResources.invalidate(binding, dependencyChanges)
PersistentResources.prune({globalBytes, projectBytes, entryBytes, olderThan})

DraftStore.load/save/reset remains its own public interface.
```

The backend-owned response cache should reuse existing Python SQLite availability and project ownership rather than introducing an Electron-native SQLite dependency. A restricted endpoint supplies a small initial batch after service health is established. Rendering the saved shell/view can precede that batch. If later measurements require cached rows before backend start, that is a separate desktop snapshot seam to review, not a reason to let the renderer read arbitrary files.

Separate persistent identity from runtime identity: a backend-instance token expires on restart, whereas recorded source fingerprints and persisted catalog revisions can remain meaningful. A renderer's counter initialized to zero, a port, a display name, or a backend PID is not a safe disk-cache identity. Do not persist process-local freshness generations as if they prove cross-restart validity. SQLite `PRAGMA data_version` is connection-local and useful only when compared on the same connection over time; it cannot serve as a restart-stable revision. [SQLite data_version](https://www.sqlite.org/pragma.html#pragma_data_version).

Initially retain existing UUID-plus-canonical-path isolation: cloned projects sharing a UUID must not borrow drafts. Moving a project therefore yields a disposable cache miss, not automatic authority transfer. A future explicit relocation operation may move view state after checking identity and preserving the old copy. Content-addressed source projections may be reusable across paths only where their existing contract verifies source/metadata identity; do not weaken that verification. Renames, relocation, and imported project copies must not silently merge pending operation records.

## Restart and hydration

1. Load the current draft through its existing recovery rules and show its view shell. A later user navigation wins over late restoration.
2. Establish the backend/project binding and obtain a bounded revision/identity manifest. Mutable summary snapshot validation must read cheap persisted revision stamps, not recompute the full overview to decide whether its cached overview is current. If those stamps are not currently available, adding an authoritative cheap validation seam is a prerequisite for that optimization; avoid pretending a TTL proves unchanged data. Existing source-integrity checks remain authoritative; this proposal does not replace file verification with mtime alone.
3. Fetch only persisted resources needed for the visible view, with a strict byte cap. Their shape and identity are validated before hydration. Cached displays may be shown as snapshots while freshness is unresolved; scientific actions remain governed by fresh server checks.
4. Admit matching resource revisions without replaying the expensive request. Revalidate only dirty or unknown dependency groups. Do not load the whole disk cache into RAM or send one giant bootstrap payload.
5. Publish newly validated successful responses asynchronously in coalesced batches. A failed cache write is a cache miss next time; it must not fail a successful scientific operation. A failed draft save retains the existing recovery/close behavior.

TanStack's persistence provider coordinates asynchronous restore with query mounting to avoid a fetch/restore race. Its documented controls include `maxAge`, a compatibility `buster`, and `gcTime` alignment; after restoration, freshness policy still governs refetching. These mechanisms can inform or implement the hydration gate, but do not establish project identity. Explicitly allowlist queries for persistence and exclude mutation state, credentials, queued commands, server leases, and one-time authority. Do not call automatic mutation resumption as part of cache hydration. [TanStack persistence contract](https://github.com/TanStack/query/blob/main/docs/framework/react/plugins/persistQueryClient.md).

## Crash consistency and publication

SQLite transactions atomically publish related rows; crash guarantees rely on supported filesystem/flush behavior. [SQLite atomic commits](https://www.sqlite.org/atomiccommit.html). For the proposed local disposable response store, start with rollback journaling and `synchronous=FULL`, matching the existing index's conservative approach; measure before changing it. Batch payload, full key, dependency revisions, checksum, and accounting in one transaction. Uncommitted records must be invisible, and late responses must be rejected against the current invalidation generation before commit.

WAL is an optional measured concurrency choice, not a default portability shortcut: it requires same-host shared-memory coordination and does not work over network filesystems. Its live `-wal` file belongs to database state. [SQLite WAL](https://www.sqlite.org/wal.html). Cache correctness must tolerate losing recent entries; user drafts cannot share that loss policy. SQLite documents weaker power-loss durability for `NORMAL` than `FULL` in WAL and filesystem-dependent rollback durability. [SQLite synchronous modes](https://www.sqlite.org/pragma.html#pragma_synchronous).

For user JSON, preserve same-directory exclusive temporary files and serialized writes. A stronger durability candidate writes and syncs the temporary file, closes it, renames it, then syncs the containing directory where supported; failure handling must retain the previous valid snapshot and report uncertain durability instead of claiming a durable save. Node provides `FileHandle.sync()` and `writeFile`'s `flush` option, but a file flush alone does not establish the complete rename/directory durability protocol. Native crash testing remains required. [Node filesystem API](https://nodejs.org/api/fs.html#fspromiseswritefilefile-data-options).

Existing metadata database-plus-seal publication uses two replacements, not an atomic two-file transaction. Its validation can reject a crash-interrupted pair and rebuild the disposable index. Preserve that safe-miss behavior; do not describe it as indivisible publication. If new immutable multiblob generations are ever necessary, publish a validated manifest last and let recovery ignore unreferenced temporary generations.

## Compatibility, invalidation, limits

- **Schema:** version the response database and each resource codec/contract. Incompatible disposable stores are discarded/rebuilt. Use explicit compatibility rather than automatically busting every cache for a cosmetic app release. Draft migrations must retain original bytes, validate project ownership, and never silently discard unknown versions.
- **Invalidation:** imports affect source/catalog membership and dependent summaries; annotations affect metadata/tag queries; selection changes affect selection-dependent resources; protocol edits affect membership-dependent reads; replacement/deletion invalidates source-linked traces. Include query/sort/page/stream/range/units where relevant. Patch only what a committed server receipt establishes; otherwise reread the affected result. See [granular retention research](ui-retention-primary-source-research.md).
- **Freshness:** persist revision provenance as evidence to compare with current authority, never as mutation permission. Existing frozen membership and recovery identities retain their own checks. Invalidate on unknown revision gaps, incompatible backend/schema, or mismatched source identity.
- **Bounds:** keep existing live trace bounds as the starting point. Proposed experiment caps for new disk responses: 256 MiB per project, 1 GiB global, and 8 MiB per entry, plus a seven-day unused-entry age limit. These are tunable hypotheses, not measured optima. Count database, journal, and temporary bytes; reserve disk headroom. Evict by last use with large trace payloads first. Do not apply these policies to drafts or recordings.
- **Maintenance:** expire in small idle batches; no full-database vacuum or all-project scan on a project switch. A cache-full/read-only/corrupt condition falls back to normal reads without deleting scientific data. Cache cleanup must stay within authenticated owned namespaces, preserve reader leases, and avoid symlink traversal. Draft recovery remains explicit.

## Benchmark and fault-test design

The timing owner should separate warm same-process return, renderer restart with live backend, full app restart with disk cache, first open without cache, and relevant-mutation return. Record click-to-correct-view plus backend-ready and fresh-authority times, request counts, bytes read/written, cache hits/misses, memory, disk growth, and quiet-background load. Compare equal fixtures and exact queries serially; no timing work was run here.

Fault cases: kill during temporary JSON write/rename and SQLite transaction; corrupt cache payload/schema; restart after committed import; reused port; same UUID at a different path; source replacement with unchanged display name; cache deletion; read-only/full disk; concurrent publish/invalidate; missing seal; late restore after navigation; and explicit quit with pending draft recovery. Expected outcome is a valid prior/new draft or preserved recovery, and a verified cache hit or safe miss. Never a wrong-project result, lost user draft, or replayed scientific mutation.
