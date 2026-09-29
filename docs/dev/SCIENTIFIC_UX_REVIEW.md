# Scientific workspace UX review — 2026-09-27

The user requested a UX agent review and concrete adjustments after the first
React implementation. The reviewer inspected the interface code and the verified
1440 × 900 app screenshot. This was a heuristic review, not a study with lab users.
The primary agent implements and checks the resulting changes in the live app.

## Findings and adjustments

1. **Hidden bulk scope could affect the wrong epochs.** Bulk targets survive
   changes in focus, paging and tree view. Make the target count and Clear action
   persistent, label action scope, and restrict a tag removal initiated on the
   focused epoch to that epoch. Focus, bulk targets, inclusion and approval remain
   independent.
2. **Export totals did not predict the actual output.** Show query filters,
   matching cells, included/excluded counts, review-held count and exact eligible
   count. Disable zero-member exports. Explicitly distinguish export query scope
   from the focused cell and bulk-action targets.
3. **Scientific context was buried.** Put cell identity/type, source recording,
   raw group label, recorded solution additions and relevant conditions before
   miscellaneous parameters. Preserve cell/group/block metadata in scoped
   sections. The source's `NBQX5um` group label and `[]` recorded external-solution
   additions are shown separately; neither is rewritten or inferred as a phase.
4. **UUID-only tree leaves obscured trial order.** Number epochs chronologically
   within their source block, retaining UUID identity underneath. Filtering and
   regrouping do not renumber epochs. Show acquisition time beside the ordinal.
5. **Small, low-contrast text and implicit scaling weakened interpretation.**
   Increase scientific labels and control text, strengthen contrast, put units on
   the trace axes and explicitly label automatic scaling for each window. A
   shared/fixed y-range across epochs remains a later comparison feature.

These changes affect presentation and action routing. Acquisition metadata and
raw waveform samples are not modified. New ordinal checks verify chronological
order and stability under filtering; existing scope, review and export tests
continue to apply.


## Verification

The running app was checked at 1440 × 900. VMN displayed the actual block start
`09/24/2026 18:13:30:868072`, followed by epochs 1–10 in acquisition order.
The raw group label and empty solution-additions field remained distinct.
Selecting an epoch for bulk action and switching to the tree retained a visible
scope banner and Clear action. Approved-only export showed 0 eligible and was
disabled; choosing explicit unreviewed inclusion showed 520 eligible without
performing an export. The source context was compacted after visual inspection
so the raw response remained visible in the landscape workspace.

The build, 36 backend tests and two client action-scope regressions pass.
A browser-metadata regression also checks exact large integer timestamps.
No research curation, approval or export was performed during this UX check.


## Follow-up review: raw-first inspector and master log (2026-09-27)

A separate review of the landscape screenshot and current components found three
issues, now adjusted: masks explicitly affect the entire protocol query regardless
of visible cell/filter/bulk targets; the log describes recorded versions and source
fingerprints and limits its transaction claim to curation; next/previous epoch
controls now cross loaded-page boundaries. Browser verification moved 60 → 61 → 60
within the 520-epoch VMN query. Full-rate traces still load only for the focused epoch.
The SQL log's action filter reduced the displayed history to the original import,
and opening an event lazily displayed its stored evidence. Legacy version provenance
is explicitly absent rather than reconstructed from today's code.

The current tests pass: 60 backend tests and two frontend scope regressions. Browser
checks are read-only; no actual scientific tags, inclusion decisions or approvals
were changed. Source data remains 3 cells / 1,086 epochs, all unreviewed. The full
parity inventory is in `WORKFLOW_FUNCTION_PARITY.md`; this review does not claim
MAT/UGM, nested query editing, stimulus display or lab tag-sharing parity.


## Tree builder and optional review (2026-09-27)

The typed CSV splitter has been replaced with an ordered, searchable tree builder.
Field autocomplete discovers actual parameter and condition metadata, displays
sample values/cardinality, preserves field casing and uses bounded results. Presets,
reordering, removal, flat mode and per-level group counts are live. Group branches
and epochs render in batches of 60; matching membership does not change.

Browser checks searched `cutoff`, added it by keyboard, moved it earlier, and
confirmed numeric cutoff groups 25/100/200/400 with 140/260/110/10 epochs, totaling
520. The compact preset selector and pinned preview status leave room for the
result tree. A grouping field name appears above values inside expanded branches.

