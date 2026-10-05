# Core module ledger

The [structured ledger](core-module-ledger.json) carries module purpose, owner,
interfaces, dependencies, implementation/proposal status, commits, correctness
detectors, existing benchmark mappings, replacement options and unmeasured gaps.
Dependencies describe conceptual integration relationships, not a direct import
graph; runnable benchmark cases and unsupported release requirements are separate.
It continues the completed local `018-core-survey/MODULE-LEDGER.md`; the historical
handoff, source and evidence remain intact. This is an index for a future module
map/version comparison, not a dashboard or another benchmark framework.

Baseline is `18975ad8240044273ca1f52783b20b8adbfd9a3f`; published stable remains
`e4aefd415dd4061af1d0856ba817628d4400122b` and main remains
`d47dcab534220fa940f917f66f90e71af4dd2f56`. This local work does not publish either.

## Implemented versus proposed

| Module | Current responsibility and interface | Status / next decision |
| --- | --- | --- |
| Tree selection | Reader owns exact routes, traversal and range mechanics; views own gestures/publication. | P03 implemented; preserve synchronous/scheduled behavior, exact order and stale refusal. |
| Mutation recovery | HTTP completion policy separates SQL commit, recovery and independent backup. | P04 implemented; client read-POST close barriers intentionally differ from server backup exemptions. |
| Export materialization | Shared format tail; callers retain frozen recipe, staging and publication. | P05 local implementation retained; native qualification and H5/Ovation work deferred. |
| Acquisition ingestion | `prepare` and `import_catalog` still combine H5/RetinAnalysis preparation with concrete catalog population. | Existing coupled implementation; generic intake remains proposed and deferred. |
| Catalog storage | DataJoint/MySQL acquisition and authored state; project lifecycle and derived typed indexes have distinct owners. | Transaction/deduplication policy still sits in importer composition; no universal storage facade exists. |
| Typed query/generation/leases | Existing typed reader, generation/cache lease and native authority owners. | Keep conservative exact method/binding proof; broad authority proposals not implemented. |
| Renderer resources | Context-specific request, activation, bounded cache and summary-job ownership. | Existing modules retained; unifying distinct freshness/profile policies is not justified. |
| Group save | Opaque session owns exact requests, retry and deferred release; tree preview owns query/validation. | Reviewed opaque-session slice `f7fc7b6`; keep-current alternative remains documented. |
| Presentation sessions | Five-operation owner hides route/fallback storage, checkpoints and pruning; App retains navigation/persistence composition. | Reviewed runtime slice `5e04525`; immutable baseline `48c2c47`, no speed claim. |
| Desktop lifecycle | Existing draft, startup, process and quit owners have separate obligations. | P07 enforcement adopted in `5d12cf0`; no runtime facade or protocol change. |
| Contract enforcement | Single adopted catalog and guard discover owners and affected tests. | Scoped desktop CJS runner added; direct imports do not prove transitive authority. |

The [adoption record](0.1.8-first-port-slices.md) and
[executable contract catalog](adopted-port-checks.json) retain operational detail.
Clean `5d12cf022b7c7ac6bc7a1727a467d14a8fd827b5` has **50 mapped desktop,
105 mapped renderer, and 81 focused Python passes**, zero skips. The Python total
includes 15 guard CLI tests. Deliberate in-memory UUID and creation-time mutations
each cause one expected registered-handler assertion failure. These are scoped
correctness results on local Node 24.13.0 and focused Python behavior tests on 3.11.13 (JavaScript guard
orchestration uses local Python 3.14.3), not a new full-suite,
CI Node 22.12, native process-exit, packaged IPC or performance qualification.
The initial sandbox loopback EPERM receipt is retained separately; the authorized
rerun uses only owned temporary sockets and fake service processes/transports.

Historical local189 evidence remains 1,471 Python passes/36 skips and 698 frontend
passes. Published e4 browser/native/CI evidence remains tied to e4. Neither is
relabeled as this candidate's qualification. No paused native/export test ran.

