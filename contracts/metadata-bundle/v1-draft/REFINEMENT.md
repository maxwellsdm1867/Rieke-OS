# Bounded tooling refinement — independently reviewed

Public bundle version remains **1.0.0-draft.1**, with unchanged schema bytes, UUID rules, entity payloads and scientific semantics. This revision adds optional diagnostics, occurrence-level teaching-mapper coverage and non-mutating golden replay. No receiver, migration or production write is implemented. Independent review passed; this package replaces the existing Library item while preserving its identity.

## Import-port interface

Import sibling `validation_diagnostics` and call `validate_bytes(raw: bytes, schema: dict)`. Supply original bytes and the explicit local reviewed schema. `REPORT_VERSION = '1.0.0-draft.1'` identifies the tooling envelope separately from the public `contract_version`. Dependency: sibling `validate_bundle.py`. The existing `validate(data, schema)` report and default CLI retain their prior behavior.

The returned object contains `format: disco-validation-diagnostics`, `report_version`, `contract_version`, `input_sha256`, `legacy_report`, ordered `diagnostics`, and `stages`. The optional CLI is:

```sh
python3 -B validate_bundle.py examples/metadata-only.json --diagnostics
```

`legacy_report.valid` means offline draft validation only. It is never receiver acceptance, provenance verification or commit success. Stage keys are `parsed`, `structural`, `semantic`, `mapping`, `raw`, `database`. Mapping is `not_run` without source evidence; raw is `unverified`, verified count zero; database is `unsupported`, checked false. No `committed` state exists. Structural failure short-circuits semantic checks. Unsupported validator vocabulary yields a capability diagnostic and structural `unsupported`, not a claim about validity under a general standards-compliant validator.

Each diagnostic has `code`, `stage`, `instance_pointer`, `schema_pointer`, `source_pointer`, `message`. RFC6901 pointers use original traversal tokens; `/` becomes `~1`, `~` becomes `~0`. Empty string denotes root; null denotes unavailable location. Missing-property/additional-property errors locate the parent object and actual schema keyword. Semantic rules have no schema keyword pointer. Source pointers remain null when validating an external bundle without mapping evidence. Parse errors may include line/column/character offset; no fake JSON pointer is inferred. Diagnostics preserve validator order; identical input bytes/configuration produce identical reports. Input object order can affect error order, matching legacy behavior. The mapper sorts unknown-key blockers.

The schema subset is described by `validate_bundle.VOCABULARY`. Only the accompanying schema is supported; local `$defs` references and the asserted UUID/date-time formats are implemented. Do not advertise general Draft2020-12 conformance. Capabilities are consolidated in existing `PROVENANCE.json`, not a second schema or registry authority.

## Exact coverage and honest query states

The synthetic mapper reports each present source leaf or empty container with its RFC6901 pointer, observed type/shape, unit evidence, missingness, snapshot retention pointer, exact public target pointers and transformations. Block parameters map only to epochs that actually inherit them; overrides map to their effective epoch value. A source key superseded by a native UUID is not falsely labeled as the UUID's copied value. Original scope/key evidence remains in the snapshot and identity ledger.

`query_support: mapped` means an explicit public-contract target exists; `retained_only` means only snapshot retention. Both carry `query_execution: unsupported_receiver`. `all_field_receiver_readiness` remains blocked. Structural tutorial notes, overridden values and metadata without a public mapping can be retained-only. The report cannot authorize an all-field production import. Absent fields have no source occurrence; omission still makes no assertion, distinct from explicit source null policy.

Reports do not claim their own tests ran: each occurrence has `test_status: not_run` and a regression case reference. Separate execution evidence records the tests actually run against this revision. General printable unit labels are not scientific dimension validation or conversion. The source adapter must document accepted labels and explicit reviewed conversions; this tutorial accepts rate units exactly Hz.

## Golden replay and compatibility

```sh
python3 -B worked-examples/replay.py --check
python3 -B -m unittest discover -s . -p 'test_*.py'
python3 -B -m unittest discover -s worked-examples -p 'test_*.py'
python3 -B compare_legacy.py --baseline /path/to/prior/validate_bundle.py
```

Replay generates only inside a disposable temporary directory, then compares every generated bundle/report/ledger/invalid/blocked expectation and eight CLI reports by exact bytes. Missing, extra or changed outputs fail. There is no bless/update mode. `build_examples.py` remains an explicitly invoked authoring tool that overwrites candidate expectations; never invoke it as a validation shortcut or on a released kit. Golden changes require review. Replay is serialized because it temporarily redirects the existing generator's output root.

Compatibility tests cover old writer→new reader and new writer→old reader. An optional property emitted by a new writer is rejected by an old closed reader. Calling a field optional does not make emission backwards compatible. The regression also tests exact namespace/name bytes, distinct authorities, Unicode normalization and whitespace differences, native UUID preservation and mutable locator stability. No implicit normalization or unit coercion is introduced.

Transaction requirements are strengthened in the existing write rejection plan: one DataJoint connection/transaction, whole-import abort on statement failure, explicit content equality for replay, no silent unknown-field dropping. All 13 DB cases remain unrun and unsupported. See [write rejection contract](worked-examples/WRITE-REJECTION-CONTRACT.md).

Primary references: [JSON Schema output](https://json-schema.org/draft/2020-12/json-schema-core#section-12), [format annotation/assertion](https://json-schema.org/draft/2020-12/json-schema-validation#section-7), [RFC6901](https://www.rfc-editor.org/info/rfc6901/), [UUIDv5](https://www.rfc-editor.org/rfc/rfc9562.html#name-uuid-version-5), [schema evolution directions](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html).
