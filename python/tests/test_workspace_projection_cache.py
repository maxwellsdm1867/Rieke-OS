import tempfile
from pathlib import Path
import unittest
from workspace_projection_cache import ProjectionCache


class ProjectionCacheTests(unittest.TestCase):
    def test_reloads_exact_projection_without_retaining_mutable_objects(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = ProjectionCache(Path(folder) / 'cache')
            key = ('source', (1, 2, 3), 'metadata')
            value = {'rows': {'epoch': {'x': 1}}, 'details': {'epoch': {'array': [1, True, None]}},
                     'cells': {}, 'source': {}, 'fingerprints': {}}
            cache.write(key, value)
            loaded = cache.read(key)
            self.assertEqual(loaded, value)
            loaded['details']['epoch']['array'].append(9)
            self.assertEqual(cache.read(key), value)
            self.assertIsNone(cache.read(('other',)))

    def test_corrupt_payload_or_seal_is_a_cache_miss(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = ProjectionCache(Path(folder) / 'cache')
            projection = dict(rows={}, details={}, cells={}, source={}, fingerprints={})
            path = Path(cache.write('key', projection))
            path.write_bytes(b'not compressed metadata')
            self.assertIsNone(cache.read('key'))
            cache.write('key', projection)
            path.with_suffix('.sha256').write_text('wrong hash')
            self.assertIsNone(cache.read('key'))


if __name__ == '__main__':
    unittest.main()
