# Shared tree read audit

Source audit and subsequent shared-read implementation, 2026-10-06. Audit baseline:
`cb64a4197a6d9c80ba52537cc0e1c37ebee5228e`. The initial callsite audit preceded the probe and implementation evidence appended below. Earlier frozen Workbench timings do not measure normal native tree
navigation: the live service has a persistent eligible scope cache and narrower
response attestation that the frozen adapter cannot automatically borrow.

## Actual shared owners and callsite gaps

| User operation | Current frontend/request path | Shared backend and repeated work |
| --- | --- | --- |
| Main protocol columns | `loadColumnTreePages`: fresh target, then concurrent parent requests; optional attested ancestor JSON reuse. Continuation recovery can read root first. | `/tree-pages` → `witnessed_tree_page` → `TreePages.page`. Each HTTP call obtains locks and resolves/checks scope; eligible persistent scope hits can avoid rebuilding. |
| Supported source/predicate tree reads | Shared loaders and `/tree-pages` accept predicate scope; this establishes supported behavior, not a proven mounted current source-tree UI. | Same TreePages grouping/projection; predicates or annotations can require fresh scope builds. |
| Incoming columns | Same loader, but `tree_column_pages` capability requests `include_ancestors`. | Workbench guarded context → `TreePages.column_pages` → one response-local scope; closing candidate/generation check covers all pages. |
| Hierarchy branch expansion | Independent `HierarchyTree.fetchPage`, one request per opened/page-stepped branch. | Same main/frozen endpoints and TreePages page owner. Single-branch expansion is already one request. |
| Hierarchy anchor reveal | Independent locator request, then sequential requests for each uncached ancestor. Applies to both live and incoming trees. | Does not use the existing column batch even for incoming. Repeated endpoint fences and scope resolutions. |
| Hierarchy restore | Sequential request for every saved page, then restore expansion state. | Repeats reads across multiple paths; target-plus-ancestors batching alone does not cover arbitrary sibling restore. |
| First epoch / shift range | `createTreeSelectionReader`: first-branch descent, or sequential 60-row leaf pages up to 1,000 positions. | Repeated page calls. Semantics are first DTO / ordered range, not whole-subtree UUID selection. |
| Incoming group selection | `incomingTreeSelection` → `/tree/selection`. | Shared `TreePages.selection` resolves one scope and ordered bounded membership; Workbench supplies candidate authority. |
| Incoming group tags / cell representative | `resolveTreeGroup` recursively pages, then verifies a fresh root; cell mode stops at the first verified matching cell epoch. | Still page traversal in some paths. UUID-only selection is insufficient without preserving representative DTO/cell proof and final tag readiness. |
| Main/source group tags | `previewTreeGroup` → `/annotations/group-preview`. | Already one TreePages scope plus `TreePath` matching, under separate retained preview/write authority. Explicit project admission is 10,000 epochs. |
| Matching epoch list | `/explore/epochs`, after a predicate preview revision. | `TreePages._scope`, whole-result chronological sort, optional all-cell summary, then bounded slice. Group values can be loaded even though only membership/revision are consumed. |
| Legacy full tree | GET protocol/source/frozen `/tree`. | `WorkspaceService.tree`: rows, catalog/values and full rendering. It is distinct from current paged navigation. |
| Arrange / metadata preview | `TreeBuilder` receives actual paged preview; frozen full catalog fetched only when chooser/combination editor opens. Main builder still enables requested summaries; metadata explorer uses compact preview requests. | Field registry and requested summaries/catalog are separate owners. Full `explore_preview` still computes membership; compact flags skip full tree/catalog statistics. |

