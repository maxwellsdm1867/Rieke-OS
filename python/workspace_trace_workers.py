"""Owned bounded CPU workers for already-admitted legacy trace windows.

No connection, lease, request context or live service enters a child. Source
admission and publication belong to WorkspaceService and the HTTP parent.
"""
from __future__ import annotations

import json
import multiprocessing
import threading
import time
import uuid
from disco.operation_timing import elapsed

MAX_PLAN_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
PROTOCOL = 1


class TraceWorkerUnavailable(RuntimeError):
    pass


class TraceWorkerBusy(TraceWorkerUnavailable):
    pass


class TraceReadCancelled(TraceWorkerUnavailable):
    pass


class _RemoteReadError(Exception):
    def __init__(self, kind, message):
        self.kind, self.message = kind, message


def _send(connection, value):
    connection.send_bytes(json.dumps(value, allow_nan=False, separators=(',', ':')).encode('utf-8'))


def _receive(connection, maximum=MAX_PLAN_BYTES):
    return json.loads(connection.recv_bytes(maxlength=maximum))


def _worker(connection):
    # Spawn imports the owning module, never the running parent's DB objects.
    from workspace_service import read_response_window
    from workspace_http_boundary import encode_exact_response
    try:
        _send(connection, {'kind': 'ready', 'protocol': PROTOCOL})
        while True:
            message = _receive(connection)
            if message == {'kind': 'stop'}:
                return
            identity = message.get('job_id')
            if message.get('kind') != 'read' or not isinstance(identity, str):
                return
            try:
                plan = message['plan']
                result = read_response_window(plan['path'], tuple(plan['signature']), plan['row'],
                                              plan['stream'], plan['start'], plan['count'])
                body = encode_exact_response(result, **message['encoding'])
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ValueError('Trace response exceeds the bounded worker payload')
                _send(connection, {'kind': 'result', 'job_id': identity, 'ok': True})
                connection.send_bytes(body)
            except Exception as error:
                name = type(error).__name__
                _send(connection, {'kind': 'result', 'job_id': identity, 'ok': False,
                                   'error': name, 'message': str(error)[:2048]})
    except (EOFError, BrokenPipeError, OSError):
        return
    finally:
        connection.close()


