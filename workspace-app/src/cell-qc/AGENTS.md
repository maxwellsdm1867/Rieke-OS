# Recorded cell identity and QC presentation

Start with `ui/CellQC.jsx` for QC navigation and bounded observations; `cellTypes.js`
provides recorded-type/unique-cell policy and exact presentation-only icon aliases.
`../components/CellTypeIcon.jsx` consumes those aliases for simple retinal silhouettes;
recorded labels remain unchanged and unknown types retain the neutral fallback. `ui/CellListSection.jsx`,
`ui/CellTypeAccordions.jsx` and `ui/CellTypeSummary.jsx` present source cell summaries.
Existing named exports, component props and adjacent CSS remain the public interface.

Recorded UUIDs identify cells even when labels/dates repeat. Type labels remain source
metadata; presentation grouping never retypes a cell. Missing type/value stays
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

Cell-list rows use desktop columns for cell label, recording date, rig, epochs,
recorded time and exported epochs. Parent type headers and child cells share icon centers and aggregate value columns.
Expanded supplemental facts and right-aligned tags share one compact full-width table.
QC is an independent sibling button available before expanding details: desktop
hover or keyboard focus reveals it at the right, while touch/coarse pointers keep
it visible. Reserved space prevents reveal from moving the row. Native disclosure
and its visible chevron retain keyboard access. QC receives the exact cell UUID
through the existing caller-owned route callback; it neither toggles disclosure
nor reads or prepares QC data. Unknown counts/export coverage remain unavailable.
Recording rig labels use the additive metadata-backed `recording_rigs` and
`recording_rig_missing` display fields; missing rig is Not recorded, multiple
source rigs remain distinguishable, and labels do not change scientific identity.
`overviewPresentation.test.js` checks collapsed-row navigation, both Overview
entries and repeated-label UUIDs; browser fixture evidence checks reveal/layout.

QC's top summary shows recorded source rigs and the sum of all same-cell catalog
epoch durations (unavailable if any duration is missing or invalid). Temperature
keeps its observation drill-down. Optional voltage preparation remains below the
recordings. Non-QC protocols have individual `protocol:<exact recorded name>`
groups; duplicate short labels retain the full name. Legacy `other` paging remains
readable. Restored `other` navigation resets its combined-list offset and resolves
the individual protocol from the preserved selected epoch (or the first available
protocol when no epoch was selected).

QC overview, bounded trial pages and response statistics use the shared 30-second,
entry/byte-bounded response snapshot cache under exact URL and structure revision.
Explicit Cell QC refresh invalidates the cell's entire QC prefix before renewing
reads. Annotation-only changes do not invalidate these annotation-free displays.
Prepared voltage is excluded: the overview requests `projection=display`,
and opening the voltage panel reads its existing integrity-checked endpoint.
Accepted preparation refreshes that panel only. Trace loading proceeds independently
of response statistics; each displayed statistic still requires matching cell and
epoch identity. The legacy overview API defaults to including prepared voltage.

First-open display requests `projection=display`: exact temperature properties,
rigs, durations, family counts and provenance, without unused resistance payloads
or supporting-voltage validation. The full QC API remains available. The bounded
trial request resolves `family=default` independently using the same family order
as the overview; explicit/restored family selection still wins and late reads are
fenced by path/revision. Trial pages request only epoch parameters from the shared
metadata owner. Canonical response lookup verifies both cell and epoch UUIDs
without sorting the whole cell; custom `cell_rows` policy retains its old path.

The Bath temperature tile opens one combined temperature/recording-conditions
panel with recorded group labels, the lazy trend and paginated epoch readings.
There is no separate conditions bar. The tile exposes expanded state and controls
the panel; its close button and the tile both collapse it. Opening uses the existing
bounded temperature-observations endpoint; the closed tile constructs no trend and
loads no observation pages. No preparation command or new endpoint is introduced.

Temperature summaries and trial rows show recorded units (Celsius aliases display
as °C). Values strictly below 25 °C, or the equivalent in recorded °F/K, are red.
Missing readings are Unknown and red. The tile shows only the numeric range or
Unknown, without observation counts or explanatory text. Per the scientist’s acquisition convention, bathTemperature
values without a separate unit field display as Celsius and are not unknown.
Explicit recorded units remain respected; source metadata remains unchanged and inspectable.

The top summary always shows Pipette solution from recorded group `pipetteSolution`,
using Not recorded for missing/null. Internal additions and External additions
are independent conditional cards from `internalSolutionAdditions` and
`externalSolutionAdditions`. Each appears when it has a recorded display value,
including explicit N/A or Unknown. Empty/serialized empty lists do not create cards.
Multiple recorded values remain distinct, and missing groups are disclosed.
Per-field group provenance is available in each card title. The display overview
reads one full detail per source/group alongside inline temperature projection;
no extra endpoint, preparation command or per-epoch ancestor copying is introduced.

Literal NA/N/A/not applicable remains N/A; missing/null remains Not recorded.
Technique and protocol names never synthesize N/A. The observed project catalog
has these three solution fields; no base external solution is inferred.
