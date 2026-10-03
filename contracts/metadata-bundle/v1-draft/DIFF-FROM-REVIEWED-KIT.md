# Diff from reviewed adapter kit

Public contract version and identity encoding are unchanged. No original file was edited.

## Reused unchanged

- `disco-metadata-bundle.schema.json`
- `public-to-storage-map.json`
- `mapping-report.template.json`
- `validate_bundle.py`
- `test_adapter_kit.py`
- `VALIDATION_CHECKLIST.md`
- `examples/metadata-only.json`
- `examples/with-raw-reference.json`
- `invalid/bad-unit.json`
- `invalid/duplicate-id.json`
- `invalid/expected-errors.json`
- `invalid/fake-verified.json`
- `invalid/missing-value.json`
- `invalid/orphan-epoch.json`
- `invalid/unknown-field.json`
- `invalid/unknown-version.json`
- `invalid/wrong-field-type.json`
- `invalid/wrong-uuid5.json`

## Modified copies

- `AGENT_PROMPT.md`: sanitized documentation; AGENT prompt also adds complete-field inventory requirement
- `json-metadata-import-design.md`: sanitized local path/thread references only
- `REVIEW-RESOLUTION.md`: sanitized local path/thread references only
- `current-database-schema.json`: Only tables[*].source paths sanitized; original baseline and all definitions/keys/DDL retained

Catalog normalization changes only source locations, never declarations, fields, keys or DDL. The generic `/Volumes/data/data/sorted` text is an upstream source comment retained verbatim, not user-data inventory.

## New files

- `README.md`
- `PROVENANCE.json`
- `source-comparison.json`
- `verify_source_catalog.py`: emits parity report and exits nonzero on any checked mismatch
- `test_source_catalog.py`: one positive and six negative synthetic scenarios
- `mapping-verification.json`
- `validation-evidence.json`
- `DIFF-FROM-REVIEWED-KIT.md`
- `changes-from-reviewed-kit.patch`
- `FILELIST.txt`

Original ZIP, handoff guide and historical validation receipts are not repackaged. New evidence is labeled separately. Independent review GO received; in-place Library replacement is authorized after offline fixture validation. Contract version unchanged; package revision handoff.2.

Recommended destination: `contracts/metadata-bundle/v1-draft/`; no benchmark registry or implementation files.
