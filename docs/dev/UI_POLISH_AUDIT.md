# Scientific UI polish audit

Date: 2026-09-27. This is an implementation and adversarial review record, not a claim of complete accessibility certification or scientific validation. No acquisition records, curation decisions, candidate revisions or dataset bindings were written during this audit.

## Scope and invariants

Reviewed the source predicate → saved candidate → comparison → explicit protocol apply → tree/trace inspection → reference export workflow. Membership predicates, tree grouping, focused epochs, bulk action targets, inclusion decisions and optional review must retain separate meanings. Tree rearrangement must preserve membership. Plots must identify the source/device and physical axes, and must not silently draw stale traces as a newly selected epoch.

## Resolved in this pass

| Finding | Change | Verification |
| --- | --- | --- |
| Secondary labels were 8–10px and pale lavender across overview, export, history and metadata | Added shared foreground/status/focus tokens in `workspace-app/src/styles.css`; raised supporting labels to 11–12px; kept numerical columns tabular and source IDs monospace | Rendered overview, predicate draft and field picker in separate Chrome audit tab at approximately 1420×807; no clipping in those views |
| Different panels used unrelated muted colors; MasterLog referenced undefined `--muted` | Defined a shared muted token and focused overrides without rewriting component layouts | Inspected computed stylesheet ordering; application build succeeds |
| Small status chips could inherit the standalone `.success` alert box | Preserved compact scoped `.badge.success` geometry and applied semantic foreground/background tokens | Rendered source/catalog badges remain inline and compact |
| Metadata helper labeled every block “Source values”, including saved query and export provenance | Removed that unconditional badge; callers can explicitly provide `badgeLabel` when appropriate | Static review of every `Metadata` use; title still identifies context |
| Scalar metadata rendering collapsed JSON null and absent values; empty text looked blank | Display null as `null`, empty string as `"" (empty text)`, and undefined as `Not recorded`; arrays/objects stay inspectable JSON | Static branch review; avoids altering values or scientific interpretation |
| Loading indicator lacked assistive status semantics | Added `role="status"` and decorative icon handling to initial `Status` load | Build plus browser accessibility tree |
| Focus indication and disabled buttons were inconsistent | Shared visible keyboard focus ring and readable disabled opacity; reduced-motion spinner stops | CSS inspection; field picker focus ring visibly retained |
| Diff cell table could clip its minimum columns | Local horizontal scrolling for the comparison cell list rather than shrinking identities/counts illegibly | CSS only; final comparison-layout QA remains with parent |

Source files changed by this audit: `workspace-app/src/styles.css`, `workspace-app/src/components/Common.jsx`, and this document. Other UI components remain owned by the parent and sibling agents.

## Interaction/scientific findings sent to owners

- **Candidate versus protocol apply terminology:** the initial action “Apply & log filter” competes with the later consequential “Apply to protocol” action. Recommended “Save candidate” and “Draft”, with clear evidence that saving a candidate does not move the protocol working dataset. Parent owns wording.
- **Legacy source-protocol handoff:** matching a bound workspace by its original acquisition protocol can open an epoch outside its new dataset. Frontend owner reported excluding bound workspaces from that legacy shortcut; direct candidate Apply is the exact-scope route.
- **Cached results during refresh:** generic `Status` cannot safely insert an extra grid child around every caller. No layout-changing universal refresh wrapper was added. Owners should keep per-panel loading/draft/current state explicit and disable dependent mutations while requests run.
- **Unavailable source epoch reconciliation:** the main resolver fails closed rather than dropping missing IDs. This requires a distinct recovery path if source removal is later supported; immutable imports currently expose no delete workflow. This is not a reason to weaken exact-membership checks.
- **Overview charts:** use unique source-cell identities for dates/types, keep unavailable dates/types explicit, distinguish acquisition protocols from analysis workspaces, and label potentially overlapping workspace coverage. Figure links remain visibly planned until a real indexed artifact relation exists.

## Checks and remaining limits

At the first checkpoint, `npm run build` passed and all 14 available frontend tests passed (curation scope, export policy, typed predicates and reorder contracts). These verify relevant state logic; they are not substitutes for drag/drop, keyboard, screen-reader or scientific waveform validation. No trivial style snapshot tests were added.

