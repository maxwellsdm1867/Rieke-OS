# Retained views and persistent read caches

Proposed design, 2026-10-13. No application implementation or installation is included. The design branch is `codex/ui-cache-design`, based on newest local UI commit `386e72d07fa044ec874306ae5197a44503411dcf`. Other local branches remain intact.

## Intended behavior

Switching back to an unchanged project, protocol, or tab shows its last state immediately. It retains scroll, expansion, selected epoch, trace zoom, filters and draft input. A committed data change updates the affected numbers and rows in place. Restarting the app restores the view from disk and reuses compatible read results instead of rebuilding them all.

These are three different paths:

| Path | Work required |
| --- | --- |
| Already-open view | Reveal the live view and focus it. No document reload or disk read is needed. |
| Evicted view or app restart | Restore saved view state; hydrate bounded compatible read results from disk; reconnect and validate relevant revisions. |
| First visit, genuinely changed data, incompatible or missing cache | Read/build the required resources once, publish them, and retain them for subsequent use. |

Disk persistence complements live retention. Loading a cache file and rebuilding React on every click would still discard useful work.

## Local source reconciliation comes first

The newest UI branch does not contain all of released 0.1.12. It lacks, among other changes, the release's overview cache and several scoped-read/trace improvements. Local startup `86e395a` descends from the release; managed-library `4a9d247` is separate work based on published main. There is no verified all-combined candidate.

Keep newest local artwork and UI behavior, explicitly integrate the missing release functionality, then reconcile intended startup and managed-library deltas. Do not replace a checkout wholesale because its branch or version label looks newer. Existing runtime files in the UI checkout name older source `ebb257d`; they are not a packaged build of `386e72d`. Measurements below name exact source rather than asserting a latest combined build.

See [branch and owner reconciliation](local-cache-baseline-audit.md).

## Storage plan

Use existing storage where it already solves the problem:

| Owner | Storage | What to keep |
| --- | --- | --- |
| Retained project/destination views | Bounded RAM | Live UI, rendered plots, scroll, focus and in-memory resources |
| Existing desktop DraftStore | Protected versioned JSON in app support | Last view and user input; pending-operation recovery identities under the existing contract |
| Existing metadata index/projection owners | Existing sealed SQLite and source projections | Parsed scientific metadata and verified indexes |
| Proposed persistent resource adapter | One separate `resource-cache.sqlite` per verified physical project namespace in a private local cache root | Selected successful summaries and bounded expensive read results |

Draft files already exist and have a 2 MiB limit, corruption recovery, and schema-based `view-v1` compatibility. Expand their view coverage where necessary; do not introduce a second draft store. Keep unsaved user input outside cache eviction. Existing preferences and tree layouts retain their current owners.

Do not append mutable response tables to the sealed metadata index or serialize the full metadata index again as JSON. The new response store, if implemented, caches only materialized results that the existing indexes do not already provide cheaply. Start with project/protocol summaries demonstrated to repeat expensive work. Add other payload classes only after measuring their cost and hit rate. Raw H5 recordings and the shared managed library are never part of this cache's eviction policy.

A SQLite response store is preferable to one ever-growing JSON file: individual entries can be published, looked up and evicted without rewriting the whole cache. Use the existing Python SQLite runtime; no Electron-native database dependency is needed. The renderer accesses it through the existing authenticated project transport, not arbitrary filesystem access. The private cache root is injectable for isolated tests. Normal restart retains entries; configured eviction or OS cache cleanup may remove disposable entries, causing correct recomputation rather than loss of user state.

## Keep the public interfaces small

This is a proposal, not an existing interface:

```text
ProjectViews.activate(projectBinding, destination)
ProjectViews.close(projectBinding)

Resources.observe(resourceKey) -> last-success snapshot + subscription
Resources.ensure(resourceKey) -> coalesced validation/load
Resources.apply(committedChangeReceipt)
```

The resource module hides RAM/disk lookup, request sharing, publication, dependency invalidation and eviction. UI callers should not implement their own cache files, timers or persistence flags. The persistent adapter is internal to the resource owner. Existing resource-specific authority checks remain at their scientific owners; a generic cache cannot recreate them.

