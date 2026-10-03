# Agent contract handoff — reviewed public draft, unsupported receiver

Use **AGENT_PROMPT.md** with this directory to map an external lab's metadata into `disco-metadata-bundle.schema.json` **1.0.0-draft.1**. The public schema, validator, mapping and synthetic examples are reused unchanged from the reviewed adapter kit. Independent review approved this draft handoff. The nonblocking source-checker exit-status caveat was fixed and verified offline. No production integration is implied.

**Current DISCO does not accept this metadata bundle.** This is an agent-translatable handoff contract for review, not a production import command. Never write SQL or internal index tables. No proposed metadata-only table exists merely because it appears in the mapping.

From this directory, with Python 3.9+:

```sh
python3 -B validate_bundle.py examples/metadata-only.json
python3 -B validate_bundle.py examples/with-raw-reference.json
python3 -B test_adapter_kit.py
python3 -B test_source_catalog.py
python3 -B validate_bundle.py /path/to/handoff.json > /path/to/validation-report.json
```

No dependencies, network, DataJoint import, database or raw-file reads are needed. Structural/semantic validation is not provenance verification, scientific approval, live-catalog conflict checking, production importer acceptance or performance evidence. The small draft validator is not a hardened production parser.

## Files and authority

- Public syntax: `disco-metadata-bundle.schema.json`, unchanged bytes/version.
- Semantics/identity: `json-metadata-import-design.md`, original reviewed design with local path/thread references sanitized; AGENT_PROMPT adds complete-field inventory instructions. New receiver requirements here supplement it without changing schema rules or identity encoding.
- Agent workflow: `AGENT_PROMPT.md`; mapping report: `mapping-report.template.json`; synthetic examples: `examples/`.
- Public-to-storage mapping: `public-to-storage-map.json`, unchanged historical mapping; `mapping-verification.json` records current evidence and gaps.
- Table catalog: `current-database-schema.json`, original 35-table catalog with only source paths sanitized. Its baseline remains `4383b2a`; do not mislabel it as a live fafb826 dump.
- Current source comparison: `source-comparison.json`. All 20 repository definitions at `fafb826ee00cfa14b657e91ecae5db0c1eda4a84`, plus 15 installed RetinAnalysis definitions, match after indentation normalization. All 18 recorded derived-DDL literals and v2 export DDL match. No additional class-definition strings were found in top-level repository Python files. Installed acquisition source is not proven equal to the pinned upstream commit; no live DDL was inspected.
- Reproduce source comparison using `verify_source_catalog.py --kit ORIGINAL_KIT --repo CHECKOUT --retinanalysis-schema INSTALLED_SCHEMA --output REPORT`. This is AST/text reading, not application execution. It writes a report and exits 0 for parity, 1 for any checked mismatch; input/runtime errors also fail nonzero. The helper records the actual checkout HEAD; compare it to the intended immutable target. The supplied report records the inspected fafb826 target.
- `PROVENANCE.json` records original/staged hashes and changes; `DIFF-FROM-REVIEWED-KIT.md` and `FILELIST.txt` describe the exact package. `validation-evidence.json` records this staging validation.

## Complete metadata access, independent of acceleration

Inventory **all metadata**, including rare, protocol-specific and export-only fields. Every representable field gets an explicit namespaced definition/type/scope/unit and exact value/status. Map known ancestry and UUID links; preserve exact native UUIDs or the kit's deterministic namespace/native-key rule. Unknown units remain null; present null is forbidden by this draft. Preserve omitted versus unknown/not_recorded/not_applicable; report ambiguous legacy null mappings. No inference of units, timestamps, biological identity or QC.

The draft limits sizes/depths and supported field scopes. A retained field outside those constraints is a reported contract blocker or documented namespaced extension where allowed, **not proof of universal query support**. Do not silently drop it, stuff it into the wrong entity scope, weaken the schema or treat an opaque extension as queryable. A future contract revision may be necessary for full coverage. Raw waveform samples remain outside this metadata bundle; metadata about them remains in scope.

Current discovery is incomplete for the new requirement: `workspace_tree._leaves` excludes long arrays/values and deep structures; `_descriptive_metadata` selects only certain attributes. Typed registry inherits those choices. The receiving app needs a complete field inventory, stable IDs/operators and extraction coverage, plus correct bounded slower evaluation for unindexed fields. If extraction is incomplete, return explicit pending/incomplete status, never empty success. Demotion removes speed optimizations, not metadata or access. Current eligible-field tests do not prove universal coverage.

The app owns optimized representation, workload-learned indexes/typed projections and revision-keyed UUID result caches. These do not alter public IDs, missingness, units, provenance, tags or frozen membership. Publication requires complete validated generations; cache keys bind query/scope/order and relevant metadata/source/binding/annotation revisions. UI refetches are not independent user actions for promotion telemetry. No adaptive policy is implemented by this package.

## Current versus proposed

Current: project-private MySQL/DataJoint acquisition/app state; H5-byte-hash Source registration; derived SQLite query indexes; UUID-facing tags; frozen recipe and H5-reference exports. No global scientific main DB is established.

Proposed/unimplemented: generalized metadata-only registration, catalog-aware JSON conflict/apply transaction, full-field fallback, verified raw resolver/binding, metadata-capable export version and complete portable roundtrip. H5 Source PK must never hold a JSON hash. Supplied locators are unverified inert claims; raw-dependent QC stays unavailable until required verified inputs exist. Preserve the current H5 path and immutable identities during future convergence.

Suggested repo destination: `contracts/metadata-bundle/v1-draft/`. This avoids benchmark owner files (`benchmarks/registry.json`, `tools/benchmark.py`, `docs/dev/benchmarks.md`). Parent integrates deliberately after review. No migration/importer/UI/cache implementation is included.
