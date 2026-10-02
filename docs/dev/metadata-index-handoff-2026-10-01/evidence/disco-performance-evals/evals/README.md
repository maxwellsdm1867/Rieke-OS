This directory freezes the current-version measurements and defines equivalent
baseline/candidate evaluations for everyday actions. Product source is in an
isolated worktree; all databases, preferences, trace files, browser profiles and
servers used by these scripts are disposable. Read-only reuse of installed
Python, MySQL binaries and Node dependencies does not connect to a running Disco
project. No desktop packaging, user project migration or release is part of this
evaluation.

The completed candidate is production-source commit
`eb1e73e2ea4af821ddc73b957568f13746dd9b8f`. The native ten-sample API, five-sample
browser, 10k/100k dense-tag and real H5 trace regression families all passed their
correctness, action-coverage and repeated-action median checks. The separately
paired ordinary lightweight filter preview passed with identical complete
response hashes and essentially unchanged latency (586→578 ms). Full scoped
catalog preview improved (4.196→2.054 s) but remains a bottleneck. See
`CANDIDATE-RESULTS.md` for first-use limits, memory scope, rich/lightweight request
distinctions and all comparisons. Optimized branch/page UI actions take roughly
100 ms at the measured 100k scale; larger scales remain unqualified.

The frozen source version is `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`.
`baseline-manifest.json` records SHA-256 checksums of copied, immutable receipts.
`baseline/` preserves observations instead of regenerating or replacing them.
The original filename `native-10k.json` referred to an unsuccessful sandbox
attempt. A candidate comparison correctly rejected that receipt. The actual
successful historical 10k run was `native-10k-permitted.json`; its bytes now form
the frozen 10k baseline. The failed attempt is retained separately as
`native-10k-initial-sandbox-attempt.json`, explicitly excluded from performance
claims. Baseline hashes and scope labels record this correction; 100k baseline
measurements were not changed.

| Primary 100k native API action | Historical median | Initial optimization goal |
|---|---:|---:|
| First 60 epochs | 56 ms | ≤100 ms |
| Next 60 epochs | 56 ms | ≤100 ms |
| Tree root | 1,983 ms | ≤200 ms |
| Expand date | 2,332 ms | ≤200 ms |
| Expand cell | 2,646 ms | ≤200 ms |
| Expand block | 2,657 ms | ≤200 ms |
| Epoch detail with protocol | 71 ms | ≤100 ms |
| Overview | 563 ms | ≤500 ms |
| Contrast filter preview | 3,905 ms | ≤500 ms; eventual ≤200 ms |

| Shared React component action | Historical median |
|---|---:|
| Expand client-unloaded cell | 2,485 ms |
| Expand client-unloaded block | 2,399 ms |
| Next 60 cells | 2,141 ms |
| Select epoch and display metadata | 96 ms |
| Search focused epoch metadata | 32 ms |
| Reopen cached cell | 65 ms |
| Scroll already loaded rows | 33 ms |
| Initial component load | 2,911 ms, one observation |

The native API fixture has 100k deterministic epochs, ten sources, one protocol,
1,000 cells, 5,000 blocks, four scalar parameters, empty shared annotations and
default saved curation. It uses the actual native MySQL contract, production
Flask routes and a verified sealed metadata index. The browser mounts actual
production-built `PagedTree` and `MetadataPanel`, uses real localhost HTTP and
waits for ready state plus two animation frames. Historical client-unloaded
actions follow API measurements and may encounter warm server caches. New
disjoint-cell/block actions measure branches that the API probe did not expand.
Neither is a full installed-app startup measurement or physical display timing.

The nine API action IDs, all historical browser IDs, and all dense tag and trace
operation IDs are preserved in `metrics-baseline.json`. Dense-tag measurements
use three authors × five tags and two curation scopes per epoch. Tag-ten,
tag-another-ten, filter-twenty, cell tag/filter, autocomplete, preparation and
durable verification remain regression coverage. The 100k dense annotation
startup (146 s historically) is first populated migration, not ordinary project
reopen. Trace probes use real temporary 32/256 MiB H5 files with a 20k-sample
window; first integrity checks and warm reads are kept separate. File caches are
warm after construction. No NAS/cold disk claim is made.

The historical 100k index build was 25.7 s and sealed-index reopen 0.696 s. The
500k and one-million build attempts hit their experiment time caps; no everyday
action qualification is asserted at those scales. Their receipts remain in the
baseline bundle. Legacy SQL-double API receipts are explicitly secondary and
must never replace actual-native measurements in performance claims.

Regression rules:

1. Exact identities, membership, ordering, pagination boundaries, metadata values,
   revision invalidation, saved scientific selections and source integrity are
   hard correctness gates. Native read evaluations also require actual native
   context, zero legacy oracle calls and normal owned-database shutdown. Product
   tests supplement these fixture assertions, especially mixed/missing metadata
   and stale requests. A faster incorrect result is rejected.
2. Freeze source before timing; record HEAD plus Python/frontend content hashes.
   Do not edit measured source during a run. Source inventory must match after
   backend measurements; frontend copying must match source before and after.
3. Run the same actions, fixture, output semantics and harness on baseline and
   candidate. Do not silently replace a rich preview with a minimal preview or
   compare SQL controls with end-to-end latency. Response bytes are recorded.
