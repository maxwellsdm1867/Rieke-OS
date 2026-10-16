#!/usr/bin/env python3
"""Serial prepared-display correctness/latency smoke with owned SQL doubles.

Uses current harness against --source-root; this is not a native package test.
"""
import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import psutil
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'benchmarks/prepared_geometry'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_identity(source):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
    return {'commit': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'),
            'dirty': git('status', '--porcelain', '--untracked-files=normal'),
            'files': {name: digest(source / name) for name in git('ls-files').splitlines()
                      if (source / name).is_file() and not (source / name).is_symlink()}}


def dependency_fingerprints(source):
    if __package__:
        from tools.benchmark_workflow import dependency_identity
    else:
        from benchmark_workflow import dependency_identity
    locks = ('workspace-app/package-lock.json', 'desktop/package-lock.json')
    # Match the existing workflow policy: only the application's version may
    # differ; every locked dependency and the Python requirements remain exact.
    return {name: hashlib.sha256(dependency_identity(source / name).encode()).hexdigest()
            for name in locks} | {'benchmarks/requirements-py311.txt': digest(source / 'benchmarks/requirements-py311.txt')}


def compile_helper(source, output):
    compiler = shutil.which('cc')
    if not compiler or platform.system() not in ('Darwin', 'Linux'):
        raise RuntimeError('Smoke requires cc and macOS or Linux; no portable fallback')
    native = output / 'runtime/native'
    native.mkdir(parents=True)
    target = native / 'libdisco_trace_inflate.dylib'
    flags = ['-O3', '-fno-fast-math', '-ffp-contract=off', '-fPIC',
             '-dynamiclib' if platform.system() == 'Darwin' else '-shared']
    command = [compiler, *flags, str(source / 'desktop/native/trace_inflate.c'), '-lz', '-lm', '-pthread', '-o', str(target)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (output / 'native-build.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Native smoke helper compilation failed')
    library = ctypes.CDLL(str(target))
    library.disco_trace_inflate_abi.restype = ctypes.c_uint
    if library.disco_trace_inflate_abi() != 4:
        raise RuntimeError('Native smoke helper ABI must be 4')
    return {'command': command, 'sha256': digest(target), 'source_sha256': digest(source / 'desktop/native/trace_inflate.c'),
            'abi': 4, 'scope': 'host CI helper; desktop macOS deployment qualification unchanged'}


def validate(receipt, *, clean=False):
    for key in ('source_start', 'source_end'):
        identity = receipt.get(key)
        if (not isinstance(identity, dict) or
                any(not isinstance(identity.get(field), str) or not re.fullmatch(r'[0-9a-f]{40}', identity[field])
                    for field in ('commit', 'tree')) or not isinstance(identity.get('dirty'), str)):
            raise ValueError('Missing or malformed source identity')
        files = identity.get('files')
        if (not isinstance(files, dict) or not files or
                any(not isinstance(name, str) or not name or name == '.' or Path(name).is_absolute() or
                    '..' in Path(name).parts or not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha)
                    for name, sha in files.items())):
            raise ValueError('Missing or malformed source file hashes')
    if receipt.get('status') != 'passed' or receipt.get('source_start') != receipt.get('source_end'):
        raise ValueError('Failed or changed-source geometry receipt')
    if clean and receipt['source_start']['dirty']:
        raise ValueError('Dirty geometry source cannot qualify comparison')
    if __package__:
        from tools.benchmark_workflow import CLICK_PROTOCOL, validate_click_protocol
    else:
        from benchmark_workflow import CLICK_PROTOCOL, validate_click_protocol
    outer = receipt.get('environment')
    browser = outer.get('browser') if isinstance(outer, dict) else None
    if not isinstance(browser, dict) or browser.get('click_dispatch_protocol') != CLICK_PROTOCOL:
        raise ValueError('Missing or incompatible geometry click protocol')
    samples = receipt.get('samples', [])
    if len(samples) != 3:
        raise ValueError('Exactly three ordinary samples required')
    for index, row in enumerate(samples):
        validate_click_protocol(row)
        if not all(row.get('exact', {}).get(key) is True for key in ('all_emitted_point_bytes_match', 'all_source_indices_match', 'whole_statistics_exact', 'all_canvas_coordinates_exact', 'prepared_display_context_exact')) or not row.get('cursor', {}).get('all_tile_bytes_exact'):
            raise ValueError('Missing independent geometry/raw cursor correctness')
        for key in ('first_visible_ms', 'first_raf_ms', 'complete_ms'):
            value = row.get('trace', {}).get(key)
            if type(value) not in (int, float) or not 0 < value < 180000:
                raise ValueError('Invalid trace observation')
        if not row['trace']['first_visible_ms'] <= row['trace']['first_raf_ms'] <= row['trace']['complete_ms']:
            raise ValueError('Trace observation order invalid')
        if row.get('authority', {}).get('foreground_extraction') != {
                'requested': index + 1, 'entry_calls': index + 1, 'default_entry_calls': 0}:
            raise ValueError('Missing actual foreground extraction evidence')
    if receipt.get('cleanup') != {'server_closed': True, 'fixture_closed': True}:
        raise ValueError('Owned fixture cleanup incomplete')


