#!/usr/bin/env python3
"""Serial baseline/candidate UI audit over freshly owned 1,000-epoch fixtures."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import benchmark_workflow as owned


def run_stage(source, output, label, args):
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'format': 'disco-ui-retention-audit-stage-v1', 'label': label,
               'source_root': str(source), 'source_start': owned.query_bench.source(source),
               'status': 'running', 'cleanup': {}}
    server = browser = None
    server_ids, browser_ids, streams = {}, {}, []
    try:
        server, stream, deadline = owned.execute_owned(
            [sys.executable, '-B', str(ROOT / 'benchmarks/retention/server.py'),
             '--source-root', str(source), '--output', str(output / 'server'),
             '--epochs', '1000', '--protocol-epochs', '1000'], output / 'server.log', 90, 2 * 1024**3, server_ids)
        streams.append(stream)
        metadata = output / 'server/server.json'
        while not metadata.exists():
            if owned.poll_owned(server, deadline, 2 * 1024**3, server_ids) is not None:
                raise RuntimeError('Owned fixture exited before readiness')
            time.sleep(.1)
        receipt['fixture'] = json.loads(metadata.read_text())
        command = ['node', str(ROOT / 'benchmarks/ui-retention-audit/browser.mjs'),
                   '--source-root', str(source), '--server-json', str(metadata),
                   '--output', str(output / 'browser'), '--label', label,
                   '--expect-retained', str(label == 'candidate').lower()]
        if args.browser_executable:
            command += ['--browser-executable', str(args.browser_executable)]
        browser, stream, deadline = owned.execute_owned(command, output / 'browser.log', 900, 4 * 1024**3, browser_ids)
        streams.append(stream)
        while True:
            if server.poll() is not None:
                raise RuntimeError('Owned fixture exited during UI audit')
            code = owned.poll_owned(browser, deadline, 4 * 1024**3, browser_ids)
            if code is not None:
                receipt['browser_exit_code'] = code
                break
            time.sleep(.1)
        receipt['browser'] = json.loads((output / 'browser/receipt.json').read_text())
        receipt['status'] = receipt['browser']['status']
        receipt['source_end'] = owned.query_bench.source(source)
        if receipt['source_end'] != receipt['source_start']:
            raise RuntimeError('Source changed during UI audit')
    except BaseException as error:
        receipt.update(status='failed', error=repr(error))
    finally:
        receipt['cleanup']['browser_processes_closed'] = owned.stop_owned(browser, browser_ids)
        receipt['cleanup']['server_processes_closed'] = owned.stop_owned(server, server_ids)
        for stream in streams:
            stream.close()
        cleanup = output / 'server/cleanup.json'
        if cleanup.exists():
            receipt['cleanup']['backend'] = json.loads(cleanup.read_text())
        owned.query_bench.write(output / 'receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', type=Path, required=True)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--baseline-ref', default='ceaf776')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser-executable', type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    roots = {name: getattr(args, name + '_root').resolve() for name in ('baseline', 'candidate')}
    baseline_head = subprocess.check_output(['git', '-C', str(roots['baseline']), 'rev-parse', 'HEAD'], text=True).strip()
    expected = subprocess.check_output(['git', '-C', str(roots['baseline']), 'rev-parse', args.baseline_ref], text=True).strip()
    if baseline_head != expected:
        raise RuntimeError(f'Baseline must be exactly {expected}, got {baseline_head}')
    harness = {str(file.relative_to(ROOT)): owned.query_bench.sha(file.read_bytes())
               for file in sorted((ROOT / 'benchmarks/ui-retention-audit').glob('*')) if file.is_file()}
    for name in ['benchmarks/retention/server.py', 'benchmarks/workflow/server.py', 'benchmarks/workflow/backend_timing.py', 'tools/benchmark_workflow.py', 'tools/benchmark_everyday.py']:
        harness[name] = owned.query_bench.sha((ROOT / name).read_bytes())
    receipt = {'format': 'disco-ui-retention-comparison-v1', 'harness': harness, 'stages': {},
               'environment': owned.query_bench.environment(), 'execution': 'serial, isolated owned fixtures'}
    for label, source in roots.items():
        receipt['stages'][label] = run_stage(source, args.output / label, label, args)
    command = ['node', str(ROOT / 'benchmarks/ui-retention-audit/compare.mjs'),
               '--baseline', str(args.output / 'baseline/browser/receipt.json'),
               '--candidate', str(args.output / 'candidate/browser/receipt.json'),
               '--source-root', str(roots['candidate']), '--output', str(args.output / 'comparison')]
    if args.browser_executable:
        command += ['--browser-executable', str(args.browser_executable)]
    receipt['comparison_exit_code'] = subprocess.run(command, check=False).returncode
    receipt['harness_end'] = {name: owned.query_bench.sha((ROOT / name).read_bytes()) for name in harness}
    receipt['status'] = 'complete' if receipt['harness_end'] == harness and receipt['comparison_exit_code'] == 0 else 'failed'
    receipt['stage_failures'] = {label: stage.get('error', stage['status']) for label, stage in receipt['stages'].items() if stage['status'] != 'passed'}
    receipt['audit_failures'] = {key: value.get('browser', {}).get('failures', []) for key, value in receipt['stages'].items()}
    owned.query_bench.write(args.output / 'receipt.json', receipt)
    print(args.output / 'receipt.json')
    if receipt['status'] != 'complete' or receipt['stage_failures'] or any(receipt['audit_failures'].values()):
        sys.exit(1)

if __name__ == '__main__':
    main()