`ProjectViews` owns a bounded live project-document set, using Electron retained views. A project owns a bounded set of stable destination identities. History-entry IDs remain separate: clicking a destination again should not give the same logical view a new component key. React Activity can retain expensive visited subtrees, but its reactivated effects must subscribe to retained resource owners rather than refetch unconditionally.

## Identity and freshness

Persistent keys include:

```text
project UUID + canonical physical project binding + durable state-store incarnation
resource kind + resource-format version
normalized query/sort/page/window parameters
source hashes / protocol or candidate identity
only the revisions that the resource actually depends on
```

Actor identity is included for actor-dependent data. Backend-instance identity gates live connections and publication, but is not the persistent content key for immutable recording samples: otherwise every restart would miss the disk cache. Ports, PIDs, renderer counters, display names and wall-clock ages cannot establish persistent validity.

The durable incarnation (or an equivalent strong generation witness) must also detect replacing/restoring a database at the same path with the same UUID and repeated revision numbers. It is distinct from the process instance. Until that witness exists, persistent mutable summaries cannot be admitted as current using only path/UUID/counter equality.

Store payload, encoded key, dependency revisions, byte size, codec, hash, and timestamps in the same SQLite transaction. Validate identity, format, length and checksum before use. Use application-controlled read/write access and one coordinated writer per cache namespace. A corrupt disposable entry is removed/quarantined and recomputed; a corrupt user draft follows the existing preserve-and-recover flow.

Derive scientific cache compatibility from explicit tested data-format contracts, not unrelated full source-file hashes. The current broad hashes can invalidate projections after edits that do not change the projection representation. Narrowing them requires contract coverage; do not simply remove verification.

## What invalidates what

| Committed change | Update/invalidate | Preserve |
| --- | --- | --- |
| New import published | Source totals/list, affected queries, incoming suggestions, changed field vocabulary | View layout; existing samples; frozen cohort membership |
| Upload progress / duplicate no-op import | Job status/history | Scientific summary/cache generations |
| Tags, review marks or inclusion | Affected overlays and aggregates; dependent tag queries | Recorded waveform samples and unrelated scopes |
| Protocol merge/binding/query edit | That protocol's membership-dependent pages and counts | Other protocols and reusable source payloads |
| Source exclusion/deletion/restoration | Affected policy, counts, queries; prune unavailable IDs | Unrelated sources and view state |
| Export completes | Relevant export status/history/counts | Source metadata and raw samples |
| Navigation, tab switch, focus with no known change | Visibility/focus only | All valid cached resources |

Apply exact values from confirmed mutation receipts when supplied. Otherwise mark the affected resource stale and perform one shared read for visible consumers. Do not infer distinct-cell counts by adding file row counts. Imports do not automatically alter a frozen protocol. Tag decoration changes do not automatically replace frozen search membership.

Replace broad unspecified `changed()` fanout incrementally with these dependency-scoped changes. Preserve a project-scoped external-tag watermark across views: the first monitor response after a remount must not automatically erase all samples. Remove unconditional focus invalidation only when reliable revision reconciliation replaces it.

On the first scan in a new process, compare the saved annotation watermark with the current committed revision. A mismatch or unknown watermark refreshes annotation-dependent resources; it must not be ignored. Raw waveform samples remain independent.

## Restart validation without rebuilding the summary

Restoration proceeds as follows:

1. Read the existing saved view. Late restoration must not override a new user navigation.
2. Establish the physical project/backend binding and show the saved shell.
3. Read a small manifest of committed source, annotation, protocol-binding and history revisions. This proposed manifest must come from already-recorded revisions; computing it must not rerun the project overview.
4. Batch-load only the resources needed for the restored view. Matching revisions reuse the disk results. Same-identity last-good presentation can remain visible while a changed resource is refreshed; it does not assert current scientific authority.
5. Replace only changed values. Edits/exports still require their current authority checks. A changed backend, incompatible schema, absent cache or invalid source falls back through the existing safe loading path.

The bounded manifest/cache-read path must be available from the lightweight project shell before heavy scientific initialization. If an implementation gates it behind the 44-second source/index rebuild observed in SRM, it cannot accelerate the first visible summary. Such an implementation could only claim reuse after backend readiness. Early cached presentation remains separate from declaring scientific data ready.

