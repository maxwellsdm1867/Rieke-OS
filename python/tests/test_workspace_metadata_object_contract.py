"""Independent scientific-content and ownership contract for ancestor storage."""
import copy
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
import zlib
from pathlib import Path
from unittest.mock import patch

from workspace_metadata_objects import Decoder, Encoder
from workspace_disk_index import DiskMetadataIndex
import workspace_disk_index as disk_module


def uid(value):return str(uuid.UUID(int=value))

def encoded_json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def fixture():
    row={'source_sha256':'a'*64,'epoch_uuid':uid(10),'cell_uuid':uid(20),'group_uuid':uid(30),'block_uuid':uid(40)}
    detail={'parameters':{'contrast':0.0},'properties':{'epoch_flag':True},'opaque_extensions':{'preserve':[None,[],{}]},
        'metadata':{'experiment':{'uuid':uid(1),'rig':'MEA'},'cell':{'uuid':uid(20),'label':'Cell3','properties':{'ON':True,'on':1,'é':1.0,'e\u0301':'1'}},
            'group':{'uuid':uid(30),'label':'same name','properties':{'mixed':[True,1,1.0,None,'1',[],{}]}},
            'block':{'uuid':uid(40),'label':'same name','parameters':{'frameTimesMs':[[0.0,0.25],[1.5,2.0]],'shape':[2,2]}},
            'epoch':{'uuid':uid(10),'label':'same name','properties':{'empty':[]}}}}
    return row,detail


