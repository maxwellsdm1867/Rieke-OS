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

Source review found no concrete correctness blockers. The scoped regression suite
and fixed core/million-record comparisons are recorded separately after execution.
Two diagnostic harnesses keep either 2,000 Workbench epochs or one 100-epoch cell
fixed while growing unrelated project metadata from 20,000 to one million rows.
They use production read code with explicit synthetic authority admission; cell
lookup uses real SQLite SQL/indexes. Fixture setup, fresh context derivation,
native/H5 ingestion, HTTP and browser latency are outside their timing boundary.
No native or end-to-end UI performance claim follows from those measurements.
