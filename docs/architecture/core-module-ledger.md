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
| Typed query/generation/leases | Existing typed reader, generation/cache lease and native authority owners. | Keep conservative exact method/binding proof; broad authority proposals not implemented. |
| Renderer resources | Context-specific request, activation, bounded cache and summary-job ownership. | Existing modules retained; unifying distinct freshness/profile policies is not justified. |
| Group save | Opaque session owns exact requests, retry and deferred release; tree preview owns query/validation. | Reviewed opaque-session slice `f7fc7b6`; keep-current alternative remains documented. |
| Presentation sessions | App owns fallback/maps; draft/navigation modules own intent and publication. | Proposed deepening only; compare session owner against smaller checkpoint/pruning helpers. |
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