def compare(before, after):
    validate(before, clean=True); validate(after, clean=True)
    for key in ('harness', 'environment', 'fixture', 'dependencies', 'payload_sha256'):
        if before.get(key) is None or before[key] != after.get(key):
            raise ValueError('Incomparable geometry ' + key)
    validate_pair(before, after)
    if before['environment']['browser'].get('timing_mode') != 'ordinary':
        raise ValueError('Diagnostic geometry timing cannot qualify comparison')
    if __package__:
        from tools.benchmark_workflow import compare_metrics
    else:
        from benchmark_workflow import compare_metrics
    policy = json.loads((ROOT / 'benchmarks/registry.json').read_text())['stress_tracks']['workflow-million']['comparison']
    def metrics(value):
        return {'prepared.geometry.million': {'total_ms': statistics.median(row['trace']['complete_ms'] for row in value['samples']),
            'endpoints': {
                'post_stroke': statistics.median(row['trace']['first_visible_ms'] for row in value['samples']),
                'first_raf': statistics.median(row['trace']['first_raf_ms'] for row in value['samples']),
                'max_post_stroke': max(row['trace']['first_visible_ms'] for row in value['samples']),
                'max_first_raf': max(row['trace']['first_raf_ms'] for row in value['samples']),
                'max_complete': max(row['trace']['complete_ms'] for row in value['samples'])}}}
    return {**compare_metrics(metrics(before), metrics(after), policy), 'policy': policy}


def new_source(source, output):
    source = source.resolve(); output = output.resolve(); output.mkdir(parents=True, exist_ok=False)
    receipt = {'status': 'running', 'source_start': source_identity(source),
        'harness': {str(p.relative_to(ROOT)): digest(p) for p in sorted([*HARNESS.glob('*'), ROOT / 'benchmarks/workflow/server.py', ROOT / 'benchmarks/workflow/fixture-app.mjs', ROOT / 'benchmarks/workflow/browser.mjs', ROOT / 'benchmarks/navigation-probe.mjs']) if p.is_file()} | {'tools/benchmark_prepared_geometry.py': digest(__file__)},
        'environment': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(),
            'packages': {name: importlib.metadata.version(name) for name in ('numpy', 'h5py', 'Flask', 'Werkzeug', 'scipy')},
            'node': subprocess.check_output(['node', '--version'], text=True).strip(), 'cpus': os.cpu_count()},
        'dependencies': dependency_fingerprints(source),
        'dependency_file_sha256': {name: digest(source / name) for name in ['workspace-app/package-lock.json', 'desktop/package-lock.json', 'benchmarks/requirements-py311.txt']},
        'fixture': 'prepared-geometry-v2:foreground:1000-metadata:200-protocol:1000000-samples:gzip64-f64-S10',
        'limits': 'Owned SQL doubles, canonical sealed index/source/geometry, production React, threaded Werkzeug. No native MySQL, packaged Waitress, compositor or cold disk qualification.'}
    return {'source': source, 'output': output, 'receipt': receipt, 'server': None}