Revision publication is a prerequisite, not an assumed existing API. Record revisions with the authoritative operation's commit/journal, and update the disposable cache only after confirmation. MySQL/scientific state and a separate SQLite cache are not one atomic transaction: if a crash occurs between them, the committed revision must reveal the stale cache at next read. Losing a cache notification must never make old data permanently look current. Detect missed event sequences/reconnects and reconcile the affected domains.

Do not persist reusable mutation authority, consent, session capabilities, in-flight promises or expired leases. Pending-operation identities already saved for recovery continue to require their existing server reconciliation; restoring them never resubmits an operation by itself.

## Memory, disk and lifecycle

Keep independent limits for live documents, destination subtrees, RAM payload bytes, disk payload bytes and individual entries. Use measured usage to choose final budgets. LRU can evict clean inactive views; preserve or safely checkpoint dirty state first. RAM limits should favor visible demand over speculative prefetch. Disk eviction removes only reconstructable entries.

Hidden views pause optional polling, animation and prefetch. Accepted imports, writes and exports stay owned independently of visibility. App close/quit includes hidden views in existing draft flush and shutdown coordination. Commands, dialogs and IPC stay tied to their sending project, not whichever project is currently visible.

Draft replacement by rename is already atomic at the file-operation level; its current contract does not promise survival of sudden power loss. Any stronger durable-save promise needs explicit fsync/parent-directory handling and fault tests. Disposable cache failures may fall back to RAM; draft-save failures must remain visible and must not report success.

## Evidence and implementation sequence

See [measured timing findings and raw receipts](ui-cache-design-evidence-2026-10-13/timings/timing-findings.md). The diagnostic harness exercises real components against owned synthetic fixtures; it does not prove full desktop switching or restart hydration. The selected trace readiness check is adapted to current controls in an isolated harness and must retain its separate attribution.

Three independent diagnostic runs on newest local UI `386e72d`, each with a 1,000-epoch owned fixture and one ordinary sample per action, gave:

| Action | Median ms | Requests on every sample |
| --- | ---: | ---: |
| Initial main view | 84.7 | 3 |
| Return to main view | 88.4 | 3 |
| Return to prepared Workbench | 113.7 | 3 |
| First owned waveform, complete | 64.4 | 2 |

The important cache finding is repeated work: main return still fetches protocol, epoch page and field catalog; prepared Workbench return still fetches queue, context/page and field catalog. A new waveform's two requests are not automatically waste—its samples must be loaded on first use. The harness does not measure a warm repeat of that trace. These are small-fixture browser development timings, not installed project-switch timings or million-row qualification. See raw samples for variability (the first trace observation was 301.4 ms).

The actual existing DraftStore, tested separately in an owned temporary directory with five synthetic samples per size, loaded/parsed an 87,166-byte snapshot in a median 0.388 ms and an 870,166-byte snapshot in 2.713 ms. OS caches were uncontrolled and likely warm. This establishes that small saved-state files are inexpensive in this diagnostic; it does not establish cold disk, IPC, React hydration or native startup latency. No proposed resource-cache adapter has been implemented or timed yet.

Implement in reviewable steps after source reconciliation:

1. Keep same-resource last-good display and split change dependencies; eliminate annotation-triggered raw-sample invalidation.
2. Retain within-project destinations/tabs and their resource owners. Verify unchanged returns do not recreate completed reads.
3. Retain project documents; adapt hidden-view IPC, drafts, memory and close handling.
4. Persist expensive derived summaries using the cheap committed revision manifest. Hydrate on restart; reuse current draft and metadata stores.
5. Add other disk entries only where measurements show useful reuse, then narrow persistent metadata compatibility with tests.

Acceptance must measure cold open, unchanged warm return, restart hydration, and post-change refresh separately. Count document/subtree mounts, requests, backend rebuilds, bytes and memory, alongside ordinary click-to-correct-result time. Demonstrate no-change return, one tag edit, one import, duplicate import, frozen cohort behavior, memory eviction, corrupt cache, backend restart, cloned UUID, same-path database restore/replacement, first-scan watermark mismatch, missed notifications and hidden pending writes. A future combined implementation requires the repository's core/million-row gates and its own native validation; the present design does not claim a speedup.

External rationale and precise storage caveats: [persistent-cache research](persistent-ui-cache-design-input.md), [frontend retention research](ui-retention-primary-source-research.md), and [Electron/project-view research](project-switching-primary-source-research.md).
