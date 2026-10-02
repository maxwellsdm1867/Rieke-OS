"""Owned native server plus paired lightweight-preview diagnostic; no browser.

Uses one identical full API prewarming sequence before ten real HTTP lightweight
requests. This does not replace the main ten-sample native performance receipt.
"""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--mysql-runtime-root', type=Path, required=True)
parser.add_argument('--index', type=Path, required=True)
args = parser.parse_args()
out = args.output_dir.resolve()
if out.exists():
    parser.error('Choose an unused output directory')
out.mkdir(parents=True)
root = Path(__file__).parent
native_out = out / 'native'
command = [sys.executable, '-B', str(root / 'native_metadata.py'), '--source-root', str(args.source_root),
           '--output-dir', str(native_out), '--mysql-runtime-root', str(args.mysql_runtime_root),
           '--index', str(args.index), '--samples', '1', '--cap-seconds', '150',
           '--serve-browser', '--browser-wait-seconds', '60']
exit_code = 1
with (out / 'native.log').open('w') as log:
    worker = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    try:
        config = native_out / 'native-metadata-browser-config.json'
        deadline = time.monotonic() + 90
        while not config.exists():
            if worker.poll() is not None:
                raise RuntimeError('Owned native worker ended before fixture server became ready; see native.log')
            if time.monotonic() > deadline:
                raise TimeoutError('Owned fixture server readiness exceeded 90 seconds')
            time.sleep(.25)
        completed = subprocess.run([sys.executable, '-B', str(root / 'diagnostic_preview.py'),
                                    '--config', str(config), '--output', str(out / 'lightweight-preview.json'),
                                    '--samples', '10', '--warmup-scope', 'api-prewarmed'], timeout=45, check=True)
        exit_code = completed.returncode
    finally:
        if native_out.exists():
            (native_out / 'native-browser-done').touch()
        try:
            worker.wait(timeout=30)
        except subprocess.TimeoutExpired:
            # Only this wrapper's own child is interrupted so its finally block
            # can stop the own native server. Never signal other processes.
            worker.send_signal(signal.SIGINT)
            worker.wait(timeout=30)
receipt = json.loads((native_out / 'native-metadata-100k.json').read_text())
assert receipt['passed'] and receipt['oracle_calls'] == 0 and receipt['owned_native_runtime_stopped']
print(json.dumps({'passed': True, 'native_context_ready': receipt['native_context_ready'],
                  'oracle_calls': receipt['oracle_calls'], 'owned_native_runtime_stopped': receipt['owned_native_runtime_stopped'],
                  'diagnostic': str(out / 'lightweight-preview.json')}))
raise SystemExit(exit_code)
