# Dedicated project worker heap: investigation and candidate

## Observed cost

The ordinary million-row workflow uses 20,000 active-protocol epochs and three
samples for each of thirteen actions. Two GitHub comparisons of the predicate
cache correction flagged incoming Select all, despite passing exact selection
and all query checks. The original failures remain in runs 38519879374 and
38521289859; they are not replaced by the diagnostics below.

Request profiling put the selected epoch-page reads below 1 ms. The surrounding
fresh authority contexts copy and validate much larger frozen recipes. A separate
collector callback identified generation-2 scans, including a 412 ms pause during
Select all. The published 0.1.13 source also paused there for 488 and 453 ms.
Each diagnostic run had ten generation-2 collections. These observations explain
the timing variation; they do not turn either failed comparison green.

Local diagnostic medians (same actual-million/20k fixture, ordinary samples,
collector callback enabled; dirty harness, not qualification):

| Action | Published 0.1.13 | Predicate cache correction b82de83 |
| --- | ---: | ---: |
| Incoming Select all | 1,391.8 ms | 987.8 ms |
| Cell-equality predicate search | 6,357.0 ms | 3,150.5 ms |

Raw evidence is retained under the task's `disco-performance-flags-20261013`
evidence directory: `select-gc-0113`, `select-gc-b82`, and
`select-profile-b82-provisioned`. No samples are subtracted or filtered.

## Candidate and review

`workspace_process_heap.install` opts a dedicated single-project worker into
Python's permanent collector generation after loading. Desktop project workers
and the disposable workflow server invoke the same production helper. Shared
library interpreters and the launcher do not opt in. Ordinary cyclic collection
stays enabled with unchanged thresholds. The measured startup cost includes the
initial full collection, and refresh timing includes thaw/collect/freeze.

The collector skips the whole loaded heap, not only metadata. Reference counting
still releases acyclic objects. Cycles entirely within new request objects remain
collectible; cycles involving frozen mutable objects wait until refresh or close.
This is the documented behavior of [Python 3.11 gc.freeze and gc.unfreeze](https://docs.python.org/3.11/library/gc.html#gc.freeze).
It is a latency/lifetime tradeoff, not a general memory bound or a change to
scientific freshness. Every refresh thaws first; success collects and freezes
the replacement state, while failure leaves ordinary collection in effect.
Shutdown and partial-load cleanup thaw even if earlier worker cleanup fails.

Independent Spec and Standards reviews checked freshness, custom-reader behavior,
source packaging and lifecycle paths. Standards review identified the partial
cleanup exception path; it was changed to release collector ownership in a
`finally`, with an injected-failure test. A performance/design reviewer checked
the mechanism and suggested the allocation follow-ups below. A real Flask probe
found initial and repeated-refresh request objects reclaimed after teardown.

Subprocess tests cover new request cycles, cross-generation cycles, repeated
refresh reclamation, failed refresh, competing ownership, close, unchanged GC
settings and integration with the actual `WorkspaceService.refresh` method.
These tests do not establish a bound for every concurrent native desktop workload.

The source-projection compatibility entry is exact: removing the refresh lifetime
wrapper and its import leaves the prior whole-file AST unchanged. Projection
construction, recorded values, verification and codecs retain their prior witness.
The old sealed cache is never rewritten or relabeled.

## Acceptance and next proposals

The new baseline must name a clean corrected commit and retain raw ordinary
action samples, the previous iteration and old pinned reference. Full query,
correctness and workflow comparisons must pass before updating the active pin.
Startup, refresh and peak memory are separate evidence; no latency threshold,
sample count or correctness oracle is relaxed. Native packaged behavior remains
unqualified until separately exercised.

Review-backed follow-ups, not implemented by this collector change:

- Avoid repeated canonical recipe hydration within one existing Workbench
  `_context_reads` lifetime. Keep independent opening and closing scopes.
- Use narrow internal binding-header/predicate projections where full detached
  public recipes are not consumed. Preserve stored-recipe verification, public
  mutation isolation, override detection and custom-reader fallback.
- Measure repeated query-result and protocol-state projection allocation behind
  their existing generation/binding proofs. Never cache an authority receipt
  across responses merely to improve timing.

The profile saw sixteen recipe copies during selection. Their atomic member
dictionaries are normally untracked by CPython; this is allocation/CPU work,
not evidence of 320,000 additional tracked cyclic objects. Each proposed reduction
needs its own correctness review and ordinary before/after measurement.
