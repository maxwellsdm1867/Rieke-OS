#!/usr/bin/env python3
"""CurationStore.update at several protocol sizes: elapsed ms and SQL statements.

Owned in-memory fixture only; never a user project, database or live port.
Production ``disco.decisions.curation.CurationStore.update`` runs unchanged.
The Curation table is an indexed in-memory double defined here (the shared test
double scans every row per insert, which would dominate timing). Each double
call stands for one SQL statement: ``insert1``/``update1`` one statement per row,
``insert`` one multi-row statement per call, and every ``to_dicts`` one SELECT.
Native MySQL latency per statement is not modelled; the statement count is the
portable result.

Cases per size N (every epoch in one call, as a full-protocol mask import):
  first   - N epochs without saved decisions: inclusion mask (writes N rows)
  toggle  - N saved epochs: flip every inclusion (rewrites N rows)
  noop    - N saved epochs: re-apply the current inclusion (changes nothing)

Run against any source tree with ``--source-root`` to compare revisions with
identical harness bytes.
"""
import argparse
import contextlib
import copy
import json
from pathlib import Path
import statistics
import sys
import time
import uuid

KEYS = ('project_uuid', 'protocol_uuid', 'epoch_uuid')


class Counter:
    def __init__(self):
        self.counts = {}

    def add(self, kind):
        self.counts[kind] = self.counts.get(kind, 0) + 1


class IndexedTable:
    """Primary-key indexed relation double with DataJoint-like calls."""

    def __init__(self, counter, rows=None, restrictions=()):
        self.counter = counter
        self.rows = {} if rows is None else rows
        self.restrictions = restrictions

    def __and__(self, restriction):
        return IndexedTable(self.counter, self.rows, self.restrictions + (restriction,))

    def proj(self, *fields):
        return self

    def to_dicts(self):
        self.counter.add('select')
        candidates = None
        for restriction in self.restrictions:
            if isinstance(restriction, list) and restriction and all(set(item) == {'epoch_uuid'} for item in restriction):
                wanted = {item['epoch_uuid'] for item in restriction}
                candidates = wanted if candidates is None else candidates & wanted
        fixed = {}
        for restriction in self.restrictions:
            if isinstance(restriction, dict):
                fixed.update(restriction)
        if candidates is not None and 'project_uuid' in fixed and 'protocol_uuid' in fixed:
            # Primary-key lookup, as an indexed SELECT ... WHERE key IN (...).
            rows = [self.rows[key] for key in ((fixed['project_uuid'], fixed['protocol_uuid'], identity)
                    for identity in candidates) if key in self.rows]
        else:
            rows = (self.rows.values() if candidates is None else
                    [row for key, row in self.rows.items() if key[2] in candidates])
        def matches(row, restriction):
            if isinstance(restriction, list):
                return any(matches(row, item) for item in restriction)
            return all(row.get(key) == value for key, value in restriction.items())
        return [copy.deepcopy(row) for row in rows
                if all(matches(row, q) for q in self.restrictions if not isinstance(q, list))]

    def insert1(self, row):
        self.counter.add('insert1')
        key = tuple(row[k] for k in KEYS)
        if key in self.rows:
            raise ValueError('Duplicate primary key')
        self.rows[key] = copy.deepcopy(row)

    def update1(self, row):
        self.counter.add('update1')
        key = tuple(row[k] for k in KEYS)
        if key not in self.rows:
            raise ValueError('Missing row')
        self.rows[key].update(copy.deepcopy(row))

    def insert(self, rows, replace=False):
        rows = list(rows)
        self.counter.add('insert_replace' if replace else 'insert')
        for row in rows:
            key = tuple(row[k] for k in KEYS)
            if key in self.rows and not replace:
                raise ValueError('Duplicate primary key')
        for row in rows:
            self.rows[tuple(row[k] for k in KEYS)] = copy.deepcopy(row)


class Connection:
    def __init__(self, counter):
        self.counter = counter

    def query(self, sql):
        self.counter.add('lock')
        return self

    def fetchone(self):
        return (1,)

    @property
    @contextlib.contextmanager
    def transaction(self):
        yield


def make_store(source_root, counter):
    sys.path[:0] = [str(source_root / 'python')]
    import disco.decisions.curation as curation
    curation_table, events, datasets = IndexedTable(counter), IndexedTable(counter), IndexedTable(counter)

    class DJ:
        pass
    dj = DJ()
    connection = Connection(counter)
    dj.conn = lambda: connection
    from unittest.mock import patch
    with patch.object(curation, 'workspace_tables', return_value=(None, None, events, None)), \
         patch.object(curation, 'curation_tables', return_value=(curation_table, datasets)):
        store = curation.CurationStore(dj, str(uuid.UUID(int=1)))
    return store, curation_table


def case(source_root, size, name):
    counter = Counter()
    store, table = make_store(source_root, counter)
    protocol = str(uuid.UUID(int=2))
    ids = [str(uuid.UUID(int=(3 << 64) | i)) for i in range(size)]
    fingerprints = {key: 'b' * 64 for key in ids}
    mask = {key: bool(i % 2) for i, key in enumerate(ids)}
    revisions = {key: 0 for key in ids}
    if name != 'first':
        store.update(protocol, ids, {}, revisions, fingerprints, 'bench', inclusion_by_epoch=mask)
        revisions = {key: row['revision'] for key, row in store.read(protocol, ids, fingerprints).items()}
        if name == 'toggle':
            mask = {key: not value for key, value in mask.items()}
    counter.counts.clear()
    started = time.perf_counter()
    store.update(protocol, ids, {}, revisions, fingerprints, 'bench', inclusion_by_epoch=mask)
    elapsed = (time.perf_counter() - started) * 1000
    counts = dict(counter.counts)
    writes = sum(value for key, value in counts.items() if key in {'insert1', 'update1', 'insert', 'insert_replace'})
    return elapsed, counts, writes


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--sizes', default='10000,50000')
    parser.add_argument('--samples', type=int, default=5)
    args = parser.parse_args()
    results = []
    for size in [int(value) for value in args.sizes.split(',')]:
        for name in ('first', 'toggle', 'noop'):
            samples, counts, writes = [], None, None
            for _ in range(args.samples):
                elapsed, counts, writes = case(args.source_root.resolve(), size, name)
                samples.append(elapsed)
            results.append({'size': size, 'case': name, 'median_ms': round(statistics.median(samples), 2),
                            'samples_ms': [round(value, 2) for value in samples],
                            'write_statements': writes, 'statements': counts})
    print(json.dumps({'source_root': str(args.source_root.resolve()), 'harness': 'benchmark_curation_writes',
                      'results': results}, indent=1))


if __name__ == '__main__':
    main()
