"""Pure canonical duration folds over immutable membership publications."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class MembershipOrder:
    parent: object
    added: tuple = ()
    removed: frozenset = frozenset()

    def identities(self):
        layers=[];base=self
        while isinstance(base,MembershipOrder):layers.append(base);base=base.parent
        identities=set(base)
        for layer in reversed(layers):identities.difference_update(layer.removed);identities.update(layer.added)
        return sorted(identities)


def fold_duration(order,rows):
    identities=order.identities() if isinstance(order,MembershipOrder) else order
    total=0;cells={}
    def durations():
        nonlocal total
        for identity in identities:
            row=rows[identity];duration=row['duration_seconds'];cell=row['cell_uuid']
            total+=duration;cells[cell]=cells.get(cell,0)+duration
            yield duration
    # Both canonical algorithms consume the same ordered values in one pass:
    # counts/cells use += while retained total_counts uses builtin sum.
    retained=sum(durations())
    return total,cells,retained


class DurationPreparation:
    """One worker; caller validates/publishes the result under its own lock."""
    def __init__(self):
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='overview-duration')
        self.closed=False;self.pending={};self.lock=threading.Lock()

    def submit(self,order,rows,publish,*,key=None,on_error=None):
        with self.lock:
            if self.closed:return
            previous=self.pending.get(key)
            # An obsolete queued fold need never run. Running pure folds retain
            # their generation fence and cannot publish into a newer owner.
            future=self.executor.submit(fold_duration,order,rows)
            self.pending[key]=future
        if previous is not None:previous.cancel()
        def done(job):
            with self.lock:
                current=self.pending.get(key) is job
                if current:self.pending.pop(key,None)
            if current and not self.closed and not job.cancelled():
                try:result=job.result()
                except Exception as error:
                    if on_error is not None:on_error(error)
                    return
                publish(result)
        future.add_done_callback(done)

    def close(self):
        with self.lock:self.closed=True
        self.executor.shutdown(wait=True,cancel_futures=True)
