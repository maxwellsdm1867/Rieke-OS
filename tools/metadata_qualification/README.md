# Independent metadata qualification

Exclusive ownership: evaluation tooling, tests and receipts only. No application
modules are changed. The source oracle imports only the standard library, never
`workspace_predicates`, field discovery, the typed model or optimized SQL.
`native-truth.json` freezes hand-authored source DTOs, complete details, eligible
field values and empty branch truth. Its seal detects accidental changes; review
both JSON and seal when deliberately updating the source specification. This is a
12-epoch development control, not real acquired data or million qualification.

The fixture exercises 164 eligible paths including 145 new protocol parameters;
Boolean versus number, exact large integers, mixed types, arrays with object
members, null/absence, literal escaping, chronology ties, identical display labels
on distinct native identities and complete non-queryable reconstruction detail.
Native discoverability rules intentionally omit clock ticks and opaque detail
paths from filtering. Those values remain in inspection/export truth. Values are
written explicitly in source truth, never generated from a candidate database.
Raw object leaves follow native discovery; object/array equality is independently
checked. Native browser integer limits must reject unsafe literals rather than
rounding scientific values.

Run from this repository with the existing runtime:

```sh
/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python -B -m unittest discover -s tools/metadata_qualification -p 'test_*.py' -v
/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python -B tools/metadata_qualification/run.py --adapter native --receipt /tmp/native-qualification.json
```

For committed core integration, use `--adapter typed --implementation-root PATH
--expected-commit EXACT_SHA --receipt /tmp/typed-qualification.json`. Only an exact
committed implementation with clean Python source is accepted. A tiny native base
and typed sidecar are built in a new temporary directory, queried, measured and
removed. The runner never reads or constructs the private million corpus. Its
source-code hashes are small; they do not verify private database seals.

`checks.qualify()` accepts an adapter with `fields`, `membership(predicate,scope)`,
`preview(predicate,scope,facet_fields,limit,cursor)`, `detail(identity)`, `close()`.
It requires complete eligible field-set equality, every predicate across structural,
explicit and conjunctive source scopes, full DTO/detail/facet equality and complete
cursor walks. Backend cursor truth is chronological integer rank; this deliberately
does not claim a public generation-bound cursor passed. Eight frozen native errors
are checked globally and in empty scopes, without sharing native validation code.

`service_checks.py` covers the approved separate field-registry/async-summary
boundary. It accepts an isolated Flask client plus caller-supplied deterministic
worker/fault callbacks; no polling sleeps or live app access. Checks retain
request/generation identity (metadata/typed/source/publication with conditional binding/annotation witnesses) on pending, ready, cancelled, stale and failed states;
only ready can publish exact requested summaries. Missing summaries must be
unavailable, never fabricated zeros. `cursor_refusal` checks stale public cursors;
`assert_empty_branches` checks complete recorded empty hierarchy DTOs. Checker
self-tests inject corrupt output; they are **not integrated service passes**.
The service worker should supply hooks to pause before execution/publication and
inject metadata/source/annotation/publication changes. Annotation faults must test
a tag-dependent predicate whose membership stays equal as well as one that changes.

`test_annotations.py` uses real shared-annotation/tag-exchange classes on isolated
transactional table doubles and temp project files. It tags ten exact epoch IDs,
checks ownership and cell inheritance stored once, removes a direct tag while
retaining inherited tags, verifies additive export/import and stale-batch rollback,
and proves immutable recording metadata and protocol curation are unchanged. It
does not qualify real SQL concurrency, million tags, UI latency, frozen waveform
exports or stimulus reconstruction. Those are open gates in `qualification-plan.json`.

## Storage and timing receipts

`storage.py` counts total metadata assets and incremental added indexes explicitly,
deduplicates hardlinks, reports file length versus allocated bytes versus SQLite
used/payload/unused pages, table rows and physical per-index/table components.
Tables identify dictionaries, core projections, ancestry/detail, membership links,
annotation/cache and index costs without pretending dbstat payload is raw storage.
Supply all persistent caches, recovery state, source generations and retained
assets explicitly. Canonical project/MySQL size stays unknown until measured.
Missing raw recording denominators stay null; projected H5/response ratios are
labelled estimates. Actual recording files count distinct originals once. Replay
metadata/reused-H5 stress ratio is not a real million-acquisition product ratio.