4. Prefer at least ten sequential native samples and five browser samples. Keep
   first request, warm median, overall median and observed maximum distinct.
   Historical samples number only three for most API/browser actions; mark that
   uncertainty. Never claim a reliable p95/p99 from these small samples.
5. A median slowdown is flagged when it exceeds BOTH 20% and 20 ms. Setup and
   first-use timings are single observations, so treat flags as investigation
   triggers and repeat fresh-process experiments before a final regression
   verdict. Every missing action is reported, not assumed unchanged. Re-run
   flagged blocks without unrelated heavy work before accepting a tradeoff.
6. Targets in the table are optimization goals, separate from regression gates.
   Report first-use costs even if caching produces excellent warm medians. Keep
   same-day baseline alongside historical baseline to expose machine noise.
7. Run heavy scale/import experiments sequentially, with time, memory and free
   disk limits. A cap is an unqualified boundary, not proof of impossibility.

Reproduction uses a Python environment with the product's dependencies:

```sh
env PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B "$EVAL/native_metadata.py" \
  --source-root "$SOURCE" --output-dir "$OUT/native" \
  --mysql-runtime-root "$MYSQL_BINARIES" --index "$SEALED_INDEX" \
  --samples 10 --cap-seconds 300
```

The output directory must be unused. The index and seal are copied into the
owned output before opening; the historical fixture is read only. Native
preferences are pinned under the output. Add `--serve-browser` to keep the owned
API on an ephemeral loopback port for at most 150 s; the config JSON identifies
that port. Run browser measurements only during that controlled interval:

```sh
"$PYTHON" -B "$EVAL/prepare_browser.py" --source-root "$SOURCE" \
  --output-dir "$OUT/browser-shell" --node-modules "$READ_ONLY_NODE_MODULES"
env DISCO_BROWSER_BUILD_ROOT="$OUT/browser-shell" \
  node "$EVAL/run-browser.mjs" "$OUT/native/native-metadata-browser-config.json" \
  "$API_ORIGIN_FROM_CONFIG" "$OUT/browser.json" 5
touch "$OUT/native/native-browser-done"
"$PYTHON" -B "$EVAL/compare.py" --family native \
  --baseline "$BASELINE/native-metadata-100k.json" \
  --candidate "$OUT/native/native-metadata-100k.json" --output "$OUT/comparison.json"
```

Optional environment variables `DISCO_NODE_PACKAGE`, `DISCO_PLAYWRIGHT_PACKAGE`
and `DISCO_CHROME` select read-only dependency installations/Chrome. A fresh
owned headless browser profile is created; no existing browser session is used.

Use the existing parameterized dense tag harness from the selected source:

```sh
env PYTHONDONTWRITEBYTECODE=1 RIEKE_PREFERENCES_DIR="$OUT/tags-prefs" \
  RIEKE_PROJECT_INDEX="$OUT/tags-prefs/project-index.json" \
  RIEKE_USER_PREFERENCES_PATH="$OUT/tags-prefs.json" \
  "$PYTHON" -B "$SOURCE/docs/dev/scale-audit-2026-09-29/benchmark_native_tag_sequence.py" \
  --source-root "$SOURCE" --mysql-runtime-root "$MYSQL_BINARIES" \
  --epochs 100000 --samples 10 --output "$OUT/tags.json"
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$SOURCE/python" \
  RIEKE_PREFERENCES_DIR="$OUT/trace-prefs" \
  RIEKE_PROJECT_INDEX="$OUT/trace-prefs/project-index.json" \
  RIEKE_USER_PREFERENCES_PATH="$OUT/trace-prefs.json" \
  "$PYTHON" -B "$SOURCE/docs/dev/scale-audit-2026-09-29/benchmark_trace_integrity.py" \
  --output "$OUT/trace.json"
```

The tag harness records exact native SQL/HTTP/backup correctness checks and
source inventories. Its retained nearest-rank quantile fields are raw legacy
receipt fields; compare/reports use medians and maxima. Run one heavy harness at
a time. Any further fixture-format changes must be measured with equivalent
baseline/candidate imports rather than reusing an incompatible old seal.

`replay_existing.py` adds the bounded, isolated wrapper used for candidate tag
and trace replay. It sets actual preference-directory/project-index overrides,
keeps the selected source harness unchanged, and places all temporary projects
under its fresh output directory. A timeout raises a normal exception so the
native harness can flush and stop its own server and preserve a partial receipt.
Cleanup can take extra time after the measurement cap. Trace sample count stays
at the unchanged five warm windows used historically; the wrapper's `--samples`
parameter applies to tags.

```sh
"$PYTHON" -B "$EVAL/replay_existing.py" --family tags --source-root "$SOURCE" \
  --output-dir "$OUT/tags-100k" --mysql-runtime-root "$MYSQL_BINARIES" \
  --epochs 100000 --samples 10 --cap-seconds 300
"$PYTHON" -B "$EVAL/replay_existing.py" --family trace --source-root "$SOURCE" \
  --output-dir "$OUT/trace" --cap-seconds 90
```

The current native API adapter records bounded 0.5 s RSS/resource samples,
phase RSS, and the Python worker's rusage high-water RSS. It excludes owned
MySQL/Chrome memory. RSS can miss transient peaks and can fall with compression
or paging. The original ten-sample native API baseline lacked these memory
fields, so candidate RSS alone is an unpaired measurement, not evidence of a
memory improvement. Catalog-specific paired memory evidence is kept separately.