## Replacement and integration decisions

An earned interface permits a substantially better implementation. Existing
internals are not preservation goals: rewrite when a materially simpler, more
robust or more efficient alternative is demonstrated under the same observable
contracts. Do not extract or retain a wrapper merely to preserve an implementation.
The ledger records a replacement option for every area, including keep-current
where it already provides useful locality. No defect or speedup is claimed merely
because ownership moves.

Integration capabilities remain explicit: tree views can change without owning
pagination; recovery panel and editor can converge on exact command identity;
format callers can share materialization without transferring publication;
desktop preferences can restore presentation without granting scientific readiness.
Their limits matter: custom query policies need conservative fallback, a saved
command may lack backup coverage, uncertain quit may retain recovery, and a test
adapter does not prove native commit/exit/durability.

## Measurement and whole-app costs

Use the existing [benchmark guide](../dev/benchmarks.md) and
[registry](../../benchmarks/registry.json): suite `1.0.3`, fixture
`native-truth-v1+mounted-workflow-500-v1`. No new benchmark executed here. The JSON
uses null baseline/candidate metrics and explicit unmeasured status, never zero or
invented per-module timings. Mounted first/return cases measure content/authority
for mocked rows, not native paint or scroll; native navigation, tag latency and
intake throughput remain unsupported release requirements.

Before optimizing a module, bind compatible baseline/candidate receipts to exact
source, suite, fixture, runtime, OS and hardware. Compare scientific correctness
first, then startup, first useful result, memory, disk, build, backup and shutdown.
Check whether warm read gains shift cost into build/open, hidden cache retention,
backup lag or exit. None of those whole-app cost shifts has been measured for this
increment. Add justified cases only to the existing registry; no fabricated budget
or historical timing retrofit. H5/Ovation/native export remain deferred.

## Import and database: current versus proposed

The importer does not yet hand a format-neutral bundle to an independent database
module. `recording_workspace.prepare` calls the H5-specific Symphony parser and
produces RetinAnalysis-shaped metadata. `import_catalog` directly acquires the SQL
advisory lock, creates connection-local collision indexes before the transaction,
checks source identity/deduplication, calls RetinAnalysis population, verifies stored
relationships and writes the audit event. Later workspace files and protocol
finalization are separate from that committed transaction. Cleanup failure must
not imply rollback of a committed catalog.

Project database provisioning/ownership (`workspace_project_database` and
`workspace_native_mysql`) is distinct from these write semantics. The typed SQLite
index/generation/lease modules already form useful derived-read modules; they do
not replace authoritative MySQL/DataJoint storage or choose scientific membership.
The structured ledger records exact source pointers, coupling and contract gaps.

A possible next design is one purpose-specific catalog-ingest transaction owner
behind the existing `import_catalog` operation. It could hide lock/collision lookup
lifetime, population and identity proof, while its caller keeps preparation and
post-commit finalization. This is a read-only candidate, not an implemented port.
Keep-current remains valid until the proposed interface removes meaningful caller
knowledge and preserves same-source revalidation, collisions, rollback, unknown
commit and partial-success reporting. No generic repository, schema rewrite or
new importer is proposed. Existing surveys informed this assessment; bounded source
reads confirmed the current coupling. No import/H5/native fixtures ran.

## Comprehensive core contract review

The structured ledger contains 59 contract records grouped into five review areas:
14 frontend, 16 scientific command/recovery/export, 10 import/storage/query/trace,
18 desktop (including the lifecycle overview), and one contract-enforcement record.
These are four product areas plus one cross-cutting engineering area, not a formal
module hierarchy. Records cover runtime owners, shared contracts, overviews and
qualification obligations; they are not 59 independently replaceable modules. The
existing overview table above summarizes the largest ownership areas; the JSON
contains the detailed records. Each record states inputs/outputs, identity/type/
order/unit/provenance rules, errors and partial success, freshness, transaction/
idempotency rules, cancellation/lifetime, caller dependencies, integration
capabilities and change rules. Source pointers and existing tests are separate
from exact executed evidence. New fault ideas remain labeled unrun.

