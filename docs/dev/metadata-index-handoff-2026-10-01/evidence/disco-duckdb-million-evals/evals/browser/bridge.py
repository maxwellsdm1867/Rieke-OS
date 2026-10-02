"""Owned experimental HTTP bridge; no production app or annotation writes.

Translate identical SQL projections into the production shared React page shape.
Only the explicit fixture protocol, empty filters, cell/block splits are supported.
Semantic oracle is arithmetic fixture generation, independent of SQL results.
"""
import argparse
from collections import OrderedDict
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import json
from pathlib import Path
import signal
import subprocess

ADAPTER = Path(__file__).resolve().parents[1] / 'readmodel' / 'projection.py'
spec = importlib.util.spec_from_file_location('analytical_projection', ADAPTER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Bridge:
    def __init__(self, projection, epochs):
        self.projection, self.epochs = projection, epochs
        self.revision = digest({'fixture_version': module.VERSION, 'epochs': epochs, 'schema': module.SCHEMA, 'splits': ['cell', 'block']})
        # Independent 10k-cell oracle index is ~1% of the million-row dataset.
        # No epoch records are materialized; parent lookups retain only groups.
        self.cell_index = {module.identity(epochs + cell): cell for cell in range((epochs + 99) // 100)}
        self.ordered_cells = tuple(sorted(self.cell_index))
        self.paths = OrderedDict()
        self.cursors = OrderedDict()
        self.checks = []

    def remember(self, mapping, key, value, limit=512):
        mapping[key] = value
        mapping.move_to_end(key)
        while len(mapping) > limit:
            mapping.popitem(last=False)

    def config(self):
        return {'epochs': self.epochs, 'engine': self.projection.engine, 'protocol_uuid': module.PROTOCOL_UUID,
                'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ADAPTER.parents[3], text=True).strip(),
                'catalog': {'fields': [{'id': 'parameters/' + name, 'path': 'parameters.' + name, 'label': name} for name, _ in module.PARAMS]},
                'scope': 'Experimental typed metadata HTTP bridge; exact deterministic million-epoch fixture; no native MySQL annotations, waveform I/O or production Flask service.'}

    def oracle(self, body):
        path = body.get('path', [])
        depth = len(path)
        offset, limit = body.get('offset', 0), body.get('limit', 60)
        parent = self.paths[tuple(path)] if path else {}
        if depth == 0:
            groups = self.ordered_cells
            return {'kind': 'branches', 'keys': list(groups[offset:offset + limit]), 'total': len(groups), 'counts': [100] * len(groups[offset:offset + limit])}
        cell_index = self.cell_index[parent['cell_uuid']]
        if depth == 1:
            # Independent fixture chronology, matching production block ordering.
            groups = [module.identity(2 * self.epochs + block) for block in range(cell_index * 5, cell_index * 5 + 5)]
            return {'kind': 'branches', 'keys': list(groups[offset:offset + limit]), 'total': 5, 'counts': [20] * len(groups[offset:offset + limit])}
        blocks = range(cell_index * 5, cell_index * 5 + 5)
        block = next(block for block in blocks if module.identity(2 * self.epochs + block) == parent['block_uuid'])
        ids = [module.identity(index) for index in range(block * 20, block * 20 + 20)]
        return {'kind': 'epochs', 'ids': ids[offset:offset + limit], 'total': 20}

    def page(self, body):
        if body.get('protocol_uuid') != module.PROTOCOL_UUID or body.get('filters') or body.get('splits') != 'cell,block':
            raise ValueError('Bridge supports only explicit fixture protocol, empty filters, cell/block splits')
        path = body.get('path', [])
        offset, limit = body.get('offset', 0), body.get('limit', 60)
        if not isinstance(path, list) or len(path) > 2 or limit != 60 or not isinstance(offset, int) or offset < 0:
            raise ValueError('Unsupported bounded page request')
        if body.get('revision', self.revision) != self.revision:
            raise ValueError('Stale revision')
        parent = self.paths[tuple(path)] if path else {}
        cursor_key = (tuple(path), offset)
        if offset and cursor_key not in self.cursors:
            raise ValueError('Sequential continuation required')
        cursor = self.cursors.get(cursor_key)
        depth = len(path)
        raw = self.projection.tree_children('cell' if depth == 0 else 'block', parent=parent, limit=limit, cursor=cursor) if depth < 2 else self.projection.page(parent=parent, limit=limit, cursor=cursor)
        branches, epochs = [], []
        if depth < 2:
            field = 'cell' if depth == 0 else 'block'
            for item in raw['items']:
                key = digest({'field': field, 'present': True, 'value': item['key']})
                child_path = [*path, key]
                self.remember(self.paths, tuple(child_path), {**parent, field + '_uuid': item['key']})
                branches.append({'key': key, 'label': item['label'], 'value': item['key'], 'missing': False,
                                 'path': child_path, 'has_children': depth == 0,
                                 'count': item['count'], 'cells': item['cells'], 'duration_seconds': item['duration_seconds'],
                                 **({'start_time': item['start_time']} if field == 'block' else {})})
            total = raw['total']
        else:
            for row in raw['items']:
                epochs.append({name: row[name] for name in ('epoch_uuid', 'start_time', 'cell_uuid', 'cell_label', 'date', 'block_uuid', 'epoch_number')} | {'label': f"Epoch {row['epoch_number']} · {row['start_time'][11:]}"})
            total = 20
        if raw['next_cursor'] is not None:
            self.remember(self.cursors, (tuple(path), offset + limit), raw['next_cursor'])
        expected = self.oracle(body)
        actual_keys = [item['value'] for item in branches] if depth < 2 else [item['epoch_uuid'] for item in epochs]
        expected_keys = expected.get('keys', expected.get('ids'))
        assert actual_keys == expected_keys and total == expected['total'], 'Independent IDs/order/count oracle failed'
        if branches:
            assert [item['count'] for item in branches] == expected['counts'], 'Independent group membership count oracle failed'
        self.checks.append({'passed': True, 'path': path, 'offset': offset, 'kind': expected['kind'], 'total': total})
        count = self.epochs if depth == 0 else 100 if depth == 1 else 20
        return {'revision': self.revision, 'split_order': ['cell', 'block'], 'levels': [{'field': 'cell', 'label': 'Cell'}, {'field': 'block', 'label': 'Block'}],
                'total_epochs': self.epochs, 'count': self.epochs, 'cells': len(self.cell_index), 'duration_seconds': float(self.epochs),
                'path': path, 'depth': depth, 'offset': offset, 'limit': limit, 'branches': branches, 'epochs': epochs,
                'selection': {'count': count, 'cells': len(self.cell_index) if depth == 0 else 1, 'duration_seconds': float(count)},
                'ancestors': [], 'source_scope_revision': None, 'kind': expected['kind'], 'total': total,
                'has_more': offset + limit < total}

    def detail(self, epoch_uuid):
        data = self.projection.detail(epoch_uuid)
        if data is None:
            raise KeyError('Missing epoch')
        index = data['synthetic_index']
        expected = dict(zip(module.NAMES, module.fixture_row(index, self.epochs)))
        assert data['epoch_uuid'] == module.identity(index), 'Independent detail UUID oracle failed'
        for field in ('cell_uuid', 'block_uuid', 'start_time', 'duration_seconds', 'protocol_uuid'):
            assert data[field] == expected[field], 'Independent detail field oracle failed: ' + field
        assert data['parameters'] == {name: expected[name] for name, _ in module.PARAMS}, 'Independent parameters oracle failed'
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=['sqlite', 'duckdb'], required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=1000000)
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    projection = module.AnalyticalProjection(args.engine, args.database)
    bridge = Bridge(projection, args.epochs)
    config = bridge.config()

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, body):
            content = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            try:
                if self.path in ('/bench-config', '/health'):
                    self.send_json(200, config)
                elif self.path == '/eval/checks':
                    self.send_json(200, {'checks': bridge.checks, 'passed': all(x['passed'] for x in bridge.checks)})
                elif self.path.startswith('/api/epochs/'):
                    self.send_json(200, bridge.detail(self.path.rsplit('/', 1)[-1]))
                else:
                    self.send_json(404, {'error': 'Unknown route'})
            except Exception as error:
                self.send_json(500, {'error': str(error)})

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/api/tree-pages':
                    self.send_json(200, bridge.page(body))
                elif self.path == '/eval/oracle':
                    self.send_json(200, bridge.oracle(body))
                else:
                    self.send_json(404, {'error': 'Unknown route'})
            except Exception as error:
                self.send_json(500, {'error': str(error)})

        def log_message(self, format, *args):
            pass

    server = HTTPServer(('127.0.0.1', args.port), Handler)
    (args.output_dir / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    (args.output_dir / 'ready.json').write_text(json.dumps({'api_origin': f'http://127.0.0.1:{server.server_port}', 'config': str(args.output_dir / 'config.json')}) + '\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        (args.output_dir / 'bridge-checks.json').write_text(json.dumps({'checks': bridge.checks, 'passed': all(x['passed'] for x in bridge.checks)}, indent=2) + '\n')
        server.server_close()
        projection.close()


if __name__ == '__main__':
    main()
