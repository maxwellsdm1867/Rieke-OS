# Backend module navigation

Start at the [application module guide](../ARCHITECTURE.md#module-guide).
[HTTP mutation recovery](disco/recovery/AGENTS.md) is the first organized Python
module. Its [canonical public contract](disco/recovery/CONTRACT.md) owns usage,
ordering, failures and scoped checks. Import its public package, not its private
implementation. The [catalog](../docs/architecture/adopted-port-checks.json)
enforces that seam for production and tests.

The remaining flat files retain their substantive responsibilities and paths:
[HTTP composition](workspace_api.py), [recording/query access](recording_workspace.py),
[group annotations](workspace_annotation_groups.py), [recovery storage](workspace_recovery_store.py),
[backup scheduling](workspace_backup_scheduler.py), [export materialization](workspace_export_artifacts.py),
and [desktop lifecycle](workspace_desktop.py). They are not completed physical
package migrations. Preserve their scientific, freshness, cancellation and
process ownership contracts in the [adoption record](../docs/architecture/0.1.8-first-port-slices.md).

The [application profile](../desktop/application-profile.json) explicitly lists
92 production Python files using v2 regular-package paths; tests and guides are
excluded. Its existing closure/staging helper remains the packaging authority.
The [module ledger](../docs/architecture/core-module-ledger.md) records measured
and unmeasured evidence. Source conformance does not qualify an assembled app,
native imports, SQL durability, parser behavior or historical benchmark results.
