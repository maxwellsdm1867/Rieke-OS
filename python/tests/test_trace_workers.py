"""Bounded worker protocol/lifecycle plus exact owned-H5 trace reads."""
import copy
import json
import multiprocessing
from multiprocessing.connection import Connection
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

from flask import Flask
import h5py

from workspace_http_boundary import ExactMetadataJSON, encode_exact_response
from workspace_trace_workers import TraceWorkers, TraceWorkerBusy, TraceWorkerUnavailable, TraceReadCancelled
import test_workspace_service as service_tests


class ThreadProcess:
    """Public Process adapter using real Pipe frames and a controllable thread."""
    def __init__(self, target, args, name):
        child = Connection(os.dup(args[0].fileno()))
        self.thread = threading.Thread(target=target, args=(child,), name=name)
        self.pid = None
        self.closed = False
    def start(self):
        self.thread.start()
        self.pid = self.thread.ident
    def is_alive(self): return self.thread.is_alive()
    def join(self, timeout=None): self.thread.join(timeout)
    def close(self):
        if self.is_alive(): raise ValueError('Process still alive')
        self.closed = True


class ThreadContext:
    def get_start_method(self): return 'spawn'
    def Pipe(self, duplex=True): return multiprocessing.get_context('spawn').Pipe(duplex=duplex)
    Process = ThreadProcess


def ready(pool):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if pool.ready(): return
        time.sleep(.005)
    raise AssertionError('Workers did not acknowledge readiness')


def plan(identity):
    return {'path': '/unused', 'signature': [], 'row': {'epoch_uuid': identity},
            'stream': {}, 'start': 0, 'count': 1}


