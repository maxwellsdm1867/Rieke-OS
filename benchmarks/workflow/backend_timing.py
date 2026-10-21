"""Request-local diagnostic profiling, never a production method wrapper.

Inclusive function times overlap and must not be summed. Self times partition the
profiled Python work. Profiled requests are separate diagnostic samples, not the
ordinary action latency; cProfile overhead is deliberately not subtracted.
"""
import cProfile
import gc
import builtins
import io
import os
import json
from pathlib import Path
import threading
import time
import uuid



GC_RECORD_LIMIT = 64


class _GcDiagnostics:
    """Passive GC intervals overlapping requests; never changes collector policy.

    Collector thread CPU is distinct from the HTTP request thread CPU. A GC
    initiated by another active thread can block a request, so intervals are
    attributed to every request active at collection start, with collector ID.
    """
    def __init__(self, clock=None):
        self.clock = clock or (lambda: (time.perf_counter(), time.thread_time(), time.process_time()))
        self.active = {}
        self.pending = {}
        self.errors = 0

    def start(self, request_id):
        model = {'request_id': request_id, 'start': self.clock(),
                 'thread_id': threading.get_ident(), 'thread_name': threading.current_thread().name,
                 'gc_count_start': list(gc.get_count()), 'freeze_count_start': gc.get_freeze_count(),
                 'records': [], 'dropped': 0, 'errors_start': self.errors,
                 'generations': {str(g): {'collections': 0, 'wall_ms': 0., 'collector_thread_cpu_ms': 0., 'process_cpu_ms': 0.} for g in (0, 1, 2)}}
        self.active[request_id] = model
        return model

    def callback(self, phase, info):
        # CPython invokes these callbacks under the GIL. Do not acquire a lock
        # that the collecting thread might already hold or call GC recursively.
        try:
            tid = threading.get_ident()
            if phase == 'start':
                if self.active:
                    self.pending[tid] = {'clock': self.clock(), 'generation': int(info['generation']),
                                         'thread_id': tid, 'thread_name': threading.current_thread().name,
                                         'targets': tuple(self.active.values())}
                return
            if phase != 'stop':
                return
            event = self.pending.pop(tid, None)
            if event is None:
                return
            end = self.clock()
            duration = [(end[i] - event['clock'][i]) * 1000 for i in range(3)]
            for model in event['targets']:
                totals = model['generations'].setdefault(str(event['generation']), {'collections': 0, 'wall_ms': 0., 'collector_thread_cpu_ms': 0., 'process_cpu_ms': 0.})
                totals['collections'] += 1
                for key, value in zip(('wall_ms', 'collector_thread_cpu_ms', 'process_cpu_ms'), duration):
                    totals[key] += value
                if len(model['records']) < GC_RECORD_LIMIT:
                    model['records'].append({'generation': event['generation'],
                        'start_ms': (event['clock'][0] - model['start'][0]) * 1000,
                        'stop_ms': (end[0] - model['start'][0]) * 1000,
                        'wall_ms': duration[0], 'collector_thread_cpu_ms': duration[1], 'process_cpu_ms': duration[2],
                        'collector_thread_id': event['thread_id'], 'collector_thread_name': event['thread_name'],
                        'request_thread': event['thread_id'] == model['thread_id'],
                        'collected': info.get('collected'), 'uncollectable': info.get('uncollectable')})
                else:
                    model['dropped'] += 1
        except Exception:
            # Preserve application behavior; explicit errors make attribution
            # incomplete rather than silently claiming there were no pauses.
            self.errors += 1

    def finish(self, model):
        end = self.clock()
        self.active.pop(model['request_id'], None)
        inflight = [{'generation': event['generation'], 'collector_thread_id': event['thread_id'],
                     'start_ms': (event['clock'][0] - model['start'][0]) * 1000}
                    for event in self.pending.values() if any(target is model for target in event['targets'])]
        return {'diagnostic_only': True, 'clock': 'server perf_counter/thread_time/process_time',
                'request_wall_ms': (end[0] - model['start'][0]) * 1000,
                'request_thread_cpu_ms': (end[1] - model['start'][1]) * 1000,
                'request_process_cpu_ms': (end[2] - model['start'][2]) * 1000,
                'request_thread_id': model['thread_id'], 'request_thread_name': model['thread_name'],
                'gc_count_start': model['gc_count_start'], 'gc_count_end': list(gc.get_count()),
                'freeze_count_start': model['freeze_count_start'], 'freeze_count_end': gc.get_freeze_count(),
                'gc_generations': {key: dict(value) for key, value in model['generations'].items()},
                'gc_records': list(model['records']), 'gc_records_limit': GC_RECORD_LIMIT,
                'gc_records_dropped': model['dropped'], 'gc_inflight_at_finish': inflight,
                'callback_errors': self.errors - model['errors_start'],
                'limits': 'GC totals overlap request wall/CPU and other requests; do not sum. Collector CPU belongs to the named collecting thread. Diagnostic setup overhead included; no GC policy changes.'}

    def discard(self, model):
        if model:
            self.active.pop(model['request_id'], None)

    def close(self):
        self.active.clear()
        self.pending.clear()