Read-only browser checks covered the real local overview and predicate draft/field picker. Parent and sibling agents own end-to-end candidate/apply fixture QA, full trace interactions, hierarchy drag/drop and the new infographic overview. Their later results should be recorded below. Small/mobile layouts and every possible metadata string have not been exhaustively tested. Component CSS still contains legacy literal colors; the targeted shared palette is a bounded consolidation, not a complete stylesheet rewrite.

## Later adversarial review

The new `Overview.jsx`/`overviewModel.js` correctly derives date and type distributions from source cells, not the sum of potentially overlapping protocol datasets. Its coverage bars use the project source-epoch denominator and explicitly state that selections may overlap. Date/type controls filter the cell list only. The rendered real-data overview showed one recording date, three source cells, 1,086 epochs and five protocol workspaces, with no clipping at the audited desktop size. Figure slots remain explicitly planned.

Reported to the parent: summing absent `duration_seconds` as zero would make an unknown/partial recording duration look measured. Preserve measured zero, mark all-missing duration unknown, and label partial sums. This concerns missing-data handling, not the observed real-data duration.

Reviewed drag helpers and handlers: IDs remain unchanged through reordering, invalid drops are no-ops, keyboard move controls remain available, and shortcut organization is local presentation state. Pure reorder tests passed; pointer-drag browser validation is owned by the parent/drag agent.

Reviewed `TraceViewer.jsx` and `traceGeometry.js`: requests are bounded to 20,000 full-rate samples; displayed responses must match epoch, stream, start and count; source values are not resampled; axes identify seconds from stream start and recorded units; Y autoscaling is explicit. Pointer dragging requests a new window only on release. Sent three concrete edge findings to the trace owner: missing-canvas guard on no-response epochs, number formatting that could trim a scientific exponent, and invisible isolated finite samples between missing samples. The owner confirmed the first two fixes; singleton segment rendering was pending at this checkpoint.

The shared text token calculation produced contrast ratios of at least 5.09:1 on the subtle surface for the audited foreground/status palette. This is a targeted palette check, not a claim that all literal component colors or all UI states meet a full accessibility standard.


## Final integration verification

The parent and three parallel agents completed this pass. The duration finding
was resolved conservatively: if any group member has unknown duration, the group
duration is unknown; measured zero remains zero. Singleton finite trace samples
now draw visible points, missing runs remain gaps, and all-missing windows report
that state. New interaction modules are included in audit source fingerprints.

Verified in Chrome on the real local app at a 1420×807 landscape viewport:

- The infographic shows one recording date, three source cells, 1,086 epochs and
  five workspaces. Date clicking sets the cell-list filter and moves focus there.
  Cell types, protocol coverage and planned figure-linking space are visible.
- Trace zoom, actual pointer drag zoom and pan, cursor keyboard movement and
  next-epoch reset worked. Drag zoom changed the window to samples 6895–10875;
  pan preserved its 3,981-sample length. Sample 10,000 at 1 second read −43.3 mV,
  independently verified directly from the original H5 dataset.
- Single local HTTP sample reads took 29.7 ms for 20,000 samples and 4.8 ms for
  3,981 samples. These are observations, not a broad performance guarantee.
- Selection masks disclose the existing controls without occupying the default
  inspection toolbar. No mask, tag, inclusion, review or export was written.
- Actual native HTML drag initially failed in the browser test. Replaced it with
  pointer capture: a 5px threshold, visual-only hover, one commit on release,
  cancellation outside/Escape/pointercancel/blur, and retained keyboard controls.
  Retesting moved Epoch block from level 3 to level 1 while retaining 101 epochs.
- Dragging Variable Mean Noise into Pinned worked and survived page reload.
  This is browser-local presentation state only.
- Predicate keyboard search selected Frequency cutoff with numeric type. A
  read-only equals-100 preview returned 361 of 1,086 source epochs. Candidate
  history remained empty. Candidate saving and protocol application are distinct.

Final checks: all 28 frontend tests, eight audit/provenance backend tests, and the production build pass; `git diff --check` is clean. Browser
inspection covered the changed desktop views, not every screen-reader/mobile
state. The in-app browser debugger became unavailable during this pass, so final
interaction QA used a separate Chrome session. Figures are intentionally planned;
no figure relation, artifact upload or figure editor is claimed.

## Data stores and source lifecycle follow-up

