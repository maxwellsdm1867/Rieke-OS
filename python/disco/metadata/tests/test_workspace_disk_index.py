import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import disco.metadata.disk_index as disk
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from disco.metadata.disk_index import DiskMetadataIndex
import disco.navigation.tree as tree
import disco.navigation.predicates as predicates


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
        return DiskMetadataIndex.build(self.path,self.rows,self.details,self.sources,'history-generation' if history else 'generation','project')
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
        tests += [{'field':'epoch','operator':'eq','value':'epoch-1'}]
        self.assertEqual(index.match({'field':'epoch','operator':'eq','value':'epoch-1'})[1], ['epoch-1'])
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
        self.assertEqual(len(opened.catalog()['fields']),len(tree.BASE_FIELDS))

    def test_uuid_equality_uses_unique_index_without_decoding_distinct_values(self):
        index=self.build(count=5000)
        with patch.object(disk.json,'loads',wraps=disk.json.loads) as decode:
            with patch.object(index,'_connect',wraps=index._connect) as connect:
                self.assertEqual(index.match({'field':'epoch','operator':'eq','value':'epoch-4900'})[1],['epoch-4900'])
                connect.assert_called_once_with([])
            self.assertEqual(decode.call_count,0)
        predicate={'field':'epoch','operator':'eq','value':'epoch-4'}
        self.assertEqual(index.match(predicate,['epoch-3','epoch-4','epoch-4'])[1],['epoch-4'])
        self.assertEqual(index.match(predicate,['epoch-3'])[1],[])
        self.assertEqual(index.match(predicate,iter(['epoch-4']))[1],['epoch-4'])
        self.assertEqual(index.match({**predicate,'value':None})[1],[])
        self.assertEqual(index.match({**predicate,'value':'foreign'})[1],[])
        with self.assertRaisesRegex(ValueError,'type'):
            index.match({**predicate,'value':4})
        with self.assertRaisesRegex(ValueError,'4096'):
            index.match({**predicate,'value':'x'*4097})
        # Nested expressions still use the general typed/scoped predicate path.
        self.assertEqual(index.match({'not':predicate},['epoch-3','epoch-4'])[1],['epoch-3'])

    def test_uuid_fast_path_preserves_empty_index_and_corruption_refusal(self):
        index=DiskMetadataIndex.build(self.path,[],{},[],'generation','project')
        self.assertEqual(index.match({'field':'epoch','operator':'eq','value':4})[1],[])
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE meta SET value='false' WHERE key='complete'")
        with self.assertRaisesRegex(ValueError,'changed'):
            index.match({'field':'epoch','operator':'eq','value':'foreign'})

    def test_nonstring_epoch_catalog_uses_general_typed_equality(self):
        rows,details,sources=fixture(3)
        converted={}
        for number,row in enumerate(rows):
            converted[number]=details[row['epoch_uuid']]
            row['epoch_uuid']=number
        index=DiskMetadataIndex.build(self.path,rows,converted,sources,'generation','project')
        self.assertEqual(index.match({'field':'epoch','operator':'eq','value':1})[1],['1'])
        with self.assertRaisesRegex(ValueError,'type'):
            index.match({'field':'epoch','operator':'eq','value':'1'})
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

    def test_bulk_details_use_one_connection_and_leave_shared_cache_unchanged(self):
        index=self.build(count=140)
        index.details['epoch-7']
        cached=list(index.details.cache)
        keys=[f'epoch-{i}' for i in (9,7,130,0)]
        with patch.object(index,'_connect',wraps=index._connect) as connect:
            result=list(index.details.many(keys))
        self.assertEqual(connect.call_count,1)
        self.assertEqual([key for key,_ in result],keys)
        self.assertEqual(dict(result),{key:self.details[key] for key in keys})
        self.assertEqual(list(index.details.cache),cached,'Bulk reads do not evict or admit shared entries')
        dict(result)['epoch-7']['parameters'].clear()
        self.assertEqual(index.details['epoch-7'],self.details['epoch-7'])
        with self.assertRaises(KeyError): list(index.details.many(['epoch-1','unknown']))

    def test_failed_rebuild_keeps_old_database(self):
        index=self.build()
        bad=dict(self.details);bad['epoch-0']={'parameters':{'invalid':float('nan')}}
        with self.assertRaises(ValueError): DiskMetadataIndex.build(self.path,self.rows,bad,self.sources,'new','project')
        self.assertEqual(len(index.rows()),31)

    def test_cell_lookup_and_count_use_exact_indexed_scope_without_details(self):
        index=self.build(count=1100)
        self.addCleanup(index.close)
        expected=[row['epoch_uuid'] for row in self.rows if row['cell_uuid']=='cell-17']
        with patch.object(index,'rows',side_effect=AssertionError('No complete row projection')):
            self.assertEqual(index.cell_epoch_ids('cell-17'),expected)
            self.assertEqual(index.cell_epoch_count('cell-17'),len(expected))
            self.assertEqual(index.cell_epoch_ids('not-registered'),[])
            self.assertEqual(index.cell_epoch_count('not-registered'),0)
        self.assertFalse(index.details.cache)
        with sqlite3.connect(self.path) as connection:
            plan=connection.execute('EXPLAIN QUERY PLAN SELECT COUNT(*) FROM epochs WHERE cell_uuid=?',('cell-17',)).fetchall()
        self.assertTrue(any('COVERING INDEX epochs_cell' in item[-1] for item in plan),plan)
        with self.path.open('ab') as stream:stream.write(b'changed')
        with self.assertRaises(ValueError):index.cell_epoch_ids('cell-17')
        with self.assertRaises(ValueError):index.cell_epoch_count('cell-17')

    def test_catalog_definitions_are_one_shared_read_only_view(self):
        index=self.build(count=140)
        self.addCleanup(index.close)
        expected={field['id']:field for field in index.catalog()['fields']}
        first=index.catalog_definitions();second=index.catalog_definitions()
        self.assertIs(first,second,'One shared view per generation, never a per-call copy')
        self.assertIs(first['epoch'],second['epoch'])
        self.assertEqual(json.dumps(dict(first),default=dict,sort_keys=True),json.dumps(expected,sort_keys=True))
        definition=first['parameters/frequencyCutoff']
        with self.assertRaises(TypeError): first['new']={}
        with self.assertRaises(TypeError): definition['label']='changed'
        self.assertIsInstance(definition['examples'],tuple)
        index.catalog()['fields'][0]['label']='caller copy'
        self.assertEqual(index.catalog()['fields'],list(expected.values()),'catalog() keeps returning independent copies')
        with self.path.open('ab') as stream:stream.write(b'changed')
        with self.assertRaises(ValueError):index.catalog_definitions()

    def test_per_key_values_read_bounded_windows_not_one_connection_per_epoch(self):
        index=self.build(count=1100)
        self.addCleanup(index.close)
        expected=dict(index.values().items())
        ids=[row['epoch_uuid'] for row in self.rows]
        for scope in (None,ids[::-1]):
            values=index.values(scope)
            order=ids if scope is None else scope
            with patch.object(index,'_connect',wraps=index._connect) as connect:
                read={key:values[key] for key in order}
            self.assertEqual(read,{key:expected[key] for key in order})
            self.assertLessEqual(connect.call_count,(len(order)//512)+11,connect.call_count)
            read[order[0]].clear()
            self.assertEqual(values[order[0]],expected[order[0]],'Each access returns an independent copy')
        scoped=index.values(ids[:3])
        with self.assertRaises(KeyError): scoped[ids[5]]
        with self.assertRaises(KeyError): index.values()['unknown']
        self.assertEqual(scoped.get(ids[2]),expected[ids[2]])
        # Random access shrinks the window: no worse than about one read per key.
        values=index.values(ids)
        jumps=ids[::97]
        with patch.object(index,'_connect',wraps=index._connect) as connect:
            self.assertEqual([values[key] for key in jumps],[expected[key] for key in jumps])
        self.assertLessEqual(connect.call_count,len(jumps))
        subset=index.values().subset(ids[5:1:-1])
        self.assertEqual(list(subset.items()),[(key,expected[key]) for key in ids[5:1:-1]])
        with self.assertRaises(KeyError): scoped.subset([ids[0],ids[9]])

    def test_epoch_prefix_is_an_index_range_probe_with_exact_total(self):
        index=self.build(count=1100)
        self.addCleanup(index.close)
        ids=sorted(row['epoch_uuid'] for row in self.rows)
        with patch.object(index,'rows',side_effect=AssertionError('No complete row projection')):
            for prefix in ('epoch-1','epoch-10','epoch-1099','epoch-','epoch-x'):
                matches=[key for key in ids if key.startswith(prefix)]
                self.assertEqual(index.epoch_prefix(prefix,5),(matches[:5],len(matches)))
            self.assertEqual(index.epoch_prefix('epoch-2',0),([],len([key for key in ids if key.startswith('epoch-2')])))
        with self.assertRaises(ValueError): index.epoch_prefix('Epoch-1',5)
        with self.assertRaises(ValueError): index.epoch_prefix('',5)
        with sqlite3.connect(self.path) as connection:
            plan=connection.execute('EXPLAIN QUERY PLAN SELECT epoch_uuid FROM epochs WHERE epoch_uuid>=? AND epoch_uuid<? ORDER BY epoch_uuid LIMIT 5',('epoch-1','epoch-2')).fetchall()
        self.assertTrue(any('USING COVERING INDEX' in item[-1] and 'epoch_uuid>? AND epoch_uuid<?' in item[-1].replace('=','') for item in plan),plan)
        rows,details,sources=fixture(3)
        rows[1]['epoch_uuid']='EPOCH-B';details['EPOCH-B']=details.pop('epoch-1')
        mixed=DiskMetadataIndex.build(Path(self.temp.name)/'mixed.sqlite',rows,details,sources,'mixed','project')
        self.addCleanup(mixed.close)
        self.assertIsNone(mixed.epoch_prefix('epoch-',5),'Mixed-case identities use the caller scan')

if __name__=='__main__': unittest.main()
