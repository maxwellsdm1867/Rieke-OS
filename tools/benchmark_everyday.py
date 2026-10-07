#!/usr/bin/env python3
"""Repeatable million-epoch query stress lane; never release qualification."""
from __future__ import annotations
import argparse
import datetime
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'disco-everyday-million-v1'
HARNESS = ['tools/benchmark_everyday.py', 'benchmarks/everyday/fixture.py',
           'benchmarks/everyday/worker.py', 'benchmarks/registry.json', 'benchmarks/requirements-py311.txt']


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def config():
    return json.loads((ROOT/'benchmarks/registry.json').read_text())['stress_tracks']['everyday-million']


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def source(root):
    # Include dirty and newly added application files, not just the HEAD commit.
    paths = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '--cached',
                                    '--others', '--exclude-standard'])
    files = {}
    for name in sorted(set(os.fsdecode(p) for p in paths.split(b'\0') if p)):
        if name.startswith(('python/', 'workspace-app/', 'desktop/')) or name == 'rieke-release.json':
            path = root/name
            files[name] = sha(path.read_bytes()) if path.is_file() else 'deleted'
    return {'commit':git(root,'rev-parse','HEAD'), 'tree':git(root,'rev-parse','HEAD^{tree}'),
            'status':git(root,'status','--porcelain'), 'files':files, 'sha256':sha(canonical(files))}


def environment():
    import psutil
    if sys.platform == 'darwin':
        cpu = subprocess.check_output(['/usr/sbin/sysctl','-n','machdep.cpu.brand_string'], text=True).strip()
    else:
        cpu = platform.processor()
        if Path('/proc/cpuinfo').is_file():
            cpu = next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), cpu)
    if not cpu:
        raise ValueError('Cannot identify CPU model')
    return {'cpu_model':cpu, 'python':sys.version, 'sqlite':sqlite3.sqlite_version, 'os':platform.platform(),
            'machine':platform.machine(), 'host':platform.node(), 'cpu_count':os.cpu_count(), 'physical_memory':psutil.virtual_memory().total,
            'packages': sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions())}


def write(path, value):
    path.write_bytes(json.dumps(value, indent=2, allow_nan=False).encode()+b'\n')


