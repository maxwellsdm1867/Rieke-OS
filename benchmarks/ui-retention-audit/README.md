# Actual UI retention comparison

This is an **interaction and visual audit**, separate from performance gates. It
runs the actual App against a new disposable 1,000-epoch fixture for each source.
The baseline must be exactly integrated source `ceaf776`; source-start/end hashes
and harness hashes are recorded. It does not touch installed Disco, native user
profiles, or real scientific projects.

Run only after the coordinating chat grants the isolated test slot:

```sh
.rieke-runtime/benchmark-python/bin/python -B benchmarks/ui-retention-audit/run.py \
  --baseline-root /absolute/frozen/ceaf776/source \
  --candidate-root /absolute/frozen/candidate/source \
  --browser-executable '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --output /absolute/new/ui-audit-output
```

Execution is strictly baseline then candidate then screenshot composition. The
runner uses the existing owned-process deadline/RSS/cleanup helpers and
`benchmarks/retention/server.py`, without modifying either harness. Its only
product response double is the shell project inventory/ready state. The browser
bridge uses the actual DraftStore in the audit output. Scientific/tree/predicate
routes and the two synthetic H5 reads use the fixture's existing production
routes over its documented SQL/index/source-admission doubles.

The matrix is in `matrix.json`. Wide Light runs the full click-through; wide Dark,
wide Fred and a 1100×760 compact window run the same core protocol/tree/trace/export
and navigation comparison. All theme changes use Appearance controls. Expansion,
focus, draft typing, scrolling, dialogs and navigation use actual public controls;
DOM evaluation is for observation/provenance, not injecting application state.
The startup context is fresh and has no saved route: the known historical cold
startup race is not silently retried or hidden by a preloaded draft.

Every checkpoint records a screenshot, visible control values, geometry/computed
styles, view/trace node identity, route, error text and request ledger. Uncaught
errors and blocked mutations are failures. A failed step is retained with its
screenshot and error, and the driver continues independent checks; it is never
excluded from a median or silently labeled unsupported. Dependent checks are marked
blocked with their exact failed prerequisites; they never count as passes. Candidate-only retention
assertions are explicit; baseline state loss is recorded as a comparison result.
Capabilities the fixture cannot exercise (notably channel selection and native
file dialogs) are listed explicitly. Activity is separately marked unsupported only
when its actual HTTP 500 and visible error are accompanied by the exact backend
`FixtureService` missing-`Event` exception; this shared fixture has no event relation. Native audits supply those separate checks.

The driver never clicks Save & export, Add tag, Merge, Apply to protocol, source
lifecycle operations, or project creation/unmount. A request guard rejects those
operations even if an unintended control fires. Predicate preview and creation
of a disposable candidate snapshot for the export-options dialog are allowed;
these operate only on the owned fixture and do not publish an export or change
protocol membership. Export names, format choices and query-preset fields remain
unsubmitted drafts.

Outputs:

- `baseline/` and `candidate/`: source receipts, backend cleanup, browser logs,
  per-profile request/console ledgers, screenshots and DOM/geometry observations.
- `comparison/comparison.html`: all screenshots side by side at their real
  captured aspect ratios.
- `comparison/sheet-*.png`: four paired checkpoints per visual review sheet.
- `comparison/comparison.json`: measured geometry/count/state changes and failures.
- `receipt.json`: execution/provenance summary; any reported UI findings retain a
  nonzero overall command exit status even when both stages completed.

No automatic image-similarity threshold declares a screen correct. The captured
pairs require independent visual inspection for clipping, misalignment, duplicate
controls, unexpected blank areas and transient-state leakage. Fixture UUIDs,
paths and timestamps are preserved in the images rather than masked.

The compact candidate checks the metadata wrapper is not absolutely positioned
and hit-tests the real trace Apply control at its center before clicking it. This
is an actual CSS/layout check; no force click bypasses overlapping content.
