"""One fresh synthetic metadata-index build; no API, MySQL, H5 or user data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--epochs', type=int, default=100000)
parser.add_argument('--cap-seconds', type=int, default=90)
args = parser.parse_args()
source = args.source_root.resolve(strict=True)
out = args.output_dir.resolve()
if out.exists():
    parser.error('Choose an unused output directory')
out.mkdir(parents=True)
os.environ['RIEKE_PREFERENCES_DIR'] = str(out / 'preferences')
os.environ['RIEKE_PROJECT_INDEX'] = str(out / 'preferences/projects.json')
sys.dont_write_bytecode = True
sys.path[:0] = [str(source / 'python'), str(source / 'docs/dev/scale-audit-2026-09-29')]
from benchmark_service_scale import fixture, Details
from workspace_disk_index import DiskMetadataIndex

receipt = {'scope': __doc__, 'source_root': str(source), 'epochs': args.epochs,
           'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
           'source_hashes': {p: hashlib.sha256((source / p).read_bytes()).hexdigest() for p in
                             ['python/workspace_disk_index.py', 'python/workspace_metadata_objects.py']},
           'single_observation': True, 'checks': []}
started = time.perf_counter()
index = None

def capped(signum, frame):
    signal.alarm(0)
    raise TimeoutError('Owned metadata index build exceeded its experiment cap')

signal.signal(signal.SIGALRM, capped)
signal.alarm(args.cap_seconds)
try:
    began = time.perf_counter()
    service, protocol = fixture(args.epochs)
    receipt['model_seconds'] = time.perf_counter() - began
    began = time.perf_counter()
    index = DiskMetadataIndex.build(out / 'fixture/index.sqlite', service.rows,
                                   Details(service.rows), service.sources,
                                   'paired-index-build', service.project['project_uuid'])
    receipt['build_seconds'] = time.perf_counter() - began
    receipt['index_bytes'] = index.path.stat().st_size
    assert index._epoch_count == args.epochs
    catalog = index.catalog()
    assert catalog['total'] == args.epochs
    receipt['catalog_sha256'] = hashlib.sha256(json.dumps(catalog, sort_keys=True,
                                             ensure_ascii=False).encode()).hexdigest()
    for identity in (next(iter(service.rows)), next(reversed(service.rows))):
        assert index.details[identity] == Details(service.rows)[identity]
    receipt['checks'].append({'name': 'counts_and_boundary_details', 'passed': True})
    index.close()
    index = None
    began = time.perf_counter()
    index = DiskMetadataIndex.open(out / 'fixture/index.sqlite', 'paired-index-build',
                                   service.project['project_uuid'])
    receipt['reopen_seconds'] = time.perf_counter() - began
    assert index._epoch_count == args.epochs
    receipt['checks'].append({'name': 'sealed_reopen', 'passed': True})
    receipt['passed'] = True
except Exception as error:
    receipt['passed'] = False
    receipt['error'] = str(error)
finally:
    signal.alarm(0)
    if index is not None:
        index.close()
    receipt['seconds'] = time.perf_counter() - started
    receipt['peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)
raise SystemExit(0 if receipt['passed'] else 1)
