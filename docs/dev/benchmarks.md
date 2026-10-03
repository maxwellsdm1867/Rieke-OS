# Fixed version-attached benchmark suite

The single registry is [benchmarks/registry.json](../../benchmarks/registry.json).
The runner is [tools/benchmark.py](../../tools/benchmark.py). It writes
`benchmark.json`, `benchmark.md`, raw subrunner outputs and correctness logs into
a new, never-overwritten output directory. These artifacts are associated with
exact source commit/tree, dirty state before and after, release/database versions,
schema format versions and implementation source hashes, suite source hashes, fixture version/seal, OS, hardware,
Python/SQLite/Node versions and frontend dependency lock. Never copy the result to
another commit and call it current. A documentation commit also changes HEAD.

## Run and compare

Reference backend profile: **CPython 3.11.13** and the fully pinned
[requirements-py311.txt](../../benchmarks/requirements-py311.txt). Create an owned
benchmark environment; do not upgrade the user's application runtime. With `uv`
available, a fresh checkout can use:

```sh
uv venv --python 3.11.13 .rieke-runtime/benchmark-python
uv pip install --python .rieke-runtime/benchmark-python/bin/python -r benchmarks/requirements-py311.txt
npm ci --prefix workspace-app
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark.py run --output benchmarks/results/unique-run
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark.py gate benchmarks/results/unique-run/benchmark.json \
  --commit "$(git rev-parse HEAD)" --app-version "$(node -p "require('./rieke-release.json').version")"
.rieke-runtime/benchmark-python/bin/python -B tools/benchmark.py compare baseline/benchmark.json \
  benchmarks/results/unique-run/benchmark.json --output comparison.md
```

The local diagnostic runs used **Node 24.13.0**; select that exact version to
reproduce their runtime profile. CI retains its existing **Node 22.12.0** profile;
those results are not comparable to the local Node 24 profile. `npm ci` uses the
committed frontend lock. Both candidate workflows now install the same dedicated
Python benchmark environment from the pinned requirements, including SciPy 1.17.1.
If `uv` is unavailable, provision CPython 3.11.13 explicitly, create its venv and
use that venv's `python -m pip install -r benchmarks/requirements-py311.txt`.
Do not substitute an unversioned system Python and call the result equivalent.

`run` returns nonzero for missing/failed/invalid core cases. Correctness failures,
skips, timeouts and missing samples cannot produce a green receipt. Dirty local
runs remain useful but cannot pass the clean-commit gate or comparison. `compare`
returns nonzero with reasons if suite, fixture, schema format versions or environment differ,
including an OS upgrade. The gate independently resolves the expected commit
and reconstructs tree, release metadata, schema versions and source hashes from
Git objects. Matching start/end declarations alone are insufficient. Comparison
also verifies both recorded commits; keep the necessary Git history available.
CPU identity, positive logical CPU count and numeric positive RAM size must be
known for gate/comparison qualification. Matching `unavailable` values are not
hardware equivalence. Sandbox-denied hardware reads yield diagnostic-only evidence;
use an appropriately permitted read-only execution context for a fresh run, never
retrofit facts into a previous receipt. There is no comparison against pre-macOS-27.0.1 results
without an explicit noncomparable label. No arbitrary speed threshold is supplied:
four raw samples and medians are observations, not percentiles or a speed guarantee.
Calibrated budgets need reviewed repeated evidence and a future versioned policy.

The Python and Node workers are serial and capped at 180 seconds each. The runner
kills only its own worker process group on timeout. Database files live in an owned
temporary directory, removed by the worker on normal exit. A killed worker may
leave a `rieke-core-benchmark-*` temporary directory; cleanup is unconfirmed and
that receipt fails. The renderer harness does not connect to a live backend.
Core measured wall time is recorded in every receipt; a verified runtime will be
added below after the first successful post-update execution.

Historical integrated development smoke: **13.1 seconds** on macOS 27.0.1 arm64,
Python 3.11.13, Node 24.13.0. This dirty-source run verifies bounded runtime only;
it is not a clean release receipt or calibrated latency baseline. The owned local
benchmark environment used SciPy 1.17.1 because the pre-update shared SciPy native
binary failed to load. Actual Python package versions are captured per run; the
shared application runtime was not modified. The subsequent abff764 runs took
11.13 and 10.43 seconds, but both recorded CPU/RAM as unavailable. Independent
review rejected their qualified comparison. Preserve their raw evidence as
**diagnostic only**; their prior gate result/comparison is superseded. Fresh
permitted-read runs on the corrected commit are required for qualification.

## What the first slice measures

Six real SQLite operation cases reuse `tools/metadata_qualification` CoreAdapter
and sealed native truth. Exact source-derived results are checked before timing
and after each sample; the check itself is excluded. Four serial fresh-reader /
same-reader pairs measure detail, scoped first/deep page batches, filter batches,
exact membership batches and requested facets (two/all eligible fields). One
untimed smoke is excluded. Cold means a fresh typed reader, **not** dropped OS disk
cache, new native server or cold H5. Reader initialization and fixture construction
are separately reported setup work. Fixed small batches are not per-row timings.

