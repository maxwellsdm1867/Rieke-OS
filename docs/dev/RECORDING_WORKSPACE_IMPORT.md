# Recording import and saved protocol workspaces

Implemented for the first real recording on 2026-09-27. This is the data/persistence layer; the interactive design preview is not connected to this database yet.

## Imported recording

Source: `/Users/maxwellsdm/Downloads/2026-09-24_F.h5`.
Project files: `/Users/maxwellsdm/Documents/RecordingWorkspace/RetinaSRM`.

The importer reuses RetinAnalysis's installed Symphony parser, acquisition schema and population functions. MySQL 8 runs in the existing `new_retinanalysis-db-1` container. Inspection before import found no user tables in that service; the older MySQL 5.7 container and the SRM/VMN SQLite research databases were not changed.

| Acquisition protocol | Cells with matching epochs | Epochs |
|---|---:|---:|
| VariableMeanNoiseCurInject | 2 | 520 |
| VariableHistoryNoiseCurInject | 2 | 101 |
| ExpandingSpots | 3 | 443 |
| SplitFieldCentering | 2 | 16 |
| SingleSpot | 3 | 6 |

Totals: 3 distinct source-identified ON-parasol cells, 1,086 unique epochs, 1,551 response streams and 1,086 stimulus references. Protocol cell counts overlap. Raw samples remain in the original H5. Do not assume all Amp1 recordings are voltage: the source includes pA recordings, and stream units are retained in the epoch index.

RetinAnalysis currently builds its experiment object from the first animal. The adapter preserves `metadata.raw.json` and creates `metadata.catalog.json` using the actual H5 experiment root UUID/attributes/properties while retaining the parser's animal/preparation/cell hierarchy. The correction is recorded as `experiment_identity_restored`. It does not change the H5 or rewrite RetinAnalysis's scientific methods.

## Files and database records

- `project.json`: project UUID/name and main-catalog reference.
- `catalog.json`: DataJoint catalog/schema reference and a local credential-provider reference. No database password is stored in protocol files.
- `protocols/*.protocol.json`: one saved query definition for each acquisition protocol found in this source. These are starting workspace definitions, not a claim that each supporting measurement should be a primary navigation item.
- `imports/<recording>-<hash>/metadata.raw.json`: original parser result.
- `metadata.catalog.json`: validated catalog representation with the experiment-identity correction.
- `epoch-index.json`: stable cell/epoch identities, parameters, stream paths, counts, rates and units for read adapters.
- `parse-manifest.json` and `import-manifest.json`: source/parser/adapter fingerprints, counts, warnings and attempt outcome.
- `jobs/*.json` and failure tracebacks: durable local job status, including failures before a database connection is available.

The existing acquisition tables live in MySQL schema `schema`. DataJoint-defined bookkeeping tables live in `recording_workspace`: `Project`, `Source`, `Event`, and `ProtocolWorkspace`. Source manifests explicitly retain `review_status: unreviewed` and `scientific_approval: false`.

## Saved protocol format, version 1

```json
{
  "format": "recording-protocol-workspace",
  "version": 1,
  "protocol_uuid": "<stable workspace UUID>",
  "project_uuid": "<project UUID>",
  "name": "VariableMeanNoiseCurInject",
  "catalog_ref": "../catalog.json",
  "query": {
    "version": 1,
    "all": [{
      "field": "EpochBlock.protocol_name",
      "operator": "eq",
      "value": "edu.washington.riekelab.chris.protocols.VariableMeanNoiseCurInject"
    }]
  },
  "view": {
    "group_by": ["cell.type", "cell.start_time"],
    "layout": "landscape",
    "sidebar_visible": true
  },
  "datasets": [],
  "exports": [],
  "figures": []
}
```

These files hold predicates and references, not copies of raw traces or a frozen dataset. Query evaluation scopes experiments through the project membership in the main catalog, resolves the protocol through EpochBlock, then returns stable epoch/cell identities. Version 1 deliberately supports one exact acquisition-protocol predicate. Unknown fields, operators, empty predicates and extra query clauses are rejected rather than silently ignored or broadened. Richer query support must be added explicitly before importing arbitrary web-app presets.

The `last_import_check` field records the most recent check's source, count, time and outcome, including `already_imported`. Actual first-import events remain in the database history. Existing dataset/export/figure references in a protocol file are preserved on another import.

## Running and querying

The installed RetinAnalysis environment supplies the dependencies. From the epicTreeGUI repository:

```sh
/Users/maxwellsdm/Documents/GitHub/retinanalysis/.venv/bin/python \
  python/recording_workspace.py /Users/maxwellsdm/Downloads/2026-09-24_F.h5 \
  --project-dir /Users/maxwellsdm/Documents/RecordingWorkspace/RetinaSRM \
  --retinanalysis /Users/maxwellsdm/Documents/GitHub/retinanalysis
```

Use `--parse-only` for source validation without database writes. A repeated successful import verifies the existing catalog and records `already_imported`; it does not duplicate acquisition rows. A changed source with an existing experiment UUID/name is stopped for explicit version reconciliation, not deleted and repopulated.