def validate_lane(lane, data, cfg):
    if data.get('status') != 'passed' or data.get('lane') != lane or data.get('epochs') != 1_000_000:
        raise ValueError(f'{lane}: incomplete, failed or wrong-scale result')
    if data.get('h5_open_attempts') != []:
        raise ValueError(f'{lane}: H5 access')
    if set(data.get('operations',{})) != set(cfg['cases'][lane]):
        raise ValueError(f'{lane}: missing/extra cases')
    if set(data.get('guards',{})) != set(cfg['guards'][lane]) or not all(v is True for v in data['guards'].values()):
        raise ValueError(f'{lane}: missing/failed refusal checks')
    for name, case in data['operations'].items():
        samples = case.get('milliseconds', [])
        count = 1 if name == 'tree.first_root' else cfg['samples']
        if (len(samples) != count or any(type(x) not in (int,float) or not math.isfinite(x) or x < 0 for x in samples)
                or case.get('oracle_passed') is not True or len(case.get('answer_sha256',[])) != count
                or any(not isinstance(d, str) or not re.fullmatch('[a-f0-9]{64}', d) for d in case.get('answer_sha256',[]))
                or case.get('median_ms') != statistics.median(samples)):
            raise ValueError(f'{name}: invalid raw samples/oracle')
    for name in ('peak_rss_bytes', 'setup_seconds', 'elapsed_seconds'):
        value = data.get(name)
        if type(value) not in (int,float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{lane}: missing resource metric {name}')


    if data['peak_rss_bytes'] > cfg['max_rss_bytes'] or data['elapsed_seconds'] > cfg['max_worker_seconds']:
        raise ValueError(f'{lane}: resource cap exceeded')

PROVENANCE = ('source_start', 'source_end', 'environment', 'config', 'harness_start', 'harness_end')


def validate_source(value):
    if not isinstance(value, dict):
        raise ValueError('Missing source identity')
    for key in ('commit', 'tree'):
        if not isinstance(value.get(key), str) or not re.fullmatch('[a-f0-9]{40}', value[key]):
            raise ValueError('Invalid Git identity')
    files = value.get('files')
    if not isinstance(value.get('status'), str) or not isinstance(files, dict) or not files:
        raise ValueError('Missing source manifest')
    for name, digest in files.items():
        if (not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts
                or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}|deleted', digest)):
            raise ValueError('Invalid source file manifest')
    if value.get('sha256') != sha(canonical(files)):
        raise ValueError('Source manifest hash mismatch')


def validate_environment(value):
    if not isinstance(value, dict):
        raise ValueError('Missing runtime identity')
    for key in ('python', 'sqlite', 'os', 'machine', 'host', 'cpu_model'):
        if not isinstance(value.get(key), str) or not value[key]:
            raise ValueError('Incomplete runtime/hardware identity')
    for key in ('cpu_count', 'physical_memory'):
        if type(value.get(key)) is not int or value[key] <= 0:
            raise ValueError('Incomplete hardware identity')
    if not isinstance(value.get('packages'), list) or not value['packages']:
        raise ValueError('Missing dependency identity')


def load_receipt(path):
    value = json.loads(path.read_text())
    if value.get('format') != FORMAT or value.get('status') != 'passed':
        raise ValueError('Failed/incomplete/unsupported receipt')
    validate_source(value.get('source_start'))
    validate_source(value.get('source_end'))
    validate_environment(value.get('environment'))
    provenance = path.parent/'provenance.json'
    if (sha(provenance.read_bytes()) != value.get('provenance_sha256')
            or json.loads(provenance.read_text()) != {k:value[k] for k in PROVENANCE}):
        raise ValueError('Provenance evidence changed')
    if value['source_start'] != value['source_end'] or value['harness_start'] != value['harness_end']:
        raise ValueError('Source/harness changed during the run')
    if value['config'] != config() or value['harness_start'] != {p:sha((ROOT/p).read_bytes()) for p in HARNESS}:
        raise ValueError('Receipt belongs to a different suite; rerun with this harness')
    if set(value['lanes']) != {'tree','typed'}:
        raise ValueError('Missing lane')
    for lane in ('tree','typed'):
        record = value['lanes'][lane]
        # Fixed local paths prevent receipts from referring to unrelated results.
        raw = path.parent/(lane+'.json')
        log = path.parent/(lane+'.log')
        if sha(raw.read_bytes()) != record['sha256'] or sha(log.read_bytes()) != record['log_sha256']:
            raise ValueError('Worker evidence changed')
        data = json.loads(raw.read_text())
        validate_lane(lane, data, value['config'])
        if data != record['result']:
            raise ValueError('Receipt and raw worker evidence disagree')
    return value


def run(root, output):
    import psutil
    cfg = config()
    root = root.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'format':FORMAT, 'status':'running', 'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'config':cfg, 'source_root':str(root), 'source_start':source(root),
               'environment':environment(), 'harness_start':{p:sha((ROOT/p).read_bytes()) for p in HARNESS}, 'lanes':{}}
    write(output/'receipt.json', receipt)
    try:
        for lane in ('tree','typed'):
            command = [sys.executable, '-B', str(ROOT/'benchmarks/everyday/worker.py'),
                       '--source-root',str(root),'--output',str(output/(lane+'.json')),'--lane',lane]
            started = time.monotonic()
            problem = None
            with (output/(lane+'.log')).open('wb') as log:
                child = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                         env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'})
                try:
                    while child.poll() is None:
                        try:
                            rss = psutil.Process(child.pid).memory_info().rss
                        except psutil.NoSuchProcess:
                            break
                        if rss > cfg['max_rss_bytes']:
                            problem = f'{lane}: RSS cap exceeded'
                        if time.monotonic()-started > cfg['max_worker_seconds']:
                            problem = f'{lane}: timed out'
                        if problem:
                            child.kill()
                            break
                        time.sleep(0.25)
                finally:
                    if child.poll() is None:
                        child.kill()
                    code = child.wait()
            if problem or code:
                raise RuntimeError(problem or f'{lane}: worker failed ({code}); see {lane}.log')
            raw = output/(lane+'.json')
            data = json.loads(raw.read_text())
            validate_lane(lane, data, cfg)
            receipt['lanes'][lane] = {'sha256':sha(raw.read_bytes()),
                                     'log_sha256':sha((output/(lane+'.log')).read_bytes()), 'result':data}
            write(output/'receipt.json', receipt)
            print(f'{lane}: passed exact results/refusals at 1,000,000 epochs', flush=True)
        receipt['source_end'] = source(root)
        receipt['harness_end'] = {p:sha((ROOT/p).read_bytes()) for p in HARNESS}
        if receipt['source_start'] != receipt['source_end'] or receipt['harness_start'] != receipt['harness_end']:
            raise RuntimeError('Source/harness changed during measurement')
        write(output/'provenance.json', {k:receipt[k] for k in PROVENANCE})
        receipt['provenance_sha256'] = sha((output/'provenance.json').read_bytes())
        receipt['status'] = 'passed'
    except BaseException as error:
        receipt['status'] = 'failed'
        receipt['error'] = repr(error)
        raise
    finally:
        write(output/'receipt.json', receipt)
    return output/'receipt.json'


