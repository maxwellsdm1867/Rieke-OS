"""List current unsuccessful Disco integration runs for the repair automation."""
import json
import subprocess
from urllib.parse import urlencode

REPOSITORY = 'maxwellsdm1867/Rieke-OS'
WORKFLOW = 'integration.yml'
BLOCKED = {'failure', 'timed_out', 'action_required', 'startup_failure'}


def get(path):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPOSITORY}/{path}'], text=True))


def open_owner_prs():
    # Paginate so a busy repository cannot hide an older, still-open PR.
    pages = json.loads(subprocess.check_output([
        'gh', 'api', '--paginate', '--slurp', f'repos/{REPOSITORY}/pulls?state=open&base=main&per_page=100'
    ], text=True))
    return [pr for page in pages for pr in page
            if pr['head']['repo'] and pr['head']['repo']['full_name'] == REPOSITORY
            and pr['user']['login'].casefold() == REPOSITORY.split('/')[0].casefold()]


def pr_numbers(run, commit, branch):
    associated = {pr['number'] for pr in run.get('pull_requests', [])}
    for child in run.get('referenced_workflows', []):
        ref = child.get('ref', '').split('/')
        if len(ref) == 4 and ref[:2] == ['refs', 'pull'] and ref[2].isdigit() and ref[3] == 'merge':
            associated.add(int(ref[2]))
    if associated:
        return associated
    # A failed plan may have started no reusable jobs. Attribute it to a PR
    # that was open for this branch when GitHub created the run.
    rows = get(f'commits/{commit}/pulls?per_page=100')
    if len(rows) >= 100:
        raise ValueError('Cannot attribute this failure to a unique PR')
    return {pr['number'] for pr in rows if pr['created_at'] <= run['created_at']
            and (not pr['closed_at'] or pr['closed_at'] >= run['created_at'])
            and pr['head']['ref'] == branch and pr['head']['sha'] == commit
            and (pr['head']['repo'] or {}).get('full_name') == REPOSITORY}


def incident(branch, commit, event, number=None):
    query = urlencode(dict(event=event, head_sha=commit, branch=branch, per_page=100 if number else 1))
    runs = get(f'actions/workflows/{WORKFLOW}/runs?{query}')['workflow_runs']
    for run in runs:
        if (run['head_sha'] != commit or run['head_branch'] != branch or run['event'] != event
                or run['repository']['full_name'] != REPOSITORY
                or (run.get('head_repository') or {}).get('full_name') != REPOSITORY
                or run['path'] != '.github/workflows/' + WORKFLOW):
            continue
        if number is not None and pr_numbers(run, commit, branch) != {number}:
            continue
        # The newest applicable run supersedes all older attempts, even while
        # it is running. Cancelled and successful runs require no repair.
        if run['status'] != 'completed' or run['conclusion'] not in BLOCKED:
            return None
        return {'branch': branch, 'commit': commit, 'pr': number, 'run_id': run['id'],
                'attempt': run['run_attempt'], 'url': run['html_url'], 'conclusion': run['conclusion']}
    if len(runs) >= 100:
        raise ValueError('Too many integration runs to identify the current PR verdict')
    return None


def current():
    main = get('branches/main')['commit']['sha']
    candidates = [incident('main', main, 'push')]
    for pr in open_owner_prs():
        candidates.append(incident(pr['head']['ref'], pr['head']['sha'], 'pull_request', pr['number']))
    return [row for row in candidates if row is not None]


if __name__ == '__main__':
    print(json.dumps(current(), indent=2))