Four independent read-only area reviews reused the completed survey and inspected
current source. The ledger records their input hashes. Conceptual dependency edges
can be reciprocal; they do not claim an acyclic import graph or transfer authority.
The interactive local HTML is generated from this ledger and the unchanged
benchmark registry. It is a review artifact, not another contract or benchmark
registry. Source-qualified evidence remains attached to its original commit.

This review documents current contracts comprehensively; it does not implement
every proposed separation or close every qualification gap. Open decisions include
format-neutral intake, the actual importer/catalog transaction seam, complete raw
field accessibility, conservative query authority, native durability and process
exit, and performance baselines. Changes beyond the reviewed P07/group-save/
presentation increments require bounded design review. No generic repository,
new importer, schema migration or native qualification was performed.

The presentation integration candidate `df40a19` passed 170 mapped renderer tests,
15 guard CLI tests, nine behavioral fault checks and the frontend build, with zero
skips. Its immutable 17-case App baseline remains unchanged. Final combined
source verification is recorded outside the repository under `task-4/evidence`.
All seven whole-app cost shifts remain unmeasured; benchmark criteria are not
measured results or calibrated latency targets.

## Presentation folder pilot

The [presentation module](../../workspace-app/src/presentation/AGENTS.md) now
colocates the named public factory, contract documentation, owner tests and private
pruning implementation. App composition tests remain at their existing seam.
This is one filesystem pilot, not whole-codebase reorganization or a depth/speed
claim. The JSON record includes its exact public entry, private root and source-review status. Resolver closure includes exact historical virtual-import
mappings and explicitly scanned outside-source test tooling; it never exempts
mapped targets from private import checks. Independent source review is GO within
the declared syntactic scope. Exact clean-commit verification belongs to
`task-4/evidence/presentation-folder-pilot/final-binding.json`; check that receipt
for execution status rather than treating this design record as a test result.

A fresh agent, given only a Data Stores return-view scenario and the repository,
followed root/frontend/module navigation to the public factory, ownership limits,
and relevant contract/composition tests and commands. This is one successful
scenario, not a whole-codebase claim. The agent identified the distinction between
sidebar return, history and draft restoration, and the harness's DataStores probe.

Next proposed sequence: tree selection reads (existing public reader and real
HTTP/test seam), then group annotation save/recovery (review its three public
surfaces and singleton lifetime). Python/desktop folders require separate
packaging-aware designs. These are ideas for review, not automatically started
refactors. The pilot adds no measured performance or behavioral-depth gain.

The implementation commit `20f04c63496031e7656db5ce8baef57ab82c8ad0`
passed 192 mapped renderer tests, all 754 frontend tests, 16 Python guard tests,
the complete architecture guard and the frontend build, with zero test skips.
The 22 guard/discovery cases include deliberate import/resolver/discovery faults.
Source checks preserve the original owner body and helper, moved contract tests,
App characterization/harness, virtual historical fixture/harness, lockfile and
benchmark registry/runner. This ledger update records those exact source results;
it does not relabel them as executions on a later documentation commit.

## Active whole-codebase organization worklist

The JSON ledger's `organization_rollout` is the canonical execution worklist. Its
cycle is goal/contract → actual file and local-contract moves → public-seam and
fault tests → independent review → local integration. All existing contract
records have work assignments; actual runtime-file coverage is still pending.
Work groups do not imply one module or folder per group or per record.

Presentation, tree-selection and group-save folder increments are locally integrated
and verified. Desktop close has a reviewed packaging design; concrete Python
package/profile/guard prerequisites await review. Remaining
frontend, Python and desktop responsibilities stay explicitly queued. Keep-in-place
choices need reasons and remain navigable; ledger labels alone do not complete
filesystem organization.

