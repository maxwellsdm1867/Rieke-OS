# Repository benchmark entry point

Before changing release tooling or claiming a performance improvement, read
[docs/dev/benchmarks.md](docs/dev/benchmarks.md) and the fixed
[benchmarks/registry.json](benchmarks/registry.json).

- Install the pinned benchmark environment from the guide, then run
  `.rieke-runtime/benchmark-python/bin/python tools/benchmark.py run --output benchmarks/results/<unique-run>`
  with the exact documented Python/Node profile and frontend dependencies.
  Local development remains possible; a dirty run is diagnostic only.
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
  another benchmark is running; stress runs are separate and opt-in.
- All metadata must remain accessible regardless acceleration tier. Current
  eligible-field checks do not prove universal field access. Adaptive indexing
  and generalized import/export changes are design only; see the linked spec.

This instruction adds benchmark discovery; other task-specific instructions and
scientific authority/qualification requirements continue to apply.

For external metadata mapping, read [the reviewed draft contract](contracts/metadata-bundle/v1-draft/README.md) and its AGENT_PROMPT.md. The offline validator is a handoff check; production import is unsupported. Preserve the packaged provenance and public identity rules.