Data stores and Activity & logs are now primary sidebar destinations alongside
Search predicate. H5 registrations use a searchable paged list; details, dataset
connections, source history and full event evidence load on demand. Files &
database remains the managed-directory/diagnostics browser. Add H5 and Import
progress lead to the existing checked import workflow, with a return to stores.

Three parallel agents reviewed and implemented the UI, SQL lifecycle backend and
adversarial source/provenance boundaries. Archive changes active-list visibility
only; freeze blocks registration archival/restoration until unfreezing. Neither
changes source-catalog query membership, protocol curation, saved exports or H5
files. SQL state changes use expected-version checking, an advisory lock and a
transaction containing both state and before/after audit event. Server user
attribution is the default; optional external actor labels are explicitly claims.

Browser verification in Chrome at 1420×807:

- The real `2026-09-24_F.h5` inventory shows 3 cells/1,086 epochs, active/unfrozen,
  its actual recorded import event time, separate filesystem modification time,
  and five linked protocol workspaces. No exports are fabricated.
- Source activity lists exact-source import/protocol-file events. Expanding an
  event fetches the complete SQL evidence, including saved protocol paths.
- Search, Add H5 navigation and View data stores return navigation work.
- A separate disposable in-memory fixture tested freeze → unfreeze → archive →
  restore. Freeze disabled Archive; archive moved the entry out of Active;
  restore returned it. Registration version reached 4, counts stayed unchanged,
  and all four events appeared in both source history and the master log.
- Browser testing found generic audit normalization counting the registration's
  after-state fields as epochs. Fixed by interpreting after-state maps as epochs
  only for curation events; lifecycle log entries now say “1 data store”. Added
  a regression test and verified the corrected visible label.

Final parent checks: 109 unittest tests, 28 frontend tests and production build
pass; diff whitespace check is clean. Focused lifecycle tests cover stale-version
rejection, frozen-state enforcement, malformed/cross-project requests, rollback
on failed audit, accurate attribution and unchanged scientific membership.
Read-only real-data HTTP observations were 42 ms inventory, 33 ms selected detail,
and 6 ms source events; these are single local observations, not scaling claims.
The history index fetches new event payloads in bounded batches and caches compact
attribution; missing historical evidence is reported rather than guessed from a
broad catalog source list. Full events remain lazy. No real data-store lifecycle,
curation or export records were changed during this follow-up.

## Source query eligibility and propagation (current behavior)

This supersedes the earlier manager-only archival behavior above, following the
user's request that removed stores be skipped by subsequent queries. Archive now
excludes source epochs from NEW exploration/predicate results while preserving
raw H5 files and the complete source catalog. Existing working datasets retain
membership until explicit propagation. A new export is blocked while its working
dataset still contains archived source epochs; saved exports remain unchanged.

Data stores now offers Propagate changes: rerun complete saved predicates across
active sources, preview cell/epoch/protocol changes, and apply individual protocol
updates. Candidate creation, binding and their audit events commit atomically.
Source eligibility is included in candidate and export provenance and stale checks.
A project eligibility lock precedes protocol locks for archive/restore and
publication; active catalog caches use the eligibility digest. Registered field
schemas remain available even when all sources are archived, so saved predicates
on dynamic parameters and NOT/empty-ALL rules still produce valid empty results.
Freeze preserves eligibility. Restoration proposes additions even when there are
no current protocol links. Original starter tree paths have an explicit canonical
fallback; original/applied grouping is retained in the revision and preview.

Three-agent adversarial review resolved a real-file blocker: legacy starter trees
used `cell.type` and `cell.start_time`, not current UI field IDs. The canonical
fallback is date/cell/block and does not alter the original starter JSON.

Browser fixture verification: archive retained 2 working epochs but fresh queries
excluded them; new-export button was disabled with a source-update explanation.
The propagation UI displayed −2 cells / −2 epochs, applied an empty dataset version 1,
then restore displayed +2 cells / +2 epochs and applied version 2. Per-source history and
old artifact preservation are covered by API tests. Injected binding-audit failure
rolled back candidate, binding and both new log writes together. Replaying stale
previews is rejected. Source-level metadata does not load waveform samples.

Real-data read-only checks: source summary: 3 cells, 1,086 epochs, 2,646.75 seconds,
64 blocks, 7 groups, 1,551 responses, 1,086 stimuli; five propagation previews all have
zero changes. No real source lifecycle, protocol binding, export or curation
records were written. File overview renders source quantities and protocol/type
bars. Missing durations remain unknown; measured zero remains zero.