Every selected module needs nearby public contract/JSDoc, executable call/error
examples linked to seam tests, local AGENTS, dependency/ownership limits, exact test
commands and canonical benchmark links. Retain real caller integration; private
algorithm tests may supplement but not replace public behavior detectors.

Completion also requires reviewed exact-candidate assembled-app E2E: isolated
synthetic project, actual pages/tree/trace oracle, tag persistence/export readback,
normal quit/reopen and owned-resource cleanup. This gate is unrun. It does not
resume paused unrelated native experiments or imply speed/release qualification.

### Tree-selection and group-save folder increment

The actual owners/tests now live in `workspace-app/src/tree-selection/` and
`workspace-app/src/group-save/`, with public JSDoc, local AGENTS and executable
consumer examples. Caller imports and the actual Vite/module-lookup seams follow
those paths. Lexical helpers, shared request shaping, preview, UI and undo remain
with their existing owners; no facade or additional runtime adapter was added.

Both worker slices received independent source GO. Focused checks and deliberate
behavior faults passed at their recorded worker source hashes. Combined source `0b1431f3098970f2cb24af0ace5ed7f33360ab18` passed
758 full frontend tests, 209 mapped frontend tests, 16 Python guard tests (zero
skips), all-language guard and production build. The 13 policy tests include both
new folders’ private/export/test-import faults. Exact source-review GO and all
413 guarded hashes are bound in `evidence/organization-rollout/final-binding.json`
(outside the checkout), SHA-256
`102c4848bad3ae86b106b57b413b39de1d4bfdc19a8445b67c1bff23923cc768`.
This documentation update does not relabel those runs as later-commit executions. Prior ledger review/receipt fields remain
historical; live paths and organization status are explicit in the JSON records.
No native, packaged-app or performance qualification follows from this increment.

## Finite remaining path coverage

The [path companion](core-module-paths.json) assigns the current frontend source,
Python/tools and desktop inventory exactly once. It is part of this ledger: 465
runtime/configuration paths (279 frontend, 144 Python/tools, 42 desktop), with tests
and exclusions separately accounted for. There are 318 proposed moves, 131
keep-in-place decisions, 12 deferred paths and 4 already organized runtime files.
These are path counts, not module counts or a completion percentage.

Whole completion requires every eligible assignment to reach actual implementation
or a reviewed, navigable keep-in-place outcome, with public contracts/examples,
meaningful tests, packaging/discovery closure and independent source review.
Documentation, contracts, benchmarks and historical evidence already have purpose
roots and retain their identities. Final exact-package UI/native acceptance remains
mandatory and unrun. No individual slice closes the whole goal.

### Desktop-close folder and retained tooling guidance

Reviewed implementation `18b3de9f9d0219a97b0d846274dddcbc8fc55b97` is integrated
at `1b456ee44a627a683844708dc4a8c7528c26911c`. Two public CJS owners and their
original tests moved byte-for-byte to `desktop/close/`. All caller/interceptor
paths, exact packaging entries, narrow discovery and release planning moved with
them. Exact-candidate evidence records 62 mapped desktop and 33 Python
guard/planner passes, zero skips, plus detected window-correlation and false-clean
Quit faults. Source packaging checks cover exact default/preview selection and
staged direct imports; actual ASAR/native qualification remains pending.

[Retained tooling guidance](../../tools/AGENTS.md) now links all 48 existing runtime
tool paths with their interfaces, dependencies, command/test entrypoints and
qualification limits. Its source-only review checked 91 links and 12 named test
methods. No tooling runtime or benchmark qualification is implied. The path
companion preserves baseline assignments and records accepted current-path changes.

### Multi-entry guard prerequisite

Source `373f286e3f0d7bb0ee8ccf9a11a4a5d47cfa9e85` supports multiple explicit
public files per coherent frontend folder, with each file's exact exports guarded.
The three current module registrations migrated without semantic changes;
catalog versions 1 and 2 retain their behavior. Independent source review and
31 JavaScript operational / 18 Python guard tests passed, zero skips; all-language
guard and explicit-base planning passed. Broad mapped application tests were
planned rather than executed for this tooling-only change. No runtime, parser or
benchmark code changed. Python package policy remains a separate prerequisite.

