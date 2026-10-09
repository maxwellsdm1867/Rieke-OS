# Incoming Workbench UI: initial source slice

Base: 6dc6e888e992ea931c8972ead94036bea7091736. Isolated branch `incoming-review-ui`.

The protocol workspace now has a Workbench tab. Import review opens the corresponding protocol Workbench; Review first opens the existing candidate browser inside that tab. Protocol sessions retain worklist choices, active revision, candidate viewer snapshots, and export receipts. These are view/session state, not actor scientific review decisions. Merely opening a proposal never approves an epoch.

The current authority returns the latest proposal per protocol. The initial queue labels this limitation. The sidebar count uses the authority's disjoint full `cell_changes.counts` groups, never truncated cell detail lists, epoch totals, or proposal counts. This is distinct affected cells in the current proposal, not a cumulative pending-cell union.

The existing candidate browser re-evaluates the recipe predicate. Its banner states that it is a live query and may differ from the immutable proposal. Shared tags publish immediately. Viewer exclusions remain temporary export selection state. Review-context export is direct only; protocol replacement/create destinations are hidden. Source eligibility, snapshot hashing, annotation freshness, acquisition compatibility, and backend concurrency fences are unchanged.

Direct queue Export uses the immutable full candidate and its SHA256, creating a one-off artifact without protocol masks or curation inheritance. Desired incoming-only selected export requires the forthcoming scoped export API. Additive Accept & export is disabled in this slice. It must not call the existing exact-replacement apply route under an additive label.

The staged legacy acceptance helper is independently tested: fresh comparison, compatibility, expected binding/query fences, authoritative binding receipt, interrupted acceptance reconciliation, export-only retry. This helper is not wired to additive acceptance. Export failure cannot trigger another binding write; interrupted artifact creation still requires export-history inspection because the legacy export API has no idempotency key.

## Separate additive service contract agreed with backend owner

- `GET /protocols/{p}/workbench`: versioned cumulative paginated proposals, full distinct pending cell/epoch counts, queue revision.
- Candidate root `/protocols/{p}/workbench/candidates/{revision}`.
- `/context`: frozen scope/hash, main binding/query fences, actor draft version and selection mode.
- `/epochs`, `/tree`, `/tree-fields`, `/epochs/{epoch}`: frozen browse with required scope revision; metadata predicate intersects frozen scope.
- `PATCH /draft`: expected draft/scope version, bounded UUID decisions selected/reviewed/excluded and deferred state. No shared annotations or main membership mutation.
- `/preview`: selected or all eligible candidate additions minus explicit exclusions; produces preview hash and current main/source/draft fences.
- `/accept`: explicit preview/fences and operation UUID; durable additive receipt preserving every existing main member and curation. No replacement relabel, no automatic scientific approval.
- Incoming-only export is a separate later capability. Acceptance plus export has staged receipts and retry without duplicate acceptance.

Scope owner implements the Inspector read-context adapter; backend owner implements persistence/frozen scientific APIs. The UI must gate capabilities before enabling these paths. Same-destination batches use fresh per-item previews and receipts, never one invented atomic transaction. New H5 imports, tag returns, saved export reuse, and package reimport remain distinct flows.

## Validation

28 focused helper/navigation/search-exclusion/suggestion tests and 2 actual React SSR/TestRenderer/JSX checks passed in the released UI test window. No live original project was written. Browser automation runtime failed; dynamic fixture capture remained blank. A static browser render of actual component SSR exists as layout evidence only, not client E2E proof. No package/build/push/merge.

## Versioned UI follow-up

The UI now negotiates `/protocols/{p}/workbench` v1 and requires declared capability flags. A cumulative queue uses only its authoritative union counts, supports stable-cursor paging, and resumes an immutable candidate even when it is not on the loaded page. An established v1 queue remains established during failed/pending refreshes; it never falls back into global query browsing. Initial opening waits for service negotiation before selecting a viewer.

`GET /workbench/summary` supplies independent sidebar pending-cell badges and the protocol's `pendingReviewCells` prop. If unavailable, the sidebar shows Review/Refresh and the dashboard count prop is null. No proposal, epoch, truncated-detail, or main-cohort total substitutes for this count. The overview owner owns the explicit main-versus-pending dashboard cards and unfiltered main summary.

