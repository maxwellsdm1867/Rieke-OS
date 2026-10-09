# Adjacent H5 conversion audit — 2026-10-09

Scope: candidate checkout based on GitHub main
`5aaf0beb983ccc32bfaa5eef53f6faa99ef21eab`. Source inspection, focused regressions and owned native database reproductions;
no installed-app or user-project mutation.
The main import/read-admission fix and restore audit have separate owners and
qualification receipts. This document does not qualify their tests.

## Findings and disposition

| Boundary | Evidence | Disposition |
| --- | --- | --- |
| H5 protocol parameters → parser JSON | `recording_workspace.prepare` re-encodes source attributes using the parser's `NpEncoder`, then compares each value using Python `!=`. Python considers `True`, `1`, and `1.0` equal, including in nested containers; positive and negative zero also compare equal. | Concrete verification weakness. Import owner implemented exact JSON type/structure/value comparison with actual `prepare` regressions; its qualification is recorded separately. SQL ULP compatibility must not be applied here. |
| Python metadata integers → browser | `workspace_api.ExactMetadataJSON` is assigned to `app.json` in `create_app`; the epoch-detail route uses `jsonify`. Integers beyond ±(2**53−1) are recursively emitted as decimal strings. Shared `workspace_http_boundary` encoding retains the same behavior for detached responses. | Already protected. Existing actual-route regression passed. Standalone `JSON.parse` of an unquoted tick bypasses this provider and is not an application defect. Corrected the earlier research note. |
| Browser copying/predicate generation | `components/metadataValues.js` preserves encoded string text and rejects encoded wide integers for source predicates; unsafe Number values are not copied as exact metadata. | Existing protection retained. Decimal strings do not carry an explicit original-type tag, so this is exact-value transport, not a universal typed JSON format. No schema change proposed. |
| NumPy floating metadata → parser JSON | External RetinAnalysis `NpEncoder.default` converts `np.floating` with `float(o)`. This could narrow a genuinely wider source format on a platform that supports one. On the installed Apple silicon NumPy runtime, both float64 and longdouble have 52 mantissa bits. | Cross-platform limitation, not a reproduced loss on this runtime. Do not claim a present float128 failure or implement speculative codecs. Wider H5 floating formats would need explicit format admission and a fixture before support is claimed. |
| H5 sample rate → verified response | Import and service trace admission compare numeric rates against the H5 attribute; linked export loader does the same. These checks are source/stream guards, separate from MySQL JSON parsing. | No demonstrated same-class false rejection. Preserve them; do not spread SQL JSON ULP tolerance into trace, stream, or export identity checks. |
| Query/group/value keys and fingerprints | Existing typed metadata owners distinguish integer, float, boolean and string values, and exact source hashes remain provenance. | No approximate grouping or source rehashing proposed. A representation compatibility policy is not an equality relation for scientific grouping. |

## Verification

Passed existing test using the installed pinned Python/dependency runtime against
candidate application source:

```sh
PYTHONPATH=python /Users/maxwellsdm/Applications/Disco.app/Contents/Resources/runtime/python/bin/python3 -B -m unittest python.tests.test_workspace_api.WorkspaceAPITests.test_browser_metadata_preserves_exact_source_ticks
```

One test passed in 0.285 seconds. It exercises the real Flask epoch-detail route
with an owned fixture service, verifies exact decimal-string response and verifies
the source Python integer remains unchanged. This is not a live browser, native
SQL, or packaged-app test. An initial invocation used the wrong test class name
and did not execute a test; the corrected command above is the passing result.

Native runtime inspection reported `np.finfo(np.float64).nmant == 52` and
`np.finfo(np.longdouble).nmant == 52`. No longdouble loss was reproduced.

The source-parameter finding was handed to the import owner before edits to avoid
conflicting changes to `recording_workspace.py`; its regression result belongs
with that owner's final receipts. The later authored-write work is described below.

## Follow-up: first writes of authored predicates and sealed recipes

The following are concrete unprotected first-write paths in the audited base,
separate from snapshot/dump restoration:

- `POST`/`PUT /api/search-presets` validates predicate literals against the source
  metadata catalog, then `SearchPresets.save` inserts/updates
  `SearchPreset.predicate` and inserts `SearchPresetVersion.recipe` through
  DataJoint JSON fields. The response uses the original Python row; a subsequent
  read uses SQL JSON. No content hash checks the saved predicate. Thus storage
  conversion can change a later equality or range bound. `record_run` also stores
  the authored predicate inside `SearchQueryLastRun.result` while its query key
  hashes the original predicate.
