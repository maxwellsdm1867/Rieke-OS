"""CI scheduling for unchanged benchmark families and exact-source evidence.

Each family measures distinct source SHAs serially on one runner. Only identical
SHAs share raw receipts; the aggregate preserves their original provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ROLES = ('pinned', 'previous', 'candidate')


def plan_sources(pinned, previous, candidate):
    sources = dict(zip(ROLES, (pinned, previous, candidate)))
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value)
           for value in sources.values()):
        raise ValueError('Every benchmark source must be a full commit SHA')
    canonical = {}
    for role, sha in sources.items():
        canonical[role] = next(name for name in ('candidate', 'pinned', 'previous') if sources[name] == sha)
    return {'sources': sources, 'canonical': canonical,
            'order': list(dict.fromkeys(canonical[role] for role in ROLES))}


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def resolve_sources(root, pinned, previous, candidate, event):
    harness = git(root, 'rev-parse', 'HEAD')
    if not previous and event == 'workflow_dispatch':
        previous = git(root, 'rev-parse', 'HEAD^')
    elif previous == '0' * 40:
        previous = pinned
    requested = (pinned, previous, candidate or harness)
    resolved = []
    for sha in requested:
        if not re.fullmatch('[0-9a-fA-F]{40}', sha or ''):
            raise ValueError('Every benchmark source must be a full commit SHA')
        if subprocess.run(['git', '-C', str(root), 'cat-file', '-e', sha + '^{commit}'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            subprocess.run(['git', '-C', str(root), 'fetch', '--no-tags', 'origin', sha], check=True)
        resolved.append(git(root, 'rev-parse', sha + '^{commit}'))
    return {**plan_sources(*resolved), 'harness': harness, 'event': event,
            'run_id': os.environ.get('GITHUB_RUN_ID', ''),
            'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT', '')}


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_command(command, output, label):
    with (output / (label + '.log')).open('wb') as log:
        try:
            return subprocess.run(list(map(str, command)), cwd=ROOT, stdout=log,
                                  stderr=subprocess.STDOUT).returncode
        except OSError as error:
            log.write(str(error).encode())
            return 1


def prepare_sources(plan, worktrees, output, python, *, browser):
    paths = {}
    for role in plan['order']:
        sha = plan['sources'][role]
        path = ROOT if sha == plan['harness'] else worktrees / role
        if path != ROOT:
            # The scope job may have fetched an otherwise unreachable manual
            # ref. Git objects are not shared between the family runners.
            present = subprocess.run(['git', '-C', str(ROOT), 'cat-file', '-e', sha + '^{commit}'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if present.returncode and run_command(['git', 'fetch', '--no-tags', 'origin', sha],
                                                  output, role + '-fetch'):
                raise ValueError('Source fetch failed: ' + role)
            if run_command(['git', 'worktree', 'add', '--detach', path, sha], output, role + '-checkout'):
                raise ValueError('Source checkout failed: ' + role)
            if browser:
                for package in ('workspace-app', 'desktop'):
                    if run_command([python, '-B', ROOT / 'tools/benchmark_workflow.py', 'dependencies-match',
                                    path / package / 'package-lock.json', ROOT / package / 'package-lock.json'],
                                   output, role + '-' + package + '-dependencies'):
                        raise ValueError('Incomparable browser dependencies: ' + role)
                    (path / package / 'node_modules').symlink_to(ROOT / package / 'node_modules', target_is_directory=True)
                    exclude = Path(git(ROOT, 'rev-parse', '--git-path', 'info/exclude'))
                    if not exclude.is_absolute():
                        exclude = ROOT / exclude
                    with exclude.open('a') as stream:
                        stream.write('/' + package + '/node_modules\n')
        paths[role] = path
    return paths


def run_family(family, plan, output, worktrees, python):
    if family not in ('backend', 'browser'):
        raise ValueError('Unknown benchmark family')
    output, worktrees = Path(output).resolve(), Path(worktrees).resolve()
    output.mkdir(parents=True, exist_ok=True)
    worktrees.mkdir(parents=True, exist_ok=True)
    record = {'family': family, 'status': 'failed', 'plan': plan, 'commands': [], 'aliases': {}}
    prefix = '' if family == 'backend' else 'workflow-'
    runner = ROOT / ('tools/benchmark_everyday.py' if family == 'backend' else 'tools/benchmark_workflow.py')

    def run(label, command):
        code = run_command(command, output, label)
        record['commands'].append({'label': label, 'exit_code': code})
        return code == 0

    try:
        expected = plan_sources(*(plan['sources'][role] for role in ROLES))
        if any(plan.get(key) != value for key, value in expected.items()) or git(ROOT, 'rev-parse', 'HEAD') != plan['harness']:
            raise ValueError('Benchmark source plan or harness differs')
        write(output / (family + '-source-plan.json'), plan)
        setup_output = output / (family + '-setup')
        setup_output.mkdir()
        paths = prepare_sources(plan, worktrees, setup_output, python, browser=family == 'browser')
        if family == 'browser':
            for role in plan['order']:
                run('compatibility-' + role, [python, '-B', runner, 'run', '--smoke',
                    '--source-root', paths[role], '--output', output / ('compatibility-' + role)])
            if any(item['exit_code'] for item in record['commands']):
                raise ValueError('Browser preflight failed; million-row browser measurements were not started')
            # Core stays on the browser runner, outside the backend critical path.
            candidate = paths[plan['canonical']['candidate']]
            run('candidate-core', [python, '-B', candidate / 'tools/benchmark.py', 'run', '--output', output / 'core'])
        for role in plan['order']:
            command = [python, '-B', runner, 'run', '--source-root', paths[role], '--output', output / (prefix + role)]
            if family == 'browser':
                command += ['--protocol-epochs', '20000']
            run(prefix + role + '-run', command)
        for role in ROLES:
            canonical = plan['canonical'][role]
            origin, destination = output / (prefix + canonical), output / (prefix + role)
            if origin.is_dir() and origin != destination:
                shutil.copytree(origin, destination)
            receipt = origin / 'receipt.json'
            if receipt.is_file():
                record['aliases'][role] = {'canonical': canonical,
                    'source_receipt': str(receipt.relative_to(output)),
                    'receipt': str((destination / 'receipt.json').relative_to(output)),
                    'sha256': digest(receipt)}
        for role in ('pinned', 'previous'):
            run(prefix + role + '-compare', [python, '-B', runner, 'compare',
                output / (prefix + role) / 'receipt.json', output / (prefix + 'candidate') / 'receipt.json',
                '--output', output / (prefix + role + '-comparison.json')])
        if any(item['exit_code'] for item in record['commands']):
            raise ValueError('One or more benchmark commands failed; raw evidence retained')
        record['status'] = 'passed'
    except Exception as error:
        record['error'] = str(error)
    finally:
        write(output / (family + '-family.json'), record)
    return record


def aggregate(plan, output, backend_result, browser_result):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result = {'status': 'failed', 'plan': plan}
    try:
        expected = plan_sources(*(plan['sources'][role] for role in ROLES))
        if (any(plan.get(key) != value for key, value in expected.items())
                or git(ROOT, 'rev-parse', 'HEAD') != plan.get('harness')):
            raise ValueError('Aggregate source plan or harness differs')
        for variable, key in (('GITHUB_RUN_ID', 'run_id'), ('GITHUB_RUN_ATTEMPT', 'run_attempt')):
            if os.environ.get(variable) and plan.get(key) != os.environ[variable]:
                raise ValueError('Aggregate workflow run or attempt differs')
        if backend_result != 'success' or browser_result != 'success':
            raise ValueError('Missing, failed, cancelled or skipped benchmark family')
        for family, prefix in (('backend', ''), ('browser', 'workflow-')):
            record = json.loads((output / (family + '-family.json')).read_text())
            if record.get('status') != 'passed' or record.get('family') != family or record.get('plan') != plan:
                raise ValueError('Family evidence does not match the successful source plan')
            expected_labels = {prefix + role + '-run' for role in plan['order']}
            expected_labels.update(prefix + role + '-compare' for role in ('pinned', 'previous'))
            if family == 'browser':
                expected_labels.update('compatibility-' + role for role in plan['order'])
                expected_labels.add('candidate-core')
            commands = record.get('commands', [])
            if (len(commands) != len(expected_labels)
                    or {item.get('label') for item in commands} != expected_labels
                    or any(item.get('exit_code') != 0 for item in commands)):
                raise ValueError('Incomplete or failed family commands')
            for role in ROLES:
                path = output / (prefix + role) / 'receipt.json'
                receipt = json.loads(path.read_text())
                start = receipt.get('source_start', {})
                if (receipt.get('status') != 'passed' or start.get('commit') != plan['sources'][role]
                        or start.get('status') != '' or receipt.get('source_end') != start):
                    raise ValueError('Source receipt differs: ' + str(path))
                alias = record.get('aliases', {}).get(role, {})
                if (alias.get('canonical') != plan['canonical'][role]
                        or alias.get('receipt') != str(path.relative_to(output))
                        or alias.get('source_receipt') != prefix + plan['canonical'][role] + '/receipt.json'
                        or alias.get('sha256') != digest(path)
                        or alias.get('sha256') != digest(output / alias['source_receipt'])):
                    raise ValueError('Aliased receipt bytes or provenance differ')
            for role in ('pinned', 'previous'):
                comparison = json.loads((output / (prefix + role + '-comparison.json')).read_text())
                if (comparison.get('status') != 'passed' or comparison.get('review_required') != []
                        or comparison.get('candidate_receipt_sha256') != digest(output / (prefix + 'candidate') / 'receipt.json')
                        or comparison.get('baseline_receipt_sha256') != digest(output / (prefix + role) / 'receipt.json')):
                    raise ValueError('Missing, failed or mismatched comparison')
        core = json.loads((output / 'core/benchmark.json').read_text())
        if (core.get('validation_errors') != [] or core.get('fixture_cleaned') is not True
                or core.get('source_start', {}).get('commit') != plan['sources']['candidate']
                or core.get('source_start', {}).get('dirty') is not False
                or core.get('source_end') != core.get('source_start')):
            raise ValueError('Core benchmark did not pass')
        result['status'] = 'passed'
    except Exception as error:
        result['error'] = str(error)
    write(output / 'family-aggregation.json', result)
    write(output / 'source-plan.json', plan)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    resolve = commands.add_parser('resolve')
    resolve.add_argument('--pinned', required=True)
    resolve.add_argument('--previous', default='')
    resolve.add_argument('--candidate', default='')
    resolve.add_argument('--event', required=True)
    resolve.add_argument('--output', type=Path, required=True)
    resolve.add_argument('--github-output', type=Path)
    run = commands.add_parser('run')
    run.add_argument('--family', choices=['backend', 'browser'], required=True)
    run.add_argument('--plan', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--worktrees', type=Path, required=True)
    run.add_argument('--python', default=sys.executable)
    merge = commands.add_parser('aggregate')
    merge.add_argument('--plan', type=Path, required=True)
    merge.add_argument('--output', type=Path, required=True)
    merge.add_argument('--backend-result', required=True)
    merge.add_argument('--browser-result', required=True)
    args = parser.parse_args()
    if args.command == 'resolve':
        result = resolve_sources(ROOT, args.pinned, args.previous, args.candidate, args.event)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write(args.output, result)
        if args.github_output:
            with args.github_output.open('a') as stream:
                for name, sha in {**result['sources'], 'harness': result['harness']}.items():
                    stream.write(name + '=' + sha + '\n')
    else:
        plan = json.loads(args.plan.read_text())
        if args.command == 'run':
            result = run_family(args.family, plan, args.output, args.worktrees, args.python)
        else:
            result = aggregate(plan, args.output, args.backend_result, args.browser_result)
    print(json.dumps(result, indent=2))
    return 1 if result.get('status') == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