The frozen reviewer gates Inspector on the scoped adapter's explicit support marker and `context.protocol`. Without that adapter it shows a scoped-service limitation; no global query is substituted. Highlighting rows does not mark them reviewed or selected durably. Explicit buttons save highlighted selected/deselected decisions. Draft batches are at most 250 UUIDs, individually version-fenced; partial failure reports possible earlier saved batches and requires refresh. Deferral/resume updates only actor draft state. Shared tags remain separate immediate writes.

Selected/all additive previews and acceptance use the separate service contract. Acceptance keeps one operation UUID and sealed preview across session restoration. An uncertain response locks new preview/draft operations and can recover the same receipt. A definitive stale/validation rejection permits refreshing and making a new preview. The receipt is saved before refreshing parent state. Incoming-only export and Accept & export stay disabled while `incoming_export:false`; the legacy full-candidate export is available only in the explicitly labelled legacy queue.

Focused checks cover mounted uncertain receipt recovery across session restore (identical acceptance body/operation, one preview, no legacy replacement routes), cumulative-count rendering, refresh authority retention, bounded draft conflict behavior, and default non-scientific deferral. These are source/component and deterministic API doubles. Integrated native frozen browsing and durable DataJoint service behavior require the backend/scoped-owner commits and separate qualification. No live original writes, package build, push, or merge.

## Incoming-only export follow-up

The UI exposes quick Export and Accept & export only when the queue declares
`incoming_export:true`. Review first remains optional. A deliberate dialog choice
uses saved selected+reviewed decisions, or explicitly approves all eligible
incoming additions minus actor exclusions. Neither choice changes scientific
approval tags or main curation.

`POST candidateRoot/exports` uses the saved draft mode, sealed preview hash,
main binding/query fences, format, optional name, and an independent export
operation UUID. It exports only additions absent from current main.

Accept & export saves the authoritative acceptance receipt before requesting
`GET /protocols/{p}/workbench/receipts/{accept_op}/export-context`. Its
`export_scope_revision`, exact accepted-new count and acceptance operation
identity fence `POST .../exports`. Retries retain the identical export body and
operation UUID; they never repeat an already confirmed acceptance. Lost
acceptance responses retain their own exact request and recover that receipt
before any export call. Saved operation cards stay reachable if acceptance
removes the proposal from the pending queue.

Client receipt checks require format, dataset/event IDs, artifact hash, operation
identity, download URL, `export_scope.kind=workbench_incoming`, and the exact new
count from the preview or accepted export context. Settings lock while an
operation needs receipt recovery. Failure leaves confirmed acceptance visible.
The durable operation records belong to the backend; dialog/session restoration
is presentation state, not a new scientific persistence mechanism.

The cumulative queue also retains conflicted/source-blocked proposals. A legacy
historical proposal whose cell identity cannot be proven can return a null
pending-cell count; the UI displays unavailable rather than substituting zero.

25 focused helper/mounted React/JSX checks pass for this follow-up. Tests cover
lost export response and remount recovery with one acceptance, identical export
requests, and an authoritative final download. This is deterministic API-double
evidence. Native export/DDL/FK/crash qualification and integrated browser proof
remain with backend/E2E integration owners. No package build, push, merge, or live
original writes were performed.

Completed workflows archive their receipts and artifacts before a deliberate new workflow. Remaining additions stay reviewable after partial acceptance/export. Definitive acceptance rejection clears only after fresh context is loaded; uncertain operations retain their saved request identities. Independent Spec/Standards source review found and verified fixes for both lifecycle transitions.

Backend counterpart: c177357 → c0ac47c → df92cb802451c7671c2bb52eb54f9c9454edfd1b. Backend owner reports 169 focused tests passing; this UI branch independently ran its 25 checks. Accepted export-context format lists are honored. MATLAB annotation/curation grouping is unsupported; JSON/SQLite preserve it. A definitive export rejection clears its uncommitted request and permits fresh context/format selection, while uncertain exports retain the exact operation/body. Native qualification remains open.

