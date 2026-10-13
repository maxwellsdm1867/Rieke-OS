#!/usr/bin/env python3
"""Fixed Workbench cohort versus unrelated project growth; owned fixtures only.

Use one harness/interpreter serially against both sources. Scope construction and
SQL/seal authority are fixture inputs, not native or HTTP performance evidence.
"""
import argparse
import copy
import cProfile
import hashlib
import inspect
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def run(source, epochs):
    sys.path[:0] = [str(source / 'python'), str(source / 'python/tests'),
                   str(ROOT / 'benchmarks/everyday'), str(ROOT / 'benchmarks/workflow'), str(ROOT / 'tools')]
    import h5py
    from fixture import row, uid
    from server import admitted_index
    from test_workspace_api import FixtureService
    from disco.navigation.tree_pages import TreePages
    from disco.workbench.workbench import ProtocolWorkbench
    from disco.workbench.recipes import checksum
    from workspace_service import WorkspaceService, _FrozenProtocolBinding
    from benchmark_everyday import source as source_identity, environment

    result = {'status': 'incomplete', 'epochs': epochs, 'members': 2000,
              'source_start': source_identity(source), 'environment': environment(),
              'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'operations': {}, 'limitations': [
                  'Production read modules; synthetic metadata/seal admission and prechecked Workbench context.',
                  'Direct-call latency excludes native authority, HTTP, browser and project setup.',
                  'Unrelated source-query membership is deliberately project-sized; pending cohort stays at 2000.']}
    with tempfile.TemporaryDirectory(prefix='disco-scoped-read-benchmark-') as folder, \
            patch.object(h5py, 'File', side_effect=AssertionError('Metadata read touched H5')):
        service = FixtureService(folder)
        service.rows = {uid(i): {**row(i), 'metadata_hash': 'b' * 64} for i in range(epochs)}
        service._fingerprints = dict.fromkeys(service.rows, 'b' * 64)
        service.cells = {value['cell_uuid']: dict(cell_uuid=value['cell_uuid'], label=value['cell_label'],
            cell_type=value['cell_type'], date=value['date']) for value in service.rows.values()}
        service.protocols[service.protocol_id]['result']['epochs'] = [
            dict(uuid=uid(i), metadata_hash='b' * 64) for i in range(2000)]
        other = uid(9_000_001)
        service.protocols[other] = copy.deepcopy(service.protocols[service.protocol_id])
        service.protocols[other]['result']['epochs'] = [dict(uuid=key, metadata_hash='b' * 64) for key in service.rows]
        service.disk_index = admitted_index(service)
        service.binding_provider = None
        service.binding_header_provider = None
        recipe = dict(revision_uuid=uid(9_000_002), name='Fixed pending cohort',
            epochs=service.protocols[service.protocol_id]['result']['epochs'], source_revisions=['a' * 64],
            predicate={'all': []}, splits='cell', tree_view={'fields': ['cell']})
        context = dict(protocol_uuid=service.protocol_id, candidate=recipe,
            candidate_scope_revision='owned-fixed-pending-v1', unavailable=set(),
            project_uuid=service.project['project_uuid'], candidate_revision_uuid=recipe['revision_uuid'],
            candidate_recipe_sha256=checksum(recipe), baseline_revision_uuid=uid(9_000_003),
            baseline_recipe_sha256='c' * 64, main_revision_uuid=uid(9_000_003), main_recipe_sha256='c' * 64,
            expected_binding_version=1, expected_query_revision='owned-query-proof',
            pending={uid(i): 'b' * 64 for i in range(2000)})
        manager = ProtocolWorkbench(service, None, None, None, None)
        body = dict(protocol_uuid=service.protocol_id, splits='cell', counts_only=True, limit=60)

        def tree(request=body):
            return TreePages(manager.frozen_service(context)).page(request)

        def check_root(answer):
            assert answer['count'] == answer['total_epochs'] == 2000
            assert [branch['value'] for branch in answer['branches']] == [uid(1_000_000 + i) for i in range(20)]
            assert [branch['count'] for branch in answer['branches']] == [100] * 20

        def measure(name, function, oracle):
            samples = []
            for _ in range(7):
                start = time.perf_counter()
                answer = function()
                samples.append((time.perf_counter() - start) * 1000)
                oracle(answer)
            result['operations'][name] = dict(milliseconds=samples, median_ms=statistics.median(samples), correct=True)
            return answer

        first = tree()
        check_root(first)
        measure('workbench.warm_tree', tree, check_root)
        branch = {**body, 'path': first['branches'][0]['path'], 'revision': first['revision']}
        def check_leaf(answer):
            assert answer['kind'] == 'epochs' and answer['total'] == 100
            assert [value['epoch_uuid'] for value in answer['epochs']] == [uid(i) for i in range(60)]
        measure('workbench.cell_page', lambda: tree(branch), check_leaf)
        def page():
            return manager.frozen_service(context).epoch_page(service.protocol_id, limit=60)
        def check_page(answer):
            assert answer['total'] == 2000
            assert [value['epoch_uuid'] for value in answer['epochs']] == [uid(i) for i in range(60)]
        measure('workbench.epoch_page', page, check_page)
        # The explicit local summary projection is the candidate's new contract.
        # Legacy source has no option and computes the unused global coverage.
        summary_options = {'cross_protocols': False} if 'cross_protocols' in inspect.signature(WorkspaceService.protocol).parameters else {}
        def summary():
            value = manager.frozen_service(context).protocol(service.protocol_id, **summary_options)
            for cell in value['cells']:
                cell.pop('protocol_uuids', None)
            return value
        def check_summary(answer):
            assert answer['counts']['epochs'] == answer['total_counts']['epochs'] == 2000
            assert answer['counts']['cells'] == 20
            assert [cell['cell_uuid'] for cell in answer['cells']] == sorted(
                [uid(1_000_000 + i) for i in range(20)], key=lambda key: service.cells[key]['label'])
            assert all(cell['epochs'] == 100 for cell in answer['cells'])
        measure('workbench.local_summary', summary, check_summary)
        # Profile only a separate pass; instrumentation does not enter medians.
        profile = cProfile.Profile()
        with profile:
            tree()
        codes = {'scope_builds': TreePages._build_scope.__code__, 'recipe_copies': _FrozenProtocolBinding.__call__.__code__}
        result['warm_work'] = {name: sum(entry.callcount for entry in profile.getstats() if entry.code is code)
                               for name, code in codes.items()}
        result['h5_open_attempts'] = 0
        result['source_end'] = source_identity(source)
        assert result['source_start'] == result['source_end']
        result['status'] = 'passed'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--epochs', type=int, choices=(20000, 200000, 1000000), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    result = run(args.source_root.resolve(), args.epochs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'epochs': args.epochs, 'work': result['warm_work'],
                      'medians': {key: value['median_ms'] for key, value in result['operations'].items()}}))