def install(app, output, source_root):
    from flask import g, request, has_request_context
    output, source = Path(output), str(Path(source_root).resolve() / 'python') + '/'
    lock = threading.Lock()
    owned_h5 = (output / 'trace-fixture.h5').resolve()
    import h5py
    original_open, original_io_open = builtins.open, io.open
    original_h5_init = h5py.File.__init__
    gc_diagnostics = _GcDiagnostics()
    gc_callback = gc_diagnostics.callback
    gc.callbacks.append(gc_callback)

    def check_h5(value, api, *, always=False):
        if not has_request_context():
            return
        if not isinstance(value, (str, bytes, os.PathLike)):
            if always:
                raise RuntimeError('Benchmark refuses H5 handles without an owned path')
            return
        path = Path(os.fsdecode(value))
        if not always and path.suffix.lower() not in ('.h5', '.hdf5'):
            return
        path = path.resolve()
        allowed = path == owned_h5 and request.path.endswith('/trace')
        attempt = {'path': str(path), 'api': api, 'allowed': allowed}
        if not hasattr(g, 'benchmark_h5_accesses'):
            g.benchmark_h5_accesses = []
        g.benchmark_h5_accesses.append(attempt)
        if not allowed:
            raise RuntimeError('Benchmark H5 access refused outside owned trace request')

    def guarded_open(file, *args, **kwargs):
        check_h5(file, 'builtins.open')
        return original_open(file, *args, **kwargs)

    def guarded_io_open(file, *args, **kwargs):
        check_h5(file, 'io.open')
        return original_io_open(file, *args, **kwargs)

    def guarded_h5_init(instance, name, *args, **kwargs):
        if isinstance(name, h5py._objects.ObjectID):
            # h5py wraps existing group/dataset IDs while validating link ownership.
            check_h5(h5py.h5f.get_name(name), 'h5py.File.existing_handle', always=True)
        else:
            check_h5(name, 'h5py.File.__init__', always=True)
        return original_h5_init(instance, name, *args, **kwargs)

    builtins.open, io.open = guarded_open, guarded_io_open
    # Preserve the h5py.File class identity; restore at owned fixture shutdown.
    h5py.File.__init__ = guarded_h5_init

    def restore():
        builtins.open, io.open = original_open, original_io_open
        h5py.File.__init__ = original_h5_init
        if gc_callback in gc.callbacks:
            gc.callbacks.remove(gc_callback)
        gc_diagnostics.close()


    def start():
        g.benchmark_started = time.perf_counter()
        g.benchmark_request_id = uuid.uuid4().hex
        g.benchmark_gc = gc_diagnostics.start(g.benchmark_request_id)
        g.benchmark_profile = None
        g.benchmark_h5_accesses = []
        g.benchmark_module_context = None
        g.benchmark_module_records = []
        g.benchmark_module_requested = request.headers.get('X-Disco-Timing') == '1'
        if g.benchmark_module_requested:
            expected = Path(source) / 'disco/operation_timing.py'
            if not expected.is_file():
                raise RuntimeError('Requested module timing is unavailable in measured source: ' + str(expected))
            import disco.operation_timing as timing
            if Path(timing.__file__).resolve() != expected.resolve():
                raise RuntimeError('Module timing helper does not belong to measured source')
            context = timing.capture_timings()
            g.benchmark_module_records = context.__enter__()
            g.benchmark_module_context = context
        if request.headers.get('X-Benchmark-Profile') == '1':
            g.benchmark_profile = cProfile.Profile()
            g.benchmark_profile.enable()

    def close_module_capture(error=None):
        context = getattr(g, 'benchmark_module_context', None)
        if context is not None:
            g.benchmark_module_context = None
            context.__exit__(type(error) if error else None, error, error.__traceback__ if error else None)

    def finish(response):
        close_module_capture()
        profile = getattr(g, 'benchmark_profile', None)
        if profile:
            profile.disable()
        gc_diagnostic = gc_diagnostics.finish(g.benchmark_gc)
        total = (time.perf_counter() - g.benchmark_started) * 1000
        phases = []
        if profile:
            for stat in profile.getstats():
                code = stat.code
                if isinstance(code, str) or not code.co_filename.startswith(source):
                    continue
                module = code.co_filename[len(source):].replace('/', '.').removesuffix('.py')
                phases.append({'module': module, 'name': code.co_name,
                               'line': code.co_firstlineno, 'calls': stat.callcount,
                               'recursive_calls': stat.reccallcount,
                               'inclusive_ms': stat.totaltime * 1000,
                               'self_ms': stat.inlinetime * 1000})
        row = {'request_id': g.benchmark_request_id,
               'action_id': request.headers.get('X-Benchmark-Action'),
               'method': request.method, 'path': request.path, 'status': response.status_code,
               'total_ms': total, 'profiled': bool(profile), 'phase': 'profile' if profile else 'ordinary', 'spans': phases,
               'clock': 'server', 'inclusive_times_overlap': True,
               'module_timing': g.benchmark_module_requested,
               'module_timings': g.benchmark_module_records,
               'gc_diagnostic': gc_diagnostic,
               'h5_accesses': g.benchmark_h5_accesses,
               'h5_access_count': len(g.benchmark_h5_accesses),
               'h5_guard_scope': 'Python open/io.open and h5py.File initialization during HTTP requests',
               'profile_overhead': 'included; separate diagnostic sample; not subtracted' if profile else 'disabled'}
        with lock, (output / 'requests.jsonl').open('a') as handle:
            handle.write(json.dumps(row) + '\n')
        response.headers['X-Benchmark-Request-Id'] = g.benchmark_request_id
        response.headers['X-Owned-Bench-Service-Ms'] = f'{total:.6f}'
        return response

    app.before_request_funcs.setdefault(None, []).insert(0, start)
    # Flask runs after hooks in reverse order; index zero records final response.
    app.after_request_funcs.setdefault(None, []).insert(0, finish)

    def stop_profile_after_failure(error):
        gc_diagnostics.discard(getattr(g, 'benchmark_gc', None))
        close_module_capture(error)
        profile = getattr(g, 'benchmark_profile', None)
        if profile:
            profile.disable()

    app.teardown_request_funcs.setdefault(None, []).append(stop_profile_after_failure)
    return restore
