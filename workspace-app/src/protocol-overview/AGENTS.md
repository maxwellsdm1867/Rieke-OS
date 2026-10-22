# Protocol overview and review entry presentation

Select the named entry for the task; there is no overview controller facade:

| Task | Public entries |
| --- | --- |
| Source/summary policy | `protocolOverviewModel.js`, `ui/overviewModel.js` |
| Overview and recorded cell presentation | `ui/Overview.jsx`, `ui/ProtocolInfographic.jsx`, `ui/ProtocolSelectionSummary.jsx`, `ui/SelectionOverview.jsx` |
| Protocol navigation and shortcuts | `ui/ProtocolSidebar.jsx`, `ui/NewPinnedProtocol.jsx` |
| Proposal and comparison presentation | `protocolSuggestions.js`, `ui/ProtocolSuggestion.jsx`, `ui/ProtocolDiff.jsx`, `ui/ProtocolApplyPanel.jsx`, `ui/SourcePropagation.jsx` |

Source cell counts deduplicate exact identities independently of overlapping protocol
cohorts. Recorded types and unclassified cells remain distinct. Source-size summaries
deduplicate shared recordings; missing files/durations are unknown, not zero or a
partial total presented as complete. Typing datasets remain distinguishable from
experimental protocols. Display names and icons do not change canonical keys.

