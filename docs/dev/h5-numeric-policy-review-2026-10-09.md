# Independent numeric policy design review — 2026-10-09

Decision: **REVISE**. Accept the separation of acquisition representation, exact
persisted scientific settings, and approximate arithmetic. Accept the narrow
import/read-admission candidate for further qualification on its pinned runtime.
Do not adopt the whole proposal as a general numeric/portability policy or expand
all JSON persistence paths in one change.

This is an independent design/source review, not native qualification. Reviewed
three diagnosis/audit documents, the recording_workspace.py,
workspace_catalog_identity.py and workspace_service.py diff against 5aaf0be,
the paused workspace_json_transport.py draft, and the saved 4,096-value conversion
result. No application code or databases were changed and no heavy tests ran.
The reported successful 1,029-epoch import, exact source detail/trace samples and
same-source retry are parent-supplied evidence, not independently rerun here.

## What makes sense

A storage conversion and a scientific computation need different contracts.
Persisting a supplied binary64 number can preserve it exactly; being an
approximation to a physical quantity does not make transport drift necessary.
An equality predicate or frozen recipe may change behavior or fail its hash after
even one representable step. Keep exact authored values, exact hashes, exact
identities and exact grouping. Use domain-specific absolute/relative tolerances
for arithmetic comparisons, with explicit near-zero behavior.

The actual acquisition candidate is usefully narrow. It compares to the immutable
source, preserves JSON types/structure/discrete values, requires a small float
change and a complete conversion witness, then admits the original source hash
and original source read model. It does not turn closeness into equality.
The additional refresh admission is necessary: the existing SQL/source hash gate
runs during ordinary reads. An import-only relaxation would be incomplete.

The exact H5-to-parser type-sensitive comparison is also appropriate. No MySQL
conversion occurs there. Do not spread the SQL exception to traces or other
source guards. The wide-integer browser issue is already protected, and no native
longdouble narrowing was demonstrated. Neither warrants a new codec now.

## Required revisions and answers

1. **Call this a runtime-specific compatibility exception, not conventional
   numerical equality.** A finite-float ULP allowance is a conventional tool;
   executing the current database parser as an additional witness is a custom
   integrity check. A float-only allowance would be simpler and less coupled to
   runtime, but would deliberately accept any nearby alteration. Keeping the
   witness is reasonable under the present integrity contract because it rejects
   a nearby value the converter does not produce. It proves consistency with the
   current conversion, not historical cause, lack of tampering, or scientific
   insignificance. Do not advertise those stronger claims.