### Renderer drafts and desktop state integration candidate

Renderer drafts now groups the existing factory and real React hook behind their
separate public entries. Desktop drafts and startup preferences retain distinct
folders and owners. Independent source review confirmed behavior preservation,
original-suite retention and exact worker evidence (74 renderer checks; 48 desktop
and 37 Python checks). Four renderer and two desktop deliberate faults were
detected. Combined validation passed at `ebdbfdb9b2dc5881973eb3955449b209c3c84a7e`:771 full frontend,222 mapped frontend,81 mapped desktop,37 Python guard/planner,20 Python profile and9 Node profile tests; zero failures/skips. Build, guard and explicit-base plan also passed. Exact binding: `d15a766f65167f82fe409396a4a2c6565899ca2ede54667477be70b893c37b82`. A missing-PYTHONPATH first profile attempt is preserved separately; corrected invocation passed.

The profile-tooling prerequisite also passed independent review after three
regression fixes (20 Python, 9 Node checks); the shipping manifest stays v1 and no
Python runtime relocation has occurred. Historical source pointers and receipts
remain unchanged; JSON organization fields and path overrides locate current code.
All seven whole-app costs remain unmeasured. Final assembled E2E is blocked on a
reviewed no-force-kill launcher implementation, pinned runtime qualification and exact package gate. An existing Python3.11.13 source-test runtime was located; that is not final app/native qualification.

Benchmark path prerequisite integrated as `7d8c68d` from reviewed `9c92a24`: revision-owned recipes and four exact legacy runner hashes preserve historical suite identity.21 source cases passed plus one separate YAML workflow case using existing Python3.11.13; three deliberate faults detected. Initial missing-PyYAML evidence remains preserved. No benchmark workload ran, no registry/schema changed, and whole-app costs remain unmeasured.

### Finite organization progress at `76962c6`

The 20 work items include 4 locally integrated items (presentation, tree selection,
group save and desktop close), 6 partial/active items and 10 queued or keep-current
design items. Seven responsibility folders are verified: presentation, tree
selection, group save, renderer drafts, desktop close, desktop drafts and startup.
Renderer drafts, startup and drafts complete only parts of their broader work items.

The original 465 runtime/config paths partition into 10 organized paths, 312
proposed moves, 131 keep-in-place decisions awaiting per-scope acceptance, and 12
explicitly deferred paths. These are path counts, not module-depth or completion
percentages. New tests/docs are tracked as accepted increments, outside that
baseline count.

| Area | Organized | Proposed moves | Keep decisions | Deferred |
| --- | ---: | ---: | ---: | ---: |
| Frontend | 6 | 243 | 28 | 2 |
| Backend/tools | 0 | 57 | 77 | 10 |
| Desktop | 4 | 12 | 26 | 0 |

Active next increments: tree-layout folder after reviewed real-hook
characterization; desktop integrity folder under independent source review;
Python v4 reader/fixture implementation before the first recovery move. Retained
tool guidance and provenance/packaging prerequisites are integrated but do not
count as runtime folder completion. Final assembled UI/native/package acceptance
and all seven whole-app cost measurements remain outstanding.

### Verified layout and integrity increment at `4a4867ee`

Exact candidate checks pass: 779 full frontend, 264 mapped frontend, 102 mapped
desktop and 38 Python guard/planner tests, with zero failures/skips. Build, guard
and explicit-base plan also pass. Binding SHA-256: `6eaa828f191653a35a7bbee144d1b4dfd2690c42d43eeac6efaa616c72b44b88`.
The invalid-receipt test gap found in review was corrected before integration;
production bodies and original obligations remain preserved.

