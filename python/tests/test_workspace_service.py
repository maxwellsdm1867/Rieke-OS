"""Safety checks for the local UI service; no research database mutations."""
import copy
import datetime as dt
import hashlib
from pathlib import Path
import tempfile
import unittest
import uuid

import h5py
import numpy as np

from workspace_service import WorkspaceService, bounded_window, number_block_epochs, validate_filters


class EventRelation:
    """Minimal queryable event fixture that records the actual fetch contract."""
    def __init__(self, rows, calls, restrictions=(), projected=None):
        self.rows, self.calls, self.restrictions, self.projected = rows, calls, restrictions, projected

    def __and__(self, restriction):
        return EventRelation(self.rows, self.calls, self.restrictions + (restriction,), self.projected)

    def proj(self, *fields):
        return EventRelation(self.rows, self.calls, self.restrictions, {'event_uuid', *fields})

    def fetch(self, *, as_dict, order_by=None, limit=None, offset=0):
        self.calls.append({'restrictions': self.restrictions, 'order_by': order_by,
                           'limit': limit, 'offset': offset})
        def matches(row, restriction):
            if isinstance(restriction, list):
                return any(matches(row, item) for item in restriction)
            return all(row.get(key) == value for key, value in restriction.items())
        rows = [row for row in self.rows if all(matches(row, restriction) for restriction in self.restrictions)]
        for clause in reversed((order_by or '').split(',')):
            if clause.strip():
                field, direction = clause.strip().split()
                rows.sort(key=lambda row: row[field], reverse=direction == 'DESC')
        rows = rows[offset:None if limit is None else offset + limit]
        return copy.deepcopy([{key: row[key] for key in self.projected} for row in rows]
                             if self.projected is not None else rows)


class EventReadTests(unittest.TestCase):
    def setUp(self):
        self.project = str(uuid.uuid4())
        self.other_project = str(uuid.uuid4())
        self.ids = [str(uuid.UUID(int=i)) for i in range(1, 6)]
        time = dt.datetime(2026, 9, 27, 12, 30)
        self.records = [
            {'project_uuid': self.project, 'event_uuid': key, 'occurred_at': time,
             'actor': 'fixture-user', 'action': 'curation_updated' if index < 3 else 'imported',
             'payload': {'fixture_index': index}}
            for index, key in enumerate(self.ids[:4])]
        self.records.append({'project_uuid': self.other_project, 'event_uuid': self.ids[4],
            'occurred_at': time + dt.timedelta(days=1), 'actor': 'other-user',
            'action': 'curation_updated', 'payload': {'private': 'other-project'}})
        self.calls = []
        self.service = WorkspaceService.__new__(WorkspaceService)
        self.service._loaded = True
        self.service.project = {'project_uuid': self.project}
        self.service.Event = EventRelation(self.records, self.calls)

    def test_event_pages_scope_project_and_stably_order_tied_timestamps(self):
        first = self.service.event_page(limit=2)
        second = self.service.event_page(limit=2, offset=2)
        self.assertEqual([row['event_uuid'] for row in first['events']], self.ids[3:1:-1])
        self.assertEqual([row['event_uuid'] for row in second['events']], self.ids[1::-1])
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertEqual((first['limit'], first['offset'], second['offset']), (2, 0, 2))
        self.assertEqual(self.calls[0]['limit'], 3)  # Fetch one look-ahead record only.
        self.assertEqual(self.calls[0]['order_by'], 'occurred_at DESC, event_uuid DESC')
        self.assertEqual(self.calls[0]['restrictions'], ({'project_uuid': self.project},))
        self.assertTrue(all(row['occurred_at'].endswith('+00:00') for row in first['events']))
        self.assertEqual(self.service.event_page(limit=2, offset=4)['events'], [])

    def test_event_action_filter_and_detail_cannot_read_another_project(self):
        filtered = self.service.event_page(limit=2, action='imported')
        self.assertEqual([row['event_uuid'] for row in filtered['events']], self.ids[3:4])
        self.assertFalse(filtered['has_more'])
        detail = self.service.event_detail(self.ids[0])
        self.assertEqual(detail['payload'], {'fixture_index': 0})
        self.assertEqual(detail['event_uuid'], self.ids[0])
        self.assertEqual(detail['occurred_at'], '2026-09-27T12:30:00+00:00')
        with self.assertRaisesRegex(KeyError, 'not found in this project'):
            self.service.event_detail(self.ids[4])
        with self.assertRaises(KeyError):
            self.service.event_detail(str(uuid.uuid4()))
        self.assertEqual(self.calls[-2]['restrictions'],
                         ({'project_uuid': self.project, 'event_uuid': self.ids[4]},))

    def test_invalid_pagination_and_uuid_fail_before_fetch(self):
        invalid = [{'limit': True}, {'limit': 0}, {'limit': 101}, {'limit': 1.5},
                   {'offset': True}, {'offset': -1}, {'offset': '1'}, {'action': ['imported']},
                   {'action': 'x' * 256}]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.service.event_page(**kwargs)
        for identity in ('not-a-uuid', '', None, '1 OR 1=1'):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                self.service.event_detail(identity)
        self.assertEqual(self.calls, [])


