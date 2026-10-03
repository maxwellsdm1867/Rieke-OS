#!/usr/bin/env python3
"""Repo-local fixed core benchmark runner, comparison and fail-closed release gate."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'rieke-core-benchmark'
NAV_TESTS = ['workspaceNavigation', 'inspectionNavigation', 'pageReadCache',
             'traceReadContext', 'navigationReadStrictMode', 'inspectorNavigationLifecycle']
DB_TESTS = ['test_workspace_sqlite', 'test_workspace_recipes', 'test_workspace_import_identities',
            'test_workspace_epoch_page_performance']


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args, root=ROOT):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()


def registry(root=ROOT):
    return json.loads((root / 'benchmarks/registry.json').read_text())


def committed_bytes(revision, name, root=ROOT):
    return subprocess.check_output(['git', '-C', str(root), 'show', f'{revision}:{name}'], stderr=subprocess.DEVNULL)


def resolve_commit(value, root=ROOT):
    try:
        return git('rev-parse', '--verify', '--end-of-options', str(value) + '^{commit}', root=root)
    except subprocess.CalledProcessError as exc:
        raise ValueError('Expected commit cannot be resolved in this repository') from exc


def suite_identity(root=ROOT, revision=None):
    paths = ['tools/benchmark.py', 'benchmarks/requirements-py311.txt', 'benchmarks/registry.json', 'benchmarks/receipt.schema.json', 'benchmarks/database.py',
             'workspace-app/src/benchmarkNavigation.mjs', 'workspace-app/isolatedViteCache.js',
             'tools/metadata_qualification/core_adapter.py', 'tools/metadata_qualification/truth.py',
             'tools/metadata_qualification/native-truth.json', 'tools/metadata_qualification/native-truth.seal.json']
    paths += [f'workspace-app/src/{name}.test.js' for name in NAV_TESTS]
    paths += [f'python/tests/{name}.py' for name in DB_TESTS]
    paths += (git('ls-tree', '-r', '--name-only', revision, '--', 'workspace-app/src/test-support', root=root).splitlines() if revision else [str(p.relative_to(root)) for p in (root / 'workspace-app/src/test-support').rglob('*') if p.is_file()])
    # Test fixture helpers transitively define the scientific data being exercised.
    paths += ['python/tests/test_workspace_api.py', 'python/tests/test_workspace_curation.py',
              'python/tests/test_workspace_matlab.py']
    files = {name: sha(committed_bytes(revision, name, root) if revision else (root / name).read_bytes()) for name in sorted(set(paths))}
    return {'sha256': sha(canonical(files)), 'files': files}


def source(root=ROOT):
    release = json.loads((root / 'rieke-release.json').read_text())
    status = git('status', '--porcelain', '--untracked-files=all', root=root)
    versions = {}
    for name, symbol in [('workspace_disk_index.py', 'FORMAT'), ('workspace_typed_index.py', 'FORMAT'), ('workspace_sqlite.py', 'SCHEMA_VERSION')]:
        match = re.search(r'^' + symbol + r'\s*=\s*(\d+)', (root / 'python' / name).read_text(), re.M)
        if not match: raise ValueError(f'Missing schema version: {name}')
        versions[name] = int(match[1])
    return {'schema_versions': versions, 'commit': git('rev-parse', 'HEAD', root=root), 'tree': git('rev-parse', 'HEAD^{tree}', root=root),
            'dirty': bool(status), 'status_sha256': sha(status.encode()),
            'application_version': release['version'], 'database_compatibility': release['database_compatibility'],
            'workspace_formats': release['workspace_formats'],
            'schema_sources': {name: sha((root / 'python' / name).read_bytes()) for name in
                               ['workspace_disk_index.py', 'workspace_typed_index.py', 'workspace_sqlite.py']}}


def committed_source(commit, root=ROOT):
    """Independent identity reconstructed from Git objects, never receipt fields."""
    commit = resolve_commit(commit, root)
    release = json.loads(committed_bytes(commit, 'rieke-release.json', root))
    schemas, versions = {}, {}
    for name, symbol in [('workspace_disk_index.py', 'FORMAT'), ('workspace_typed_index.py', 'FORMAT'), ('workspace_sqlite.py', 'SCHEMA_VERSION')]:
        raw = committed_bytes(commit, 'python/' + name, root)
        match = re.search(r'^' + symbol + r'\s*=\s*(\d+)', raw.decode(), re.M)
        if not match: raise ValueError(f'Missing committed schema version: {name}')
        versions[name], schemas[name] = int(match[1]), sha(raw)
    return {'commit': commit, 'tree': git('rev-parse', commit + '^{tree}', root=root),
            'dirty': False, 'status_sha256': sha(b''), 'schema_versions': versions,
            'schema_sources': schemas, 'application_version': release['version'],
            'database_compatibility': release['database_compatibility'],
            'workspace_formats': release['workspace_formats']}


def provenance_errors(receipt, expected_commit, root=ROOT):
    try:
        trusted = committed_source(expected_commit, root)
        errors = [f'Committed provenance differs: {key}' for key in ('source_start', 'source_end') if receipt.get(key) != trusted]
        if receipt.get('suite') != suite_identity(root, trusted['commit']):
            errors.append('Suite differs from committed benchmark source')
        if receipt.get('fixture', {}).get('sha256') != sha(committed_bytes(trusted['commit'], 'tools/metadata_qualification/native-truth.json', root)):
            errors.append('Fixture differs from committed frozen truth')
        return errors
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as exc:
        return [f'Cannot verify committed provenance: {exc}']


def hardware_errors(env):
    unknown = {'', 'unknown', 'unavailable', 'missing', 'n/a', 'none', 'null'}
    errors = []
    if not isinstance(env.get('cpu'), str) or env['cpu'].strip().lower() in unknown:
        errors.append('CPU hardware is unknown; diagnostic only')
    if type(env.get('logical_cpus')) is not int or env['logical_cpus'] <= 0:
        errors.append('CPU count is unknown; diagnostic only')
    memory = env.get('memory_bytes')
    if type(memory) not in (str, int) or not str(memory).isdigit() or int(memory) <= 0:
        errors.append('Memory hardware is unknown; diagnostic only')
    return errors


def environment():
    def command(*args):
        try: return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError): return 'unavailable'
    memory = command('/usr/sbin/sysctl', '-n', 'hw.memsize') if sys.platform == 'darwin' else str(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES'))
    cpu = command('/usr/sbin/sysctl', '-n', 'machdep.cpu.brand_string') if sys.platform == 'darwin' else platform.processor()
    packages = {}
    for name in ('numpy', 'scipy', 'h5py', 'flask', 'datajoint'):
        try: packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name] = 'missing'
    return {'python_packages': packages, 'os': platform.platform(), 'architecture': platform.machine(), 'cpu': cpu,
            'logical_cpus': os.cpu_count(), 'memory_bytes': memory,
            'machine_id': sha(platform.node().encode())[:16], 'python': platform.python_version(),
            'sqlite': sqlite3.sqlite_version, 'node': command('node', '--version'),
            'frontend_packages': command('node', '-p', "JSON.stringify(Object.fromEntries(['react','react-dom','react-test-renderer','vite','jsdom'].map(n=>[n,require(process.cwd()+'/workspace-app/node_modules/'+n+'/package.json').version])))"),
            'dependencies': {name: sha((ROOT / name).read_bytes()) for name in ['workspace-app/package-lock.json']}}


def execute(command, log, timeout=180):
    """Serial owned subprocess; timeout kills only its new process group."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT / 'python') + os.pathsep + str(ROOT / 'python/tests'))
    started = time.perf_counter()
    with log.open('w') as stream:
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = child.wait(timeout=timeout)
        except BaseException:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise
    if code:
        raise RuntimeError(f'Exit {code}; see {log.name}')
    return (time.perf_counter() - started) * 1000


