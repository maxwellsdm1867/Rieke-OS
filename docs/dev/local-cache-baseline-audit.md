# Local baseline reconciliation and cache seams

Read-only source audit, 2026-10-13. No application edits, integration, installation or benchmark workloads were performed for this audit. Companion audits describe installed 0.1.12; they must not be mistaken for an audit solely of the newest UI branch.

## Source identities inspected

All four application checkouts were clean when inspected:

| Owner | Checkout | HEAD / branch |
| --- | --- | --- |
| Newest local UI | `/Users/maxwellsdm/.codex/worktrees/full-epoch-qc/Rieke-OS` | `386e72d07fa044ec874306ae5197a44503411dcf`, `codex/next-version-integration` |
| Installed release source | `/private/tmp/disco-release-0111-20261011` | `add33d153ae8f533d5c4a68c50690764323c4336`, `codex/release-0.1.12` |
| Startup improvements | `/Users/maxwellsdm/.codex/worktrees/startup-discovery/Rieke-OS` | `86e395afb5abb5cfc2f2fa0f895caee5a6205f8a`, `codex/startup-discovery` |
| Shared managed H5 library | `/private/tmp/disco-managed-library-20261012` | `4a9d2470c3e0932fc30f4df1de1c8df852f74b8d`, `codex/managed-recording-library` |

The isolated documentation/design worktree `/Users/maxwellsdm/.codex/worktrees/project-switch-investigation/Rieke-OS` is now based on newest local UI `386e72d` on `codex/ui-cache-design`, as coordinated by the parent task. Existing untracked investigation documents were preserved. Earlier audits were written there while it was based on published `8cd6182`; their explicit installed-release source attribution still applies. No shared primary or other application checkout was switched.

Newest commit time is insufficient for choosing a complete application baseline. UI and release diverge at `d4890420ba3b56702787cfc7c99ad3d4d9977149`. The complete release-to-UI diff has **86 files, 629 insertions and 6,226 deletions**, including evidence and tooling. Its frontend-source subset has 35 changed paths. Neither branch should replace the other wholesale.

The UI branch adds the approved retinal-cell artwork and themes, including `components/UnknownCellDrawing.jsx`, `components/CellTypeIcon.jsx`, `cell-qc/cellTypes.js`, `themes.css` and their tests. The release branch separately includes completed overview caching, protocol membership/index reuse, scoped Workbench/cell reads, rectangular zoom/continuous pan and 0.1.12 trace-cache admission. The UI branch does not contain `protocol-overview/overviewCache.js` or `useOverviewResource.js`; its summaries still use `useStableSummary`. Claims about those completed cache owners apply to release, not UI HEAD.

Startup `86e395a` descends from release through `6418220`. Its changes include deferred desktop analysis imports and bounded project discovery in `python/disco/projects/project_inventory.py`, plus launcher/packaging and retained-contract updates. Preserve these rather than measuring an older discovery implementation as the proposed candidate.

Managed-library `4a9d247` is based on published main `8cd6182`, not release or UI. Its intended commit changes 23 files; the full comparison against release spans 195. Preserve the intended managed-recording delta in `recording_registry.py`, `recording_files.py`, portability/import endpoints and notices; do not bring its older app wholesale into integration. Authoritative managed H5 recordings are durable data, never evictable UI cache.

Before implementation, create or identify a reviewed combined candidate containing newest UI plus release functionality, then explicitly reconcile startup and managed-library changes. Preserve each original branch. Bind timing results to the exact measured tree; measuring each source separately does not qualify a combined build.

## Findings rechecked on newest UI

- `App.selectProject` calls `window.location.assign`; desktop `main.cjs` uses `loadURL`. Project return destroys the frontend document despite backend-process reuse.
- `presentation/workspacePresentationSessions.js` owns maps for only one App mount. Snapshots preserve route/fallback fields, not DOM, fetched resource lifetimes or a bounded retained project session.
- `workspace-navigation` creates visit identities; `App.jsx` uses them in route composition and conditionally renders protocol tab content. Snapshot restoration still requires mounting and fetching.
- `resourceCache.js` is bounded at 128 entries/32 MiB with a 30-second TTL; response keys include path and broad revision. Tag changes therefore can retire unchanged sample reuse.
- `useWorkspaceChanges.js` increments one general revision for every event; only annotations/curation avoid the structural increment. `useSummaryRevision` defers hidden annotation summaries but structural changes still fan out.
- `resourceRequest.visibleResourceState` returns `data:null` when revision/nonce identity changes. Updating data can replace a useful existing display.
- `annotations/externalTagMonitor.js` starts with null revision and treats the first successful scan as changed. Tree ancestors and search activation explicitly retire caches on focus/visibility events.
- `RetainedTreePresentation.jsx` already uses React Activity for one eligible slot. It provides a useful local retention pattern, not whole-app retention. Retaining DOM without lifting request lifetime still lets reactivated effects fetch again.

## Existing persistence to reuse

