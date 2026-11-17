"""Reuse a successful PR integration verdict only for its identical merged tree."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from zipfile import BadZipFile

if __package__:
    from .desktop_source_ci import api, artifact, require_jobs, successful
else:
    from desktop_source_ci import api, artifact, require_jobs, successful


FORMAT = 'disco-integration-pr-proof-v1'
VERDICT = 'Disco integration verdict'
PROOF_FILE = 'integration-pr-proof.json'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value), 'Invalid commit or tree identity')
    return value


def positive(value):
    require(type(value) is int and value > 0, 'Invalid GitHub identifier')
    return value


def workflow_name(env):
    prefix = env['GITHUB_REPOSITORY'] + '/.github/workflows/'
    workflow, _, ref = env['GITHUB_WORKFLOW_REF'].partition('@')
    require(ref and workflow.startswith(prefix), 'Workflow belongs to another repository')
    name = workflow[len(prefix):]
    require(re.fullmatch(r'[A-Za-z0-9_-]+\.ya?ml', name), 'Unexpected workflow path')
    return name


def checkout(env):
    def git(*args):
        return subprocess.check_output(['git', *args], text=True).strip()
    expected = sha(env['GITHUB_SHA'])
    require(git('rev-parse', 'HEAD') == expected and not git('status', '--porcelain'),
            'Checkout does not match the clean event revision')
    # cat-file retains the real parent headers even in a depth-one checkout.
    tree, *parents = [line.split(' ', 1)[1] for line in git('cat-file', '-p', expected).split('\n\n', 1)[0].splitlines()
                      if line.startswith(('tree ', 'parent '))]
    return sha(tree), [sha(parent) for parent in parents]


def record(env, event):
    repo, pr = env['GITHUB_REPOSITORY'], event['pull_request']
    number = positive(pr['number'])
    require(env['GITHUB_EVENT_NAME'] == 'pull_request' and env['GITHUB_REF'] == f'refs/pull/{number}/merge',
            'Requires a pull request merge checkout')
    require(event['repository']['full_name'] == pr['base']['repo']['full_name'] == pr['head']['repo']['full_name'] == repo,
            'Requires a same-repository pull request')
    tree, parents = checkout(env)
    base, head = sha(pr['base']['sha']), sha(pr['head']['sha'])
    require(parents == [base, head], 'Checkout parents differ from the PR event')
    return {'format': FORMAT, 'repository': repo, 'workflow': workflow_name(env),
            'pull_request': number, 'base_ref': pr['base']['ref'], 'base': base, 'head': head,
            'tested_commit': sha(env['GITHUB_SHA']), 'tested_tree': tree,
            'run_id': positive(int(env['GITHUB_RUN_ID'])), 'run_attempt': positive(int(env['GITHUB_RUN_ATTEMPT']))}


def check(env, event):
    require(env['GITHUB_EVENT_NAME'] == 'push' and env['GITHUB_REF'] == 'refs/heads/main',
            'Only automatic main pushes reuse PR evidence')
    repo, workflow = env['GITHUB_REPOSITORY'], workflow_name(env)
    require(event['ref'] == env['GITHUB_REF'] and event['repository']['full_name'] == repo
            and event['forced'] is False and event['deleted'] is False,
            'Requires an ordinary main push from this repository')
    before, after = sha(event['before']), sha(event['after'])
    require(before != '0' * 40 and after == env['GITHUB_SHA'], 'Push revision differs')
    tree, parents = checkout(env)
    require(parents and parents[0] == before, 'Push includes additional commits or a different base')
    base_url = f'repos/{repo}'
    pulls = api(f'{base_url}/commits/{after}/pulls?per_page=100')
    merged = [pr for pr in pulls if pr.get('state') == 'closed' and pr.get('merged_at')
              and pr.get('merge_commit_sha') == after and pr['base']['ref'] == 'main']
    require(len(merged) == 1, 'No unique merged PR for this main revision')
    pr = merged[0]
    number, head = positive(pr['number']), sha(pr['head']['sha'])
    require(pr['base']['repo']['full_name'] == pr['head']['repo']['full_name'] == repo
            and pr['base']['sha'] == before and parents in ([before], [before, head]),
            'Merged PR repository, base or head differs')

    runs_url = f'{base_url}/actions/workflows/{workflow}/runs?event=pull_request&head_sha={head}&per_page=1'
    def latest_run():
        rows = api(runs_url)['workflow_runs']
        require(len(rows) == 1, 'Missing PR integration workflow run')
        run = rows[0]
        successful(run, workflow, head)
        require(run['event'] == 'pull_request' and run['repository']['full_name'] == run['head_repository']['full_name'] == repo,
                'PR workflow run originates from another repository or event')
        return run

    run = latest_run()
    run_id, attempt = positive(run['id']), positive(run['run_attempt'])
    require_jobs(repo, run, [VERDICT])
    # Treat artifact JSON as data only. The artifact reader bounds archive and
    # member sizes, verifies transport identity and never extracts remote paths.
    proof = artifact(repo, run, f'integration-pr-proof-{run_id}-{attempt}', PROOF_FILE)
    tested = sha(proof['tested_commit'])
    # The Actions API reports the synthetic PR ref and resolved SHA of each
    # local reusable workflow even when run.pull_requests is empty after merge.
    # This corroborates the receipt against the jobs GitHub actually dispatched.
    for child in ('workspace-ci.yml', 'everyday-million.yml'):
        path = f'{repo}/.github/workflows/{child}'
        refs = [row for row in run['referenced_workflows'] if row['path'].partition('@')[0] == path]
        require(len(refs) == 1 and refs[0]['ref'] == f'refs/pull/{number}/merge' and refs[0]['sha'] == tested,
                'Source or performance workflow did not test the recorded PR merge revision')
    expected = {'format': FORMAT, 'repository': repo, 'workflow': workflow, 'pull_request': number,
                'base_ref': 'main', 'base': before, 'head': head, 'tested_commit': tested,
                'tested_tree': tree, 'run_id': run_id, 'run_attempt': attempt}
    require(proof == expected, 'PR verdict receipt does not match this push and workflow attempt')
    tested_commit = api(f'{base_url}/git/commits/{tested}')
    require(tested_commit['sha'] == tested and tested_commit['tree']['sha'] == tree
            and [p['sha'] for p in tested_commit['parents']] == [before, head],
            'GitHub does not confirm the tested merge tree and both parents')
    current = latest_run()
    require(current['id'] == run_id and current['run_attempt'] == attempt, 'PR run or attempt was superseded')
    return {'reused': True, 'merged_commit': after, 'proof': proof,
            'run_url': f'https://github.com/{repo}/actions/runs/{run_id}/attempts/{attempt}'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['record', 'check'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    try:
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        result = (record if args.action == 'record' else check)(os.environ, event)
    except (KeyError, IndexError, TypeError, ValueError, OSError, RuntimeError, subprocess.SubprocessError, BadZipFile) as exc:
        # A missing API permission, expired artifact or an ambiguous identity
        # costs a normal integration run. It cannot waive verification.
        result = {'reused': False, 'reason': str(exc)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    if args.github_output:
        with args.github_output.open('a') as out:
            out.write(f"reused={str(result.get('reused', False)).lower()}\nrun_url={result.get('run_url', '')}\n")
    print(json.dumps(result))


if __name__ == '__main__':
    main()
