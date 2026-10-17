# Request and scale-decoupling audit (2026-10-17)

Source audited: `main` at `f3f3fb95` (Disco 0.1.18 + README). Branch
`claude/request-decoupling` carries the first fixes. Findings come from reading the
code unless a timing is shown; timings name their harness.

Two properties are the goal:

1. **No redundant work.** A user action sends the requests its view needs, once, and
   the server does each validation, decode or build once per request.
2. **Cost follows the view, not the project.** Opening a trace costs O(samples);
   expanding a branch costs O(page); a cell's QC costs O(that cell); a predicate search
   costs O(matches) or an index probe. None should grow with total epochs, tags or
   protocols on a cache hit.

## Design lens

The vocabulary follows *A Philosophy of Software Design* (Ousterhout), already used in
`ARCHITECTURE.md` ("deep modules"). Complexity shows up as change amplification,
cognitive load and unknown unknowns; it is caused by dependencies and obscurity.

| Pattern seen here | Ousterhout term | Effect |
| --- | --- | --- |
| One app `revision` clock read by trees, epoch pages, registry, QC and traces | Unnecessary dependency → change amplification | A tag edit reloads views whose data cannot have changed |
| Client walks tree pages to collect a group; server already has `TreePages.selection()` | Information leakage, shallow interface | Same traversal knowledge in two places; N requests instead of one |
| Workbench `context()` built at request start and again at close | Temporal decomposition | Full O(pending + main + annotations) rebuild twice per request |
| Per-epoch detail reads for one cell's QC | Shallow interface (no bulk read) | Connection + decode + copy per epoch; LRU churn shared with the tree |
| Freshness proven by comparing contents (fingerprint dicts, rows, recipes) | Complexity not pulled downward | Every hit costs O(N); a generation token would cost O(1) |
| One `db_lock` across 78 routes, including H5 reads | General mechanism with global coupling | Any slow request delays every other, including traces |

Fix direction in the same terms: give each reader the narrowest revision that its data
depends on; move multi-request traversals behind one deep server read; validate once per
immutable generation and compare tokens afterwards; add bulk reads where a view needs many
items.

## History: what the 0.1.10 → 0.1.18 display work removed

| | 0.1.10 / first "whole epoch" default (10‑10) | 0.1.18 |
| --- | --- | --- |
| Requests per whole trace | One per ≤100k window, sequential | One binary batch ≤1M samples (`e7d899a7`) |
| Source check | Full SHA-256 whenever the stat signature cache missed; checked per request | Signature-cached; one stat per request |
| Encoding | `tolist()` → sorted-key JSON → `JSON.parse` | binary64 → `Float64Array` (`97ac4d50`) |
| Other | Per-chunk allocation; hidden viewers kept reading | Fixed (`483e00b9`, `7d916bc7`) |

The remaining findings below are the same four patterns elsewhere: many small requests,
repeated validation, per-item decode instead of bulk, and reloads driven by unrelated
changes.

## Findings, ranked

### A. Redundant requests and passes (per action)

1. **Workbench `context()` twice per request** — `disco/workbench/workbench.py` `checked`
   and `finish` → `context()` (~:370–466). Each builds membership, conflicts and a
   checksum over every fingerprint and loads `shared.snapshot()`. Fix: keep the opening
   context; close with a cheap witness (draft version, binding version, generation
   tokens). *High risk — closing authority.*
2. **Tag edits reload trees and pages twice** — `TreeGroupTags.jsx:73` bumps the tree
   `scopeKey`, then the app `revision` bumps (`useWorkspaceChanges.js:8`). Without tag
   filters/tag splits, branch data is unchanged. Fix: key tree reloads on
   `structureRevision` unless `annotationFilterNeedsRefresh(filters)`; update leaf tag
   markers in place.
3. **Workbench frozen-view restore fetches ≤25 pages sequentially**
   (`HierarchyTree.jsx:63`). Fix: one multi-page read sharing one scope snapshot.
4. **"Tag this group" walks pages from the browser** (`treeGroupTargets.js:18–51`).
   Fix: expose `TreePages.selection()` as a main-tree route.
5. **Column/hierarchy reveal is two sequential reads** (`columnTreeReads.js:13–28`).
6. **Cell-branch click refetches the page it just expanded** (`HierarchyTree.jsx:147`,
   `treeSelectionReader.js:70–80`).
