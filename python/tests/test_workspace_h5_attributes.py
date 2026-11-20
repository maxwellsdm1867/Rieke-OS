"""Physical HDF5 inventory, scope inheritance, precise values and safe cache recovery."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import h5py
import numpy as np

import recording_workspace as rw
import workspace_h5_attribute_inventory as store
import workspace_h5_attributes as inv
from python.tests.test_workspace_source_identity import fixture, uid


class H5AttributeInventoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name).resolve()
        self.source = self.project / 'owned.h5'
        self.doc = fixture(self.source)
        with h5py.File(self.source, 'r+') as h:
            h.attrs['version'] = np.uint64(2**63+9)
            cell, group, block, epoch = next(rw.epochs(self.doc))
            response = h[epoch['responses']['Amp1']['h5path']]
            data = response['data']
            data.attrs['tick'] = np.uint64(2**63+3)
            data.attrs['empty'] = h5py.Empty('f')
            data.attrs['compound'] = np.array([(b'x', 3),(b'y', 4)],dtype=[('word','S2'),('index','i2')])
            data.attrs['special'] = np.float32(-np.inf)
            data.attrs['region'] = data.regionref[1:3]
            data.attrs['other'] = h['/'].ref
            data.attrs['opaque'] = np.void(b'\xff\x00')
            bad_name = response.create_group(b'raw\xff')
            bad_name.attrs.create(b'cal\xfe', b'bad\xff', dtype=h5py.string_dtype('utf-8'))
            data.attrs['arr'] = np.arange(257,dtype=np.uint16)
            dt = h5py.string_dtype()
            data.attrs.create('labels', ['a' * 250, 'Café MESURE'], dtype=dt)
            root = h['experiment-' + uid(1)]
            z = root['epochGroups/group-' + uid(21) + '/epochBlocks/empty-' + uid(30)]
            z.attrs['sourceOnly'] = 'Orphän voilà'
            scoped = data.parent.create_group('calibration')
            scoped.attrs['a/b~c'] = 1.25
            scoped['self'] = scoped
            data.parent['z-alias'] = h5py.SoftLink(scoped.name)
            data.parent['z-hard'] = scoped
        self.sha = rw.digest(self.source)
        self.descriptor = self.build()

    def build(self, expected=None):
        with h5py.File(self.source,'r') as h:
            identity = rw.validate_source_identity(h,self.doc)
            with patch.object(h5py.Dataset,'__getitem__',side_effect=AssertionError('No dataset payload reads')):
                return inv.ensure_inventory(h,identity,self.project,self.sha,expected=expected)

    def test_complete_physical_location_and_value_coverage(self):
        expected = {}
        with h5py.File(self.source,'r') as h:
            def count(_,obj):
                expected[h5py.h5o.get_info(obj.id).addr] = sorted(os.fsencode(name) for name in obj.attrs)
            count('/',h['/'])
            h.visititems(count)
            region_hex = h5py.h5r.get_region(h[next(rw.epochs(self.doc))[3]['responses']['Amp1']['h5path']+
                                               '/data'].attrs['region'],h.id).encode()
        with sqlite3.connect(self.descriptor['path']) as db:
            actual={addr:[] for addr, in db.execute('SELECT address FROM objects')}
            for addr,name in db.execute('SELECT object,raw_name FROM attributes ORDER BY object,raw_name'):
                actual[addr].append(name)
        self.assertEqual(actual,expected)
        self.assertEqual(sum(map(len, expected.values())), self.descriptor['attribute_count'])
        self.assertEqual(self.descriptor['physical_attribute_count'],self.descriptor['attribute_count'])
        values = {fid:value for _,fid,value in inv.epoch_values(self.descriptor,[uid(13)])}
        base='h5/response/Amp1/data/@'
        self.assertEqual(values['h5/file/@version'],2**63+9)
        self.assertEqual(values[base+'tick'],2**63+3)
        self.assertIsNone(values[base+'empty'])
        self.assertEqual(values[base+'arr'],list(range(257)))
        self.assertEqual(values[base+'compound'],[{'word':'x','index':3},{'word':'y','index':4}])
        self.assertEqual(values[base+'opaque'],{'$h5_opaque':'/wA='})
        self.assertEqual(values['h5/response/Amp1/raw%FF/@cal%FE'], {'$h5_bytes':'YmFk/w=='})
        page=inv.attribute_page(self.descriptor,epoch_uuid=uid(13),q='raw%FF')
        item=inv.attribute_record(self.descriptor,page['records'][0]['record_id'],epoch_uuid=uid(13))
        self.assertTrue(bytes.fromhex(item['path_bytes_hex']).endswith(b'/raw\xff'))
        self.assertEqual(bytes.fromhex(item['name_bytes_hex']), b'cal\xfe')
        self.assertIn('$h5_float',values[base+'special'])
        self.assertIn('$h5_reference',values[base+'other'])
        import base64
        self.assertEqual(base64.b64decode(values[base+'region']['region']),region_hex)
        self.assertEqual(values['h5/response/Amp1/calibration/@a~1b~0c'],1.25)
        self.assertNotIn('h5/block/@sourceOnly',values)
        self.assertIn('h5/block/@sourceOnly',{f['id'] for f in inv.field_definitions(self.descriptor)})
        self.assertNotIn(base+'tick',{fid for _,fid,_ in inv.epoch_values(self.descriptor,[uid(23)])})

    def test_inspector_search_includes_full_values_and_preserves_scopes(self):
        first=inv.attribute_page(self.descriptor,limit=2)
        second=inv.attribute_page(self.descriptor,offset=2,limit=2)
        self.assertEqual(first['total'],self.descriptor['physical_attribute_count'])
        self.assertEqual([r['record_id'] for page in (first,second) for r in page['records']], [1,2,3,4])
        view=inv.attribute_page(self.descriptor,q='CAFÉ MESURE',epoch_uuid=uid(13))
        self.assertEqual(view['total'],1)
        record=view['records'][0]
        self.assertTrue(record['value_truncated'])
        self.assertLessEqual(len(record['value_preview']),240)
        self.assertEqual(record['shape'],[2])
        self.assertEqual(json.loads(inv.attribute_record(self.descriptor,record['record_id'],
                         epoch_uuid=uid(13))['value_json'])[1],'Café MESURE')
        with self.assertRaises(KeyError):
            inv.attribute_record(self.descriptor,record['record_id'],epoch_uuid=uid(23))
        self.assertEqual(inv.attribute_page(self.descriptor,q='orpHÄn voilà')['total'],1)
        self.assertEqual(inv.attribute_page(self.descriptor,q='orpHÄn voilà',epoch_uuid=uid(13))['total'],0)

    def test_coverage_recovery_and_repeated_project_validation(self):
        expected=inv.coverage_summary(self.descriptor)
        self.assertNotIn('path',expected)
        with patch.object(store,'_sha',side_effect=AssertionError('warm inventory must not hash files')):
            self.assertEqual(inv.verified_inventory(self.project,self.sha,expected=expected),self.descriptor)
        path=Path(self.descriptor['path'])
        path.write_bytes(b'damaged')
        with self.assertRaisesRegex(ValueError,'checksum'):
            inv.verified_inventory(self.project,self.sha,expected=expected)
        recovered=self.build(expected)
        self.assertEqual(inv.coverage_summary(recovered),expected)
        with self.assertRaisesRegex(ValueError,'registered import'):
            self.build({**expected,'logical_sha256':'f'*64})
        self.assertEqual(inv.coverage_summary(self.build({**expected,'version':0})),expected)

    def test_large_registered_source_set_keeps_warm_hash_proof(self):
        path = Path(self.descriptor['path'])
        entries = []
        # Each artifact is a complete independently sealed SQLite fixture.
        # Separate directory entries stand in for different source assets.
        for n in range(258):
            copy = self.project / ('artifact-' + str(n) + '.sqlite')
            copy.hardlink_to(path)
            copy.with_suffix('.seal.json').hardlink_to(path.with_suffix('.seal.json'))
            entries.append(copy)
        # Creating hardlinks changes the shared inode's ctime. Admit each final
        # signature only after the fixture has finished creating every link.
        for copy in entries:
            store._admit(copy,store._signature(copy),store._signature(copy.with_suffix('.seal.json')))
        with patch.object(store,'_sha',side_effect=AssertionError('warm sources rehashed')):
            for copy in entries:
                store._admit(copy,store._signature(copy),store._signature(copy.with_suffix('.seal.json')))
