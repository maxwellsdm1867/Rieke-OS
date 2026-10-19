#!/usr/bin/env python3
"""Million-epoch backend route track: timed and counted production Flask routes.

Measures request paths only (no H5, no traces, no browser). Each profile runs in
its own owned worker process (benchmarks/routes/worker.py) importing application
code from ``--source-root`` with this checkout's harness bytes. Profiles differ
in project size and active-protocol membership so a flat line (work scales with
the target) can be distinguished from growth with the project.

  run      measure one source at the selected profiles
  pair     measure baseline then candidate serially, same harness, then compare
  compare  per-case comparison of two retained run receipts

Timing policy reuses everyday-million (greater of +25% or +5 ms on medians and
cold samples). Counted evidence (attestations, generation reads, SQL statements,
deep copies, witness/marshal calls, response bytes) is reported beside timings;
count increases are flagged for review but never averaged into timings.
Predicate-count differences on labels listed under ``expected_by_contract`` are
reported as contract changes (B11 missing semantics), not regressions.
Synthetic SQL doubles and an in-process Flask client: not native MySQL, HTTP
transport, renderer or release qualification.
"""
from __future__ import annotations
import argparse
import datetime
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

if __package__:
    from . import benchmark_everyday as query_bench
else:
    import benchmark_everyday as query_bench

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'disco-route-million-v1'
HARNESS = ['tools/benchmark_routes.py', 'tools/benchmark_everyday.py', 'benchmarks/routes/worker.py',
           'benchmarks/workflow/server.py', 'benchmarks/registry.json', 'benchmarks/requirements-py311.txt']


def config():
    return json.loads((ROOT/'benchmarks/registry.json').read_text())['stress_tracks']['route-million']


def harness():
    return {name: query_bench.sha((ROOT/name).read_bytes()) for name in HARNESS}