class ReadServiceTests(unittest.TestCase):
    def test_epoch_labels_follow_recording_order_not_uuid_or_filter_order(self):
        rows = {
            'a': {'epoch_uuid': 'a', 'block_uuid': 'block1', 'date': '2026-09-24',
                  'start_time': '09/24/2026 18:13:33:000000'},
            'z': {'epoch_uuid': 'z', 'block_uuid': 'block1', 'date': '2026-09-24',
                  'start_time': '09/24/2026 18:13:32:000000'},
            'b': {'epoch_uuid': 'b', 'block_uuid': 'block2', 'date': '2026-09-24',
                  'start_time': '09/24/2026 19:00:00:000000'},
        }
        number_block_epochs(rows)
        self.assertEqual([rows[key]['epoch_number'] for key in ('z', 'a', 'b')], [1, 2, 1])
        service = WorkspaceService.__new__(WorkspaceService)
        service.rows = rows
        service.sources = []
        service._loaded = True
        service.details = {key: {'parameters': {}, 'properties': {}, 'metadata': {}} for key in rows}
        protocol_id = str(uuid.uuid4())
        for row in rows.values():
            row.update(cell_uuid='cell', cell_label='Cell1', group_uuid='group', group_label='recorded')
            row['block_start_time'] = '09/24/2026 18:13:31:000000' if row['block_uuid'] == 'block1' else '09/24/2026 19:00:00:000000'
        service.filtered_rows = lambda *_: [rows['a'], rows['z']]
        tree = service.tree(protocol_id, splits='block')
        self.assertEqual(tree['children'][0]['epoch_uuids'], ['z', 'a'])
        self.assertEqual(tree['children'][0]['epochs'][1]['epoch_number'], 2)
        self.assertEqual(tree['children'][0]['label'], 'Block · 09/24/2026 18:13:31:000000')
        service.filtered_rows = lambda *_: [rows['a']]
        filtered = service.tree(protocol_id, splits='block')
        self.assertEqual(filtered['children'][0]['epochs'][0]['epoch_number'], 2)

    def test_filter_language_is_closed(self):
        for filters in ({'sql': '1=1'}, {'cell_type': ['RGC']}, {'cell_uuid': 'Cell1'}):
            with self.assertRaises(ValueError):
                validate_filters(filters)
        self.assertEqual(validate_filters({'group_label': 'NBQX 5um', 'cell_type': ''}),
                         {'group_label': 'NBQX 5um'})

    def test_window_bounded_without_decimation(self):
        self.assertEqual(bounded_window(500, 1000, 700), (500, 700))
        for start, count in ((-1, 10), (701, 1), (0, 0), (0, 100001), (0.1, 10), (True, 10)):
            with self.assertRaises(ValueError):
                bounded_window(start, count, 700)

    def test_review_is_explicit(self):
        row = {'epoch_uuid': 'test'}
        self.assertEqual(WorkspaceService._decorate(row, {})['curation']['review_state'], 'unreviewed')
        self.assertFalse(WorkspaceService._decorate(row, {'test': {'reviewed': True}})['curation']['reviewed'])
        self.assertTrue(WorkspaceService._decorate(row, {'test': {'review_state': 'approved'}})['curation']['reviewed'])

    def make_trace_service(self, folder):
        path = Path(folder) / 'source.h5'
        epoch_id, stream_id = str(uuid.uuid4()), str(uuid.uuid4())
        stream_path = f'/epoch-{epoch_id}/responses/stream-{stream_id}'
        with h5py.File(path, 'w') as h5:
            ep = h5.create_group(f'/epoch-{epoch_id}')
            ep.attrs['uuid'] = epoch_id
            stream = h5.create_group(stream_path)
            stream.attrs['uuid'] = stream_id
            stream.attrs['sampleRate'] = 10000.0
            values = np.zeros(200, dtype=[('quantity', 'f8'), ('units', 'S8')])
            values['quantity'] = np.arange(200) / 7
            values['units'] = b'mV'
            stream.create_dataset('data', data=values)
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        service = WorkspaceService.__new__(WorkspaceService)
        service._loaded = True
        service._source_signatures = {}
        service.rows = {epoch_id: {'epoch_uuid': epoch_id, 'source_sha256': source_hash,
            'streams': [{'uuid': stream_id, 'kind': 'responses', 'sample_rate': 10000.0,
                         'sample_count': 200, 'units': 'mV', 'h5_path': stream_path}]}}
        service.manifests = {source_hash: {'source_path': str(path), 'source_sha256': source_hash,
                                         'source_size': path.stat().st_size}}
        return service, path, epoch_id, stream_id

    def test_trace_exact_slice_and_cross_epoch_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            service, _, epoch_id, stream_id = self.make_trace_service(folder)
            result = service.trace(epoch_id, stream_id, 13, 17)
            self.assertEqual(result['values'], (np.arange(13, 30) / 7).tolist())
            self.assertEqual(result['count'], 17)
            self.assertFalse(result['decimated'])
            with self.assertRaises(ValueError):
                service.trace(epoch_id, str(uuid.uuid4()), 0, 10)

    def test_source_change_rejected_even_after_successful_read(self):
        with tempfile.TemporaryDirectory() as folder:
            service, path, epoch_id, stream_id = self.make_trace_service(folder)
            service.trace(epoch_id, stream_id, 0, 10)
            with h5py.File(path, 'r+') as h5:
                dataset = h5[service.rows[epoch_id]['streams'][0]['h5_path'] + '/data']
                sample = dataset[0]
                sample['quantity'] = 500
                dataset[0] = sample
            with self.assertRaisesRegex(ValueError, 'checksum changed'):
                service.trace(epoch_id, stream_id, 0, 10)

    def test_rate_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            service, _, epoch_id, stream_id = self.make_trace_service(folder)
            service.rows[epoch_id]['streams'][0]['sample_rate'] = 20000
            with self.assertRaisesRegex(ValueError, 'sample rate changed'):
                service.trace(epoch_id, stream_id, 0, 10)

    def test_nonfinite_samples_rejected_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            service, path, epoch_id, stream_id = self.make_trace_service(folder)
            with h5py.File(path, 'r+') as h5:
                dataset = h5[service.rows[epoch_id]['streams'][0]['h5_path'] + '/data']
                sample = dataset[0]
                sample['quantity'] = np.nan
                dataset[0] = sample
            new_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            old_manifest = next(iter(service.manifests.values()))
            old_manifest['source_sha256'] = new_hash
            service.manifests = {new_hash: old_manifest}
            service.rows[epoch_id]['source_sha256'] = new_hash
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                service.trace(epoch_id, stream_id, 0, 10)


if __name__ == '__main__':
    unittest.main()
