# Backend module navigation

Start at the [application module guide](../ARCHITECTURE.md#module-guide) and
[mutation recovery instructions](disco/recovery/AGENTS.md).
Owner instructions are [metadata](disco/metadata/AGENTS.md),
[decisions](disco/decisions/AGENTS.md), [backup](disco/backup/AGENTS.md),
[navigation](disco/navigation/AGENTS.md), [projects](disco/projects/AGENTS.md)
and [workbench](disco/workbench/AGENTS.md).
Import the substantive named leaf for the operation; these package initializers
are inert and do not create aggregate facades. Existing functions, classes,
constants, required helpers and imported attributes retain their interfaces.

| Responsibility | Canonical local contract |
| --- | --- |
| HTTP mutation completion and independent backup status | [Mutation recovery](disco/recovery/CONTRACT.md) |
| Metadata readers, typed queries and disposable generations | [Metadata](disco/metadata/CONTRACT.md) |
| Authored annotations, curation and interchange | [Decisions](disco/decisions/CONTRACT.md) |
| Checkpoints, tag indexes, applied queries and response-only undo | [Adjacent decisions](disco/decisions/ADJACENT.md) |
| Current-state mirror and backup scheduling | [Backup](disco/backup/CONTRACT.md) |
| Bounded predicates, saved methods and tree navigation | [Navigation](disco/navigation/CONTRACT.md) |
| Project storage, retention and provisioning | [Projects](disco/projects/CONTRACT.md) |
| Frozen recipes, review and separate export publication | [Workbench](disco/workbench/CONTRACT.md) |

The [catalog](../docs/architecture/adopted-port-checks.json) records adopted public
seams and scoped checks. Read each contract before selecting tests; central suites
can load native/scientific/HTTP composition even when their names appear narrow.
Do not replace existing assertions or lower provenance rules to accommodate a move.

Retained composition includes [HTTP](workspace_api.py),
[recording/query access](recording_workspace.py),
[protocol-state proof](workspace_protocol_state.py),
[export materialization](workspace_export_artifacts.py),
[desktop lifecycle](workspace_desktop.py), and
[snapshot capture/restore CLI](workspace_state_snapshot.py).
The documented snapshot command remains unchanged. Project creation, servers,
unmount and portability retain physical paths because their code-root, sibling
executable and command-ownership contracts depend on them; see the
[project KEEP decisions](disco/projects/CONTRACT.md#explicit-retained-paths).
Metadata's [KEEP rationale](disco/metadata/KEEP.md) preserves scientific authority
and source-verified trace composition outside disposable read owners.

The [application profile](../desktop/application-profile.json) explicitly lists
production Python files using v2 regular-package paths; tests and guides are
excluded. Its closure/staging helper remains the packaging authority.
The [module ledger](../docs/architecture/core-module-ledger.md) and
[finite path companion](../docs/architecture/core-module-paths.json) distinguish
current source organization from historical evidence. Leaf source bytes and
checkpoint basename labels change conservatively; old receipts are never resealed
or relabeled. Source conformance does not qualify an assembled app, native imports,
SQL durability, parser behavior or historical benchmark results.


## Optional operation elapsed timing

[disco/operation_timing.py](disco/operation_timing.py) supplies simple module-local
`elapsed(module, operation)` tic/toc and context-local `capture_timings()`.
Operations place `with elapsed(__name__, "operation"):` around their existing
body; callers can collect already-instrumented operations directly:

```python
from disco.operation_timing import capture_timings

with capture_timings() as timings:
    page = pager.page(request)
```

Without capture, no clock is read or timing list created. Capture records two
`perf_counter_ns` reads per call and `{module, operation, elapsed_ms, outcome}`;
nested elapsed times overlap. Nineteen operations across seven modules are covered,
not every module. Preserve function identity, signatures, results, exceptions and
existing control flow: no decorators, replacement implementations or HTTP adapters.
Use benchmark `--module-timing` for ordinary-sample diagnostics; see the
[benchmark guide](../docs/dev/benchmarks.md). The runtime helper is explicitly in
the application profile. Review source-byte/catalog witness updates separately;
a timing change does not authorize authority changes.
