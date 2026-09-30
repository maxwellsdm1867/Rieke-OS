"""Exact autocomplete counts and attribution survive edits and scope switches."""
import unittest
from unittest.mock import patch
from test_workspace_shared_tag_index import Fixture
from workspace_shared_tag_index import SharedTagsChanged


class SharedVocabularyTests(unittest.TestCase):
    def setUp(self):
        self.fixture=Fixture()
        self.addCleanup(self.fixture.index.close)

    def expected(self, query='', limit=30):
        values={}
        for (kind,target,profile),record in sorted(self.fixture.saved.items()):
            for tag in record['tags']:
                entry=values.setdefault(tag,{'targets':set(),'authors':{}})
                entry['targets'].add((kind,target));entry['authors'][profile]=record['author_name']
        selected=sorted(((tag,value) for tag,value in values.items() if tag.casefold().startswith(query.strip().casefold())),
            key=lambda item:(-len(item[1]['targets']),item[0].casefold(),item[0]))
        return {'tags':[{'tag':tag,'count':len(value['targets']),'authors':[
            {'profile_uuid':key,'display_name':name} for key,name in sorted(value['authors'].items())]} for tag,value in selected[:limit]],
            'scope':'project_shared_annotations','query':query,'total':len(selected),'limit':limit,
            'count_unit':'distinct_annotation_targets','match':'case_insensitive_prefix','has_more':len(selected)>limit}

    def check(self):
        for query in ('','qC','é','e\u0301','different','new','  qc  ','%','_','\U0010ffff','\ud800'):
            for limit in (1,30):
                self.assertEqual(self.fixture.index.suggestions(query,limit),self.expected(query,limit))

    def test_counts_are_targets_not_profiles_or_inherited_epochs_and_warm_reads_are_bounded(self):
        self.check();self.assertEqual(len(self.fixture.calls),1)
        for _ in range(4):self.check()
        self.assertEqual(len(self.fixture.calls),1)
        self.fixture.index.matching(self.fixture.rows[:2],{'tag':'QC'})
        self.check()  # Autocomplete covers the project, not the last filter scope.
        self.assertEqual(len(self.fixture.calls),1)

    def test_edit_remove_delete_and_rebuild_preserve_exact_counts_and_names(self):
        f=self.fixture;self.check()
        for kind,target,profile,tags in [('epoch','e0','p1',['QC','new']),('epoch','e0','p2',[]),
                ('cell','c0','p1',[]),('epoch','e5','p1',['QC']),('epoch','e2','p1',['QC']),
                ('epoch','e5','p1',[]),('epoch','e0','p1',[]),('epoch','e2','p1',[])]:
            f.put(kind,target,profile,tags)
            f.saved[(kind,target,profile)]['author_name']='Distinct stored name '+target
            self.check()
        key=('epoch','e2','p1');del f.saved[key];f.version+=1;f.changes[key]=f.version
        self.check()
        f.index.changes=lambda _:None
        f.put('epoch','e3','p2',['new'])
        self.check();self.assertEqual(f.index.stats['full_builds'],2)

    def test_generation_failure_rolls_back_derived_counts_then_recovers(self):
        f=self.fixture;self.check();f.put('epoch','e2','p1',['QC','new'])
        original=f.index.records
        def race(keys):
            yield from original(keys)
            f.version+=1
        with patch.object(f.index,'records',side_effect=race):
            with self.assertRaises(SharedTagsChanged):f.index.suggestions('',30)
        self.check()

    def test_same_display_names_keep_profiles_separate_and_last_target_name_is_stable(self):
        f=self.fixture
        f.put('epoch','e5','p1',['QC']);f.saved[('epoch','e5','p1')]['author_name']='Final saved name'
        self.check()
        f.put('epoch','e0','p1',['QC']);f.saved[('epoch','e0','p1')]['author_name']='Earlier saved name'
        self.check()
        f.put('epoch','e5','p1',[]);self.check()
        f.put('epoch','e5','p2',['QC']);self.check()

    def test_many_prefixes_bound_author_cache_and_evicted_results_rebuild_exactly(self):
        f=self.fixture
        f.put('epoch','e0','p1',[f'tag-{i:03}' for i in range(80)])
        f.put('epoch','e1','p2',[f'tag-{i:03}' for i in range(80,160)])
        for i in range(160):
            query=f'tag-{i:03}'
            self.assertEqual(f.index.suggestions(query,1),self.expected(query,1))
        self.assertEqual(f.index.connection.execute('SELECT COUNT(*) FROM shared_vocabulary_ready').fetchone()[0],128)
        self.assertEqual(f.index.suggestions('tag-000',1),self.expected('tag-000',1))

    def test_failed_initialization_discards_partial_derived_schema_and_retries_safely(self):
        from workspace_shared_vocabulary import SharedVocabulary
        original=SharedVocabulary.__init__
        def fail_after_schema(vocabulary,index):
            original(vocabulary,index)
            raise OSError('Injected derived storage failure')
        with patch.object(SharedVocabulary,'__init__',fail_after_schema):
            with self.assertRaises(OSError):self.fixture.index.suggestions('',30)
        self.assertIsNone(self.fixture.index.connection)
        self.check()

    def test_large_external_batch_rebuilds_only_vocabulary_without_old_union_copies(self):
        f=self.fixture;self.check()
        f.put('epoch','e1','p2',['new']);f.put('epoch','e2','p1',['new','QC'])
        with patch('workspace_shared_tag_index.MATCH_DELTA_MAX_RECORDS',1), \
             patch.object(f.index.shared_vocabulary,'before',side_effect=AssertionError('No large old-union copy')):
            f.index.refresh()
        self.assertIsNone(f.index.shared_vocabulary)
        self.check();self.assertEqual(f.index.stats['full_builds'],1)

    def test_failed_large_batch_restores_dropped_vocabulary_then_retries(self):
        f=self.fixture;self.check();original=f.index.shared_vocabulary
        f.put('epoch','e1','p2',['new']);f.put('epoch','e2','p1',['new','QC'])
        records=f.index.records
        def race(keys):
            yield from records(keys)
            f.version+=1
        with patch('workspace_shared_tag_index.MATCH_DELTA_MAX_RECORDS',1), \
             patch.object(f.index,'records',side_effect=race):
            with self.assertRaises(SharedTagsChanged):f.index.refresh()
        self.assertIs(f.index.shared_vocabulary,original)
        self.assertTrue(f.index.connection.execute('SELECT COUNT(*) FROM shared_vocabulary_counts').fetchone()[0])
        self.check()


if __name__=='__main__':unittest.main()
