# Run a complete synthetic source-to-bundle example

**SYNTHETIC scientific records, actual usable files.** `source.json` borrows the inspected nested cells → epochGroups → epochBlocks → epochs, parameters and device-keyed responses shape. It is deliberately named `synthetic-parser-shaped-v1`; it is NOT an actual RetinAnalysis parser export, full parser adapter or private experiment. The mapper supports only this teaching format. The public target remains the unchanged reviewed `disco-metadata-bundle` 1.0.0-draft.1.

Validation completed: all three bundle variants validate; five bad bundles reject. All 9 worked-example tests, 25 original adapter tests and 2 source-checker tests pass. See EXECUTION-EVIDENCE.json and cli-reports/ for actual outputs. Independent review remains pending; no Library replacement yet.

## Start with two real files

Open `source.json` beside `expected/bundle.json`. The collection includes three cells (one empty), four epochs, two protocols, two cells with the same label but different IDs, one described response, cell/epoch tags and an exact large integer seed. No samples are embedded or opened. An author name is a claim, not authentication.

Run from this `worked-examples` directory:

```sh
python3 -B map_source.py source.json --out /tmp/disco-worked-new-output
python3 -B ../validate_bundle.py /tmp/disco-worked-new-output/bundle.json
```

Choose a fresh output directory. A blocked run writes its mapping report and ledger but no bundle; an existing output directory is refused to prevent stale-success files. Success emits bundle.json, mapping-report.json, identity-ledger.json and validation-report.json. Copying those JSON files into a live project is NOT an import operation; the production receiver remains unimplemented.

## Trace five source fields to exact targets

1. `experiment.cells[0].uuid` is already `7f4e8e7b-3a2d-4c91-8f12-0e9c28a40351`. Target `cells[0].id` and `cells[0].identity.native_key` preserve it; mode is native_uuid. `epochs[0].cell_id` refers to that same ID.
2. `experiment.cells[1].key` is `cell:2`. Combine with immutable experiment key into `session:synthetic-A/cell:2`, then apply the exact kit UUIDv5 rule. Target ID is `cf1b8bd1-f76e-5cf6-b41d-b1ebeedc3d24`. Its label is also Cell1; labels do not merge cells.
3. First block `parameters.amplitude` is 50 pA; first epoch overrides it with numeric zero. Target `epochs[0].fields["demo:amplitude"]` is `{ "status": "present", "value": 0 }`. Second epoch inherits 50. Original defaults/overrides remain verbatim in `extensions["demo:source_snapshot"]`; the queried epoch field contains the effective value.
4. First block temperature is null, and the **synthetic source explicitly declares** `null_status: not_recorded`. The target contains status not_recorded with no value. A null without that source evidence blocks mapping. False remains false; an omitted seed remains omitted; seed `9007199254740993` remains an exact integer_string.
5. First response `sampleRate: 10000`, `sampleRateUnits: Hz`, `units: mV` map to sample_rate_hz and unit. Unknown rate units block rather than guessing. Default trace_state is absent; h5path is retained source metadata, not accessible raw evidence. The optional raw-claim variant adds only a fabricated checksum/locator claim and referenced state; raw_assets_verified remains 0 and QC remains unavailable.

`expected/mapping-report.json` lists field mappings, explicit null/units/time rules, every entity's ID derivation and a leaf-level losslessness inventory. Every source leaf is retained in the namespaced source snapshot. This proves retention in this bounded example, **not universal query support** for snapshot-only fields. Queryable mapped parameters have field definitions; other retained facts still need explicit future registry/fallback coverage. Unknown source keys/parameters block this mapper instead of silently disappearing. An oversized or unsupported payload is a contract blocker, not permission to relax schema limits.

The naive `10/01/2026 10:15:00:000000` timestamp is preserved with unknown status; the mapper does not assign UTC. The fixed exported_at is a synthetic fixture transport time only.

## Walk all references

Use UUID-LINKS.md and `expected/identity-ledger.json`. The graph is:

```text
source -> cell -> group -> block -> epoch -> stream
                          protocol <- epoch
profile -> annotation(target_kind + exact cell/epoch UUID)
separate teaching frozen selection -> exact Epoch1 and Epoch4 UUIDs
```

Read the actual `source_id`, `cell_id`, `group_id`, `block_id`, `protocol_id` and `epoch_id` strings in bundle.json. They must resolve to rows of the appropriate kind with consistent ownership. Empty cells remain rows. No invented animal/preparation records fill unknown ancestry.

## Re-import, metadata revision and raw claims

Regeneration command:

```sh
python3 -B build_examples.py
python3 -B map_source.py source-revision-2.json --out /tmp/disco-worked-r2-new
python3 -B map_source.py source.json --raw-claim --out /tmp/disco-worked-raw-new
```

Re-running the same source reproduces identical entity IDs. Revision 2 changes the dataset/source revision and first-cell label, preserving entity IDs; a receiving catalog would still need implemented conflict/revision logic. The raw variant preserves scientific IDs and tags, adds only unverified asset/stream claims, and never opens a file. Synthetic all-`a` checksum and nonexistent path are intentional: **not a checksum of supplied H5 bytes**.

`frozen-selection.demo.json` is a separate teaching sidecar selecting Epoch1 and Epoch4 at r1. It is NOT a competing metadata schema or implemented DISCO recipe. Updating a label/current revision does not reevaluate those member IDs. Actual production frozen records require their existing versioned fingerprint/annotation receipts; this example does not fabricate them.

## Understand failures and repairs

The generator prepares full failing bundles under `bad/`, exact expected validator reports, and `bad/cases.json` with repairs. The repaired counterpart is `expected/bundle.json`:

| Failure | Expected rejection | Honest repair |
|---|---|---|
| Dangling cell UUID | broken_link | Restore the actual referenced cell ID |
| Duplicate epoch identity | duplicate_id | Remove duplicate representation or resolve origin-key conflict |
| Whitespace unit ` pA ` | unit | Restore explicit source pA; don't infer units |
| Numeric value written as `"0"` | field_type | Preserve source number type |
| Present null temperature | field_type (and possibly schema) | Apply explicit not_recorded status without value |

After generation, commands are:

```sh
python3 -B ../validate_bundle.py bad/dangling-uuid.json
# expected nonzero; inspect errors, don't remove validation rules
python3 -B ../validate_bundle.py expected/bundle.json
# expected zero; draft_only true, database_checked false, raw_assets_verified 0
python3 -B map_source.py source-blocked.json --out /tmp/disco-worked-blocked-new
# expected nonzero and mapping report; no bundle emitted
python3 -B test_worked_examples.py
python3 -B ../test_adapter_kit.py
python3 -B ../test_source_catalog.py
```

CLI reports also include the input file SHA256; it is a transport checksum, never an H5 Source key. `expected/validation-report.json` is the validator function result without that CLI checksum. The commands were run for this package; actual outputs are recorded. Library uploads wait for independent review.

## Database must reject invalid writes

Read WRITE-REJECTION-CONTRACT.md and WRITE-REJECTION-CASES.json. These require receiving-side revalidation, database constraints where applicable, rollback/no partial entities or leaked asset registrations and actionable errors. All database integration cases are explicitly not run because the receiver is unsupported; the saved offline failures are not database enforcement evidence.

Strict source parsing: the mapper uses the kit’s bounded byte loader before output creation. Duplicate scientific JSON keys, NaN, Infinity and overflowing floats are rejected with nonzero status and no bundle. Four CLI rejection scenarios passed in the focused validation pass.