def start_source(state):
    source, output, receipt = state['source'], state['output'], state['receipt']
    receipt['native_helper'] = compile_helper(source, output)
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'RIEKE_DESKTOP_RUNTIME': str(output / 'runtime')}
    with (output / 'server.log').open('w') as log:
        state['server'] = subprocess.Popen([sys.executable, '-B', str(HARNESS / 'server.py'), '--source', str(source), '--output', str(output / 'server')], stdout=log, stderr=subprocess.STDOUT, env=env)
    deadline = time.monotonic() + 180
    while not (output / 'server/server.json').exists():
        if state['server'].poll() is not None or time.monotonic() > deadline:
            raise RuntimeError('Owned server startup failed or timed out')
        time.sleep(.1)
    receipt['payload_sha256'] = json.loads((output / 'server/server.json').read_text())['diagnostic']['payload_sha256']


def finish_source(state, error=None):
    source, output, receipt, server = (state[key] for key in ('source', 'output', 'receipt', 'server'))
    if error is not None:
        receipt.update(status='failed', error=str(error))
    browser_file = output / 'browser/receipt.json'
    if browser_file.exists():
        try:
            browser = json.loads(browser_file.read_text())
            receipt['samples'] = browser.get('samples', [])
            if 'environment' in browser:
                receipt['environment']['browser'] = browser['environment']
            for key in ('pair', 'pair_role'):
                if key in browser: receipt[key] = browser[key]
            if browser['status'] != 'passed':
                raise RuntimeError('Browser correctness failed: ' + browser.get('error', 'unknown'))
            if error is None: receipt['status'] = 'passed'
        except Exception as caught:
            receipt.update(status='failed', browser_error=str(caught))
    else:
        receipt.update(status='failed', browser_error='Missing browser receipt')
    if server and server.poll() is None:
        server.terminate()
        try: server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill(); server.wait(); receipt.update(status='failed', cleanup_error='Server killed after graceful shutdown timeout')
    if server and server.returncode != 0:
        receipt.update(status='failed', server_exit=server.returncode)
    cleanup = output / 'server/cleanup.json'
    receipt['cleanup'] = json.loads(cleanup.read_text()) if cleanup.exists() else None
    receipt['source_end'] = source_identity(source)
    try: validate(receipt)
    except ValueError as caught: receipt.update(status='failed', validation_error=str(caught))
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    return receipt


def terminate_browser_groups(process, process_file):
    groups = {process.pid}; identity_error = None
    # Snapshot detached descendant groups before asking Node to shut down.
    try:
        for child in psutil.Process(process.pid).children(recursive=True):
            try:
                if os.getpgid(child.pid) == child.pid: groups.add(child.pid)
            except ProcessLookupError: pass
    except psutil.NoSuchProcess: pass
    process_files = process_file if isinstance(process_file, (tuple, list)) else [process_file]
    for process_file in process_files:
        if not process_file or not process_file.exists(): continue
        try:
            identity = json.loads(process_file.read_text()); pid = identity.get('pid')
            if type(pid) is not int or pid < 2 or not isinstance(identity.get('args'), list):
                raise RuntimeError('Malformed owned browser process identity')
            try:
                owner = psutil.Process(pid)
                if owner.cmdline() != identity['args'] or os.getpgid(pid) != pid:
                    raise RuntimeError('Owned browser process identity changed')
            except (psutil.NoSuchProcess, ProcessLookupError): pass
            groups.add(pid)
        except Exception as caught: identity_error = caught
    def alive(group):
        try: os.killpg(group, 0); return True
        except ProcessLookupError: return False
    for group in groups:
        try: os.killpg(group, signal.SIGTERM)
        except ProcessLookupError: pass
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired: pass
    # A reaped Node leader says nothing about its detached browser or children.
    for group in groups:
        if alive(group):
            try: os.killpg(group, signal.SIGKILL)
            except ProcessLookupError: pass
    process.wait(timeout=5)
    deadline = time.monotonic() + 5
    while any(alive(group) for group in groups):
        if time.monotonic() >= deadline: raise RuntimeError('Owned browser process groups survived forced cleanup')
        time.sleep(.05)
    if identity_error is not None: raise RuntimeError('Owned browser identity could not be verified') from identity_error


