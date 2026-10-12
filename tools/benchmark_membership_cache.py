#!/usr/bin/env python3
"""Real sealed SQLite membership reuse; owned 20k fixture, separate reader per query."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def run():
    sys.path[:0] = [str(ROOT / 'python'), str(ROOT / 'tools')]
    from benchmark_everyday import source, environment
    from disco.metadata.tests.test_workspace_disk_index import fixture
    from disco.metadata.disk_index import DiskMetadataIndex
    from disco.metadata.typed_index import TypedMetadataIndex, build
    from disco.metadata.typed_lifecycle import MembershipCache
    import h5py
    receipt = {'status': 'incomplete', 'source_start': source(ROOT), 'environment': environment(),
               'epochs': 20000, 'operations': {}, 'cold_build_ms': {}, 'warm_recipe_reads': 0,
               'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'limitations': ['20k synthetic epochs in real sealed SQLite files; not million/native/UI qualification.',
                              'One owner generation; session restart and index building are excluded from query timing.']}
    with tempfile.TemporaryDirectory() as temp, patch.object(h5py, 'File', side_effect=AssertionError('H5 read')):
        root = Path(temp)
        rows, details, sources = fixture(20000)
        native = DiskMetadataIndex.build(root/'native.sqlite', rows, details, sources, 'cache-benchmark', 'owned')
        try:
            build(native.path, root/'typed.sqlite', min_free_gib=0)
            with TypedMetadataIndex(root/'typed.sqlite') as owner:
                cache = MembershipCache(owner, native)
                for size in (2000, 20000):
                    ids = [row['epoch_uuid'] for row in rows[:size]]
                    authority = {'revision': str(size)}
                    start = time.perf_counter()
                    handle = cache.get(authority, ['source'], lambda: iter(ids))
                    receipt['cold_build_ms'][str(size)] = (time.perf_counter()-start)*1000
                    def forbidden():
                        receipt['warm_recipe_reads'] += 1
                        raise AssertionError('Warm cache hydrated membership')
                    for mode in ('rebuild', 'reuse'):
                        samples = []
                        for _ in range(7):
                            start = time.perf_counter()
                            scope = cache.get(authority, ['source'], forbidden) if mode == 'reuse' else iter(ids)
                            with TypedMetadataIndex.open_verified(owner) as reader:
                                result = reader.summaries(scope={'epoch_ids': scope, 'sources': ['source']},
                                    facet_fields=['parameters/frequencyCutoff'])
                            samples.append((time.perf_counter()-start)*1000)
                            assert result['count'] == size
                            assert result['facets']['parameters/frequencyCutoff'] == {
                                'values': [{'value': 100, 'type': 'number', 'count': size//2},
                                           {'value': 200, 'type': 'number', 'count': size//2}],
                                'present_count': size, 'missing_count': 0, 'values_truncated': False}
                        receipt['operations'][f'{mode}_{size}'] = {'median_ms': statistics.median(samples),
                                                                  'milliseconds': samples, 'correct': True}
                    assert handle.path.exists()
        finally:
            native.close()
    receipt['source_end'] = source(ROOT)
    assert receipt['source_start'] == receipt['source_end']
    receipt.update(status='passed', h5_open_attempts=0)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('Output exists')
    receipt = run()
    args.output.write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({'status': receipt['status'], 'cold_build_ms': receipt['cold_build_ms'],
        'medians': {k: v['median_ms'] for k, v in receipt['operations'].items()}}))
