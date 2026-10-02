"""Serial paired backend observations with exact output and generation fences.

Main thread only, POSIX, owned disposable process recommended. No UI SLO claims.
Timeouts retain incomplete observations. Never resume receipt under new seals.
"""
import json
import os
import threading
import resource
import signal
import statistics
import sys
import time
from truth import digest, canonical


def rss_bytes():
    value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform=='darwin' else value*1024


def paired(baseline, candidate, expected, generation, *, repeats=5, seconds=45, memory_bytes=1024**3):
    if repeats<2:raise ValueError('First and warm observations require at least two samples')
    if not 0<seconds<=45 or not 0<memory_bytes<=1024**3:raise ValueError('Preserve serial paired resource caps')
    before=json.loads(canonical(generation()));target=digest(expected)
    receipt=dict(status='running',arms={n:dict(samples_ms=[]) for n in ('baseline','candidate')},
                 generation=before,expected_payload_sha256=target,
                 caps=dict(sample_seconds=seconds,peak_rss_bytes=memory_bytes),
                 timing_scope='backend call plus JSON serialization',ui_slo_certified=False)
    previous=signal.getsignal(signal.SIGALRM)
    previous_memory=signal.getsignal(signal.SIGUSR1)
    stopped=threading.Event()
    def memory_fault(*_):raise MemoryError('RSS watchdog cap')
    def watch():
        while not stopped.wait(.05):
            if rss_bytes()>memory_bytes:
                os.kill(os.getpid(),signal.SIGUSR1);return
    signal.signal(signal.SIGUSR1,memory_fault)
    watcher=threading.Thread(target=watch,daemon=True);watcher.start()
    def timeout(*_): raise TimeoutError('45-second or tighter sample cap')
    signal.signal(signal.SIGALRM,timeout)
    try:
        for index in range(repeats):
            order=[('baseline',baseline),('candidate',candidate)]
            if index%2:order.reverse()
            for name,call in order:
                if generation()!=before:raise ValueError('Generation changed before sample')
                if rss_bytes()>memory_bytes:raise MemoryError('RSS cap before sample')
                started=time.perf_counter();signal.setitimer(signal.ITIMER_REAL,seconds)
                try: result=call();checksum=digest(result)
                finally:signal.setitimer(signal.ITIMER_REAL,0)
                elapsed=(time.perf_counter()-started)*1000
                if generation()!=before:raise ValueError('Generation changed during sample')
                if rss_bytes()>memory_bytes:raise MemoryError('RSS cap after sample; external process watchdog required for hard cap')
                if checksum!=target:raise AssertionError('Independent truth payload mismatch')
                receipt['arms'][name]['samples_ms'].append(elapsed)
        receipt['status']='complete'
    except Exception as error:
        receipt.update(status='incomplete',error_type=type(error).__name__,error=str(error))
    finally:
        stopped.set();watcher.join()
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
        signal.signal(signal.SIGUSR1,previous_memory)
    for arm in receipt['arms'].values():
        samples=arm['samples_ms'];arm.update(first_ms=samples[0] if samples else None,
            warm_median_ms=statistics.median(samples[1:]) if len(samples)>1 else None,
            max_ms=max(samples) if samples else None,p95_ms=None,p99_ms=None)
    receipt['peak_rss_bytes']=rss_bytes()
    receipt['memory_guard_limit']='50 ms RSS watchdog polling; bounded overshoot between polls possible'
    return receipt
