"""Owned H5/index tests for historical display membership; no research state."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
import uuid
from unittest.mock import patch

import h5py
import numpy as np
from flask import Flask
from disco.metadata.disk_index import DiskMetadataIndex
from disco.workbench.workbench import register_workbench_routes
from workspace_service import WorkspaceService
from workspace_trace_views import TraceViews, TraceViewConflict
from test_workspace_api import FixtureService


class TraceViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        fixture = FixtureService(root)
        service = WorkspaceService.__new__(WorkspaceService)
        service.__dict__.update(fixture.__dict__)
        self.service = service
        self.path = root / 'fixture.h5'
        self.streams = [str(uuid.uuid4()) for _ in service.ids]
        values = np.zeros(200, dtype=[('quantity', '<f8'), ('units', 'S10')])
        values['quantity'], values['units'] = np.arange(200) / 7, b'pA'
        with h5py.File(self.path, 'w') as h5:
            for i, (epoch, stream) in enumerate(zip(service.ids, self.streams)):
                h5.create_group(str(i)).attrs['uuid'] = epoch
                g = h5.create_group(f'{i}/responses/stream')
                g.attrs['uuid'], g.attrs['sampleRate'] = stream, 10000.
                g.create_dataset('data', data=values, chunks=(64,), compression='gzip')
                service.rows[epoch]['streams'] = [dict(uuid=stream, kind='responses',
                    h5_path=f'/{i}/responses/stream', sample_rate=10000., sample_count=200, units='pA')]
        sha = hashlib.sha256(self.path.read_bytes()).hexdigest()
        service.sources[0]['source_sha256'] = sha
        service.manifests = {sha: dict(source_path=str(self.path), source_sha256=sha, source_size=self.path.stat().st_size)}
        for row in service.rows.values():
            row['source_sha256'] = sha
        service.disk_index = DiskMetadataIndex.build(root / 'owned.sqlite', service.rows,
            service.details, service.sources, 'test-generation', service.project['project_uuid'])
        self.addCleanup(service.disk_index.close)
        service._fingerprints = {identity: service.disk_index.trace_record(identity)['fingerprint'] for identity in service.ids}
        service._source_signatures = {}
        service._explore_publication = str(uuid.uuid4())
        service.dj = types.SimpleNamespace()
        self.context = dict(actor='owner', protocol_uuid=service.protocol_id,
            candidate_revision_uuid=str(uuid.uuid4()), candidate_recipe_sha256='c'*64,
            baseline_recipe_sha256='d'*64, main_recipe_sha256='e'*64,
            expected_binding_version=1, main_revision_uuid=str(uuid.uuid4()),
            pending=dict(service._fingerprints))
        self.views = TraceViews(service)
        self.public = self.views.prepare(self.context)
        self.epoch, self.stream = service.ids[0], self.streams[0]

    def capture(self):
        return self.views.capture(self.public['token'], self.epoch, 'owner')

    def test_exact_samples_and_context_echo(self):
        witness = self.capture()
        value = self.service.trace_batch(self.epoch, self.stream, 0, 100, 2)
        result = self.views.finish(self.public['token'], self.epoch, 'owner', witness, value)
        self.assertEqual([v for w in result['windows'] for v in w['values']], (np.arange(200)/7).tolist())
        self.assertEqual(result['read_context'], self.public)
        self.assertTrue(all(w['read_context'] == self.public for w in result['windows']))
        self.assertNotIn('candidate_scope_revision', self.public)

    def test_historical_membership_survives_later_recipe_binding_and_tag_changes(self):
        self.context.update(candidate_recipe_sha256='f'*64, expected_binding_version=2,
                            pending={}, draft_version=99, tags=['later'])
        other = self.views.prepare(self.context)
        self.assertNotEqual(self.public['token'], other['token'])
        self.capture()  # Old display describes the captured view, never current draft state.

    def test_selected_subset_and_stable_tag_refresh_token(self):
        context = dict(self.context, _view_ids={self.epoch}, draft_version=1)
        public = self.views.prepare(context)
        self.assertEqual(public['view_kind'], 'workbench_selected')
        self.assertEqual(public, self.views.prepare(dict(context, draft_version=2, tags=['later'])))
        with self.assertRaises(TraceViewConflict):
            self.views.capture(public['token'], self.service.ids[1], 'owner')

    def test_empty_filtered_selection_cannot_read_original_pending_epoch(self):
        # Preparation has evaluated all filters, excluding the original UUID.
        public = self.views.prepare(dict(self.context, _view_ids=set()))
        self.assertEqual(public['view_kind'], 'workbench_selected')
        with self.assertRaises(TraceViewConflict):
            self.views.capture(public['token'], self.epoch, 'owner')

    def test_target_change_and_publication_change_fail_closed(self):
        for field, replacement in [('epoch_number', 900), ('streams', [])]:
            with self.subTest(field=field):
                original = self.service.rows[self.epoch][field]
                self.service.rows[self.epoch][field] = replacement
                with self.assertRaises(TraceViewConflict): self.capture()
                self.service.rows[self.epoch][field] = original
        self.service._explore_publication = 'new'
        with self.assertRaises(TraceViewConflict): self.capture()

    def test_other_epoch_change_does_not_rewrite_captured_target(self):
        self.service.rows[self.service.ids[1]]['epoch_number'] = 99
        self.capture()

    def test_owner_session_and_custom_adapter_rejected(self):
        with self.assertRaises(TraceViewConflict):
            self.views.capture(self.public['token'], self.epoch, 'different-owner')
        with self.assertRaises(TraceViewConflict):
            TraceViews(self.service).capture(self.public['token'], self.epoch, 'owner')
        self.service.trace = lambda *a: {}
        self.assertIsNone(self.views.prepare(self.context))
        with self.assertRaises(TraceViewConflict): self.capture()

    def test_custom_sample_reader_fails_closed(self):
        with patch('workspace_service.read_response_window', return_value={}):
            self.assertIsNone(self.views.prepare(self.context))
            with self.assertRaises(TraceViewConflict): self.capture()

    def test_unsupported_service_does_not_require_native_publication_fields(self):
        self.assertIsNone(TraceViews(types.SimpleNamespace()).prepare(self.context))

    def test_late_source_change_rejected(self):
        witness = self.capture()
        value = self.service.trace(self.epoch, self.stream, 0, 100)
        os.utime(self.path, ns=(self.path.stat().st_atime_ns, self.path.stat().st_mtime_ns+1000000))
        with self.assertRaises(TraceViewConflict):
            self.views.finish(self.public['token'], self.epoch, 'owner', witness, value)

    def test_registration_change_and_index_close_rejected(self):
        manifest = next(iter(self.service.manifests.values()))
        manifest['extra'] = 'changed'
        with self.assertRaises(TraceViewConflict): self.capture()
        del manifest['extra']
        self.service.disk_index.close()
        with self.assertRaises(ValueError): self.capture()

    def test_bounded_registry_eviction(self):
        with patch('workspace_trace_views.MAX_VIEWS', 1):
            self.views.prepare(dict(self.context, _view_ids={self.epoch}))
        self.assertEqual(len(self.views.entries), 1)
        with self.assertRaises(TraceViewConflict): self.capture()

    def test_source_proofs_cover_only_captured_members_and_are_budgeted(self):
        from workspace_trace_views import ENTRY_BYTES
        # An unrelated registration must not be inspected or retained as a
        # copied witness just because this service also knows about it.
        self.service.manifests['f' * 64] = {'unrelated': object()}
        public = self.views.prepare(dict(self.context, _view_ids={self.epoch}))
        entry = self.views.entries[public['token']]
        self.assertEqual(len(entry['members']), 48)
        self.assertEqual(len(entry['source_records']), 64)
        self.assertEqual(entry['byte_cost'], 48 + 64 + ENTRY_BYTES)
        self.assertEqual(self.views.bytes, sum(value['byte_cost'] for value in self.views.entries.values()))
        self.views.capture(public['token'], self.epoch, 'owner')
        self.service.manifests[next(iter(self.service.manifests))]['changed'] = True
        with self.assertRaises(TraceViewConflict):
            self.views.capture(public['token'], self.epoch, 'owner')

    def test_source_proof_and_entry_cost_control_admission_and_eviction(self):
        from workspace_trace_views import ENTRY_BYTES
        context = dict(self.context, _view_ids={self.epoch})
        cost = 48 + 64 + ENTRY_BYTES
        views = TraceViews(self.service)
        with patch('workspace_trace_views.MAX_BYTES', cost - 1):
            self.assertIsNone(views.prepare(context))
        self.assertEqual(views.bytes, 0)
        with patch('workspace_trace_views.MAX_BYTES', cost):
            first = views.prepare(context)
            second = views.prepare(dict(self.context, _view_ids={self.service.ids[1]}))
        self.assertEqual(views.bytes, cost)
        self.assertEqual(list(views.entries), [second['token']])
        with self.assertRaises(TraceViewConflict):
            views.capture(first['token'], self.epoch, 'owner')

    def test_revoked_publication_releases_old_mapping_roots(self):
        import gc
        import weakref
        class Rows(dict): pass
        old_rows = Rows(self.service.rows)
        self.service.rows = old_rows
        public = self.views.prepare(self.context)
        reference = weakref.ref(old_rows)
        self.service.rows = dict(old_rows)
        del old_rows
        with self.assertRaises(TraceViewConflict):
            self.views.capture(public['token'], self.epoch, 'owner')
        gc.collect()
        self.assertIsNone(reference())
        self.assertEqual(self.views.bytes, 0)
        self.assertFalse(self.views.entries)

    def test_http_read_does_not_acquire_catalog_or_annotation_locks(self):
        app = Flask(__name__)
        app.extensions['curation_store'] = None
        app.register_error_handler(ValueError, lambda error: ({'error':str(error)}, 400))
        lock = threading.Lock()
        def forbidden(*a, **kw): raise AssertionError('Display touched current SQL/context/annotations')
        register_workbench_routes(app, self.service, None, None, forbidden, forbidden,
                                  lock, forbidden)
        views = app.extensions['trace_views']
        # Only fixture eligibility is substituted; canonical reader/index/source guards run.
        views.policy = lambda: True
        public = views.prepare(self.context)
        manager = app.extensions['protocol_workbench']
        manager.context = forbidden
        with lock, patch('disco.decisions.author_preferences.selected_author', return_value={'profile_uuid':'owner'}):
            result = []
            def read():
                with app.test_client() as client:
                    result.append(client.get(f"/api/trace-views/{public['token']}/epochs/{self.epoch}/trace",
                        query_string=dict(stream_uuid=self.stream, start=0, count=100, chunks=2)))
            thread = threading.Thread(target=read, daemon=True)
            thread.start(); thread.join(3)
            self.assertFalse(thread.is_alive(), 'Display blocked behind current catalog/tag work')
        self.assertEqual(result[0].status_code, 200, result[0].get_json())
        self.assertEqual(result[0].get_json()['read_context'], public)
        with app.test_client() as client, patch('disco.decisions.author_preferences.selected_author', return_value={'profile_uuid':'owner'}):
            invalid = client.get(f"/api/trace-views/{public['token']}/epochs/{self.epoch}/trace",
                query_string=dict(stream_uuid=self.stream, selection_token='mutation-authority'))
        self.assertGreaterEqual(invalid.status_code, 400)

    def test_foreground_option_keeps_custom_batch_adapter_signature(self):
        from workspace_trace_binary import read_trace_batch
        calls = []
        def custom(epoch, stream, start, count, chunks):
            calls.append((epoch, stream, start, count, chunks))
            return {'custom':True}
        adapter = types.SimpleNamespace(trace_batch=custom)
        self.assertEqual(read_trace_batch(adapter,self.epoch,self.stream,0,100,2,
            binary=True,foreground=True), {'custom':True})
        self.assertEqual(len(calls),1)

    def test_only_admitted_prepared_reads_pass_foreground_to_native_extraction(self):
        from workspace_trace_geometry import CONTENT_TYPE, ALGORITHM
        from workspace_trace_binary import BINARY_CONTENT_TYPE
        import workspace_trace_native as native
        app = Flask(__name__)
        app.extensions['curation_store'] = None
        app.register_error_handler(ValueError, lambda error: ({'error':str(error)},400))
        register_workbench_routes(app,self.service,None,None,lambda:None,lambda:None,
                                  threading.Lock(),lambda:None)
        views = app.extensions['trace_views']; views.policy = lambda:True
        public = views.prepare(self.context)
        root = f"/api/trace-views/{public['token']}/epochs/{self.epoch}"
        with patch.object(native,'read_native_values',return_value=None) as read:
            self.service.trace_batch(self.epoch,self.stream,0,100,2,array_windows=True)
            self.assertNotIn('foreground',read.call_args.kwargs)
            with app.test_client() as client, patch('disco.decisions.author_preferences.selected_author',return_value={'profile_uuid':'owner'}):
                for path, query, media in [
                    ('/display',dict(stream_uuid=self.stream,count=200,physical_width=7.5,algorithm=ALGORITHM),CONTENT_TYPE),
                    ('/trace',dict(stream_uuid=self.stream,count=100,chunks=2),BINARY_CONTENT_TYPE)]:
                    read.reset_mock()
                    result = client.get(root+path,query_string=query,headers={'Accept':media})
                    self.assertEqual(result.status_code,200,result.get_json())
                    self.assertEqual(read.call_args.kwargs,{'foreground':True})
                    read.reset_mock()
                    blocked = client.get(root+path,query_string=query,headers={'Accept':media,'X-Disco-Trace-Priority':'background'})
                    self.assertEqual(blocked.status_code,400)
                    read.assert_not_called()
            with app.test_client() as client, patch('disco.decisions.author_preferences.selected_author',return_value={'profile_uuid':'other'}):
                read.reset_mock()
                denied = client.get(root+'/trace',query_string=dict(stream_uuid=self.stream,count=100,chunks=2),headers={'Accept':BINARY_CONTENT_TYPE})
                self.assertEqual(denied.status_code,409)
                read.assert_not_called()

    def test_display_geometry_is_separate_exact_and_independent_of_current_locks(self):
        from workspace_trace_geometry import CONTENT_TYPE, ALGORITHM
        from test_trace_geometry import decode, reference_indices
        app = Flask(__name__)
        app.extensions['curation_store'] = None
        app.register_error_handler(ValueError, lambda error: ({'error': str(error)}, 400))
        lock = threading.Lock()
        def forbidden(*a, **kw): raise AssertionError('Geometry touched current SQL/context/annotations')
        register_workbench_routes(app, self.service, None, None, forbidden, forbidden, lock, forbidden)
        views = app.extensions['trace_views']; views.policy = lambda: True
        public = views.prepare(self.context)
        app.extensions['protocol_workbench'].context = forbidden
        path = f"/api/trace-views/{public['token']}/epochs/{self.epoch}/display"
        query = dict(stream_uuid=self.stream, count=200, physical_width=7.5, algorithm=ALGORITHM)
        with lock, patch('disco.decisions.author_preferences.selected_author', return_value={'profile_uuid': 'owner'}):
            result = []
            def read():
                with app.test_client() as client:
                    result.append(client.get(path, query_string=query, headers={'Accept': CONTENT_TYPE}))
            thread = threading.Thread(target=read, daemon=True); thread.start(); thread.join(3)
            self.assertFalse(thread.is_alive(), 'Geometry blocked behind catalog/tag work')
        self.assertEqual(result[0].status_code, 200, result[0].get_json())
        header, indices, values = decode(result[0].data)
        raw = np.arange(200)/7
        self.assertEqual(indices.tolist(), reference_indices(raw, 7.5))
        self.assertEqual(values.tobytes(), raw[indices].tobytes())
        self.assertEqual(header['read_context'], public)
        self.assertNotIn('Server-Timing', result[0].headers)
        with app.test_client() as client, patch('disco.decisions.author_preferences.selected_author', return_value={'profile_uuid': 'owner'}):
            timed = client.get(path, query_string=query,
                headers={'Accept': CONTENT_TYPE, 'X-Disco-Trace-Timing': '1'})
            self.assertEqual(timed.status_code, 200)
            self.assertEqual(timed.data, result[0].data, 'Diagnostics must preserve every wire byte')
            self.assertIn('trace_native_scope_wall;dur=', timed.headers['Server-Timing'])
            self.assertIn('trace_native_scope_thread_cpu;dur=', timed.headers['Server-Timing'])
            self.assertIn('trace_native_scope_process_cpu;dur=', timed.headers['Server-Timing'])
            self.assertLess(len(timed.headers['Server-Timing']), 8192)
            for options in ({}, {'Accept': 'application/json'}, {'Accept': CONTENT_TYPE, 'X-Disco-Trace-Priority': 'background'}):
                self.assertEqual(client.get(path, query_string=query, headers=options).status_code, 400)
            self.assertEqual(client.get(path, query_string=dict(query, count=199), headers={'Accept':CONTENT_TYPE}).status_code, 400)
            self.assertEqual(client.get(path, query_string=dict(query, selection_token='mutation'), headers={'Accept':CONTENT_TYPE}).status_code, 400)

    def test_display_geometry_closing_source_check_and_typed_unavailable(self):
        import workspace_trace_geometry
        app = Flask(__name__); app.extensions['curation_store'] = None
        app.register_error_handler(ValueError, lambda error: ({'error': str(error)}, 400))
        register_workbench_routes(app, self.service, None, None, lambda *a: None, lambda *a: None,
                                  threading.Lock(), lambda *a: None)
        views = app.extensions['trace_views']; views.policy = lambda: True
        public = views.prepare(self.context)
        path = f"/api/trace-views/{public['token']}/epochs/{self.epoch}/display"
        query = dict(stream_uuid=self.stream, count=200, physical_width=7.5, algorithm=workspace_trace_geometry.ALGORITHM)
        headers={'Accept':workspace_trace_geometry.CONTENT_TYPE}
        original = workspace_trace_geometry.prepare_display_geometry
        def changed(*args):
            value=original(*args)
            os.utime(self.path, ns=(self.path.stat().st_atime_ns, self.path.stat().st_mtime_ns+1000000))
            return value
        with app.test_client() as client, patch('disco.decisions.author_preferences.selected_author', return_value={'profile_uuid':'owner'}):
            unavailable=client.get(path, query_string=dict(query, physical_width=100), headers=headers)
            self.assertEqual(unavailable.status_code, 409)
            self.assertEqual(unavailable.get_json()['code'], 'trace_geometry_unavailable')
            with patch('workspace_trace_geometry.prepare_display_geometry', side_effect=changed):
                result=client.get(path, query_string=query, headers=headers)
            self.assertGreaterEqual(result.status_code, 400)
            self.assertNotEqual(result.get_json().get('code'), 'trace_geometry_unavailable')


if __name__ == '__main__': unittest.main()
