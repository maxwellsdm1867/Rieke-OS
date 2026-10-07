"""Private serial worker. Invoke through tools/benchmark_everyday.py."""
import argparse
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import statistics
import sys
import time
import traceback

parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--lane', choices=['tree', 'typed'], required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.source_root.resolve() / 'python'))
if not __debug__:
    raise RuntimeError('Oracles require Python without -O')
import h5py
attempts = []


def forbidden(*values, **kwargs):
    attempts.append(str(values[:1]))
    raise AssertionError('Metadata benchmark attempted H5 access')


def guard(original):
    def checked(path, *values, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)):
            name = os.fsdecode(path).lower()
            if name.endswith(('.h5', '.hdf5')):
                forbidden(path)
        return original(path, *values, **kwargs)
    return checked


h5py.File = forbidden
builtins.open = guard(builtins.open)
io.open = guard(io.open)
os.open = guard(os.open)
from fixture import N, SOURCE_SHA, detail, row, tree_fixture, typed_fixture, uid

result = {'status': 'running', 'lane': args.lane, 'epochs': N, 'operations': {},
          'guards': {}, 'h5_open_attempts': attempts}
started = time.perf_counter()


def report(event, **values):
    print(json.dumps({'event': event, **values}), flush=True)


def measure(name, fn, oracle, samples=3):
    times = []
    digests = []
    for sample in range(samples):
        start = time.perf_counter()
        answer = fn()
        elapsed = (time.perf_counter() - start) * 1000
        oracle(answer)
        times.append(elapsed)
        digests.append(hashlib.sha256(json.dumps(answer, sort_keys=True).encode()).hexdigest())
        report('sample', case=name, sample=sample, milliseconds=elapsed)
    result['operations'][name] = {'milliseconds': times, 'median_ms': statistics.median(times),
                                  'answer_sha256': digests, 'oracle_passed': True}
    return answer


def equal(actual, expected):
    assert actual == expected, f'Oracle mismatch: {str(actual)[:300]} != {str(expected)[:300]}'


def refuses(name, exception, fn):
    try:
        fn()
    except exception:
        result['guards'][name] = True
    else:
        raise AssertionError(f'{name}: invalid request accepted')