2. **Three adjacent values is an application cap, not a demonstrated MySQL
   guarantee.** RapidJSON documents maximum 3-ULP error for its normal parser, but
   does not establish that this means the candidate's bit-distance metric for
   all MySQL inputs. Spacing changes at binade boundaries; decimal input and the
   original binary64 reference also need a clearly defined relationship. Keep
   the conservative three-step cap if desired, fail closed beyond it, and change
   wording in h5-json-precision-2026-10-09.md that calls three adjacent values
   “the documented bound.” Do not mechanically increase it to five because five
   was observed after repeated conversions: those are separate losses. The
   85-value fixture supports one step for that file, not universal coverage.
   [RapidJSON primary documentation](https://rapidjson.org/md_doc_internals.html#ParsingDouble).

3. **The witness creates a real upgrade compatibility dependency.** Suppose
   version A maps source x to y, and version B maps x to z. An unchanged stored y
   now fails, even if y remains within the cap. Exact donor backup preservation
   does not solve that read-admission problem. Qualify this candidate only on the
   pinned runtime; an upgrade must explicitly test reopening older accepted
   catalogs before promotion. Do not silently fall back to ULP-only acceptance
   when the witness fails. Longer term, choose one deliberate approach: exact
   source-preserving acquisition writes/rebuilds, or a versioned acceptance
   receipt binding source identity and exact accepted catalog content. Do not
   build a history of parser emulators now. A receipt is optional future design,
   not a requirement for the scoped fix.

4. **Keep zero/nonzero strict; signed-zero strictness is a conservative storage
   decision.** Crossing zero is not merely a tiny relative error and can erase a
   nonzero value or alter a sentinel. Preserving the zero sign costs very little
   here and aligns with exact source fingerprints. It is stronger than ordinary
   numerical equality, not a universal scientific requirement. Keep it for this
   fix unless a concrete supported input demonstrates the need for a separate
   normalization contract. Do not guess a universal absolute epsilon.

5. **Saved settings and backup exactness are separate workstreams.** Their exact
   contract is justified by equality filters, sealed recipes and existing exact
   transfer inventory, not by the acquisition tolerance. The source inspection
   identifies credible first-write defects but lacks native first-write proof.
   Reproduce one saved predicate and one sealed-recipe failure through their real
   APIs before integrating a shared writer. That proof should compare the initial
   supplied value, SQL readback, fresh API read and resulting query membership.
   Avoid an inventory-wide write abstraction before those cases pass.

6. **Do not integrate the dump appendix draft unchanged.** It discovers only
   float leaves changed by reparsing on the donor. A different recipient parser
   may change a donor-stable leaf, for which no correction is emitted. The exact
   final inventory should reject that restore, so this is primarily a portability
   limitation, not silent acceptance; nevertheless the design does not provide
   general cross-version exact transport. Restrict initial support to qualified
   runtimes, or carry all authoritative float leaves for recipient restoration.
   Keep the complete exact inventory gate. An alternate normalized hash is not
   sufficient: the corpus already disproves general reparse idempotence.

7. **A small explicit typed-JSON helper is justified only with bounded scope and
   exact readback.** Reusing it for proven authored writes and restoring existing
   values can avoid duplicated escaping/conversion code. Keep normal caller
   transactions and full primary-key identity. The draft's 64 leaves per nested
   JSON_SET is not a total expression-size/depth bound: large documents still
   create arbitrarily deep expressions. Define supported size/depth or use
   bounded sequential operations within the transaction before calling it a
   bounded implementation. Test quoted/unicode/path-like keys and SQL modes.
   Do not patch DataJoint globally or invent a universal tagged numeric schema.

The known MySQL report is supporting evidence for JSON-versus-DOUBLE behavior
and dump/restore risk, not proof of a fix, supported workaround for every number,
or a promised MySQL error bound.
[MySQL report 112904](https://bugs.mysql.com/bug.php?id=112904).

## Minimal progression and acceptance tests

First finish the narrow acquisition import and source-read admission change,
correct its claims, and retain the exact default. Required evidence:

- Real failing file imports, reopens and retries against the original sealed
  source; exact membership, source metadata/hash and representative trace values
  survive. Queries at the original value and immediately adjacent boundaries
  use the source value; inspect actual resulting membership and grouping.
- Negative controls reject altered UUID/parent/stream, integer, bool, JSON type,
  key/order/shape, wrong nearby float even inside the cap, and four-step changes.
  Exercise zero signs, zero/subnormal transitions, both sides of powers of two,
  extreme finite values and nonfinite refusal. Keep the strict default test.
- A converter-change double demonstrates that unchanged old accepted values can
  fail under a new witness. Document the upgrade limitation rather than claiming
  it is solved. SQL errors and missing witness results fail before publication.
- Run ordinary project prepare/restore, then refresh and source recheck, using
  both the actual file and at least a drifting corpus value. A fixture-only pass
  cannot establish general transfer compatibility. If this fails, do not describe
  the import candidate as a completed sustainable persistence fix.

Next reproduce the two authored first-write cases, then implement only the
needed exact writer call sites with transaction rollback/readback tests. Snapshot
restoration and logical backup can reuse its numeric primitive after separate
qualification. For backup, require exact donor/recipient inventory and source
reopen across repeated cycles, interrupted restoration refusal, and any runtime
pair actually claimed as supported. A same-version pass is sufficient for a
same-version claim; it is not cross-version evidence.

Defer generic field-semantic inference, wider-float codecs, universal epsilon,
fuzzy fingerprints/grouping, parser-version registries and broad migrations.
A source schema can eventually identify discrete quantities stored as floats;
field-name guesses cannot. Be explicit that the current candidate does not
promise every semantically discrete float is exact.

Overall: the narrow witness is defensible additional integrity checking, not a
necessary law of floating-point arithmetic. The larger exact transport effort
addresses real and separate contracts, but needs staged native evidence and a
clear runtime support boundary before integration.

## Additional dump construction conditions

The appendix is not just an alternative numeric serializer: it executes UPDATEs
after the main restore. If mysqldump has already recreated triggers, correction
updates can fire them, change audit/derived state or timestamps, and violate the
intended donor inventory. Restrict the first implementation to admitted schemas
without relevant triggers/automatic update side effects, or establish an explicit
restore order that corrects data before such behavior is installed. Do not assume
that setting the JSON value back is semantically inert. Foreign-key/check/generated
column behavior also belongs in the supported-schema qualification.

The dump, correction scan and donor inventory must describe the same database
snapshot. A quiescent owned project or shared consistent snapshot is sufficient;
separately timed reads are not. A before/after inventory is useful for detecting
changes but is not a substitute for a single snapshot if concurrent writers can
make and revert changes. Keep the existing publication fence and do not publish a
backup assembled from mixed states. All correction bytes must be included in the
sealed artifact and restoration must remain private until final inventory passes.

Preserve SQL NULL independently of JSON null. In the inspected draft, an original
SQL NULL is skipped while text JSON `null` is decoded as JSON null; that separation
appears intentional. Add an actual driver round-trip test because connectors may
return different representations. Cover empty containers, mixed JSON scalar types,
complete composite keys, extreme/subnormal finite doubles and signed zero. Typed
DOUBLE conversion plus exact readback can fail closed on unsupported values; it
must not silently replace them or claim all binary64 values are supported solely
because the 85-value real fixture passes.

## Revised design review addendum — 2026-10-09

The original REVISE verdict above is retained as the historical review. Subsequent
source inspection closes the design objections for the explicitly bounded
MySQL 8.4.2 candidate, subject to final integrated restore qualification:

- The three-step threshold is now described as an application cap; the live
  witness remains strict and parser-upgrade rejection is documented/tested.
  No fallback weakens the integrity gate.
- `workspace_authored_json.write_row` admits five explicit app-owned table
  schemas and preserves caller transactions, complete keys, readback and
  rollback. It does not patch DataJoint globally. The limited preset, explorer
  and export integrations are justified by demonstrated first-write failures.
- Typed expressions now cap total float leaves at 1,024 and added path/number
  parameters at 4 MiB, giving at most 16 nested JSON_SET expressions. The original
  document retains the database packet limit, so a large integer/string/member
  list does not acquire the same artificial limit. Unsupported expressions
  explicitly refuse rather than rounding silently.
- Logical corrections are bounded and refuse affected tables with unsafe UPDATE
  triggers, ON UPDATE columns or generated columns. Known disposable triggers
  may be omitted only through the existing verified trigger contract. Owned
  project dumping holds a global read lock across its dump and correction scan;
  prepare's outer lock also covers the donor inventory. External migration is
  deferred. This is an appropriate scope boundary.
- Donor/recipient claims are now limited to qualified MySQL 8.4.2, with exact
  recipient inventory retained. Cross-version behavior remains unqualified;
  requiring cross-version success is unnecessary for this narrower claim.

I inspected `authored-firstwrite-final.json`: actual Flask/native SQL rereads
preserve 0.15261696363083765; equality membership matches the initial fixture
member; explorer recipe hash verifies and fresh GET returns 200. Preset updates,
version rows, last-run values and export recipe/index checks preserve the value.
The injected failure returns 400 with unchanged rows and events. This receipt
qualifies owned two-epoch source fixtures, not packaged UI or arbitrary schemas.

I also inspected `exact-json-transport-native-result.json`: two correction/dump
cycles each report exact inventory, 34 corrected documents/441 float leaves,
exact restart, tampered-integer detection, SQL NULL versus JSON null distinction
and successful NO_BACKSLASH_ESCAPES exercise. A 5,280,049-byte original document
with a small typed overlay passed. These are transport-module receipts, not by
themselves an ordinary prepared-project/source-reopen or snapshot test.

One pre-existing limitation remains outside this numeric change: app-state
snapshot `_column_value` maps SQL NULL and JSON null to the same Python None.
Both old and revised snapshot writers restore that as JSON null. Do not claim
snapshot SQL-NULL distinction from the logical-dump test; correcting the snapshot
format would be separate work. This is not a newly introduced numeric regression.

At this inspection point, no blocking design defect remains in the revised
bounded policy. Integrated prepare/restore and snapshot evidence still must be
recorded before calling the corresponding application paths qualified. Packaging
must include both new runtime helper files; source tests do not establish that.

The subsequently inspected `authored-firstwrite-final-current.json` supersedes
the authored receipt above and repeats the successful checks with five recorded
source hashes. It includes the verifier's explicit `sql_null_fields` handling:
SQL NULL is required only when named by the authored caller; ordinary None in the
numeric expression denotes JSON null. This closes readback's former null-kind
ambiguity without claiming to repair the legacy snapshot format.

### Final bounded design verdict

**ACCEPT the revised design for the stated pinned-runtime scope.** This closes the
original design revisions; it does not grant packaged-app or release qualification.
No further numeric-policy abstraction is required for this change.

`integrated-json-transport-result.json` now records the public snapshot restore
path preserving its supplied predicate, refusing an injected bad encoder and
rolling back to the prior predicate. Two public prepare/restore cycles report
verified packages, MySQL 8.4.2 recipients, preserved source-JSON conversion witness,
exact restarted inventories and unchanged transfer format. All three production
source hashes match before/after the run. I inspected that receipt after completion.
The owner reports 48 focused unit checks passed; I did not rerun them.

That integration fixture is an owned empty project populated with numeric corpus
and settings, not the actual 1,029-epoch H5 project. Final real-H5 restored-app
reopening and packaged qualification remain the lead task's separate gates.
The accepted design does not imply those gates have passed. Parser upgrades,
external database migration, arbitrary schema side effects and the legacy snapshot
SQL-NULL ambiguity remain outside the qualified claim.