## Composed reviewer fixes and cumulative scope gap

Incoming export reuse now routes to `target_protocol_uuid` Workbench with the
exact saved candidate, format/name and optional committed acceptance operation;
it never opens the synthetic export-only protocol or global Search. History
labels distinguish incoming additions. No export occurs on navigation.

Frozen context reloads when parent revision changes (including successful shared
tags and external source/annotation changes). The old browser token is hidden
until fresh context loads; uncertain acceptance previews and prepared export
requests retain their exact original bodies/operation IDs. 30 focused checks pass,
including callback/external revision refresh and preserved uncertain state.

Current df92 browser remains per-proposal `C-B`, which can include already-main
epochs after partial acceptance. Deduplicated cumulative counts do not establish
cumulative browsing semantics. The UI now labels that gap explicitly. Backend
owner is implementing an approved authoritative cumulative pending snapshot
(`prepare`) and consistent `C-B-M` readers. That subsequent slice requires its
own tests and source integration; no client union/global fallback is supplied.

## Capability-gated cumulative default

When `cumulative_pending_browse:true` is declared, Workbench defaults to an
authoritative prepared cumulative snapshot; original proposals move to optional
history. The UI requests `POST /protocols/{p}/workbench/prepare` with exactly the
latest `expected_queue_revision`, once per queue fence (explicit retry on an
error). The server derives an idempotent operation if omitted. The response must
be v1, kind `workbench_pending_union`, include its preparation operation ID,
canonical frozen candidate root, matching context/scope and requested queue echo.
The nested candidate identity and destination protocol identity must also match;
native protocol DTOs identify their protocol in `definition.protocol_uuid`.
No row union, predicate rerun or membership interpretation occurs in the client.

Fresh queue fences after imports/partial acceptance prepare updated snapshots.
The backend owns exact unmerged membership, fingerprint-conflict refusal,
original proposal provenance, and same-fingerprint actor decision carry. Empty
queues without original history avoid preparation writes. Saved exclusions remain
resumable even when the awaiting-review count is zero. Ordinary renders, identical queue responses,
and resuming the same prepared scope do not create repeated requests.

Pending acceptance is published to session state before POST; an unresolved
acceptance/export keeps its old prepared root and request body until receipt
recovery. Earlier prepared scopes retain recovery buttons and exact accepted
subset export actions after newer snapshots open. Completed receipts/artifacts
remain accessible. Quick Export/Accept & export display the selected/all preview
counts before confirmation and keep full inspection optional.

32 focused component/helper/JSX checks pass. Two independent source reviews
verified preparation/recovery lifecycle fixes. Native three-import union,
identity dedup, pending subtraction, durable draft carry, and actual browser
proof still require the new backend checkpoint and E2E qualification. The old
df92 implementation does not satisfy cumulative incoming-only browsing merely
because it returns deduplicated counts.

Preparation keeps the prior frozen browser mounted while the newer scope loads,
with draft/preview/accept/export mutation controls fenced. The replacement opens
only after the complete prepared DTO passes identity and scope validation. A
durable acceptance receipt resolves its transient pending flag; uncertain
operations still retain their exact request and block scope replacement.

34 focused checks cover identity refusal, zero-count exclusion resume, in-flight
recovery, and preserved mounted browser/write fences during asynchronous prepare.
Backend initialization must preserve the queue authority token (actor CAS version
and actual later edits remain fenced); paired queue→prepare→queue qualification
belongs to the cumulative backend slice. Open export dialogs are fenced too,
and publish in-flight workflow state before requests to prevent scope replacement.
Inspector review toggles must use candidate `review_decision`; synthetic scientific
curation stays separate (owned Inspector adapter followup).

Queue refresh continuity is fenced before effects run: the queue hook reports
loading synchronously when its revision/request parameters change, even while
retaining the prior queue DTO. Cumulative refresh retains the mounted Inspector
through delayed queue and prepare responses; fresh context is required for new
actions. Exact uncertain operation recovery still uses its original request.
35 focused checks include the actual hook's old-token loading sequence.

