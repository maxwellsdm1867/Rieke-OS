# Foreground trace scheduling: exact projection compatibility review

Reviewed against clean parent `5c78fd689c0c9c725272a7a7bdde359fe8b93e0e`.
The optional foreground flag changes scheduling for explicitly admitted trace
work; it does not change metadata projection semantics. This review admits one
complete five-file fingerprint vector, not arbitrary future scheduling edits.

## Exact source proof

`python/workspace_service.py` changes from SHA256
`3c9fc897975c3345b6290e33c8b10fa63f4b93386642eefed112ae29fcb29121` to
`a15fe9699c8fdd5134ddc4e8a6640e0de630af784d0c116cb601da4899eb181c`.
The actual diff contains exactly these AST edits:

- `_response_window_reader` gains keyword-only `foreground=False`; its existing
  `read_native_values` call gains `**({'foreground': True} if foreground is True else {})`.
- `WorkspaceService.trace_batch` gains keyword-only `foreground=False`; its existing
  `_response_window_reader` call gains the same conditional forwarding expression.

An independent AST check asserts exactly one named call in each function,
verifies both final keyword-only defaults are the literal `False`, and verifies
both new forwarding ASTs equal the parsed expression above. Removing only those
four asserted edits makes `ast.dump(..., include_attributes=False)` of the entire
module identical to the parent. No function, class, import, validation branch or
method body is excluded from comparison. The normalized full-module AST SHA256
is `405df5c15abc8d15ca04b7ae31d39ef91e0aebe8f50af53ce3279632c834354b`
(using the review environment's Python AST format).

All other vector owners are byte-identical to the parent:

| Ordered owner | SHA256 |
| --- | --- |
| `recording_workspace.py` | `6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230` |
| `disco/metadata/projection_cache.py` | `a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9` |
| `disco/metadata/metadata_objects.py` | `8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd` |
| `workspace_service.py` (reviewed candidate) | `a15fe9699c8fdd5134ddc4e8a6640e0de630af784d0c116cb601da4899eb181c` |
| `disco/metadata/projection_contract.py` | `04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024` |

The appended literal receipt retains the already-reviewed legacy contract
`d612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37`.
Earlier receipts remain unchanged. Unknown vectors still require their complete
five-file identity; no wildcard, partial-vector match, cache reseal, migration,
scientific-source exemption or projection-resolver change is introduced.

## Reviewed-use provenance

`python/lifecycle_diagnostic.py` remains byte-identical, SHA256
`88ab25a0b97bdd65dab7b3fba42b58ce30165a47be3c07d43efef186cd5c42a3`.
Its five reviewed sites keep the same selectors, AST hashes, categories, origins
and targets; only three `workspace_service` owner hashes change.

`python/tests/test_workspace_refresh_cache.py` remains byte-identical, SHA256
`347a06862c242e0a704598a6c1bdd72e6c84444cc3b625da27a3c369f55a1fa6`.
Its fifteen reviewed sites likewise preserve their exact reviewed structure,
with fifteen updated `workspace_service` owner hashes. Each affected record adds
a reason linked to this proof. No guard policy or owner exemption is widened.

The external review script and machine-readable result are retained in the task
kit at `evidence/direct-recovery/foreground-qos-projection-proof.py` and
`foreground-qos-projection-proof.json`. They bind exact parent/candidate bytes
and check all four inverse AST edits, the other vector files, and unchanged
reviewed-use source files. This is source-projection compatibility evidence only;
backend exact-value tests, packaged scheduling behavior and native performance
retain their separate qualification and source attribution.

## Validation

The strict AST/vector proof passed. `tools/architecture_guard.py check` passed
with the reviewed owner witnesses; its original stale-witness failure remains in
the external `foreground-qos-guard-before.log`, and the passing result is in
`foreground-qos-guard-after.log`. The guard implementation was not changed.

The existing `test_workspace_projection_contract` and
`test_workspace_refresh_cache` modules passed all 38 checks in 2.357 seconds using
`.rieke-runtime/benchmark-python/bin/python -B` with
`PYTHONPATH=python:python/tests`. Raw output is retained in
`foreground-qos-projection-tests.log`. `git diff --check` passed. These scoped
checks neither rerun native performance nor extend any benchmark sample count.
