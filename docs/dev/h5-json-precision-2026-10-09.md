# H5 import JSON precision diagnosis and candidate

## Observed failure and evidence

The untouched source `/Users/maxwellsdm/Downloads/2026-07-02_E.h5` has SHA-256
`72af5187843ece08ea4fa79a120f0d3806cf3294b70c9f041eaee94f7c0ce979`.
The installed Disco 0.1.9 package identifies clean application source
`f9788f81f4fb3f529c358eaafabd89ace47b2911`, MySQL 8.4.2, and parser
`5dc9018ff754e1a01f60d929ceaf4e7f40815e70`. An owned disposable desktop-backend
project reproduced the failure in approximately 55 seconds. Parsing found two
cells, 1,029 epochs, 2,058 responses, 1,029 stimuli and nine protocols.

The first rejected epoch was `7d2575ec-984d-4545-8ca3-d298fc0fa46e`, DovesMovie:
`backgroundIntensity` was `0.15261696363083765` in both H5 and parsed metadata,
but `0.15261696363083763` in native MySQL JSON. Independent native SQL reproduced
the change with `CAST(text AS JSON)`. `CAST(text AS DOUBLE)` followed by a JSON
constructor retained the exact binary64 value. All 85 observed differing values
(48 backgroundIntensity, 18 equivalentIntensity, 19 equivalentIntensityConeLin)
survived that typed path exactly. Both failed import attempts left zero experiment
and epoch rows. The UI failure's `catalog_committed: null` reflects conservative
transaction error reporting, not observed partial persistence.

Owned original evidence is retained outside Git at
`/private/tmp/disco-h5-diagnosis-20261009/`: `diagnosis.json`,
`exact-mismatch.json`, `json-roundtrip.json`, `numeric-probe.json`,
`baseline/result.json`, and reproduction/capture/numeric-probe scripts. The
original H5 was rehashed unchanged. This is a real native backend reproduction,
not a UI rendering or packaged-candidate qualification.

## Chosen import policy

The isolated candidate starts from live GitHub main
`5aaf0beb983ccc32bfaa5eef53f6faa99ef21eab` (verified October 9). DataJoint's JSON
placeholder uses ordinary `json.dumps`, followed by MySQL JSON text parsing.
The pinned population helper forwards the dictionaries. The source parser did
not cause this discrepancy. A one-ULP difference here is approximately
2.78e-17 absolute, with no demonstrated scientific significance; the old exact
catalog comparison was stricter than this storage converter's representation.

The chosen fix is a read-only, acquisition representation policy in
`validate_catalog_identity(..., mysql_json_rounding=True)`. Ordinary validator callers
remain exact by default. New imports and same-source rechecks use the same policy:

1. Exact documents need no extra query.
2. Only properties, attributes and parameters can use the representation rule.
   Their complete structure, keys, sequence order, Python JSON types, integers,
   booleans, text and nulls must match. Both values must be finite binary64 for a
   differing leaf. Zero sign and zero versus nonzero remain strict.
3. Each differing float must lie within three representable binary64 steps of
   the original source. This is a conservative application cap inspired by the
   RapidJSON documentation, not a promised MySQL bound or an assertion that its
   documented ULP error uses this exact bit-distance metric.
4. The entire stored document must also exactly equal this server's independent
   `CAST(original source JSON AS JSON)` result. A different nearby float is not
   accepted merely because it fits the step cap. This establishes consistency
   with the current converter, not historical cause or scientific significance.

The source remains the anchor on every recheck; no previous catalog value becomes
new authority. All UUID membership, parent links, protocol identity, stream/device
links and scalar-column rules stay exact under their existing encodings. No metadata or SQL rows are rewritten, and no fuzzy comparator is applied to
grouping, querying or fingerprint equality. Integer-valued float settings are not identified by field-name guesses:
like other float leaves, they require the whole-document converter witness.
An exactly represented 42.0 seed changed by one ULP is explicitly rejected.

Witness queries are batched to at most 32 differing documents or about 1 MiB of
serialized JSON, with a larger individual document queried alone. Existing scoped
catalog reads are reused. There is no per-leaf SQL and no additional update.
Unknown SQL errors, malformed/incomplete witnesses, nonfinite values and larger
changes fail closed. A different future database converter may reject an unchanged old
representation even inside the cap. A converter-change regression explicitly
proves there is no ULP-only fallback. Qualification is limited to the pinned
runtime; upgrades must test reopening previously accepted catalogs.

[The independent comparison-policy research](h5-float-comparison-policy-research-2026-10-09.md)
compares conventional relative/absolute tolerances, ULP bounds, converter witnesses
and exact-write alternatives. A general numerical-computation tolerance is a
valid tool, but this import can make a narrower, directly tested claim about a
specific representation change. This policy does not assert every one-ULP change
is scientifically harmful or that all numerical equality should be exact.

## Source authority and persistence

WorkspaceService detail and typed read-model construction use sealed original
`metadata.catalog.json`: its checksum is verified, H5 identity is checked, and
source parameters populate detail objects and metadata fingerprints. A native
end-to-end test exposed a second active boundary: refresh compares the default
SQL evaluator's catalog-derived metadata hash with the original-source hash.
Accepting the import alone was therefore insufficient to open the workspace.

