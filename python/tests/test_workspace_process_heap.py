"""Collector ownership and reclamation in disposable child interpreters."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


class ProcessHeapTests(unittest.TestCase):
    def child(self, code):
        prelude = '''
import gc, weakref
from workspace_process_heap import ProjectHeap
class Cycle:
    def __init__(self): self.loop = self
'''
        result = subprocess.run([sys.executable, '-B', '-c', prelude + textwrap.dedent(code)],
            env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_loaded_heap_is_skipped_but_new_request_cycles_still_collect(self):
        self.child('''
            loaded = Cycle(); original = weakref.ref(loaded)
            thresholds = gc.get_threshold()
            heap = ProjectHeap().start()
            assert gc.isenabled() and gc.get_threshold() == thresholds
            assert gc.get_freeze_count() > 0
            del loaded
            request = Cycle(); request_ref = weakref.ref(request); del request
            gc.collect()
            assert request_ref() is None
            assert original() is not None
            heap.close(); heap.close()
            assert gc.get_freeze_count() == 0 and original() is None
        ''')

    def test_repeated_refresh_reclaims_retired_graph_and_preserves_live_graph(self):
        self.child('''
            current = Cycle(); heap = ProjectHeap().start()
            retired = []
            for _ in range(12):
                retired.append(weakref.ref(current))
                with heap.refresh():
                    assert gc.get_freeze_count() == 0
                    with heap.refresh():
                        current = Cycle()
                assert gc.get_freeze_count() > 0
                assert all(reference() is None for reference in retired)
                assert current.loop is current
            heap.close()
        ''')

    def test_failed_refresh_thaws_and_later_success_can_freeze_again(self):
        self.child('''
            current = Cycle(); reference = weakref.ref(current)
            heap = ProjectHeap().start()
            try:
                with heap.refresh():
                    current = None
                    raise ValueError('owned refresh failed')
            except ValueError:
                pass
            assert gc.get_freeze_count() == 0 and reference() is None
            with heap.refresh(): current = Cycle()
            assert gc.get_freeze_count() > 0
            heap.close()
            try:
                with heap.refresh(): pass
            except RuntimeError:
                pass
            else:
                raise AssertionError('Closed owner reused')
        ''')

    def test_cycles_crossing_frozen_objects_are_reclaimed_at_refresh(self):
        self.child('''
            class Owner: pass
            old = Owner(); heap = ProjectHeap().start()
            request = Cycle(); request.owner = old; old.request = request
            old_ref, request_ref = weakref.ref(old), weakref.ref(request)
            del old, request
            gc.collect()
            assert old_ref() is not None and request_ref() is not None
            with heap.refresh(): pass
            assert old_ref() is None and request_ref() is None
            heap.close()
        ''')

    def test_foreign_collector_owner_is_never_thawed(self):
        self.child('''
            gc.freeze(); count = gc.get_freeze_count()
            try: ProjectHeap().start()
            except RuntimeError: pass
            else: raise AssertionError('Adopted foreign frozen heap')
            assert gc.get_freeze_count() == count
            gc.unfreeze()
            heap = ProjectHeap().start(); count = gc.get_freeze_count()
            try: ProjectHeap().start()
            except RuntimeError: pass
            else: raise AssertionError('Two owners')
            assert gc.get_freeze_count() == count
            heap.close()
            gc.disable(); heap = ProjectHeap().start(); heap.close()
            assert not gc.isenabled()
        ''')

    def test_actual_service_refresh_enters_and_exits_heap_lifetime(self):
        self.child('''
            from workspace_service import WorkspaceService
            class Service(WorkspaceService):
                def __init__(self): self.fail = False; self.graph = Cycle()
                def _refresh_verified_sources(self, metrics):
                    assert gc.get_freeze_count() == 0
                    self.graph = Cycle()
                    if self.fail: raise ValueError('broken input')
                    return {'epochs': 1}
            service = Service(); old = weakref.ref(service.graph)
            service._project_heap = ProjectHeap().start()
            assert service.refresh()['status'] == 'complete'
            assert old() is None and gc.get_freeze_count() > 0
            service.fail = True
            try: service.refresh()
            except ValueError: pass
            else: raise AssertionError('Suppressed failure')
            assert service.last_refresh['status'] == 'failed'
            assert gc.get_freeze_count() == 0
            service._project_heap.close()
        ''')


if __name__ == '__main__':
    unittest.main()
