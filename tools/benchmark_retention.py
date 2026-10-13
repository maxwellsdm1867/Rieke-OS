#!/usr/bin/env python3
"""Owned full-App retention diagnostic; separate from the fixed workflow suite.

Uses the existing disposable Flask workflow fixture and lifecycle guards. Never
accepts a backend URL, installed application, or scientific project directory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import benchmark_workflow as workflow

ROOT = Path(__file__).resolve().parents[1]


def run(args):
    source, output = args.source_root.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = {
        'format': 'disco-full-app-retention-diagnostic-v1', 'status': 'running',
        'source_root': str(source), 'source_start': workflow.query_bench.source(source),
        'environment': workflow.query_bench.environment(), 'samples': args.samples,
        'fixture_epochs': 1000, 'expect_retained': args.expect_retained,
        'limitations': ['Owned Flask fixture uses SQL/index/source-admission doubles.',
                       'Full product App in development browser; no native compositor claim.',
                       'Shell project inventory is an explicit owned-fixture response.',
                       'Draft bridge uses real DraftStore but no Electron IPC.'],
        'harness': {}, 'cleanup': {},
    }
    for name in ['tools/benchmark_retention.py', 'tools/benchmark_workflow.py',
                 'tools/benchmark_everyday.py', 'benchmarks/retention/browser.mjs', 'benchmarks/retention/server.py',
                 'benchmarks/workflow/server.py', 'benchmarks/workflow/backend_timing.py', 'benchmarks/navigation-probe.mjs']:
        receipt['harness'][name] = workflow.query_bench.sha((ROOT / name).read_bytes())
    server = browser = None
    server_ids, browser_ids, streams = {}, {}, []
    started = time.monotonic()
    try:
        server, stream, deadline = workflow.execute_owned(
            [sys.executable, '-B', str(ROOT / 'benchmarks/retention/server.py'),
             '--source-root', str(source), '--output', str(output / 'server'),
             '--epochs', '1000', '--protocol-epochs', '1000'],
            output / 'server.log', 60, 2 * 1024**3, server_ids)
        streams.append(stream)
        meta = output / 'server/server.json'
        while not meta.is_file():
            code = workflow.poll_owned(server, deadline, 2 * 1024**3, server_ids)
            if code is not None:
                raise RuntimeError(f'Owned fixture exited before readiness: {code}')
            time.sleep(.1)
        receipt['fixture'] = json.loads(meta.read_text())
        command = ['node', str(ROOT / 'benchmarks/retention/browser.mjs'),
                   '--source-root', str(source), '--server-json', str(meta),
                   '--output', str(output / 'browser'), '--samples', str(args.samples),
                   '--expect-retained', str(args.expect_retained).lower()]
        if args.browser_executable:
            command += ['--browser-executable', str(args.browser_executable)]
        browser, stream, deadline = workflow.execute_owned(
            command, output / 'browser.log', 240, 3 * 1024**3, browser_ids)
        streams.append(stream)
        while True:
            if server.poll() is not None:
                raise RuntimeError('Owned fixture exited during browser checks')
            code = workflow.poll_owned(browser, deadline, 3 * 1024**3, browser_ids)
            if code is not None:
                if code:
                    raise RuntimeError(f'Browser retention check failed: {code}')
                break
            time.sleep(.1)
        receipt['browser'] = json.loads((output / 'browser/receipt.json').read_text())
        if receipt['browser']['status'] != 'passed':
            raise RuntimeError('Browser retention receipt did not pass')
        receipt['source_end'] = workflow.query_bench.source(source)
        if receipt['source_start'] != receipt['source_end']:
            raise RuntimeError('Source changed during measurement')
        receipt['harness_end'] = {name: workflow.query_bench.sha((ROOT / name).read_bytes())
                                  for name in receipt['harness']}
        if receipt['harness_end'] != receipt['harness']:
            raise RuntimeError('Harness changed during measurement')
        receipt['status'] = 'diagnostic'
    except BaseException as error:
        receipt.update(status='failed', error=repr(error))
        raise
    finally:
        receipt['cleanup']['browser_processes_closed'] = workflow.stop_owned(browser, browser_ids)
        receipt['cleanup']['server_processes_closed'] = workflow.stop_owned(server, server_ids)
        for stream in streams:
            stream.close()
        cleanup = output / 'server/cleanup.json'
        if cleanup.exists():
            receipt['cleanup']['backend'] = json.loads(cleanup.read_text())
        receipt['elapsed_seconds'] = time.monotonic() - started
        workflow.query_bench.write(output / 'receipt.json', receipt)
    print(output / 'receipt.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, choices=range(1, 6), default=3)
    parser.add_argument('--expect-retained', action='store_true')
    parser.add_argument('--browser-executable', type=Path)
    run(parser.parse_args())