Validation: full Python suite: 152 tests and 112 subtests passed, followed by the added
legacy-adaptation persistence test (focused 5/5 propagation tests pass); 28 frontend
tests pass; production build and whitespace checks pass. Historical exports stay
readable. Starter queries still retain their pre-existing live-import behavior
until explicitly bound; exact bound working sets always update through revisions.

## Independent query participation and duplicate-aware import (current behavior)

The user's later clarification supersedes archive-as-query-exclusion above.
Archive/Restore now changes manager-list placement only. Exclude/Include in queries
is a separate control and the only registration flag affecting fresh-query
eligibility. Both preserve ingestion records and raw H5 files; explicit propagation
still changes existing working datasets. Freeze locks both registration controls,
not epoch curation. Query revision hashes ignore visibility-only changes.

A resumable schema migration backfills legacy query_excluded from archived, with
transactional audit events for legacy state rows, preserving previous behavior
without silently re-including sources. The production server was stopped before
migration and restarted successfully. The real source remains visible, included,
unfrozen, version 0; no source lifecycle or scientific dataset rows were changed.

Import jobs now stream a SHA-256 check before parsing, re-fetch SQL registrations
after hashing, and validate that the file did not change during checking. Exact
copies are skipped regardless of filename and retain original references and all
registration settings. Same-name/different-content files receive a warning and
continue to identity validation. Duplicate uploaded staging copies alone can be
removed; external/original files are never removed. Failed validation surfaces the
specific importer reason when available. SQL and local job records retain the
outcome; the UI distinguishes Checking duplicates, Parsing, Already imported and
Failed states without polling completed duplicate jobs forever.

New-SHA ingestion also checks global Cell, EpochGroup, EpochBlock and Epoch UUIDs
in bounded batches before population inside the import lock and transaction.
Exact-SHA idempotence is retained. This does not deduplicate scientific repeat
trials or check stream/animal/preparation UUID sharing semantics. Missing original
H5 references are not automatically relinked by a duplicate attempt.

Browser fixture checks verified that an archived source stayed Included in queries
until explicitly excluded. Importing a renamed identical file displayed “Already
imported · skipped”, produced no parser call/new source, and preserved its archived
and query-excluded state. The real H5 was checked read-only: SHA matched its existing
registration for 219,532,474 bytes. No real import attempt or lifecycle change was made.

Validation: 178 Python tests and 118 subtests, 28 frontend tests, production build and
whitespace checks passed. The real 1420×807 desktop table shows a separate New queries
column and keeps Freeze/Archive under Manage. Fixture server/tab were stopped after
verification; the real Data stores page remains open.

## Project identity and EpicTree handoff — 2026-09-27

Rieke OS is the product; Spike Response Model is the current project. The visible
project name is persisted separately from catalog/storage identity, with an audit
event. Real project rail entries and a keyboard-operable dropdown replace the
single generic project button. Only adjacent validated project manifests appear;
other project contexts run in separate local processes to isolate DataJoint.

The export control now distinguishes JSON analysis handoff from a MATLAB ZIP.
The completed artifact is checksummed as a whole before its SQL revision is
published. Membership and curation checks remain transactional. MATLAB bundles
retain the exact query, UUIDs, tags, metadata and tree grouping; waveforms remain
lazy H5 references. Explicit UGM import belongs under the inspection mask tools,
with a completed-export selector for ambiguous membership matches. A returned
mask updates only its exported subset and preserves other working-epoch decisions.

Native MATLAB R2022a validation passed for a disposable hierarchy/tree, a two-file
same-dataset-path regression, Python→MATLAB→Python UGM interchange, and two actual
VMN epochs from 2026-09-24_F.h5. Actual sample values, units, rates, counts and epoch
UUIDs matched WorkspaceService. Real-recording compatibility files were temporary;
no research export revisions were created for validation. React UI verification
uses the real overview and an isolated disposable HTTP fixture for export/import
mutations. Figure linking remains explicitly planned rather than a working claim.

Final browser check: disposable project exported two epochs through the MATLAB
format selector, exposed the ZIP download, then accepted a reordered two-UUID UGM
without custom provenance. Explicit Apply matched the completed export, displayed
a receipt and changed the intended focused epoch to Excluded while retaining its
saved-export connection. The file chooser alone made no change. The fixture was
stopped afterward. Backend: 220 tests + 131 subtests passed; frontend: 28 tests and
production build passed. Real project remains at zero saved export revisions.