def numeric_samples(value, count):
    return (isinstance(value, list) and len(value) == count and
            all(type(n) in (int, float) and math.isfinite(n) and n >= 0 for n in value))


def validate(receipt, reg=None):
    """Do not trust a top-level green status, omitted cases, skipped tests or NaN."""
    reg = reg or registry()
    errors = []
    if receipt.get('format') != FORMAT or receipt.get('schema_version') != 1:
        return ['Unsupported receipt format/schema']
    for key in ('source_start', 'source_end', 'environment', 'suite', 'fixture', 'method'):
        if not isinstance(receipt.get(key), dict): errors.append(f'Missing {key}')
    if errors: return errors
    try:
        stamp = dt.datetime.fromisoformat(receipt.get('created_at', ''))
        if stamp.tzinfo is None: raise ValueError('timezone missing')
    except (ValueError, TypeError): errors.append('Missing/invalid timestamp')
    elapsed = receipt.get('wall_seconds')
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0: errors.append('Invalid wall runtime')
    if receipt.get('error'): errors.append('Runner reported failure')
    for key in ('source_start', 'source_end'):
        value = receipt[key]
        if not re.fullmatch(r'[a-f0-9]{40}', str(value.get('commit', ''))): errors.append(f'Invalid {key} commit')
        if not re.fullmatch(r'[a-f0-9]{40}', str(value.get('tree', ''))): errors.append(f'Missing {key} tree')
        if not re.fullmatch(r'[a-f0-9]{64}', str(value.get('status_sha256', ''))): errors.append(f'Missing {key} status digest')
        if not isinstance(value.get('workspace_formats'), list) or type(value.get('database_compatibility')) is not int: errors.append(f'Missing {key} format compatibility')
        if type(value.get('dirty')) is not bool: errors.append(f'Missing {key} dirty state')
        if not value.get('application_version') or not value.get('schema_sources') or not value.get('schema_versions'): errors.append(f'Incomplete {key} versions')
    if receipt['source_start'] != receipt['source_end']: errors.append('Source changed during run')
    if receipt.get('suite_version') != reg['suite_version'] or receipt['method'] != reg['method']:
        errors.append('Suite or sample method differs')
    if receipt['fixture'].get('version') != reg['fixture_version']: errors.append('Fixture version differs')
    if not re.fullmatch(r'[a-f0-9]{64}', str(receipt['suite'].get('sha256', ''))): errors.append('Missing suite digest')
    if not re.fullmatch(r'[a-f0-9]{64}', str(receipt['fixture'].get('sha256', ''))): errors.append('Missing fixture digest')
    if any(not receipt['environment'].get(k) for k in ('os','architecture','cpu','logical_cpus','memory_bytes','machine_id','python','sqlite','node','dependencies','python_packages','frontend_packages')):
        errors.append('Incomplete environment/hardware')
    if receipt.get('samples') != reg['samples']: errors.append('Sample count differs')
    if receipt.get('fixture_cleaned') is not True: errors.append('Fixture cleanup unconfirmed')
    rows = receipt.get('cases', [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows): return errors + ['Malformed cases']
    expected = {case['id']: case for case in reg['cases']}
    actual = {case.get('id'): case for case in rows}
    if len(actual) != len(rows) or set(actual) != set(expected): errors.append('Missing, extra or duplicate core cases')
    for case_id, definition in expected.items():
        row = actual.get(case_id, {})
        if row.get('status') != 'passed': errors.append(f'{case_id}: failed/incomplete')
        if definition['kind'] == 'latency':
            metrics = row.get('metrics', {})
            if not isinstance(metrics, dict):
                errors.append(f'{case_id}: malformed metrics'); continue
            if set(metrics) != set(definition['metrics']): errors.append(f'{case_id}: metric set differs')
            for name in definition['metrics']:
                if not numeric_samples(metrics.get(name), reg['samples']): errors.append(f'{case_id}.{name}: invalid samples')
        elif type(row.get('tests')) is not int or row['tests'] <= 0 or row.get('skipped') != 0:
            errors.append(f'{case_id}: no complete correctness evidence')
    if receipt.get('release_requirements') != reg['release_requirements'] or receipt.get('gaps') != reg['gaps']:
        errors.append('Coverage ledger differs')
    return errors


def gate(receipt, *, expected_commit, expected_version, release=False, root=ROOT):
    errors = validate(receipt, registry(root))
    errors += provenance_errors(receipt, expected_commit, root)
    errors += hardware_errors(receipt.get('environment', {}))
    if errors: raise ValueError('; '.join(errors))
    identity = receipt['source_start']
    if identity['dirty'] or receipt['source_end']['dirty']: errors.append('Dirty-source receipts cannot qualify')
    if identity['commit'] != resolve_commit(expected_commit, root): errors.append('Stale/wrong candidate commit')
    if identity['application_version'] != expected_version: errors.append('Wrong application version')
    if receipt['suite'] != suite_identity(root): errors.append('Stale/changed benchmark harness or fixtures')
    if receipt['fixture']['sha256'] != sha((root / 'tools/metadata_qualification/native-truth.json').read_bytes()): errors.append('Wrong frozen fixture seal')
    if release:
        for requirement in receipt['release_requirements']:
            if requirement.get('status') != 'passed': errors.append(f"Release requirement incomplete: {requirement['id']}")
    if errors: raise ValueError('; '.join(errors))
    return {'core_execution': 'passed', 'release_qualified': release,
            'performance_budget': 'uncalibrated', 'source_commit': identity['commit']}


def compare(before, after, root=ROOT):
    reasons = [f'{label}: {error}' for label, receipt in [('baseline', before), ('candidate', after)] for error in validate(receipt)]
    for receipt in (before, after):
        reasons += hardware_errors(receipt.get('environment', {}))
        reasons += provenance_errors(receipt, receipt.get('source_start', {}).get('commit', ''), root)
        if receipt.get('source_start', {}).get('dirty'): reasons.append('Dirty source is not a comparable baseline/candidate')
    for key in ('suite_version', 'suite', 'fixture', 'method', 'samples', 'environment'):
        if before.get(key) != after.get(key): reasons.append(f'Noncomparable {key}')
    for key in ('database_compatibility', 'workspace_formats', 'schema_versions'):
        if before.get('source_start', {}).get(key) != after.get('source_start', {}).get(key): reasons.append(f'Noncomparable {key}')
    if reasons: return {'comparable': False, 'reasons': reasons, 'changes': []}
    previous = {row['id']: row for row in before['cases']}
    changes = []
    for row in after['cases']:
        for metric, values in row.get('metrics', {}).items():
            left, right = statistics.median(previous[row['id']]['metrics'][metric]), statistics.median(values)
            changes.append({'id': row['id'], 'metric': metric, 'baseline_median_ms': left,
                            'candidate_median_ms': right, 'delta_ms': right-left,
                            'delta_percent': ((right/left)-1)*100 if left else None})
    return {'comparable': True, 'reasons': [], 'changes': changes,
            'interpretation': 'Observed differences only; four samples do not establish significance or a calibrated budget.'}


def report(receipt, comparison=None):
    errors = validate(receipt)
    lines = ['# Core benchmark report', '', f"Commit: `{receipt.get('source_start', {}).get('commit', 'unknown')}`",
             f"Application: {receipt.get('source_start', {}).get('application_version', 'unknown')}; suite: {receipt.get('suite_version')}",
             f"Core execution: {'INCOMPLETE/FAILED' if errors else 'passed'}; release qualification: INCOMPLETE.",
             f"Hardware qualification: {'diagnostic only' if hardware_errors(receipt.get('environment', {})) else 'identified; provenance gate still required'}.",
             f"Wall runtime: {receipt.get('wall_seconds', 0):.3f} s. Performance budget: uncalibrated.",
             '', 'These are actual operation timings; correctness-test duration is listed separately. Mounted UI is not native browser paint.', '',
             '| Case / metric | Median ms | Raw samples ms |', '|---|---:|---|']
    for row in receipt.get('cases', []):
        for name, values in row.get('metrics', {}).items():
            if numeric_samples(values, receipt.get('samples')):
                lines.append(f"| {row['id']} / {name} | {statistics.median(values):.3f} | {', '.join(f'{v:.3f}' for v in values)} |")
        if 'execution_ms' in row: lines.append(f"| {row['id']} / correctness execution only | {row['execution_ms']:.3f} | {row.get('tests', 0)} tests |")
    lines += ['', '## Coverage and release blockers', '']
    lines += [f"- {item['id']}: {item['reason']}" for item in receipt.get('release_requirements', []) + receipt.get('gaps', [])]
    if errors: lines += ['', '## Receipt errors', '', *[f'- {e}' for e in errors]]
    if comparison is not None:
        lines += ['', '## Comparison', '', f"Comparable: {comparison['comparable']}"]
        lines += [f'- {reason}' for reason in comparison['reasons']]
        if comparison['comparable']:
            lines += ['', '| Case / metric | Baseline ms | Candidate ms | Delta ms |', '|---|---:|---:|---:|']
            lines += [f"| {r['id']} / {r['metric']} | {r['baseline_median_ms']:.3f} | {r['candidate_median_ms']:.3f} | {r['delta_ms']:+.3f} |" for r in comparison['changes']]
            lines += ['', comparison['interpretation']]
    lines += ['', '## Addressed changes and bottlenecks', '',
              'Review operation medians and comparable deltas above. Link reviewed changes in the release notes; no causal improvement is inferred from a timing difference alone.', '']
    return '\n'.join(lines)


def run(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)  # Preserve earlier evidence; never overwrite a run.
    reg = registry()
    start = time.perf_counter()
    fixture_path = ROOT / 'tools/metadata_qualification/native-truth.json'
    receipt = {'format': FORMAT, 'schema_version': 1, 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
               'suite_version': reg['suite_version'], 'suite': suite_identity(), 'fixture': {'version': reg['fixture_version'], 'sha256': sha(fixture_path.read_bytes())},
               'source_start': source(), 'environment': environment(), 'load_average_start': list(os.getloadavg()), 'method': reg['method'], 'samples': reg['samples'],
               'cases': [], 'release_requirements': reg['release_requirements'], 'gaps': reg['gaps'], 'fixture_cleaned': False}
    try:
        for name, command in [('database', [sys.executable, '-B', str(ROOT / 'benchmarks/database.py')]),
                              ('frontend', ['node', str(ROOT / 'workspace-app/src/benchmarkNavigation.mjs')])]:
            result_path = output / f'{name}.json'
            duration = execute(command + [str(reg['samples']), str(result_path)], output / f'{name}.log')
            result = json.loads(result_path.read_text())
            if result.get('fixture_cleaned') is not True: raise RuntimeError(f'{name} cleanup unconfirmed')
            receipt['cases'].extend(result['cases'])
            receipt[name] = {k:v for k,v in result.items() if k != 'cases'}
            receipt[name]['execution_ms'] = duration
        node_ms = execute(['node', '--test', '--test-reporter=tap', '--test-concurrency=1', *[str(ROOT / f'workspace-app/src/{n}.test.js') for n in NAV_TESTS]], output / 'frontend-tests.log')
        log = (output / 'frontend-tests.log').read_text()
        count = re.search(r'^# tests (\d+)$', log, re.M)
        skipped = re.search(r'^# skipped (\d+)$', log, re.M)
        if not count or not skipped: raise RuntimeError('Missing Node test summary')
        for label in ('fail', 'cancelled', 'todo'):
            summary = re.search(r'^# ' + label + r' (\d+)$', log, re.M)
            if not summary or int(summary[1]): raise RuntimeError(f'Incomplete Node correctness: {label}')
        receipt['cases'].append({'id':'correctness.navigation', 'status':'passed', 'tests':int(count[1]), 'skipped':int(skipped[1]), 'execution_ms':node_ms})
        script = "import unittest,sys,json; suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:]); result=unittest.TextTestRunner(verbosity=2).run(suite); open(sys.argv[1],'w').write(json.dumps({'tests':result.testsRun,'skipped':len(result.skipped)})); sys.exit(0 if result.wasSuccessful() and result.testsRun and not result.skipped else 1)"
        stats = output / 'database-tests.json'
        db_ms = execute([sys.executable, '-B', '-c', script, str(stats), *DB_TESTS], output / 'database-tests.log')
        receipt['cases'].append({'id':'correctness.frozen_export_tags_ingest', 'status':'passed', **json.loads(stats.read_text()), 'execution_ms':db_ms})
        receipt['fixture_cleaned'] = True
    except Exception as exc:
        receipt['error'] = str(exc)
    finally:
        receipt['source_end'] = source()
        receipt['load_average_end'] = list(os.getloadavg())
        receipt['wall_seconds'] = time.perf_counter() - start
        receipt['logs'] = {p.name: sha(p.read_bytes()) for p in output.glob('*.log')}
        receipt['validation_errors'] = validate(receipt)
        (output / 'benchmark.json').write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
        (output / 'benchmark.md').write_text(report(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    running = commands.add_parser('run'); running.add_argument('--output', type=Path, required=True)
    checking = commands.add_parser('gate'); checking.add_argument('receipt', type=Path); checking.add_argument('--commit', required=True); checking.add_argument('--app-version', required=True); checking.add_argument('--release', action='store_true')
    comparison = commands.add_parser('compare'); comparison.add_argument('baseline', type=Path); comparison.add_argument('candidate', type=Path); comparison.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'run':
            receipt = run(args.output)
            print(json.dumps({'receipt':str(args.output / 'benchmark.json'), 'errors':receipt['validation_errors'], 'wall_seconds':receipt['wall_seconds']}))
            return bool(receipt['validation_errors'])
        if args.command == 'gate':
            print(json.dumps(gate(json.loads(args.receipt.read_text()), expected_commit=args.commit, expected_version=args.app_version, release=args.release)))
        else:
            before, after = json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text())
            result = compare(before, after)
            args.output.write_text(report(after, result))
            args.output.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n')
            return not result['comparable']
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
