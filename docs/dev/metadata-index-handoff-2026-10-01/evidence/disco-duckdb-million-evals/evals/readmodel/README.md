# Typed analytical read-model experiment

This is a disposable read model, not a production database migration. SQLite
and DuckDB consume the **same CSV**, retain the same columns and parameter
presence/type markers, and use the same SQL query contract. Annotation writes
remain in the actual native MySQL store; supplied annotation membership is
only used to select metadata records here.

## Scope and fairness

`generate_csv(path, epochs)` streams one deterministic input. The four recorded
parameters (`contrast`, `seed`, `stimTime`, `currentMean`) and metadata are
equivalent to `benchmark_service_scale.fixture(epochs)`. UUIDs use the same
SHA-256-derived IDs, cells contain 100 epochs, blocks contain 20, ten sources
are assigned by cell, the synthetic metadata hash is `b` repeated 64 times,
and there is one protocol. The historical fixture deliberately retains its
constant `2026-09-01` date even when its start times advance beyond that date.
No realistic multi-protocol, arbitrary nested metadata, recorded H5 data, or
QC analyses are represented.

Each engine executes the same paging, grouping, count, details, facet and
bounded annotation-membership queries. SQLite gets conventional B-tree
indexes for chronology, cell/block children and contrast; DuckDB uses its
normal columnar scan plans. Both receive an exact UUID unique index. Index
creation and checkpoint time and persisted sizes are included in build
receipts. This compares two configured engines, not identical physical plans.
DuckDB is configured with two threads, a 512 MB database memory limit and a
2 GB owned spill limit. The memory limit is an engine allocation setting,
not a guarantee about whole-process RSS; the outer experiment must enforce
its own process/system guards.

Comparison against the old SQLite EAV implementation additionally changes
schema, endpoint work, and lazy ownership. It cannot establish a DuckDB engine
advantage. The paired typed SQLite/DuckDB comparison isolates that question
much more directly, while still reflecting their usual indexing strategies.

## API

Import `projection.py` from this directory (and make the isolated DuckDB wheel
available on Python's path):

```python
generate_csv(csv_path, 1_000_000)
model = AnalyticalProjection('sqlite', database_path)
phases = model.build(csv_path)  # fresh database path required
model.checkpoint()
model.close()
model = AnalyticalProjection('sqlite', database_path)  # persisted reopen
model.page(limit=60)
model.tree_children('cell', limit=60)
model.tree_children('block', parent={'cell_uuid': cell_id}, limit=60)
model.detail(epoch_id)
model.preview({'contrast': .3}, facet_fields=('contrast', 'currentMean'))
model.facets('seed', {'contrast': .3}, limit=60)
model.tag_page(native_authoritative_ids, filters={'contrast': .3})
```

There are no explicit result caches. Ordinary database and OS caching still
apply, so restarting/reopening is not an OS-cold disk test. Every response is
bounded to at most 100 displayed records or facet values. Tree results include
an exact scoped group count. Preview returns an exact epoch count, one page,
and requested bounded facets, not all matching UUIDs. High-cardinality facet
aggregation can still scan broadly despite returning a small page.

Epoch continuation uses `(date,start_time,epoch_uuid)` as a deterministic key.
Cell/date continuation uses the structural UUID or date value; block
continuation uses `{start_time, key}` to preserve chronological block order.
A production caller
would need to bind these cursors to a metadata generation and selection
revision and reject stale cursors. This experiment's source is immutable;
it does not pretend to implement production cursor lifecycle or arbitrary
scientific predicate semantics.

`model.lazy_rows` and `model.lazy_cells` are read-only mappings with SQL point
lookups and streamed iteration. They expose the prior fixture's row/cell
shape without retaining one million Python objects. Epoch iteration buffers
at most 2,000 SQL records; cell iteration buffers at most 1,000.

Parameter values have separate `_present` and `_kind` columns. Missing and
explicit null remain distinct, and recorded numeric kind flags can be queried
separately. **The fixed typed schema does not preserve arbitrary JSON primitive
values and types**, even with those flags. For example, an integer `1` stored
in the DOUBLE contrast column returns as JSON `1.0`, although its kind flag can
still say `integer`. Heterogeneous values require a richer representation and
reconstruction contract before production use. For this exact baseline corpus
every parameter is present and each parameter has one fixed recorded type;
paired canonical JSON comparisons qualify this narrow fixture only. Separate
tests cover missing/null behavior and numeric flag distinctions while asserting
the DOUBLE reconstruction limitation explicitly.

## Small correctness qualification

`test_projection.py` checks both engines against each other and independent
fixture arithmetic, including every cursor page and exact order, no duplicate
or omitted epochs, parent grouping/counts, details, high-cardinality truncation,
native-supplied membership intersection, streamed point mappings, persisted
reopen, missing/null behavior and numeric kind flag distinctions. They also
assert the fixed schema's loss of an integer JSON primitive in a DOUBLE column.
Four tests pass on 1,000
records. Large-scale receipt oracles and the actual browser/native tagging
experiments are separate and must pass before this million-epoch typed
prototype is qualified. That does not qualify the complete production app,
native protocol bootstrap or complete filter-preview workflow.

Run with the original Python runtime read-only:

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/private/tmp/disco-duckdb-deps-20261001 \
  /PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python \
  -B -m unittest -v test_projection
```

## Exact full-catalog engine control

`eav_duck.py` reuses the current production `DiskMetadataIndex.catalog`
algorithm, including all sixteen fixture fields, within-cell variation,
suggestions and grouping roles. The only SQL dialect changes add dependent
`value_json` to strict GROUP BY lists and translate SQLite's constrained
CROSS JOIN to an equivalent ordinary join. Cursor wrappers make DuckDB
results iterable without fetching every SQL result into Python at once.

`import_sqlite(source, destination)` imports the owned sealed 100k EAV fixture
in 5,000-record DataFrame batches. It does not use DuckDB row-at-a-time writes.
`derive_from_typed(typed_duck, template_sqlite, destination)` constructs the
same sixteen synthetic EAV relations with bulk SQL, one field at a time,
without constructing a million-row Python metadata map. Derived detail blobs
are deliberately absent: this adapter only supports catalog queries, and
never replaces the verified metadata detail reader.

The exact catalog small test verifies imported and SQL-derived DuckDB output
SHA-256 equality against the actual production SQLite implementation,
including global recomputation, a contrast subset, reversed member order,
an empty scope and full predicate choices. This is separate from the bounded
two-facet preview experiment.

`evaluate_catalog.py` is a root-callable bounded worker. It saves ten catalog
plus canonical JSON samples per arm; first, warm median, overall median and
observed maximum are separate. In 100k mode, the actual SQLite and imported
DuckDB outputs must have exactly the same catalog hash. In million mode,
arithmetic membership/order, all sixteen expected field counts and numeric
JSON kinds are checked independently. The known field definitions are loaded
before timing. Build and measure phases each have a 180-second cap, and only
this worker is stopped if its RSS exceeds 1.5 GiB, available system memory
falls below 600 MiB or free disk falls below 4 GiB. Partial receipts survive
errors and guard stops.

The million-epoch derived EAV experiment has no same-scale SQLite EAV control:
its `exact_sqlite_control_hash_passed` is explicitly null. Exact engine output
parity is established at 1,000 and 100,000 records; the million-epoch result is
qualified by the stated independent arithmetic and type oracles.

These are **catalog-stage timings**, excluding full Flask preview preparation,
curation/revisions, frozen membership payloads and browser rendering. They
cannot silently stand in for the original complete filter-preview benchmark.
