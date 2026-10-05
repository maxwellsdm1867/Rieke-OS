# Recorded cell identity and QC presentation

Start with `ui/CellQC.jsx` for QC navigation and bounded observations; `cellTypes.js`
provides recorded-type/unique-cell policy. `ui/CellListSection.jsx`,
`ui/CellTypeAccordions.jsx` and `ui/CellTypeSummary.jsx` present source cell summaries.
Existing named exports, component props and adjacent CSS remain the public interface.

Recorded UUIDs identify cells even when labels/dates repeat. Type labels remain source
metadata; presentation grouping never retypes a cell. Missing type/value/unit stays
unknown rather than becoming a zero or a fabricated category count. QC plots use
finite recorded observations and preserve recorded units. Bath-temperature pages
remain bounded to 50 observations; opening a selected epoch verifies both its epoch
and cell identity before displaying source details.

QC display/readiness, cell annotations and baseline preparation are separate owners.
Opening or restoring the view grants no approval, inclusion or preparation authority.
Existing route/revision and React effect lifetime fence late reads; loading a new cell
must not publish old-cell data. Error/retry states remain visible. Annotation commands
continue through [annotations](../annotations/AGENTS.md); read transport/cache stays
shared rather than being absorbed by a QC facade.

Deleting recorded cell helpers duplicates UUID/type/deduplication knowledge across
lists, QC and overview. Merging them with the view would make pure summary callers
learn React and remote request lifetime. The folder improves locality; it introduces
no deeper abstraction or smaller capability set. Policy is in-process; React/DOM and
request doubles are local-substitutable/remote-owned adapters. Real scientific QC,
source H5 reads and native preparation remain separately qualified.

Existing mounted public examples remain root tests. From `workspace-app`, after
cross-owner imports are reconciled:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/cellBaselinePreparation.test.js src/cellTemperatureObservations.test.js src/cellQCNavigationLifecycle.test.js
```

They demonstrate actual component readiness and navigation with controlled request
responses. These checks do not perform native baseline preparation or scientific
measurements, and source organization claims no chart-paint or performance result.
