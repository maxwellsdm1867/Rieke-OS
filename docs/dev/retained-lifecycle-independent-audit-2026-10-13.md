# Independent retained lifecycle audit

2026-10-13, working implementation on `codex/ui-cache-design`, before final integrated qualification. This is a review note, not the central adoption inventory or a release receipt. The root task owns final fingerprints and full-suite receipts.

## Scope and census

The production import closure must start at `workspace-app/src/App.jsx`, not just the newly introduced retention file. App contains inline Protocol, ImportPage, Logs and HistoryPage implementations, and imports the project shell plus retained routes. Follow literal relative imports, re-exports and lazy imports through shared modules. A read-only initial census found 234 source modules; counts change as concurrent approved fixes add modules. Exclude tests, test-support, assets and external packages. Unsupported local absolute/alias/computed imports must fail closure discovery rather than disappear from it.

File-level classification alone needs care: App mixes project-lifetime effects with retained Protocol effects; `api.js` and other shared hooks serve both. Whole-module fingerprints are deliberately conservative, but an inventory's rationale should distinguish the specific lifetimes below.

## Reviewed lifecycle classes

| Class | Representative owners | Required behavior and verification |
| --- | --- | --- |
| Semantic presentation reset | AnnotationTags input; CandidateExportPanel options; TraceViewer sample inputs; Inspector highlights; CellTypeAccordions disclosure; DataStores source paging; ProtocolApplyPanel target initialization | Reset on real epoch/candidate/window/source/target-request identity changes, not Activity reconnect. Shared `useSemanticReset` is appropriate for synchronous presentation changes. Tests must preserve actual edits across repeated hide/reveal and reset on a different identity. |
| Scientific authority lifetime | Inspector active read/highlight/navigation owners; PagedTree selection generation; IncomingTreeSelection queue; IncomingSelectionTools; AnnotationTags committed scope; TreeGroupTags preview lease; useAnnotationReceipts | Cleanup revokes/cancels replaceable work; setup reconnects exact scope, actor, revision and owner. Do not convert these effects into once-per-identity resets. Late response and stale callback tests must still reject publication/actions after replacement. |
| Fresh reads with preserved navigation | HierarchyTree; ColumnTree; InspectionCellTree; useEpochBrowserPage; useProtocolBrowse | Revalidation remains required. Preserve expansion, selected focus and scroll as navigation intent; do not retain response objects as fresh authority. A changed scope/revision or mismatch rejects old receipts. Delayed restoration must yield to newer user navigation. |
| Immutable initial hydration | MetadataExplorer initial saved candidate | Only successfully completed, matching candidate/retry hydration is remembered. Abort/error is not completion. Reveal must not overwrite later authored edits. Separate current preview reads continue to revalidate. |
| Checkpoint publication and authored state | Protocol/Inspector/Explorer/CellQC session callbacks; renderer DraftStore hook; project preference client; tree-layout saver | Callbacks publish to the originating route. An eviction guard protects RAM only; each authored field also needs a checkpoint owner or truthful unsupported persistence contract. Never checkpoint a lease, reusable consent or in-flight request as authority. |
| Visibility-owned input and chrome | RetainedPortal/useRetainedModal; local search Undo; InspectorActions Escape listener; IncomingCellTypes Escape/outside listener; PredicateBuilder/ValueInput popups; TreeBuilder popup; native active-command registry | Busy hidden modules may remain mounted, so mount lifetime is insufficient proof of input authority. Global input, focus restoration, portals, modal top-layer state and navigation callbacks need active view/tab checks. Scientific completion still invalidates data when its initiating view is hidden. |
| Replayable visual subscription | ResizeObserver, pointer/drag cleanup, trace canvas/RAF, scroll capture/restore, loading announcement timers | Reconnect observers and rendering work without reinitializing unrelated presentation. Hidden geometry and temporary empty loading content must not overwrite saved position. Clean up captured pointer/RAF/timer work; no scientific authority is created. |
| Consent/freshness reset | ProtocolApplyPanel removal acknowledgment; NewPinnedProtocol mixed-protocol review; PredicateDialog scoped preview; SourcePropagation preview | Conservative invalidation is intentional. These are not ordinary text drafts. Preserve authored names/targets separately while rechecking the scope that gives consent meaning. |
| Project lifetime outside Activity | App startup restoration; useDesktopDraft; useSourceMerge; import queue/monitor; global mutation Undo; annotation profile and external scan; desktop document lifecycle | These owners outlive route visibility. Accepted writes/recovery remain project-scoped. Native project activation, teardown and backend incarnation are separate from route/tab activity. |

