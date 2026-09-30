"""Independent exact predicate oracle for persistent native target lookups."""
import copy
import unittest
from workspace_native_tag_filter import matching,FIELDS
from workspace_predicates import matches
from test_workspace_shared_tag_index import Fixture


class Lookup:
    def __init__(self,fixture):self.fixture=fixture
    def targets(self,tag,kinds=('cell','epoch')):
        return {(kind,target) for (kind,target,profile),row in self.fixture.saved.items()
                if kind in kinds and tag in row['tags']}
    def tagged_targets(self,kinds=('cell','epoch')):
        return self.targets_outside([],kinds)
    def targets_outside(self,tags,kinds=('cell','epoch')):
        return {(kind,target) for (kind,target,profile),row in self.fixture.saved.items()
                if kind in kinds and set(row['tags'])-set(tags)}


class NativeTagFilterTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.lookup=Lookup(self.f)
        self.addCleanup(self.f.index.close)

    def test_all_supported_operators_equal_independent_canonical_array_oracle(self):
        f=self.f
        for field in FIELDS:
            predicates=[{'field':field,'operator':op} for op in ('exists','missing','is_null')]
            predicates += [{'field':field,'operator':'contains','value':tag} for tag in ('QC','qc','é','e\u0301','Inherited','absent','')]
            predicates += [{'field':field,'operator':op,'value':value} for op in ('eq','ne')
                for value in ([],['QC'],['QC','qc'],['qc','QC'],['QC','QC'],['Inherited','QC'])]
            predicates += [{'field':field,'operator':op,'value':[[],['QC'],['different']]} for op in ('in','not_in')]
            for predicate in predicates:
                for node in (predicate,{'not':predicate},{'all':[predicate,{'not':{'field':field,'operator':'missing'}}]},
                        {'any':[predicate,{'field':field,'operator':'eq','value':[]}]}):
                    with self.subTest(node=node):
                        expected=tuple(row['epoch_uuid'] for row in f.rows if matches(node,f.values(row)))
                        self.assertEqual(matching(f.rows,{},node,self.lookup),expected)
        self.assertEqual(f.index.stats['full_builds'],0)

    def test_cell_and_epoch_composition_scope_order_and_edits_are_immediate(self):
        f=self.f;rows=[f.rows[5],f.rows[1],f.rows[0]]
        predicate={'all':[{'field':'annotations/cell/tags','operator':'contains','value':'Inherited'},
            {'field':'annotations/epoch/tags','operator':'contains','value':'QC'}]}
        self.assertEqual(matching(rows,{},predicate,self.lookup),('e0',))
        f.put('epoch','e1','p1',['QC'])
        self.assertEqual(matching(rows,{},predicate,self.lookup),('e1','e0'))
        self.assertEqual(matching(rows,{}, {'not':predicate},self.lookup),('e5',))
        self.assertEqual(matching(rows,{'tag':'Inherited'},None,self.lookup),('e1','e0'))
        self.assertEqual(matching(rows,{'tagged':'true'},None,self.lookup),('e1','e0'))
        before=copy.deepcopy({key:value for key,value in f.saved.items() if key[0]=='epoch'})
        f.put('cell','c0','p1',[])
        self.assertEqual(matching(rows,{},predicate,self.lookup),())
        self.assertEqual({key:value for key,value in f.saved.items() if key[0]=='epoch'},before)

    def test_duplicate_membership_cannot_be_published(self):
        with self.assertRaisesRegex(ValueError,'unique'):
            matching([self.f.rows[0],self.f.rows[0]],{},None,self.lookup)


if __name__=='__main__':unittest.main()