`renderer-drafts/desktopDraftSession.js` and `useDesktopDraft.js` already serialize renderer checkpoints and integrate load/save/recovery. Desktop `drafts/draft-store.cjs` stores a versioned project envelope with 2 MiB limit, identity/owner/symlink checks, temporary-file rename and explicit unreadable-state recovery. Do not duplicate this with arbitrary JSON writes or stuff waveform payloads into its bounded draft.

**Source correction:** `desktop/drafts/README.md` still describes app-version:view-v1 scope, but current executable `desktop/startup/startup-session.cjs` uses schema compatibility `view-v1`, with fallback to 0.1.8/0.1.9 namespaces. `main.cjs` chooses a UUID/canonical-path/schema namespace and preserves corrupt originals. Thus a release-number-independent draft namespace already exists; it is not a missing feature to implement again.

`project-preferences/projectPreferences.js` owns project-backed recent searches and protocol shortcuts; localStorage is only a cache/migration source. It hydrates before writes and serializes updates. `protocol-tree-layout` owns versioned/coalesced layout persistence. Preserve portable preference authority rather than replacing it with browser-origin-only data. Per-project loopback ports can change, making localStorage a poor canonical restart store.

## Proposed narrow integration seams

1. Desktop project-view owner: `activate(projectIdentity)`, `close(projectIdentity)`, `snapshotForEviction(projectIdentity)`. Identity includes verified UUID/canonical root and current backend instance. Own bounded live documents and memory accounting; integrate all hidden views into existing draft flush/close/security admission. Project data, scientific operations and preferences remain their existing owners.
2. App destination owner: stable destination identity separate from history-entry identity; reuse current session checkpoint/prune methods for eviction recovery. Retain visited routes/tabs within limits, preserve dirty views, pause hidden replaceable reads. Accepted imports/writes stay project-owned.
3. Resource owner: synchronous last-success lookup plus subscription, coalesced ensure/read, and dependency-scoped change receipt application. Adapt existing release overview, tree and trace owners, not a second generic cache that disagrees with them. Keep same-resource display while refreshing.
4. Persistent acceleration adapter: versioned manifest plus bounded payloads under verified project scope; explicit compatibility, source fingerprints, dependency revisions, corruption miss handling and atomic publication. Persist only useful reusable read results and cheap UI snapshots. Do not serialize promises, errors as data, consent, action leases or reusable mutation authorization.

These are proposed contracts, not implemented APIs. Existing local guides require discussion/adoption updates before changing lifetime or authority; the requested design document is the reviewable contract proposal.

## Dependency matrix

| Resource | Cache identity / revisions | Changes that affect it | Changes that must not erase it |
| --- | --- | --- | --- |
| Project view | UUID + canonical root + compatible view schema; backend instance for live connection | Explicit reset/close, incompatible restore, identity pruning | Navigation, focus, ordinary import or tag updates |
| Source totals/list | Project source catalog generation | Committed import, source delete/restore/exclusion | Import progress, duplicate no-op import, tag edits |
| Protocol membership/page | Protocol binding + query/sort + actual dependent generations | Merge, binding/predicate changes, affected source policy | Import into unrelated/frozen cohort, unrelated protocol edits |
| Raw samples | Verified source content + stream + sample window + representation | Source replacement, representation change, eviction | Tags, review/inclusion, focus, wall-clock TTL |
| Epoch decorations | Epoch identity + annotation/curation revisions | Confirmed tag, review, inclusion or external edit | Pure view changes or unrelated annotations |
| Query/tree results | Scope + query + order + only referenced field generations | Relevant membership/metadata/tag-dependent predicates | Unrelated annotation fields, focus |
| Field registry | Schema/metadata vocabulary revisions | Import introducing fields, metadata/vocabulary change | Selection or trace zoom |
| Workbench queue | Protocol binding/candidate revision + queue revision | Candidate disposition, merge, relevant import suggestions | Tab return, unrelated traces |
| Export history | Project history revision | Export completion/history change | Tag edit or import progress |
| UI intent/drafts | Project/view identity | User change, targeted deletion pruning | Data revalidation |

A committed import publishes one change; progress does not invalidate source summaries. Patch exact counts/rows when receipts suffice, otherwise refetch affected visible resources once. Frozen membership remains frozen. Disk data can furnish a recoverable display but must not renew scientific authority; reconnect should reconcile cheap revision witnesses, not recompute every summary.

## Verification gaps to address

Existing public tests cover snapshots, history restoration without merge consent, draft corruption/identity, preference hydration, tree layout serialization and local retained tree behavior. They do not establish end-to-end instant project switching, bounded retained documents or restart cache hit performance.

Add behavioral cases for A→B→A document/mount/request counts, protocol-tab return, returning after trace TTL, hidden-view eviction, memory pressure and pending draft writes. Verify one committed tag edit updates relevant decoration without waveform reads; one import updates totals without remount and without changing frozen cohorts. Test restart hydration, corrupt derived caches, schema compatibility, same UUID at different roots, backend-instance change, source replacement, missed event watermark, stale action rejection and duplicate notifications. Existing project-unmount/strict replacement/quit tests must cover hidden documents too. Run required fixed core and actual-million gates only after an application candidate exists, followed by separately attributed native qualification.
