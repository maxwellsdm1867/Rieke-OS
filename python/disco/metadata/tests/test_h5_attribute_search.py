"""Native/typed parity for the H5 inventory's field dictionary and epoch links."""
import json
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from disco.metadata.disk_index import DiskMetadataIndex
from disco.metadata.typed_index import TypedMetadataIndex, build
from disco.navigation.predicates import h5_value_digest


class AttributeIndexTests(unittest.TestCase):
    def test_inherited_long_arrays_exact_ticks_and_empty_owner_fields(self):
        sha = 'a' * 64
        ids = [str(uuid.UUID(int=i)) for i in (1, 2)]
        fields = ['h5/epoch/@ticks','h5/block/@array','h5/preparation/@unassociated']
        data = [2**63+1, 2**63+2, list(range(460)), 'orphan']
        keys = [fields[0],fields[0],fields[1],fields[2]]
        # Separate physical JSON buckets may carry the same scientific number.
        groups = {
            'numeric':(1,1.0), 'equalArrays':([1,{'x':0.0}],[1.0,{'x':-0.0}]),
            'differentArrays':([1,{'x':0}],[1,{'x':1}]), 'longText':('X'*241,'Y'*241),
        }
        extra_links=[]
        for name,pair in groups.items():
            field='h5/epoch/@'+name
            fields.append(field)
            for epoch,value in zip(ids,pair):
                extra_links.append((epoch,len(data)))
                keys.append(field); data.append(value)
        descriptors = [{'id':key,'label':key,'path':key,'category':'Recorded H5 attributes'} for key in fields]
        inventory = types.SimpleNamespace(
            field_definitions=lambda d:descriptors,
            field_value_rows=lambda d:((i, key, json.dumps(value,separators=(',',':'))) for i,(key,value) in enumerate(zip(keys,data))),
            epoch_value_ids=lambda d:iter([(ids[0],0),(ids[1],1),(ids[0],2),(ids[1],2),*extra_links]))
        source={'source_sha256':sha,'h5_attribute_inventory':{'source_sha256':sha,'sha256':sha,
            'logical_sha256':'b'*64,'contract':'c'*64,'field_count':len(fields)}}
        rows={e:{'epoch_uuid':e,'source_sha256':sha,'date':'2026-11-20','start_time':'00:00','cell_uuid':'cell'} for e in ids}
        details={e:{'parameters':{'exactTick':tick},'metadata':{}} for e,tick in zip(ids,data)}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules,{'workspace_h5_attributes':inventory}):
            native = DiskMetadataIndex.build(Path(tmp)/'native.sqlite',rows,details,[source],'generation','project')
            try:
                for field in (fields[0], 'parameters/exactTick'):
                    with native.scalar_value_rows(field,[sha],ids[:1]) as values:
                        self.assertEqual(list(values),[data[0]])
                    with native.scalar_value_rows(field,[]) as values:
                        self.assertEqual(list(values),[])
                with native.scalar_value_rows(fields[1],[sha]) as values:
                    self.assertEqual(list(values),[])
                receipt=native.h5_attribute_coverage()[sha]
                self.assertEqual((receipt['registered_field_count'],receipt['unassociated_field_count'],receipt['epoch_field_associations']),(len(fields),1,4+len(extra_links)))
                self.assertEqual(native.catalog_definitions()[fields[2]]['label'],fields[2])
                self.assertNotIn('h5/',json.dumps(list(native.rows().values())))
                self.assertFalse(any(field['choices'] for field in native.predicate_catalog()['fields'] if field['id'].startswith('h5/')))
                side=Path(tmp)/'typed.sqlite'
                build(native.path,side,expected_generation='generation',expected_project_uuid='project',min_free_gib=0)
                with TypedMetadataIndex(side,native.path) as typed:
                    for key,op,encoding,value,want in [
                        (fields[0],'eq','json',str(data[0]),ids[:1]),
                        ('parameters/exactTick','eq','json',str(data[0]),ids[:1]),
                        ('parameters/exactTick','in','json',json.dumps(data[:2]),ids),
                        (fields[0],'gt','json',str(data[0]),ids[1:]),
                        (fields[1],'contains','json','454',ids),
                        (fields[1],'eq','json',json.dumps(data[2]),ids),
                        (fields[1],'eq','sha256',h5_value_digest(data[2]),ids),
                        (fields[2],'exists',None,None,[])]:
                        query={'field':key,'operator':op}
                        if encoding:query.update(value_encoding=encoding,value=value)
                        with self.subTest(key=key,op=op,encoding=encoding):
                            self.assertEqual(sorted(native.match(query)[1]),want)
                            self.assertEqual(sorted(typed.iter_membership(query)),want)
                    for name,n in [('numeric',1),('equalArrays',1),('differentArrays',2),('longText',2)]:
                        field='h5/epoch/@'+name
                        facets=typed.summaries(facet_fields=[field])['facets'][field]['values']
                        self.assertEqual(len(facets),n,name)
                        for bucket in facets:
                            query={'field':field,'operator':'eq','value_encoding':'json','value':json.dumps(bucket['value'])}
                            self.assertEqual(len(native.match(query)[1]),bucket['count'])
                            self.assertEqual(typed.count(query),bucket['count'])
                    hits,_=native.search_h5_values('1',[sha],50)
                    numeric=[hit for hit in hits if hit[0]=='h5/epoch/@numeric']
                    self.assertEqual({hit[1] for hit in numeric},{'1','1.0'})
                    for _,_,count,predicate in numeric:
                        self.assertEqual(count,len(native.match(predicate)[1]))
                        self.assertEqual(count,typed.count(predicate))
                    hits,more=native.search_h5_values('454',[sha],3)
                    self.assertEqual((len(hits),more,hits[0][2]),(1,False,2))
                    self.assertEqual(native.match(hits[0][3])[1],ids)
            finally:native.close()
