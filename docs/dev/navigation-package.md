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
app and ZIP to clean source commit `b11e3e9538457e29999b179ee9a8d5b2d405da41`,
including the clipboard fix, Workbench loading update and Arrange tree cleanup below. Its SHA-256 identifies the exact ZIP;
the package and full raw receipts remain in the local kit directory recorded
there. The binary is not stored in Git.

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
