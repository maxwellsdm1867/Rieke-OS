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


def merge_groups(groups):
    """One profile result from disjoint case-group workers, in group order."""
    results = {name: record['result'] for name, record in groups.items()}
    cases, owner = {}, {}
    for name, result in results.items():
        for case, data in result.get('cases', {}).items():
            if case in cases:
                raise ValueError(f'Case {case} measured by both {owner[case]} and {name}')
            cases[case], owner[case] = data, name
    first = next(iter(results.values()))
    predicate_counts = {}
    for result in results.values():
        predicate_counts.update(result.get('predicate_counts', {}))
    return {'format': first.get('format'), 'grouped': True, 'case_groups': list(groups),
            'status': 'passed' if all(r.get('status') == 'passed' for r in results.values()) else 'failed',
            'epochs': first.get('epochs'), 'protocol_epochs': first.get('protocol_epochs'), 'samples': first.get('samples'),
            'cases': cases, 'case_group_of': owner, 'predicate_counts': predicate_counts,
            'notes': sorted({note for r in results.values() for note in r.get('notes', [])}),
            'failed_cases': [case for r in results.values() for case in r.get('failed_cases', [])],
            'h5_open_attempts': [item for r in results.values() for item in r.get('h5_open_attempts', [])],
            'typed_index': {name: r.get('typed_index') for name, r in results.items()},
            'publication': {name: r.get('publication') for name, r in results.items()},
            'peak_rss_bytes_by_group': {name: r.get('peak_rss_bytes') for name, r in results.items()}}


def run_grouped(source_root, output, name, profile, cfg):
    """Each case group in its own worker (fresh fixture), each with its own peak RSS.

    Used where one process holding every case exceeds the RSS cap. Base and
    candidate share the registry grouping, so merged results stay comparable.
    """
    groups = {}
    for group, prefixes in cfg['case_groups'].items():
        print(f'{name}: group {group}', flush=True)
        groups[group] = run_profile(source_root, output, f'{name}--{group}', profile, cfg, ','.join(prefixes))
    record = {'profile': profile, 'groups': groups,
              'peak_rss_bytes': max(g['peak_rss_bytes'] for g in groups.values()),
              'wall_seconds': sum(g['wall_seconds'] for g in groups.values()),
              'load_before': next(iter(groups.values())).get('load_before'),
              'load_after': list(groups.values())[-1].get('load_after'),
              'load_one_samples': [v for g in groups.values() for v in g.get('load_one_samples', [])]}
    errors = [f'{group}: {g["error"]}' for group, g in groups.items() if g.get('error')]
    if errors:
        record['error'] = '; '.join(errors)
    else:
        record['result'] = merge_groups(groups)
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
            profile = cfg['profiles'][name]
            if profile.get('grouped') and not cases:
                record = run_grouped(source_root, output, name, profile, cfg)
            else:
                record = run_profile(source_root, output, name, profile, cfg, cases)
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
                  *([f"Case groups (separate workers): " + ', '.join(f"{g} {(part.get('peak_rss_bytes') or 0) / 2**30:.2f} GiB / {part.get('wall_seconds', 0):.0f} s" for g, part in record['groups'].items()), ''] if record.get('groups') else []),
                  *([f"Typed sidecar: {result['typed_index'].get('status')}.", ''] if result.get('typed_index') and 'status' in result['typed_index'] else []),
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
        parts = ({f'{name}--{group}': part for group, part in record['groups'].items()}
                 if 'groups' in record else {name: record})
        for label, part in parts.items():
            raw = path.parent/f'{label}.json'
            if query_bench.sha(raw.read_bytes()) != part.get('sha256') or json.loads(raw.read_text()) != part.get('result'):
                raise ValueError(f'{path}: raw {label} evidence changed')
        if 'groups' in record and merge_groups(record['groups']) != record.get('result'):
            raise ValueError(f'{path}: merged {name} result differs from its group evidence')
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


SCALING_COUNTS = ('sqlite.execute', 'copy.deepcopy', 'predicate.matches', 'sql_double.read', 'generation.scope_read',
                  'protocol_state.metadata', 'protocol_state.materialized_state', 'service.query_result',
                  'service.refresh', 'tree_pages.build_scope', 'marshal.dumps')
ORDER = ('flat', 'sublinear', 'linear', 'superlinear')


