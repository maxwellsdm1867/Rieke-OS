#!/usr/bin/env python3
"""Cell QC read latency against a real sealed metadata index at two project sizes.

Measures the production CellQC methods (overview, trial page, response summary)
for one cell of fixed size while the rest of the project grows, so a flat median
across --epochs values shows QC cost is independent of project size. Details
come from a real DiskMetadataIndex (SQLite + compressed detail blobs + shared
ancestor objects). H5 trace reads are replaced by an in-memory double that
returns the same shape as service.trace; HTTP, Flask JSON and UI are not timed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'python'), str(ROOT / 'python/tests')]

SOURCE = 'a' * 64
CELLS_PER_BLOCK = 20


def uid(namespace, i):
    return str(uuid.UUID(int=(namespace << 64) | i))


def build_service(folder, epochs, cell_epochs):
    from test_workspace_api import FixtureService
    from disco.metadata.disk_index import DiskMetadataIndex
    service = FixtureService(folder)
    service.rows, details, service.cells, service._fingerprints = {}, {}, {}, {}
    stream = {'kind': 'responses', 'device': 'Amp1', 'units': 'mV', 'sample_count': 100000,
              'sample_rate': 10000., 'sample_rate_units': 'Hz'}
    # Cell 0 owns the first cell_epochs epochs; the remainder is 100-epoch cells.
    def cell_of(i):
        return 0 if i < cell_epochs else 1 + (i - cell_epochs) // 100
    for i in range(epochs):
        c, block = cell_of(i), i // CELLS_PER_BLOCK
        identity, cell, group, block_id = uid(1, i), uid(2, c), uid(3, c), uid(4, block)
        protocol = ('ExpandingSpots', 'SingleSpot', 'CurrentStep', 'VariableMeanNoiseCurInject')[block % 4]
        service.rows[identity] = {'epoch_uuid': identity, 'cell_uuid': cell, 'cell_label': f'Cell{c}',
            'cell_type': 'ON parasol', 'date': '2026-09-24',
            'start_time': f'09/24/2026 12:{(i // 60) % 60:02d}:{i % 60:02d}:000000',
            'group_uuid': group, 'group_label': 'control', 'block_uuid': block_id,
            'protocol_name': 'edu.washington.riekelab.protocols.' + protocol, 'duration_seconds': 10,
            'streams': [{**stream, 'uuid': uid(5, i)}], 'source_sha256': SOURCE, 'epoch_number': i % CELLS_PER_BLOCK + 1,
            'block_start_time': '09/24/2026 12:00:00:000000'}
        details[identity] = {
            'parameters': {'amp': 'Amp1', 'preTime': 500., 'stimTime': 1000., 'tailTime': 500.,
                           'currentSpotSize': float(40 + 20 * (i % 6)), 'contrast': 0.5, 'meanIntensity': 0.1,
                           'numberOfAverages': 5, 'interpulseInterval': 0, 'sampleRate': 10000},
            'properties': {'bathTemperature': {'quantity': 32. + (i % 7) * .1, 'units': 'degC'}},
            'attributes': {'note': 'synthetic'},
            'metadata': {'epoch': {'uuid': identity},
                'cell': {'uuid': cell, 'properties': {'type': 'ON parasol', 'inputResistance': {'quantity': 120., 'units': 'MOhm'}}},
                'group': {'uuid': group, 'properties': {'label': 'control', 'seriesResistanceCompensation': 50}},
                'block': {'uuid': block_id, 'parameters': {'protocolID': protocol, 'chan1': 'Amp1'}}}}
        service._fingerprints[identity] = hashlib.sha256(identity.encode()).hexdigest()
        if c not in service.cells:
            service.cells[cell] = {'cell_uuid': cell, 'label': f'Cell{c}', 'cell_type': 'ON parasol',
                                   'date': '2026-09-24', 'start_time': service.rows[identity]['start_time']}
    service.sources = [{'source_sha256': SOURCE, 'source_path': str(Path(folder) / 'never-open.h5'),
                        'filename': 'never-open.h5', 'counts': {'cells': len(service.cells), 'epochs': epochs}}]
    service.manifests = {SOURCE: {'source_path': service.sources[0]['source_path']}}
    started = time.perf_counter()
    index = DiskMetadataIndex.build(Path(folder) / 'qc.sqlite', service.rows, details, service.sources,
                                    f'qc-bench-{epochs}', service.project['project_uuid'])
    build_seconds = time.perf_counter() - started
    service.disk_index, service.details = index, index.details

    def trace(epoch, stream_uuid, start, count):
        values = [-60.] * 5000 + [-50.] * 10000 + [-60.] * (count - 15000)
        return {'epoch_uuid': epoch, 'stream_uuid': stream_uuid, 'start': start, 'count': count,
                'values': values, 'sample_rate': 10000., 'units': 'mV', 'total_samples': 100000,
                'source_sha256': SOURCE, 'decimated': False}
    service.trace = trace
    return service, index, uid(2, 0), build_seconds


def run(epochs, cell_epochs, repeats):
    from workspace_qc import CellQC
    with tempfile.TemporaryDirectory(prefix='disco-cell-qc-benchmark-') as folder:
        service, index, cell, build_seconds = build_service(folder, epochs, cell_epochs)
        qc = CellQC(service)
        first_epoch = uid(1, 0)
        operations = {}

        def measure(name, call, cold=False):
            samples = []
            for _ in range(repeats):
                if cold:
                    index._detail_cache.clear(); index._detail_cache_costs.clear(); index._detail_cache_bytes = 0
                    index._metadata_decoder.clear()
                started = time.perf_counter()
                call()
                samples.append((time.perf_counter() - started) * 1000)
            operations[name] = {'median_ms': round(statistics.median(samples), 2),
                                'min_ms': round(min(samples), 2), 'samples_ms': [round(s, 2) for s in samples]}

        overview = qc.overview(cell)
        assert overview['counts']['epochs'] == cell_epochs, overview['counts']
        measure('overview.cold_cache', lambda: qc.overview(cell), cold=True)
        measure('overview.repeat', lambda: qc.overview(cell))
        measure('epochs.page40', lambda: qc.epochs(cell, 'expanding_spots', 0, 40))
        measure('response.summary', lambda: qc.response(cell, first_epoch))
        # One complete "open QC" = the four backend calls the view issues for its first trial.
        def open_view():
            qc.overview(cell); qc.epochs(cell, 'expanding_spots', 0, 40)
            service.epoch(first_epoch) if hasattr(service, 'epoch') else None
            qc.response(cell, first_epoch)
        measure('open_view.backend', open_view, cold=True)
        index.close()
        return {'epochs': epochs, 'cell_epochs': cell_epochs, 'index_build_seconds': round(build_seconds, 2),
                'operations': operations}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs', type=int, nargs='+', default=[20000, 100000])
    parser.add_argument('--cell-epochs', type=int, nargs='+', default=[200, 1000])
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    results = [run(n, k, args.repeats) for n in args.epochs for k in args.cell_epochs if k < n]
    text = json.dumps({'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'results': results}, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    for item in results:
        print(item['epochs'], item['cell_epochs'], {k: v['median_ms'] for k, v in item['operations'].items()})