- `POST /api/explore/revisions` calls `ExplorerHistory.create`. Its frozen recipe
  embeds the original predicate and `content_sha256`, then DataJoint serializes
  `ExplorerRevision.recipe`. `get` recomputes the checksum from stored SQL JSON,
  so a converted numeric literal rejects the otherwise valid saved revision.
- `CurationStore.record_dataset_revision` similarly inserts the sealed export
  recipe, including its frozen query snapshot, into `DatasetRevision.recipe`.
  `_export_index` later calls `verify(row['recipe'])`, exposing the same potential
  first-write integrity rejection. Local recipe files use Python JSON and are a
  distinct, exact round-trip path.

The pinned DataJoint `Table` implementation's JSON placeholder calls
`json.dumps(value)` directly for both insert and update. These paths do not use a
precision-preserving typed SQL constructor. The correction below is limited to explicit authored JSON write sites and uses
the shared exact SQL JSON expression inside their existing transactions. It
preserves hashes and source predicate semantics; acquisition-import ULP allowance
does not apply to authored numbers.


## Native first-write proof and scoped correction

Owned fixtures on pinned MySQL **8.4.2** exercised the real Flask preset and
explorer write/read routes using actual DataJoint tables. The source service was
an owned two-epoch metadata fixture, with one epoch at `0.15261696363083765` and
one at its adjacent lower value `0.15261696363083763`. This is native persistence
and application-route evidence, not H5 parsing, a live browser or installed-app
qualification.

Before the correction, the preset POST returned 201 and the submitted literal,
but SQL and fresh GET returned the lower adjacent value. Re-evaluating that saved
equality predicate selected the **other epoch**. The explorer POST also returned
201, but its SQL recipe had the lower value, its content hash failed, and a fresh
GET returned 400. A separate actual `CurationStore.record_dataset_revision` probe
stored a sealed export recipe with the same conversion; listing saved exports
then raised `Snapshot checksum mismatch`.

`workspace_authored_json.write_row` now supports only five explicit app-owned
schemas: preset, preset version, last run, explorer revision and dataset revision.
It verifies full column names/types and complete primary keys before using a
single INSERT/UPDATE with the shared typed JSON expression. Canonical DataJoint
write-method identity is required; custom writers execute their own methods and
must pass exact readback. The caller retains its original transaction, locks,
optimistic versions, audit and publication. Readback failure raises before commit.
No global DataJoint patch, data migration, automatic resealing or approximate
comparison was introduced. Existing already-corrupted rows are not repaired.

The shared helper supports at most 1,024 float leaves (16 nested JSON_SET calls)
and 4 MiB of **added** path/number parameters. Large original JSON documents keep
the pre-existing packet-size contract; a large membership list with one predicate
float is not rejected merely for exceeding 4 MiB. This bounded typed path fails
explicitly for unsupported documents instead of changing numbers.

The final native probe confirmed exact SQL/fresh-API preset values, unchanged
equality membership, successful preset update/version and last-run round trips,
valid explorer hashes with GET 200, and successful exact export-index rebuild.
An injected post-write verification failure returned 400 and left native preset
and event row counts unchanged, demonstrating transaction rollback.

Retained evidence under `/private/tmp/disco-h5-diagnosis-20261009/`:

- `authored-firstwrite-baseline2.json`: preset membership switch and sealed
  explorer checksum failure before authored fixes.
- `authored-firstwrite-candidate2-exportbaseline.json`: corrected preset/explorer
  paths plus independently reproduced export recipe failure before its fix.
- `authored-firstwrite-final-current.json`: complete corrected paths, native rollback
  and before/after-stable SHA-256 identities for all five participating source files.
  This rerun includes the final explicit SQL NULL versus JSON null readback API.
- `authored_firstwrite_probe.py`: final owned-fixture API/method probe.
- `authored-focused-tests-final.log`: 49 focused tests across authored JSON,
  search presets, compact explorer and curation. Five added public regressions
  cover exact round trips/membership and rollback after lossy custom writes.

The native failures were reproduced before the respective application edits.
An initial sandbox-blocked bootstrap fixture and its failed retry were retained;
a fresh owned fixture produced the baseline above. No user project was involved.