Primary sources: [column orchestration](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/tree-ancestors/columnTreeReads.js#L8),
[hierarchy loader](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/tree-browser/ui/HierarchyTree.jsx#L26),
[shared request shape](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/pagedTreeRequest.js#L2),
[live route/witness](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/python/disco/navigation/tree_pages.py#L663),
[scope cache](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/python/disco/navigation/tree_pages.py#L286),
[frozen columns/selection](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/python/disco/workbench/workbench.py#L879),
[range reader](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/tree-selection/treeSelectionReader.js#L39),
[tag target traversal](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/annotations/treeGroupTargets.js#L18),
[tag dispatch](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/annotations/ui/TreeGroupTags.jsx#L40),
[group preview](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/python/disco/decisions/annotation_groups.py#L142),
[matching epochs](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/python/disco/navigation/matching_epochs.py#L9),
[legacy routes](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/python/workspace_api.py#L841),
[legacy tree](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/python/workspace_service.py#L1043),
[Arrange catalog loading](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/typed-query/ui/TreeBuilder.jsx#L27),
[compact preview](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/python/workspace_service.py#L1096),
[metadata preview caller](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/metadata-explorer/ui/MetadataExplorer.jsx#L113).

## Recommended shared seam

Keep exact membership, split projection, opaque path matching, grouping order and
bounded page rendering in `disco.navigation.tree_pages`. The existing
`TreePages.column_pages` is already a visualization-independent target/ancestor
operation despite its name: hierarchy anchor reveal needs the same pages. Expose
it through the live route as an explicitly bounded response-local operation and
consume it through common frontend target/ancestor orchestration for both column
and hierarchy presentations. Do not implement another Workbench-only resolver or
copy grouping logic into the renderer.

The route/authority adapters remain separate. Workbench must retain frozen
candidate opening/closing checks. Live witnessed protocol reads must attest all
returned pages within the existing generation/annotation lock scope and attach
one consistent identity; a cacheable identity must never be fabricated for source,
filtered, joint, annotation or custom-reader requests that are currently ineligible.
Unsupported/custom readers retain fresh ordinary page behavior. A batch may save
HTTP and schema/read setup even when native `_scope` already hits its cache;
measure those savings rather than assuming repeated builds.

A live batch contract needs explicit review before implementation: accepted
options, page/count/byte bounds, stale response behavior, exact parent offsets,
anchor handling and capability/fallback behavior. If a continuation first needs a
fresh root revision, that freshness step must remain or be incorporated as an
explicit operation. Silently dropping the expected revision changes correctness.
For un-witnessed scopes, response-local reuse must have an appropriate existing
closing generation fence or preserve independent canonical reads; matching tree
revision alone does not establish every annotation/display authority.

Hierarchy arbitrary restore should be a separate measured operation with bounded
page count and projection union, not an unbounded general page batch. Keep its
state eviction, sibling preservation, expansion and cancellation semantics.
First-epoch/range operations can eventually use the same prepared-scope primitive,
but their ordering, synchronous supplied-page behavior and DTO requirements are
different. Group-tag preview already has a single-scope resolution and mutation
receipts: do not replace that authority with a browsing batch or incoming UUID
selection response. See the [tree selection contract](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/tree-selection/AGENTS.md)
and [ancestor reuse contract](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/tree-ancestors/AGENTS.md).

## Additional backend opportunities to measure

- `_scope` cache hits still perform index integrity checks, binding/source checks,
  fingerprint equality and key preparation. Cache miss cases resolve membership,
  project fields and compute revision. Compare structural date/cell/block, dynamic
  fields and annotation-filtered cases separately.
- Matching epochs reuse the tree scope but discard values, then sort full rows
  every request. A shared membership/revision result with an independently bounded
  chronological view is a plausible next design; retain exact preview revision,
  filters, annotations and include-cells semantics.
- Full-tree `WorkspaceService.tree` obtains `_tree_rows`, then `_tree_fields`,
  which may resolve rows again on a catalog cache miss. These are legacy/full
  outputs; establish an active caller before optimizing or removing them.
- Compact source preview and subsequent tree/list reads can re-evaluate the same
  predicate membership. Reuse would require source/metadata/annotation generation
  proof and explicit memory bounds. A saved preview alone grants no new cache or
  mutation permission.
- Frozen catalog requests intentionally request full metadata only when the user
  opens its chooser. Do not regress that behavior by preloading catalogs to make
  navigation batches easier.

## Exact regression and benchmark matrix

Use one disposable fixture generator and identical source/runtime/controller
receipts; separate HTTP counts, scope builds/cache hits, backend elapsed time,
serialized bytes and renderer-visible completion. Do not monkeypatch canonical
pager methods when timing: their identity guards intentionally activate fallback.
Profile separately. Qualify native and SQL-double results independently.

| Dimension | Required cases |
| --- | --- |
| Authority | Native main protocol (cold/warm); source predicate; metadata/tag filtered protocol; frozen pending candidate; custom pager/service fallback |
| Scale/shape | 1k, 10k, 50k; fixed selected/page count; one cell versus many; depth 0/3/8; >60 siblings; expensive dynamic metadata |
| Presentation | Main and incoming columns; hierarchy simple expand; anchor reveal; restore with sibling branches; source matching tree/list; Arrange chooser closed/open |
| Ordering/content | Typed bool/number/string; dynamic null/missing; built-in null; joints; block chronology; exact leaf UUID order; counts-only/full summaries |
| Navigation | First and later parent offsets; anchor beyond first page; stale continuation recovery; repeated warm navigation; cancelled/replaced intent; hierarchy eviction/restore |
| Authority failures | Source/index/binding/annotation generation changes at closing; stale tree/candidate revision; missing witness; changed fingerprint; overridden readers; malformed batch options |
| Scientific actions | First epoch DTO; same-page synchronous range; multipage <=1k range; incomplete range refusal; tag representative cell identity; preview receipts and limits unchanged |

For target/ancestor batching, compare every returned page against independent
fresh baseline reads, including revision/identity and parent offsets. Assert one
canonical scope resolution per eligible batch, no extra catalog loads, bounded
response size, and no partial publication after failure. Native UI testing must
verify both presentations, not merely the frozen backend endpoint. Architectural
review and module contract/adoption updates are required before adding the shared
live batch API; this audit proposes the seam and does not approve unseen changes.


## Verified production callers and preview distinction

Current production `PagedTree` imports are
[`EpochTreePane`](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/epoch-browser/ui/EpochTreePane.jsx#L3)
for the hierarchy presentation and
[`RetainedTreePresentation`](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/tree-browser/ui/RetainedTreePresentation.jsx#L4)
for columns. The legacy `TreePreview` component has no production importer in the
inspected source. Supported predicate/source request shapes and backend routes
must therefore not be described as proof that a legacy source-tree presentation
is currently mounted. Benchmark supported APIs separately from verified visible
flows and follow the actual parent composition when choosing native UI checks.

`Inspector` derives `treePage` from `treeReceipt.data` received from paged tree
metadata; its Arrange preview does not issue an additional full-tree request.
See [receipt ownership](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/epoch-browser/ui/Inspector.jsx#L145).
The main Inspector passes `summaryEnabled: !readContext`, and `TreeBuilder`
requests summaries when that flag, registry support, generation and requested
fields allow it. Thus main Arrange can perform additional summary work even
while frozen Arrange disables it. This is the separate requested-summaries owner,
not evidence of full-tree reconstruction. See
[builder configuration](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/epoch-browser/ui/Inspector.jsx#L402)
and [summary activation](https://github.com/maxwellsdm1867/Rieke-OS/blob/cb64a4197a6d9c80ba52537cc0e1c37ebee5228e/workspace-app/src/typed-query/ui/TreeBuilder.jsx#L44).

## Concrete live bundle design for review

This is a recommendation pending the shared cold/warm probe, not authorization
to broaden read authority or a report that runtime wiring has changed.

1. Reuse `TreePages.column_pages` as the only backend target/ancestor assembly
   algorithm. Add opt-in live request fields equivalent to the frozen route:
   `include_ancestors` must be boolean and `ancestor_offsets` must contain at most
   eight null/bounded-integer entries. Each page retains its <=100 row limit.
   Single-page requests preserve existing response shape and behavior.
2. Put live assembly inside the existing witnessed response's locks, opening
   generation and closing generation/contract checks. Attach the same current
   read identity to every returned page. The first admission can match the
   already-witnessed unfiltered protocol scope; other sources require a reviewed
   closing scope or remain on ordinary reads. Pager overrides retain canonical
   fallback. Do not manufacture a witness for an otherwise ineligible scope.
3. Advertise scope-specific bundle support in an ordinary fresh page/metadata
   response, avoiding a discovery-only network request. Reuse the existing frozen
   context capability for incoming. Unknown/older capability follows the current
   target-plus-parent path. Do not reinterpret a generic 400 or a stale 409 as
   permission to retry a different request and hide the original failure.
4. Have common target/ancestor frontend orchestration validate parent paths,
   offsets, order, revision and identity, returning pages independently of visual
   layout. ColumnTree consumes ordered columns; HierarchyTree merges those pages
   while retaining siblings and expanding only the revealed path. Both preserve
   abort/current-intent checks. Arbitrary hierarchy restore remains separate.
5. Preserve the live fresh-root continuation recovery until the new operation
   explicitly represents and validates that same freshness step. An anchor still
   uses the locator's recorded parent offsets; explicit non-anchor parent offsets
   retain their existing meaning.

**Warm-path tradeoff:** a fresh target followed by already-attested cached parent
JSON can be faster and smaller than a fresh bundle which recomputes and sends all
parents. A bundle principally removes cold parent round trips and duplicated
response setup. It should not automatically replace the cache-hit path without
measurements. Benchmark fresh target plus cached parents against fresh bundle
using native main structural and dynamic splits, including serialized bytes and
visible completion. A conservative initial policy can retain the proven live
warm path and use bundles for known cold/no-retained-parent cases; policy should
not add a speculative first target request followed by a second full bundle.
Incoming hierarchy anchor currently misses its already-supported bundle and has
no live ancestor lease to preserve, making it a distinct low-risk callsite gap.

The shared engine probe should determine whether live scope-cache misses,
repeated grouping/rendering, HTTP setup or renderer work dominate before selecting
a patch. No new runtime edits are recommended solely from the earlier frozen SQL
fixture timings.


## Measured shared-engine probe

A serial disposable probe used the current TreePages engine, synthetic metadata
and a real SQLite index at 1k/10k/50k epochs. Three unprofiled cold/repeat pairs
compared separate target/ancestor calls with existing column_pages. Separate
cProfile passes counted scope construction without changing reader eligibility.
No runtime source, installed application or scientific project was changed.

| Live grouping / epochs | Separate pages cold / repeat | Shared batch cold / repeat | Scope builds separate → batch |
|---|---:|---:|---|
| date/cell/block / 50k | 150 / 16 ms | 137 / 8 ms | cold 1→1; repeat 0→0 |
| date/parameter/cell / 10k | 605 / 25 ms | 245 / 24 ms | cold 3→1; repeat 0→0 |
| date/parameter/cell / 50k | 3362 / 3492 ms | 1368 / 1376 ms | cold 3→1; repeat 3→1 |

This confirms that the main tree's large custom-split path also repeatedly builds
metadata. At 50k the separate depth projections are not retained across this
sequence under the existing cache policy; increasing cache budgets is not assumed
to be the right fix. Shared batching removes two builds, but the remaining build
still scales with dataset size. Structural groups already reuse their scope.

These are inner-engine observations, excluding HTTP, native authority/SQL and
paint. The actual renderer can reuse attested parent JSON and skip backend parent
calls entirely; its warm path must be measured independently before choosing an
always-batch policy. Frozen warm measurements in the raw probe reuse one service
instance, unlike real frozen requests, so they do not prove cross-request reuse.
All disposable fixtures were cleaned. Raw controller, timing samples and counts
are retained in the local kit under shared-tree-read-probe-2026-10-06T11-26-01,
with shared-tree-read-probe-summary.json alongside it.

## Independent preimplementation review: selected narrow wiring

Approved design for the user-requested shared wiring, before runtime changes:

- Live bundles use the existing witnessed scientific eligibility and closing
  checks. Strip/validate bundle-only options before strict page parsing. Advertise
  scope-local capability only after a successful current witness and canonical
  pager admission. A later request still revalidates eligibility; capability is
  never a freshness receipt. Explicit bundles in scientifically ineligible scopes
  fail closed rather than silently downgrade. The selected live contract also rejects explicit bundles when pager methods
  are overridden; ordinary custom page behavior remains unchanged and no bundle
  capability is advertised. This stricter choice is acceptable for the new opt-in
  live API. Existing frozen `column_pages` custom-reader fallback remains unchanged.
- Learn capability from verified pages of the current scope, including an already
  required fresh continuation root. Unknown/older capability retains current
  requests. Reset capability with endpoint/scope activation; avoid global flags
  and generic error-based retries.
- Preserve the live warm path when retained current columns already cover the
  requested parents/offsets. Use a known-supported bundle for absent/cold parents,
  including when a read owner exists. For anchors whose parent path is unknown,
  a known-supported bundle is appropriate. This conservative hint changes only
  transport choice: the fresh target witness still decides reuse. It avoids a
  new cache-probe API; hidden historical entries may cause a harmless missed
  reuse opportunity. Do not choose always-batch simply because splits are dynamic.
- Validate the whole live bundle before publishing pages. Validated parent bodies
  may enter the existing cache via `readOwner.read` under the fresh lease, with a
  loader returning the already-validated parent. Existing immutable copy, body/
  identity checks, byte bounds, cancellation and lease checks remain in force.
  Such logical cache reads are not extra HTTP requests; benchmark counters must
  distinguish them. Oversized/nonadmitted results retain existing behavior.
- Hierarchy anchor uses the same orchestration when current verified capability
  is known; incoming can use its existing frozen context capability immediately.
  Other hierarchy operations retain current behavior. Preserve sibling merge,
  recorded anchor parent offsets, expansion, supersession and final publication.

Required focused regressions include unknown capability, known capability after
scope change, scientifically ineligible explicit bundle refusal, custom live batch refusal with ordinary custom-page behavior preserved, warm
retained columns avoiding a bundle,
cold bundle cache seeding and a subsequent fresh witness hit, invalid parent
preventing all publication, closing generation failure, and frozen hierarchy
anchor parity. This review approves the specified design, not unseen runtime
implementation or performance results.

## Initial implementation review

The inspected runtime diff connects live bundles to shared column orchestration
and reuses that orchestration for hierarchy anchor reveal. Current callers clear
retained pages on scope reset; the backend strips and validates bundle options,
rejects ineligible/custom live bundles, and checks closing generation before
attaching the shared identity. Warm retained geometry remains a scheduling hint;
cache reuse still requires a fresh witness. No additional current caller has the
same target-plus-ancestor shape without different semantics: first-epoch/range,
scientific tag target capture and arbitrary hierarchy restore remain distinct.

A review item was returned to the implementation owner: validate the live target
against the original requested path/offset or anchor, pinned revision, split order
and page limit, and validate parent DTO shape even without a cache owner. Parent
consistency derived solely from the returned target can accept a self-consistent
wrong-target bundle. The initial helper tests used minimal DTOs and did not
establish those checks. This paragraph records the initial review item; final
implementation/tests must establish its resolution before claiming full validation.

A deliberate compatibility limitation remains: an initial main-tree anchor on a
new mount has no learned capability and can use the legacy multiple requests.
Known current capability enables subsequent eligible bundles. Thus this wiring
does not make every navigation one HTTP request, and warm ancestor-cache reads may
be preferred even when batching is supported.

Final production review: the implementation now validates live target request
path/offset, requested revision, split order, page limit and anchor locator, plus
parent DTO shape and shared identity before publication/cache admission. The
initial wrong-target review item above is resolved in the inspected code. Boolean
and conditional-expression precedence was reviewed; no blocking correctness
finding remains in the four production files. This is read-only source review;
focused/mounted test outcomes and performance measurements remain attributed to
the implementation owner's separate runs.


## Implemented shared read and route experiment

The live tree endpoint now exposes the existing target/ancestor operation under
its existing witness scope. Main columns and live/frozen hierarchy anchor reveal
consume the same orchestration; Workbench columns retain that operation. The
frontend preserves the fresh-target/attested-cache path when retained parents are
available. Only capability learned within the current scope enables live bundles;
initial anchors with unknown support and arbitrary multipath restoration retain
ordinary reads. First-epoch, range and tag operations have distinct output and
scientific authority contracts and were not redirected to a browsing bundle.

Three unprofiled paired synthetic route samples per operation measured the exact
same pages, using production Flask serialization and the SQLite metadata index,
with SQL doubles. For date/parameter/cell grouping, cold separate/bundle medians
were 57.21/23.51 ms at 1k, 608.17/247.26 ms at 10k and 3392.04/1369.66 ms at 50k.
At 50k repeated reads measured 3515.02/1372.92 ms. Each compared operation changed
three requests and three scope builds to one. This is a dirty-source diagnostic,
not native MySQL, network, UI paint, H5 throughput or release qualification. Actual
warm renderer ancestor-cache hits can eliminate the parent HTTP calls already.
Raw controller and results are retained in the local kit; clean-source and package
evidence are recorded separately in the package handoff.

Independent design and final production review passed after adding full live
request/target and parent validation. Full frontend checks passed (910 cases);
a subsequent additional immutable-cache seeding case is checked separately.
142 tree/cache/identity/matching/Workbench/pending/recovery checks passed. Initial
backend invocation used three nonexistent suite names; the corrected run includes
all intended existing modules. Initial added mounted tests needed the harness's
animation-frame stand-in; the corrected full suite passed. No failure is counted
as passing evidence.


### Initial-load follow-up

The common loader now also consumes capability from the first fresh live target:
when several cold ancestors remain, it loads the deepest ancestor and its parents
in one bundle, then verifies exact original paths/offsets/revision/identity before
joining the original target or seeding cache. A three-level first reveal becomes
two reads; a known-capability reveal remains one. No discovery-only read or generic
error retry is added. Every hierarchy anchor now uses that same loader and merges
atomically while retaining siblings. Older/unsupported contexts fetch the complete
bounded ancestor path, potentially re-reading previously retained parent pages;
this explicit compatibility tradeoff replaces the former sequential partial loads.
Arbitrary multipath restoration remains distinct. Follow-up source review and
cold/offset/generation/cancellation/old-context tests are required separately from
the earlier 910-test checkpoint.