class TraceWorkerTests(unittest.TestCase):
    def source(self, folder):
        service, path, epoch, stream = service_tests.ReadServiceTests().make_trace_service(folder)
        service.project = {'project_uuid': str(uuid.uuid4())}
        service._explore_publication = 'generation-1'
        service._metadata_readiness = {'valid': True}
        return service, path, epoch, stream

    def test_json_response_matches_flask_exact_provider(self):
        app = Flask(__name__)
        app.json = ExactMetadataJSON(app)
        value = {'values': [1.25, -0.0, 1e-300], 'tick': 2**60, 'units': 'µV'}
        for compact in (True, False):
            for ascii_only in (True, False):
                app.json.compact, app.json.ensure_ascii = compact, ascii_only
                with app.app_context():
                    self.assertEqual(app.json.response(value).data,
                        encode_exact_response(value, compact=compact, ensure_ascii=ascii_only))

    def test_spawned_workers_match_exact_oracle_and_close(self):
        with tempfile.TemporaryDirectory() as folder:
            service, _, epoch, stream = self.source(folder)
            pool = TraceWorkers()
            self.assertEqual(pool.stats()['ready'], 0)
            try:
                pool.start(); ready(pool)
                for start, count in ((13, 17), (0, 20000), (200, 1)):
                    job, witness = service.capture_trace_read(epoch, stream, start, count)
                    body = pool.execute(job, {})
                    service.validate_trace_read(witness)
                    self.assertEqual(body, encode_exact_response(service.trace(epoch, stream, start, count)))
                    self.assertEqual(json.loads(body)['values'], [index / 7 for index in range(start, min(start + count, 200))])
                bad = copy.deepcopy(job); bad['row']['epoch_uuid'] = str(uuid.uuid4())
                with self.assertRaisesRegex(ValueError, 'identity changed'): pool.execute(bad, {})
                self.assertTrue(pool.ready(), 'scientific rejection does not poison healthy workers')
                missing = copy.deepcopy(job); missing['path'] += '.missing'
                with self.assertRaises(FileNotFoundError): pool.execute(missing, {})
                with self.assertRaisesRegex(ValueError, 'bounded worker payload'):
                    pool.execute({**job, 'unused': 'x' * 70000}, {})
            finally:
                pool.close()
            self.assertTrue(pool.stats()['closed'])
            pool.close()

    def test_parent_rejects_generation_manifest_row_and_source_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            service, path, epoch, stream = self.source(folder)
            for change in ('generation', 'readiness', 'rows', 'manifest', 'row', 'source'):
                with self.subTest(change=change):
                    job, witness = service.capture_trace_read(epoch, stream)
                    original = (service._explore_publication, service._metadata_readiness,
                                service.rows, copy.deepcopy(service.manifests), copy.deepcopy(service.rows))
                    if change == 'generation': service._explore_publication = 'generation-2'
                    elif change == 'readiness': service._metadata_readiness = {'valid': True}
                    elif change == 'rows': service.rows = copy.deepcopy(service.rows)
                    elif change == 'manifest': service.manifests[job['row']['source_sha256']]['source_size'] += 1
                    elif change == 'row': service.rows[epoch]['streams'][0]['sample_rate'] += 1
                    elif change == 'source':
                        with h5py.File(path, 'r+') as file:
                            file.attrs['changed'] = True
                    with self.assertRaisesRegex(ValueError, 'changed'):
                        service.validate_trace_read(witness)
                    if change != 'source':
                        service._explore_publication, service._metadata_readiness, service.rows = original[:3]
                        service.manifests.clear(); service.manifests.update(original[3])
                        service.rows.clear(); service.rows.update(original[4])

    def test_queue_is_bounded_and_foreground_precedes_waiting_speculation(self):
        entered = {name: threading.Event() for name in ('a', 'b', 'c', 'd')}
        release = {name: threading.Event() for name in ('a', 'b')}
        order, failures, threads = [], [], []
        def read(path, signature, row, stream, start, count):
            name = row['epoch_uuid']; order.append(name); entered[name].set()
            if name in release and not release[name].wait(3): raise RuntimeError('Unreleased test read')
            return {'epoch_uuid': name, 'values': [1.]}
        def run(pool, name, background=False):
            try: pool.execute(plan(name), {}, background=background)
            except BaseException as error: failures.append(error)
        pool = TraceWorkers(context=ThreadContext(), queue_limit=2)
        with patch('workspace_service.read_response_window', side_effect=read):
            try:
                pool.start(); ready(pool)
                for name in ('a', 'b'):
                    thread = threading.Thread(target=run, args=(pool, name));threads.append(thread);thread.start()
                    self.assertTrue(entered[name].wait(1))
                for name, background in (('c', True), ('d', False)):
                    thread = threading.Thread(target=run, args=(pool, name, background));threads.append(thread);thread.start()
                    deadline = time.monotonic() + 1
                    expected = 1 if name == 'c' else 2
                    while pool.stats()['waiting'] < expected and time.monotonic() < deadline: time.sleep(.005)
                    self.assertEqual(pool.stats()['waiting'], expected)
                with self.assertRaises(TraceWorkerBusy): pool.execute(plan('overflow'), {}, wait_timeout=0)
                release['a'].set()
                self.assertTrue(entered['d'].wait(1));self.assertTrue(entered['c'].wait(1))
                self.assertEqual(order[:4], ['a', 'b', 'd', 'c'])
            finally:
                for event in release.values(): event.set()
                for thread in threads: thread.join(3)
                pool.close()
        self.assertEqual(failures, [])

    def test_cancelled_running_read_keeps_slot_and_close_timeout_is_retryable(self):
        entered, release, cancel = threading.Event(), threading.Event(), threading.Event()
        failures = []
        def read(*args):
            entered.set()
            if not release.wait(3): raise RuntimeError('Unreleased test read')
            return {'values': [1.]}
        pool = TraceWorkers(workers=1, queue_limit=0, context=ThreadContext())
        def run():
            try: pool.execute(plan('a'), {}, cancel=cancel)
            except BaseException as error: failures.append(error)
        thread = threading.Thread(target=run)
        with patch('workspace_service.read_response_window', side_effect=read):
            try:
                pool.start(); ready(pool);thread.start();self.assertTrue(entered.wait(1));cancel.set()
                self.assertEqual(pool.stats()['active'], 1)
                with self.assertRaises(TraceWorkerBusy): pool.execute(plan('b'), {}, wait_timeout=0)
                with self.assertRaises(TraceWorkerUnavailable) as failure: pool.close(timeout=.01)
                self.assertEqual(failure.exception.desktop_shutdown_stage, 'trace_workers')
                self.assertFalse(pool.stats()['closed'])
                self.assertEqual(pool.stats()['active'], 1)
            finally:
                release.set();thread.join(3);pool.close()
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], TraceReadCancelled)
        self.assertTrue(pool.stats()['closed'])

    def test_worker_transport_loss_is_not_resubmitted(self):
        class DyingContext(ThreadContext):
            def Process(self, target, args, name):
                def broken(connection):
                    from workspace_trace_workers import _send, _receive
                    _send(connection, {'kind': 'ready', 'protocol': 1})
                    _receive(connection)
                    connection.close()
                return ThreadProcess(broken, args, name)
        pool = TraceWorkers(workers=1, context=DyingContext())
        try:
            pool.start();ready(pool)
            with self.assertRaises(TraceWorkerUnavailable): pool.execute(plan('a'), {})
            self.assertFalse(pool.ready());self.assertTrue(pool.stats()['broken'])
        finally: pool.close()

    def http_app(self):
        import test_workspace_api as api_tests
        from workspace_api import create_app
        from workspace_service import WorkspaceService
        fixture = api_tests.WorkspaceAPITests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        source, _, epoch, stream = self.source(fixture.temp.name)
        service = WorkspaceService.__new__(WorkspaceService)
        service.__dict__.update(fixture.service.__dict__)
        service.rows, service.manifests = source.rows, source.manifests
        service._source_signatures = {}
        service._explore_publication = 'http-generation'
        service._metadata_readiness = {'valid': True}
        app = create_app(fixture.temp.name, fixture.temp.name, service=service, store=fixture.store,
                         explorer_history=fixture.explorer_history, data_stores=fixture.data_stores,
                         protocol_suggestions=fixture.protocol_suggestions)
        self.addCleanup(app.extensions['close_trace_workers'])
        return app, service, epoch, stream

    def test_http_worker_response_matches_inline_and_rejects_retired_result(self):
        app, service, epoch, stream = self.http_app()
        client, pool = app.test_client(), app.extensions['trace_workers']
        url = f'/api/epochs/{epoch}/trace?stream_uuid={stream}&start=13&count=17'
        first = client.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(pool.stats()['started'])
        headers = {'X-Disco-Trace-Priority': 'background'}
        warmup = client.get(url, headers=headers)
        self.assertEqual(warmup.data, first.data)
        ready(pool)
        second = client.get(url, headers=headers)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data, first.data)
        self.assertEqual(second.mimetype, first.mimetype)
        with patch.object(pool, 'execute', side_effect=AssertionError('Foreground entered IPC')):
            self.assertEqual(client.get(url).data, first.data)
        original = pool.execute
        def retire(*args, **kwargs):
            body = original(*args, **kwargs)
            service._explore_publication = 'retired'
            return body
        with patch.object(pool, 'execute', side_effect=retire):
            stale = client.get(url, headers=headers)
        self.assertEqual(stale.status_code, 400)
        self.assertIn('generation changed', stale.json['error'])
        self.assertNotIn('values', stale.json)

    def test_http_custom_serializer_stays_inline_without_starting_workers(self):
        app, _, epoch, stream = self.http_app()
        class CustomJSON(ExactMetadataJSON):
            def dumps(self, value, **kwargs):
                return super().dumps({**value, 'custom': True}, **kwargs)
        app.json = CustomJSON(app)
        response = app.test_client().get(f'/api/epochs/{epoch}/trace?stream_uuid={stream}',
                                       headers={'X-Disco-Trace-Priority': 'background'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['custom'])
        self.assertFalse(app.extensions['trace_workers'].stats()['started'])

    def test_corrupt_worker_header_releases_child_sending_a_large_body(self):
        for header in ('oversize', [], None, {'error': []}, {'ok': 'yes'}):
            with self.subTest(header=header):
                class CorruptContext(ThreadContext):
                    def Process(self, target, args, name):
                        def corrupt(connection):
                            from workspace_trace_workers import _send, _receive
                            try:
                                _send(connection, {'kind': 'ready', 'protocol': 1})
                                job = _receive(connection)
                                if header == 'oversize':
                                    connection.send_bytes(b'x' * (64 * 1024 + 1))
                                else:
                                    envelope = ({'kind': 'result', 'job_id': job['job_id'],
                                                 'ok': False, 'message': 'bad', **header}
                                                if isinstance(header, dict) else header)
                                    _send(connection, envelope)
                                connection.send_bytes(b'x' * (4 * 1024 * 1024))
                            except (OSError, EOFError):
                                pass
                            finally:
                                connection.close()
                        return ThreadProcess(corrupt, args, name)
                pool = TraceWorkers(workers=1, context=CorruptContext())
                try:
                    pool.start();ready(pool)
                    with self.assertRaises(TraceWorkerUnavailable): pool.execute(plan('a'), {})
                finally: pool.close(timeout=2)
                self.assertTrue(pool.stats()['closed'])

    def test_background_waiters_cannot_consume_reserved_foreground_capacity(self):
        entered, release, rejected = threading.Event(), threading.Event(), threading.Event()
        failures, threads = [], []
        def read(*args):
            entered.set()
            if not release.wait(3): raise RuntimeError('Unreleased test read')
            return {'values': [1.]}
        pool = TraceWorkers(workers=1, queue_limit=2, context=ThreadContext())
        def run(name, background=False):
            try: pool.execute(plan(name), {}, background=background)
            except BaseException as error:
                if name == 'overflow' and isinstance(error, TraceWorkerBusy): rejected.set()
                else: failures.append(error)
        with patch('workspace_service.read_response_window', side_effect=read):
            try:
                pool.start();ready(pool)
                for name, background in [('active', False), ('waiting', True), ('overflow', True)]:
                    thread = threading.Thread(target=run, args=(name, background));threads.append(thread);thread.start()
                    if name == 'active': self.assertTrue(entered.wait(1))
                    elif name == 'waiting':
                        deadline = time.monotonic() + 1
                        while pool.stats()['waiting'] != 1 and time.monotonic() < deadline: time.sleep(.005)
                    else:
                        deadline = time.monotonic() + 1
                        while not rejected.is_set() and pool.stats()['waiting'] == 1 and time.monotonic() < deadline: time.sleep(.005)
                        self.assertEqual(pool.stats()['waiting'], 1)
                        self.assertTrue(rejected.is_set())
                foreground = threading.Thread(target=run, args=('foreground', False));threads.append(foreground);foreground.start()
                deadline = time.monotonic() + 1
                while pool.stats()['waiting'] != 2 and time.monotonic() < deadline: time.sleep(.005)
                self.assertEqual(pool.stats()['waiting'], 2)
            finally:
                release.set()
                for thread in threads: thread.join(3)
                pool.close()
        self.assertEqual(failures, [])

    def test_never_started_close_does_not_spawn(self):
        pool = TraceWorkers();pool.close()
        self.assertFalse(pool.stats()['started']);self.assertTrue(pool.stats()['closed'])


if __name__ == '__main__':
    unittest.main()
