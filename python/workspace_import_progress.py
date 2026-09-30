"""Atomic actual-stage progress and defensive local job diagnostics (no SQL)."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import time
import uuid

TERMINAL = {'complete', 'complete_with_warnings', 'duplicate', 'failed', 'interrupted'}
LABELS = {'queued': 'Queued', 'checking_duplicates': 'Checking file identity',
    'freezing_baselines': 'Preserving current protocol datasets', 'source_hashing': 'Verifying source checksum',
    'parsing': 'Parsing Symphony metadata', 'validating_metadata': 'Validating epochs and source pointers',
    'verifying_source_hash': 'Rechecking source checksum', 'writing_catalog': 'Writing catalog transaction',
    'verifying_catalog': 'Checking inserted catalog records', 'catalog_committed': 'Catalog transaction committed',
    'finalizing_files': 'Saving protocol query files', 'refreshing_workspace': 'Refreshing the project',
    'rerunning_protocols': 'Checking saved protocol queries', 'complete': 'Complete', 'failed': 'Stopped',
    'duplicate': 'Already imported',
    'indexing_shared_annotations': 'Indexing epoch and cell tags',
    'preparing_native_tag_lookup': 'Preparing persistent tag lookup',
    'preparing_tag_filters': 'Preparing tag filters',
    'preparing_tag_summary': 'Preparing tag summaries',
    'preparing_tag_suggestions': 'Preparing tag suggestions',
    'indexing_dataset_tags': 'Indexing dataset tags',
    'preparing_protocol_reads': 'Preparing protocol views'}


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + str(uuid.uuid4()) + '.tmp')
    try:
        with temporary.open('w') as handle:
            json.dump(value, handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class ProgressReporter:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.current = {'version': 1, 'commit_state': 'not_started', 'pid': os.getpid()}
        self._written_at = 0

    def emit(self, stage, **fields):
        if self.current.get('commit_state') == 'committed':
            fields.update(commit_state='committed', catalog_committed=True)
        previous = self.current.get('stage')
        stamp = utcnow()
        if stage != previous:
            for key in ('completed', 'total', 'unit', 'message'):
                self.current.pop(key, None)
            self.current['stage_started_at'] = stamp
        self.current.update(stage=stage, stage_label=LABELS.get(stage, stage.replace('_', ' ')), updated_at=stamp, **fields)
        # Stage changes and completed measurements are durable immediately;
        # intermediate measured counters are throttled, never extrapolated.
        instant = time.monotonic()
        final = fields.get('completed') is not None and fields.get('completed') == fields.get('total')
        if self.path and (stage != previous or instant - self._written_at >= .2 or final or 'outcome' in fields):
            try:
                atomic_json(self.path, self.current)
                self._written_at = instant
            except OSError as error:
                # Progress telemetry cannot turn a committed catalog into a
                # reported parse failure. A missing terminal marker is unknown.
                self.current['progress_write_error'] = str(error)
        return dict(self.current)


def load_json(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError('Saved job/progress must be a JSON object')
    return value


def seconds_since(value, end=None):
    try:
        start = dt.datetime.fromisoformat(value)
        stop = dt.datetime.fromisoformat(end) if end else dt.datetime.now(dt.timezone.utc)
        if start.tzinfo is None or stop.tzinfo is None:
            return None
        return max(0., (stop-start).total_seconds())
    except (TypeError, ValueError):
        return None


def progress_for(path, job):
    # Derive the sidecar path; do not trust arbitrary paths from damaged JSON.
    target = Path(path).parent / 'progress' / (Path(path).stem + '.json')
    if not target.exists():
        return None, None
    try:
        value = load_json(target)
        if value.get('version') != 1 or not isinstance(value.get('stage'), str):
            raise ValueError('Unsupported progress format')
        if any(key in value and not isinstance(value[key], str) for key in ('stage_label', 'message', 'unit', 'error', 'error_type')):
            raise ValueError('Progress labels and diagnostic text must be strings')
        if not isinstance(value.get('commit_state', 'not_started'), str) or value.get('commit_state', 'not_started') not in {'not_started', 'unknown', 'committed'}:
            raise ValueError('Invalid progress commit state')
        if 'catalog_committed' in value and value['catalog_committed'] is not None and type(value['catalog_committed']) is not bool:
            raise ValueError('Catalog commit evidence must be true, false or unknown')
        for key in ('completed', 'total'):
            if key in value and (type(value[key]) is not int or value[key] < 0):
                raise ValueError('Progress counters must be nonnegative integers')
        if 'completed' in value and 'total' in value and value['completed'] > value['total']:
            raise ValueError('Progress completed count exceeds its measured total')
        return value, None
    except (OSError, ValueError) as error:
        return None, {'stage': 'progress_log', 'message': str(error), 'path': str(target)}


def read_job(path, owner_run_id, active_jobs=()):
    path = Path(path)
    try:
        job = load_json(path)
        if (not isinstance(job.get('status'), str)
                or ('source' in job and not isinstance(job['source'], str))
                or ('warnings' in job and (not isinstance(job['warnings'], list)
                    or any(not isinstance(value, dict) for value in job['warnings'])))):
            raise ValueError('Saved job has invalid status, source or warnings fields')
        def text_fields(record, names, context):
            for key in names:
                if key in record and record[key] is not None and not isinstance(record[key], str):
                    raise ValueError(f'Saved {context}.{key} must be text')
        text_fields(job, ('message', 'error', 'error_type', 'audit_write_error', 'log_path',
                          'source_filename', 'source_path'), 'job')
        diagnostics = job.get('diagnostics')
        if diagnostics is not None:
            if not isinstance(diagnostics, dict):
                raise ValueError('Saved job diagnostics must be an object')
            text_fields(diagnostics, ('message', 'error', 'stage', 'error_type', 'path', 'traceback_path'), 'diagnostics')
        for warning in job.get('warnings', []):
            text_fields(warning, ('message', 'error', 'stage', 'error_type', 'path'), 'warning')
        # Recovery may persist a copy of the last validated progress. Validate
        # its display text too when a sidecar is absent or damaged.
        if 'progress' in job:
            if not isinstance(job['progress'], dict):
                raise ValueError('Saved job progress must be an object')
            text_fields(job['progress'], ('stage_label', 'message', 'error', 'stage', 'unit'), 'progress')
    except (OSError, ValueError) as error:
        return {'job_uuid': path.stem, 'status': 'interrupted', 'catalog_committed': None,
            'requires_reconciliation': True, 'error': 'Saved job metadata is unreadable.',
            'diagnostics': {'stage': 'job_log', 'error_type': type(error).__name__, 'message': str(error), 'path': str(path)},
            'heartbeat_at': utcnow(), 'monitor_alive': False}
    progress, diagnostic = progress_for(path, job)
    running = path.stem in active_jobs and job.get('owner_run_id') == owner_run_id
    if job.get('status') not in TERMINAL and not running:
        job.update(status='interrupted', requires_reconciliation=True,
            catalog_committed=True if progress and progress.get('commit_state') == 'committed' else None,
            error='The import worker belongs to an earlier server session or is no longer active. Check Data stores and diagnostics before retrying; a child process may still be finishing.')
    if progress:
        job['progress'] = progress
        job['stage_elapsed_seconds'] = seconds_since(progress.get('stage_started_at'), job.get('finished_at'))
        job['progress_age_seconds'] = seconds_since(progress.get('updated_at'))
    if diagnostic:
        job.setdefault('warnings', []).append(diagnostic)
    job.update(job_uuid=path.stem, elapsed_seconds=seconds_since(job.get('started_at', job.get('created_at')),job.get('finished_at')),
               heartbeat_at=utcnow(), monitor_alive=running)
    return job


def read_jobs(folder, owner_run_id, active_jobs=()):
    def mtime(path):
        try:return path.stat().st_mtime_ns
        except OSError:return 0
    paths = sorted(Path(folder).glob('*.json'), key=mtime, reverse=True)[:50]
    return [read_job(path, owner_run_id, active_jobs) for path in paths]


def recover_jobs(folder, owner_run_id):
    """Persist interrupted status on restart; never infer absent SQL commits."""
    for path in Path(folder).glob('*.json'):
        try:
            original = load_json(path)
            if not isinstance(original.get('status'), str):
                continue
            if original.get('status') in TERMINAL or original.get('owner_run_id') == owner_run_id:
                continue
            recovered = read_job(path, owner_run_id)
            if recovered.get('diagnostics', {}).get('stage') == 'job_log':
                continue  # Keep corrupt raw evidence intact for inspection.
            for key in ('heartbeat_at', 'monitor_alive', 'elapsed_seconds', 'stage_elapsed_seconds', 'progress_age_seconds', 'job_uuid'):
                recovered.pop(key, None)
            recovered['interrupted_at'] = utcnow()
            atomic_json(path, recovered)
        except (OSError, ValueError):
            pass  # Preserve corrupt evidence; GET exposes a diagnostic row.