def run_browser(command, log, timeout, process_file=None):
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        code = process.wait(timeout=timeout)
        if code: raise subprocess.CalledProcessError(code, command)
    except BaseException:
        terminate_browser_groups(process, process_file)
        raise


def run(source, output):
    state = new_source(source, output); error = None
    try:
        start_source(state)
        with (state['output'] / 'browser.log').open('w') as log:
            run_browser(['node', str(HARNESS / 'browser.mjs'), str(state['source']), str(state['output'] / 'server/server.json'), str(state['output'] / 'browser'), '3'], log, timeout=900, process_file=state['output'] / 'browser/browser-process.json')
    except Exception as caught: error = caught
    return finish_source(state, error)


def source_binding(identity):
    return {key: identity[key] for key in ('commit', 'tree')} | {
        'files_sha256': hashlib.sha256(json.dumps(identity['files'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()}


PAIRED_PROTOCOL = 'paired-independent-browsers-BCCBBC-v1'
PAIRED_ORDER = [{'role': role, 'sample': sample} for role, sample in (
    ('baseline', 0), ('candidate', 0), ('candidate', 1), ('baseline', 1), ('baseline', 2), ('candidate', 2))]


def validate_pair(before, after):
    pair = before.get('pair')
    if (not isinstance(pair, dict) or pair != after.get('pair') or
            before.get('pair_role') != 'baseline' or after.get('pair_role') != 'candidate' or
            pair.get('protocol') != PAIRED_PROTOCOL or not isinstance(pair.get('id'), str) or
            not re.fullmatch(r'[0-9a-f]{32}', pair['id'])):
        raise ValueError('Missing or incompatible paired sampling identity')
    if pair.get('sources') != {'baseline': source_binding(before['source_start']), 'candidate': source_binding(after['source_start'])}:
        raise ValueError('Paired source binding mismatch')
    if pair.get('order') != PAIRED_ORDER or pair.get('completed') != [dict(item, execution_index=i) for i, item in enumerate(PAIRED_ORDER)]:
        raise ValueError('Incomplete or reordered paired sampling')
    if (any(type(item['sample']) is not int for item in pair['order']) or
            any(type(item['sample']) is not int or type(item['execution_index']) is not int for item in pair['completed'])):
        raise ValueError('Malformed paired sample ordinals')
    instances = pair.get('browser_instances')
    if (not isinstance(instances, dict) or set(instances) != {'baseline', 'candidate'} or
            any(type(value) is not int or value < 2 for value in instances.values()) or
            instances['baseline'] == instances['candidate']):
        raise ValueError('Paired sources require independent browser instances')
    for role, receipt in (('baseline', before), ('candidate', after)):
        outer_environment = receipt.get('environment')
        environment = outer_environment.get('browser') if isinstance(outer_environment, dict) else None
        if not isinstance(environment, dict): raise ValueError('Missing paired browser environment')
        if (not isinstance(pair.get('browser_version'), str) or not pair['browser_version'] or environment.get('browser') != pair['browser_version'] or
                environment.get('sampling_protocol') != PAIRED_PROTOCOL):
            raise ValueError('Paired browser identity mismatch')
        launch = environment.get('browser_launch')
        if (not isinstance(launch, dict) or launch.get('distribution') != 'playwright-chromium-headless-shell' or
                launch.get('executable_override') is not False or not isinstance(launch.get('playwright_version'), str) or
                not launch['playwright_version']):
            raise ValueError('Paired comparison requires the pinned Playwright browser')
        for index, row in enumerate(receipt['samples']):
            execution_index = PAIRED_ORDER.index({'role': role, 'sample': index})
            if (type(row.get('sample_index')) is not int or type(row.get('execution_index')) is not int or
                    row.get('pair_id') != pair['id'] or row.get('protocol') != PAIRED_PROTOCOL or
                    row.get('source_role') != role or row.get('sample_index') != index or
                    row.get('browser_instance') != instances[role] or
                    row.get('execution_index') != execution_index or
                    row.get('sample_class') != ('first_trace_after_setup_warm_OS' if index == 0 else 'subsequent_trace_fresh_renderer_warm_OS')):
                raise ValueError('Missing or duplicated paired source sample')


def run_pair(baseline, candidate, output):
    output = output.resolve(); output.mkdir(parents=True, exist_ok=False)
    states = {}; error = None
    try:
        for role, source in (('baseline', baseline), ('candidate', candidate)):
            states[role] = new_source(source, output / role)
            start_source(states[role])
        if states['baseline']['receipt']['dependencies'] != states['candidate']['receipt']['dependencies']:
            raise ValueError('Paired sources require identical locked dependencies')
        plan = {'pair_id': uuid.uuid4().hex, 'sources': {
            role: {'root': str(state['source']), 'serverJson': str(state['output'] / 'server/server.json'),
                   'output': str(state['output'] / 'browser'), 'process_file': str(state['output'] / 'browser-process.json'), 'binding': source_binding(state['receipt']['source_start'])}
            for role, state in states.items()}}
        (output / 'plan.json').write_text(json.dumps(plan, indent=2))
        with (output / 'browser.log').open('w') as log:
            run_browser(['node', str(HARNESS / 'paired.mjs'), str(output / 'plan.json')], log, timeout=1800, process_file=[state['output'] / 'browser-process.json' for state in states.values()])
    except Exception as caught: error = caught
    finally:
        # Both owned servers must close even if one receipt or cleanup is broken.
        receipts = {}
        for role, state in states.items():
            try: receipts[role] = finish_source(state, error)
            except Exception as caught:
                error = caught
                state['receipt'].update(status='failed', finalization_error=str(caught))
                (state['output'] / 'receipt.json').write_text(json.dumps(state['receipt'], indent=2))
                receipts[role] = state['receipt']
    try:
        if error is not None: raise error
        result = compare(receipts['baseline'], receipts['candidate'])
    except Exception as caught: result = {'status': 'failed', 'error': str(caught)}
    (output / 'comparison.json').write_text(json.dumps(result, indent=2))
    return result


def main():
    def interrupted(signum, _frame):
        raise InterruptedError('Geometry run cancelled by signal ' + str(signum))
    for signum in (signal.SIGTERM, signal.SIGINT): signal.signal(signum, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('run'); command.add_argument('--source-root', type=Path, required=True); command.add_argument('--output', type=Path, required=True)
    command = sub.add_parser('pair'); command.add_argument('--baseline-source', type=Path, required=True); command.add_argument('--source-root', type=Path, required=True); command.add_argument('--output', type=Path, required=True)
    command = sub.add_parser('compare'); command.add_argument('baseline', type=Path); command.add_argument('candidate', type=Path); command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'run': result = run(args.source_root, args.output)
    elif args.command == 'pair': result = run_pair(args.baseline_source, args.source_root, args.output)
    else:
        try: result = compare(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
        except Exception as error: result = {'status': 'failed', 'error': str(error)}
        args.output.write_text(json.dumps(result, indent=2))
    summary = result if args.command in ('compare', 'pair') else {'status': result['status']}
    print(json.dumps({**summary, 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