There are now **9 verified responsibility folders / 14 organized baseline runtime
paths**. Remaining classifications: 308 proposed moves, 131 keep-in-place decisions
requiring acceptance and 12 deferred paths. The 20 broad work items still comprise
4 integrated, 6 partial/active and 10 queued/keep-current designs. Layout and
integrity complete only parts of those broad work items. The prior snapshot is
historical; JSON progress_snapshot contains the current counts.

Next: reviewed navigation/update slices, corrected Python v4 reader before any
Python move, and concrete assembly/runtime preparation. Launcher source is
reviewed at `54771398`; execution remains on hold pending the final candidate,
package/runtime qualification, synthetic preflight and reviewed quiet window.
No new performance measurements or native acceptance are implied.

### Navigation, updates and reader prerequisite at `268de3e2`

Exact candidate checks pass: 780 full frontend, 269 mapped frontend, 130 scoped
desktop, 55 Python guard/planner and 21 benchmark-source tests; zero failures or
skips. Build, guard and explicit-base plan also pass. Binding SHA-256:
`bd516fd5a16c6efdd9a6c68340dd73f7f0c8daad53f4019d58bbd28c8300b909`. Benchmark-source tests execute mocked workers, not measurements.
Original updater host/native suites remain explicitly unrun.

Current finite inventory: **11 verified folders / 19 organized baseline runtime
paths**, 302 proposed moves, 132 keep-in-place classifications and 12 deferred
paths. The shared root updater validator changed from proposed relocation to a
reviewed keep rationale; this is not an additional organized folder. Broad work
items remain 4 integrated, 6 partial/active and 10 queued/keep-current designs.
The nine functional areas discussed with the user describe responsibilities, not
nine completed physical modules.

Python reader A is integrated and reviewed, including explicit module-shim and
lexical-scope regression fixes. Shipping catalog v3/profile v1 remain unchanged;
no Python runtime relocation occurred. Recovery move B needs its refreshed exact
loader bindings and separate gate. Existing runtime reuse is a preparation
candidate pending full byte verification and static audit; final application
assembly/imports/UI acceptance and all whole-app costs remain unqualified or
unmeasured.

## Parallel source wave awaiting aggregate verification

Source checkpoint `50ff9bd77b72c7a4e39444b4f2c653cbb0a27307` integrates reviewed search activation, requested summaries, tree ancestors, scientific presentation folders and the byte-identical Python recovery registration package. Desktop installation/startup/state owners have explicit KEEP rationale and injected public examples. The JSON pending-wave snapshot and path companion record current paths; the earlier aggregate snapshot and receipts retain their original source identity.

Current baseline-path dispositions: 139 keep-in-place, 241 move-proposed, 73 organized, 12 deferred. These are path classifications, not completion or depth metrics. Shared mappings, aggregate build/tests, HTTP completion checks and final assembled-app acceptance remain pending. Independent owners proceed in parallel; one integration owner serializes shared edits. Interface review emphasizes clear caller knowledge and progressive disclosure, not export counts or implementation size.

## Frontend finite A/B/C current path composition

The current path companion composes the 52/72/61 runtime moves in the finite
remaining frontend plan: A/B from `d0ae570` to `41230b1`, and C from `d0ae570`
to `61b6e1f`. These are 185 runtime files, 28 companion tests, 16 local guides
and one new summary-job public-example test. All 185 planned runtime paths occur
exactly once in the composed move map. The 279 baseline frontend paths now
partition into 248 organized, 29 retained and two deferred; zero proposed moves
remain. Retained paths still require their own acceptance gates.

`source_paths` and `existing_tests` identify current module locations; historical
`source_pointers`, review verification, receipts, baseline inventories and progress
snapshots retain their original source identities. New folder guides are discoverable
from the root module guide and frontend navigation. Physical grouping preserves
existing file-level APIs and does not adopt additional architectural ports.

Exact combined source review and aggregate checks remain pending for this
composition. Backend organization, packaging, native and assembled-app gates
remain open; no timing, release or whole-app qualification is asserted.


## Backend finite current path composition

