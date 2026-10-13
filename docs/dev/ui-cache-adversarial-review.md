# Adversarial review: retained views and persistent read caches

2026-10-13. Reviewed design and baseline audit against local UI `386e72d` in `codex/ui-cache-design`. No app changes or benchmarks. This review agrees with the direction, but not an implementation that treats the proposed revision manifest, destination identity, or Electron view registry as existing infrastructure.

## Blocking decisions, scoped to the affected implementation step

### 1. Establish one integrated source before changing behavior

The UI branch lacks released owners that this design proposes to adapt. Integrating by copying a directory or cherry-picking the release-to-UI aggregate diff risks losing artwork and scientific fixes. Record merge base, intended commits and conflict decisions for release, UI, startup and managed-library work; preserve original branches. Inspect the final implementations and tests for overview, trace admission, Workbench scoped reads, startup discovery and recording ownership. Do not duplicate release caches on the UI baseline and merge them afterward. This is a blocker for application implementation, not for continuing review.

### 2. Define destination identity separately for each route kind

`App.jsx` keys Protocol, DataStores, CellQC and MetadataExplorer from `route.key`; Explorer also uses that visit key as its undo scope. Replacing all keys with page/protocol identity would conflate distinct searches, clear or share undo unexpectedly, and ignore later navigation parameters. A retained protocol is reusable, but a new inspection request still needs to update selected epoch and navigation intent. Multiple search drafts may legitimately be different destinations.

Agree on a small route table: identity, update-on-activation inputs, history snapshot semantics, draft ownership and eviction behavior. Test back/forward to two different searches and two different epoch inspections, plus deliberate new search and merge/export recovery intent. No retained-view effect may replay a mutation or old consent.

### 3. Retained desktop views require authenticated content ownership, not just a view map

`desktop/security.cjs:validateSender` finds `event.sender` only through each registered window's `webContents`. `main.cjs` uses those window objects for draft scope, dialogs, permission admission, downloads, recovery and broadcasts; DraftBarrier ties acknowledgements to the precise window object. A WebContentsView does not automatically become a valid sender by being attached to a window.

Specify one registry of retained scientific content with immutable project/backend binding and separate host-window association. Adapt admission, main-frame checks, origin checks, clipboard focus, downloads, dialogs, draft acknowledgements and active command routing together. Tests must reject a hidden A sender claiming B, a subframe, retired content, reused backend port and late A reply after B activation. Hiding is not revocation of legitimate draft flush, while hidden content must not acquire focused clipboard/command authority. Recovery should identify the failed view rather than silently misattribute failure to the visible project.

### 4. Hidden autosave must not change the next-start project

Every successful `desktop:save-draft` currently invokes `startupSession.remember(record.project_uuid, record.project_path, route.page)`. Retaining several App documents retains several three-second autosave owners. Hidden A saving after visible B would make restart open A. Move last-active-project recording to confirmed activation, or gate that startup preference update by active retained content while still saving all drafts. Cover A→B, late A save, quit and restart. This is a concrete existing-code regression unless handled.

### 5. Name authoritative manifest sources and close the response-publication race

The proposal identifies needed revision domains but no executable mapping of domain to durable owner, commit site, external mutation detection and lightweight read location. A timestamp or renderer counter is insufficient. Before persistent *current* summaries, document that mapping for the first payload class only. Reads must bind payload to the revisions of the actual read: use a consistent snapshot or a before/read/after equality check and reject racing publication. Merely recording the latest revision next to an older response can bless stale content forever.

Also specify missing-domain behavior, notification sequence gaps, reconnect, duplicate events, late responses and writer coordination across two backends for the same physical project. Conservative stale/read fallback is valid. Do not build a universal revision service before one narrow summary proves useful.

### 6. An incarnation stored inside the backed-up database does not detect restoring that database

A same-path restore can restore UUID, incarnation and all counters together. A random identifier minted once and backed up with state does not solve the design's stated case. Choose a verifiable restore/replacement witness, content-derived committed state identity, or conservative restart revalidation before mutable results become current. State explicitly which external replacement paths are detected. Immutable samples can use verified source identity independently. This blocks persistent mutable authority admission, not last-good presentation or live retention.

### 7. Early restart presentation needs an actual lightweight serving path

The existing `projectReady && !dataReady` App branch shows ProjectWelcome rather than normal summary routes. Returning a cached summary from a route gated on full scientific initialization will not fix the observed long first display. Specify where the shell obtains cached presentation and compatibility before heavy initialization, and how freshness/readiness remains visibly distinct without layout churn. A last-good view must not enable exports, edits or selection operations against unvalidated scope. If this path is deferred, explicitly limit the claim to reuse after backend readiness; do not call it restart hydration acceleration.

