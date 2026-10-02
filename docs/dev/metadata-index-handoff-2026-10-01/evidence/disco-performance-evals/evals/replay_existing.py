"""Bounded replay of unchanged existing tag/trace harnesses from selected source.

All state/preferences/temp projects are below a fresh owned output directory.
An alarm raises a normal exception so native harness cleanup and partial receipts
can complete; no user's server, app or browser process is stopped.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import runpy
import signal
import sys
import tempfile
import time
import traceback

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--family', choices=('tags', 'trace'), required=True)
parser.add_argument('--mysql-runtime-root', type=Path)
parser.add_argument('--epochs', type=int, default=100000)
parser.add_argument('--samples', type=int, default=10)
parser.add_argument('--cap-seconds', type=int, default=300)
args = parser.parse_args()
source = args.source_root.resolve(strict=True)
out = args.output_dir.resolve()
if out.exists():
    parser.error('Choose an unused owned output directory')
if args.family == 'tags' and args.mysql_runtime_root is None:
    parser.error('--mysql-runtime-root is required for tags')
out.mkdir(parents=True)
(out / 'temporary').mkdir()
tempfile.tempdir = str(out / 'temporary')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True
os.environ['RIEKE_PREFERENCES_DIR'] = str(out / 'preferences')
os.environ['RIEKE_PROJECT_INDEX'] = str(out / 'preferences/project-index.json')
os.environ['RIEKE_USER_PREFERENCES_PATH'] = str(out / 'preferences.json')
sys.path[:0] = [str(source / 'python'), str(source / 'docs/dev/scale-audit-2026-09-29')]
harness = source / 'docs/dev/scale-audit-2026-09-29' / (
    'benchmark_native_tag_sequence.py' if args.family == 'tags' else 'benchmark_trace_integrity.py')
receipt = out / (args.family + '.json')
sys.argv = [str(harness), '--output', str(receipt)]
if args.family == 'tags':
    sys.argv += ['--source-root', str(source), '--mysql-runtime-root', str(args.mysql_runtime_root.resolve(strict=True)),
                 '--epochs', str(args.epochs), '--samples', str(args.samples)]
started = time.perf_counter()
report = {'started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'family': args.family, 'source_root': str(source), 'cap_seconds': args.cap_seconds,
          'argv': sys.argv, 'existing_harness_sha256': hashlib.sha256(harness.read_bytes()).hexdigest(),
          'wrapper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

def capped(signum, frame):
    signal.alarm(0)
    raise TimeoutError(f'Owned {args.family} experiment hit {args.cap_seconds} second limit')

signal.signal(signal.SIGALRM, capped)
signal.alarm(args.cap_seconds)
exit_code = 0
try:
    runpy.run_path(str(harness), run_name='__main__')
except SystemExit as error:
    exit_code = error.code if isinstance(error.code, int) else int(error.code is not None)
except Exception as error:
    report['error'] = str(error)
    report['traceback'] = traceback.format_exc()
    exit_code = 1
finally:
    signal.alarm(0)
    report['exit_code'] = exit_code
    report['seconds'] = time.perf_counter() - started
    report['peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    report['receipt_exists'] = receipt.exists()
    (out / 'runner.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
raise SystemExit(exit_code)
