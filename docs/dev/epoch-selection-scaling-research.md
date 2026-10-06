# Frozen tree selection scaling investigation

Date: 2026-10-06. Source inspected: `238e15cc954ed12c301f42b4aa983802efc3a9e8`.
This is a local source investigation and preimplementation design review, not
desktop or H5 import qualification. Line references below identify that baseline.

## Finding

The bounded selection endpoint traverses ordinary 60-row pages recursively. Each
descendant request calls `TreePages.page`, which resolves the full eligible scope
again before locating its branch. It also builds ancestor labels and response
records that selection discards. The 1,000-epoch output bound therefore does not
bound the number of whole-candidate reads. See [selection traversal](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/workbench/workbench.py#L925),
[scope construction](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/tree_pages.py#L336), and
[page construction](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/tree_pages.py#L403).

The retained scope cache deliberately falls back for annotation filters or
unproven structural policies; frozen services clear their scope cache and install
their own binding/curation providers. General cache eligibility must not be relaxed
to fix this. See [scope admission](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/tree_pages.py#L257),
[structural reader proof](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/tree_pages.py#L24), and
[frozen service](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/workbench/workbench.py#L489).

The diagnostic [raw summary](../../../epoch-scale-diagnostic-2026-10-06T10-54-26/summary.json)
measured 349.34 ms for selecting 1,000 epochs from one cell, 3,510.91 ms for the
same count across 100 cells, and 3,567.75 ms for selecting 1,000 from 10,000
available epochs. These required 20, 203, and 18 scope builds respectively;
scope construction consumed 83.1%, 89.4%, and 87.2% of selection time. The
50,000-epoch case exceeded its 15-second traversal budget. Measurements use
production Flask handlers with disposable SQL doubles and a real SQLite metadata
index; they exclude setup and are not native MySQL, network, paint, or import timings.

## Alternatives and recommendation

| Approach | Benefit | Cost / boundary |
| --- | --- | --- |
| A. Exact bounded selection from one resolved scope | Eliminates repeated membership/projection reads and discarded page/label construction | Must preserve DFS grouping order and all typed branch semantics |
| B. One prepared scope for a response-local page batch | Removes repeated scope reads while retaining existing page results; useful for target plus ancestor navigation | Selection still constructs unnecessary descendant pages; prepared scope must include every accessed field |
| C. Legacy traversal for custom readers | Preserves adapters whose overrides define behavior | Retains prior cost; must remain an explicit fallback rather than silently bypassed |

Recommend A for selection and a narrow B for target/ancestor navigation, with C
for custom pager implementations. The navigation owner should provide a bounded
selection method and a response-local column-page helper. Workbench owns the
existing authority lifetime and response publication. This keeps scientific
membership in its current owner and avoids a persistent frozen-data cache.

**Preimplementation review:** approved for this scope, subject to the invariants
and checks below. This review covers the algorithm and ownership boundary; it
does not establish implementation correctness or release qualification.

## Required invariants

1. Resolve scope through the existing authoritative reader once. Preserve
   `_tree_rows`, filter validation, source eligibility, binding revision and
   scoped annotation generation behavior. An internal all-split projection must
   expand joint components; do not reuse a depth-limited cache entry as though it
   contains all fields. See [scope projection and revision](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/tree_pages.py#L336).
2. Preserve exact typed values and missing/null rules through `TreePath`,
   `value_key`, and `field_value_order`. Built-in scalar null is missing; dynamic
   null is recorded; joint component presence remains explicit. Share the
   existing bucket/group ordering code rather than copying a new sort model.
   Block order uses source block timestamps; leaf order uses date, time and UUID.
   See [TreePath](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/tree_pages.py#L174),
   [group sorting](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/tree_pages.py#L442),
   [leaf ordering](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/tree_pages.py#L234), and
   [typed/joint ordering](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/tree.py#L97).
3. Validate malformed path/revision/count requests as before; reject stale
   revisions, nonexistent branches, actual oversized groups and count mismatch
   before descendant enumeration. Return exactly the existing DFS UUID order,
   with completeness and uniqueness checks and the 1,000 result bound.
   See [bounded selection contract](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/workbench/CONTRACT.md#bounded-branch-selection-read).
4. Keep `guarded` → `checked` → `finish` unchanged: annotation/database locks,
   opening generation, frozen candidate scope and closing generation/candidate
   checks remain mandatory. Closing failure must discard UUIDs/pages. Selection
   creates no draft, annotations, acceptance or export authority. See
   [read guards and finish](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/workbench/workbench.py#L659).
5. Request-local column pages can reuse a scope prepared for the target because
   ancestor paths require prefixes of its projection. Anchor lookup needs all
   splits. Prefer a private page-from-scope renderer behind an explicit helper;
   never replace the service's `_scope` dynamically or retain the scope beyond
   the guarded response. Existing counts-only and full-summary responses must
   remain identical. See [column batch contract](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/workbench/CONTRACT.md#fresh-column-navigation-batches).
6. Detect custom/overridden pager `page`, `_scope`, and `_build_scope` methods
   before using a canonical shortcut. Preserve legacy traversal/individual page
   calls for them. Custom service readers still run through the canonical
   scope builder's existing override fallback; exact type or method assumptions
   must not bypass them. The baseline oversized-group test deliberately patches
   `TreePages.page`; retain that contract check. See
   [navigation override contract](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/CONTRACT.md#L24)
   and [selection tests](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/tests/test_workspace_workbench.py#L65).

## Verification and benchmark plan

- Compare optimized ordered UUIDs against a complete independent page DFS across
  more than 60 branches and leaves, root and nested paths, many cells, dynamic
  typed values, explicit null/missing, joint fields and block chronology.
- Assert one scope resolution for the canonical selection path and no
  descendant label rendering; verify target/ancestor batch bodies equal separate
  fresh page reads, including anchor and explicit parent offsets.
- Preserve bad-input, actual oversize, stale revision, opening/closing scope,
  annotation mutation, read-only state, and custom reader fallback tests.
- Rerun the same diagnostic script, fixtures, runtime and workload matrix against
  baseline and candidate sequentially. Record source identity/dirty state, all
  raw samples, timeout status, scope/page call counts and medians. A timeout is a
  lower bound, not an exact speedup denominator. Separate setup and workload cost.
- The algorithm still scans eligible candidate membership once, so 50,000 or
  100,000 candidates need not become constant-time. Report residual root-page
  and scope cost alongside selection gains. Retain the 1,000 selection cap.

Repository performance/release requirements remain governed by the
[benchmark guide](benchmarks.md); these disposable synthetic results do not
qualify installed application responsiveness or H5 parsing throughput.

## Implementation review and next scaling experiment

Read-only review of the experimental A/B implementation found no blocking issue
in the inspected diff. `_group_buckets` preserves the original page grouping
algorithm; selection uses one all-field scope, validates revision/path/count,
then traverses exact groups and chronological leaves. `column_pages` shares the
projection only within its call; ancestor prefixes are covered by the target
projection, and anchor reads already request every split. Method-identity guards
include `page`, `_page`, `_scope` and `_build_scope`; custom pager implementations
retain the original traversal. The Workbench opening/closing sequence remains
present. This is a source review, not a test result.

A/B removes multiplication by descendant-page count. It does not remove the
remaining candidate-size cost:

- `ProtocolWorkbench.context` rebuilds base/proposed/previous/incoming/pending
  maps, checks current fingerprints and source eligibility, and hashes incoming
  membership and relevant fingerprints. It runs at both opening and closing.
  See [context](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/workbench/workbench.py#L215) and
  [finish](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/workbench/workbench.py#L721).
- `ExplorerHistory.get` deep-copies recipes and verifies their content checksum;
  repeated proposal, baseline, origin and binding reads can therefore copy/hash
  the same large sealed membership repeatedly. These checks establish integrity;
  they are not dispensable overhead. See [recipe reader](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/decisions/explorer.py#L215).
- `selection_revision` sorts and hashes the complete eligible membership, while
  the selection projection currently requests all split components across that
  membership. This is at least linear data work, with a sort in revision creation,
  even when the selected result has at most 1,000 epochs. See
  [selection revision](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/disco/navigation/tree_pages.py#L238).

**Next measured experiment:** after the uninstrumented A/B comparison, run one
separate profiling pass at 10,000 and 50,000 candidates with a fixed 1,000-epoch
selection. Attribute cumulative and exclusive time to opening/closing `context`,
`ExplorerHistory.get`, `_build_scope`, `DiskMetadataIndex.values`,
`selection_revision`, and grouping. Also compare fixed dataset size with 1 versus
many cells, and fixed selected count as dataset size grows. Keep profiler timings
out of the headline unprofiled speedup.

Do not monkeypatch pager methods to measure candidate call counts: the intentional
method-identity guard will route those measurements through the legacy fallback.
Use an external Python profiler/call statistics or another observation mechanism
that leaves method identities unchanged.

If projection dominates, the best narrow follow-up is a two-stage projection:
resolve the existing full eligible scope and its revision, load only fields needed
for the requested path, refuse oversized membership, then project remaining split
components for the bounded selected UUIDs. Compare exact DFS output and peak
memory against the all-fields implementation. Root selection above 1,000 should
be refused before projecting descendant fields. This preserves the current
membership/authority model while reducing work for expensive dynamic metadata.

If recipe/context work dominates, investigate generation-bound reuse of verified
immutable recipes and derived member maps. A reusable entry needs proven recipe
content identity, native revision/storage attestation, exact binding version,
metadata publication/index identity, source eligibility, annotation generations,
actor/draft version and applicable filter identity. In-place mutation, custom
readers, missing authority or an unverified storage change must fall back to fresh
verification. Preserve live opening/closing generation and candidate checks.
Reusing a cached `context` by protocol/candidate UUID alone is unsafe.

Longer-term indexed pending membership could intersect sealed membership with
source/filter indexes and read only required projected rows. That requires a
separate reviewed authority/invalidations design and benchmarks for index build,
retention and refresh costs; it is not justified merely by A/B speedup. Prefer
measured bottlenecks over adding a general cache, and keep the 1,000-output bound
until the full workflow has separately been assessed.

## Post-A/B profile: recipe reuse has a separate authority boundary

The follow-up [50,000-candidate profile](../../../epoch-scale-profile-2026-10-06T11-06-37/scale-50000-selection-profile.txt)
records 5.827 seconds under profiling: two `context` calls total 2.984 seconds,
three `proposal` calls total 2.330 seconds, six `ExplorerHistory.get` calls total
2.066 seconds, and one `_build_scope` totals 1.831 seconds. Index value iteration
accounts for 0.867 seconds. These cumulative times overlap and must not be added.
`deepcopy` accounts for 3.908 seconds cumulatively, including 1.238 seconds inside
the SQL-double `Table.to_dicts` path. The profiler materially increases runtime;
use the separate unprofiled A/B results for speedup claims.

The SQL double explicitly copies rows, whereas native SQL has retrieval and JSON
deserialization costs. Therefore this profile cannot establish the native fraction
spent copying. However, whole-state reconstruction is not exclusively a fixture
artifact: `ProtocolStateReader.materialized_state` still calls `full_state` even
when `native_context` succeeds, then checks its closing context. See
[materialized state](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/workspace_protocol_state.py#L381) and
[full state implementation](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/workspace_api.py#L190).

**Existing native generation does not attest recipe-table contents.**
`StateGenerationAuthority` watches curation, shared annotations, annotation
profiles and its own authority tables. Its trigger manifest does not cover
`ExplorerRevision`, proposal or Workbench draft tables. The response lease reuses
schema attestation while annotation scope counters remain live; it is not a
transactional snapshot or a recipe-content witness. See
[watched tables and triggers](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/workspace_state_generation.py#L36),
[response lease](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/workspace_state_generation.py#L198), and
[live token](https://github.com/maxwellsdm1867/Rieke-OS/blob/238e15cc954ed12c301f42b4aa983802efc3a9e8/python/workspace_state_generation.py#L360).
Consequently, placing a `history.get` memo under `response_contract` and serving
closing reads from it would weaken the existing recipe integrity verification.
The older binding recipe cache is an existing narrower contract, not permission
to extend caching to every proposal/baseline/origin read.

A narrow response-local experiment is viable without replacing the closing
context: reuse verified immutable recipe material only for intermediate duplicate
reads, while forcing fresh canonical reads and checksum/summary validation for
every candidate, baseline and origin at the closing boundary. Keep binding,
source eligibility, fingerprints, annotation witnesses, draft and actor reads
live. In particular, the final `context` must not read the intermediate memo.
This can remove duplicate guarded-to-opening hydration; it cannot remove all
candidate-size work and may have a modest payoff after defensive-copy costs.

Before implementing that experiment, define and test these obligations:

- Reuse applies only to exact native reader methods and read-only Workbench
  responses. Custom histories, revision tables, providers, overridden context
  or proposal readers, missing witnesses and mutations retain the full path.
- The entry is confined to one response and stores a validated immutable value;
  a caller cannot mutate shared recipe members or summaries. Public APIs that
  promise detached mutable dictionaries must retain that behavior.
- Closing reads independently verify recipe bytes and summaries, not merely a
  stored `content_sha256` field or revision UUID. Changed or deleted recipes,
  binding/draft/source changes, failed closing attestation and exceptions discard
  the result and any temporary entries.
- Exercise candidate, baseline and origin corruption; same-UUID content edits;
  binding replacement; custom-reader behavior; and mutation attempts through a
  returned object. Compare exact responses with the unfactored reader.
- Measure native disposable data separately before accepting a speed claim.
  Do not treat a reduction in SQL-double `deepcopy` as native database evidence.

Eliminating the remaining closing recipe reread needs an additional verified
storage/content witness or a different explicitly reviewed snapshot contract.
The existing annotation token is insufficient. Keep that broader design pending
rather than weaken freshness to obtain an attractive diagnostic number. The
current A/B change addresses the measured page-multiplied work; two-stage field
projection remains the next lower-authority-risk experiment if large dynamic
metadata projection is the practical bottleneck. Neither approach establishes
constant-time browsing as candidate membership grows.

## First matched A/B results

The [clean baseline receipt](../../../epoch-scale-comparison-2026-10-06T11-03-12/receipt.json)
and [experimental candidate receipt](../../../epoch-scale-comparison-2026-10-06T11-05-21/receipt.json)
use the same controller hash, Python 3.11.13 and macOS ARM64 host. Candidate source
was dirty experimental source based on `238e15c`; these are diagnostic results,
not clean packaged-candidate qualification. Completed cases have three sequential
unprofiled samples; interrupted baseline cases have one budget-limited sample.

| Available epochs / cells | Selected epochs | Baseline median | Candidate median |
| --- | ---: | ---: | ---: |
| 1,000 / 1 | 1,000 | 344.2 ms | 34.9 ms |
| 1,000 / 100 | 1,000 | 3,319.8 ms | 37.0 ms |
| 1,000 / 1,000 | 1,000 | Exceeded 15 s budget | 42.0 ms |
| 10,000 / 10 | 1,000 | 3,500.4 ms | 363.2 ms |
| 50,000 / 50 | 1,000 | Exceeded 15 s budget | 2,065.7 ms |

At 50,000 epochs, target/ancestor column navigation improved from 3,733.8 to
2,152.3 ms. This supports shipping the verified single-scope-resolution change;
it also makes the residual candidate-size cost visible. Selecting 1,000 from
50,000 still takes about two seconds in this synthetic backend fixture. No
constant-time scaling, native desktop timing or H5 import improvement is claimed.

The implementation owner reported 118 focused backend checks and the architecture
guard passing, with additional identity/cache regressions in progress. The source
review found no blocking issue in the inspected A/B implementation. Broader recipe
reuse remains future work: preserve fresh closing recipe checks in this patch,
add no cross-request memoization, and do not treat annotation generations as
recipe-storage authority.