7. **Workbench branch select + summary = 2 sequential POSTs, 4 context builds**
   (`incomingTreeSelection.js:10`, `IncomingSelectionSummary.jsx:21–34`).
8. **Field registry refetched on every Edit Tree mount and tag edit**
   (`useFieldRegistry.js:7–27`) though it carries a generation.
9. **Cell QC** — fixed on this branch (see below).
10. **Traces** — 20k–100k streams used JSON (fixed on this branch); revisits re-read
    whole arrays (no whole-array cache by contract); neighbour prefetch warms 20k windows
    that whole mode never reads for longer streams and does not yield to whole reads;
    Workbench geometry re-reads the whole stream on width change.

### B. Cost coupled to total project size

Classified as per-request O(N) uncached (worst), O(N) on cache miss, or decoupled.

| # | Path | Class | Fix direction |
| --- | --- | --- | --- |
| B1 | Protocol current revision (`workspace_protocol_state.py:185–380`), used by epoch detail with `protocol_uuid`, curation, protocol GET, Workbench | Per request O(m), twice per read; falls back to O(m + A) legacy state above the 64 MB proof budget (~20–40k epochs/protocol, inferred) | Revision = (binding revision/version, state generation, index generation); compare tokens |
| B2 | `TagPredicates.snapshot` (`disco/navigation/tag_predicates.py:96–146`) via tag search, tag-filtered trees, Workbench, `/explore/predicate-fields` | Per request O(N·P) + O(A) | Answer from the shared tag index; per-protocol inverted curation index keyed on state generation |
| B3 | `GET /api/search` per keystroke (`disco/metadata/search.py:39–122`) | Per request O(N·P) | Iterate `service.cells`; sorted UUID array per generation for prefixes; cached membership sets |
| B4 | Workbench `context()` (also A1) | Per request O(main + candidate + A), twice | Token comparisons; cache immutable recipes by content hash |
| B5 | Fingerprint re-checks on cache hits (`tree_pages.py:351,375`, `workspace_service.py:1110`, `workbench.py:520`) | O(N) dict compare per hit; 40 MB copy on admission | Versioned fingerprint map; compare one token |
| B6 | `binding()` / `query_result()` per call | Per request O(m) | Cache per (revision, version, fingerprint generation) |
| B7 | Tree pages at ≥500k (4 MB group cache, linear anchor scan, non-structural regroup) | Per page O(N) once caches stop fitting (inferred) | SQLite group indexes per generation; anchor path from its own row |
| B8 | `_tree_rows(None)` sorts all rows per call (`workspace_service.py:1235`) | Per request O(N log N) | Cache sorted active IDs per (generation, source scope) |
| B9 | `POST /api/explore/preview` eligibility + `dict.fromkeys(ids)` | Per request O(N) | Pass the source set to the typed reader |
| B10 | `/api/overview`, Workbench summary | Per request O(N·P) | Cache per generation |
| B11 | Recovery mirror on Workbench select/deselect | Full app-table capture under lock (debounced) | Incremental for row-keyed Workbench tables |

Already decoupled: trace route (row/stream lookup + stat), Cell QC membership
(`cell_epoch_ids`), annotation reads (`for_epochs`, scoped SQL), `generation()` with the
tracker, field registry (sealed catalog), typed `explore_page`.

## Fixed on this branch, with timings

Harness: `tools/benchmark_cell_qc.py` (real sealed `DiskMetadataIndex`; production
`CellQC` methods; H5 replaced by an in-memory double; Flask/HTTP/UI not timed).
CPython 3.11.13, Apple silicon, local diagnostic run, not a release gate.

| Cell epochs / project epochs | Overview before → after | Open view (4 backend calls) before → after | Trial page before → after |
| --- | --- | --- | --- |
| 200 / 20k | 56 → 11 ms | 70 → 16 ms | 1.8 → 2.4 ms |
| 2,000 / 20k | 566 → 113 ms | 581 → 121 ms | 4.1 → 5.3 ms |
| 200 / 200k | 62 → 11 ms | 75 → 16 ms | 1.7 → 2.6 ms |
| 2,000 / 200k | 616 → 110 ms | 635 → 118 ms | 4.7 → 5.2 ms |

