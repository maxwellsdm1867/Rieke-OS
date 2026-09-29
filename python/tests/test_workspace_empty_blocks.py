import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import h5py
from recording_workspace import restore_empty_blocks

class EmptyBlockTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'recording.h5'
        with h5py.File(self.path,'w') as f:
            g=f.create_group('experiment-fixture/epochGroups/group');g.attrs['uuid']='group'
            b=g.create_group('epochBlocks/empty');b.attrs['uuid']='empty'
            b.attrs['protocolID']='SealAndLeak';b.create_group('epochs')
            b.create_group('protocolParameters').attrs['sampleRate']=10000.
        self.group={'uuid':'group','epoch_blocks':[]}
        self.experiment={'animals':[{'preparations':[{'cells':[{'epoch_groups':[self.group]}]}]}]}
        def build(d):
            return SimpleNamespace(uuid=d.attrs['uuid'],protocolID=d.attrs['protocolID'],
                                   parameters=dict(d['protocolParameters'].attrs),epochs=[])
        self.parser=SimpleNamespace(parse_value=lambda x:x,EpochBlockObj=build)

    def test_preserves_source_empty_block_and_parameters_idempotently(self):
        with h5py.File(self.path,'r') as f:
            warnings=restore_empty_blocks(f,self.experiment,self.parser)
            self.assertEqual(len(warnings),1)
            block=self.group['epoch_blocks'][0]
            self.assertEqual(block,{'uuid':'empty','protocolID':'SealAndLeak',
                                    'parameters':{'sampleRate':10000.},'epochs':[]})
            self.assertEqual(restore_empty_blocks(f,self.experiment,self.parser),[])

    def test_missing_populated_block_is_not_silently_reconstructed(self):
        with h5py.File(self.path,'a') as f:
            f['experiment-fixture/epochGroups/group/epochBlocks/empty/epochs'].create_group('recorded')
        with h5py.File(self.path,'r') as f,self.assertRaisesRegex(ValueError,'populated'):
            restore_empty_blocks(f,self.experiment,self.parser)
        self.assertEqual(self.group['epoch_blocks'],[])

    def test_backreference_does_not_hide_canonical_empty_block(self):
        with h5py.File(self.path,'a') as f:
            f['aaa-backreference']=f['experiment-fixture/epochGroups/group/epochBlocks/empty']
        with h5py.File(self.path,'r') as f:
            self.assertEqual(len(restore_empty_blocks(f,self.experiment,self.parser)),1)

    def test_unknown_parent_fails_closed(self):
        self.group['uuid']='different'
        with h5py.File(self.path,'r') as f,self.assertRaisesRegex(ValueError,'epoch group'):
            restore_empty_blocks(f,self.experiment,self.parser)
