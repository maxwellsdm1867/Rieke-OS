import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
import zlib

from workspace_metadata_objects import canonical
from workspace_projection_cache import ProjectionCache, VERSION
from workspace_recipes import checksum


def fixture(count=60):
    parents = {kind: str(uuid.uuid4()) for kind in ('cell', 'group', 'block')}
    metadata = {kind: {'uuid': identity, 'label': 'same label'} for kind, identity in parents.items()}
    metadata['block']['frameTimes'] = [[position / 123. for position in range(1000)] for _ in range(4)]
    rows, details = {}, {}
    for position in range(count):
        identity = str(uuid.uuid4())
        rows[identity] = {'epoch_uuid': identity, 'source_sha256': 'a'*64,
            **{kind+'_uuid': value for kind, value in parents.items()}}
        details[identity] = {'metadata': {**metadata, 'epoch': {'uuid': identity, 'number': position}},
            'parameters': {'seed': position}}
    return dict(rows=rows, details=details, cells={}, source={}, fingerprints={})


class ProjectionObjectTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.cache = ProjectionCache(self.folder.name)

    def document(self, key='key'):
        return json.loads(zlib.decompress(self.cache._path(key).read_bytes()))

    def reseal(self, document):
        path = self.cache._path('key')
        payload = zlib.compress(canonical(document))
        path.write_bytes(payload)
        path.with_suffix('.sha256').write_text(hashlib.sha256(payload).hexdigest())

    def test_normalized_lazy_exact_independent_reconstruction(self):
        value = fixture()
        path = Path(self.cache.write('key', value))
        document = self.document()
        self.assertEqual(document['version'], 2)
        self.assertEqual(len(document['objects']), 3)
        for detail in document['details'].values():
            self.assertEqual(set(detail['objects']), {'cell', 'group', 'block'})
            self.assertEqual(set(detail['inline']['metadata']), {'epoch'})
        raw_repeated = canonical(value)
        raw_normalized = zlib.decompress(path.read_bytes())
        self.assertLess(len(raw_normalized), len(raw_repeated) / 10)
        self.assertLess(path.stat().st_size, len(zlib.compress(raw_repeated, 1)) / 5)
        loaded = self.cache.read('key')
        details = loaded['details']
        self.assertEqual(details._decoder.object_decodes, 0)
        for identity in value['rows']:
            self.assertEqual(canonical(details[identity]), canonical(value['details'][identity]))
        self.assertEqual(details._decoder.object_decodes, 3)
        first, second = list(details)[:2]
        details[first]['metadata']['block']['frameTimes'][0][0] = 'changed'
        self.assertEqual(details[second], value['details'][second])
        self.assertEqual(details[first], value['details'][first])
        loaded['rows'][first]['block_uuid'] = str(uuid.uuid4())
        self.assertEqual(details[first], value['details'][first])
        # It is entirely memory-owned after reading, so reclamation is safe.
        self.cache.publish([])
        self.assertFalse(path.exists())
        self.assertEqual(details[first], value['details'][first])

    def test_conflicting_identity_rejects_before_replacing_previous_cache(self):
        value = fixture(2)
        self.cache.write('key', value)
        old = self.cache._path('key').read_bytes()
        bad = copy.deepcopy(value)
        second = list(bad['details'])[1]
        bad['details'][second]['metadata']['block'] = copy.deepcopy(bad['details'][second]['metadata']['block'])
        bad['details'][second]['metadata']['block']['frameTimes'][0][0] = 999
        with self.assertRaisesRegex(ValueError, 'Conflicting ancestor'):
            self.cache.write('key', bad)
        self.assertEqual(self.cache._path('key').read_bytes(), old)
        self.assertEqual(self.cache.read('key'), value)
        self.assertFalse(list(Path(self.folder.name).glob('*.writing*')))

    def test_reference_ownership_and_malformed_objects_fail_closed(self):
        self.cache.write('key', fixture(2))
        original = self.document()
        for mutation in ('source', 'uuid', 'missing', 'bool', 'inline', 'duplicate', 'bad-base64', 'digest'):
            with self.subTest(mutation=mutation):
                document = copy.deepcopy(original)
                first = next(iter(document['details'].values()))
                if mutation == 'source':
                    document['objects'][0]['source_sha'] = 'other'
                elif mutation == 'uuid':
                    document['objects'][0]['uuid'] = str(uuid.uuid4())
                elif mutation == 'missing':
                    first['objects']['cell'] = 999
                elif mutation == 'bool':
                    first['objects']['cell'] = True
                elif mutation == 'inline':
                    first['inline']['metadata']['cell'] = {}
                elif mutation == 'duplicate':
                    document['objects'].append(document['objects'][0])
                elif mutation == 'bad-base64':
                    document['objects'][0]['payload'] = '**not base64**'
                else:
                    document['objects'][0]['sha256'] = 'z'*64
                self.reseal(document)
                self.assertIsNone(self.cache.read('key'))
        # Inner checksums are evaluated only for requested metadata objects.
        document = copy.deepcopy(original)
        document['objects'][0]['sha256'] = '0'*64
        self.reseal(document)
        loaded = self.cache.read('key')
        self.assertEqual(loaded['details']._decoder.object_decodes, 0)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            loaded['details'][next(iter(loaded['details']))]

    def test_equal_names_do_not_merge_different_uuids_or_sources(self):
        value = fixture(3)
        second, third = list(value['rows'])[1:]
        value['details'][second] = copy.deepcopy(value['details'][second])
        new_uuid = str(uuid.uuid4())
        value['rows'][second]['block_uuid'] = new_uuid
        value['details'][second]['metadata']['block']['uuid'] = new_uuid
        value['rows'][third]['source_sha256'] = 'b'*64
        self.cache.write('key', value)
        self.assertEqual(len(self.document()['objects']), 7)
        self.assertEqual(self.cache.read('key'), value)

    def test_streaming_writer_never_serializes_whole_projection(self):
        value = fixture(3)
        original = json.dumps
        def guarded(obj, *args, **kwargs):
            self.assertIsNot(obj, value)
            self.assertFalse(isinstance(obj, dict) and 'projection' in obj)
            return original(obj, *args, **kwargs)
        with patch('json.dumps', side_effect=guarded):
            self.cache.write('key', value)
        self.assertEqual(self.cache.read('key'), value)
        old_path = Path(self.folder.name) / (checksum({'version': 1, 'key': 'key'}) + '.json.zlib')
        self.assertNotEqual(old_path, self.cache._path('key'))
        self.assertEqual(VERSION, 2)


if __name__ == '__main__':
    unittest.main()
