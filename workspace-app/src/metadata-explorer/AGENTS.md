# Metadata exploration presentation

## Public interface

`ui/MetadataExplorer.jsx` owns exploration composition; `ui/QueryPresetDialog.jsx` and `ui/QueryPresetHistory.jsx` expose preset interactions. `explorerScope.js` and `searchInclusion.js` retain their named pure interfaces.

All existing exports and props remain public. Import the named entry directly; no
barrel, forwarding facade or export demotion is introduced. CSS stays beside its
view. Public entries and styles:

- `ui/MetadataExplorer.css`
- `ui/MetadataExplorer.jsx`
- `ui/QueryPresetDialog.jsx`
- `ui/QueryPresetHistory.jsx`
- `explorerScope.js`
- `searchInclusion.js`

## Contract and authority

A focused UUID requires an explicit matching membership result. Pending, invalid, error, included and excluded are distinct states. Preserve typed predicates, source scope, exact preset receipt identity, inclusion exclusions and explicit action-time validation.

Typed-query editors, project preset storage, export execution, summary execution, cached reads and scientific membership remain their existing owners. This folder consumes those public entries without creating authority.

Statistics are not part of building or previewing a query: every preview, run and
revision request sends `catalog_summary: false`, and there is no explicit
full-catalog mode. Once a query's results are shown (results or tree step), the
explorer submits one requested-summaries job for that result set over the
registered tree fields and passes the decorated fields to the tree builder
(`summaryEnabled: false`, so the builder starts no job of its own). The job stays
while the same query only reloads its tree (layout, focus); a changed predicate,
view filter or registry generation retires it, and a new job starts only after
the new results load. `Result statistics` status shows pending/cancel/retry.
Ledger tests: `requested-summaries/requestedSummariesLifecycle.test.js` (running a
query sends exactly one job; a changed query cancels and resubmits once).

## Factoring decision

These files share a presentation responsibility and change locality. Pure helpers
are in-process; React and storage lifetimes are local-substitutable. Existing
remote reads use the existing adapter and test stand-ins. No new hypothetical
seam is introduced. Deleting a helper would spread its identity, bounds or
presentation rules across callers; moving it beside those callers improves
discovery. This is physical organization, not a claim of new behavioral depth.

## Executable public examples

From `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/metadata-explorer/explorerScope.test.js src/metadata-explorer/searchInclusion.test.js
```

Existing examples exercise the same named interfaces as callers. Cross-owner
lifetime tests stay at their existing paths where their composition belongs.
Run scoped tests after coordinating the frontend test lane. These checks do not
qualify browser paint, native reads, HTTP deployment or scientific results.

## Maintenance

Read this guide and the relevant named entry before editing. Preserve ordering,
identity, error, cancellation and lifetime contracts. Authority or runtime body
changes require independent review before implementation. The integration owner
maintains the shared catalog, ledger, path companion and root navigation; source
proof and coordinated integration checks bind this mechanical relocation.

Trace viewing preferences belong to the Explorer session, separately from matching
navigation. Filter/search/preset changes may clear navigation without resetting
Whole/Sample or the user’s sample bounds. Both result and tree layouts pass the
same controlled preference into MatchingEpochs. Restored preferences are validated
by the trace presentation owner and never restore read or mutation authority.

Successful initial candidate hydration is keyed by initial revision and explicit retry. Activity reveal cannot reapply the immutable recipe over later draft/name edits. Current preview reads still refresh through their existing authority owner; aborted or failed initial hydration remains retryable.