## Concrete findings and disposition

1. **Healthy project loss after another renderer crashed:** desktop global clear was replaced by isolated unavailable-owner accounting and nondestructive recovery suspension. Healthy draft checkpointing and strict replacement refusal were checked in follow-up source review.
2. **Queued/in-flight activation could cover recovery:** generation fencing was added at authorization and view activation, preserving loaded inactive state while refusing stale attachment.
3. **Recovery-only restore action blocked by general IPC fence:** narrowed recovery-host admission restores the existing strict restoration path.
4. **Guard-only draft eviction:** retention eviction now checks the unmount-guard map as well as explicit protection; authored checkpoint coverage is audited separately.
5. **Effect replay erasing drafts/highlights:** migrated to semantic reset logic and real-control regressions; broad source inventory must prevent recurrence.
6. **Hidden busy portal chrome remained interactive:** retained portals now carry hidden/inert state outside their origin DOM subtree.
7. **Hidden local search Undo remained registered while another write pinned effects:** identified for visibility gating. Global scientific Undo remains project-owned; local temporary search Undo must not depend on unrelated request timing.
8. **TreeGroupTags mixes disposable preview with authored text:** releasing preview authority on disconnect is correct; the separate authored-draft work must retain exact target-scoped text without restoring the old preview as authority.
9. **Hierarchy reconnect discarded expanded siblings and scroll:** assigned repair in `tree-browser/ui/HierarchyTree.jsx` stores only bounded navigation intent for the exact prior scope, refetches every saved page using the saved revision as a server witness, fences late old-scope responses and lets new user scroll supersede delayed restoration. `hierarchyRetention.test.js` covers this with real React DOM; existing selection/ancestor composition suites remain required.

## Gate review

The proposed full-module canonical AST fingerprint closes the important gap where a helper or callback body changes without changing a hook call. Ordered effect-site records make additions visible. It is a review receipt, not proof of semantic correctness, and must have no automatic acceptance/update command.

Keep semantic template literal raw text in fingerprints: `TemplateElement.value.raw` affects tagged templates. Ordinary source-location data may be omitted. Resolve or reject local absolute imports. Explicitly test React named-import aliases and namespace calls; effect-binding escapes, re-exports and destructuring need either supported discovery or a fail-closed rule. A successful source fingerprint check must not be described as replacing the behavioral tests.

The reusable behavioral matrix should exercise: same identity reconnect, real identity change, identity change while hidden, reconnect before an aborted read resolves, known revision/actor/backend change, pending write after departure, local Undo/keyboard while hidden, modal/portal visibility, dirty eviction, successful checkpoint and refused checkpoint, and saved-state restart without authority reuse. Actual control modules and full-App/native cases complement the helper tests.


## Trace display and inactive read follow-up, 2026-10-15

The integration owner and separate frontend/package reviewers reviewed these changes. Exactly twenty changed production modules receive updated receipts; unchanged modules retain their prior evidence. This does not waive later source changes.

The first full frontend run retained 1,252 passing cases and two failures: an outdated review-receipt fixture caused a runaway React Fiber assertion dump, and the inventory correctly rejected changed/missing lifecycle reviews. The corrected fixture distinguishes a valid page receipt from absence in both page and detail. The corrected full suite passed all 1,256 tests in 101.0 seconds at clean source `7d916bc7cbe7427df8b98251f3daba8b2f24fba6`; the raw first failure and successful rerun remain preserved.

