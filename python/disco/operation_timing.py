"""Opt-in, module-local elapsed timers; nested elapsed times overlap."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter_ns

_records = ContextVar('disco_operation_timings', default=None)


@contextmanager
def capture_timings():
    """Collect this context's timers; restore any enclosing capture on exit."""
    records = []
    token = _records.set(records)
    try:
        yield records
    finally:
        _records.reset(token)


@contextmanager
def elapsed(module, operation):
    """Place inside a module operation; record only its label and elapsed time."""
    records = _records.get()
    if records is None:
        yield
        return
    tick = perf_counter_ns()
    outcome = 'error'
    try:
        yield
        outcome = 'ok'
    finally:
        records.append({'module': module, 'operation': operation,
                        'elapsed_ms': (perf_counter_ns() - tick) / 1_000_000,
                        'outcome': outcome})