Mounted App/Protocol/Inspector cases measure first mount and recent Overview →
Inspect return on a fixed 500-row mock API. Content and current-membership gates
are separate. Module transforms are excluded; React work and mock request handling
are included. One fresh-harness smoke is excluded, then four fresh harnesses.
Trace child rendering, native browser layout/scroll/paint, H5 and server latency
are absent. Polling granularity can affect short timings. This supplementary UI
measurement cannot fulfill `ui.native.navigation`.

Selected tests separately check scoped restoration, cache reuse/invalidation,
StrictMode, lazy trace context, current page membership/tag changes, frozen export,
real disposable SQLite roundtrip and small synthetic import identity/collision guards. Their total test
execution time is not application latency. Native SQL tag throughput, ingestion
throughput and waveform portability are not inferred from transactional doubles.

## Release integration and deliberate blockers

The desktop candidate workflow runs the core after its runtime/dependencies exist
and packages JSON/Markdown receipts. `tools/desktop_release.py promote` requires
those files and calls the exact-commit **release** gate before any publication
mutation. It also adds the validated report files to the published asset set.
Local test/dev commands are unaffected. Missing, dirty, stale or failed results
are rejected. Changing a report's top-level status cannot replace its case evidence.

The initial release gate intentionally refuses complete qualification because the
registry still lists native navigation, native tag latency and end-to-end ingest
throughput as unsupported. Resolve those with actual owned fixture adapters and
reviewed registry changes; do not remove the requirement merely to release.
The reusable [native observer](../../benchmarks/navigation-probe.mjs) has no launch
side effects; [its contract](../../benchmarks/NATIVE-CONTRACT.md) explains the
missing launcher, fixtures, independent authority, H5 and lifecycle checks.
Historical restoration results do not qualify a different commit or this suite.

Retain reviewed run artifacts with each release, and link changed cases to the
release notes explaining addressed bottlenecks. Generated files are ignored under
`benchmarks/results`; attach CI artifacts before publication. Avoid committing a
receipt into the very source commit it claims to measure (a self-reference).

## Database and field-access design

[Database portability and benchmark spec](schema-portability-benchmark-spec.md)
contains the code-backed design and proposed stress/adaptive cases. Registry IDs
are authoritative; the note's proposed names are advisory. Universal field access,
slow correct fallback, extraction-incomplete status, generalized JSON import,
metadata-only export and Attach Traces remain explicit gaps. Current 164 eligible
fields are not all raw fields: depth/length/type discovery limits remain. Index
tiers may change speed, never whether scientific fields are accessible. No engine
replacement or adaptive implementation is part of this benchmark slice.

[Stress track](../../benchmarks/stress.md) stays separate. Project/workspace
organization is a deferred follow-up; this work does not reorganize user projects.

Schema-changing work must bump the relevant FORMAT/SCHEMA_VERSION and fixture/suite semantics as appropriate. Implementation source hashes are provenance, not automatically schema incompatibility; ordinary query optimizations remain comparable when formats, fixtures, harness and environment match.

Legacy source-candidate diagnostics upload with `if: always()` before the complete release gate and signing. An expected unsupported-native failure therefore still preserves the run JSON, report and logs.

`RIEKE_TEST_DOM_MODULE` must be **unset** for benchmark runs (even an empty value is rejected). The runner refuses to launch any worker with that override and retains a failed diagnostic receipt. A dynamically imported external DOM module is not covered by the committed suite or installed-jsdom version and cannot silently qualify.


## React 19 and native research attachments

Suite 1.0.3 runs both frontend commands with the committed
`workspace-app/src/test-support/reactTestEnvironment.js` preload. Its exact bytes
are part of the suite hash; environment overrides remain prohibited.

Native research receipts remain attributed to the commit actually measured.
Create a separate attachment (never edit or retrofit the native receipt):

```sh
python tools/benchmark_native.py --evidence-root /owned/research \
  --measured-commit <full-measured-sha> --candidate-commit <full-candidate-sha> \
  --source-receipt source.json --report report.md --output native-attachment.json
python tools/benchmark_native.py --evidence-root /owned/research --verify native-attachment.json
```

The source receipt must contain its original `commit`. Every selected file is
hashed, path escapes and symlinks fail, and Git must show only the fixed list of
infrastructure/test/documentation changes between commits. The tool checks byte
integrity and restricted source equivalence, **not** scientific assertions in the
reports. The attachment is separate from the core receipt and has no power to
satisfy release requirements. Native tag latency, ingestion throughput and full
navigation qualification remain unsupported. Retain private ledgers privately;
explicitly select sanitized reports for any distributable attachment.

Packaged test launchers now select the configured `Disco.app` output beneath
`desktop/dist/mac-arm64`, verify the bundle/executable path, and clone it into the
owned test HOME. They do not search installed applications or fall back to stale
`Rieke OS.app` builds. This path check is not packaged-content qualification;
`verifyPackagedSource` and an explicitly coordinated package smoke remain required.