def tree():
    from disco.navigation.tree_pages import StaleTreePage
    start = time.perf_counter()
    service, pager = tree_fixture()
    result['setup_seconds'] = time.perf_counter() - start
    report('setup_complete', lane='tree', seconds=result['setup_seconds'])
    base = {'splits': 'cell', 'counts_only': True, 'limit': 60}

    def root_oracle(answer, offset=0):
        equal([answer['count'], answer['total_epochs'], answer['total']], [N, N, N // 100])
        equal([b['value'] for b in answer['branches']], [uid(N+i) for i in range(offset, offset+60)])
        equal([b['count'] for b in answer['branches']], [100] * 60)
        equal(answer['has_more'], offset+60 < N//100)

    first = measure('tree.first_root', lambda: pager.page(base), root_oracle, 1)
    measure('tree.repeated_root', lambda: pager.page(base), root_oracle)
    revision, path = first['revision'], first['branches'][0]['path']
    measure('tree.next_cells', lambda: pager.page(dict(base, offset=60, revision=revision)),
            lambda a: root_oracle(a, 60))
    measure('tree.deep_cells', lambda: pager.page(dict(base, offset=9000, revision=revision)),
            lambda a: root_oracle(a, 9000))

    def leaf_oracle(answer, start=0, offset=0):
        equal([answer['count'], answer['selection']['count'], answer['total']], [N, 100, 100])
        equal([r['epoch_uuid'] for r in answer['epochs']],
              [uid(i) for i in range(start+offset, start+min(100, offset+60))])
        equal(answer['has_more'], offset == 0)

    measure('tree.open_cell', lambda: pager.page(dict(base, path=path, revision=revision)), leaf_oracle)
    measure('tree.scroll_cell', lambda: pager.page(dict(base, path=path, revision=revision, offset=60)),
            lambda a: leaf_oracle(a, offset=60))
    anchor_id = N-25

    def anchor_oracle(answer):
        leaf_oracle(answer, N-100, 60)
        equal(answer['anchor']['epoch_uuid'], uid(anchor_id))
        equal(answer['anchor']['index'], 75)
        equal(answer['anchor']['offset'], 60)

    anchor = measure('tree.anchor', lambda: pager.page(dict(base, anchor_uuid=uid(anchor_id))), anchor_oracle)

    def column_oracle(answer):
        target, parents = answer
        anchor_oracle(target)
        equal(len(parents), 1)
        equal([b['value'] for b in parents[0]['branches']], [uid(N+i) for i in range(9960,10000)])

    measure('tree.anchor_columns', lambda: pager.column_pages(dict(base, anchor_uuid=uid(anchor_id))), column_oracle)
    measure('tree.return_root', lambda: pager.page(base), root_oracle)

    def split_oracle(answer):
        equal([answer['count'], answer['total'], answer['branches'][0]['count']], [N, 1, N])
        equal(answer['branches'][0]['value'], '2026-10-07')

    measure('tree.change_splits', lambda: pager.page(dict(base, splits='date,cell,block')), split_oracle)
    measure('tree.return_splits', lambda: pager.page(base), root_oracle)
    selection = {'splits': 'cell', 'path': path, 'revision': revision}
    measure('tree.select_cell', lambda: pager.selection(selection, 100),
            lambda a: equal([a['count'], a['epoch_uuids']], [100, [uid(i) for i in range(100)]]))
    refuses('selection_cap', ValueError, lambda: pager.selection(selection, 1001))
    refuses('selection_count', StaleTreePage, lambda: pager.selection(selection, 99))
    refuses('missing_revision', ValueError, lambda: pager.page(dict(base, path=path)))
    refuses('outside_anchor', KeyError, lambda: pager.page(dict(base, anchor_uuid=uid(8*N))))
    service._fingerprints[uid(0)] = 'c' * 64
    refuses('changed_fingerprint', StaleTreePage, lambda: pager.page(dict(base, path=path, revision=revision)))
    refuses('stale_selection', StaleTreePage, lambda: pager.selection(selection, 100))


def typed():
    start = time.perf_counter()
    reader = typed_fixture(report)
    result['setup_seconds'] = time.perf_counter() - start
    report('setup_complete', lane='typed', seconds=result['setup_seconds'])
    def ids():
        return (uid(i) for i in range(N))

    def page_oracle(answer, start=0, step=1, stop=N):
        numbers = list(range(start, min(stop, start+60*step), step))
        equal(answer['rows'], [row(i) for i in numbers])
        equal(answer['cursor'], numbers[-1]+1 if numbers and numbers[-1]+step < stop else None)

    cases = [
        ('typed.first', lambda: reader.page(limit=60), 0, 1, N),
        ('typed.deep', lambda: reader.page(cursor=N//2, limit=60), N//2, 1, N),
        ('typed.source', lambda: reader.page(scope={'sources': [SOURCE_SHA]}, limit=60), 0, 1, N),
        ('typed.membership', lambda: reader.page(scope={'epoch_ids': ids()}, limit=60), 0, 1, N),
        ('typed.protocol_first', lambda: reader.page(scope={'sources': [SOURCE_SHA], 'epoch_ids': ids()}, limit=60), 0, 1, N),
        ('typed.protocol_deep', lambda: reader.page(scope={'sources': [SOURCE_SHA], 'epoch_ids': ids()}, cursor=N//2, limit=60), N//2, 1, N),
        ('typed.cell', lambda: reader.page(scope={'cell': uid(N+5000)}, limit=60), 500000, 1, 500100),
        ('typed.cell_scroll', lambda: reader.page(scope={'cell': uid(N+5000)}, cursor=500060, limit=60), 500060, 1, 500100),
        ('typed.block', lambda: reader.page(scope={'block': uid(2*N+25000)}, limit=60), 500000, 1, 500020),
        ('typed.contains_first', lambda: reader.page({'field': 'parameters/unique', 'operator': 'contains', 'value': 'unique'}, limit=60), 0, 1, N),
        ('typed.contains_deep', lambda: reader.page({'field': 'parameters/unique', 'operator': 'contains', 'value': 'unique'}, cursor=N//2, limit=60), N//2, 1, N),
        ('typed.category', lambda: reader.page({'field': 'parameters/category', 'operator': 'eq', 'value': 0}, limit=60), 0, 10, N),
        ('typed.empty', lambda: reader.page({'field': 'parameters/category', 'operator': 'eq', 'value': 99}, limit=60), 0, 1, 0),
        ('typed.one', lambda: reader.page({'field': 'parameters/unique', 'operator': 'eq', 'value': 'unique-000000500000'}, limit=60), 500000, 1, 500001),
    ]
    for name, fn, begin, step, end in cases:
        measure(name, fn, lambda a, b=begin, s=step, e=end: page_oracle(a,b,s,e))
    measure('typed.detail', lambda: reader.detail(uid(500000)), lambda a: equal(a, detail(500000)))
    for name, scope, want in [('all', None, N), ('source', {'sources': [SOURCE_SHA]}, N), ('cell', {'cell': uid(N+5000)}, 100)]:
        measure('typed.count_'+name, lambda s=scope: reader.count(scope=s), lambda a, n=want: equal(a,n))
    for name, cursor, begin in [('first', None, 0), ('next', uid(N+59), 60), ('deep', uid(N+8999), 9000)]:
        measure('typed.cells_'+name, lambda c=cursor: reader.groups('cell', cursor=c, limit=60),
                lambda a, b=begin: equal(a, {'groups': [{'uuid': uid(N+i), 'count':100} for i in range(b,b+60)], 'cursor':uid(N+b+59)}))
    pred = {'field':'parameters/category','operator':'eq','value':0}
    def preview_oracle(a):
        page_oracle(a, step=10)
        equal(a['count'], N//10)
        equal(a['facets']['parameters/category'], {'values':[{'value':0,'type':'number','count':N//10}],
              'missing_count':0,'present_count':N//10,'values_truncated':False})
    measure('typed.filter_preview', lambda: reader.preview(pred, facet_fields=['parameters/category']), preview_oracle)
    refuses('missing_detail', KeyError, lambda: reader.detail(uid(8*N)))
    refuses('invalid_limit', ValueError, lambda: reader.page(limit=101))
    equal(reader.page(scope={'sources':['z'*64]}), {'rows':[], 'cursor':None})
    result['guards']['outside_source_empty'] = True
    reader.close()
    refuses('closed_reader', ValueError, lambda: reader.page())


try:
    {'tree': tree, 'typed': typed}[args.lane]()
    assert not attempts
    result['status'] = 'passed'
except BaseException:
    result['status'] = 'failed'
    result['error'] = traceback.format_exc()
    traceback.print_exc()
finally:
    result['elapsed_seconds'] = time.perf_counter()-started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result['peak_rss_bytes'] = rss if sys.platform == 'darwin' else rss*1024
    args.output.write_text(json.dumps(result, indent=2)+'\n')
if result['status'] != 'passed':
    sys.exit(1)
