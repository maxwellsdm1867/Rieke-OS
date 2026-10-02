"""Copy an exact frontend snapshot to a disposable benchmark shell."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--node-modules', type=Path, required=True)
args = parser.parse_args()
source = args.source_root.resolve(strict=True)
destination = args.output_dir.resolve()
if destination.exists():
    parser.error('Choose an unused output directory')

def inventory():
    return {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((source / 'workspace-app' / 'src').rglob('*')) if path.is_file()}

before = inventory()
destination.mkdir(parents=True)
shutil.copytree(source / 'workspace-app' / 'src', destination / 'src')
for name in ('bench.jsx', 'index.html'):
    shutil.copy2(Path(__file__).with_name(name), destination / name)
(destination / 'node_modules').symlink_to(args.node_modules.resolve(strict=True), target_is_directory=True)
after = inventory()
copied = {str(Path('workspace-app/src') / path.relative_to(destination / 'src')):
          hashlib.sha256(path.read_bytes()).hexdigest()
          for path in sorted((destination / 'src').rglob('*')) if path.is_file()}
if not before == after == copied:
    raise RuntimeError('Frontend source changed during copy or copy is incomplete')
manifest = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
            'source_root': str(source), 'source_inventory': before,
            'exact_source_snapshot_verified': True}
(destination / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(destination)
