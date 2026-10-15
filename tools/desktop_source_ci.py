"""Read-only publication gate for exact-source GitHub regression evidence."""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import re
import subprocess
import zipfile
import tempfile
from pathlib import Path


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


SMALL_ARCHIVE_LIMIT = 16 * 1024 * 1024
DIAGNOSTIC_ARCHIVE_LIMIT = 256 * 1024 * 1024
MEMBER_LIMIT = 8 * 1024 * 1024
_ARTIFACT_CACHE = contextvars.ContextVar('publication_artifact_cache', default=None)


@contextlib.contextmanager
def _artifact_scope():
    # Each publication check obtains fresh evidence; no cache survives a recheck.
    with tempfile.TemporaryDirectory(prefix='disco-ci-proof-') as folder:
        token = _ARTIFACT_CACHE.set((Path(folder), {}))
        try:
            yield
        finally:
            _ARTIFACT_CACHE.reset(token)


def _download_archive(repository, row, target, limit):
    declared = row.get('size_in_bytes')
    expected = row.get('digest')
    if type(declared) is not int or not 0 < declared <= limit:
        raise ValueError('CI proof artifact exceeds its transport bound or lacks a valid size')
    if expected is not None and (not isinstance(expected, str) or
            not re.fullmatch(r'sha256:[0-9a-f]{64}', expected)):
        raise ValueError('Malformed CI artifact digest')
    size, digest = 0, hashlib.sha256()
    with tempfile.TemporaryFile() as errors, target.open('wb') as output:
        process = subprocess.Popen(['gh', 'api',
            f'repos/{repository}/actions/artifacts/{row["id"]}/zip'],
            stdout=subprocess.PIPE, stderr=errors)
        try:
            while True:
                block = process.stdout.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > limit:
                    raise ValueError('CI proof artifact exceeds its actual-byte transport bound')
                digest.update(block)
                output.write(block)
            if process.wait() != 0:
                raise ValueError('CI proof artifact download failed')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
    if size != declared:
        raise ValueError('CI proof artifact size differs from its declared bytes')
    if expected is not None and expected != 'sha256:' + digest.hexdigest():
        raise ValueError('CI proof artifact digest differs')


def artifact(repository, run, name, filename, *, with_digest=False):
    if _ARTIFACT_CACHE.get() is None:
        with _artifact_scope():
            return artifact(repository, run, name, filename, with_digest=with_digest)
    rows = api(f'repos/{repository}/actions/runs/{run["id"]}/artifacts?per_page=100')['artifacts']
    found = [row for row in rows if row['name'] == name and not row['expired']]
    if len(found) != 1:
        raise ValueError(f'Missing or ambiguous CI artifact: {name}')
    # Only the exact aggregate diagnostic family receives the larger disk budget.
    diagnostic = name == f'everyday-million-{run["id"]}-{run.get("run_attempt")}'
    limit = DIAGNOSTIC_ARCHIVE_LIMIT if diagnostic else SMALL_ARCHIVE_LIMIT
    row = found[0]
    folder, cache = _ARTIFACT_CACHE.get()
    key = (repository, row['id'], row.get('size_in_bytes'), row.get('digest'), limit)
    if key not in cache:
        target = folder / f'archive-{len(cache)}.zip'
        _download_archive(repository, row, target, limit)
        cache[key] = target
    # Read only one unique explicitly named member; never extract remote paths.
    with zipfile.ZipFile(cache[key]) as archive:
        members = [member for member in archive.infolist() if member.filename == filename]
        if len(members) != 1:
            raise ValueError('Missing or duplicate CI proof member')
        if members[0].file_size > MEMBER_LIMIT:
            raise ValueError('CI proof member exceeds its metadata bound')
        with archive.open(members[0]) as stream:
            raw = stream.read(MEMBER_LIMIT + 1)
        if len(raw) > MEMBER_LIMIT:
            raise ValueError('CI proof member exceeds its actual-byte metadata bound')
        parsed = json.loads(raw)
        return (parsed, hashlib.sha256(raw).hexdigest()) if with_digest else parsed


def successful(run, path, source=None):
    if (run.get('path') != '.github/workflows/' + path
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'
            or source is not None and run.get('head_sha') != source):
        raise ValueError(f'Required exact-source CI is missing, pending or failed: {path}')


def require_jobs(repository, run, names):
    jobs = api(f'repos/{repository}/actions/runs/{run["id"]}/attempts/{run["run_attempt"]}/jobs?per_page=100')['jobs']
    for name in names:
        matches = [job for job in jobs if job['name'] == name]
        if len(matches) != 1 or matches[0]['conclusion'] != 'success':
            raise ValueError(f'CI lacks required successful job: {name}')


def require_tag(repository, tag, source, *, allow_missing=False):
    refs = api(f'repos/{repository}/git/matching-refs/tags/{tag}')
    exact = [ref for ref in refs if ref['ref'] == 'refs/tags/' + tag]
    if not exact and allow_missing:
        return
    if len(exact) != 1:
        raise ValueError('Missing or ambiguous publication tag')
    target = exact[0]['object']
    if target['type'] == 'tag':
        target = api(f'repos/{repository}/git/tags/{target["sha"]}')['object']
    if target.get('type') != 'commit' or target.get('sha') != source:
        raise ValueError('Publication tag differs from the qualified source')


