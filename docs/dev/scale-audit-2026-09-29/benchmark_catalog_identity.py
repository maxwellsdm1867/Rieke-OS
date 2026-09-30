"""Measure the complete ownership verifier with synthetic indexed SQL doubles.

No database, file parsing or waveform reads. The fake semi-join uses a hash
membership lookup so it does not introduce a quadratic test-only nested loop.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import workspace_catalog_identity as validator
from test_workspace_catalog_identity import Rows, fixture


class IndexedRows(Rows):
    def __and__(self, restriction):
        conditions = restriction.rows if isinstance(restriction, Rows) else restriction if isinstance(restriction, list) else [restriction]
        groups = {}
        for condition in conditions:
            keys = tuple(sorted(condition))
            groups.setdefault(keys, set()).add(tuple(condition[key] for key in keys))
        selected = [row for row in self.rows if any(tuple(row.get(key) for key in keys) in values
                                                  for keys, values in groups.items())]
        return IndexedRows(selected, self.fetches, self.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs', type=int, default=100000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.epochs < 2 or args.epochs % 2:
        parser.error('epochs must be positive and even')
    if args.output.exists():
        parser.error('Choose a new output file; preserve earlier evidence')
    path = Path(validator.__file__)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    started = time.perf_counter()
    source, catalog, rows, fetches = fixture(args.epochs // 2)
    for name, relation in vars(catalog).items():
        setattr(catalog, name, IndexedRows(relation.rows, relation.fetches, relation.name))
    construction = time.perf_counter() - started
    started = time.perf_counter()
    counts = validator.validate_catalog_identity(source, catalog, 7)
    elapsed = time.perf_counter() - started
    fetch_count = len(fetches)
    rows['EpochGroup'][0]['parent_id'], rows['EpochGroup'][1]['parent_id'] = rows['EpochGroup'][1]['parent_id'], rows['EpochGroup'][0]['parent_id']
    try:
        validator.validate_catalog_identity(source, catalog, 7)
    except validator.CatalogIdentityConflict as error:
        rejection = error.conflict['kind']
    else:
        raise AssertionError('Swapped-parent corruption accepted')
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    report = dict(epochs=args.epochs, counts=counts, fixture_seconds=construction,
                  validation_seconds=elapsed, table_fetches=fetch_count,
                  peak_process_rss_native_units=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  rss_units='bytes on macOS, KiB on Linux; entire process including fixture and deep-copy fetches',
                  swapped_parent_rejection=rejection, helper_sha256=before, source_unchanged=before == after,
                  environment='Synthetic indexed relational doubles with deep-copy fetch; no native SQL/H5 parsing; one timed sample')
    assert before == after and counts['Epoch'] == args.epochs and rejection == 'catalog_parent'
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