Source candidate `572d3ffed71e71a0776632a120cbb89ec569a961`, integrated as
`9723d46`, composes 50 existing production leaves into metadata, decisions, backup,
navigation, projects and workbench packages. Six existing tests move with their
owners in that candidate; root additionally colocates the unchanged backup and
workbench diff suites, giving eight current test moves. Six inert production initializers bring the explicit production profile from 92 to
98 files. Package contracts remain separate and preserve file-level interfaces,
import timing, exact scientific authority and distinct transaction lifetimes.

The finite backend/tools baseline of 144 paths now partitions into 51 organized
(including the earlier mutation-recovery owner), 83 retained and 10 deferred;
zero proposed moves remain. The six retained decisions from the remaining plan
are project creation, project servers, unmount, portability, protocol-state proof
and snapshot composition. Snapshot composition keeps its documented executable
path and `__main__` command; the original proposed move remains historical.

The JSON ledger adds current backend path/guidance fields without changing baseline
source pointers, metrics or prior receipts. The frontend's 185-move composition
and its 248/29/2 baseline partition remain unchanged. Actual checkpoint leaf
bytes and basename labels conservatively change the opaque source contract; old
receipts refuse reuse and are not rewritten. NativePreview retains the historical
flat predicate import and separate baseline root. Current benchmark source-recipe
and catalog adoption remain separately owned integration work.

The source candidate records 173 exact normalized AST comparisons, two comparator
files byte-identical to the reviewed two-root fix, 11 pure predicate/undo/diff tests
and three inert two-root import tests. Those receipts describe that source candidate
only. This metadata update runs JSON/path checks and imports no product modules.
Exact combined source review, catalog/discovery closure, runtime/native/scientific
qualification and final assembled-app acceptance remain separate gates; whole-app
costs remain unmeasured.

## Retained background trace execution

`python/workspace_trace_workers.py` is a new retained execution helper, not a move
from the finite backend baseline. The [local contract](trace-worker-execution.md)
keeps admission/source authority in WorkspaceService and records process/close
ownership. The application profile includes the helper; historical finite-path
counts and source receipts are unchanged.

## Workbench loading and tag coverage follow-up

The current App composition mounts incoming review independently of the main
protocol summary and saved main-tree layout. Main inspection and export retain
their readiness gates; frozen review continues to obtain its own context. This
removes a serialized presentation dependency, not a measured native latency
guarantee. The local incoming-workbench and protocol-tree-layout guides record
the composition and delayed/failed-summary examples.

Frozen tree pages may include exact descendant shared-tag coverage from the
Workbench's already captured annotation snapshot. The existing response-end
scope check still owns freshness. The tree view treats complete, partial and
unavailable coverage separately and does not equate tags with merge membership
or scientific approval. See the backend workbench/navigation contracts and tree
browser guide for the narrow optional callback and presentation fences. The
catalog adds the mounted coverage regression; the reviewed tree-page observer
ASTs, identities and targets are unchanged while source hashes are updated.

New audit events now fingerprint the current organized frontend paths. Previously
recorded audit events remain unchanged. The source-install workflow fetches the
Git history required by historical benchmark tests; recovery subprocess tests
use the organized backup module. Chooser validation tests distinguish required
launch resources from MySQL's later scientific activation and full byte audit.
These changes preserve the existing organization rather than restoring flat
compatibility modules.

Reviewed Python AST identities retain their existing Python 3.14 encoding through
an explicit serializer. This removes dependence on `ast.dump` defaults when CI
uses Python 3.11; it does not regenerate catalog AST hashes or relax source-byte,
selector, provenance or owner-byte checks. The tooling guide and guard examples
cover literal empty lists/None and changed nonempty arguments and keywords.

Project public examples retain their standalone import guard and upstream
stand-in in an isolated child when invoked by combined test discovery. This
prevents their process-wide substitutions from affecting neighboring recovery
tests. The exact delegated import AST remains unchanged; its source hash and
catalog explanation record the discovery wrapper.