def require_source_ci(repository, source, candidate_run_id):
    with _artifact_scope():
        return _require_source_ci(repository, source, candidate_run_id)


def _require_source_ci(repository, source, candidate_run_id):
    if repository not in {'maxwellsdm1867/Rieke-OS', 'maxwellsdm1867/disco'}:
        raise ValueError('Unexpected publication repository')
    if not isinstance(source, str) or not re.fullmatch('[0-9a-f]{40}', source):
        raise ValueError('Publication requires a full source commit')
    if not re.fullmatch('[1-9][0-9]*', str(candidate_run_id)):
        raise ValueError('Publication requires a successful desktop candidate run ID')
    receipts = {}
    for workflow in ('workspace-ci.yml', 'everyday-million.yml'):
        rows = api(f'repos/{repository}/actions/workflows/{workflow}/runs?head_sha={source}&per_page=1')['workflow_runs']
        if not rows:
            raise ValueError(f'Missing exact-source CI: {workflow}')
        run = rows[0]  # The latest run must pass; never pick an older green run.
        successful(run, workflow, source)
        receipts[workflow] = run
    regression = artifact(repository, receipts['workspace-ci.yml'], 'adopted-architecture-plan', 'architecture-plan.json')
    if (regression.get('head') != source or regression.get('dirty') is not False
            or regression.get('selection') != 'all' or regression.get('source_changed') is not True):
        raise ValueError('Publication requires full_checks on the exact clean source, not a PR merge or documentation-only plan')
    require_jobs(repository, receipts['workspace-ci.yml'],
        ['Adopted architecture contract discovery', 'frontend', 'python',
         'Scoped desktop lifecycle contracts', 'Apple Silicon native project lifecycle and transfer'])
    run = receipts['everyday-million.yml']
    require_jobs(repository, run,
        ['Backend million query regression', 'Browser million workflow regression',
         'Actual million metadata query regression', 'macOS foreground trace regression'])
    # Read the bounded proof, never the full browser/native diagnostic archive.
    # Recompute the existing policy so a stale green comparison cannot qualify
    # changed, incomplete or incomparable trace observations.
    if __package__:
        from tools.benchmark_prepared_geometry import compare as compare_trace
    else:
        from benchmark_prepared_geometry import compare as compare_trace
    trace_name = f'trace-macos-proof-{run["id"]}-{run["run_attempt"]}'
    trace_before = artifact(repository, run, trace_name, 'baseline/receipt.json')
    trace_after = artifact(repository, run, trace_name, 'candidate/receipt.json')
    trace_comparison = artifact(repository, run, trace_name, 'comparison.json')
    if (trace_before.get('source_start', {}).get('commit') != '4de896f2e0b4ea966b5a428c3d2314f93fba935f'
            or trace_after.get('source_start', {}).get('commit') != source):
        raise ValueError('Foreground trace proof differs from the pinned baseline or publication source')
    expected_trace = compare_trace(trace_before, trace_after)
    if expected_trace.get('status') != 'passed' or trace_comparison != expected_trace:
        raise ValueError('Missing, failed or mismatched foreground trace comparison')
    name = f'everyday-million-{run["id"]}-{run["run_attempt"]}'
    candidate_digests = {}
    for filename in ('candidate/receipt.json', 'workflow-candidate/receipt.json'):
        receipt, candidate_digests[filename] = artifact(repository, run, name, filename, with_digest=True)
        start = receipt.get('source_start', {})
        if (receipt.get('status') != 'passed' or start.get('commit') != source
                or start.get('status') != '' or receipt.get('source_end') != start):
            raise ValueError('Benchmark evidence does not measure the exact clean publication source')
    for filename in ('pinned-comparison.json', 'previous-comparison.json',
                     'workflow-pinned-comparison.json', 'workflow-previous-comparison.json'):
        comparison = artifact(repository, run, name, filename)
        if comparison.get('status') != 'passed' or comparison.get('review_required') != []:
            raise ValueError('Publication is blocked by a missing or failed performance comparison')
        receipt_name = 'workflow-candidate/receipt.json' if filename.startswith('workflow-') else 'candidate/receipt.json'
        # Query comparisons identify the source through the exact receipt hash;
        # browser comparisons additionally declare its commit explicitly.
        if (comparison.get('candidate_commit', source) != source
                or filename.startswith('workflow-') and comparison.get('candidate_commit') != source
                or comparison.get('candidate_receipt_sha256') != candidate_digests[receipt_name]):
            raise ValueError('Performance comparison differs from the exact candidate receipt')
    candidate = api(f'repos/{repository}/actions/runs/{candidate_run_id}')
    successful(candidate, 'desktop-candidate.yml')
    plan = artifact(repository, candidate, 'desktop-release-plan', 'release-plan.json')
    if (plan.get('head') != source or plan.get('build_required') is not True
            or any(type(plan.get(flag)) is not bool for flag in ('updater', 'database', 'packaging', 'full_ui'))):
        raise ValueError('Candidate plan does not build the publication source')
    required = ['build', 'Verify smoke'] + [f'Verify {suite}' for flag, suite in
        [('updater', 'updater'), ('database', 'database'), ('packaging', 'packaging'), ('full_ui', 'ui')] if plan.get(flag)]
    require_jobs(repository, candidate, required)
    return {'source_commit': source, 'regression_run': receipts['workspace-ci.yml']['id'],
            'million_run': run['id'], 'candidate_run': candidate['id']}
