# Navigation and startup package

This isolated assembly starts at accepted Disco 0.1.8 plus startup commit
12099185bcb5a76ed303eca5188adee298e88b4e. It incorporates the reviewed right-side
trace UI from b2e7303 and d2fc59f, the preview-tested trace-first navigation and
bounded worker/cache owners from c870e66, and progressive epoch-list scrolling.
The startup App/data activation and desktop ownership remain in place.

The shared Inspector/workbench cell list no longer has a Previous/range/Next
strip. It appends bounded pages on scrolling, retains a keyboard-accessible
Load more fallback, restores saved frontiers sequentially, and reveals keyboard
focus beyond the loaded frontier. Rows retain exact page receipts and ordinals.
Changed query/binding/total, malformed rows and duplicate IDs refuse accumulated
membership with retry. Frozen cohort refresh keeps prior row nodes inert until
new authority is ready. It does not grant curation consent.

The column tree uses full available height and places recorded traces beside
terminal epochs. Optional detailed metadata defaults off, while tags remain
independent. Existing trace buffers are bounded; background workers perform the
unchanged source-verified trace read and must exit before native database cleanup.
Partial scientific activation now closes workers before database cleanup as well.
The broader predicate/split priority scheduler remains a design, not this build.

Source checks include scrolling/membership/keyboard/frozen continuity, optional
metadata and cache lifetime, trace execution, API lock isolation, project shell,
service semantics and desktop close/startup. The original API test's reviewed
fixture AST is unchanged; inserting its encoding concurrency test moves the
reviewed selector from Call:74 to Call:111. Observer and alias owner hashes are
updated without changing their identities or reviewed ASTs. The compatibility
request owner is included; scoped predicate preference UI and imported backend
composition are outside this assembly and are not claimed by its test list.

Final build receipts and test logs are retained beside the isolated checkout in
`epoch-navigation-perf-2026-10-05`. The runtime manifest binds the exact clean
commit and packaged application files. Packaged smoke, relocated native imports,
whole-bundle audit and actual waveform/list UI evidence must refer to those bytes.

This is a local unsigned testing package for Apple silicon, not release promotion.
The host is macOS 27.0.1; macOS 14 runtime behavior and Developer ID/notarization
remain unqualified. A source test or static native audit does not establish them.

## Installed package and main handoff (2026-10-05)

