# Metadata refresh presentation

## Public interface

`ui/MetadataRefresh.jsx` owns the refresh interaction; `metadataRefresh.js` exposes receipt validation and availability wording.

All existing exports and props remain public. Import the named entry directly; no
barrel, forwarding facade or export demotion is introduced. CSS stays beside its
view. Public entries and styles:

- `ui/MetadataRefresh.css`
- `ui/MetadataRefresh.jsx`
- `metadataRefresh.js`

## Contract and authority

Success requires the complete quantitative receipt, finite nonnegative values and valid completion timestamp. Route failures, cancellation and invalid receipts must remain visible. File availability is not checksum verification; changed or missing files must not be described as deleted or scientifically verified.

Refresh work and source authority remain backend responsibilities. Import progress formatting remains with its owner; shared resource lifetime and freshness publication are not transferred here.

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
node --import ./src/test-support/reactTestEnvironment.js --test src/metadata-refresh/metadataRefresh.test.js src/metadataRefreshLifecycle.test.js
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
