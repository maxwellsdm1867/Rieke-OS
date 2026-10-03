# Repository benchmark entry point

Before changing release tooling or claiming a performance improvement, read
[docs/dev/benchmarks.md](docs/dev/benchmarks.md) and the fixed
[benchmarks/registry.json](benchmarks/registry.json).

- Run `python tools/benchmark.py run --output benchmarks/results/<unique-run>`
  with the project's Python runtime and pinned frontend dependencies installed.
  Local development remains possible; a dirty run is diagnostic only.
- Preserve raw JSON, logs and Markdown. Compare with `tools/benchmark.py compare`;
  a different suite/fixture/schema/runtime/OS/hardware is not a valid baseline.
- Release promotion requires exact clean candidate evidence. Do not bypass the
  gate or relabel missing/native cases as passed. The initial native navigation
  launcher, native tags and ingest-throughput requirements remain incomplete.
- Use only owned disposable fixtures. Never point benchmarks at user projects,
  installed apps, live API ports or scientific databases. Coordinate load when
  another benchmark is running; stress runs are separate and opt-in.
- All metadata must remain accessible regardless acceleration tier. Current
  eligible-field checks do not prove universal field access. Adaptive indexing
  and generalized import/export changes are design only; see the linked spec.

This instruction adds benchmark discovery; other task-specific instructions and
scientific authority/qualification requirements continue to apply.