## Predicate rows from supplied UI references — 2026-09-27

Replaced multi-row predicate cards with aligned field/comparison/value rows,
inline add/remove controls, nested All/Any/None headers and optional row details.
Field picker groups recorded metadata into Experiment, Cell, Epoch group/block,
Epoch, Conditions and Protocol settings; searches names and examples. Protocol ID
is a friendly label over the unchanged acquisition-protocol field. Scalar types
come from recorded metadata; numeric inputs retain exact typed predicate values.
None compiles to NOT(ANY), and restored NOT(ALL) remains explicitly Not all.

Source discovery now exposes 139 actual recorded fields, including previously
omitted experiment descriptions and hierarchy timestamps. Existing identities and
metadata fingerprints are preserved. Notes/nulls/empty arrays stay explicit;
absent comments or keywords are not invented. Protocol inclusion is not promoted
to a global source property. Dates use exact calendar values; timestamps preserve
source strings. Preview does not save or apply any working dataset.

Real-browser validation: protocol contains VariableMeanNoiseCurInject AND cutoff
is 25 produced 140 epochs, 2 cells, 1 recording date and 1 protocol. Adding nested
None(group label is Wash) preserved 140 matches and showed the correct NOT(ANY)
JSON. The separate direct preview took 85 ms for this 1086-epoch catalog (one local
measurement, not a general performance guarantee). No research candidate,
curation or export revision was created during this UI check.

Final validation: 222 backend tests + 131 subtests passed; 34 frontend tests and
production build passed. Browser verified the final Protocol ID alias, compact
rows, numeric matching, stale-preview invalidation, and nested None logic. Final
screenshot: `rieke-os-predicate-rows.png` in the session visualization directory.

## Both export handoffs verified end to end — 2026-09-27

Wheeler SQLite is now the default primary export, alongside EpicTree MATLAB.
Reference JSON remains available under Advanced. SQLite is a normalized recording
snapshot with stable UUIDs, source/stream pointers, frozen curation, exact queries,
recipes, SQL examples and schema documentation. Foreign keys and integrity checks
run before atomic artifact publication; completed exports retain the existing SQL
revision/audit transaction. It is a new raw-recording schema, not an alias for the
older Compact/SRM/VMN fitted-result schemas. Waveforms remain external H5 references.

Full real-data temporary validation matched all 520 VMN epoch UUIDs between MAT
and SQLite: 2 cells, 20 blocks, 1,040 streams. All embedded example SQL queries ran;
SQLite integrity/foreign-key checks passed. A separate consumer process read
20 source samples at 10 kHz in mV with exact agreement to the live checked reader,
without connecting to DataJoint. The standalone reader verifies source SHA-256,
metadata/stream identity, sample counts, units and bounds; it supports explicitly
relocated byte-identical H5 files. Checked source tables reject accidental edits.

Actual MATLAB desktop validation opened a visible EpicTreeGUI with 520 epochs and
529 graphical tree nodes, selected an epoch and plotted its 5,000 recorded samples
at 10 kHz. Timestamp/protocol display, units and source-path warnings were fixed
where the runtime check exposed mismatches. Native UGM save/reload matched all
520 UUIDs and preserved the single excluded epoch (519 included). The regression
is saved in tests/test_workspace_matlab_gui.m; proof screenshot is
`epictree-native-vmn.png` in the session visualization directory. The validation
window remains open; all output files were temporary, with no research dataset
revision or curation mutation.

Final verification: 232 Python tests + 139 subtests, 37 frontend tests, production
build and diff whitespace check passed. The real UI shows Wheeler SQLite as the
new-export default and EpicTree MATLAB as the second primary destination.

## Drag-first tree arrangement — 2026-09-27

Tree levels now expose larger grip handles, a visible drag instruction, stronger
insertion markers and a moving-level cue. Mouse users can drag the level label
as well as the handle; touch dragging stays on the handle so the list can scroll.
Up/down buttons are hidden behind Show move controls; Alt+arrow keyboard ordering
and live announcements remain available. Preview recomputes after committed drops,
not during pointer hover. Browser pointer checks moved Cell before Recording date
by its handle, then restored Recording date by dragging its label; the preview
followed both changes while preserving all 520 matching epochs. Production build,
37 frontend tests and whitespace validation passed.

