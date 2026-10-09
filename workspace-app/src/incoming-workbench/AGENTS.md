# Incoming workbench

Start with `ui/IncomingWorkbench.jsx` for queue presentation and
`ui/FrozenIncomingReview.jsx` / `ui/CumulativeIncomingReview.jsx` for review.
`useWorkbenchQueue.js` owns queue loading/paging; `incomingSelection.js` owns
complete ordered frozen selection. The small public UI entries render cell types,
review decisions, merge preview, selection controls and tag summaries. Their
matching named policy files retain the current callable interfaces.

## Read, command and consent owners

Queue/read presentation (`useWorkbenchQueue.js`, `incomingSelection.js`, and the
review UI) does not acquire acceptance authority by sharing this folder.
`workbenchAuthority.js` retains explicit versioned draft/preview/accept choreography;
`selectedIncomingWorkflow.js` composes selected decisions through it.
`incomingReview.js` retains proposal acceptance and export helpers.
`incomingMergeIntent.js` and `useIncomingMergeIntent.js` retain ephemeral single-use
consent; App routing issues and consumes intent. A saved view is inert and cannot
reconstruct that consent. Backend transactions and replay remain authoritative.

Queue candidates deduplicate exact UUIDs within one queue revision. Protocol,
project, candidate scope revision, draft version, queue revision and one-shot request
UUID remain distinct. Explicit contract v1/capability checks and safe nonnegative
counts remain mandatory; null counts mean unavailable. Frozen selection traverses
60-row pages in scoped cell order. Current capable Workbench selections have no fixed epoch-count ceiling. Main cell totals,
partial pages, duplicates, wrong-cell rows or changed revisions cannot substitute
for exact scoped membership. Counts do not sum overlapping proposal totals.

Preserve abort signals plus generation/isCurrent publication fences on refresh,
paging, scope changes and unmount. Retained data may display inert after failure;
closing a review proves no rollback. UI labels never create recorded identities.

## Entry readiness

App mounts Workbench independently of the main protocol summary and main tree
layout. Incoming queue negotiation, preparation and fresh candidate context still
gate the frozen browser. A pending or failed main summary cannot block incoming
queue loading; main Inspect and protocol export retain their own readiness gates.
Workbench does not request a filtered main summary for retained browsing filters.
`workbenchRouteRendering.test.js` holds or rejects the main summary and verifies
this separation without connecting to a user project. It is ordering/correctness
evidence, not a measured native latency improvement.

When cumulative preparation replaces its frozen candidate, a previously absent
viewer may inherit only tree/list/design mode, focused UUID/cell and offset hints
from the same mounted project/protocol. Current candidate context/pages still
load before actions become available. Existing destination viewer state takes
precedence. Selected epochs, operation/preview/receipt/export state and unfinished
tag text stay with the old candidate. Revision-bound tree paths/pages/scroll are
not transferred to a different candidate; same-candidate restoration is unchanged.
The mounted `workbenchSessionLifecycle.test.js` covers pending preparation,
fresh context, absence of carried consent/edit state and project/protocol fences.

Fresh preparation responses may supply the first frozen context without another
GET only when their response header is `X-Disco-Workbench-Context: fresh-v1`.
The retained `api.js` request adapter supports an optional `onResponse` callback
with `{status, headers}` after successful JSON decoding; the callback is excluded
from fetch options and does not alter the returned body. Error or undecodable
responses never publish this metadata.

Cumulative review holds the context offer separately from all saved session,
prepared, scope and receipt data. It requires the current project, protocol,
queue and revision plus a resolved profile matching the response actor. A frozen
child claims an offer once; StrictMode effect replay may keep that child's claim,
but a true child remount, restored session, receipt replay, recovery or refresh
uses GET. Profile/loading/error and other owner transitions mask old context
before effects and reject late A-B-A responses. An ordinary fresh GET retains the
existing server-context fallback when optional profile UI is unavailable.
Late draft/preview completions cannot overwrite a replacement owner's context,
clear it through an old error, or publish a preview under the new owner. Already
submitted writes and acceptance receipts/recovery identities retain their existing
commit and uncertain-outcome semantics; no rollback or automatic retry is implied.
Bounded pages and scientific commands retain their independent current-scope
checks. `incomingWorkbenchStrictMode.test.js` covers this response/lifetime
handoff; it does not grant native storage or measured performance qualification.