### 8. Eviction must be a successful checkpoint transition

A saved tab snapshot is not yet proof that filters, scroll, zoom, draft inputs and pending-operation identity can survive destroying that destination. Enumerate retained state coverage and maximum serialized size. If an aggregate project draft exceeds the existing 2 MiB cap or save fails, refuse clean eviction and surface recovery; do not silently evict dirty state to honor a hard count. Set an initial deterministic live-document and destination cap, with visible/dirty/pending-write pinning, before rollout; later tune from measured memory. Apply existing strict replacement versus bounded explicit Quit to every retained content owner, including crashed hidden content.

## Nonblocking scope corrections

- Keep last-success display identity separate from authority/freshness. In `visibleResourceState`, matching only a URL is unsafe across transport rebinding, actor change or source replacement. Stale display is allowed only within verified project/resource identity; consumers need freshness status to preserve existing action gates.
- Do not require disk waveform caching, index hash narrowing or perfect field-level invalidation in the first delivery. Existing source/index owners already solve much of persistence. Start with one measured expensive summary and conservative domain invalidation.
- A trace TTL removal needs bounded byte eviction and source identity checks; TTL is not evidence of stale immutable samples, but unlimited retention is not a replacement.
- React Activity tears down effects while hidden. Keep accepted operation and recovery owners above the visibility boundary; pause optional polling explicitly. Retaining DOM alone does not retain request lifetime.
- SQLite transaction/checksum/corruption handling is appropriate. Disk-full, locked database and unavailable cache root should fall back to ordinary reads without blocking scientific writes; draft failures retain their stronger behavior.
- Source exclusion can preserve raw bytes in a cache, but current visibility/access policy must still deny their use. Removal/restoration is not merely a visual-decoration update.

## Smallest viable correct sequence

1. Produce and record the combined candidate. Update adopted architecture contracts for intentional lifetime/interface changes as each owner is modified.
2. Adapt existing release read owners: identity-fenced last-good display, shared completed reads, annotation/raw-sample separation and conservative domain invalidation. Add race and stale-action tests.
3. Retain a bounded set of within-project destinations using the route table. Keep draft, mutation and recovery ownership outside optional hidden work. Prove navigation and eviction recovery before desktop retention.
4. Add retained project contents with the complete security/lifecycle registry and active-project restoration correction. Prove A→B→A, hidden writes, failed flush, crash and strict replacement/explicit Quit behavior.
5. Implement the narrow authoritative revision mapping and consistent publication contract for one summary. Implement its bounded disposable disk adapter and explicit early-shell hydration path. An absent reliable witness yields stale presentation/recompute, never current admission.
6. Measure and expand only when results justify it. Keep metadata compatibility narrowing and additional payload classes independent follow-ups.

## Criteria for agreement and qualification

Review agreement requires explicit resolutions of items 1–8 in the design or step-specific implementation contract. Routine resolutions do not require another human approval. Agreement authorizes the reviewed sequence; it is not qualification of unimplemented behavior.

Behavioral gates: unchanged return does not remount or re-read completed resources; first request for a new scope still works; tag edit changes decoration/counts without sample reads; one import refreshes affected totals without changing frozen membership; duplicate import does not invalidate scientific generations. Include stale response after change, missed event/reconnect, actor switch, cloned UUID at different root, same-path restore, first-scan watermark mismatch, hidden pending writes, two-project late draft saves, oversized draft, cache corruption and disk failure.

Benchmark gates: bind all evidence to the exact combined source and fixture; separately measure cold open, unchanged destination return, A→B→A, process restart hydration and post-mutation correctness. Record ordinary elapsed action latency alongside document/component mounts, API requests, backend rebuilds, memory across repeated visits and disk bytes. Run required core and actual-million repository gates on the candidate; follow with native desktop evidence in isolated projects. Existing browser and draft-file diagnostics do not establish retained native view behavior, restart latency or a speedup. Do not modify original scientific projects or managed H5 data for these checks.

## Review agreement on narrowed implementation

Reviewed `ui-cache-review-resolutions.md` on 2026-10-13. Agree to its scoped sequence; no remaining design blocker before source integration. A presentation-only restart overview, with one mandatory canonical current read after verification, resolves the manifest/restore-witness objections for this delivery. It does not claim reuse of mutable disk results as current authority or elimination of cold scientific initialization.

Implementation acceptance details: use an explicit presentation-field serialization allowlist; mark saved/updating presentation quietly without layout movement; gate every scientific action path (including callbacks and keyboard commands) until current readiness; verify physical project namespace before serving the snapshot. The source integration checkpoint and behavioral/native qualification remain required. This agreement authorizes the reviewed implementation sequence, not release promotion or a performance claim.