Sidebar preferences and restored navigation do not grant acceptance or new scientific
membership. Proposal review retains exact candidate/query/binding/compatibility fences;
showing a suggestion, count or diff is not applying it. Pending main-versus-incoming
counts use their authoritative responses, never sums of overlapping proposal totals.
The [incoming-workbench owner](../incoming-workbench/AGENTS.md) retains explicit
acceptance/consent choreography; export preparation/publication remain separate.
The Overview match card follows the cumulative queue's mergeable pending counts
and offers Inspect plus the shared one-second Hold to merge all (see "Direct held
recording merge"); it has no click-to-merge or cumulative-preview button. The
infographic Needs review tile counts mergeable pending cells from /workbench/summary.
Review imported data renders the same card per pending protocol from those summary
rows (`importReviewCards`), with the overview protocol row as Main.
Network failure preserves error/retry and already-confirmed partial outcomes rather
than silently treating an uncertain operation as absent.

Deleting summary policy repeats identity/deduplication and unknown-value rules across
views. Deleting suggestion orchestration spreads exact request/receipt knowledge into
presentation. Existing interfaces earn their capabilities; a generic dashboard facade
would couple pure summary callers to protocol mutation lifetime. Co-location improves
locality and progressive discovery, not depth or scientific authority. Summary policy
is in-process; React/UI is local-substitutable; owned reads/commands use existing
request adapters. Backend native membership/transaction evidence stays separate.

From `workspace-app`, run the existing public pure examples:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/overviewModel.test.js src/protocolOverviewModel.test.js src/protocolSuggestions.test.js
```

`overviewPresentation.test.js`, `protocolSelectionSummary.test.js` and retained
workflow tests mount real public components with controlled data after integration
resolves callers. Keep all original assertions. No actual import, scientific
application, native approval or performance qualification is part of this move.

Protocol sections (Pinned, Protocols, Typing & backtracking) collapse independently;
organizing temporarily reveals all sections. Renaming uses the managed manifest's
compare-and-set display-name route and refreshes the app; UUID, query, binding and
frozen membership stay unchanged. Audit failure restores the previous manifest.

A new pinned dataset may explicitly contain multiple acquisition Protocol IDs.
Creation submits every ID from the frozen revision and its recipe hash; multi-ID
creation requires a review checkbox. The destination accepts a nonempty candidate
only when every epoch belongs to its allowed recorded IDs. Overlap alone is never
sufficient. Narrowing still shows removals and requires explicit consent. Direct
candidate export preserves the entire saved selection without creating a binding.
Public mounted checks: `src/protocolSidebarWorkflow.test.js`.

## Overview lifetime and change-driven refresh

`overviewCache.js` and `useOverviewResource.js` retain read-only summaries above
route mounts in the App's project/path lifetime. Ordinary, pinned and typing
protocols use the same owner. A revisit at the same local revision returns the
snapshot without a request. Known structure/import changes refresh only visited
summaries in the background, serially; visible reads coalesce with that work.
Tag/curation changes invalidate hidden summaries without competing with the live
editor; opening one refreshes it. Focus/reconnect revalidate to catch external
changes. Protocol ETags can confirm reuse without rebuilding the summary.

Keys include the caller's presentation scope and complete URL. Custom request
owners bypass this cache. Request replacement, project disposal, errors and
explicit retry preserve publication fences. Twelve entries/eight MiB bound
retention; a currently visible oversized response may render but is evicted on
release. Cached summaries never grant edit/export authority: those operations
continue to obtain independent current receipts. `overviewSwitching.test.js`
mounts the real App/Protocol; `overviewCache.test.js` covers invalidation,
coalescing, late completions, failures and bounded retention.

Protocol infographics use `/protocols/<uuid>/overview` and a separate
`/protocols/<uuid>/recording-sizes` read. Cross-protocol links are intentionally
absent from that overview DTO; missing fields must not be treated as complete
empty membership. Project overview keeps the full project DTO. Linked file-size
reads inspect only relevant registered paths and never request epoch inventory.

Retained Protocol panels keep Overview, Inspect and Workbench state separately. Summary failure exposes `displayData` independently of canonical `data`; App renders that display inert while keeping current authority unavailable. An invalidated unfinished root summary restarts even if its deferred summary revision did not change, preventing startup from remaining empty after simultaneous draft restoration and an annotation scan. `overviewDemand.test.js` covers this race and failed-refresh separation. Native project visibility messages suppress the coalesced internal focus refresh; genuine app focus/reconnect still revalidates. Disk presentation uses a fixed-height quiet status slot and disables Overview callbacks/recording-size requests until canonical data is current.

Project and ordinary protocol overview summaries request a first window of 200
cells. `useOverviewCells` owns later display-only windows separately from the
cached first summary, fenced by response object, project/request owner, path and
revision. Hidden/inert presentations cannot request more. Total cells come from
`cells_total`; type/date and experimental-cell breakdowns explicitly describe
loaded cells until all windows arrive. Exact date/export-participation totals
remain unavailable until complete. Export membership reads retain their separate
full-response authority. See `../pagedOverviewLists.test.js`.

Prepared Overview counts stay authoritative after membership edits while exact
canonical duration folds finish. `duration_seconds: null` with
`duration_status: pending` displays “Preparing…” in the protocol, date, type and
cell summaries; it must not become zero or retain the prior cohort's duration.
Missing duration without the pending marker remains unavailable. Counts and
independent inclusion/review controls retain their existing semantics.


Curation receipts advance the protocol review-card clock even when Inspector
applies them without reloading its pages. Hidden Overview/Workbench queues defer
that read until shown; their merge controls require the renewed queue revision.
Shared tag receipts do not change this clock. Opening the import review dialog
revalidates its cached project queue summary before enabling held merges.
`workspaceChangesLedger.test.js` mounts the real suggestion card to verify
curation -> hidden reads remain quiet -> reveal -> fresh held merge;
`importReviewDialog.test.js` covers reopening and pending renewal.

A verified Undo retires the merge-card suppression for that project/protocol.
Only fresh queue membership supplies the restored banner/counts; an undo alone
does not invent pending epochs. The same pre-merge queue revision may return, so
revision equality alone cannot suppress the card after Undo.
`protocolSuggestionHold.test.js` covers merge -> empty -> Undo -> restored original
queue -> merge again, plus unrelated-protocol isolation.


### Finish reviewing (2026-10-21)

The cumulative pending card also offers Finish reviewing. Opening confirmation
writes nothing; confirming leaves out the displayed queue's remaining epochs via
fresh preparation and the guarded Finish endpoint. Queue replacement retires
confirmation. Verified completion publishes the shared Undo notice and invalidates
Overview/Workbench. Undo reopens only the completed pending review; it does not
remove earlier Main merges. The same control is used in import review.

Overview and Import Review render the same ProtocolSuggestion card and issue the
same held merge-all request. A confirmed merge stays on the current route; only
Inspect in Workbench navigates. Import Review closes after confirmed Merge or
Finish reviewing so the App-owned Undo notice is immediately usable. Failures
keep review open. Its native modal uses the shared retained-visibility lifecycle,
including cleanup when a busy retained route becomes hidden. Finish reviewing
uses FinishReviewConfirmation in both cards and prepared Workbench; queue versus
prepared-candidate command fences remain owned by their existing controllers.

Delayed project-wide prefetch visits only still-invalidated summaries. A visible
owner that already refreshed (or is reading) with its own revision clock wins;
background prefetch must not replace that clock or make the fresh view inert.
The cache and actual-App overview switching tests cover the delayed startup path.

Action failures appear once: the card does not duplicate a failure already reported
by its command owner. Local notifications are dismissible, expire after eight
seconds, and retire when their queue/candidate owner changes. Notification expiry
never retries a command or changes recovery authority; uncertain-operation
recovery remains owned by the command controller.

An active Overview renews an invalidated cache entry even when it retains display
data and its descriptor revision has not changed. Otherwise aborting the old read
can leave the page permanently inert at Updating. Hidden consumers remain quiet;
activation renews their invalidated demand. `overviewDemand.test.js` covers populated
same-descriptor invalidation, superseded replies and hidden/visible transitions.
The App shell keeps root-summary initial/unfinished demand active off the Overview
page, but passes `renewRetained:false` there to defer invalidation of a populated
root snapshot. Returning to Overview renews it; changed descriptor revisions still
read normally. Protocol summaries retain visible renewal. This preserves the
external-annotation no-unrelated-summary-read contract in `workflowResponsiveness.test.js`.
