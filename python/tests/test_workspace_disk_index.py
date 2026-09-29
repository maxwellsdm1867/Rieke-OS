import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import workspace_disk_index as disk
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from workspace_disk_index import DiskMetadataIndex
import workspace_tree as tree
import workspace_predicates as predicates


def fixture(count=31, history=False):
    rows=[];details={}
    candidates=[None,False,True,0,-0.0,1,1.0,'1',[0,675],[True,1],{'x':1}]
    for i in range(count):
        identity=f'epoch-{i}'
        rows.append(dict(epoch_uuid=identity,cell_uuid=f'cell-{i//8}',cell_label=f'Cell {i//8}',cell_type='ON',date='2026-09-24',source_sha256='source',block_uuid=f'block-{i//4}',block_start_time=f'time-{i//4}',group_uuid='group',group_label='g',protocol_name='VariableHistoryNoiseCurInject' if history else 'Test'))
        params={'a/b~':candidates[i%len(candidates)],'frequencyCutoff':[100,200][i%2]}
        if i%3: params['sometimes']=None if i%2 else 2
        if history: params.update(history1=[0,i%2],history2=[0,4],target=[0,5],isControl=i%3==0,segmentTime=100)
        details[identity]={'parameters':params,'metadata':{'cell':{'start_time':'2026-09-24T10:00','properties':{'type':'ON'}}}}
    sources=[{'source_sha256':'source','metadata':{'purpose':'test'}}]
    return rows,details,sources


