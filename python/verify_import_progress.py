"""Exercise real parsing progress and malformed-H5 errors without SQL writes.

Run with the RetinAnalysis Python environment. All output goes to a new proof
directory; the supplied H5 is read-only. The child always uses --parse-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def exercise(source, folder, repository, expected_hash=None):
    folder.mkdir(parents=True, exist_ok=False)
    progress = folder / 'progress.json'
    command = [sys.executable, str(Path(__file__).with_name('recording_workspace.py')),
               str(source), '--project-dir', str(folder / 'project'),
               '--retinanalysis', str(repository), '--parse-only',
               '--progress-file', str(progress)]
    if expected_hash:
        command += ['--expected-sha256', expected_hash]
    snapshots = []
    previous = None
    started = time.monotonic()
    with (folder / 'process.log').open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            while True:
                if progress.exists():
                    value = json.loads(progress.read_text())
                    if value != previous:
                        snapshots.append({'observed_seconds': round(time.monotonic()-started, 3), 'progress': value})
                        previous = value
                if process.poll() is not None:
                    if progress.exists():
                        final = json.loads(progress.read_text())
                        if final != previous:
                            snapshots.append({'observed_seconds': round(time.monotonic()-started, 3), 'progress': final})
                    break
                if time.monotonic() - started > 180:
                    raise TimeoutError('Disposable parse-only verification exceeded 180 seconds')
                time.sleep(.05)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    assert snapshots, 'No durable progress was produced'
    result = {'exit_code': process.returncode, 'elapsed_seconds': round(time.monotonic()-started, 3),
              'snapshots': snapshots, 'final': snapshots[-1]['progress']}
    (folder / 'observed-progress.json').write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--retinanalysis', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source, output = args.source.resolve(strict=True), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    original = (source.stat().st_size, source.stat().st_mtime_ns, digest(source))
    valid = exercise(source, output / 'valid-source', args.retinanalysis, original[2])
    assert valid['exit_code'] == 0, valid['final']
    assert valid['final']['stage'] == 'complete', valid['final']
    assert valid['final'].get('catalog_committed') is False, 'Parse-only must never claim a SQL commit'
    validation = [item['progress'] for item in valid['snapshots']
                  if item['progress']['stage'] == 'validating_metadata']
    assert validation and validation[-1]['completed'] == valid['final']['counts']['epochs']
    assert all(item['unit'] == 'epochs' and 0 <= item['completed'] <= item['total']
               for item in validation)
    assert [item['completed'] for item in validation] == sorted(item['completed'] for item in validation)
    parsing = [item['progress'] for item in valid['snapshots'] if item['progress']['stage'] == 'parsing']
    assert parsing and all('total' not in item for item in parsing), 'Opaque parser must remain indeterminate'
    malformed = output / 'malformed.h5'
    malformed.write_bytes(b'Disposable invalid H5 fixture. No research samples.\n')
    invalid = exercise(malformed, output / 'malformed-source', args.retinanalysis)
    assert invalid['exit_code'] != 0 and invalid['final']['stage'] == 'failed', invalid['final']
    assert invalid['final'].get('catalog_committed') is False, invalid['final']
    assert invalid['final'].get('error') and invalid['final'].get('error_type'), invalid['final']
    assert original == (source.stat().st_size, source.stat().st_mtime_ns, digest(source))
    proof = {'status': 'passed', 'source': str(source), 'source_sha256': original[2],
             'source_unchanged': True, 'parse_only_no_sql_writes': True,
             'valid': {key: value for key, value in valid.items() if key != 'snapshots'},
             'malformed': {key: value for key, value in invalid.items() if key != 'snapshots'}}
    (output / 'proof.json').write_text(json.dumps(proof, indent=2))
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
