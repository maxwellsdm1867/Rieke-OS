"""Watch settled top-level H5 files in the single project-managed raw store."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
import uuid

from workspace_import_progress import atomic_json
from workspace_storage import managed_directory, log_dir


class H5Inbox:
    def __init__(self, project, submit, *, quiet_seconds=5, clock=time.time):
        self.project = Path(project).resolve()
        self.path = self.project / 'raw-uploads'
        self.ledger_path = self.project / 'logs/storage/h5-inbox-ledger.json'
        self.submit = submit  # callback(source, reserved_job_uuid) -> accepted bool
        self.quiet_seconds = quiet_seconds
        self.clock = clock
        self.entries = {}
        self.error = None
        self.enabled = False
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        managed_directory(self.project, 'raw-uploads')
        log_dir(self.project, 'storage')
        if self.ledger_path.exists() or self.ledger_path.is_symlink():
            if self.ledger_path.is_symlink() or self.ledger_path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError('Inbox ledger must be a regular local file smaller than 10 MB')
            saved = json.loads(self.ledger_path.read_text())
            if saved.get('version') != 1 or not isinstance(saved.get('files'), dict):
                raise ValueError('Inbox ledger is invalid; preserve it for recovery')
            for name, entry in saved['files'].items():
                if Path(name).name != name or not isinstance(entry, dict):
                    raise ValueError('Inbox ledger contains an invalid filename')
                identity = entry.get('job_uuid')
                if identity and str(uuid.UUID(identity)) != identity:
                    raise ValueError('Inbox ledger contains an invalid job identity')
            self.entries = saved['files']
        self._loaded = True

    def _save(self):
        if self.ledger_path.is_symlink():
            raise ValueError('Inbox ledger cannot be a symbolic link')
        atomic_json(self.ledger_path, {'version': 1, 'files': self.entries})

    def scan(self):
        """One nonblocking scan, injectable clock/submit for deterministic tests."""
        with self._lock:
            self._load()
            if self.path.is_symlink():
                raise ValueError('Managed H5 folder cannot be a symbolic link')
            present = set()
            submitted_this_scan = False
            for source in sorted(self.path.iterdir()):
                if source.name.startswith('.') or source.suffix.lower() not in {'.h5', '.hdf5'}:
                    continue
                try:
                    info = source.lstat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
                    continue
                present.add(source.name)
                fingerprint = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
                entry = self.entries.get(source.name)
                if not entry or entry.get('fingerprint') != fingerprint:
                    self.entries[source.name] = {'fingerprint': fingerprint, 'observed_at': self.clock(), 'status': 'settling'}
                    self._save()
                    continue
                if entry.get('status') == 'submitted':
                    job = self.project / 'logs/app-jobs' / (entry['job_uuid'] + '.json')
                    if job.is_file() and not job.is_symlink():
                        try:
                            result = json.loads(job.read_text())
                            state = result.get('status')
                            if state in {'complete', 'complete_with_warnings', 'duplicate', 'failed', 'interrupted'}:
                                entry['status'] = state
                                if result.get('error'):
                                    entry['error'] = str(result['error'])
                                elif result.get('requires_reconciliation'):
                                    entry['error'] = 'This import needs reconciliation; inspect its diagnostics in Imports.'
                                self._save()
                        except (ValueError, OSError):
                            pass
                    continue
                if entry.get('status') not in {'settling', 'planned'}:
                    continue
                if self.clock() - entry['observed_at'] < self.quiet_seconds:
                    continue
                if entry.get('status') != 'planned':
                    entry.update(status='planned', job_uuid=str(uuid.uuid4()))
                    self._save()  # Reserve job ID before queueing: crash-safe correlation.
                job = self.project / 'logs/app-jobs' / (entry['job_uuid'] + '.json')
                if job.exists():
                    entry['status'] = 'submitted'
                    self._save()
                    continue
                if not submitted_this_scan and self.submit(source, entry['job_uuid']):
                    entry['status'] = 'submitted'
                    self._save()
                    submitted_this_scan = True
            for name in set(self.entries) - present:
                self.entries.pop(name)
                self._save()
            self.error = None

    def status(self):
        with self._lock:
            return {'path': str(self.path), 'enabled': self.enabled, 'quiet_seconds': self.quiet_seconds,
                    'files': [{'name': name, 'status': item['status'],
                               **({'job_uuid': item['job_uuid']} if item.get('job_uuid') else {}),
                               **({'error': item['error']} if item.get('error') else {})}
                              for name, item in sorted(self.entries.items())], 'error': self.error}

    def open_folder(self):
        with self._lock:
            self._load()
            if self.path.is_symlink():
                raise ValueError('Managed H5 folder cannot be a symbolic link')
            command = ['open', str(self.path)] if sys.platform == 'darwin' else ['explorer', str(self.path)] if os.name == 'nt' else ['xdg-open', str(self.path)]
            subprocess.run(command, check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.enabled = True
        def loop():
            while not self._stop.is_set():
                try:
                    self.scan()
                except Exception as error:
                    self.error = str(error)
                self._stop.wait(1)
            self.enabled = False
        self._thread = threading.Thread(target=loop, name='rieke-h5-inbox', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=12)
            if self._thread.is_alive():
                raise RuntimeError('H5 inbox is still finishing an operation; wait before closing the project')
        self.enabled = False