class MetadataObjectContractTests(unittest.TestCase):
    def database(self):
        database=sqlite3.connect(':memory:');self.addCleanup(database.close);return database

    def test_exact_typed_arrays_nested_shapes_and_unknown_fields_survive(self):
        row,detail=fixture();database=self.database();blob=Encoder(database).encode(row,detail)
        actual=Decoder().decode(database,row,blob)
        self.assertEqual(encoded_json(actual),encoded_json(detail))
        values=actual['metadata']['group']['properties']['mixed']
        self.assertEqual([type(value) for value in values],[bool,int,float,type(None),str,list,dict])
        self.assertEqual(actual['metadata']['block']['parameters']['frameTimesMs'],[[0.0,0.25],[1.5,2.0]])

    def test_equal_labels_with_different_uuids_and_source_versions_never_merge(self):
        row,detail=fixture();database=self.database();encoder=Encoder(database);decoder=Decoder();versions=[]
        for source,offset,value in [('a'*64,0,'first'),('a'*64,100,'different owners'),('b'*64,0,'new source version')]:
            owner=copy.deepcopy(row);datum=copy.deepcopy(detail);owner['source_sha256']=source
            for kind in ('cell','group','block'):
                owner[kind+'_uuid']=uid(int(uuid.UUID(row[kind+'_uuid']))+offset)
                datum['metadata'][kind]['uuid']=owner[kind+'_uuid'];datum['metadata'][kind]['version_note']=value
            versions.append((owner,datum,encoder.encode(owner,datum)))
        self.assertEqual(database.execute('SELECT COUNT(*) FROM metadata_objects').fetchone()[0],9)
        for owner,datum,blob in reversed(versions):self.assertEqual(encoded_json(decoder.decode(database,owner,blob)),encoded_json(datum))

    def test_same_uuid_in_different_ancestor_kinds_does_not_merge(self):
        row,detail=fixture();database=self.database()
        for kind in ('cell','group','block'):row[kind+'_uuid']=uid(77);detail['metadata'][kind]['uuid']=uid(77)
        blob=Encoder(database).encode(row,detail)
        self.assertEqual(database.execute('SELECT COUNT(*) FROM metadata_objects').fetchone()[0],3)
        self.assertEqual(encoded_json(Decoder().decode(database,row,blob)),encoded_json(detail))

    def test_same_owner_different_typed_values_reject_even_without_encoder_cache(self):
        for first,second in [(True,1),(1,1.0),(0.0,-0.0),(None,[]),('é','e\u0301'),('QC','qc')]:
            with self.subTest(first=first,second=second):
                row,detail=fixture();database=self.database();encoder=Encoder(database,cache_bytes=0)
                detail['metadata']['block']['scientific_value']=first;encoder.encode(row,detail)
                changed=copy.deepcopy(detail);changed['metadata']['block']['scientific_value']=second
                with self.assertRaisesRegex(ValueError,'Conflicting ancestor'):encoder.encode(row,changed)

    def test_uuid_spelling_is_preserved_but_ownership_is_semantic(self):
        row,detail=fixture();row['block_uuid']='ABCDEFFF-0000-0000-0000-000000000040'
        detail['metadata']['block']['uuid']=row['block_uuid'].lower();database=self.database()
        blob=Encoder(database).encode(row,detail)
        self.assertEqual(encoded_json(Decoder().decode(database,row,blob)),encoded_json(detail))

    def test_decode_public_results_do_not_share_mutable_ancestors_or_inline_values(self):
        row,detail=fixture();database=self.database();blob=Encoder(database).encode(row,detail);decoder=Decoder()
        a=decoder.decode(database,row,blob);b=decoder.decode(database,row,blob)
        a['metadata']['block']['parameters']['frameTimesMs'][0].append(99)
        a['metadata']['group']['properties']['mixed'][5].append('mutated')
        a['opaque_extensions']['preserve'][2]['mutated']=True
        self.assertEqual(encoded_json(b),encoded_json(detail))
        self.assertEqual(encoded_json(decoder.decode(database,row,blob)),encoded_json(detail))

    def test_oversized_decoded_ancestor_is_not_retained_between_reads(self):
        row,_=fixture();times=[index/1000 for index in range(4096)]
        detail={'metadata':{'block':{'uuid':row['block_uuid'],'parameters':{'frameTimesMs':times,'shape':[4096,1]}}}}
        database=self.database();blob=Encoder(database).encode(row,detail);decoder=Decoder(cache_bytes=8192);queries=[]
        database.set_trace_callback(queries.append)
        for _ in range(2):self.assertEqual(encoded_json(decoder.decode(database,row,blob)),encoded_json(detail))
        reads=[query for query in queries if 'FROM metadata_objects WHERE object_id=' in query]
        self.assertEqual(len(reads),2)
        self.assertEqual(len(decoder.cache.values),0)
        self.assertEqual(decoder.cache.bytes,0)

    def test_missing_legacy_identity_stays_inline_without_invented_ownership(self):
        row,detail=fixture();row.pop('block_uuid');detail['metadata']['cell'].pop('uuid');database=self.database()
        blob=Encoder(database).encode(row,detail)
        self.assertEqual(database.execute('SELECT kind FROM metadata_objects').fetchall(),[('group',)])
        self.assertEqual(encoded_json(Decoder().decode(database,row,blob)),encoded_json(detail))

    def test_explicit_parent_uuid_disagreement_rejects_for_each_kind(self):
        for kind in ('cell','group','block'):
            with self.subTest(kind=kind):
                row,detail=fixture();detail['metadata'][kind]['uuid']=uid(999)
                with self.assertRaisesRegex(ValueError,'ownership'):Encoder(self.database()).encode(row,detail)

    def test_reference_type_and_duplicate_inline_ancestor_corruption_reject(self):
        row,detail=fixture();database=self.database();blob=Encoder(database).encode(row,detail);original=json.loads(zlib.decompress(blob))
        for value in (True,1.0,'1',None,0,-1,99999):
            with self.subTest(reference=value):
                altered=copy.deepcopy(original);altered['objects']['block']=value
                with self.assertRaises(ValueError):Decoder().decode(database,row,zlib.compress(encoded_json(altered)))
        altered=copy.deepcopy(original);altered['inline']['metadata']['block']=detail['metadata']['block']
        with self.assertRaises(ValueError):Decoder().decode(database,row,zlib.compress(encoded_json(altered)))

    def test_recomputed_digest_cannot_hide_ancestor_uuid_disagreement(self):
        row,detail=fixture();database=self.database();blob=Encoder(database).encode(row,detail)
        changed=copy.deepcopy(detail['metadata']['block']);changed['uuid']=uid(999);raw=encoded_json(changed)
        database.execute("UPDATE metadata_objects SET payload=?,sha256=? WHERE kind='block'",(zlib.compress(raw),hashlib.sha256(raw).digest()))
        with self.assertRaisesRegex(ValueError,'identity'):Decoder().decode(database,row,blob)

    def test_envelope_version_requires_exact_integer_type(self):
        row,detail=fixture();database=self.database();blob=Encoder(database).encode(row,detail);original=json.loads(zlib.decompress(blob))
        for version in (True,1.0,'1',None,2):
            with self.subTest(version=version):
                altered=copy.deepcopy(original);altered['version']=version
                with self.assertRaises(ValueError):Decoder().decode(database,row,zlib.compress(encoded_json(altered)))

    def test_decoder_never_reuses_an_object_from_a_different_database_generation(self):
        row,detail=fixture();first=self.database();second=self.database();changed=copy.deepcopy(detail)
        changed['metadata']['block']['parameters']['frameTimesMs']=[[10.0,20.0],[30.0,40.0]]
        a=Encoder(first).encode(row,detail);b=Encoder(second).encode(row,changed);decoder=Decoder()
        self.assertEqual(encoded_json(decoder.decode(first,row,a)),encoded_json(detail))
        with self.assertRaisesRegex(ValueError,'different database generation'):decoder.decode(second,row,b)

    def test_same_immutable_file_reopened_connection_keeps_exact_cached_ancestors(self):
        row,detail=fixture()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'metadata.sqlite'
            with sqlite3.connect(path) as writer:
                blob=Encoder(writer).encode(row,detail);writer.commit()
            writer.close();decoder=Decoder()
            for _ in range(3):
                reader=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
                try:self.assertEqual(encoded_json(decoder.decode(reader,row,blob)),encoded_json(detail))
                finally:reader.close()
            self.assertEqual(decoder.object_decodes,3)

    def test_disk_details_do_not_multiply_oversized_shared_ancestors(self):
        row,detail=fixture();rows=[];details={}
        detail['metadata']['block']['parameters']['frameTimesMs']=[i/1000 for i in range(4096)]
        for ordinal in range(4):
            owner={**row,'epoch_uuid':uid(100+ordinal),'cell_label':'Cell3','cell_type':'ON',
                   'date':'2026-09-29','group_label':'same name','protocol_name':'Oracle','block_start_time':'2026-09-29T12:00:00'}
            datum=copy.deepcopy(detail);datum['metadata']['epoch']['uuid']=owner['epoch_uuid'];rows.append(owner);details[owner['epoch_uuid']]=datum
        with tempfile.TemporaryDirectory() as directory:
            index=DiskMetadataIndex.build(Path(directory)/'index.sqlite',rows,details,[{'source_sha256':row['source_sha256']}],'generation',uid(1))
            try:
                index._metadata_decoder=Decoder(cache_bytes=8192)
                for owner in rows:self.assertEqual(encoded_json(index.details[owner['epoch_uuid']]),encoded_json(details[owner['epoch_uuid']]))
                retained={id(datum['metadata']['block']) for datum in index._detail_cache.values()}
                self.assertLessEqual(len(retained),1,'The detail cache duplicated one oversized ancestor for each epoch')
            finally:index.close()

    def test_disk_detail_cache_accounts_for_evicted_decoder_objects_still_referenced(self):
        row,detail=fixture();rows=[];details={};budget=20000
        for ordinal in range(8):
            owner={**row,'epoch_uuid':uid(100+ordinal),'block_uuid':uid(200+ordinal),'cell_label':'Cell3','cell_type':'ON',
                   'date':'2026-09-29','group_label':'same name','protocol_name':'Oracle','block_start_time':'2026-09-29T12:00:00'}
            datum=copy.deepcopy(detail);datum['metadata']['epoch']['uuid']=owner['epoch_uuid']
            datum['metadata']['block']['uuid']=owner['block_uuid'];datum['metadata']['block']['parameters']['frameTimesMs']=[ordinal+i/1000 for i in range(256)]
            rows.append(owner);details[owner['epoch_uuid']]=datum
        def reachable_bytes(value,seen=None):
            seen=set() if seen is None else seen
            if id(value) in seen:return 0
            seen.add(id(value));total=sys.getsizeof(value)
            children=[*value.keys(),*value.values()] if isinstance(value,dict) else value if isinstance(value,(tuple,list)) else []
            return total+sum(reachable_bytes(child,seen) for child in children)
        with tempfile.TemporaryDirectory() as directory,patch.object(disk_module,'DETAIL_CACHE_BYTES',budget):
            index=DiskMetadataIndex.build(Path(directory)/'index.sqlite',rows,details,[{'source_sha256':row['source_sha256']}],'generation',uid(1))
            try:
                index._metadata_decoder=Decoder(cache_bytes=budget)
                for owner in rows:
                    self.assertEqual(encoded_json(index.details[owner['epoch_uuid']]),encoded_json(details[owner['epoch_uuid']]))
                    self.assertLessEqual(reachable_bytes(index._detail_cache),budget)
                self.assertLess(len(index._detail_cache),len(rows))
            finally:index.close()


if __name__=='__main__':unittest.main()