def load_average():
    try:
        one, five, fifteen = os.getloadavg()
    except OSError:
        return None
    return {'one': one, 'five': five, 'fifteen': fifteen, 'cpu_count': os.cpu_count(),
            'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}


def run_profile(source_root, output, name, profile, cfg, cases=''):
    import psutil
    raw = output/f'{name}.json'
    command = [sys.executable, '-B', str(ROOT/'benchmarks/routes/worker.py'), '--source-root', str(source_root),
               '--output', str(raw), '--epochs', str(profile['epochs']), '--protocol-epochs',
               str(profile['protocol_epochs']), '--samples', str(cfg['samples'])]
    if cases:
        command += ['--cases', cases]
    record = {'profile': profile, 'load_before': load_average(), 'peak_rss_bytes': 0}
    started = time.monotonic()
    problem = None
    with (output/f'{name}.log').open('wb') as log:
        child = subprocess.Popen(command, cwd=source_root, stdout=log, stderr=subprocess.STDOUT,
                                 env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, start_new_session=True)
        samples = []
        try:
            while child.poll() is None:
                try:
                    rss = psutil.Process(child.pid).memory_info().rss
                    record['peak_rss_bytes'] = max(record['peak_rss_bytes'], rss)
                except psutil.NoSuchProcess:
                    break
                if rss > cfg['max_rss_bytes']:
                    problem = f'{name}: RSS cap exceeded'
                elif time.monotonic() - started > cfg['max_worker_seconds']:
                    problem = f'{name}: timed out'
                if problem:
                    child.kill()
                    break
                if not samples or time.monotonic() - samples[-1][0] >= 30:
                    load = load_average()
                    samples.append((time.monotonic(), load['one'] if load else None))
                time.sleep(0.25)
        finally:
            if child.poll() is None:
                child.kill()
            code = child.wait()
    record.update(load_after=load_average(), load_one_samples=[value for _, value in samples],
                  wall_seconds=time.monotonic() - started, exit_code=code)
    if problem:
        record['error'] = problem
    if raw.is_file():
        record['sha256'] = query_bench.sha(raw.read_bytes())
        record['result'] = json.loads(raw.read_text())
    else:
        record['error'] = record.get('error') or f'{name}: worker produced no result (exit {code})'
    return record


def run(source_root, output, profiles=None, cases=''):
    cfg = config()
    source_root, output = source_root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    names = profiles or cfg['default_profiles']
    unknown = set(names) - set(cfg['profiles'])
    if unknown:
        raise ValueError(f'Unknown route profiles: {sorted(unknown)}')
    receipt = {'format': FORMAT, 'status': 'running', 'config': cfg, 'source_root': str(source_root),
               'source_start': query_bench.source(source_root), 'environment': query_bench.environment(),
               'harness_start': harness(), 'profiles': {}, 'case_subset': cases or None,
               'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    query_bench.write(output/'receipt.json', receipt)
    try:
        for name in names:
            print(f'{name}: running {cfg["profiles"][name]}', flush=True)
            record = run_profile(source_root, output, name, cfg['profiles'][name], cfg, cases)
            receipt['profiles'][name] = record
            query_bench.write(output/'receipt.json', receipt)
            status = record.get('result', {}).get('status')
            print(f'{name}: {status or record.get("error")} in {record["wall_seconds"]:.0f}s, '
                  f'peak RSS {record["peak_rss_bytes"] / 2**30:.2f} GiB', flush=True)
        receipt['source_end'] = query_bench.source(source_root)
        receipt['harness_end'] = harness()
        if receipt['source_start'] != receipt['source_end'] or receipt['harness_start'] != receipt['harness_end']:
            raise RuntimeError('Source/harness changed during measurement')
        failed = [name for name, record in receipt['profiles'].items()
                  if record.get('error') or record.get('result', {}).get('status') != 'passed']
        receipt['failed_profiles'] = failed
        receipt['status'] = 'diagnostic' if cases else ('failed' if failed else 'passed')
    except BaseException as error:
        receipt['status'] = 'failed'
        receipt['error'] = repr(error)
        raise
    finally:
        query_bench.write(output/'receipt.json', receipt)
        report(receipt, output/'routes.md')
    return output/'receipt.json'


def report(receipt, path):
    lines = ['# Million-epoch backend routes', '', f"Status: **{receipt['status']}**; source "
             f"`{receipt['source_start']['commit'][:12]}`{' (dirty)' if receipt['source_start']['status'] else ''}.", '']
    for name, record in receipt.get('profiles', {}).items():
        result = record.get('result', {})
        load = record.get('load_before') or {}
        lines += [f"## {name}: {record['profile']['epochs']:,} project / {record['profile']['protocol_epochs']:,} protocol epochs", '',
                  f"Worker {result.get('status', record.get('error'))}; wall {record.get('wall_seconds', 0):.0f} s; "
                  f"peak RSS {record.get('peak_rss_bytes', 0) / 2**30:.2f} GiB; load before {load.get('one', 'n/a')}, "
                  f"after {(record.get('load_after') or {}).get('one', 'n/a')}.", '',
                  *([f"Typed sidecar: {result['typed_index'].get('status')}.", ''] if result.get('typed_index') else []),
                  *(['Notes: ' + '; '.join(result['notes']), ''] if result.get('notes') else []),
                  '| Case | Cold ms | Warm median ms | Bytes | Attest | SQLite stmts | Deep copies | Rows evaluated | Status |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
        for case, data in result.get('cases', {}).items():
            counts = data.get('counts', {})
            lines.append(f"| {case} | {data.get('cold_ms', '')} | {data.get('median_ms', '')} | "
                         f"{(data.get('bytes') or [''])[-1]} | {statistics.median(data['attestations']) if data.get('attestations') else ''} | "
                         f"{counts.get('sqlite.execute', '')} | {counts.get('copy.deepcopy', '')} | {counts.get('predicate.matches', '')} | "
                         f"{data.get('status')}{(': ' + data['error'][:80]) if data.get('error') else ''} |")
        lines.append('')
    path.write_text('\n'.join(lines) + '\n')


def load_receipt(path, *, allow_dirty=True):
    receipt = json.loads(path.read_text())
    if receipt.get('format') != FORMAT or receipt.get('status') != 'passed':
        raise ValueError(f'{path}: missing, failed or diagnostic route receipt')
    if receipt.get('config') != config() or receipt.get('harness_start') != harness():
        raise ValueError(f'{path}: different route suite; rerun both sources with this harness')
    for boundary in ('source_start', 'source_end'):
        query_bench.validate_source(receipt.get(boundary))
    query_bench.validate_environment(receipt.get('environment'))
    if receipt['source_start'] != receipt['source_end']:
        raise ValueError(f'{path}: source changed during measurement')
    for name, record in receipt['profiles'].items():
        raw = path.parent/f'{name}.json'
        if query_bench.sha(raw.read_bytes()) != record.get('sha256') or json.loads(raw.read_text()) != record.get('result'):
            raise ValueError(f'{path}: raw {name} evidence changed')
    return receipt


def compare(baseline_path, candidate_path, output):
    baseline, candidate = load_receipt(baseline_path), load_receipt(candidate_path)
    for key in ('environment', 'config', 'harness_start'):
        if baseline[key] != candidate[key]:
            raise ValueError(f'Incomparable {key}; use matched runtime/hardware/harness')
    if baseline['source_start']['status']:
        raise ValueError('Baseline source must be clean and immutable')
    cfg = candidate['config']
    policy = cfg['comparison']
    rows, findings, count_findings, contract = [], [], [], []
    for profile in baseline['profiles']:
        before_cases = baseline['profiles'][profile]['result']['cases']
        after_cases = candidate['profiles'][profile]['result']['cases']
        if set(before_cases) != set(after_cases):
            raise ValueError(f'{profile}: different case coverage')
        for case, before in before_cases.items():
            after = after_cases[case]
            for metric in ('median_ms', 'cold_ms'):
                if before.get(metric) is None:
                    continue
                old, new = before[metric], after[metric]
                threshold = max(old*(1+policy['relative']), old+policy['absolute_ms'])
                review = new > threshold
                rows.append({'profile': profile, 'case': case, 'metric': metric, 'baseline_ms': old,
                             'candidate_ms': new, 'threshold_ms': threshold, 'review_required': review,
                             'change': (new-old)/old if old else None})
                if review:
                    findings.append(f'{profile}/{case}/{metric}')
            for name, old in ({} if before.get('counts_variable') else before.get('counts', {})).items():
                new = after.get('counts', {}).get(name, 0)
                if new > old:
                    count_findings.append({'profile': profile, 'case': case, 'count': name, 'baseline': old, 'candidate': new})
        before_counts = baseline['profiles'][profile]['result'].get('predicate_counts', {})
        after_counts = candidate['profiles'][profile]['result'].get('predicate_counts', {})
        for label, value in before_counts.items():
            if after_counts.get(label) != value:
                entry = {'profile': profile, 'predicate': label, 'baseline': value, 'candidate': after_counts.get(label)}
                if label in cfg['expected_by_contract']:
                    contract.append(entry)
                else:
                    findings.append(f'{profile}/predicate_counts/{label}')
                    entry['unexpected'] = True
                    contract.append(entry)
    result = {'format': FORMAT+'-comparison', 'status': 'review_required' if findings else 'passed',
              'baseline_commit': baseline['source_start']['commit'], 'candidate_commit': candidate['source_start']['commit'],
              'candidate_dirty': bool(candidate['source_start']['status']),
              'baseline_receipt_sha256': query_bench.sha(baseline_path.read_bytes()),
              'candidate_receipt_sha256': query_bench.sha(candidate_path.read_bytes()),
              'policy': policy, 'review_required': findings, 'count_increases': count_findings,
              'predicate_count_changes': contract, 'metrics': rows,
              'load': {side: {name: {k: record.get(k) for k in ('load_before', 'load_after', 'load_one_samples')}
                              for name, record in receipt['profiles'].items()}
                       for side, receipt in (('baseline', baseline), ('candidate', candidate))},
              'qualification': 'Synthetic SQL doubles and in-process Flask; not native MySQL/HTTP/UI/release qualification.'}
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return result


def acquire_lock(lock, timeout=None, *, poll=2.0, report_every=30.0, out=sys.stderr):
    """Wait for the shared stress lock instead of failing at once.

    Other runners still take it non-blocking and fail fast; this one polls,
    logs who holds it, and records itself as holder once acquired. The holder
    line is advisory: the flock is the only exclusion.
    """
    import fcntl
    started = time.monotonic()
    last = None
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            waited = time.monotonic() - started
            if timeout is not None and waited >= timeout:
                raise TimeoutError(f'Stress lock still held after {waited:.0f} s: {lock_holder(lock)}')
            if last is None or time.monotonic() - last >= report_every:
                print(f'waiting for stress lock held by {lock_holder(lock)} ({waited:.0f} s)', file=out, flush=True)
                last = time.monotonic()
            time.sleep(poll)
    lock.seek(0)
    lock.truncate()
    lock.write(f'pid={os.getpid()} since={datetime.datetime.now(datetime.timezone.utc).isoformat()} '
               f'cmd={" ".join(sys.argv)[:300]}\n')
    lock.flush()
    return time.monotonic() - started


def lock_holder(lock):
    try:
        lock.seek(0)
        text = lock.read().strip()
    except OSError:
        text = ''
    return text or 'an unrecorded process (runners that do not write holder lines)'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    run_parser = commands.add_parser('run')
    run_parser.add_argument('--source-root', type=Path, default=ROOT)
    run_parser.add_argument('--output', type=Path, required=True)
    run_parser.add_argument('--profile', action='append', help='Profile name from the registry (repeatable)')
    run_parser.add_argument('--cases', default='', help='Diagnostic case-name prefixes; receipt cannot qualify')
    pair = commands.add_parser('pair')
    pair.add_argument('--baseline-source', type=Path, required=True)
    pair.add_argument('--source-root', type=Path, default=ROOT)
    pair.add_argument('--output', type=Path, required=True)
    pair.add_argument('--profile', action='append')
    for sub in (run_parser, pair):
        sub.add_argument('--lock-timeout', type=float, default=None,
                         help='Seconds to wait for the shared stress lock (default: wait indefinitely)')
    comparison = commands.add_parser('compare')
    comparison.add_argument('baseline', type=Path)
    comparison.add_argument('candidate', type=Path)
    comparison.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('RIEKE_TEST_DOM_MODULE') is not None:
        print('RIEKE_TEST_DOM_MODULE must be unset', file=sys.stderr)
        return 1
    try:
        if args.command in ('run', 'pair'):
            import tempfile
            # Shares the stress-track lock: never overlap million-row workers.
            with (Path(tempfile.gettempdir())/'disco-everyday-million.lock').open('a+') as lock:
                acquire_lock(lock, args.lock_timeout)
                try:
                    if args.command == 'run':
                        print(run(args.source_root, args.output, args.profile, args.cases))
                        return 0
                    args.output.mkdir(parents=True, exist_ok=False)
                    base = run(args.baseline_source, args.output/'baseline', args.profile)
                    cand = run(args.source_root, args.output/'candidate', args.profile)
                finally:
                    lock.seek(0)
                    lock.truncate()  # Holder line is cleared before the flock is released.
            result = compare(base, cand, args.output/'comparison.json')
        else:
            result = compare(args.baseline, args.candidate, args.output)
        print(json.dumps({'status': result['status'], 'review_required': result['review_required'],
                          'count_increases': len(result['count_increases'])}))
        return 2 if result['review_required'] else 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