Medians of 5 (cold detail cache), same harness bytes before and after; raw samples in
[request-decoupling-cellqc-results.json](request-decoupling-cellqc-results.json). QC cost
was already independent of project size (O(cell)); the fix lowers the per-epoch constant
about 5×. The trial page is ~1 ms slower because the overview no longer leaves entries in
the shared LRU for it to hit. The bounded response read is not visible here because H5 is
a double.

1. **Bulk detail read** — `_Details.many()` decodes one cell's details over one SQLite
   connection without admitting them to the shared 64-entry LRU (which also served the
   tree). `CellQC.overview` and the trial page use it; plain mappings keep per-key reads.
2. **Summary reads stop at the stimulus end** — `/qc/response?summary_only=true` and
   condition summaries read `[0, preTime+stimTime)` instead of up to 100k samples, with
   identical statistics and the same refusal when the window exceeds the bound.
3. **Tag edits no longer reload QC samples or summaries** — Cell QC reads overview, trial
   pages, response summaries, traces and the metadata catalog on `structureRevision`;
   only the epoch detail (which carries annotations) and tag controls follow the live
   revision. The epoch detail no longer warms a 20k trace window the whole-trace read
   does not use.
4. **20k–100k whole traces use binary64** — `readWholeTrace` opts into a `chunks=1`
   binary batch. In-process Flask timing for 100k samples (encode + response, H5 read
   excluded): JSON 108 ms / 1.9 MB → binary 0.3 ms / 0.8 MB; browser `JSON.parse` of the
   JSON body is additionally avoided.

## Timing plan for the rest

The fixed suite (`tools/benchmark.py`, `benchmarks/registry.json`) already has
`trace.inspect`, `tree.*`, `predicate.search`, `view.open`, `workbench.*`, with a
million-epoch track. Missing: `cell_qc.open` and a "tag edit → reloads" case. Each B-item
fix should report medians at ≥2 project sizes (e.g. 20k / 200k / 1M) so a flat line, not
one number, demonstrates decoupling. A dev-only request ledger (requests per action,
duplicate GETs within a window, time waiting on `db_lock`) would make A-items measurable
in the live app.

## Live results on a real project (2026-10-17)

Project: 5,669 epochs, 19 cells, 5 sources, 7 protocols. Same machine, same data;
`main` at `e5dd7ce` versus this branch, both run from source against the project with
a cloned desktop runtime. Browser timings from Chrome Resource/Long Task APIs; endpoint
medians of 7 from `live_timing.py` (scratch harness).

| Action | `main` | Branch |
| --- | --- | --- |
| Add one epoch tag (epoch browser) | 1 write + 58 reads (15 cell pages, 2 protocol pages, 40 trace prefetches, trace re-read); 16 tree sections redrawn | 1 write (8–19 ms); tag visible 10–48 ms; 0 rereads; no redraw |
| Remove one epoch tag | 1 write + 38 reads | 1 write; gone in 42–71 ms |
| Add tag in Cell QC | 1 write + 14 reads (overview ~490 ms ×2, predicate-fields ~900 ms ×2); visible 1.1 s | 1 write; visible ~40–60 ms alone, ~100–130 ms when other views are mounted (app re-render, see below) |
| Tag, then filter on it | — | Search predicate on the new tag finds it immediately (1 cell, 1 epoch) |
| Select an epoch (300k-sample stream) | ~21 requests (20 unused 20k prefetch windows) | 1 request |
| Idle tag poll (`/annotations/scan`, every 3 s) | ~65 ms under the DB lock, incl. a full recovery snapshot | ~2 ms, no lock |
| Cell QC overview (797-epoch cell) | 514 ms | 185 ms |

Remaining tag cost: a confirmed receipt still bumps the app-wide `revision`, re-rendering
the App tree (~40–60 ms of main-thread time when several views are mounted). Splitting
annotation receipts into their own channel would remove it.

Not yet addressed (see B-items): search keystroke (~347 ms), `/explore/predicate-fields`
(~350 ms), project overview (~650–700 ms), epoch detail inside a protocol (~71 ms, the
double `native_context` rebuild), per-request generation-token attestation.