[The local package record](local-package-0.1.8.json) binds the installed 0.1.8
app and ZIP to clean source commit `2060575732d059641129a8d521f978fd5486d0bc`,
including the clipboard fix, Workbench loading update and Arrange tree cleanup below. Its SHA-256 identifies the exact ZIP;
the package and full raw receipts remain in the local kit directory recorded
there. The earlier counts-only ZIP remains published as the [0.1.8 manual testing prerelease](https://github.com/maxwellsdm1867/Rieke-OS/releases/tag/desktop-test-v0.1.8),
with `SHA256SUMS` and the package record attached. The release tag identifies the
packaged source `60f9567`; `7992957` adds the later test/documentation handoff.
No rebuild, stable release promotion or automatic-update descriptor is part of
this publication. The binary is a release asset and is not stored in Git.

GitHub main before this Workbench follow-up was
`a61afb2748a7788696325c0a9940ec85c491b39a`, an ancestor of this source. Startup branch tip `a294c908` has two UI commits
after the shared startup base; their changes are incorporated by `cde28e3`
with the optional-metadata integration retained. This records content inclusion,
not merge ancestry. The tracking commit changes documentation only and does not
relabel the packaged source or benchmark commit.

## Workbench follow-up

Workbench entry no longer waits for the main protocol summary or saved main-tree
layout. Frozen context preparation still owns its scientific readiness. A single
disposable-project observation found preparation dominated entry time; it is not
a comparable baseline or a latency guarantee.

Incoming tree selection uses green Selected / blue Select controls. A branch flip applies
to all verified descendants, with the existing 1,000-epoch limit. Individual child
or epoch changes leave explicit parent switches unchanged; the next parent flip
replaces descendant overrides. Shared-tag coverage is a separate neutral count.
Replacement frozen candidates retain only inert browsing presentation, preserving
tree mode after tagging without copying selections or review consent.
If a refresh interrupts a pending selection, its message survives tree remounts
and asks for an explicit retry. Interrupted work cannot overwrite a later choice.

The cell-count metric opens a compact recorded-type breakdown on hover, keyboard
focus or click. Export preview content uses the available dialog width. Final
source, package and native receipts must identify the later clean candidate;
earlier package evidence does not qualify these changes.

The preceding `7dda900` package validation: 862 frontend tests, the architecture guard, exact clean
core benchmark, relocated scientific imports and 813-file native audit passed.
The unattended packaged smoke verified real descendant selection across pages,
green/blue rendering, automatic tree-mode retention after tagging, cell-type
disclosure and export preview layout, followed by clean shutdown. It did not
merge or export data. The final native run did not encounter selection interruption;
the mounted real-tree remount regression covers its explicit feedback/retry path.


## Workbench loading update

The `ee616dc` package reuses the already verified catalog connection during one
refresh, retains normal admission for a different catalog, initializes tree-layout
storage before recovery captures state, and uses the existing response-local
schema attestation for read-only Workbench requests. Transactional mutation and
backup checks are unchanged. Lazy layout DDL and its recovery triggers previously
changed the native authority after preparation, causing another preparation on
the first return.

An identical five-click controller ran on the same owned 2,041-epoch fixture
with 63 pending epochs. One baseline session and two final-package sessions found:

| Time until branch selection is enabled | Baseline | Final package |
| --- | ---: | ---: |
| Initial entry | 2.552 s | 1.457 s median |
| First return | 2.315 s | 0.333 s median |
| Later returns | 0.593 s median | 0.286 s median |

The final package prepares once across these five entries. The second candidate
session also passed descendant/epoch selection, computed highlight colors,
tagging, tree-mode preservation and export preview, followed by clean shutdown.
Raw receipts, controller copies and comparison limitations are identified in the
package record. These are small-fixture observations, not percentile guarantees
or measurements of the user's live project. No merge or export was published.

The full backend run on `6bae2bf` passed 1,517 tests with 36 opt-in skips, plus 86
owner-module tests. The final catalog-fallback refinement passed 40 scoped tests
with one opt-in skip. The exact clean `ee616dc` core benchmark gate, architecture
checks, 813-file native audit, source/resource verification and relocated scientific
imports passed. Frontend implementation bytes remain unchanged from `7dda900`;
its full frontend result remains attributed to that source.


## Arrange tree card cleanup

The `b0b7dac` package removes both Select and Tag from the Arrange tree level
cards. These cards retain layout controls; selection and tagging remain in the
actual tree columns. The shared selection/tag controls are unchanged.

Independent source review and 12 focused frontend cases passed. The exact clean
core benchmark gate, architecture checks, whole-bundle native audit, resource
verification and relocated imports passed. The installed native UI was checked
for the requested card cleanup. Backend implementation is unchanged from
`ee616dc`; its earlier full native workflow and loading measurements remain
attributed to that source rather than relabeled as this UI-only package.


## Arrange tree overview restoration

The current package restores field value and missing-value counts through the
frozen candidate catalog, with exact revision/filter/split identity. It avoids
fetching the full recursive tree. Counts describe field values, not whole-level
branches or selection membership. Scope changes hide old results immediately;
late responses are rejected by the existing resource owner.

Remove controls now have visible labels. Column headings have no Select/Tag
actions; each branch retains its controls, and its Tag button matches its green
or blue selection background. Saved tag coverage remains separate and neutral.

All 864 frontend tests and independent source review passed. The current clean
core gate, package resource checks, native audit and relocated imports passed.
Earlier loading timings remain attributed to their original source commit.


## Arrange tree summary-control cleanup

The current package removes Metadata summaries, Advanced layout suggestions and
Preferred summaries from Arrange tree in both main and incoming views. Field
counts, matching epoch count, missing-field notices, catalog errors/retry and
Current tags remain. Scoped summary computation retains its existing lifetime.
Eight focused frontend checks and independent source review passed, along with
the exact clean core gate and package checks. Earlier full frontend/native evidence
remains attributed to its original source in the package record.


## Compact tree-level removal

The current package replaces the prominent Remove label with a muted minus-circle
control. Its tooltip and accessible name identify the level; keyboard focus remains
visible. Removal logic and grouping counts are unchanged. Eight focused frontend
checks, independent review and package checks passed.


## Simplified splitter cards

The current package shows splitter names without value-count subtitles on the
Arrange tree cards. The tree totals remain above the columns. Removal icons have
a subtle border. Chooser metadata and exact scoped reads are unchanged. Eight
focused checks and independent source review passed with package checks.


## Frozen column navigation follow-up

Level clicks start immediately; this path has no debounce. Advertised candidate
contexts now request the target and up to eight ancestors in one bounded fresh
response. Existing opening/closing authority checks remain, and the renderer
rejects incomplete or mismatched batches. Candidate cache reuse remains disabled.
The full metadata catalog is requested only when a split chooser is open.
Leaf Tag backgrounds use actual selected UUIDs, matching their epoch rows.

An identical-controller comparison on the owned 2041-epoch fixture with 63 pending
epochs measured median click readiness of 204 ms before and 101 ms after. Opening
the epoch column used four requests before and one after; its three samples were
298/304/311 ms before and 125/200/117 ms after. One session per source, three rounds,
uncontrolled OS caches and no calibrated budget limit this result. The reported
20-second live-project stall was not reproduced or claimed resolved by this test.
The package record links raw receipts and controller hashes.

877 frontend tests, 83 scoped backend tests, independent review, the exact clean
core gate and package checks passed. The current owned native workflow verifies
selection overrides, leaf Tag colors, tagging, retained mode and export preview.


## Terminal epoch column appearance

The final epoch column uses one soft background per row, a leading selection
switch and compact tag/inclusion icons. Removed nested button borders, the blue
left stripe and repeated count text. Recorded epoch labels and separate actions,
accessible names, tooltips and keyboard focus remain. Branch columns are unchanged.

21 scoped frontend checks, independent review, exact clean core gate, bundle
provenance, static native audit and relocated scientific imports passed. The owned
native workflow verifies 38-pixel rows, absent child borders/stripe, blue/green
selection colors, branch and epoch overrides, tagging and export preview.
Historical full-suite and timing results retain their original source attribution.


## Counts-only tree browsing

Paged column and hierarchy views request only per-split group totals and per-group
epoch counts. Full-bucket duration, distinct-cell and tag-coverage scans are skipped.
The UI removes these aggregates and distribution bars; cell groups show epoch counts.
Direct annotations and selection, tagging and inclusion actions remain available.
The representative label renderer retains its existing bounded work and semantics.
Legacy page clients retain full summaries. Cache modes remain separate, and query-tag
previews omit the new presentation flag from their scientific membership scope.

878 frontend tests, 92 scoped backend tests, independent review, exact clean core
gate and packaging checks passed. Owned native checks cover counts-only requests,
absence of aggregate badges, exact saved tags, selection and export preview.
No new latency comparison or full release qualification is claimed.


## End-to-end verification follow-up

Fresh runs against packaged source `60f9567` passed six desktop smoke checks and
the owned Workbench tree workflow. Smoke covers launch, update status, native
project creation, automatic restoration, new backend session and two clean quits.
The stale smoke expectation of a project picker on restart was corrected to the
implemented automatic-restore behavior; project UUID/path and native readiness
checks remain required. The initial failed test receipt is retained locally.

The tree run verified 72 count-only responses, exact saving of tags on 63 epochs,
parent/child/epoch selection overrides, retained tree mode, export preview and
clean shutdown. No export publication or user-project mutation occurred. Raw
receipts and controller hashes are linked from the package record. This remains
local testing evidence, not full release qualification.


## Compact left tree and explicit highlighted selection

The current local package renames the layout action to Edit Tree and keeps it
visible at narrow pane widths. Left browsing branches retain navigation and epoch
counts; group selection and tagging remain in Edit Tree. Compact epoch rows keep
their controls within the row, with explicit Select/Deselect labels in Workbench.

Shift-click highlights a range and Command-click adjusts that set. Highlighting
is independent of selection. The always-visible Select Highlighted and Deselect
Highlighted buttons apply the set explicitly, preserving selection outside it.
Highlight ownership and pending range reads are cleared/fenced across scope and
mode changes, including A-B-A returns. Nothing is persisted as a new annotation.

882 frontend tests, independent review, architecture checks, exact clean core gate,
packaging verification, relocated imports and owned native workflow passed. Native
checks exercise both left tree modes, separate highlight/selection colors, compact
row geometry, downstream selection, saved tagging and export preview. The earlier
six-check smoke receipt remains attributed to source 60f9567. Public prerelease
assets and its tag are unchanged; this is a newer local testing package.


## Stable transient tree status

Updating downstream selection and Refreshing notices use a noninteractive overlay
inside the tree, rather than inserting a layout row. Existing live status text,
readiness gates, disabled controls, errors and cancellation remain unchanged.
34 scoped frontend checks, independent review and the exact clean core gate passed.
Native requests were deliberately held open: header, ancestry and column-strip
geometry stayed identical before/during/after selection and refresh.
Earlier complete selection/tag/export evidence remains attributed to source 4cb8391.
This run checks status geometry only. Broader harness attempts were retained with
their focus/branch-state and interception failures, not counted as passes.


## Quiet status and explicit view count

The count heading now says Current view · N epochs, retaining scoped totals rather
than implying that all displayed epochs are selected for merge. Transient selection
and refresh announcements are visually hidden; counts and layout stay steady.
Screen-reader status, errors and readiness guards remain. 34 scoped tests and
independent review passed. Owned native checks verify the header label, clipped
status geometry and identical tree layout before/during/after both operations.


## Visible pending import notification

Review import now carries a 14px bright red dot with a contrasting border instead
of the small amber indicator. Pending-state authority and dismissal behavior are
unchanged. Three existing notification checks and the exact clean core gate passed;
owned native checks verify the red color, 14px size and border in light/dark themes.


## Exact current selection and stable branch switches

The Edit Tree header now shows a integrated full-width Current selection status row with
selected epochs, unique cells and recorded cell types. Its type breakdown includes
unclassified cells. It follows exact selected UUIDs even outside the visible branch;
pending details occupy fixed slots. The 52px row shares the tree surface and borders,
uses inline counts, and marks current details Live. Updating/paused/unavailable
labels retain the same reserved space; count emphasis respects reduced motion. The bounded read is capped at 1,000 selected
epochs and fails closed on changed frozen metadata or request lifetime.

Selected branch switches retain their committed green/Deselect appearance while
expansion loads. Actions remain disabled until current pages arrive. Scope/owner
changes and errors still invalidate retained appearance.

All 886 frontend checks and 61 scoped backend/recovery checks passed at `2600e40`;
six focused frontend checks passed after the final status-row presentation update, alongside
independent source review and the exact clean core gate. Owned native checks verify
63 selected epochs / 2 cells, 2 epochs / 1 cell after a child is deselected, empty
and pending states, unchanged header/ancestry/column geometry, held expansion, and
light/dark rendering. The initial native harness whitespace assertion was corrected
and rerun without product changes. Earlier broad workflow evidence retains its
original source attribution; this is a local package, not release promotion.


## Tree cards without blue leading edges

Removed both the thick left border and inset blue shadow from selected/open tree
branch cards. Cards retain their normal thin borders, selection colors and controls.
Four existing tree checks and the exact clean core gate passed. Final native
light/dark checks confirm matching 1px side borders, no inset shadow and retained
selection during held expansion. Earlier summary/workflow evidence remains bound
to its original source. Public prerelease assets remain unchanged.


## Responsive incoming selection and column navigation

A bounded branch-selection read now resolves exact UUIDs under one guarded server
request. Ordered Select/Deselect commands remain clickable while waiting; only
validated results update selected UUIDs. Read-only Edit Tree navigation can replace
pending reads, retaining scope/owner/activation checks and scientific action gates.
Focus-producing navigation retains its existing loading gate.

Native comparison on the same owned 63-epoch fixture: ten alternating selection
clicks improved from 395.5 ms median (363–438) to 109.5 ms (97–125), with seven
descendant-page requests replaced by one selection request. This is a 72.3%
reduction for this fixture, not a general performance guarantee. Nine next-column
samples were essentially unchanged: 84 ms versus 86 ms median to visible column;
controls-ready medians were 88 ms versus 92 ms. Navigation now accepts a replacement
destination during a held read, and queued sibling selection completed exactly.
Both runs used separate sessions with the same host, runtime and closed source clone.
Measurement loops match; the candidate controller adds a held-navigation check
after timings. Raw receipts, controllers and comparison JSON are retained in the kit.

890 frontend checks, 62 backend/recovery checks, independent review and the exact
clean core gate passed. Source/frontend/ASAR identity, whole-bundle static audit and
relocated scientific imports passed. Native smoke exited cleanly with no page errors.
Earlier visual and full-workflow evidence retains its original source attribution.
This remains a local testing package; public prerelease assets are unchanged.


## Resolve frozen metadata once per response

Canonical branch selection resolves one metadata projection and emits exact typed
DFS UUID order directly. Column batches share their target projection with ancestor
prefixes. This removes repeated scope construction within a response. Overridden
pagers retain independent reads; closing authority and the 1,000 UUID limit remain.

The [research](epoch-selection-scaling-research.md) and
[comparison](epoch-selection-scaling-results.json) preserve methods and limits.
Three unprofiled samples on identical synthetic workloads showed 1,000 epochs
across 100 cells improving from 3,319.77 to 38.26 ms; selecting 1,000 out of 10,000
improved from 3,500.37 to 359.54 ms. At 50,000 epochs, the baseline selection
exceeded the 15-second diagnostic budget; the candidate completed in 2,024.06 ms
median. The baseline 50k next-column observation was 3,733.77 ms; candidate median
was 2,135.13 ms. Timeout cases have one baseline observation, not three completed
samples. Root-page time is essentially unchanged and still grows with scope size.

These are Flask route diagnostics using SQL doubles and a real SQLite metadata
index, not native/MySQL/paint/H5-import timings. Separate profiling identifies
remaining whole-state and recipe validation cost. Existing annotation-generation
authority does not attest recipe storage; no unsafe recipe memo was introduced.
All disposable fixtures were cleaned; raw receipts, profiles, sealed baseline
source manifest and controller hashes are retained in the local kit.

158 focused backend checks, independent research/design/source review and the
exact clean core gate passed. The final packaged native fixture verified exact
selection, queued clicks and held navigation, with no page errors and clean exit.
Source/frontend/ASAR identity, full static native audit and relocated scientific
imports passed. Public prerelease assets remain unchanged.


## Shared tree metadata reads across presentations

The local package at source `2060575732d059641129a8d521f978fd5486d0bc`
uses the same bounded target/ancestor resolver for main and incoming columns and
hierarchy anchor reveal. Live scope support is advertised by a fresh witness;
all returned pages keep exact path/offset/revision and generation checks. Initial
three-level main reveals can discover support on their first target and fetch
remaining parents together (four reads to two); known-capability reveals use one.
Warm attested ancestor reuse is preserved. Unsupported contexts retain bounded
ordinary reads, and arbitrary multipath restore/range/tag operations keep their
separate contracts. No scientific membership, selection cap or mutation authority
is widened.

[Audit](shared-tree-read-audit.md) and [route results](shared-tree-read-results.json)
retain scope and measurement details. At the exact final source, 50k synthetic
`cell type,metadata/cell/start_time` target-plus-two-parent reads measured
3326.30 ms cold versus 1224.64 ms bundled, with three scope constructions/requests
reduced to one. Repeated medians were 3343.02 and 129.82 ms, benefiting from reuse
of the same server projection; renderer metadata-cache admission remains disabled.
These are three paired Flask/SQLite-index observations with SQL doubles, not
native MySQL/network/paint/H5 throughput. One scope construction still grows with
dataset size. Other layouts and larger metadata values can have different cache
retention and costs.

916 frontend and 144 scoped backend checks, independent design/source review,
architecture guard and the exact clean core benchmark gate passed. The final
packaged owned fixture exercises selection, queued clicks, held navigation and
main/incoming column and hierarchy behavior. Source/frontend/ASAR identity,
static native audit (813 files) and scientific imports passed. Earlier extended
controller attempts stopped at missing focus, a collapsed sidebar folder and a
hash-only route transition; their clean-exit failure receipts are retained. The
corrected controller establishes focus and navigates through ordinary sidebar/tab
UI, including expanding the support section. A separate native metadata-layout
check then exposed missing batching eligibility; that coverage gap was fixed under
independent review before this final package. The installed app restored the
saved Workbench view; its temporary 441-epoch selection was restored through the
visible root switch. Public prerelease assets remain unchanged. This is local testing evidence, not release promotion.
