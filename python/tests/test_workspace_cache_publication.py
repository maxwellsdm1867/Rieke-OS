"""Concurrent writers may not replace a valid generation under live readers."""
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
import threading
import time
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

from workspace_disk_index import DiskMetadataIndex
from workspace_cache_lifecycle import CacheNamespace
from workspace_projection_cache import ProjectionCache
from test_workspace_disk_index import fixture


def _concurrent_build(path, start, inspect, messages):
    index = None
    try:
        rows, details, sources = fixture(9)
        start.wait(10)
        index = DiskMetadataIndex.build(path, rows, details, sources, 'generation', 'project')
        messages.put(('published', index._signature))
        if not inspect.wait(10):
            raise RuntimeError('Reader barrier timed out')
        messages.put(('read', index.rows() == {row['epoch_uuid']: row for row in rows}))
    except BaseException as error:
        messages.put(('error', type(error).__name__ + ': ' + str(error)))
    finally:
        if index is not None:
            index.close()


class MetadataPublicationTests(unittest.TestCase):
    def test_build_reuses_verified_same_generation_without_invalidating_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ('a'*64 + '.sqlite')
            rows, details, sources = fixture(5)
            first = DiskMetadataIndex.build(path, rows, details, sources, 'generation', 'project')
            self.addCleanup(first.close)
            signature = first._signature
            second = DiskMetadataIndex.build(path, rows, details, sources, 'generation', 'project')
            self.addCleanup(second.close)
            self.assertEqual(first.rows(), second.rows())
            self.assertEqual(first._signature, signature)
            self.assertEqual(second._signature, signature)

    def test_two_cold_processes_publish_one_immutable_generation(self):
        context = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / ('b'*64 + '.sqlite'))
            start, inspect = context.Event(), context.Event()
            messages = context.Queue()
            children = [context.Process(target=_concurrent_build, args=(path, start, inspect, messages)) for _ in range(2)]
            try:
                for child in children:
                    child.start()
                start.set()
                published = [messages.get(timeout=15) for _ in children]
                self.assertTrue(all(item[0] == 'published' for item in published), published)
                inspect.set()
                results = [messages.get(timeout=15) for _ in children]
                self.assertEqual(results, [('read', True), ('read', True)])
                self.assertEqual(published[0][1], published[1][1])
            finally:
                inspect.set()
                for child in children:
                    child.join(timeout=5)
                    if child.is_alive():
                        child.kill();child.join(timeout=5)
                messages.close();messages.join_thread()


class ProjectionPublicationTests(unittest.TestCase):
    def test_reader_waits_for_whole_payload_and_seal_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=ProjectionCache(folder)
            before=dict(rows={'epoch':{}},details={'epoch':{'value':1}},cells={},source={},fingerprints={})
            after={**before,'details':{'epoch':{'value':2}}}
            cache.write('key',before)
            replaced,release,reading=threading.Event(),threading.Event(),threading.Event()
            original=os.replace
            def interrupted_replace(source,destination):
                original(source,destination)
                if Path(destination)==cache._path('key'):
                    replaced.set()
                    if not release.wait(10):raise RuntimeError('Publication barrier timed out')
            def read():
                reading.set()
                return cache.read('key')
            with ThreadPoolExecutor(max_workers=2) as pool:
                with patch('workspace_projection_cache.os.replace',side_effect=interrupted_replace):
                    writer=pool.submit(cache.write,'key',after)
                    try:
                        self.assertTrue(replaced.wait(10))
                        reader=pool.submit(read)
                        self.assertTrue(reading.wait(10))
                        time.sleep(.05)
                        self.assertFalse(reader.done(),'Reader saw a torn payload/seal pair')
                    finally:
                        release.set()
                    writer.result(timeout=10)
                    self.assertEqual(reader.result(timeout=10),after)

    def test_writer_registry_is_bounded_across_retired_generations(self):
        with tempfile.TemporaryDirectory() as folder:
            namespace=CacheNamespace(folder,'projections')
            for number in range(256):
                with namespace.writer(f'{number:064x}.json.zlib'):
                    pass
            files=list((Path(folder)/'.writer-locks').iterdir())
            self.assertLessEqual(len(files),64)
            self.assertTrue(all(path.stat().st_size==0 for path in files))


if __name__ == '__main__':
    unittest.main()
