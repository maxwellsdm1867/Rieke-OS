# Exact JSON transport: scoped implementation and evidence

2026-10-09. This is source/native qualification on owned disposable projects with
the installed bundle's MySQL 8.4.2, not a packaged candidate or release approval.
See [the independent policy review](h5-numeric-policy-review-2026-10-09.md) for the
distinction between acquisition representation and exact authored state.

## Implemented scope

`workspace_json_transport.mysql_json_expression` builds parameterized JSON text
plus typed DOUBLE operands for finite floating leaves. Targeted authored writes
and offline snapshot restore can preserve the supplied value, rather than silently
rounding an equality threshold or breaking a sealed recipe. Callers retain their
transactions and must verify exact JSON readback before commit. The primitive has
at most 1,024 float leaves, 16 nested JSON_SET calls, and 4 MiB of added UTF-8
path/number parameters. The original JSON retains its existing server packet limit;
large membership lists do not acquire a new 4 MiB size cap. Unsupported typed
expressions fail explicitly, before their row is written.

`workspace_portability._dump` keeps a global read lock while creating the ordinary
logical dump and scanning donor JSON. `prepare_project` also retains its existing
outer read lock from exact inventory through dump completion. Only leaves that
change under donor JSON text reparsing produce a typed correction appendix. Each
update has at most 64 paths and 1 MiB of SQL. Values and paths use hex literals;
identifiers come from the admitted server schema and are quoted. There is no SQL
dump parser, tolerant fingerprint, alternate inventory, or extra restore privilege.
The appendix is sealed inside the existing `database.sql`, and the original exact
database inventory must pass before the owned recipient can publish.

Correction-bearing tables require complete primary keys. UPDATE triggers must
either be absent or belong to the already-verified derived set omitted from the
dump. Automatic ON UPDATE and generated columns cause refusal. Foreign keys are
retained and tested; JSON correction does not modify their ordinary key columns.
CHECK constraints are not bypassed and may cause a private restore to refuse.
Errors preserve the source and prevent publication of a purportedly verified copy.

External legacy migration is unchanged: its before/after inventory alone is not a
quiescent snapshot suitable for this appendix. No global source-server lock was
added to that separate workflow.

## Native evidence

- `restore-precision-corpus-result.json`: 4,096 deterministic finite binary64
  values, five MySQL text conversions. 427 values changed again after their first
  conversion; maximum observed distance from the original was five representable
  steps. This justified a transport fix beyond the stable 85-value H5 subset.
- `exact-json-transport-native-result.json`: two direct donor/recipient logical
  copy cycles over 4,096 finite values. Each corrected 441 leaves in 34 documents
  and reproduced the complete exact inventory. Restart preserved that inventory;
  a deliberately changed integer failed it. Composite quoted/backslash/Unicode
  keys and a foreign key survived. SQL NULL remained distinct from JSON null.
  The typed expression preserved signed zero, subnormals and extreme finite
  values; a 5.28 MiB base JSON document with one float passed. This receipt
  qualifies the mechanism, not ordinary project preparation by itself.
- `integrated-json-transport-result.json`: public `save`/`load`/offline `restore`
  retained an exact numeric predicate. A deliberately substituted ordinary JSON
  encoder failed exact readback, rolled back SQL, retained the previous predicate,
  and removed the pending marker. Public `prepare_project` and `restore_project`
  then completed two verified cycles with a drifting JSON value and that saved
  predicate. Both recipients reported MySQL 8.4.2, retained the exact original
  conversion witness and predicate, and preserved inventory across restart. The
  existing version-1 transfer format was unchanged. These projects intentionally
  had no scientific sources; the real-H5 app reopening lane is separate.
- `exact-json-transport-sqlmode-result.json`: typed parameter expressions and the
  production dump appendix actually executed with `NO_BACKSLASH_ESCAPES`. Exact
  donor/recipient inventory passed, including quoted, backslash and Unicode keys.
  The owned recipient's prior global mode was restored and both runtimes stopped.

All four receipts and their probe scripts are retained under
`/private/tmp/disco-h5-diagnosis-20261009/`. Source byte hashes accompany the two
transport receipts; the integrated receipt verifies the same bytes at completion.
Owned runtimes were stopped cleanly. An initial integration probe's unquoted
reserved database identifier failed test setup and was corrected before the
reported passing run; it was not a product failure.

The focused command covering JSON transport, explicit SQL-null readback, snapshot
rollback, portability, generation-trigger fencing and existing snapshots passed **49 tests**, with three
pre-existing opt-in native tests skipped. The separate native evidence above is
not relabeled as those skipped test cases.

## Qualification limits

Initial native qualification is MySQL **8.4.2 → 8.4.2**. A different recipient
parser may change donor-stable leaves that need no appendix on the donor; the
unchanged exact inventory should reject that recipient. Cross-version transport
and reopening accepted acquisition catalogs after a parser upgrade require their
own qualification. No silent ULP-only fallback is provided.

Dump SQL NULL versus JSON null preservation does **not** qualify snapshot null
typing: the pre-existing snapshot capture representation collapses both root
values to Python None, and its historical writer treats that value as JSON null.
This patch retains that existing format; it fixes finite-float transport without
inventing a new snapshot schema. The shared readback helper can distinguish the
two when the caller provides an explicit SQL-null field contract.

Current source-manifest locator rebasing is outside the generic typed writer;
its supported fields are strings, integers, booleans and counts. No arbitrary
floating manifest-extension contract or general SQL-schema preservation claim
is added. Installed application bytes and scientific originals were not changed.