class TraceWorkers:
    """Two physical jobs, a bounded priority queue, and acknowledged close.

    The caller must not hold a DB lock during ready/start, execute or close.
    Worker capacity is retained until a physical reply or observed process exit,
    even when the requesting consumer has been cancelled.
    """
    def __init__(self, *, workers=2, queue_limit=4, context=None):
        if type(workers) is not int or workers not in (1, 2):
            raise ValueError('Trace workers must be one or two')
        if type(queue_limit) is not int or not 0 <= queue_limit <= 4:
            raise ValueError('Trace waiting queue must be bounded by four')
        self.context = context or multiprocessing.get_context('spawn')
        if self.context.get_start_method() != 'spawn':
            raise ValueError('Trace workers require spawn, never inherited process state')
        self.worker_count, self.queue_limit = workers, queue_limit
        self.condition = threading.Condition()
        self.close_lock = threading.Lock()
        self.workers, self.waiting = [], []
        self.started = self.closing = self.closed = self.broken = False
        self.serial = 0

    def start(self):
        with self.condition:
            if self.closing or self.broken:
                raise TraceWorkerUnavailable('Trace worker admission is closed')
            if self.started:
                return
            self.started = True
            try:
                for _ in range(self.worker_count):
                    parent, child = self.context.Pipe(duplex=True)
                    process = self.context.Process(target=_worker, args=(child,), name='Disco trace reader')
                    worker = {'process': process, 'connection': parent, 'child': child,
                              'ready': False, 'busy': False, 'stop_sent': False, 'started': False}
                    # Keep every handle before attempting start, including uncertain starts.
                    self.workers.append(worker)
                    process.start()
                    worker['started'] = True
                    child.close()
            except BaseException:
                self.broken = True
                self.condition.notify_all()
                raise

    def _check_ready_locked(self):
        if self.closing or self.broken:
            return False
        for worker in self.workers:
            process, connection = worker['process'], worker['connection']
            if not process.is_alive():
                self.broken = True
                self.condition.notify_all()
                return False
            if not worker['ready'] and connection.poll(0):
                try:
                    if _receive(connection) != {'kind': 'ready', 'protocol': PROTOCOL}:
                        raise ValueError('Invalid trace worker handshake')
                    worker['ready'] = True
                except (OSError, EOFError, ValueError):
                    self.broken = True
                    self.condition.notify_all()
                    return False
        return bool(self.workers) and all(worker['ready'] for worker in self.workers)

    def ready(self):
        with self.condition:
            return self._check_ready_locked()

    def _stop_idle_locked(self, worker):
        if worker['busy'] or worker['stop_sent']:
            return
        try:
            _send(worker['connection'], {'kind': 'stop'})
            worker['stop_sent'] = True
        except (OSError, EOFError, BrokenPipeError):
            # Only join/is_alive below can establish process completion.
            pass

    def execute(self, plan, encoding, *, background=False, cancel=None, wait_timeout=2):
        with elapsed("workspace_trace_workers", "execute"):
            identity = str(uuid.uuid4())
            message = json.dumps({'kind': 'read', 'job_id': identity, 'plan': plan, 'encoding': encoding},
                                 allow_nan=False, separators=(',', ':')).encode('utf-8')
            if len(message) > MAX_PLAN_BYTES:
                raise ValueError('Trace plan exceeds the bounded worker payload')
            deadline = time.monotonic() + max(0, wait_timeout)
            with self.condition:
                if not self._check_ready_locked():
                    raise TraceWorkerUnavailable('Trace workers are not ready')
                self.serial += 1
                ticket = (bool(background), self.serial)
                can_enter = any(not worker['busy'] for worker in self.workers) and (not self.waiting or ticket < min(self.waiting))
                waiting_limit = max(0, self.queue_limit - 1) if background else self.queue_limit
                if not can_enter and len(self.waiting) >= waiting_limit:
                    raise TraceWorkerBusy('Trace workers are busy; retry the selected window')
                self.waiting.append(ticket)
                try:
                    while True:
                        if self.closing or self.broken:
                            raise TraceWorkerUnavailable('Trace worker admission is closed')
                        if cancel is not None and cancel.is_set():
                            raise TraceReadCancelled('Trace read was cancelled')
                        idle = next((item for item in self.workers if not item['busy']), None)
                        if idle is not None and ticket == min(self.waiting):
                            worker = idle
                            worker['busy'] = True
                            break
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TraceWorkerBusy('Trace workers are busy; retry the selected window')
                        self.condition.wait(min(remaining, .05))
                finally:
                    self.waiting.remove(ticket)
                    self.condition.notify_all()
            try:
                connection = worker['connection']
                connection.send_bytes(message)
                while not connection.poll(.05):
                    if not worker['process'].is_alive():
                        raise TraceWorkerUnavailable('Trace worker exited before acknowledging its read')
                result = _receive(connection)
                if (not isinstance(result, dict) or result.get('kind') != 'result' or
                        result.get('job_id') != identity or type(result.get('ok')) is not bool or
                        result['ok'] is False and (not isinstance(result.get('error'), str) or
                                                   not isinstance(result.get('message'), str))):
                    raise TraceWorkerUnavailable('Trace worker response identity changed')
                if result.get('ok') is True:
                    body = connection.recv_bytes(maxlength=MAX_RESPONSE_BYTES)
                else:
                    error_type = {'ValueError': ValueError, 'KeyError': KeyError,
                                  'FileNotFoundError': FileNotFoundError}.get(result.get('error'), RuntimeError)
                    raise _RemoteReadError(error_type, result.get('message', 'Trace worker read failed'))
                if self.closing or cancel is not None and cancel.is_set():
                    raise TraceReadCancelled('Trace read was cancelled')
                return body
            except _RemoteReadError as error:
                raise error.kind(error.message) from None
            except TraceReadCancelled:
                raise
            except TraceWorkerUnavailable:
                with self.condition:
                    self.broken = True
                worker['connection'].close()
                raise
            except (EOFError, BrokenPipeError, OSError, ValueError) as error:
                with self.condition:
                    self.broken = True
                worker['connection'].close()
                raise TraceWorkerUnavailable('Trace worker transport failed') from error
            finally:
                with self.condition:
                    worker['busy'] = False
                    if self.closing:
                        self._stop_idle_locked(worker)
                    self.condition.notify_all()

    def close(self, *, timeout=5):
        deadline = time.monotonic() + max(0, timeout)
        with self.close_lock:
            if self.closed:
                return
            with self.condition:
                self.closing = True
                self.condition.notify_all()
                for worker in self.workers:
                    self._stop_idle_locked(worker)
            for worker in self.workers:
                process = worker['process']
                if process.pid is None:
                    if not worker['started']:
                        raise TraceWorkerUnavailable('Trace worker start remains unconfirmed')
                    continue
                process.join(max(0, deadline - time.monotonic()))
                if process.is_alive():
                    error = TraceWorkerUnavailable('Trace workers have not exited; retry project close')
                    error.desktop_shutdown_stage = 'trace_workers'
                    raise error
            with self.condition:
                for worker in self.workers:
                    worker['connection'].close()
                    worker['child'].close()
                    worker['process'].close()
                self.closed = True
                self.condition.notify_all()

    def stats(self):
        with self.condition:
            return {'started': self.started, 'ready': sum(item['ready'] for item in self.workers),
                    'active': sum(item['busy'] for item in self.workers), 'waiting': len(self.waiting),
                    'closing': self.closing, 'closed': self.closed, 'broken': self.broken}
