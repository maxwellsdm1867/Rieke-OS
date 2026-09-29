# Workspace navigation UX audit

## Findings addressed

- **Leaving a protocol discarded its workspace.** Navigation previously incremented a component key and recreated its filters, tab and selected epoch. App now keeps lightweight per-visit snapshots and a last-visited snapshot per protocol. Back/forward restores the exact visit; selecting a protocol from the sidebar resumes its latest workspace.
- **Back navigation was absent.** Browser history and persistent Back/Forward controls now use explicit local workspace routes. Project, protocol, import, search and cell-QC handoffs preserve their origin. The project breadcrumb is a direct route to the overview.
- **Inspection lost the protocol navigation controls.** A consistent Overview / Inspect / Exports toolbar now remains visible above every protocol view. It names the active protocol and exposes the active-filter count.
- **Exact epoch handoff conflicted with older cached filters.** An explicit search/QC epoch handoff starts inspection at that exact UUID and clears previous presentation filters. Back to the previous history entry restores those earlier filters rather than silently rewriting them.
- **Cell context could be hard to recover.** Cell QC is reachable from source-cell lists, protocol-cell lists and the focused epoch. The QC route carries the cell UUID and optionally an exact epoch UUID; its Back action returns to the prior workspace.

## State and scientific boundaries

Snapshots preserve protocol tab, presentation filters, cell focus, selected epoch UUID, loaded epoch-page offset, tree/list mode, grouping order, tree design path and export settings. Cell QC retains its family, page, selected epoch and metadata visibility per history entry. Source-predicate work retains the unsaved typed draft, name, grouping edits, saved-revision identity and tree focus; the ordinary sidebar Search action resumes that draft, while an explicit new field/value or protocol handoff seeds a fresh workspace. Bulk checkbox targets, unfinished tag text, files selected for mask import, and in-flight operations are deliberately not replayed across navigation. Returning to a workspace performs fresh metadata reads and source/API validation. Explorer cached preview payloads are discarded; a saved recipe may be reevaluated through the read-only preview endpoint, but no revision save or protocol apply is replayed. A request that was in flight when the user left is flagged for checking in Candidate history. No hidden inspectors stay mounted, and navigation does not load waveforms for inactive pages.

The search overlay uses explicit result callbacks. Linked epochs open inspection only in the reported working protocol. Unlinked epochs open read-only cell QC with their exact epoch UUID. A source predicate search opens the predicate workspace with the typed AST, without applying it to a protocol.

## Verification

Pure tests cover route validation, exact per-visit restoration, export recipe reuse versus history restoration, and explicit epoch handoff overriding incompatible cached filters. Production bundle compilation checks the integrated route/component contracts. Native browser QA should verify protocol → QC → Back and protocol → data stores → Back, including a selected epoch beyond the first 60-row page.

## Current limits

Workspace snapshots live in the current app tab's memory; refreshing/restarting the browser restores the route but does not claim to persist an unsaved UI session. Saved queries, tree recipes, curation and exports remain backed by their existing storage. Raw-trace zoom windows and arbitrary page scroll positions are not included in the navigation snapshot. These are presentation limitations, not changes to data membership.
