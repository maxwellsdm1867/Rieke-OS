# Wheeler SQLite handoff audit

Verified 2026-09-27 against the local databases, their consumer code and Wheeler's
registered dataset descriptions. This is an engineering schema audit; no research
database, fitted result, source H5 or Wheeler graph node was changed.

## Existing consumers

| Database | Observed contract | Size on disk |
|---|---|---:|
| `retina_srm_compact.db` | 108 conditions; per-sample time, raw/cleaned voltage and injected current; canonical identity/remediation views; separate fitted-result tables | 2,711,527,424 bytes |
| `vmn_diff_mean.db` | 168 conditions, 3,304 Ovation epochs; per-sample voltage ordered by rowid; explicit stimulus regeneration fields and acquisition-block timing | 1,398,251,520 bytes |
| New protocol export | Frozen query and UUID membership; normalized acquisition hierarchy, typed parameters, tags, stream metadata and checked original-H5 references | Depends on selected cohort |

Wheeler dataset registrations: [D-94c3efc5] (Compact) and [D-353beead] (VMN).
The graph describes VMN's voltage-only storage and validated legacy stimulus
regeneration. The live SQLite schemas additionally contain analysis/QA tables;
registration prose is not used as a substitute for inspecting the current files.

Primary local sources:

- `/Users/maxwellsdm/Documents/GitHub/matlabPyrTools/retinaSRM/kosmos_export/build_kosmos_db_compact.py`
- `/Users/maxwellsdm/Documents/GitHub/matlabPyrTools/retinaSRM/load_vmn_epoch.m`
- `/Users/maxwellsdm/Documents/GitHub/matlabPyrTools/retinaSRM/vmn_stimulus_python/vmn_stimulus.py`
- Both databases' `sqlite_master` definitions, read with `mode=ro`.

These are all queryable through SQLite. They do not share a drop-in analysis
schema. Legacy condition/trial integers and Ovation URI identities must not be
silently aliased to Symphony epoch UUIDs. Existing canonical QC is not equivalent
to the new protocol's inclusion/review flags.

## Schema 2

Implemented in `python/workspace_sqlite.py`:

- Preserve stable project, protocol, export, cell, group, block, epoch and stream
  identities, plus source SHA256. Labels and dates remain display metadata.
- `parameter_sets` stores exact typed parameter combinations once.
  `parameter_values` indexes fields for SQL filtering; `epoch_parameters` is a
  compatible view with the prior epoch/field/type/value columns. Full parameter
  export does not inherit interactive UI truncation limits.
- `frozen_records` stores losslessly compressed source-record JSON with decoded
  length and SHA256. Decoding is bounded and rejects truncation, trailing bytes
  and incorrect checksums. SQL-facing metadata stays ordinary JSON and columns.
- Cell recording date derives from cell start, avoiding conflicting cell rows
  when later epochs cross midnight. Per-epoch timing remains unchanged.
- Acquisition blocks remain independent even when parameter values repeat.
  A parameter-set hash is not a scientific condition definition.
- No sample-per-row duplication, fabricated drug conditions, cleaned voltage,
  current reconstruction or model-fit values are introduced.
- `PRAGMA user_version=2` and `export_metadata.schema_version=2` identify the
  contract. Existing exports are not rewritten. The consumer supports v1/v2.

SQL consumers can begin with `epoch_overview`, `epoch_parameters`, `streams`,
`example_queries` and `documentation`. Those tables/views provide the query and
source pointers without requiring a running app or DataJoint connection. Original
H5 files remain required for samples. `epochs.metadata_json` retains complete
parameter/property/attribute/hierarchy detail, including values unsuitable for a
small UI dropdown.

## Reader and analysis boundary

`python/query_workspace_export.py` exposes `ExportReader` as a context manager.
It verifies each unchanged H5 once per session, checks file signatures for every
read, keeps a bounded 32-record metadata cache and returns bounded full-rate
windows. A changed database or source invalidates the session. One-shot
`read_export_trace` remains available. `load_frozen_record` decodes either schema;
new callers must not assume v2 still has the v1 `epochs.record_json` column.

Wheeler can query this schema and use the reader directly. Existing Compact/VMN
analysis scripts require a deliberate adapter:

1. Define condition/grouping fields while preserving cell and acquisition block.
2. Use full epoch UUIDs for per-epoch caches and result joins, never cell names or
   short trial names. Preserve export UUID and source SHA in derived provenance.
3. Validate stimulus reconstruction against the exact generator/version, seed,
   sample rate and units. Current Symphony stimuli can be metadata-only and use
   amperes where older APIs return picoamperes. No implicit conversion or legacy
   generator substitution is supplied. `read_trace` accepts recorded responses.
4. Store scientific preprocessing and fitted results separately with their code,
   parameters and input-export identity. A separate analysis database is preferred
   so the published snapshot's artifact checksum stays stable.

## Validation

Same real 520-epoch VMN selection, 2 cells, 20 blocks, 1,040 streams:

- v1 export: **13,332,480 bytes**; v2 export: **10,362,880 bytes** — **22.27% smaller**.
  This compares identical metadata and membership. It is not a comparison against
  the much larger, different legacy sample datasets above.
- Every decoded source record exactly equals its v1 record (520/520).
- `epoch_parameters`, `streams`, `epoch_tags`, `epoch_overview` return identical
  rows for this fixture. All eight embedded SQL examples execute.
- All **2,600,000 response samples** match original H5 quantities exactly across
  520 epochs; one source checksum for the session. Local warm 20-sample reads
  averaged **0.296 ms** over 30 calls; full validation took **1.631 s**. These are
  warm local measurements, not latency guarantees on another drive or dataset.
- Tests cover typed/null/array/large-integer parameters, long values, midnight
  cells, corruption/size limits, immutable snapshot tables, source changes,
  cross-epoch stream mismatches, v1 compatibility and API publication checks.
- Read-only peer review found no blocking correctness or data-loss issues.

Exact temporary artifact paths and measurements are in
`docs/dev/sqlite_handoff_validation.json`. Test artifacts were created in an
isolated temporary directory; no research exports were published to project logs.
