# Native annotation benchmark at one million metadata rows

`benchmark.py` runs the unchanged production `SharedAnnotations` implementation
and its registered Flask routes against an owned native MySQL database. The
metadata universe is the shared typed SQLite fixture built for the SQLite versus
DuckDB experiment. Selected epoch and cell membership checks use bounded SQL
point lookups, with a 2,048-entry cache; the benchmark does not allocate one
million Python metadata records.

This is a focused annotation route benchmark, not a whole-application startup
benchmark or a production protocol `/epochs` evaluation. The Flask wrapper
configures the production generation authority, native lookup preparation,
recovery checkpoint and `BackupScheduler`. It appends the same persistence
status shape used by the full application's annotation response. It does not
replace native authority or protocol-state contracts.

The initial seed contains 1,000 annotated epochs (0.1% of the million-row
universe), three authors, and five tags per author. This is 3,000 canonical
annotation records and 15,000 tag memberships. It is deliberately **sparse**;
the previous dense 100k test annotated every epoch and also populated two
curation scopes. Their migration/setup timings are not comparable.

Ten sequential samples measure revision preflight, tagging ten epochs, tagging
another ten, autocomplete, cell tagging, removing the twenty epoch tags, and
removing the cell tag. Ten additional targets near the end of the million-row
universe start unannotated; their first insert, later updates and removals are
measured separately. Each sample validates exact persisted revisions and tag
presence, and verifies that a cell tag does not create epoch annotation records.
The experiment also checks case-sensitive and composed/decomposed Unicode tag
identity, atomic rejection of a revision conflict, native generation stability,
and exact final recovery mirror content. Native tables and triggers remain
enabled throughout timed operations.

The two `experimental_native_lookup_sql_*` actions use authoritative native tag
membership followed by an exact metadata SQL join. The generation is checked
before and after the join. These are experimental read-model timings, **not the
existing production tag-filter endpoint**. The production `filter_epoch_ids`
still constructs/validates its entire eligible universe in Python; swapping in
this bounded join requires a separate correctness-reviewed integration.

`production_native_hierarchy_filter_scoped100` additionally runs the unchanged
production tag predicate evaluator over an explicitly preselected 100-child
cell scope, checking that inherited cell tags intersect direct epoch tags into
the exact ten selected children. This is not a million-row-wide filter timing.

Optional `--duckdb` runs the identical native membership-to-metadata join against
the completed DuckDB arm and checks exact ordered parity. Annotation writes
remain in MySQL for both arms; the comparison does not claim DuckDB transaction
performance for mutable annotations.

Whole-app startup is also unresolved at one million epochs: `create_app` calls
supporting-voltage baseline preparation, whose current cell scan can repeat an
epoch-universe scan for every cell. The harness neither invokes nor overrides
that lifecycle method. Scientific QC issue #5 remains outside this experiment.

Only the owned temporary project is modified. Preferences/project index paths
are isolated, databases stop normally in `finally`, and a 300-second alarm
bounds the worker. Receipts preserve failures rather than treating them as
passing results. Timings include Flask serialization, JSON decoding, native SQL
transaction work and recovery scheduling; browser rendering, network, setup and
oracle checks are excluded. Recovery flush duration is reported separately.

Example (after root has completed the shared fixture and granted the benchmark
window):

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  /PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python -B \
  docs/dev/duckdb-million-evals-2026-10-01/tagging/benchmark.py \
  --source-root /private/tmp/disco-duckdb-million-20261001 \
  --sqlite /path/to/shared-million.sqlite \
  --mysql-runtime-root /PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/mysql \
  --output-dir /path/to/unused-tagging-run --samples 10 --cap-seconds 300
```

Use receipt sample medians and maxima; with ten observations, do not infer
stable tail percentiles or extrapolate dense million-epoch migration latency.