## Factoring decision

Pure selection/count/review policy is in-process; queue and scientific commands use
remote but owned endpoints through existing request adapters. Tests inject owned
request stand-ins and mount actual UI/hook lifetimes. The deletion test favors KEEP
for existing authority and consent entries: flattening them into the UI spreads
version/replay rules, while one generic workbench facade makes read callers learn
acceptance and consent preconditions. Multiple entries preserve clear responsibilities
and needed capabilities. Co-location improves locality without claiming new depth.

From `workspace-app`, run executable public examples and retained composition:

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/incoming-workbench/*.test.js src/incomingReviewDecision.test.js src/incomingSelectionRendering.test.js src/incomingWorkbenchRendering.test.js src/incomingWorkbenchStrictMode.test.js src/workbenchSessionLifecycle.test.js src/workbenchRouteRendering.test.js src/incomingAuthorityRecovery.test.js
```

Selection examples demonstrate complete paging and all-or-nothing refusal; authority
examples exercise versioned payloads and separate acceptance/export behavior.
Mounted examples preserve real controls, StrictMode lifetime and inert restoration.
Ledger: `incoming-read-presentation`; scientific command record
`frozen-workbench-review` retains its separate authority.

## Maintenance and evidence

Use the named file entries directly; there is no barrel, compatibility forwarding
module, or newly private export. The interface includes accepted types, identity,
ordering, freshness, errors and lifetime; a lower export count is not the goal.
The executable examples above use the same public seam as callers. Preserve the
original tests; this organization does not replace them with implementation tests.

Read this guide and the relevant entry before editing. Agree on changes to
scientific meaning, authority, request identity or lifetime before implementation.
Keep local changes within those contracts, run the scoped examples and retained
composition tests, and obtain independent source review. The integration owner
updates the existing catalog, ledger and path companion and runs the coordinated
import/build checks. Benchmark links in the ledger are historical/indirect;
relocation establishes neither new performance nor native qualification. Browser
layout/paint, native data reads and full backend qualification remain separate.

## Binary tree selection commands

`incomingSelection.js` holds the pure scoped branch-command policy; the tree hook
verifies complete current descendant IDs through `resolveTreeGroup` before any
selection change. Branch color is the nearest explicit on/off command, not child
coverage. A child or epoch can be off while its parent remains on; flipping the
parent overwrites all downstream commands and selected UUIDs. Complete membership, partial-page, duplicate, cancellation and final-revision checks remain mandatory.
Inspector owns ephemeral branch commands shared by column/hierarchy presentations.
They are not persisted in sessions and never replace selected UUIDs for merge/export.
Global selection tools send explicit root-command metadata only after successful
selection; individual epoch updates leave ancestor commands intact. Saved tags use
separate neutral badges and convey neither selection nor merge approval.

If a mounted tree refresh/availability change interrupts a branch selection, retire
the request and show explicit retry feedback. Never replay it automatically or let
its late response overwrite a newer command; unmount cleanup does not publish UI.

Inspector owns interruption feedback outside the retained tree subtree, with a
dedicated mount-only guard. Scope eviction may remount PagedTree without losing
that alert. A new explicit branch/global command clears it; parent unmount ignores
child cleanup notifications. Standalone tree callers retain local feedback.


Incoming left browsing uses optional ephemeral highlighted UUIDs separate from
selected UUIDs. Plain/Command/Shift gestures affect highlights through existing
bounded range readers and freshness fences. The top selection toolbar has one
counted highlight action: Select Highlighted unions this set; when every highlighted
UUID is selected, Deselect Highlighted subtracts it, without imposing a Workbench selection-count ceiling.
The action is disabled for an empty set or while selection authority is unavailable.
Candidate/query/revision/split or presentation changes mask old highlights before
paint; highlights are not persisted and never imply merge/export consent.
Left browsing suppresses branch actions; Edit Tree keeps group controls. Individual
epoch switches retain actual selection and show Select/Deselect action labels.

Current selection uses selected UUIDs, independently of visible tree paths.
`incomingSelectionSummary.js` validates bounded exact receipts;
`ui/IncomingSelectionSummary.jsx` owns the abortable candidate/binding/owner and
pause-transition lifetime. The 52px status row marks verified selection counts Live and shows selected epochs, unique
cells and recorded types; unclassified cells stay in the breakdown. Pending/error
receipts never borrow old counts. `incomingSelectionSummaryRendering.test.js`
covers first-paint pause/resume and A-B-A retirement. This is read presentation,
not a new selection or merge/export authority.

Branch selection uses `incomingTreeSelection.js`: capable frozen contexts resolve
exact ordered UUIDs in one guarded read; older contexts retain verified paging.
`IncomingTreeSelection` accepts up to 32 queued explicit commands. Desired on/off
comes from projected command intent; UUIDs and committed colors change only after
verification. Following commands wait for both prior selection and intent commits.
Failure, scope/owner change, external selection/intent changes and unmount retire
dependent commands. Stale A-B-A handlers cannot enqueue. Other branch switches
remain clickable; pending controls show Selecting/Deselecting and aria-busy.
Authority-disabled checks remain; older services retain their advertised finite selection limits. Queue and stale-lifetime examples
are in `incomingTreeSelectionQueue.test.js`.

Epoch Select/Deselect switches also accept Shift-click: the first ordinary switch
click establishes an anchor, and Shift-click applies the target switch's direction
to the complete range. Column/hierarchy ranges stay inside one branch; the cell
list supports its existing ordered cross-cell range reader. Plain switch clicks
accumulate independent targets. Switch gestures change actual selected UUIDs,
not highlights or trace focus; label gestures retain their separate highlight
store. Scope retirement, concurrent selection changes, complete paging and the complete-membership requirement retain the existing all-or-nothing checks.

The counted Merge action is explicit consent to review and add exactly its selected
UUIDs. It performs versioned selected-draft save, a fresh sealed additive preview,
and acceptance in one action. Excluded UUIDs refuse the operation before saving;
no focused-row fallback or replacement/removal is permitted. A revision, owner or
availability change before submission retires the action. Once submitted, uncertain
acceptance retains the exact preview and operation UUID for receipt recovery.
Selection/navigation/session restoration alone never issues that consent. Export
retains its separate review and confirmation workflow. Mounted one-action, lost
reply, excluded selection, incomplete preview and interrupted-lifetime checks are
in `incomingWorkbenchRendering.test.js`.

Edit Tree shares the same ephemeral highlighted UUID set and single counted
Select Highlighted / Deselect Highlighted toolbar action. Command/Ctrl-click
adds or removes rows from this set; highlighted labels are bold and green fills
continue to denote selected membership. Presentation changes retire highlights.

Imported-data hold consent carries exact project, protocol, frozen candidate and
recording SHA identity. `importedSelection.js` exposes `loadImportedSelection`:
it verifies complete frozen pages with existing bounded selection reads, then
keeps only rows from that recording and preserves draft exclusions. A suggestion
may contain older pending sources, so its trigger SHA never authorizes the whole
proposal. Missing source identities/counts, stale pages, incomplete drafts and
scopes over 1,000 epochs refuse direct merging and require inspection. The ledger
issues this consent only in memory, claims it once, and rejects altered payloads;
restoring a route cannot reconstruct it. Backend additive acceptance and exact
operation recovery still own publication. `importedSelection.test.js` checks
source isolation, exclusions, bounded refusal, stale reads and single-use consent.

Capable contexts advertise `list_selection`. Whole-view/cell selection then uses
one bounded `list-selection` read, verifying exact requested cell order/counts,
per-cell UUID lists, flattened equality, uniqueness and candidate/query/binding
fences. The same abort and current-owner checks surround the request. Older
contexts retain verified 60-row paging. This changes read admission only; ephemeral
selection, saved draft review, merge consent and export authority remain separate.

## Initial context/page offer

`incomingBootstrap.js` validates opt-in context/prepare bootstrap identity,
actor/project/protocol/candidate/root, generation, query/binding, complete bounded
page identities and exact cell totals. Cumulative review removes the response-only
bootstrap before saving prepared receipts, scopes or sessions. Fresh replay uses
only `bootstrap.context` for display/read authority; the unchanged historic receipt
context does not supply current action fields. A resolved profile mismatch refuses
a bootstrap GET before it can become an actionable context.

Frozen review owns at most one offer object per bootstrap in its mounted component.
Retained or paused contexts do not offer pages. `Inspector.initialPageRead` forwards
that opaque offer to `api.useResource` for its initial page only. The hook claims
inside its effect; one unchanged mounted consumer may repeat its claim under
StrictMode, receiving detached data, but another mount cannot claim the response.
Exact root/filter/position/limit/include-cells matching is mandatory. Custom request
ports and caches bypass the offer. Pause, reload, path/revision/owner changes and
replacing/removing an offer permanently retire it; A-B-A never restores the old
claim. Offer identity and retirement participate in render-visible resource state,
so old offered data cannot become actionable before passive effects. A later fresh
HTTP bootstrap can supply a new offer. No global page cache or scientific consent
is created. The resource/StrictMode/session tests exercise these boundaries with
held requests and the actual Inspector hook composition.

## Direct held recording merge

`sourceMerge.js` owns context → source-scoped preview → accept for one held
recording. `useSourceMerge.js` binds its operation to App lifetime. Inspect still
opens Workbench; direct hold never selects a client cohort or navigates there.
Server source selection preserves main membership, full exclusions and publication
fences, independently of interactive selection.

Persist the exact acceptance body, operation UUID and actor through the existing
desktop draft saver before submission. Recovery hydration runs independently of
presentation restoration; restored operations never auto-submit. Explicit recovery
only looks up the saved receipt and requires the original selected or default author. A separate one-second Hold to retry merge grants fresh consent to submit the same original body/UUID; an absent receipt never implies rollback. Monotonic owner
tokens retire pre-submission work across A→B→A navigation and unmount. Verified
same-project completion refreshes data even after navigation; only a still-current
owner opens Overview. Lost/invalid replies retain recovery identity.

Run `sourceMerge.test.js`, `useSourceMerge.test.js`, `importMergeAppRoute.test.js`,
renderer-draft tests and the backend Workbench authority suite for these contracts.

## Large exact Workbench selections

`selection_manifests` advertises the current uncapped-selection contract. Shared
selection helpers keep their Main defaults; only capable incoming views opt out.
Select all batches cell descriptors and verifies full ordered UUID membership;
large cells retain bounded 60-row reads. No partial response changes selection.
`createWorkbenchSelection` uploads at most 1,000 UUIDs per request and verifies the
final count, scope/binding receipts and SHA-256 against the full original array.
The ephemeral manifest is actor/project/protocol/candidate/scope bound, expires
and may be evicted. It grants no draft review, acceptance or export consent.

View selected carries the opaque token in readContext, separately from ordinary
filters. Every selected-view read resolves it freshly; stale/expired tokens refuse
and never widen to all incoming epochs. View loading retires on owner, selection,
pause or navigation changes. Tokens are not presentation checkpoints. Summary and
atomic selected-review use the same complete selection; selected-review replaces
selected flags using the full server draft, preserves exclusions and review flags
outside the explicit set, and requires explicit consent to mark that set reviewed.
Existing sealed preview, exact counts and acceptance/replay remain authoritative.

`compactWorkbenchSelections` only compacts recognized Workbench selected arrays
in the disk checkpoint when their aggregate presentation budget is exceeded. Live
selections remain exact. It records an omitted count for a restart notice; it never
restores a partial selection or drops a preview, operation, receipt or export state.
Frozen review publishes its recovery operation and awaits `flushDesktopDrafts`
before acceptance. Failed persistence or retired ownership submits nothing.

The large-selection backend/renderer tests cover 1,691 incoming epochs, truncated
saved draft details, tokenized views, exact summary/merge membership, replay and
persistence failure. Manifest transfer tests cover 20,001 IDs; disk compaction
covers 100,000. These fixtures do not establish arbitrary-size native latency.

Unconfirmed Workbench recovery reads the existing receipt with GET. A missing
receipt never submits acceptance. Retry this merge is a separate explicit action
using the original preview and operation UUID, including after a pre-submit save
was retired by navigation. Restored acceptPending state cannot recreate consent.