def compare(baseline_path, candidate_path, output):
    baseline, candidate = load_receipt(baseline_path), load_receipt(candidate_path)
    for key in ('environment','config','harness_start'):
        if baseline[key] != candidate[key]:
            raise ValueError(f'Incomparable {key}; use matched runtime/hardware/harness')
    if baseline['source_start']['status']:
        raise ValueError('Baseline source must be clean and immutable; dirty candidates are diagnostic only')
    policy = candidate['config']['comparison']
    findings, rows = [], []
    for lane in ('tree','typed'):
        before = baseline['lanes'][lane]['result']
        after = candidate['lanes'][lane]['result']
        metrics = [(k, v['median_ms'], after['operations'][k]['median_ms'], policy['relative'], policy['absolute_ms'])
                   for k,v in before['operations'].items()]
        metrics += [(lane+'.peak_rss_bytes',before['peak_rss_bytes'],after['peak_rss_bytes'],policy['memory_relative'],policy['memory_absolute_bytes']),
                    (lane+'.setup_ms',before['setup_seconds']*1000,after['setup_seconds']*1000,policy['relative'],policy['absolute_ms'])]
        for name, old, new, relative, absolute in metrics:
            threshold = max(old*(1+relative), old+absolute)
            review = new > threshold
            rows.append({'case':name,'baseline':old,'candidate':new,'threshold':threshold,'review_required':review})
            if review:
                findings.append(name)
    result = {'format':FORMAT+'-comparison','status':'review_required' if findings else 'passed',
              'baseline':str(baseline_path.resolve()),'candidate':str(candidate_path.resolve()),
              'baseline_receipt_sha256':sha(baseline_path.read_bytes()), 'candidate_receipt_sha256':sha(candidate_path.read_bytes()),
              'policy':policy,'review_required':findings,'metrics':rows,
              'qualification':'Synthetic query stress only. A pass is not native/UI/release qualification.'}
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    run_parser = commands.add_parser('run')
    run_parser.add_argument('--source-root', type=Path, default=ROOT)
    run_parser.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('iteration', help='Run the retained baseline then the current candidate, serially')
    check.add_argument('--baseline-source', type=Path, required=True)
    check.add_argument('--source-root', type=Path, default=ROOT)
    check.add_argument('--output', type=Path, required=True)
    comp = commands.add_parser('compare')
    comp.add_argument('baseline', type=Path)
    comp.add_argument('candidate', type=Path)
    comp.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'compare':
            result = compare(args.baseline,args.candidate,args.output)
        else:
            # Serialize this stress track across checkouts; never contend with itself.
            with (Path(tempfile.gettempdir())/'disco-everyday-million.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError('Another everyday-million run is active') from None
                if args.command == 'run':
                    path = run(args.source_root,args.output)
                    print(path)
                    return 0
                if git(args.baseline_source, 'status', '--porcelain'):
                    raise ValueError('Baseline source must be clean')
                args.output.mkdir(parents=True, exist_ok=False)
                baseline = run(args.baseline_source,args.output/'baseline')
                candidate = run(args.source_root,args.output/'candidate')
                result = compare(baseline,candidate,args.output/'comparison.json')
        print(json.dumps({'status':result['status'],'review_required':result['review_required']}))
        return 2 if result['review_required'] else 0
    except Exception as error:
        print(f'Benchmark failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
