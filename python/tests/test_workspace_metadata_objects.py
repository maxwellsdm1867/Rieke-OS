"""Exact ownership and round-trip tests for shared ancestor metadata storage."""
import copy
import json
import sqlite3
import unittest
import uuid
import zlib

from workspace_metadata_objects import Encoder, Decoder, canonical


class MetadataObjectTests(unittest.TestCase):
    def setUp(self):
        self.database = sqlite3.connect(':memory:')
        self.encoder = Encoder(self.database)
        self.decoder = Decoder()
        self.row = {'source_sha256': 'a' * 64, 'epoch_uuid': str(uuid.uuid4()),
            'cell_uuid': str(uuid.uuid4()), 'group_uuid': str(uuid.uuid4()), 'block_uuid': str(uuid.uuid4())}
        self.detail = {'parameters': {'amplitude': 1.0}, 'properties': {'flag': True}, 'metadata': {
            'cell': {'uuid': self.row['cell_uuid'], 'label': 'same', 'attributes': {'ON': 1, 'on': 1.0}},
            'group': {'uuid': self.row['group_uuid'], 'label': 'same', 'properties': {'é': True, 'e\u0301': 1}},
            'block': {'uuid': self.row['block_uuid'], 'parameters': {'frameTimesMs': [i / 1000 for i in range(10000)]}},
            'epoch': {'uuid': self.row['epoch_uuid'], 'original': {'value': None}}}}

    def tearDown(self):
        self.database.close()

    def test_many_epochs_share_exact_objects_and_preserve_public_mutation_isolation(self):
        original = canonical(self.detail)
        encoded = [self.encoder.encode(self.row, self.detail) for _ in range(100)]
        self.assertEqual(self.database.execute('SELECT COUNT(*) FROM metadata_objects').fetchone()[0], 3)
        self.assertLess(sum(map(len, encoded)), len(original))
        for blob in encoded:
            value = self.decoder.decode(self.database, self.row, blob)
            self.assertEqual(canonical(value), original)
            value['metadata']['block']['parameters']['frameTimesMs'][0] = -100
        self.assertEqual(self.decoder.object_decodes, 3)
        self.assertEqual(canonical(self.detail), original)

    def test_equal_names_do_not_merge_different_sources_or_uuid_owners(self):
        self.encoder.encode(self.row, self.detail)
        other_source = {**self.row, 'source_sha256': 'b' * 64}
        changed = copy.deepcopy(self.detail)
        changed['metadata']['cell']['attributes']['ON'] = False
        encoded = self.encoder.encode(other_source, changed)
        self.assertEqual(self.database.execute('SELECT COUNT(*) FROM metadata_objects').fetchone()[0], 6)
        self.assertEqual(canonical(self.decoder.decode(self.database, other_source, encoded)), canonical(changed))
        with self.assertRaisesRegex(ValueError, 'different source'):
            self.decoder.decode(self.database, self.row, encoded)

    def test_conflicting_same_uuid_metadata_is_rejected_with_and_without_cache(self):
        self.encoder.encode(self.row, self.detail)
        for clear in (False, True):
            if clear:
                self.encoder.cache.values.clear(); self.encoder.cache.bytes = 0
            changed = copy.deepcopy(self.detail)
            changed['metadata']['cell']['attributes']['ON'] = True  # True must not equal 1.
            with self.assertRaisesRegex(ValueError, 'Conflicting ancestor'):
                self.encoder.encode(self.row, changed)

    def test_explicit_wrong_parent_uuid_rejects_instead_of_relabeling(self):
        changed = copy.deepcopy(self.detail)
        changed['metadata']['block']['uuid'] = str(uuid.uuid4())
        with self.assertRaisesRegex(ValueError, 'ownership'):
            self.encoder.encode(self.row, changed)

    def test_unidentified_and_nonobject_metadata_round_trips_inline(self):
        for value in (None, {}, {'block': None}, {'block': {'name': 'unidentified'}}, {'cell': []}):
            detail = {**self.detail, 'metadata': value}
            encoded = self.encoder.encode(self.row, detail)
            self.assertEqual(canonical(self.decoder.decode(self.database, self.row, encoded)), canonical(detail))

    def test_dangling_wrong_role_and_wrong_uuid_references_reject(self):
        encoded = self.encoder.encode(self.row, self.detail)
        for kind in ('missing', 'other_role', 'other_owner'):
            doc = json.loads(zlib.decompress(encoded))
            row = dict(self.row)
            if kind == 'missing':
                doc['objects']['block'] = 999
            elif kind == 'other_role':
                doc['objects']['block'] = doc['objects']['cell']
            else:
                row['cell_uuid'] = str(uuid.uuid4())
            with self.assertRaises(ValueError):
                self.decoder.decode(self.database, row, zlib.compress(canonical(doc)))

    def test_valid_sqlite_with_changed_ancestor_payload_fails_content_checksum(self):
        encoded = self.encoder.encode(self.row, self.detail)
        self.database.execute('UPDATE metadata_objects SET payload=? WHERE kind=?',
                              (zlib.compress(b'{"changed":true}'), 'cell'))
        self.assertEqual(self.database.execute('PRAGMA quick_check').fetchone()[0], 'ok')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.decoder.decode(self.database, self.row, encoded)

    def test_decoded_cache_obeys_object_memory_budget(self):
        decoder = Decoder(cache_bytes=1024)
        encoded = self.encoder.encode(self.row, self.detail)
        self.assertEqual(canonical(decoder.decode(self.database, self.row, encoded)), canonical(self.detail))
        self.assertLessEqual(decoder.cache.bytes, 1024)
        # Large arrays are decoded on demand, not retained above the budget.
        self.assertTrue(all(value[0][0][1] != 'block' for value in decoder.cache.values.values()))


if __name__ == '__main__':
    unittest.main()
