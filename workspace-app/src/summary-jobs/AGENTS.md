# Summary controls and field registry presentation

## Public interface

`ui/SummaryPreferences.jsx`, `ui/SummaryStatus.jsx`, `useFieldRegistry.js` and `useProtocolSummaryPreferences.js` are named public entries.

All existing exports and props remain public. Import the named entry directly; no
barrel, forwarding facade or export demotion is introduced. CSS stays beside its
view. Public entries and styles:

- `ui/SummaryPreferences.jsx`
- `ui/SummaryStatus.jsx`
- `useFieldRegistry.js`
- `useProtocolSummaryPreferences.js`

## Contract and authority

Field registry fallback is allowed only on 404/405 route absence, never generation or validation failure. Invalid field arrays fail visibly. Cleanup aborts requests and suppresses late publication. Summary preferences retain versioned project/protocol/view identity; unavailable identity disables writes and storage failures remain visible.

Despite the historical group name, this folder does not execute summary jobs. KEEP requested-summaries as the submit/poll/cancel and requested-field policy owner; backend computation owns scientific results. Controls and locally stored preferences cannot certify data freshness.

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
node --import ./src/test-support/reactTestEnvironment.js --test src/requested-summaries/requestedSummaries.test.js src/summary-jobs/publicExamples.test.js
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