`incremental()` needs same-layout before/after assets and explicit imported
record/relationship/source/field/value counts. `growth()` refuses simplified
synthetic points, mismatched layouts and unsealed lineage. Compare original,
deterministic intermediate whole-block replays and the exact million. Explain
changes in identity length, cardinality, field mix and compression when per-record
cost increases. These tools report observations; they do not invent a universal
storage budget. `HighWater` samples explicit staging, old/new generation, cache and
recovery assets; its maximum is an **observed lower bound**, not proof of the true
peak. Record sampling cadence and steady-state cleanup separately.

`sqlite_components()` defaults to refusing files over 64 MiB and any WAL. Inspect
only sealed standalone isolated files. Do not lift the limit during parallel
implementation. `replay_gate.inventory()` performs stat-only inventory and calls
all assets unverified. `verify(...,serial_authorized=True)` is a future coordinator
operation: hash the original 2,781 source and exact million, verify saved
359+1,621/140-field/77,107,863-link receipt, exact generation and project, and count
rows. Exact replay seal binds preserved namespace/whole-block tail; independent
streaming lineage/value and source eligibility checks still follow. Changed seals
require a fresh paired baseline. No large hash/replay/benchmark was run for this job.

`timing.paired()` runs arms serially in alternating order, retains raw samples,
separates first/warm median/max and refuses incorrect payloads or generation
changes. Sample cap is at most 45 seconds and RSS cap at most 1 GiB, with a 50 ms
RSS watchdog (polling may overshoot between samples). Use an owned POSIX main-thread
worker process; SIGALRM/SIGUSR1 are reserved during the pair. Timeout/memory/error
receipts stay incomplete, never pass with invented latencies. Generation callback
must include verified source seals, metadata and relevant annotations. Five samples
do not establish p95/p99. These are backend observations, not UI SLOs. Never resume
old pairs after input/code/policy changes; archive the prior receipt and start fresh.

## Current evidence and limits

`baseline-references.json` retains exact archive paths/hashes without replacing
historical raw receipts. `qualification-plan.json` accounts for all nine everyday
actions with explicit unrun integrated-real-million status and lists missing MAT
fixtures. The shared native baseline, complete typed small fixture and isolated
annotation results are separate receipts. No live native source registration,
active-app restart/install, package build, push, PR, merge to user branch or paid
experiment occurred. The parent coordinates heavy million runs serially after
service/UI integration.

## Completed service and serial real-million extension

`REPORT.md` is the final human-readable before/after report. `REPORT.json` carries
its nine-action status ledger. The report distinguishes equal-output backend
pairs from capped arms, after-only observations and complete UI/API actions.

`integrated_service.py --implementation-root TARGET --expected-commit COMMIT
--receipt RECEIPT` runs independent small native service/HTTP truth, context and
fault gates on an exact clean commit. It uses disposable fixture source data and
transactional SQL doubles, never a live project.

The million sequence is exclusive and serial, after source/replay seal checks:

1. `million_build.py` constructs only an owned complete typed sidecar over the
   already sealed native replay, recording resources and sampled staging/old/new
   disk. Its build available-RAM floor was declared but not enforced; build time,
   RSS and free disk were enforced. Timing workers enforce RAM as well.
2. `million_batch.py` runs all 12 frozen page cases and four two-facet cases,
   alternating five samples per arm under 45-second/1-GiB limits. It freezes
   original-source truth, checks all million UUID/rank mappings and checks every
   candidate member against original native truth plus lineage-weighted counts.
   A failed baseline is retained; after-only retries never establish a pair.
3. `million_controls.py` checks three native full details and minimal second-60
   cell UUID/count projections. Neither is a full legacy tree or rendered action.
4. `million_storage.py --serial-authorized` inspects physical SQLite/dbstat and
   stored-column bytes only after the timing batch completes. It distinguishes
   steady total, incremental sidecar, old/new coexistence, projected recordings,
   actual reused recordings and unrun import/growth/cleanup gates.
5. `million_report.py --root RECEIPTS --output REPORT.md` produces the report
   and machine-readable action ledger, leaving incomplete values visible.

Inputs and outputs are explicit CLI arguments except the preserved original and
million corpus paths bound in the serial coordinator. Never substitute simplified
synthetic million data. Exact runtime arguments/provenance are retained alongside
receipts. No corpus databases or recordings belong in this Git branch.
