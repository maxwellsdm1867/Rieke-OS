# Protocol-local SQL work in a shared datastore

Researched 2026-10-11. This is a design recommendation from official SQL documentation, not evidence that Disco already implements it or that an application benchmark passed.

A protocol can remain a small, indexed working set inside one authoritative database. Separate copied databases are unnecessary. The performance contract should cover membership acquisition, freshness, tree construction, paging, and cache admission—not only the final SQL result filter.

## Membership relation and query shape

**Proposed design:** store explicit, ordered membership with a stable scope identity and revision. For example:

```sql
CREATE TABLE protocol_member (
  protocol_id TEXT NOT NULL,
  membership_version INTEGER NOT NULL,
  ordinal INTEGER NOT NULL,
  epoch_uuid TEXT NOT NULL,
  PRIMARY KEY (protocol_id, membership_version, epoch_uuid),
  UNIQUE (protocol_id, membership_version, ordinal)
);
CREATE INDEX protocol_member_by_epoch
  ON protocol_member(epoch_uuid, protocol_id, membership_version);
```

This is illustrative SQLite syntax; use existing identity types, constraints, and project partitioning in the real schema. The UUID key enforces set membership; ordinal preserves recipe order. The reverse index supports finding affected protocols on a member mutation. Retain old versions only as required by snapshot/recovery policy.

An ordinary page should seek the protocol/version/ordinal range and fetch metadata by indexed UUID:

```sql
SELECT m.ordinal, e.epoch_uuid, e.cell_id
FROM protocol_member AS m
JOIN epoch_metadata AS e ON e.epoch_uuid = m.epoch_uuid
WHERE m.protocol_id = ? AND m.membership_version = ?
  AND m.ordinal > ?
ORDER BY m.ordinal
LIMIT ?;
```

