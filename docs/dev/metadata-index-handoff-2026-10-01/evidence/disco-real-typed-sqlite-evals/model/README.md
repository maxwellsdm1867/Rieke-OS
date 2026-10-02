# Actual metadata typed SQLite experiment

`typed_real.py` adapts the previous typedSQLite prototype to the full existing
native metadata index. It uses Python's standard `sqlite3`, without TypeSQL or
any new library. It is an isolated experiment, not an app change.

The input is the sealed 2,781-epoch SQLite clone. `build(source_db,target_db)`
requires a new destination. It retains all seven original tables and streams
hashes to verify unchanged JSON, compressed details, original field eligibility,
shared ancestor identities and payloads. It neither discovers new raw fields nor
reads compressed details during construction. A changed candidate is not covered
by the original production seal, and should be read with `TypedReal`, not passed
to `DiskMetadataIndex.open` with the old seal.

Original typed pattern: ordinary typed core columns, exact UUID lookup,
chronology and parent indexes, a bounded count/first-page/facet query, and group
cursors. Generic adaptation: every existing native field receives scalar kind,
number and string dictionary indexes. Native equality is represented separately
from original value JSON: integers and doubles of the same exact value merge,
booleans stay distinct, and recursive arrays/objects preserve the native equality
semantics. Wide integers take the original Python predicate dictionary fallback;
they are never converted to floating point. The observed input has no wide ints.

Interface:

- `build(source_db,target_db)` returns construction/preservation receipt.
- `TypedReal(db_path)` opens a persistent immutable read connection with a 32 MiB
  SQLite page cache and the production metadata Decoder's bounded shared cache.
- `membership(predicate=None,scope=None)` returns all matching UUIDs for oracles.
- `preview(predicate=None,scope=None,facet_fields=(),limit=60,cursor=None)` returns
  `{count, rows, cursor, facets}`. Rows are exactly the original row JSON. Each
  requested facet returns `{values,missing_count,present_count,values_truncated}`;
  each value is `{value,type,count}`. At most the first 60 distinct values are
  returned, in their first appearance order. Values use production semantic
  equality, including mixed integer/double fields.
- `page(...)` returns `{rows,cursor}` and fetches only the bounded row page.
- `detail(uuid)` uses the production Decoder with exact original compressed
  details and shared object references. It returns the same full mutable DTO.
- `groups(kind='cell'/'block',predicate=None,scope=None,cursor=None,limit=60)`
  returns `{groups:[{uuid,count}],cursor}`. Cells sort by UUID; blocks sort by recorded block start time and then UUID.
- `explain(predicate=None,scope=None)` reports membership/page query plans.
- `close()` closes the handle and decoder cache.

Predicates use the production `field/operator/value`, `all`, `any` and `not`
shapes and validation. Scope accepts a dictionary of native `protocol`, `cell`,
`block` or `group` equality values, or an explicit set/list of UUID membership.
Missing is absence from original epoch_values, null is a recorded null, scalar
range comparisons are numeric only. Contains uses production dictionary matches.

Page ordering is exactly the app's lexical `(date,start_time,epoch_uuid)` order.
`typed_core.sort_rank` assigns its 1-based position in the complete source universe.
The integer page cursor is the last returned global chronology rank; subsequent
pages use `sort_rank>cursor`, with no offset. Facet ordering uses the same ranks.
Cell group cursors use the last returned UUID. Block group cursors use `{start_time,key}` from the last returned block; comparison occurs after grouping. Caller-owned source generation
validation is required for reuse of cursors across a refreshed database.

Build receipt identifies which additions came from the earlier typed pattern and
which were required to retain all native field and detail semantics. Query timing
must be performed separately from build/verification and include JSON conversion
when comparing with native output. This real-data experiment does not establish
performance at one million real epochs.

V2: core string fields use one validation representative after the builder proves exact equality/presence/string kind and the reader checks dictionary kinds. This avoids decoding every UUID solely to establish the field type. No database tables changed. The original V1 source and receipts are preserved under `attempts/v1`.