| Module | Reviewed lifetime and boundary | Behavioral evidence |
| --- | --- | --- |
| `src/api.js` | Binary dispatch retains request ownership. Hidden read demand cancels while commands continue; offers retire and reload waits for activation. | `src/traces/retainedReadLifecycle.test.js`, `src/traces/traceBinary.test.js` |
| `src/epoch-browser/ui/EpochViewer.jsx` | Separately admitted trace row/context reaches the shared viewer without granting curation from display state. | `src/epoch-browser/inspectionMetadata.test.js` |
| `src/epoch-browser/ui/InspectionCellTree.jsx` | Focus carries the original row and its validated page; explicit selection retains revision authority. | `src/epoch-browser/inspectionCellTree.test.js`, `src/epoch-browser/inspectionMetadata.test.js` |
| `src/epoch-browser/ui/Inspector.jsx` | Display requires current owner/navigation lifetime, exact prepared capability and row source. Central freshness still gates curation; selected pages cannot borrow parent authority. | `src/epoch-browser/inspectionMetadata.test.js`, `src/incomingReviewDecision.test.js` |
| `src/epoch-browser/ui/MatchingEpochs.jsx` | Known stream descriptors are independent of optional live values; current result and annotation authority remain required. | `src/epoch-browser/inspectionMetadata.test.js`, `src/scopedPredicateLifecycle.test.js` |
| `src/epoch-browser/useEpochBrowserPage.js` | Visibility gates page reads; abort and owner/transport/key checks reject late results. Retry nonce waits for activation. | `src/traces/retainedReadLifecycle.test.js`, `src/epoch-browser/epochPageReads.test.js` |
| `src/epoch-browser/useEpochInspection.js` | An admitted page row supplies descriptors and proposal receipts independently of optional detail values. Missing page and detail receipts expose no review action. | `src/epoch-browser/inspectionMetadata.test.js`, `src/incomingReviewDecision.test.js` |
| `src/incoming-workbench/ui/FrozenIncomingReview.jsx` | Prepared display capability passes from the frozen candidate without changing draft, selection, merge or publication ownership. | `src/incomingWorkbenchRendering.test.js`, `src/traceReadContext.test.js` |
| `src/protocol-overview/useOverviewResource.js` | Hidden demand releases reads. Deferred reload remains stale; only committed visibility authorizes old reload closures. | `src/traces/retainedReadLifecycle.test.js`, `src/protocol-overview/overviewDemand.test.js` |
| `src/summary-jobs/useFieldRegistry.js` | Registry/fallback reads follow visibility, abort on hide and retain completed same-key presentation. | `src/traces/retainedReadLifecycle.test.js` |
| `src/traces/readWholeTrace.js` | Binary batches retain cancellation and exact identity/count admission; partial arrays never publish as complete. | `src/traces/traceBinary.test.js`, `src/traceReadContext.test.js` |
| `src/traces/traceBinary.js` | Pure framing validates shape, count, identity, finite data and byte boundaries; no effects or background work. | `src/traces/traceBinary.test.js` |
| `src/traces/traceDisplayGeometry.js` | Distinct DTM1 validates indices, complete statistics, viewport width and exact prepared context. Only typed unsupported geometry permits raw fallback. | `src/traces/traceDisplayGeometry.test.js` |
| `src/traces/traceReadContext.js` | Strict capability fields preserve project/protocol/candidate/publication identity; selected pages require their own capability. | `src/traceReadContext.test.js` |
| `src/traces/traceStatistics.js` | Statistics derive from complete owned arrays; geometry statistics stay distinct. No effects, timers or external writes. | `src/traces/traceBinary.test.js`, `src/traces/traceGeometry.test.js` |
| `src/traces/ui/traceGeometry.js` | Screen extrema keep original coordinates and bits; geometry painting avoids another reduction. Raw gaps and finite segments retain their behavior. | `src/traces/traceGeometry.test.js`, `src/traces/traceGeometryLifecycle.test.js` |
| `src/traces/ui/TraceViewer.jsx` | Whole geometry, raw windows and cursor tiles stay separate. Owner/context/width fences reject stale paint; unchanged reveals retain input text. | `src/traces/traceGeometryLifecycle.test.js`, `src/traces/traceDisplayLifecycle.test.js`, `src/retainedControls.test.js` |
| `src/traces/useExactTraceCursor.js` | One tile/latest intent belongs to current source/owner. Hide and supersession cancel timers/requests; pending values never interpolate. | `src/traces/exactTraceCursor.test.js`, `src/traces/retainedReadLifecycle.test.js` |
| `src/traces/usePreparedTraceRead.js` | Layout reads retain exact ownership and AbortSignal retirement on hide, replacement and Activity replay; completed stale results cannot resurrect. | `src/traces/preparedTraceRead.test.js`, `src/traces/retainedReadLifecycle.test.js` |
| `src/traces/useTraceViewport.js` | ResizeObserver and rearmed DPR listeners dispose with the canvas owner. Actual fractional physical width controls geometry admission and demand. | `src/traces/traceGeometryLifecycle.test.js` |

The native a25b437 audit independently matched every point bit/index/statistic for three 300k and six 600k traces against original H5 sources, plus raw Inspect windows and an exact cursor. Geometry also matched 46 physically valid Light/Dark/DPR Canvas oracle cases. These observations qualify their measured source and do not replace the new inactive-read and clicked-row tests. Accepted writes remain mounted; only read demand follows visibility. The Suspense regression rejects an old reload during an abandoned reveal.