def expected_class(case, cfg):
    """Everyday clicks must be flat; whole-project search predicates and exports may be linear.

    Query results (run, first and later pages, cursor pages) must be flat; the
    async result summary job is linear by design and informational.
    """
    for prefix in cfg['scaling'].get('flat_prefixes', []):
        if case.startswith(prefix):
            return 'flat'
    for prefix in cfg['scaling'].get('informational_prefixes', []):
        if case.startswith(prefix):
            return 'linear-informational'
    for prefix in cfg['scaling']['linear_allowed']:
        if case.startswith(prefix):
            return 'linear-allowed'
    return 'flat'


def growth(small, large, size_ratio, floor=0.0):
    """Ratio and class of a quantity between two sizes; at or under floor is flat."""
    import math
    if small is None or large is None:
        return None, None
    if large <= floor:
        return (large / small if small else None), 'flat'
    if not small:
        return None, 'superlinear'  # Appears only at the larger size.
    ratio = large / small
    exponent = math.log(ratio) / math.log(size_ratio) if ratio > 0 else 0.0
    return ratio, ('flat' if exponent < 0.25 else 'sublinear' if exponent < 0.75 else
                   'linear' if exponent < 1.3 else 'superlinear')


def peak_load(record):
    values = [v for v in record.get('load_one_samples', []) if v is not None]
    for key in ('load_before', 'load_after'):
        if (record.get(key) or {}).get('one') is not None:
            values.append(record[key]['one'])
    return max(values) if values else None