### Protocol-owned exports — 2026-09-27

- Each protocol has a prominent Export action and an Exports tab. EpicTreeGUI and Wheeler SQL database are the two primary destinations; reference JSON remains under Advanced formats for compatibility.
- Protocol export history loads only when Exports opens, via the existing protocol-scoped endpoint. Rows expose downloads, exact format/count/time, provenance and reuse settings. Reuse checks protocol identity and retains the backend's saved-query compatibility check. Repeated reuse reloads settings even for the same saved export.
- Project Export log is an aggregate audit view. Saved queries, UUID membership, masks and artifact formats are unchanged.
- Validation: production React build and all 37 frontend tests pass. Browser verified both destinations, protocol navigation, empty scoped history and retained counts (VMN: 520 epochs, 2 cells). This UI validation did not publish research exports.

### Familiar tree splitting fields — 2026-09-27

The field picker previously opened on automatically varying suggestions, excluding
Epoch group and Epoch block, while exposing internal metadata paths and escaped
source strings. It now opens on Common: recording date, cell, epoch group, epoch
block, acquisition protocol, cell type, group label and block start time (already
used levels are omitted). Protocol settings, suggestions and all metadata remain
searchable. Paths stay in tooltips; source identities and values are unchanged.
A Date → Cell → Epoch group → Block preset is explicit. The picker distinguishes
separate group identities from combining equal group labels. Browser verification
used the 520-epoch VMN cohort; no curation or export was changed. Frontend build
and 40 tests passed.

### Protocol-aware splits and trace-first metadata — 2026-09-27

Read the current VariableHistoryNoiseCurInject protocol/generator and all 101
recorded epochs' metadata. History 1, History 2 and Target are [mean, SD] pairs;
there is no History 3 field. History 1 varies across six pairs, Target across two,
segment duration across two, and History 2 is constant. Three target-only control
epochs retain unused history settings. Suggested layouts therefore separate the
recorded control flag before the history/target settings, and preserve acquisition
blocks. No condition, drug label or delivered stimulus is inferred from a group
label.

The field catalog ranks named scientific axes ahead of bookkeeping/display fields,
reports variation within cells, and keeps constants and technical fields available
for manual selection. Mean-noise suggestions use cutoff, mean, SD and seed mode.
Suggestions do not silently change the tree: the user adds a field or applies a
layout. Exact typed values and UUID membership are unchanged. Pair display labels
preserve full numeric precision and do not infer parameter units from protocol
names (raw stimulus output units are not necessarily parameter display units).

Sources: `retinaSRM/symphony_protocols/+edu/+washington/+riekelab/+chris/+protocols/VariableHistoryNoiseCurInject.m`,
`+stimuli/historyTrialNoiseWaveform.m`, and the current file's metadata. Audit was
read-only. Regression coverage includes meaningful history-pair ranking,
constant/technical-field handling, correlated-but-distinct mean/SD axes, control
labels, full-precision branch labels and unchanged membership.

Inspector completion: raw trace/epoch navigation/curation stay in a separate
center pane; detailed metadata, source/export connections and context use a
collapsible right sidebar with independent scroll. Metadata search expands
matching groups. Relevant varying protocol settings lead, with technical fields
under collapsed Acquisition details. Copy controls provide raw key, API-JSON
value/pair, registered field ID and validated predicate JSON. Unsafe browser
numbers and ambiguous oversized decimal-string predicates are blocked rather
than silently changing source types. API JSON encoding is disclosed.

Browser checks on the real history cohort: scrolling metadata 807 px left trace
bounds unchanged (x546,y462.2265625,w522,h250.1640625 at 1420 px viewport).
Copied parameters/history1Mean yielded {field:"parameters/history1Mean",
operator:"eq",value:200}; metadata collapse/expand preserved trace visibility.
Suggestions showed control epoch, History 1 pair, Target pair and segment duration;
the suggested 8-level tree retained 101 epochs. Final validation: 245 Python tests,
146 subtests and 48 frontend tests passed, production build passed. No research
curation, exports or source data changed during UI validation.

### Shareable tree layouts and native MATLAB parity — 2026-09-27