Following the scientist's correction, review is optional. Included epochs are
exportable by default, tags remain independent, and an optional reviewed-only
filter is explicit. Browser checks verified the default 520-epoch export button
is enabled and reviewed-only is disabled at zero without mutating any data.
Epoch details show the main database/query and exact completed export memberships.
Tests distinguish frozen output members from a broader query snapshot, enforce
project isolation and validate source/metadata revision matches.

Validation: 105 Python tests plus 60 subtests, four frontend tests, production
build and browser checks passed. The UI is using real imported data; no demo
exports or annotations were inserted into the research catalog.

## Tree arrangement and source-first inspection (2026-09-27)

Rieke OS now separates tree arrangement from the existing tree-and-trace inspector.
The arrangement preview shows branch distributions, unique cells and recorded
duration; choosing a terminal group's epoch loads its trace explicitly. Builder
suggestions and presets are compact controls rather than permanent chip banks.
Browser verification traversed date → Single Spot → Cell1 → epoch, displayed the
7,500-sample Amp1 recording with calibrated time/units, and returned to the same
expanded preview path. No source annotations or export records were changed.

The scientist clarified that the acquisition tree remains a useful inspection
interface. The separate arrangement mode does not replace that behavior; tree
serialization is optional. A parallel source audit confirmed Samarjit's filtered
acquisition hierarchy and focused metadata/device lookup as the reuse seam; see
SOURCE_FIRST_WORKFLOW.md for implementation references and adaptation hazards.

Remaining integration work is explicit: arbitrary source metadata/tag predicates,
saving those predicates as new cohorts, and shared source-tag synchronization.
Current protocol-scoped tags and predefined query workspaces do not yet implement
that complete source-first interaction.

Latest validation: 113 Python tests plus 65 subtests, four frontend tests and the
production build passed. Project preview remains metadata-only until inspection;
branch and epoch lists are bounded to avoid mounting every item at once.

## Predicate → proposed update → protocol working dataset (2026-09-27)

The project entry now starts with a typed, nested predicate editor. A protocol's
Advanced predicates action seeds its effective predicate and current cell/group
filters. The tree appears after explicitly recording the candidate. Predicate
changes, tree arrangement and protocol publication have separate visible states.

The scientist clarified that the result must be applied to a protocol's working
dataset. The interface now compares an immutable candidate against that dataset,
then applies with an optimistic version guard. Refresh & compare reruns the saved
predicate and records a proposed revision without changing active membership;
Review update opens that exact candidate with its protocol preselected. Overview,
inspection, masks and exports share the applied UUID set. The original protocol
JSON is identified as a starter query, not the active applied recipe.

Visual review replaced a sentence of counts with a compact comparison strip:
current/proposed cells, epochs and recorded acquisition protocols; signed deltas;
retained/added/removed bars; duration; and an expandable dated cell/type list.
It distinguishes a genuinely new cell from extra epochs in an existing cell.
The comparison collapses while retaining totals and Apply. A global success-box
style collision was corrected so small status chips do not consume 100 pixels of
vertical space. Friendly acquisition-protocol labels accompany exact literals.

Validation evidence:
- A source-file traversal independently identified 370 VMN epochs at cutoffs 100
  or 200. API membership matched every UUID across three tree layouts. Warm
  read-only previews were about 90 ms; the first metadata-catalog build was about
  340 ms on this recording. Browser predicate preview also returned 370/1,086.
- Disposable browser fixtures exercised filter preview, logging, a changed tree
  revision, history restore, compare/apply, protocol overview, and Refresh &
  compare → Review update with the target preselected. A separate +2-cell fixture
  verified the visual deltas, affected cell identities and collapsed layout.
- Six focused HTTP integration tests verify applied membership across tree,
  masks and export; annotations surviving a working-set update; old exports
  remaining byte-identical; stale-write rejection; transaction rollback; and a
  newly added source epoch becoming a proposal before explicit application.
- Full backend suite: 135 tests and 105 subtests passed. Frontend: 10 tests and
  production build passed. No test revisions, protocol bindings, annotations or
  exports were written into the research project; all write QA used disposable
  transactional fixtures. The real project still has zero explorer revisions.

Remaining boundaries: shared source Tags synchronization and full legacy
acquisition-level predicate parity are separate work. Missing source epochs fail
closed and require recovery; the app does not provide source deletion/reconciliation.