```sh
/Users/maxwellsdm/Documents/GitHub/retinanalysis/.venv/bin/python \
  python/query_protocol_workspace.py /absolute/path/to/workspace.protocol.json --identities
```

`evaluate_protocol_file()` is the corresponding Python API. The app can call this same evaluator instead of reimplementing selection semantics. Desktop launching/service management and a live React UI remain separate integration work.

## Failure behavior and validation

Before insertion, validate source and parser-cache fingerprints, unique/full epoch membership, source epoch/block/protocol identities, block-plus-epoch parameter values, stream UUID/device paths, sample rates and supported representations. Check recorded units across each response's samples in bounded chunks. Retain source bytes and metadata; do not convert unknown metadata into guessed values. JSON files are replaced atomically and reject non-finite numeric values.

Acquisition rows, source registration and their audit event commit in one MySQL transaction after round-trip membership, parameter, attribute and stream-reference checks. A database transaction failure is logged; a failed connection can leave the commit outcome unverified, so a retry checks the source marker and membership before taking any action. Failures after catalog commit while finalizing workspace files are distinguished from transaction failures. Local job records remain available if the database/audit write is unavailable.

Parser-cache checksum/version mismatches stop processing. Keep the suspicious output for diagnosis; do not overwrite it merely to make an import pass. Original H5 files are always read-only. Passing structural validation does not establish scientific quality: every imported source starts unreviewed.

Validation performed on this recording:

- Full source/parsed epoch UUID membership equality and source protocol/parameter checks.
- 1,551 response and 1,086 stimulus locators checked; bounded sample reads and explicit units.
- Catalog round-trip comparison of all epoch IDs, parameters, attributes, devices and stream paths.
- Reimport returned `already_imported` with unchanged acquisition counts.
- An intentional failure rolled back temporary rows in both acquisition and audit schemas.
- All five protocol definitions evaluated to the expected counts; exact UUID-set verification is recorded in the project verification report.
- Four unit tests cover unknown-query rejection, tampered-cache rejection, atomic failure preservation and integer tick precision.

These checks cannot infer whether the experiment itself was performed correctly or whether a cell/type/drug annotation is scientifically correct. Those facts remain available for inspection and review.

## Query snapshots, export recipes and optional trees

`python/workspace_recipes.py` adds the reusable persistence contract. A query
snapshot saves the predicate, main-catalog reference, protocol/project UUIDs,
source revisions, view settings and all matching epoch UUIDs with metadata
fingerprints. Export preparation embeds this entire snapshot, the inclusion and
exclusion decisions, review policy, destination/options, actor and exact eligible
membership. It is explicitly `prepared`; it does not claim a data artifact has
been exported. Snapshot publication is atomic and refuses to replace an existing
revision. Checksums detect subsequent edits.

Refreshing compares query snapshots, including the original candidate set rather
than only approved/exported members. Added, removed and changed epoch IDs are
returned separately. Different query definitions/catalogs cannot accidentally be
compared as a same-query refresh. The current evaluator fingerprints epoch
parameters/properties/attributes; ancestor metadata and persisted review/tag
revision fingerprints still need to be integrated before comprehensive change
detection is available.

Save a baseline, without exporting scientific data:

```sh
/Users/maxwellsdm/Documents/GitHub/retinanalysis/.venv/bin/python \
  python/snapshot_protocol_workspace.py /absolute/path/to/workspace.protocol.json \
  /absolute/path/to/new-query-snapshot.json
```

Use `--compare /absolute/path/to/previous-query-snapshot.json` to produce a diff.
Actual baselines for all five imported protocols now live beneath the project's
`query-snapshots/<protocol_uuid>/` directory. Their 443, 6, 16, 101 and 520 epoch
memberships were checked against the validated import index. These are query
baselines, not approved datasets or completed exports. The snapshot CLI currently
writes files only; it does not append database audit events.

`build_tree(rows, "date, cell, block")` implements the existing EpicTree ordered
field grouping model for the metadata index. It supports date, cell, cell type,
block, group and protocol; `→` is accepted in place of commas. Missing metadata
gets its own visible group. Invalid fields and duplicate epoch identities fail
explicitly. Reordering splits never filters membership. This helper builds a
metadata tree; the future React adapter must request/paginate children lazily.
The original MATLAB `epicTreeTools.buildTree(keyPaths)` and custom splitters remain
the scientific tree backbone. The preview additionally demonstrates mean, drug
and phase grouping on illustrative data, not a validated generic parameter mapper.

Eight unit tests now cover importer checks plus export scope/review rejection,
immutable snapshots, query diffs and tree membership invariance. The preview has
a typed split builder, saved recipe details, a reuse-query action and workflow
icons. It remains a simulation. Live React controls, review storage, destination
adapters and transactional export-completion audit records remain integration
work; existing MATLAB/SQLite export paths have not yet been wired through this
new recipe contract. Every such adapter must first persist a prepared recipe,
consume its frozen members, then log artifact checksum/counts and completion (or
failure) without overwriting the original recipe.
