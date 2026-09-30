"""Exact metadata contracts for one large disposable project.

Independent oracle: generated integer acquisition ordinals determine expected
parents, sources, pointers and typed membership. No production match/tree code
is used to compute expected sets. This tests the indexed read model, not the
real Symphony parser or physical 100k-waveform H5 recording.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import copy
import json
from pathlib import Path
import random
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from benchmark_service_scale import Details, fixture, uid
from workspace_disk_index import DiskMetadataIndex
from workspace_tree_pages import StaleTreePage, TreePages

EPOCH_COUNT = 1000


class AcquisitionDetails(Details):
    def __getitem__(self, key):
        result = super().__getitem__(key)
        row = self.rows[key]; ordinal = row['synthetic_index']
        result['parameters']['typed'] = [True, 1, 1.0, '1', None, [1, False]][ordinal%6]
        if ordinal%7:
            result['parameters']['sometimes'] = None if ordinal%7 == 1 else 42
        result['metadata']['group'] = {'uuid':row['group_uuid']}
        result['metadata']['epoch'] = {'uuid':key}
        return result


class LargeProjectContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='rieke-stress-contracts-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        cls.service, cls.protocol = fixture(EPOCH_COUNT)
        cls.oracle = {}
        for ordinal, (key, row) in enumerate(cls.service.rows.items()):
            source = f'{(ordinal//100)%10+1:064x}'
            cell, group, block = uid(EPOCH_COUNT+ordinal//100), uid(3*EPOCH_COUNT+ordinal//100), uid(2*EPOCH_COUNT+ordinal//20)
            stream = uid(5*EPOCH_COUNT+ordinal)
            pointer = f'/cells/{cell}/groups/{group}/blocks/{block}/epochs/{key}/responses/{stream}'
            row.update(group_uuid=group, streams=[{'uuid':stream,'kind':'responses','device':'Amp1',
                'h5_path':pointer,'data_path':pointer+'/data','sample_rate':10000.,'sample_count':20000,'units':'pA'}])
            # Store independently defined expected identity relationships.
            cls.oracle[key] = (ordinal,source,cell,group,block,stream,pointer)
        cls.raw_details = AcquisitionDetails(cls.service.rows)
        started = time.perf_counter()
        cls.index = DiskMetadataIndex.build(cls.folder/'index.sqlite',cls.service.rows,
            cls.raw_details,cls.service.sources,'stress-generation',cls.service.project['project_uuid'])
        cls.build_seconds = time.perf_counter()-started
        cls.service.disk_index = cls.index; cls.service.details = cls.index.details
        cls.service._fingerprints = cls.index.fingerprints()
        cls.pager = TreePages(cls.service)

    def expected(self, condition):
        return {key for key,(ordinal,*_) in self.oracle.items() if condition(ordinal)}

    def test_every_indexed_parent_source_and_pointer_matches_manifest(self):
        rows = self.index.rows()
        self.assertEqual(set(rows),set(self.oracle))
        for key, (_,source,cell,group,block,stream,pointer) in self.oracle.items():
            row = rows[key]
            self.assertEqual((row['source_sha256'],row['cell_uuid'],row['group_uuid'],row['block_uuid']),
                             (source,cell,group,block))
            actual = row['streams'][0]
            self.assertEqual((actual['uuid'],actual['h5_path'],actual['data_path']),
                             (stream,pointer,pointer+'/data'))
            self.assertEqual(tuple(actual[field] for field in ('kind','device','sample_rate','sample_count','units')),
                             ('responses','Amp1',10000.,20000,'pA'))

    def test_filters_have_exact_typed_membership(self):
        cases = [
            ({'field':'parameters/typed','operator':'eq','value':True},lambda i:i%6==0),
            ({'field':'parameters/typed','operator':'eq','value':1},lambda i:i%6 in (1,2)),
            ({'field':'parameters/typed','operator':'eq','value':'1'},lambda i:i%6==3),
            ({'field':'parameters/typed','operator':'eq','value':[1,False]},lambda i:i%6==5),
            ({'field':'parameters/typed','operator':'is_null'},lambda i:i%6==4),
            ({'field':'parameters/sometimes','operator':'missing'},lambda i:i%7==0),
            ({'field':'parameters/sometimes','operator':'is_null'},lambda i:i%7==1),
            ({'not':{'field':'parameters/sometimes','operator':'exists'}},lambda i:i%7==0),
            ({'all':[{'field':'parameters/contrast','operator':'eq','value':.3},
                {'field':'parameters/currentMean','operator':'gte','value':100}]},lambda i:i%5==3 and i%3>=1)]
        with patch('h5py.File',side_effect=AssertionError('Metadata filtering must not read waveforms')):
            for predicate, condition in cases:
                with self.subTest(predicate=predicate):
                    _, actual = self.index.match(predicate)
                    self.assertEqual(set(actual),self.expected(condition))
                    self.assertEqual(len(actual),len(set(actual)))

    def test_scoped_not_never_selects_foreign_epochs(self):
        scope = [key for key,(ordinal,*_) in self.oracle.items() if ordinal%13==0]
        _, actual = self.index.match({'not':{'field':'parameters/contrast','operator':'eq','value':.3}},scope)
        self.assertEqual(set(actual),self.expected(lambda i:i%13==0 and i%5!=3))
        self.assertEqual(actual,[key for key in scope if self.oracle[key][0]%5!=3])

    def test_random_uuid_selection_and_details_never_cross_map(self):
        keys = random.Random(927).sample(list(self.oracle),min(32,EPOCH_COUNT))
        for key in keys:
            _, actual = self.index.match({'field':'epoch','operator':'eq','value':key})
            self.assertEqual(actual,[key])
            detail = self.index.details[key]; _,_,cell,group,block,*_ = self.oracle[key]
            self.assertEqual(tuple(detail['metadata'][level]['uuid'] for level in ('cell','group','block','epoch')),
                             (cell,group,block,key))

    def test_small_pages_and_far_anchors_have_exact_chronology(self):
        ordered = sorted(self.service.rows,key=lambda key:(self.service.rows[key]['date'],
                          self.service.rows[key]['start_time'][11:],key))
        with patch('h5py.File',side_effect=AssertionError('Page navigation must not read waveforms')):
            for position in (0,EPOCH_COUNT//2,EPOCH_COUNT-1):
                key = ordered[position]
                flat = self.pager.page({'splits':'','anchor_uuid':key,'limit':80})
                self.assertEqual(flat['anchor']['index'],position)
                self.assertEqual([row['epoch_uuid'] for row in flat['epochs']],
                                 ordered[(position//80)*80:(position//80+1)*80])
                grouped = self.pager.page({'splits':'cell,block','anchor_uuid':key,'limit':80})
                self.assertIn(key,[row['epoch_uuid'] for row in grouped['epochs']])
                self.assertTrue(all(row['cell_uuid']==self.oracle[key][2] and row['block_uuid']==self.oracle[key][4]
                                    for row in grouped['epochs']))

    def test_stale_revision_is_rejected_after_fingerprint_change(self):
        root = self.pager.page({'splits':'cell','limit':80})
        key = next(iter(self.oracle)); previous = self.service._fingerprints[key]
        try:
            self.service._fingerprints[key] = 'c'*64
            with self.assertRaises(StaleTreePage):
                self.pager.page({'splits':'cell','limit':80,'revision':root['revision'],
                                 'path':root['branches'][0]['path']})
        finally:self.service._fingerprints[key] = previous

    def test_source_projection_contains_exact_owned_epochs(self):
        for source in self.service.sources:
            sha = source['source_sha256']; projected = self.index.source_projection(sha,lazy_details=True)
            expected = {key for key,entry in self.oracle.items() if entry[1]==sha}
            self.assertEqual(set(projected['rows']),expected)
            self.assertEqual(set(projected['details']),expected)
            foreign = next((key for key in self.oracle if key not in expected),None)
            if foreign is not None:
                with self.assertRaises(KeyError):projected['details'][foreign]
            # Validate every detail via bounded source partitions, independently
            # checking relationships and exact JSON representation of parameters.
            eager = self.index.source_projection(sha,lazy_details=False)
            for key,detail in eager['details'].items():
                ordinal,_,cell,group,block,*_ = self.oracle[key]
                self.assertEqual(tuple(detail['metadata'][level]['uuid'] for level in ('cell','group','block','epoch')),
                                 (cell,group,block,key))
                parameters = {'contrast':(ordinal%5)/10,'seed':ordinal,'stimTime':1000,
                              'currentMean':(ordinal%3)*100,
                              'typed':[True,1,1.0,'1',None,[1,False]][ordinal%6]}
                if ordinal%7:parameters['sometimes']=None if ordinal%7==1 else 42
                self.assertEqual(json.dumps(detail['parameters'],sort_keys=True),json.dumps(parameters,sort_keys=True))
            del eager

    def test_concurrent_detail_readers_keep_cache_bounded_and_copies_isolated(self):
        keys = random.Random(928).sample(list(self.oracle),min(140,EPOCH_COUNT))
        def read(key):
            detail = self.index.details[key]
            self.assertEqual(detail['metadata']['epoch']['uuid'],key)
            detail['parameters'].clear()
            self.assertIn('typed',self.index.details[key]['parameters'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(read,keys*3))
        self.assertLessEqual(len(self.index.details.cache),64)

    def test_failed_index_rebuild_preserves_last_verified_generation(self):
        key = next(iter(self.oracle)); datum = copy.deepcopy(self.raw_details[key])
        datum['parameters']['invalid'] = float('nan')
        previous_inventory = set(self.folder.iterdir())
        with self.assertRaises(ValueError):
            DiskMetadataIndex.build(self.index.path,[self.service.rows[key]],{key:datum},self.service.sources,
                                    'failed-generation',self.service.project['project_uuid'])
        restored = DiskMetadataIndex.open(self.index.path,'stress-generation',self.service.project['project_uuid'])
        self.assertEqual(len(restored.details),EPOCH_COUNT)
        self.assertEqual(restored.details[key],self.raw_details[key])
        self.assertEqual(set(self.folder.iterdir()),previous_inventory)

    def test_corrupt_index_copy_fails_closed_without_affecting_current_reader(self):
        corrupt = self.folder/'corrupt.sqlite'
        try:
            shutil.copyfile(self.index.path,corrupt)
            shutil.copyfile(str(self.index.path)+'.sha256.json',str(corrupt)+'.sha256.json')
            with sqlite3.connect(corrupt) as connection:
                connection.execute("UPDATE epochs SET row_json='{}' WHERE epoch_id=1")
            with self.assertRaisesRegex(ValueError,'checksum'):
                DiskMetadataIndex.open(corrupt,'stress-generation',self.service.project['project_uuid'])
            self.assertEqual(len(self.index.details),EPOCH_COUNT)
        finally:
            corrupt.unlink(missing_ok=True);Path(str(corrupt)+'.sha256.json').unlink(missing_ok=True)


class RecordingResult(unittest.TextTestResult):
    def startTest(self,test):self.started=time.perf_counter();super().startTest(test)
    def stopTest(self,test):
        self.records.append({'test':test.id(),'seconds':time.perf_counter()-self.started})
        super().stopTest(test)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs',type=int,default=1000)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 100<=args.epochs<=1000000:parser.error('--epochs must be 100–1000000')
    EPOCH_COUNT=args.epochs
    RecordingResult.records=[]
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(LargeProjectContracts)
    result=unittest.TextTestRunner(verbosity=2,resultclass=RecordingResult).run(suite)
    report={'epochs':EPOCH_COUNT,'fixture':'One disposable project; synthetic pointers, independent ordinal-based identity/membership oracle.',
        'successful':result.wasSuccessful(),'tests_run':result.testsRun,
        'failures':[{'test':test.id(),'traceback':trace} for test,trace in result.failures],
        'errors':[{'test':test.id(),'traceback':trace} for test,trace in result.errors],
        'measurements':result.records,'build_seconds':getattr(LargeProjectContracts,'build_seconds',None),
        'limits':'No physical100k-H5 parsing, liveSQL, browser, export or actual process-kill recovery. Strict adversarial import/UI gates are separate and currently fail.'}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