class DiskIndexTests(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'index.sqlite'
    def tearDown(self): self.temp.cleanup()
    def build(self,history=False,count=31):
        self.rows,self.details,self.sources=fixture(count,history)
        return DiskMetadataIndex.build(self.path,self.rows,self.details,self.sources,'generation','project')
    def test_catalog_values_exact_parity(self):
        for history in (False,True):
            index=self.build(history)
            expected,values=tree.catalog(self.rows,self.details,sources=self.sources)
            self.assertEqual(dict(index.values().items()),values)
            self.assertEqual(json.dumps(index.catalog(),sort_keys=True),json.dumps(expected,sort_keys=True))
            for ids in ([self.rows[3]['epoch_uuid'],self.rows[1]['epoch_uuid']],[]):
                rows=[row for identity in ids for row in self.rows if row['epoch_uuid']==identity]
                scoped,scoped_values=tree.catalog(rows,self.details,known_fields=expected['fields'],sources=self.sources)
                self.assertEqual(dict(index.values(ids).items()),scoped_values)
                self.assertEqual(index.catalog(ids),scoped)
    def test_predicate_types_missing_and_scoped_not(self):
        index=self.build()
        catalog,values=tree.catalog(self.rows,self.details,sources=self.sources)
        self.assertEqual(index.predicate_catalog(),predicates.predicate_catalog(catalog,values))
        tests=[{'field':'parameters/a~1b~0','operator':op,**({'value':value} if op not in predicates.UNARY else {})} for op,value in [('eq',1),('eq',True),('eq',[0,675]),('ne',1),('contains',1),('exists',None),('missing',None),('is_null',None)]]
        tests += [{'not':{'field':'parameters/sometimes','operator':'eq','value':2}}, {'all':[]},{'any':[]},{'all':[{'field':'parameters/frequencyCutoff','operator':'gte','value':100},{'any':[{'field':'parameters/sometimes','operator':'missing'},{'field':'parameters/sometimes','operator':'is_null'}]}]}]
        for predicate in tests:
            expected=predicates.evaluate(predicate,catalog,values)
            self.assertEqual(index.match(predicate),expected)
            ids=['epoch-2','epoch-1']
            self.assertEqual(index.match(predicate,ids)[1],[identity for identity in ids if identity in expected[1]])
        with self.assertRaises(ValueError): index.match({'field':'parameters/frequencyCutoff','operator':'eq','value':'100'})
    def test_projection_details_fresh_and_generic_joint(self):
        index=self.build()
        self.assertEqual(index.rows(),{row['epoch_uuid']:row for row in self.rows})
        copy=index.details['epoch-1'];copy.clear();self.assertEqual(index.details['epoch-1'],self.details['epoch-1'])
        key=tree.joint_id(['parameters/sometimes','parameters/frequencyCutoff'])
        values=dict(index.values(['epoch-0','epoch-1'],[key]).items())
        self.assertEqual(values['epoch-0'][key][0],{'present':False})
        self.assertEqual(values['epoch-1'][key][0],{'present':True,'value':None})
        self.assertEqual(index.source_projection('source')['details'],self.details)
        with self.assertRaises(KeyError): index.details['foreign']
        with self.assertRaises(ValueError): dict(index.values(fields=['foreign']).items())
    def test_seal_generation_and_post_open_changes_fail_closed(self):
        index=self.build()
        with self.assertRaises(ValueError): DiskMetadataIndex.open(self.path,'other','project')
        with self.assertRaises(ValueError): DiskMetadataIndex.open(self.path,'generation','other')
        with sqlite3.connect(self.path) as connection: connection.execute("UPDATE epochs SET row_json='{}' WHERE epoch_id=1")
        with self.assertRaises(ValueError): index.rows()
        with self.assertRaises(ValueError): DiskMetadataIndex.open(self.path,'generation','project')
    def test_chunk_schema_union_and_large_scope(self):
        index=self.build(count=1100)
        self.assertEqual(len(dict(index.values(fields=['date']).items())),1100)
        self.assertEqual(len(index.match({'not':{'any':[]}},[row['epoch_uuid'] for row in self.rows])[1]),1100)
        self.assertLessEqual(len(index.details.cache),64)
    def test_history_choices_and_cross_chunk_schema_union(self):
        rows,details,sources=fixture(520,True)
        for i,row in enumerate(rows):
            params=details[row['epoch_uuid']]['parameters']
            for field in ('history1','history2','target'):
                if field != ('history1' if i<256 else 'history2' if i<512 else 'target'): params.pop(field)
        index=DiskMetadataIndex.build(self.path,rows,details,sources,'generation','project')
        catalog,values=tree.catalog(rows,details,sources=sources)
        self.assertEqual(json.dumps(index.catalog(),sort_keys=True),json.dumps(catalog,sort_keys=True))
        self.assertEqual(json.dumps(index.predicate_catalog(),sort_keys=True),json.dumps(predicates.predicate_catalog(catalog,values),sort_keys=True))
        self.assertEqual(dict(index.values().items()),values)
    def test_empty_and_persisted_summaries(self):
        index=DiskMetadataIndex.build(self.path,[],{},[],'generation','project')
        self.assertEqual(index.catalog(),tree.catalog([],{})[0])
        self.assertEqual(index.match({'not':{'any':[]}})[1],[])
        opened=DiskMetadataIndex.open(self.path,'generation','project')
        self.assertIsNotNone(opened._catalog_cache)
        self.assertIsNotNone(opened._predicate_cache)
        mutated=opened.catalog();mutated['fields'].clear()
        self.assertEqual(len(opened.catalog()['fields']),8)
    def test_truncated_choices_and_numeric_identity_exact(self):
        rows,details,sources=fixture(160)
        sequence=[1,1.0,True,-0.0,0.0,0,None,2**60,2**60+1,float(2**60)]+list(range(100))+[1.0,49,99]*16
        for row,value in zip(rows,sequence): details[row['epoch_uuid']]['parameters']['mixed']=value
        index=DiskMetadataIndex.build(self.path,rows,details,sources,'generation','project')
        catalog,values=tree.catalog(rows,details,sources=sources)
        self.assertEqual(json.dumps(index.predicate_catalog(),sort_keys=True),json.dumps(predicates.predicate_catalog(catalog,values),sort_keys=True))
        self.assertEqual(json.dumps(dict(index.values().items()),sort_keys=True),json.dumps(values,sort_keys=True))

    def test_lazy_source_projection_parity_and_bounded_decompression(self):
        rows,details,sources=fixture(40)
        for row in rows:
            details[row['epoch_uuid']]['metadata']['cell']['start_time']='09/23/2026 15:12:00:000000'
        rows[-1]['source_sha256']='other-source'
        sources.append({'source_sha256':'other-source','metadata':{}})
        index=DiskMetadataIndex.build(self.path,rows,details,sources,'generation','project')
        eager=index.source_projection('source')
        with patch.object(disk.zlib,'decompress',wraps=disk.zlib.decompress) as decompress:
            lazy=index.source_projection('source',lazy_details=True)
            self.assertEqual(decompress.call_count,len(eager['cells']))
        self.assertEqual({key:value for key,value in lazy.items() if key!='details'},
                         {key:value for key,value in eager.items() if key!='details'})
        self.assertEqual(dict(lazy['details']),eager['details'])
        self.assertTrue(all(cell['date']=='2026-09-23' for cell in lazy['cells'].values()))
        datum=lazy['details']['epoch-1'];datum['parameters'].clear()
        self.assertEqual(lazy['details']['epoch-1'],details['epoch-1'])
        self.assertIs(lazy['details'].details,index.details)
        lazy['rows']['epoch-39']=rows[-1]
        with self.assertRaises(KeyError): lazy['details']['epoch-39']
        self.assertEqual(len(lazy['details']),39)
        self.assertLessEqual(len(index.details.cache),64)
    def test_cached_mapping_lengths_do_not_rebuild_scopes(self):
        index=self.build()
        view=index.values(['epoch-1','epoch-1','unknown'])
        self.assertEqual(len(view),1)
        with patch.object(index,'_connect',side_effect=AssertionError('No scope rebuild for cached len')):
            self.assertEqual(len(view),1)
            self.assertEqual(len(index.values()),31)
            self.assertEqual(len(index.details),31)

    def test_shared_detail_cache_concurrent_readers_return_fresh_copies(self):
        index=self.build(count=140)
        def read(number):
            identity=f'epoch-{number%140}'
            datum=index.details[identity]
            self.assertEqual(datum,self.details[identity])
            datum['parameters'].clear()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(read,range(420)))
        self.assertLessEqual(len(index.details.cache),64)
        self.assertEqual(index.details['epoch-0'],self.details['epoch-0'])

    def test_failed_rebuild_keeps_old_database(self):
        index=self.build()
        bad=dict(self.details);bad['epoch-0']={'parameters':{'invalid':float('nan')}}
        with self.assertRaises(ValueError): DiskMetadataIndex.build(self.path,self.rows,bad,self.sources,'new','project')
        self.assertEqual(len(index.rows()),31)

if __name__=='__main__': unittest.main()
