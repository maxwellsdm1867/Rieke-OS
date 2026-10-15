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
import re
import shutil
import statistics
import subprocess
import sys
import time

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
    samples = receipt.get('samples', [])
    if len(samples) != 3:
        raise ValueError('Exactly three ordinary samples required')
    for index, row in enumerate(samples):
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


def run(source, output):
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
    server = None
    try:
        receipt['native_helper'] = compile_helper(source, output)
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'RIEKE_DESKTOP_RUNTIME': str(output / 'runtime')}
        with (output / 'server.log').open('w') as log:
            server = subprocess.Popen([sys.executable, '-B', str(HARNESS / 'server.py'), '--source', str(source), '--output', str(output / 'server')], stdout=log, stderr=subprocess.STDOUT, env=env)
        deadline = time.monotonic() + 180
        while not (output / 'server/server.json').exists():
            if server.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Owned server startup failed or timed out')
            time.sleep(.1)
        receipt['payload_sha256'] = json.loads((output / 'server/server.json').read_text())['diagnostic']['payload_sha256']
        with (output / 'browser.log').open('w') as log:
            subprocess.run(['node', str(HARNESS / 'browser.mjs'), str(source), str(output / 'server/server.json'), str(output / 'browser'), '3'], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
        browser = json.loads((output / 'browser/receipt.json').read_text())
        if browser['status'] != 'passed':
            raise RuntimeError('Browser correctness failed')
        receipt['samples'] = browser['samples']; receipt['environment']['browser'] = browser['environment']
        receipt['status'] = 'passed'
    except Exception as error:
        receipt.update(status='failed', error=str(error))
    finally:
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
        except ValueError as error: receipt.update(status='failed', validation_error=str(error))
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('run'); command.add_argument('--source-root', type=Path, required=True); command.add_argument('--output', type=Path, required=True)
    command = sub.add_parser('compare'); command.add_argument('baseline', type=Path); command.add_argument('candidate', type=Path); command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'run': result = run(args.source_root, args.output)
    else:
        try: result = compare(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
        except Exception as error: result = {'status': 'failed', 'error': str(error)}
        args.output.write_text(json.dumps(result, indent=2))
    summary = result if args.command == 'compare' else {'status': result['status']}
    print(json.dumps({**summary, 'output': str(args.output)}))
    return 0 if result['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