Composite indexes support equality on a leading key prefix followed by ordered/range access. SQLite can combine searching and ordering, and covering indexes can avoid table fetches. MySQL likewise uses leftmost prefixes of multicolumn indexes. These facts motivate the key order above; the optimizer must still be inspected. [SQLite query planner](https://www.sqlite.org/queryplanner.html), [MySQL multicolumn indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html).

**Recommendation:** reuse an existing indexed scope table if it already exists. Do not rebuild a temporary membership table or reserialize/hash every member for each page. Build once per membership revision and reuse through a trusted scope handle. For tree group counts or filtering, visit protocol members and their required metadata; aggregate cost can legitimately scale with membership size M. UUID lookups into shared B-trees retain a logarithmic dependence on total size N, so the realistic goal is no linear project scan, not literal mathematical independence from N. Broad discovery predicates remain separate global operations.

## Freshness without repeated global validation

**Proposed design:** use a compact authority tuple such as `(project incarnation, scope id, membership revision, relevant metadata revision, recipe/layout revision, index schema revision)`. A project incarnation changes on replacement/recovery, not every unrelated insert. Versions must change atomically with the data they certify. A membership-only revision is insufficient when member metadata, ancestry, tags, or query semantics can change.

A member mutation can identify affected scopes through the reverse index and increment their relevant metadata revision in the same transaction. Shared cell/recording metadata needs equivalent dependency invalidation. This moves work to mutations; measure fan-out when many protocols overlap. If complete invalidation cannot yet be guaranteed, a batched check of only the M members is a correct transitional design. Never replace a proved freshness contract with an unmaintained counter.

Read versions and data under one consistent snapshot, then attach the authority tuple to the response. SQLite WAL supports snapshot isolation; MySQL InnoDB REPEATABLE READ uses one consistent-read snapshot per transaction, whereas READ COMMITTED uses a new snapshot per read. [SQLite isolation](https://www.sqlite.org/isolation.html), [InnoDB consistent reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html).

For mutations, enforce the existing revision/authority precondition at commit, rather than trusting a previously rendered page. Within one read request, resolve one scope snapshot and pass it to tree/metadata helpers instead of independently reacquiring it. Different UI requests may share a verified immutable snapshot if their authority tuples match.

SQLite `PRAGMA data_version` is not a per-protocol revision: it detects other-connection commits at database scope, does not change for the same connection's commits, and is comparable only across observations from the same connection. It can signal that invalidation information needs refreshing, but is not the membership freshness token. [SQLite data_version](https://www.sqlite.org/pragma.html#pragma_data_version).

## Verification and benchmark gates

SQLite `EXPLAIN QUERY PLAN` reveals loop order, indexed searches, whole-table scans, and temporary sorting. Inspect that the membership range drives indexed metadata probes; writing membership first in SQL alone does not guarantee execution order. A scan of a small materialized scope is acceptable; a scan of all metadata for a tiny scope is the regression. Do not depend on exact plan text in production because SQLite documents its output as unstable. [SQLite EXPLAIN QUERY PLAN](https://sqlite.org/eqp.html).

MySQL `EXPLAIN ANALYZE` actually executes the statement and reports iterator time, actual rows, and loops, enabling verification against expected M or page-size work. Use read-only benchmark queries. [MySQL EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html).

**Proposed benchmark:** keep the same 2,000 ordered members and metadata while growing unrelated project records from 20,000 to 200,000 to 1,000,000. Separately increase membership size with fixed project size. Measure cold scope acquisition, first tree build, warm tree expansion, page revisit, and selection. Record wall time, SQL calls, HTTP requests, membership rebuilds, fingerprint entries visited, tree nodes built, cache retained bytes, and plans. Separate startup/index construction from steady-state reads. Confirm exact membership/order and freshness after member edits, unrelated edits, additions/removals, recipe changes, index rebuild, recovery, and held concurrent requests. Report both latency and work counts; a cache hit that silently walks all project fingerprints fails the contract even if a small fixture is fast.

## Concrete source inspection: explicit membership still permits global SQL work

Read-only inspection of `/private/tmp/disco-membership-local-20261012`, specifically `python/disco/metadata/typed_query.py`, `typed_index.py`, and `disk_index.py`. These observations describe those files at inspection time; no application files were edited.

| Location | Observed behavior | Consequence for small explicit membership |
| --- | --- | --- |
| `typed_query.py:123-131` | Sources use an uncorrelated `IN (SELECT e.epoch_id FROM native.epochs e JOIN supplied_sources ...)`, separately intersected with supplied epoch IDs. | Source membership can enumerate all project/source epochs before intersection. |
| `typed_index.py:528-557` | Existing correlated metadata predicate optimization is enabled only for `cell`, `block`, or `group` scope keys. | `epoch_ids` dictionaries and direct iterable membership miss this optimization. |
| `typed_query.py:65-96` | Unoptimized field exists/missing and typed comparisons form global field-membership subqueries. | A tiny protocol can enumerate a common field's project-wide membership. |
| `typed_index.py:492-505` | Facet `selective` mode likewise recognizes only cell/block/group. | Explicit member facets do not select the existing outer-core/point-field join path. Plan choice can start from project field memberships. |
| `typed_query.py:83-93` | Contains and wide-number comparisons stream every dictionary entry for a field through Python before executing final SQL. | Extending the correlated predicate flag alone does not remove this project-dictionary cost. |
| `typed_query.py:114-116,155-159` | Each `_where` rebuilds supplied membership and dictionary matches. | This is O(M), not O(N), but repeated count/page/facet calls can repeat scope construction. |

The schema already provides the needed point indexes: `epochs.epoch_id` primary key, unique epoch UUID, `epoch_values(epoch_id,field_no)` primary key, and typed dictionary `value_id` primary key. No new database copy or schema migration is needed for the immediate source/predicate/facet fixes. `typed_index.py:343-351` also checks three file signatures and cancellation rather than rescanning per-epoch fingerprints; preserve this cheap sealed-generation guard.

### Small EXPLAIN evidence

Owned in-memory SQLite 3.53.0 probe: 1,000 synthetic epochs, all sharing one source and one metadata value; two explicit members (IDs 7 and 23). This was a plan probe, not a latency benchmark or application qualification.

Current source form showed `LIST SUBQUERY`, `SCAN e`, and source-index probes before intersection. Replacing it with the following preserved the two result IDs and produced native-epoch primary-key searches:

```sql
EXISTS (
  SELECT 1 FROM native.epochs e
  WHERE e.epoch_id = c.epoch_id
    AND e.source_sha IN (SELECT source_sha FROM supplied_sources)
)
```

Use native `epochs.source_sha`, not unchecked `typed_core.source_sha256`, to preserve the current source-authority semantics. Initially specialize this form to explicit-ID scopes; retain the existing broad discovery strategy unless separate measurements justify changing it.

Current metadata equality form showed a list subquery scanning the field's reverse index. The existing structurally scoped rewrite produced `SEARCH ev USING PRIMARY KEY (epoch_id=? AND field_no=?)` followed by a typed value primary-key read and preserved results. Thus the minimal fix is to recognize explicit-ID membership as selective in both `_where` predicate rewriting and `summaries`/`preview` facet selection. Recognize key presence, not iterable truthiness; empty and generator scopes must retain their semantics.

### Remaining dictionary path and safe next step

`_where` currently compiles predicates before populating `supplied_scope`. To bound Python dictionary comparisons, prepare validated explicit membership before predicate compilation, then select **distinct value IDs reachable from supplied members** using membership → `epoch_values` point lookups → `typed_values` point lookup. Preserve `predicates.matches`, exact numeric equality, and original JSON. Do not add a Python DTO materialization or a field-global `DISTINCT` subquery. A clean hook for choosing the dictionary candidate iterator is safer than duplicating predicate semantics. Source filtering can further reduce candidates, but using all M explicit members already removes dependence on unrelated N rows. Consume generators once, maintain guard/cancellation calls, and ensure failed requests cannot leak prior scope state.

### Recommended tests

Extend `python/disco/metadata/tests/test_workspace_typed_index.py`:

- Run the native-truth predicate matrix under `{'epoch_ids': ids}` and `{'epoch_ids': ids, 'sources': ...}` without a cell/block/group key; the existing mixed-scope test includes a cell key and therefore hides this optimization gap.
- Cover both dict key orders, direct list/generator scopes, empty IDs/sources, duplicate/unknown IDs, excluded-source members, and invalid input. Preserve chronological output and pagination rather than input order (the present API uses `sort_rank`).
- Compare count, eager/streamed membership, all pages, groups, summaries and preview facets to native truth, including null versus missing, compound negation, empty `in`, nested JSON contains and wide integers.
- For a small fixture with many unrelated matching epochs, instrument SQLite progress/operation counts or inspect representative plans to demonstrate that source filtering and metadata predicates visit scoped IDs. Avoid brittle exact EXPLAIN text assertions across SQLite versions.
- For dictionary fallback, instrument calls to `predicates.matches` or capture candidate value IDs; increasing unrelated distinct field values must not increase comparisons for fixed explicit membership.
- Preserve tests for cancellation, sealed-generation mutation, and no row/detail DTO decoding in summary-only operations.

These are local SQL improvements. They do not by themselves remove global work done by callers before opening the typed query, and they do not replace the parent's end-to-end serial scaling benchmarks.