`evaluate_protocol_file` now has an explicit, optional `verified_source_metadata`
argument, supplied by WorkspaceService only after source/H5 admission. It receives
source rows plus lazy source details. Exact SQL/source hashes follow the existing
fast path without loading details or querying the converter. For a differing
hash, the evaluator loads only that epoch's original details, verifies their exact
hash against the admitted source row, and applies the same bounded/full-document
converter witness. Only after this succeeds does it publish the original source
hash. Hash comparison itself remains exact. Unknown UUIDs or inconsistent source
fingerprints reject before publication. The ordinary evaluator without admitted
source context continues to return its original catalog-derived hashes.

Native repeated-conversion evidence shows all 85 affected values move one ULP on
the first parse and remain unchanged for rounds 2 through 20. This is evidence for
this file, not a general idempotence guarantee. A typed-write prototype preserved
the original catalog bits, but ordinary logical dump/restore changed all 85 back
to the normal JSON representation. That prototype was therefore superseded by the
smaller policy above; its patch and native evidence remain outside the repository.
No repair adapter or private DataJoint monkeypatch remains in the candidate.

The production transfer inventory continues to require exact canonical content
before path rebasing. Its comparator remains unchanged. Exact numeric transport for authored
writes, snapshots and logical backups is a separately qualified change; see
[the transport record](h5-json-transport-2026-10-09.md). The snapshot format
still has its pre-existing SQL NULL versus JSON null ambiguity; this work does
not claim to fix it. A successful candidate import alone does not qualify transfer; ordinary
prepare/restore and an original-source recheck are separate required evidence.

## Related conversion audit and remaining gates

- The JSON risk covers properties and attributes on Experiment through Epoch,
  plus parameters on EpochBlock/Epoch, rather than only the observed protocol.
- Acquisition timestamps use the schema's documented DATETIME(0) encoding;
  the existing validator accepts only exact/truncated/documented-rounded values.
  Response rates and offset ticks are varchar and checked by exact decimal value.
- NumPy floating scalars become Python binary64 in the pinned parser. Wider input
  would need an explicit representation policy; the source check shares that
  encoder. This is a potential unsupported-input limitation, not observed here.
- The physical H5 parameter check now compares exact typed JSON, rejecting
  bool/int, int/float and signed-zero changes that Python equality conflated.
  There is no SQL converter at this boundary and no ULP allowance is applied.
  Actual pinned-parser tests also preserve an affected binary64 value exactly.
- Authored-state snapshots and logical MySQL dump/restore can also cross JSON text
  conversion. Persistence/restore must be checked before this candidate is called
  sustainable. A successful import alone is insufficient.

The lead scoped suite passes 176 tests with no skips in the installed pinned
Python/parser runtime. Preliminary native candidate-source CLI import and
same-source retry passed for the actual recording. After the read-admission fix,
WorkspaceService exposed the exact original parameter, all 1,029 epochs and nine
protocols; 16 response samples matched an independent H5 read exactly. Earlier
failed attempts and their diagnostics remain retained, including the import-only
trial that exposed the active SQL/source hash gate and a transfer-helper setup
failure before transfer ran.

Those are development composition results, not final committed-candidate or
installed-app qualification. Final source-frozen native import/reopen/query/group/
transfer/known-good-file checks and fixed-core/million-query regressions are written
as external receipts under `/private/tmp/disco-h5-diagnosis-20261009/`, bound to the
measured commit and runtime hashes. Installed-app replacement, UI testing, assembled
package qualification and release promotion remain outside this task.

## Upstream evidence

[MySQL report 112904](https://bugs.mysql.com/bug.php?id=112904) describes the same
JSON parse versus typed-double distinction and explicitly demonstrates differing
checksums after logical dump/restore. Its proposed RapidJSON full-precision flag
is a reporter's patch, not an available setting or a qualified server upgrade;
the report is closed as Not a Bug. [Report 118497](https://bugs.mysql.com/bug.php?id=118497)
records another JSON floating-value mismatch on 8.0.41 and is marked duplicate.
These primary reports support investigating the encoding boundary but do not
establish that a newer MySQL version fixes it.

## Focused test scope and retained evidence

The 176-test lead suite covers source/H5 identity, importer guards, catalog
collision/batching, import progress/API/worker leases, workspace refresh/service,
and the new numeric policy. It includes exact-default and source-type tests,
nearby nonconverter changes, the three/four-step cap, negative/binade/subnormal/
extreme finite values, integer/bool/type/shape/order refusal, signed-zero and
zero/nonzero refusal, count/byte batching, converter upgrades, SQL witness failure,
source anchoring on retries, lazy exact-hash admission, and rejection of SQL
metadata tampering during refresh. See `policy-backend-regression-tests-v3.log`.
SQL doubles do not establish native conversion.

Preliminary actual-source receipts are `policy-native-result.json` and its
preserved first/second failure receipts, with the explicit source compositions in
the JSON. `candidate-native-result.json` belongs to the superseded typed-repair
prototype and is not evidence for the final policy. Original file bytes and the
installed application have not been changed. Final committed results belong to
`policy-final-native-result.json` and separately retained benchmark receipts,
when those runs complete; this document does not predeclare their outcomes.