Paired qualification used backend `d62593489ff21d49f0b1a8b3613b3538b9eb855c`
composed with scoped/generation dependencies `a0f010a`, `6845e85`, `39a8ebd`.
Two backend SQL-double queue/initialization/carry tests passed independently.
Its actual three-proposal/three-pending-epoch DTOs then mounted in this UI:
queue→prepare→queue/ordinary refresh produced one prepare POST, matching nested
identities and no global query. This qualifies DTO/lifecycle composition on
disposable doubles; native storage and actual browser proof remain separate.
The backend commit alone lacks those generation dependencies and is not a
standalone qualified composition.

## StrictMode first-entry preparation

Preparation retains its promise for the same protocol, queue fence and explicit
retry key. Effect cleanup detaches only its display subscriber. React StrictMode
setup/cleanup/setup rejoins one request, while a genuinely unmounted or superseded
subscriber cannot publish a late response. Explicit retry and real remount send
the identical body; the backend's deterministic preparation receipt supplies
idempotency. An aborted display does not imply rollback of a native write.

Five real ReactDOM createRoot/StrictMode regressions run with jsdom (test-only
dependency): first entry without Retry, changed authority/late completion, real
unmount/remount, lost response/exact-body retry, and uncertain acceptance before
new preparation. The previous implementation fails the first-entry regression
with the reported permanent interrupted message. All 40 focused checks pass.
Inspector and filter probes isolate the lifecycle boundary; these tests do not
claim native or full Inspector resource/browser qualification.

Candidate read contexts also carry optional `cohort_key` for browser intent:
`JSON.stringify([root, candidate_recipe_sha256, expected_binding_version])`.
It is omitted when immutable evidence is missing. Draft saves keep that identity
while every read and mutation still uses the newly fenced scope token. Main
binding, candidate root or recipe changes create a different intent identity.
The scoped Inspector adapter owns focus/tree continuity and fresh-membership
validation; the key is never sent as read or write authority. The mounted
pass-through regression brings the focused total to 41 passing checks.

## One-action selected merge (2026-10-08)

The counted Workbench Merge button explicitly approves its exact selected UUIDs
and adds them in one action. The renderer saves selected/reviewed decisions using
current draft/scope versions, obtains a fresh selected-mode sealed additive preview,
and submits acceptance with its binding/query fences and a new operation UUID.
There is no intervening review or confirmation click. Excluded selection refuses
before saving; unrelated review marks and exclusions remain intact. Selection,
focus, navigation and restored sessions do not authorize this action. Existing main
membership and curation remain preserved by the additive service.

The selection must contain 1–1,000 distinct exact UUIDs and the complete actor draft
must be available. Incomplete preview membership refuses acceptance. A mounted
owner/revision/availability change during preparation also refuses submission.
Partial draft failures require refresh; uncertain acceptance preserves the original
preview and operation UUID for explicit receipt recovery. A successful acceptance
publishes its receipt before refreshing the parent. Export keeps its existing
separate review/preview workflow. These semantics supersede the previous selected
merge's separate review and preview confirmation steps; they do not change the
backend's additive authority, replacement semantics or transaction boundaries.

`incomingWorkbenchRendering.test.js` exercises one-action exact save/preview/accept,
retained exclusions, lost-reply recovery with identical request identity, and refusal
for excluded selection, short preview, revision change and unmount. These are owned
component/API doubles, not native data or release qualification.

## Imported-recording hold (2026-10-08)

On each imported-data card, a normal click inspects that exact candidate. Holding
the same control for one second issues a single-use project/protocol/candidate/source
intent. Fresh frozen pages identify the source's exact eligible UUIDs, excluding
authored exclusions and unrelated older pending sources; the selected merge above
then saves, previews and accepts. Leaving or cancelling the request retires consent;
restored routes cannot issue it again. File browsing and H5 ingestion are unchanged.

This uses the existing complete frozen-selection bound: a candidate larger than
1,000 epochs refuses the shortcut and asks for inspection/manual selection. It does
not silently merge a partial candidate. Component and policy tests cover the timer,
source identity, exclusions, stale reads, navigation departure and receipt recovery.
They do not qualify a packaged app or native H5 throughput.