def scaling(receipt_path, small, large, project, output):
    """Per-case growth between two sizes, judged by load-independent counts.

    Primary verdict: call/statement/copy counts and response bytes from the
    counting pass. Warm-median timing ratios are shown beside them and are
    diagnostic whenever either profile ran at a load average above the limit.
    """
    receipt = json.loads(Path(receipt_path).read_text())
    cfg = receipt['config']
    profiles = receipt['profiles']
    for name in (small, large) + ((project,) if project else ()):
        if name not in profiles or 'result' not in profiles[name]:
            raise ValueError(f'Receipt lacks profile {name}')
    size = lambda name: profiles[name]['profile']['epochs']
    size_ratio, floor = size(large) / size(small), cfg['scaling']['flat_floor_ms']
    count_floor, load_limit = cfg['scaling']['count_floor'], cfg['scaling']['timing_load_limit']
    loads = {name: peak_load(profiles[name]) for name in profiles}
    used = [loads[n] for n in (small, large, project) if n]
    timing_diagnostic = any(v is None or v > load_limit for v in used)
    small_cases, large_cases = profiles[small]['result']['cases'], profiles[large]['result']['cases']
    project_cases = profiles[project]['result']['cases'] if project else {}
    rows, flagged, timing_notes = [], [], []

    def measures(a, b, ratio):
        out = {}
        for name in SCALING_COUNTS:
            x, y = a.get('counts', {}).get(name, 0), b.get('counts', {}).get(name, 0)
            if x or y:
                kind = growth(x, y, ratio, count_floor)[1] if (x or y > count_floor) else 'flat'
                out[name] = {'small': x, 'large': y, 'kind': kind}
        bx, by = statistics.median(a.get('bytes') or [0]), statistics.median(b.get('bytes') or [0])
        if bx or by:
            out['bytes'] = {'small': bx, 'large': by, 'kind': growth(bx, by, ratio, 4096)[1]}
        return out

    def worst(values):
        kinds = [v['kind'] for v in values.values() if v['kind'] in ORDER]
        return max(kinds, key=ORDER.index) if kinds else 'flat'

    for case, a in small_cases.items():
        b = large_cases.get(case)
        if b is None or a.get('status') != 'passed' or b.get('status') != 'passed':
            rows.append({'case': case, 'status': 'missing or failed at one size'}); flagged.append(case); continue
        expected = expected_class(case, cfg)
        counted = measures(a, b, size_ratio)
        if a.get('counts_variable'):
            counted = {k: v for k, v in counted.items() if k == 'bytes'}
        verdict = worst(counted)
        time_ratio, time_kind = growth(a.get('median_ms'), b.get('median_ms'), size_ratio, floor)
        row = {'case': case, 'expected': expected, 'verdict': verdict, 'counts': counted,
               'small_ms': a.get('median_ms'), 'large_ms': b.get('median_ms'), 'time_ratio': time_ratio,
               'time_kind': time_kind, 'timing_diagnostic': timing_diagnostic}
        p = project_cases.get(case)
        if p is not None and p.get('status') == 'passed':
            project_counts = measures(a, p, size(project) / size(small))
            row['project_verdict'] = worst(project_counts)
            row['project_counts'] = {k: v for k, v in project_counts.items() if v['kind'] != 'flat'}
            row['project_ms'] = p.get('median_ms')
        reasons = []
        if expected == 'flat' and verdict != 'flat':
            reasons.append('counts ' + verdict + ': ' + ', '.join(n for n, v in counted.items() if v['kind'] != 'flat'))
        if expected in ('linear-allowed', 'linear-informational') and verdict == 'superlinear':
            reasons.append('counts superlinear: ' + ', '.join(n for n, v in counted.items() if v['kind'] == 'superlinear'))
        if expected == 'flat' and row.get('project_verdict') not in (None, 'flat'):
            reasons.append('grows with project size: ' + ', '.join(row['project_counts']))
        row['flags'] = reasons
        if reasons:
            flagged.append(case)
        if not timing_diagnostic and ((expected == 'flat' and time_kind not in ('flat', None))
                                      or time_kind == 'superlinear'):
            timing_notes.append(case)
        rows.append(row)
    result = {'format': FORMAT + '-scaling', 'source': receipt['source_start']['commit'],
              'dirty': bool(receipt['source_start']['status']), 'small': small, 'large': large, 'project': project,
              'size_ratio': size_ratio, 'primary_signal': 'counts and response bytes (load-independent)',
              'timing_load_limit': load_limit, 'peak_load': loads, 'timing_diagnostic': timing_diagnostic,
              'fixture_paths': {n: {'typed_index': (profiles[n]['result'].get('typed_index') or {}).get('status'),
                                    'frozen': (profiles[n]['result'].get('publication') or {}).get('frozen')}
                                for n in (small, large) + ((project,) if project else ())},
              'flagged': flagged, 'timing_notes': timing_notes, 'rows': rows}
    output = Path(output)
    output.write_text(json.dumps(result, indent=2) + '\n')
    fmt = lambda v: '' if v is None else (f'{v:.1f}' if isinstance(v, float) else str(v))
    load_text = ', '.join(f'{n} {fmt(v)}' for n, v in loads.items())
    lines = [f"# Route scaling: {small} → {large} ({size_ratio:.0f}× epochs)" + (f", project-only {project}" if project else ''), '',
             f"Source `{result['source'][:12]}`{' (dirty)' if result['dirty'] else ''}. Verdicts use load-independent counts "
             f"(statements, copies, evaluations, reads, response bytes); ≈1× flat, ≈{size_ratio:.0f}× linear.", '',
             f"Peak load average: {load_text}. Timing is "
             + ('**diagnostic only** (load above ' + str(load_limit) + ').' if timing_diagnostic else 'valid (load at or under ' + str(load_limit) + ').'), '',
             'Fixture paths: ' + '; '.join(f"{n}: typed index {((profiles[n]['result'].get('typed_index') or {}).get('status'))}, "
                                          f"frozen publication {((profiles[n]['result'].get('publication') or {}).get('frozen'))}"
                                          for n in (small, large) + ((project,) if project else ())) + '.', '',
             f"Flagged by counts: {len(flagged)} case(s)." + (f" Timing notes: {', '.join(timing_notes)}." if timing_notes else ''), '',
             '| Case | Expected | Count verdict | Counts / bytes small→large | Project-only | ms small→large (ratio) | Flags |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for row in rows:
        if 'expected' not in row:
            lines.append(f"| {row['case']} | | | | | | {row['status']} |"); continue
        counts = '; '.join(f"{n} {fmt(v['small'])}→{fmt(v['large'])}" + ('' if v['kind'] == 'flat' else f" ({v['kind']})")
                           for n, v in row['counts'].items())
        project_text = row.get('project_verdict', '')
        timing = f"{fmt(row['small_ms'])}→{fmt(row['large_ms'])} ({fmt(row['time_ratio'])}×)" + (' diag' if row['timing_diagnostic'] else '')
        lines.append(f"| {row['case']} | {row['expected']} | {row['verdict']} | {counts} | {project_text} | {timing} | {'; '.join(row['flags'])} |")
    output.with_suffix('.md').write_text('\n'.join(lines) + '\n')
    return result


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
    scale = commands.add_parser('scaling', help='Per-case growth between two sizes in one run receipt')
    scale.add_argument('receipt', type=Path)
    scale.add_argument('--small', default='10k-protocol-10k')
    scale.add_argument('--large', default='200k-protocol-200k')
    scale.add_argument('--project', default='200k-protocol-10k', help="Same protocol as --small in a larger project; '' to skip")
    scale.add_argument('--output', type=Path, required=True, help='JSON path; a .md report is written beside it')
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
        elif args.command == 'scaling':
            result = scaling(args.receipt, args.small, args.large, args.project or None, args.output)
            print(json.dumps({'flagged': result['flagged'], 'report': str(args.output.with_suffix('.md'))}))
            return 2 if result['flagged'] else 0
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
