#!/usr/bin/env python3
"""Cold first access to a recording after start-up: time spent under db_lock.

Owned disposable files only. A recording of ``--megabytes`` random bytes is
registered with its SHA-256; a WorkspaceService shell (no database) has no
verified stat signature, as after a process restart. Measured:

- ``locked_ms``: ``_verified_source`` (what the trace/merge paths run while
  holding db_lock) on the cold source.
- ``outside_ms``: ``preverify_sources`` (candidate trees only), run before the
  locked step without any lock, as the trace route and project-open prewarm do.
- ``hashes_under_lock``: whole-file SHA-256 calls made inside the locked step.

Run with ``--source-root`` against baseline and candidate with identical bytes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time


def run(source_root, megabytes, repeats):
    sys.path[:0] = [str(source_root / 'python')]
    import workspace_service as module
    samples = []
    with tempfile.TemporaryDirectory(prefix='disco-source-signature-benchmark-') as folder:
        path = Path(folder) / 'recording.h5'
        with path.open('wb') as handle:
            for _ in range(megabytes):
                handle.write(os.urandom(1 << 20))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = {'source_path': str(path), 'source_sha256': sha, 'source_size': path.stat().st_size}
        original = module.digest
        for _ in range(repeats):
            service = module.WorkspaceService.__new__(module.WorkspaceService)
            service.__dict__.update(manifests={sha: manifest}, _source_signatures={}, _loaded=True)
            outside = None
            if hasattr(service, 'preverify_sources'):
                begin = time.perf_counter()
                service.preverify_sources()
                outside = (time.perf_counter() - begin) * 1000
            calls = []
            module.digest = lambda value, _calls=calls: _calls.append(1) or original(value)
            try:
                begin = time.perf_counter()
                service._verified_source(manifest)
                locked = (time.perf_counter() - begin) * 1000
            finally:
                module.digest = original
            samples.append({'locked_ms': locked, 'outside_ms': outside, 'hashes_under_lock': len(calls)})
    return {'megabytes': megabytes,
            'locked_ms_median': round(statistics.median(item['locked_ms'] for item in samples), 3),
            'outside_ms_median': (round(statistics.median(item['outside_ms'] for item in samples), 1)
                                  if samples[0]['outside_ms'] is not None else None),
            'hashes_under_lock': statistics.median(item['hashes_under_lock'] for item in samples),
            'samples': samples}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--megabytes', type=int, nargs='+', default=[64, 512])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = args.source_root.resolve()
    results = [run(source, size, args.repeats) for size in args.megabytes]
    text = json.dumps({'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       'source_root': str(source), 'python': sys.version.split()[0], 'results': results}, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    for item in results:
        print(item['megabytes'], 'MB locked', item['locked_ms_median'], 'ms, outside', item['outside_ms_median'],
              'ms, hashes under lock', item['hashes_under_lock'])
