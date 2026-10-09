# H5 floating metadata comparison policy

Research date: 2026-10-09. Policy recommendation, not an implemented contract.
Application changes and packaging are outside this note.

## Finding

A difference in the last displayed digit can be scientifically negligible without
being an identical stored value. Rejecting every such metadata difference is not
the only defensible policy. Accepting a small, documented representation error is
reasonable when original H5/parsed metadata remain the authoritative source and
identity, structure and discrete values remain exact. This is our recommendation,
not a requirement imposed by IEEE 754 or MySQL.

Binary64 has 53 significant binary bits. The familiar 15–17 decimal-digit range
describes different conversion guarantees; it does not mean every conversion must
lose the last digit. Oracle's numerical guide explains that double-to-decimal and
back needs at least 17 significant decimal digits for recovery. Python documents
that its shortest `repr` preserves `eval(repr(x)) == x`. Thus an already-rounded
machine float can be transported exactly even though it approximates a real-world
measurement. [Oracle numerical guide](https://docs.oracle.com/cd/E19059-01/stud.10/819-0499/ncg_math.html),
[Python floating-point tutorial](https://docs.python.org/3/tutorial/floatingpoint.html).

RapidJSON documents a maximum 3-ULP error in its normal-precision decimal parser
and a separate full-precision mode. MySQL report #112904 describes the matching
JSON-text-versus-typed-DOUBLE discrepancy, including JSON_SET → dump → restore
checksum failure. The reporter supplies the parser diagnosis; the verification
team closed the report as “Not a Bug.” It is evidence of the reported behavior,
not an official promise of a fix or a universal MySQL error bound.
[RapidJSON internals](https://rapidjson.org/md_doc_internals.html#ParsingDouble),
[MySQL #112904](https://bugs.mysql.com/bug.php?id=112904).

## Options

The evaluations in this table are engineering judgments informed by those sources.

| Policy | Benefit | Limitation / required scope |
| --- | --- | --- |
| Relative/absolute tolerance (`isclose`) | Conventional for measured or computed results when the scientific error budget is known. | A single default is not an error budget for arbitrary metadata. Python's default relative tolerance, `1e-9`, spans approximately 4.5 million adjacent steps just above 1.0; far wider than this parser discrepancy. |
| Small ULP allowance for finite floating metadata | Minimal read-only compatibility rule tied to machine representation, with exact structure and discrete fields. | Needs explicit edge cases, runtime qualification, and source-anchored comparisons. Closeness cannot become a grouping/identity relation. It admits any defect within the allowance, not only parser rounding. |
| Exact match to the expected MySQL encoding | Reparse the original source JSON on the same server and require the stored document to equal that result; closely attributes accepted change to the known path. | Runtime-dependent and not proof of a small error by itself. Combine with a bounded source-to-result float check. Not generally stable across different runtimes or repeated conversion of already-converted values. |
| Precision-preserving conversion plus strict validator | Preserves current exact queries, hashes and stored binary64 values; a strict check remains useful for transport integrity. | More implementation and validation work, including dump/restore and app-state writes. Import-only correction is incomplete. Not required merely because the data are scientific. |

PEP 485 defines `isclose` using the maximum of relative and absolute tolerances,
expects computed-result comparisons, and deliberately defaults absolute tolerance
to zero because no nonzero default suits every scale. Near-zero scientific
tolerances must therefore come from the domain, not a guessed universal epsilon.
[PEP 485](https://peps.python.org/pep-0485/).

## Recommended decision and guardrails

For the immediate H5 import rejection, prefer a documented **bounded representation
comparison** over a broad `isclose` default or an immediate general-purpose transport
rewrite. A stronger version also requires exact agreement with the server's encoding
of the original document. Keep lossless storage as an independent option if exact
query behavior or restoration contracts require it. This recommendation is now
being evaluated in the scoped candidate described below.

- Apply tolerance only to finite floating leaves in acquisition metadata. Preserve
  exact object keys, array length/order, strings, nulls, booleans, integers, UUIDs,
  membership and parent/device relationships. Do not convert arbitrary numbers to
  float. IDs, counts, seeds and discrete settings remain exact even when supplied
  using a floating container if their field semantics identify them as discrete.
- Define the allowance in adjacent representable steps, with a separately stated
  boundary policy. A candidate three-step allowance is motivated by RapidJSON's
  documented error scale, not a proven universal guarantee for every MySQL value.
  Test both directions at powers of two, normal/subnormal boundaries and maximum
  finite magnitude. `nextafter` enumerates adjacent values; `ulp(x)` gives local
  spacing, which is not uniform across exponent boundaries.
  [Python math documentation](https://docs.python.org/3.11/library/math.html#math.nextafter).
- Make zero behavior explicit. Conservatively refuse nonzero-to-zero underflow
  under a compatibility exception. Treat `+0.0` and `-0.0` as equivalent only if
  the metadata contract does not use their signs; preserve the source sign in the
  authoritative artifact. IEEE equality equates signed zeros, but some operations
  distinguish them. [Java's IEEE equality discussion](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).
- Reject NaN/infinity under the existing JSON contract, rather than treating them
  as close. JSON syntax excludes both; JSON also permits implementations to limit
  numeric range and precision. [RFC 8259 §6](https://www.rfc-editor.org/rfc/rfc8259#section-6).
- Always compare with the immutable source, not the previously accepted value.
  Log source value, stored value, path, distance and runtime for an exception.
  Exercise import, same-source retry, save/reopen and repeated transfer cycles.

The last rule follows mathematically: tolerance is nontransitive. For a one-step
rule, `1.0`, `1.0000000000000002`, `1.0000000000000004` pass neighboring comparisons,
but the endpoints do not. For any finite step budget, the same construction extends
it. Repeatedly accepting the previous result can therefore authorize cumulative
drift; this is a risk, not a claim that every parser repeatedly drifts.

Do not replace exact grouping, deduplication or query predicates with this relation.
MySQL JSON numeric comparison, ordering and grouping follow their own documented
value rules. **Inference:** accepting neighboring floats at import does not make
them interchangeable in an exact equality filter or at a threshold. Verify relevant
app queries against retained source values, or use a separate explicitly defined
canonical representation. [MySQL JSON comparison and ordering](https://dev.mysql.com/doc/refman/8.4/en/json.html#json-comparison).

The candidate now under evaluation implements the three-step bound plus the exact
same-server encoding witness, scoped to import and same-source revalidation. Its
default validator remains exact. It treats Python integer types exactly; it does
**not** infer discrete semantics from keys such as `seed`, and integral-valued
floats remain eligible in principle. The stronger discrete-field recommendation
above would require an explicit field schema. An altered `42.0` fails when it does
not match the server's encoding of the original `42.0`; nevertheless the policy
must not be described as guaranteeing every semantically discrete float exact.

## Local audit and remaining work

Two local probes distinguish the proposed storage approaches:

- Starting with **typed, precision-preserving writes**, the dump probe reports
  85 values preserved before dump and 85 differences after ordinary restore.
  Evidence: `/private/tmp/disco-h5-diagnosis-20261009/dump-precision-result.json`.
- Starting with **ordinary JSON conversion**, all 85 affected values shift by one
  ULP on the first conversion; rounds 2–20 make no further changes, and the maximum
  distance from the original remains one ULP. Thus the naturally rounded values
  are stable under repeated conversion in this fixture. Evidence:
  `/private/tmp/disco-h5-diagnosis-20261009/repeated-conversion-result.json`.

These measurements support a bounded compatibility policy for this file. They do
not prove every binary64 value or a complete prepared-project restore. In particular,
the first probe is not evidence that a normally rounded database necessarily fails
its next dump/restore.

A later independent MySQL 8.4.2 probe tested 4,096 deterministic finite binary64
values (edge cases plus a seeded random corpus) through five successive
server-text-to-JSON conversions. It observed 1,229 first-pass differences and
1,069 later change events affecting 427 distinct values; the largest observed
distance from the original was five representable steps. There were no SQL errors.
For example, `5.551115123125782e-17` first became `5.5511151231257815e-17` and then
returned to its original value, while `2.6513785690225286e-213` changed to
`2.651378569022529e-213` and then `2.6513785690225292e-213`. This proves that the
85-value fixture's stability cannot be generalized to ordinary JSON values.
Evidence: `/private/tmp/disco-h5-diagnosis-20261009/restore_precision_corpus.py` and
`/private/tmp/disco-h5-diagnosis-20261009/restore-precision-corpus-result.json`.
The owned disposable server was stopped after the probe. These are conversion
tests, not a completed full-project transfer test.

**Design implication:** an alternate normalized backup hash by itself is
insufficient: a second-conversion value may fail the current source-anchored
import/read witness. Exact preservation of the donor's existing value avoids that
problem without relaxing backup identity. Following independent review, the
scoped `workspace_json_transport.py` helper was integrated into owned prepared
transfers and snapshot restoration. The existing exact inventory remains intact;
external migration was not expanded. The separate
[transport evidence note](h5-json-transport-2026-10-09.md) records native same-runtime
qualification, bounds, refusal conditions and remaining limits.

Baseline source inspection found that `workspace_portability._database_inventory` hashes
canonicalized values exactly, `_dump_logical` uses ordinary mysqldump, and
`workspace_state_snapshot._restore` inserts serialized JSON. Portability also
reserializes source manifests during locator rebasing. Consequently, relaxing only
the H5 comparison does not change the existing exact transfer checker, while fixing
only the H5 writer does not guarantee exact restoration. These are separate
contracts; the scoped implementation and evidence are linked above. Current
source-manifest rebasing retains its existing strings/integers/counts shape; no
general arbitrary-JSON manifest extension guarantee is claimed.

Before adopting the candidate: complete negative controls for changed
IDs/integers/keys and larger numeric differences, and test source-anchored repeated
round trips plus exact filtering/grouping. No source, native, packaged-app or
release qualification is implied by this note.

## Independent source review: related boundaries

`workspace_service.py` verifies the metadata SHA before loading the sealed parsed
document and building details, current fingerprints and the metadata read model
(`_read_source_metadata`, refresh around lines 528–590). However, the baseline
`recording_workspace.evaluate_protocol_file` computes `metadata_hash` values from
SQL epoch JSON, and **every current refresh compares those hashes with the verified
source hashes** before publishing (around lines 634–638). This is an active
admission gate, not merely a dormant legacy consumer. Parent native validation
reported `Database epoch metadata differs from verified import` after the initial
import-only candidate succeeded. Thus an import-only policy change is incomplete.
The query's membership selection uses protocol names and identities, but its
metadata gate also needs the bounded representation proof before it can admit the
source-derived current model. The candidate evaluator now has that explicit
opt-in; source-authoritative query/display claims require that gate to pass first.

The adjacent browser integer boundary is already protected. Actual source ticks
such as `639185810498529170` exceed JavaScript's exact integer range, but
`workspace_api.ExactMetadataJSON` is installed at application creation and
recursively emits those Python integers as decimal strings. The epoch-detail
route uses that provider through Flask `jsonify`; the detached response encoder
retains the same rule. The existing actual-route regression
`WorkspaceAPITests.test_browser_metadata_preserves_exact_source_ticks` passed on
October 9 with the pinned runtime: the HTTP result contains exact text and the
underlying source integer remains unchanged.

A standalone Node parse of an unquoted tick does round it, but that bypasses the
application's provider and is not evidence of a Disco transport defect. Frontend
metadata copying preserves the encoded text and refuses to generate numerical
predicates from encoded wide integers. No new transport policy or codec is needed
for this finding. The JSON string does not retain an explicit integer type tag;
that pre-existing format limitation is separate from precision preservation.
