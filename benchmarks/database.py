"""Actual SQLite operation timings on the existing sealed independent small truth.
No real catalog, scientific files, services or network are opened.
"""
from pathlib import Path
import json
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'python'), str(ROOT / 'tools/metadata_qualification')]
from truth import Truth, canonical, digest
from core_adapter import CoreAdapter
from disco.metadata.typed_index import TypedMetadataIndex


def run(samples):
    truth = Truth()
    fixture = truth.fixture()
    predicates = [None, {'any': []}, {'field': 'parameters/mixed', 'operator': 'eq', 'value': True},
                  {'field': 'parameters/optional', 'operator': 'missing'},
                  {'field': 'parameters/optional', 'operator': 'is_null'},
                  {'field': 'parameters/optional', 'operator': 'gte', 'value': 2},
                  {'field': 'parameters/array', 'operator': 'contains', 'value': 1},
                  {'any': [{'field': 'parameters/optional', 'operator': 'is_null'}, {'field': 'parameters/mixed', 'operator': 'eq', 'value': True}]},
                  {'not': {'field': 'parameters/optional', 'operator': 'is_null'}},
                  {'all': [{'field': 'parameters/mixed', 'operator': 'exists'}]}]
    scopes = [None, {'cell': truth.values[truth.ids[0]]['cell']},
              {'block': truth.values[truth.ids[0]]['block']},
              {'sources': ['source-A'], 'epoch_ids': [truth.ids[0], truth.ids[2], truth.ids[0], 'foreign']}]
    page_requests = [dict(scope=scope, limit=3, cursor=cursor) for scope in scopes for cursor in (None, 3)]
    cases = {
        'db.typed.detail': (lambda a: a.detail(truth.ids[0]), fixture['details'][truth.ids[0]]),
        'db.typed.page.scope': (lambda a: [a.preview(**request) for request in page_requests],
                                [truth.preview(**request) for request in page_requests]),
        'db.typed.filter.matrix': (lambda a: [a.membership(p) for p in predicates],
                                   [truth.membership(p) for p in predicates]),
        'db.typed.membership.exact': (lambda a: [a.membership(scope=s) for s in scopes],
                                     [truth.membership(scope=s) for s in scopes]),
        'db.typed.facets.two': (lambda a: a.preview(facet_fields=['parameters/mixed', 'parameters/optional'], limit=3),
                                truth.preview(facet_fields=['parameters/mixed', 'parameters/optional'], limit=3)),
        'db.typed.facets.all_eligible': (lambda a: a.preview(facet_fields=truth.fields, limit=3),
                                        truth.preview(facet_fields=truth.fields, limit=3)),
    }
    rows = []
    with tempfile.TemporaryDirectory(prefix='rieke-core-benchmark-') as temporary:
        path = Path(temporary) / 'typed.sqlite'
        start = time.perf_counter()
        adapter = CoreAdapter(path, fixture)
        setup_ms = (time.perf_counter() - start) * 1000
        try:
            # Complete currently eligible field registry must survive acceleration.
            if set(adapter.fields) != set(truth.fields):
                raise AssertionError('Eligible field registry changed')
            # Independent expected data, generated outside all measured regions.
            for operation, expected in cases.values():
                if canonical(operation(adapter)) != canonical(expected):
                    raise AssertionError('Preflight exact source-truth mismatch')
            for case_id, (operation, expected) in cases.items():
                measurements = {'cold_reader_ms': [], 'warm_reader_ms': []}
                for _ in range(samples):
                    adapter.reader.close()
                    adapter.reader = TypedMetadataIndex(path, expected_generation='qualification-v1', expected_project_uuid='isolated')
                    for metric in measurements:
                        started = time.perf_counter_ns()
                        actual = operation(adapter)
                        elapsed = (time.perf_counter_ns() - started) / 1e6
                        if canonical(actual) != canonical(expected):
                            raise AssertionError(f'{case_id}: exact source-truth mismatch')
                        measurements[metric].append(elapsed)
                rows.append(dict(id=case_id, status='passed', metrics=measurements,
                                 oracle_sha256=digest(expected), correctness='exact canonical source-truth equality'))
        finally:
            adapter.close()
    return dict(cases=rows, setup_ms=setup_ms, fixture_sha256=truth.sha256,
                records=len(truth.ids), eligible_fields=len(truth.fields),
                universal_field_access=False,
                scope='real SQLite derived-index reads; excludes SQL authority, HTTP, H5 and browser',
                fixture_cleaned=True)


if __name__ == '__main__':
    result = run(int(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