The tree designer now includes a collapsible EpicTreeGUI code section with a
Copy EpicTree code action. Its one-line `launchWorkspaceTree` call uses the same
ordered semantic field IDs as the current successful preview. Copy is disabled
while that preview is stale or has failed. Every new MAT export also includes
`tree_layout.m` and the helper, so the command is available without clipboard use.
Run from the extracted export directory with EpicTreeGUI on the MATLAB path.
This reconstructs the frozen exported membership; it does not rerun the source
database query. Fields absent from that export's mapping fail explicitly.

The MATLAB adapter validates mappings, epoch values and the adjacent UUID mask,
preserves typed JSON grouping values, and applies the web tree's sibling order.
Missing values remain distinct from null, false and literal placeholder strings.
The native GUI previously treated decimal dots as namespace separators, corrupting
labels such as `[0.0,500.0]` and `1000.0`. Workspace grouping labels now bypass
protocol abbreviation and truncation; genuine protocol namespaces still abbreviate.

Independent audit compared history (101 epochs) and mean noise (520 epochs) trees
against paged query membership, including reversed and flat layouts. No missing
or duplicate epochs were found. Local tree construction measured about 6 ms and
16–22 ms respectively. Warm catalogs were typically 2–3 ms; one first catalog
build was 243 ms. The 520-epoch tree payload is about 190 KB, with duplicated UUID
and leaf information, so this is not evidence of large-cohort scaling.

The actual copied command ran in MATLAB against a temporary real-data bundle:
101 epochs, 27 ordered leaves and exact UUID membership matched the web preview.
The GUI opened and plotted a recorded response. All 71 typed graphical labels
matched their full values, including 23 pair labels and 17 decimal labels.
Proof: `tree_share_validation.json`. No research exports, curation or raw source
files were changed by this verification.

Validation: 248 Python tests plus 154 subtests, 48 frontend tests, nine focused
MATLAB tests, production React build and `git diff --check` passed. Browser checks
verified the rendered command and copy success state. The browser automation
clipboard bridge returned stale contents, so OS clipboard contents were not
independently verified; the same command in `tree_layout.m` was executed in MATLAB.

### Combined settings and one shared protocol tree — 2026-09-27

Added an explicit combined grouping level: epochs share a branch only when every
selected component matches. History 1 + History 2 + Target is available directly,
including History 2 when constant. Other combinations accept 2–6 recorded fields.
Combining replaces those fields' separate levels at their first position; the
result remains one draggable level. The preview renders color-coded component
rows instead of an opaque concatenated label. Suggested history layouts keep the
recorded control flag separate, because control epochs retain unused history
configuration. Grouping never changes inclusion or query membership.

Canonical `joint/` IDs encode component field identities independently. Tuple
values carry a presence flag and exact typed value for each component; missing,
null, false, empty arrays, numbers and strings cannot collide. Unknown, nested,
duplicate and malformed components are rejected. Combination fields stay out of
source predicates and metadata fingerprints. Requested custom combinations are
materialized on demand, not enumerated combinatorially. Export recipes retain
component definitions and the same grouping IDs; MATLAB uses exact tuple strings
and matching sibling order. Its native combined-branch labels are currently the
exact tuple JSON (verbose); the React preview supplies the concise display rows.

Cell clicks now focus epoch navigation and matching branches in the shared
protocol tree. Tree requests/catalogs retain protocol filters and all matching
cells. Explicit saved cell filters remain query filters. Cross-cell selection
clears transient cell focus and bulk targets; curation checks fail closed outside
the focused cell. Later saved-layout hydration synchronizes without an older tree
response overwriting it. Branches/leaves remain bounded and traces load on demand.

Browser verification: Cell1 had 49 navigation epochs and Cell3 had 52, while both
kept the same four-level tree of 101 epochs / two cells. The history combination
had eight distinct tuples and 12 branches across cells/control state. Under Cell1
history sequence, [250,0] / [0,0] / [0,300] and [250,0] / [0,0] / [0,400] were
separate branches (six and one epochs). A custom Cell + Epoch block combination
replaced both separate levels and retained all 101 epochs; the history preset was
restored afterward. No real curation, source or export records were changed.

Independent code audit found no remaining blockers. Validation: 255 Python tests
plus 159 subtests, 55 frontend tests, production build and whitespace checks pass.
Native MATLAB reconstructed 101 epochs, 27 ordered leaves and eight joint tuples
with exact membership and constant History 2 preserved. The tuple occupied one
level, not three hidden levels. Proof: `composite_tree_validation.json`.
