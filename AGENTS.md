# Architecture entry point

Start from [README developer navigation](README.md#working-on-the-code) and the
[physical module guide](ARCHITECTURE.md#module-guide). Follow the local contract
linked there before changing an owner; use its executable public examples and
scoped checks. Preserve a single detailed local contract instead of duplicating it
in top-level summaries.

For backend work, start at [backend navigation](python/AGENTS.md).

For tooling work, start at [retained tooling navigation](tools/AGENTS.md).

For desktop work, start at [desktop navigation](desktop/AGENTS.md).

For frontend work, start at [module navigation](workspace-app/src/AGENTS.md) and
the [current frontend path composition](docs/architecture/core-module-ledger.md#frontend-finite-abc-current-path-composition).
Use current paths and local guides; historical snapshots are provenance, not
current file locations or combined-candidate qualification.

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the implemented module map and
[stable behavioral ports proposal](docs/architecture/stable-ports.md) before
changing cross-module contracts. Proposed ports are not implemented APIs or a
broad refactor authorization. Preserve scientific behavior and exact qualification.

For changes affecting the adopted slices, follow the operational checks linked
from ARCHITECTURE.md. Run `python tools/architecture_guard.py check` after the
existing frontend dependencies are available; use its explicit-base plan/mapped
tests or `--all` local diagnostic as documented. CI is the repository execution
path; an optional local hook does not replace it. Contract/authority changes need
review and an update to the existing adoption record, not just a green guard.

# Repository benchmark entry point

Before any application update, changing release tooling or claiming a performance improvement, read
[docs/dev/benchmarks.md](docs/dev/benchmarks.md) and the fixed
[benchmarks/registry.json](benchmarks/registry.json).

- Install the pinned benchmark environment from the guide, then run
  `.rieke-runtime/benchmark-python/bin/python tools/benchmark.py run --output benchmarks/results/<unique-run>`
  with the exact documented Python/Node profile and frontend dependencies.
  Local development remains possible; a dirty run is diagnostic only.
- After every application update and implementation iteration, run the existing
  fixed core correctness suite plus the actual-million everyday query track using
  [the canonical iteration workflow](docs/dev/benchmarks.md#required-everyday-query-check-after-every-app-update).
  Run matched baseline/candidate sources serially with the same current harness;
  preserve the pinned regression baseline and previous iteration. Missing, failed
  or incomparable evidence is not green. Synthetic admission and in-memory typed
  queries do not qualify native/UI/recovery behavior or replace release gates.
- Preserve raw JSON, logs and Markdown. Compare with `tools/benchmark.py compare`;
  a different suite/fixture/schema/runtime/OS/hardware is not a valid baseline.
- Release promotion requires exact clean candidate evidence. Do not bypass the
  gate or relabel missing/native cases as passed. The initial native navigation
  launcher, native tags and ingest-throughput requirements remain incomplete.
- Native research evidence can be hash-bound with `tools/benchmark_native.py`;
  read the benchmark guide before attaching it. Attachments never grant release
  qualification or change the measured commit.
- Use only owned disposable fixtures. Never point benchmarks at user projects,
  installed apps, live API ports or scientific databases. Coordinate load when
  another benchmark is running; stress runs stay separate from core. The everyday
  query track is required after updates; other stress runs remain opt-in.
- Before desktop packaging, read [the macOS compatibility matrix](docs/dev/macos-compatibility.md).
  Preserve the hash-pinned desktop wheel policy and run native imports after
  relocation. Audit the entire assembled bundle; a wheel tag or core benchmark
  pass does not establish macOS 14 runtime support or Intel support.
- All metadata must remain accessible regardless acceleration tier. Current
  eligible-field checks do not prove universal field access. Adaptive indexing
  and generalized import/export changes are design only; see the linked spec.

This instruction adds benchmark discovery; other task-specific instructions and
scientific authority/qualification requirements continue to apply.

For external metadata mapping, read [the reviewed draft contract](contracts/metadata-bundle/v1-draft/README.md) and its AGENT_PROMPT.md. The offline validator is a handoff check; production import is unsupported. Preserve the packaged provenance and public identity rules.


## Current local Workbench package (2026-10-07)

Installed `~/Applications/Disco.app` is local 0.1.8 source
`7ffd664d0e27ad5446120ba60be79ee2a66315ae` with counted toolbar highlighting.
All unselected rows, including highlighted rows, use the default background;
highlighted labels are bold and selected rows remain green without borders.
See `docs/dev/local-package-default-epochs-2026-10-07.json`.
These source commits are local ahead of last-verified GitHub main `95465c6`; verify
live main and local Git status before further app changes. Public release assets
are unchanged. Keep earlier package evidence attributed to its original source.
