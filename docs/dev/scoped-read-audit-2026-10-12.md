# Scoped metadata read audit

Local baseline: `2014f38` (installed membership-cache work), including protocol
switching `bb25b08` and retinal icons `d489042`. This work is for later local
integration. It does not change the installed package.

## Findings and ownership

| Operation | Finding and change | Owner |
| --- | --- | --- |
| Repeated Workbench tree/page reads | Fresh adapters rebuilt frozen recipe/grouping. Retain one immutable input and its bounded navigation caches; make a fresh adapter for live policy. | Workbench input; Navigation grouping |
| Workbench cell summary | Cross-protocol coverage loaded unrelated memberships that this consumer does not use. Explicit canonical local summary omits the coverage field. | Workspace service; Workbench consumer |
| Cell QC and annotation/detail count | Traversed all basic epoch rows. Use covering SQLite cell membership index, exact count, and only selected cell rows. | Metadata index; service methods |
| Epoch detail curation | Hydrated project curation before selecting one epoch. Canonical provider now receives only that epoch fingerprint. | Workspace service |
| Large annotation target lists | More than 250 targets fell back to an unrestricted target read. All explicit lists now use batches of at most 250. Summary fallback supplies exact epoch and inherited-cell targets. | Decisions annotations |
| Empty tag snapshot | Read definitions and project fingerprints for an empty result. Return the existing exact empty shape/checksum immediately. | Navigation tag predicates |

Prepared-candidate reuse on Workbench return already existed in the switching
branch. This change targets repeated backend read computation, not preparation or
scientific publication. Membership/action freshness, excluded/accepted identities,
custom callbacks, stale metadata and closing refusals remain enforced.

One frozen recipe is retained, with the existing separately bounded page/tree
caches. The recipe is proportional to the active candidate, so this is not a total
RSS ceiling. Switching the candidate/view replaces the prior retained input. Index
cell membership assumes the published immutable generation and basic rows agree;
production generation identity includes the metadata-index implementation, causing
one rebuild after upgrade. Legacy/custom readers use their prior scan behavior.

## Audit boundaries and remaining work

Global search/source predicate discovery, project overview, import/recovery,
annotation preparation and persisted nonempty tag evidence legitimately need
project-wide information. Their scope was not silently narrowed. Exact-UUID search
and datastore inventory still contain global basic-row scans; selected export
normalization also scans project rows and validates cross-source cell identity.
Those are separate follow-ups requiring their own contracts and measurements.
This is not a claim that every repository query is optimally scoped.

## Validation

Source review found no concrete correctness blockers. Application source is
`52f1ba5ff868941bcda759a15d973ae50696cd54`. All 302 scoped tests, the architecture
check, fixed core suite (13.72 seconds) and clean-source core gate passed.
Two diagnostic harnesses keep either 2,000 Workbench epochs or one 100-epoch cell
fixed while growing unrelated project metadata from 20,000 to one million rows.
They use production read code with explicit synthetic authority admission; cell
lookup uses real SQLite SQL/indexes. Fixture setup, fresh context derivation,
native/H5 ingestion, HTTP and browser latency are outside their timing boundary.
No native or end-to-end UI performance claim follows from those measurements.


### Measured results

The same clean source and harness produced these direct backend medians with
one million project epochs; Workbench membership stayed at 2,000 and the selected
cell at 100 epochs. Raw samples and hashes are in
[the results record](scoped-read-results-2026-10-12.json).

| Operation | Before ms | After ms |
| --- | ---: | ---: |
| Workbench warm tree | 15.460 | 0.353 |
| Workbench cell page | 15.486 | 0.242 |
| Workbench epoch page | 5.377 | 0.187 |
| Workbench local summary | 1369.398 | 18.452 |
| Cell epoch count | 84.117 | 0.192 |
| Cell QC rows | 72.425 | 0.252 |

At 20k, 200k and one million project epochs, the new local summary medians were
19.290, 19.105 and 18.452 ms. Warm tree profiling recorded zero scope builds and
zero binding recipe copies (previously one and three per read). At every scale,
cell count visited zero basic rows and Cell QC visited exactly 100; both old paths
visited the full project. Every exact-result oracle passed; no H5 was opened.

### Broader regression comparisons

All tree and typed-query exact results/refusal checks passed in each actual-million
comparison. Initial pinned-baseline comparison flagged `tree.scroll_cell`:
1176.712 to 2928.110 ms. The immediately preceding-source comparison did not
reproduce that flag (980.177 to 989.115 ms), but flagged synthetic `tree.setup_ms`
(2101.972 to 2868.180 ms). A single complete preceding-source repeat passed without
any timing or memory flags: setup 2201.55 to 2132.02 ms, scrolling 987.26 to
987.94 ms. The original flagged runs are retained; the initial pinned comparison
is still labeled review-required, not rewritten as green. The repeat establishes
that those two flags did not reproduce; it does not prove their external cause.

The complete raw evidence was recorded at
`/private/tmp/disco-scoped-operations-evidence` and copied alongside the durable
checkout under `Documents/Codex/Disco-scoped-reads-2026-10-12/evidence`.
The later documentation commit does not relabel the measured application source.
No browser action timings or native workflow qualification were added by this pass.
