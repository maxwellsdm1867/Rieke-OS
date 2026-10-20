#!/usr/bin/env python3
"""Fixed 2,000-member tree versus growing unrelated metadata; owned fixtures only.

Production service/pager and immutable binding owner; synthetic index admission
and SQL tables. Direct-call latency is not HTTP, browser or native qualification.
Invoke the same file/interpreter serially against baseline and candidate sources.
"""
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


def run(source, epochs):
    sys.path[:0] = [str(source/'python'), str(source/'python/tests'),
                   str(ROOT/'benchmarks/everyday'), str(ROOT/'benchmarks/workflow')]
    import h5py
    from fixture import row, uid
    from server import admitted_index
    from test_workspace_api import FixtureService
    from test_workspace_curation import Table
    from disco.decisions.explorer import ExplorerHistory
    from disco.navigation.tree_pages import TreePages, StaleTreePage
    from benchmark_everyday import source as identity, environment

    result = {'status':'incomplete', 'epochs':epochs, 'members':2000,
              'source_start':identity(source), 'environment':environment(),
              'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'operations':{}, 'limitations':[
                  'Synthetic metadata/index admission and SQL tables; real service/pager and binding owner.',
                  'Direct calls; HTTP requests, browser rendering, native SQL and package behavior unmeasured.',
                  'Fixture setup excluded. Full project startup/import intentionally remain project-wide.']}
    with tempfile.TemporaryDirectory(prefix='disco-member-benchmark-') as folder, \
         patch.object(h5py, 'File', side_effect=AssertionError('Metadata read touched H5')):
        service = FixtureService(folder)
        service.rows = {uid(i): {**row(i), 'metadata_hash':'b'*64} for i in range(epochs)}
        service._fingerprints = dict.fromkeys(service.rows, 'b'*64)
        service.ids = [uid(i) for i in range(2000)]
        # Original acquisition query is deliberately project-sized. The frozen
        # binding replaces it with the identical small cohort at every scale.
        service.protocols[service.protocol_id]['result']['epochs'] = [
            {'uuid':key, 'metadata_hash':'b'*64} for key in service.rows]
        service.disk_index = admitted_index(service)
        bindings, revisions = Table(('project_uuid','protocol_uuid')), Table(('project_uuid','revision_uuid'))
        history = ExplorerHistory(object(), service.project['project_uuid'], event_table=Table(('event_uuid',)),
                                  revision_table=revisions, binding_table=bindings)
        recipe = {'epochs':[{'uuid':key,'metadata_hash':'b'*64} for key in service.ids],
                  'source_revisions':['a'*64], 'predicate':{'all':[]},
                  'tree_view':{'fields':['cell']}, 'splits':'cell', 'name':'Fixed cohort'}
        history._recipe_cache['fixed-members'] = recipe
        bindings.insert1({'project_uuid':service.project['project_uuid'],
                          'protocol_uuid':service.protocol_id, 'version':1, 'revision_uuid':'fixed-members'})
        service.set_binding_provider(history.protocol_binding, header_provider=history.protocol_binding_header)
        # Trees that publish deep-frozen read models (publication serial) get the
        # same publication production refresh performs; older trees stay plain.
        import workspace_service as service_module
        freeze = getattr(service_module, 'publish_frozen', None)
        if freeze is not None:
            service.rows = freeze(service.rows, rows=True)
            service.cells, service.protocols = freeze(service.cells), freeze(service.protocols)
            service._fingerprints = freeze(service._fingerprints)
        result['frozen_publication'] = freeze is not None

        def edit_fingerprint(key, value):
            # Frozen maps change only by republication (as refresh does).
            if freeze is not None:
                service._fingerprints = freeze({**service._fingerprints, key: value})
            else:
                service._fingerprints[key] = value
        pager = TreePages(service)
        body = {'protocol_uuid':service.protocol_id, 'splits':'cell', 'counts_only':True, 'limit':60}

        def check_root(answer):
            assert answer['count'] == answer['total_epochs'] == 2000
            assert [branch['value'] for branch in answer['branches']] == [uid(1_000_000+i) for i in range(20)]
            assert [branch['count'] for branch in answer['branches']] == [100]*20

        def measure(name, function, oracle):
            samples = []
            for _ in range(7):
                start = time.perf_counter()
                answer = function()
                samples.append((time.perf_counter()-start)*1000)
                oracle(answer)
            result['operations'][name] = {'milliseconds':samples, 'median_ms':statistics.median(samples), 'correct':True}
            return answer

        def cold():
            service._tree_page_scope_cache = None
            service._epoch_page_cache = None
            return pager.page(body)

        root = measure('tree.cold_root', cold, check_root)
        measure('tree.warm_root', lambda:pager.page(body), check_root)
        branch = {**body, 'path':root['branches'][0]['path'], 'revision':root['revision']}
        def check_leaf(answer, start, stop):
            assert answer['kind'] == 'epochs' and answer['total'] == 100
            assert [item['epoch_uuid'] for item in answer['epochs']] == [uid(i) for i in range(start,stop)]
        measure('tree.expand_cell', lambda:pager.page(branch), lambda answer:check_leaf(answer,0,60))
        measure('tree.next_leaf', lambda:pager.page({**branch,'offset':60}), lambda answer:check_leaf(answer,60,100))
        measure('tree.anchor', lambda:pager.page({**body,'anchor_uuid':uid(1999)}),
                lambda answer:check_leaf(answer,1960,2000))
        metadata = {**body, 'splits':'parameters/example'}
        def check_metadata(answer):
            assert answer['count'] == 2000
            assert [branch['value'] for branch in answer['branches']] == list(range(10))
            assert [branch['count'] for branch in answer['branches']] == [200]*10
        pager.page(metadata)
        measure('tree.warm_metadata_root', lambda:pager.page(metadata), check_metadata)

        # Separate instrumented pass: no instrumentation enters latency samples.
        selection = {**body, 'path':root['branches'][0]['path'], 'revision':root['revision']}
        selection.pop('counts_only'); selection.pop('limit')
        measure('tree.select_branch', lambda:pager.selection(selection, 100), lambda answer:None)
        with patch.object(pager, '_build_scope', wraps=pager._build_scope) as builds:
            pager.page(branch); pager.page({**branch,'offset':60}); pager.selection(selection, 100)
        result['warm_branch_select_scope_builds'] = builds.call_count
        frozen_visits = {'count':0}
        if freeze is not None:
            frozen_type = type(service._fingerprints)
            original = {name:getattr(frozen_type, name) for name in ('__getitem__','get','__eq__','__ne__')}
            def counted(name):
                def call(self, *args):
                    if self is service._fingerprints or any(arg is service._fingerprints for arg in args):
                        frozen_visits['count'] += len(self) if name in ('__eq__','__ne__') else 1
                    return original[name](self, *args)
                return call
            pager.page(body)
            with patch.multiple(frozen_type, **{name:counted(name) for name in original}), \
                 patch.object(pager, '_build_scope', wraps=pager._build_scope) as builds:
                check_root(pager.page(body))
            result['frozen_warm_work'] = {'fingerprint_visits':frozen_visits['count'], 'scope_builds':builds.call_count}
        class Fingerprints(dict):
            visited = 0
            def __getitem__(self, key):
                self.visited += 1
                return super().__getitem__(key)
            def get(self, key, default=None):
                self.visited += 1
                return super().get(key,default)
            def __ne__(self, other):
                self.visited += len(self)
                return super().__ne__(other)
        service._fingerprints = Fingerprints(service._fingerprints)
        pager.page(body)
        service._fingerprints.visited = 0
        bindings.read_log.clear()
        with patch.object(pager, '_build_scope', wraps=pager._build_scope) as builds:
            check_root(pager.page(body))
        result['warm_work'] = {'fingerprint_visits':service._fingerprints.visited,
                              'binding_reads':len(bindings.read_log), 'scope_builds':builds.call_count,
                              'http_requests':0}
        # Count cache-owned estimates consistently; independent of process RSS.
        cache = service._tree_page_scope_cache
        result['warm_work']['retained_scope_bytes'] = sum(entry[2] for entry in cache[1].values())
        result['warm_work']['project_fingerprint_snapshot_bytes'] = sys.getsizeof(cache[2]) if cache[2] is not None else 0
        if freeze is not None:
            service._fingerprints = freeze(dict(service._fingerprints))
        edit_fingerprint(uid(epochs-1), 'c'*64)
        with patch.object(pager, '_build_scope', wraps=pager._build_scope) as builds:
            check_root(pager.page(body))
        result['unrelated_edit_scope_builds'] = builds.call_count
        edit_fingerprint(uid(0), 'd'*64)
        try:
            pager.page({**body, 'revision':root['revision']})
        except StaleTreePage:
            result['member_edit_rejected_stale_revision'] = True
        else:
            raise AssertionError('Member edit left the old tree current')
        result['h5_open_attempts'] = 0
        result['source_end'] = identity(source)
        assert result['source_start'] == result['source_end']
        result['status'] = 'passed'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--epochs', type=int, choices=(20000,200000,1000000), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    result = run(args.source_root.resolve(), args.epochs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'epochs':args.epochs, 'status':result['status'], 'warm_work':result['warm_work'],
                      'medians':{key:value['median_ms'] for key,value in result['operations'].items()}}))
