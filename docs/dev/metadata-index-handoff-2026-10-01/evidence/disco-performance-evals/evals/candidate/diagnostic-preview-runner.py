"""Separate real-HTTP lightweight-filter diagnostic after timed browser actions.

This is not substituted for the historical full-catalog preview operation.
The request uses MetadataExplorer's already-existing catalog_summary:false path.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import statistics
import time
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--samples', type=int, default=10)
args = parser.parse_args()
if args.output.exists():
    parser.error('Choose an unused output receipt')
config = json.loads(args.config.read_text())
origin = config['api_origin']
if not origin.startswith('http://127.0.0.1:'):
    parser.error('Use only the owned loopback fixture server')
body = {'predicate': {'field': 'parameters/contrast', 'operator': 'eq', 'value': .3},
        'splits': 'date,cell,block', 'summary_only': True, 'catalog_summary': False}
encoded = json.dumps(body).encode()
samples = []
hashes = []
sizes = []
response_keys = None
for _ in range(args.samples):
    request = Request(origin + '/api/explore/preview', data=encoded,
                      headers={'Content-Type': 'application/json', 'X-Workspace-Request': '1', 'Origin': origin})
    began = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        raw = response.read()
        value = json.loads(raw)
    samples.append(time.perf_counter() - began)
    assert value['matched_count'] == 20000 and value['catalog_summary'] is False
    assert value['total_source'] == 100000 and value['total_catalog'] == 100000
    response_keys = sorted(value)
    hashes.append(hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
    sizes.append(len(raw))
assert len(set(hashes)) == 1, 'Repeated deterministic preview changed its response'
report = {'started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'source_head': config['source_head'], 'scope': config['scope'],
          'name': 'http_contrast_filter_preview_catalog_summary_false',
          'measurement_scope': 'Real localhost HTTP, response bytes and JSON decode; no browser rendering. Post-browser warm server diagnostic. Existing UI lightweight path, separate from historical default full-catalog API preview.',
          'request_body': body, 'samples_seconds': samples, 'first_seconds': samples[0],
          'median_seconds': statistics.median(samples), 'maximum_seconds': max(samples),
          'response_bytes': sizes, 'response_keys': response_keys, 'canonical_response_sha256': hashes[0],
          'matched_count': 20000, 'passed': True,
          'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
