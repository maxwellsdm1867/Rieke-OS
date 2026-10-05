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

Presentation is integrated. Tree-selection and group-save designs have independent
GO and parent authorization for bounded implementation; desktop close has a reviewed
packaging design; concrete Python package/profile/guard prerequisites await review. Remaining
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
