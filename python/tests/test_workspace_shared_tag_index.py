"""Exact multi-profile/inherited membership and incremental source fencing."""
import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

from workspace_annotations import tags
from workspace_predicates import matches
from workspace_predicates import predicate_catalog
from workspace_tree import value_key,value_order,value_label
from workspace_service import validate_tag_filter_predicate
from workspace_shared_tag_index import SharedTagIndex,SharedTagsChanged,FIELDS


class Fixture:
    def __init__(self):
        self.version=1;self.calls=[];self.changes={};self.saved={}
        self.rows=[{'epoch_uuid':f'e{i}','cell_uuid':f'c{i//2}'} for i in range(6)]
        self.put('cell','c0','p1',['Inherited','QC'])
        self.put('epoch','e0','p1',['QC','qc','é'])
        self.put('epoch','e0','p2',['QC','e\u0301'])
        self.put('epoch','e1','p2',[])
        self.put('epoch','e2','p1',['different'])
        self.index=SharedTagIndex(generation=lambda:self.version,
            changes=lambda old:([{'target_kind':key[0],'target_uuid':key[1],'profile_uuid':key[2]}
                for key,value in self.changes.items() if value>old],self.version),
            records=self.records,validate=lambda row:tags(row['tags']))
    def put(self,kind,target,profile,values):
        self.version+=1;key=(kind,target,profile);self.changes[key]=self.version
        self.saved[key]={'target_kind':kind,'target_uuid':target,'profile_uuid':profile,
            'author_name':'same author display name','revision':self.version,'tags':values}
    def records(self,keys):
        self.calls.append(copy.deepcopy(keys))
        selected=self.saved.values() if keys is None else [self.saved[(key['target_kind'],key['target_uuid'],key['profile_uuid'])]
            for key in keys if (key['target_kind'],key['target_uuid'],key['profile_uuid']) in self.saved]
        yield from copy.deepcopy(list(selected))
    def values(self,row):
        cell={tag for (kind,target,_),record in self.saved.items() if kind=='cell' and target==row['cell_uuid'] for tag in record['tags']}
        epoch={tag for (kind,target,_),record in self.saved.items() if kind=='epoch' and target==row['epoch_uuid'] for tag in record['tags']}
        return dict(zip(FIELDS,[sorted(cell),sorted(epoch),sorted(cell|epoch)]))


class SharedTagIndexTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.addCleanup(self.f.index.close)

    def test_exact_case_unicode_profile_union_inheritance_and_all_predicate_operators(self):
        f=self.f;self.assertTrue(f.index.refresh())
        for field in FIELDS:
            predicates=[{'field':field,'operator':op} for op in ('exists','missing','is_null')]
            predicates += [{'field':field,'operator':'contains','value':value} for value in ('QC','qc','é','e\u0301','Inherited','absent')]
            predicates += [{'field':field,'operator':op,'value':value} for op in ('eq','ne') for value in ([],['QC'],['QC','qc'],['qc','QC'],['QC','QC'],['Inherited','QC'])]
            predicates += [{'field':field,'operator':op,'value':[[],['QC'],['different']]} for op in ('in','not_in')]
            for predicate in predicates:
                for node in (predicate,{'not':predicate},{'all':[predicate,{'not':{'field':field,'operator':'missing'}}]}, {'any':[predicate,{'field':field,'operator':'eq','value':[]}]}):
                    with self.subTest(node=node):
                        expected=tuple(row['epoch_uuid'] for row in f.rows if matches(node,f.values(row)))
                        actual,token=f.index.matching(f.rows,{},node)
                        self.assertEqual(actual,expected);self.assertEqual(token,f.version)
        self.assertEqual(len(f.calls),1,'Warm filters must not reread canonical tag JSON')

    def test_scope_order_and_not_complement_exclude_foreign_epochs(self):
        f=self.f;f.index.refresh();rows=[f.rows[5],f.rows[1],f.rows[0]]
        node={'not':{'field':'annotations/epoch/tags','operator':'contains','value':'QC'}}
        self.assertEqual(f.index.matching(rows,{},node)[0],('e5','e1'))
        self.assertEqual(f.index.matching(rows,{'tag':'Inherited'})[0],('e1','e0'))
        self.assertEqual(f.index.matching(rows,{'tagged':'true'})[0],('e1','e0'))

    def test_unrelated_tag_edits_keep_boolean_membership_but_use_fresh_generation(self):
        f=self.f;f.index.refresh()
        predicate={'all':[{'any':[{'field':'annotations/epoch/tags','operator':'contains','value':'QC'},
            {'field':'annotations/cell/tags','operator':'contains','value':'Inherited'}]},
            {'not':{'field':'annotations/effective/tags','operator':'contains','value':'excluded'}}]}
        original,old=f.index.matching(f.rows,{},predicate)
        f.put('epoch','e2','p1',['different','unrelated'])
        f.index.refresh();sql=[];f.index.connection.set_trace_callback(sql.append)
        actual,current=f.index.matching(f.rows,{},predicate)
        self.assertEqual(actual,original);self.assertNotEqual(current,old)
        self.assertFalse(any('FROM filter_scope AS s WHERE' in query for query in sql),sql)
        # Changing a referenced inherited literal must invalidate the result.
        f.put('cell','c0','p1',['QC']);f.index.refresh();sql.clear()
        actual,_=f.index.matching(f.rows,{},predicate)
        self.assertEqual(actual,tuple(row['epoch_uuid'] for row in f.rows if matches(predicate,f.values(row))))
        self.assertTrue(any('FROM filter_scope AS s WHERE' in query for query in sql),sql)

    def test_array_and_empty_memberships_invalidate_on_unrelated_literals(self):
        f=self.f;f.index.refresh()
        queries=[({}, {'field':'annotations/epoch/tags','operator':'eq','value':[]}),
            ({'tagged':'true'},None),({}, {'field':'annotations/epoch/tags','operator':'in','value':[[],['different']]})]
        for filters,predicate in queries:f.index.matching(f.rows,filters,predicate)
        f.put('epoch','e1','p2',['new']);f.index.refresh()
        self.assertEqual(f.index.match_cache_bytes,0)
        for filters,predicate in queries:
            expected=tuple(row['epoch_uuid'] for row in f.rows if
                (bool(f.values(row)['annotations/effective/tags']) if predicate is None else matches(predicate,f.values(row))))
            self.assertEqual(f.index.matching(f.rows,filters,predicate)[0],expected)

    def test_large_change_batches_drop_matches_without_retaining_old_tag_sets(self):
        f=self.f;f.index.refresh();f.index.matching(f.rows,{'tag':'QC'})
        f.put('epoch','e2','p1',['different','unrelated'])
        f.put('epoch','e3','p1',['unrelated'])
        with patch('workspace_shared_tag_index.MATCH_DELTA_MAX_RECORDS',1):f.index.refresh()
        self.assertEqual(f.index.match_cache_bytes,0)
        self.assertEqual(f.index.matching(f.rows,{'tag':'QC'})[0],('e0','e1'))

    def test_exact_literal_invalidation_handles_case_unicode_deletions_and_author_only_changes(self):
        f=self.f;f.index.refresh()
        f.index.matching(f.rows,{'tag':'QC'});f.index.matching(f.rows,{'tag':'é'})
        f.put('epoch','e0','p1',['QC','é'])  # Only lowercase qc was removed.
        f.index.refresh();self.assertEqual(len(f.index.match_cache),2)
        f.put('epoch','e0','p1',['QC','e\u0301'])
        f.index.refresh();self.assertEqual(len(f.index.match_cache),1)
        f.saved[('epoch','e0','p1')]['author_name']='Changed stored name'
        f.version+=1;f.changes[('epoch','e0','p1')]=f.version
        f.index.refresh();self.assertEqual(len(f.index.match_cache),1)
        del f.saved[('epoch','e0','p1')];f.version+=1;f.changes[('epoch','e0','p1')]=f.version
        f.index.refresh();self.assertEqual(len(f.index.match_cache),0)
        self.assertEqual(f.index.matching(f.rows,{'tag':'QC'})[0],('e0','e1'))

    def test_incremental_edits_deletion_and_profile_changes_load_only_changed_rows(self):
        f=self.f;f.index.refresh();f.calls.clear()
        f.put('epoch','e2','p1',['QC','new'])
        key=('cell','c0','p1');del f.saved[key];f.version+=1;f.changes[key]=f.version
        f.version+=1;f.changes[('profile','p1','p1')]=f.version
        f.index.refresh()
        self.assertEqual(len(f.calls),1)
        self.assertCountEqual(f.calls[0],[{'target_kind':'epoch','target_uuid':'e2','profile_uuid':'p1'},
            {'target_kind':'cell','target_uuid':'c0','profile_uuid':'p1'}])
        self.assertEqual(f.index.matching(f.rows,{'tag':'QC'})[0],('e0','e2'))
        self.assertEqual(f.index.stats['full_builds'],1);self.assertEqual(f.index.stats['delta_updates'],1)

    def test_generation_race_and_invalid_tags_never_publish_a_partial_index(self):
        f=self.f;f.index.refresh();old=f.index.token
        f.put('epoch','e2','p1',['new'])
        original=f.index.records
        def racing(keys):
            yield from original(keys)
            f.version+=1
        f.index.records=racing
        with self.assertRaises(SharedTagsChanged):f.index.refresh()
        self.assertEqual(f.index.token,old)
        f.index.records=original;f.index.refresh()
        f.put('epoch','e2','p1',['duplicate','duplicate'])
        with self.assertRaises(ValueError):f.index.refresh()
        with self.assertRaises(SharedTagsChanged):f.index.matching(f.rows,{'tag':'new'})

    def test_unavailable_generation_never_uses_old_cached_membership(self):
        f=self.f;f.index.refresh();f.version=None
        self.assertFalse(f.index.refresh())
        with self.assertRaises(SharedTagsChanged):f.index.matching(f.rows,{'tag':'QC'})

    def test_large_valid_literals_do_not_exceed_sqlite_variable_limit(self):
        f=self.f;f.index.refresh()
        predicate={'any':[{'field':'annotations/effective/tags','operator':'eq',
            'value':[f't{number:02}' for number in range(100)]} for _ in range(70)]}
        predicate=validate_tag_filter_predicate(json.dumps(predicate))
        f.index.connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER,999)
        self.assertEqual(f.index.matching(f.rows,{},predicate)[0],())

    def test_summary_is_exact_across_profiles_inheritance_and_empty_scope(self):
        f=self.f;f.index.refresh()
        for rows in (f.rows,[f.rows[1],f.rows[0]],[]):
            expected_tags={};cells=set();epochs=set()
            for row in rows:
                for tag in f.values(row)['annotations/effective/tags']:
                    item=expected_tags.setdefault(tag,[set(),set()]);item[0].add(row['epoch_uuid']);item[1].add(row['cell_uuid'])
                    epochs.add(row['epoch_uuid'])
                if f.values(row)['annotations/cell/tags']:cells.add(row['cell_uuid'])
            counts=sorted([{'tag':tag,'epoch_count':len(e),'cell_count':len(c)} for tag,(e,c) in expected_tags.items()],
                key=lambda item:(-item['epoch_count'],item['tag'].casefold(),item['tag']))
            expected={'shared_tagged_cells':len(cells),'shared_tagged_epochs':len(epochs),'tags':counts[:12],
                'total_tags':len(counts),'truncated':len(counts)>12}
            self.assertEqual(f.index.summary(rows),expected)
            self.assertEqual(f.index.summary(rows),expected)
        self.assertEqual(len(f.calls),1)

    def test_catalog_matches_exact_legacy_arrays_authorship_order_and_bounded_choices(self):
        f=self.f
        for number in range(70):
            row={'epoch_uuid':f'x{number}','cell_uuid':'extra'};f.rows.append(row)
            f.put('epoch',row['epoch_uuid'],'p3',[f'unique-{number}', 'quoted"tag','\\slash','Σ'])
        f.index.refresh()
        fields=[*FIELDS,'annotations/authors','annotations/author_uuids']
        actual=f.index.catalog(f.rows,fields)
        for field in fields:
            values={}
            for row in f.rows:
                effective=[record for (kind,target,_),record in f.saved.items()
                    if (kind=='epoch' and target==row['epoch_uuid'] or kind=='cell' and target==row['cell_uuid']) and record['tags']]
                current=f.values(row)
                current['annotations/authors']=sorted({r['author_name'] for r in effective})
                current['annotations/author_uuids']=sorted({r['profile_uuid'] for r in effective})
                values[row['epoch_uuid']]={field:current[field]}
            distinct={value_key(current[field]):current[field] for current in values.values()}
            expected=predicate_catalog({'fields':[{'id':field}]},values)['fields'][0]
            self.assertEqual(actual[field]['choices'],expected['choices'])
            self.assertEqual(actual[field]['choices_truncated'],expected['choices_truncated'])
            self.assertEqual(actual[field]['distinct_count'],len(distinct))
            self.assertEqual(actual[field]['examples'],[value_label(value)[:160] for value in sorted(distinct.values(),key=value_order)[:5]])
        f.index.catalog(f.rows,fields)
        self.assertEqual(len(f.calls),1)

    def test_incremental_aggregates_match_clean_rebuild_after_changes_and_tombstones(self):
        f=self.f;f.index.refresh();fields=[*FIELDS,'annotations/authors','annotations/author_uuids']
        f.index.catalog(f.rows,fields);f.index.summary(f.rows)
        for number in range(18):
            kind='cell' if number%3==0 else 'epoch'
            target=f'c{number%3}' if kind=='cell' else f'e{number%6}'
            profile=f'p{number%2+1}'
            f.put(kind,target,profile,[] if number%4==0 else [f'new-{number%5}','QC' if number%2 else 'qc'])
            if number%7==0:
                key=(kind,target,profile);del f.saved[key]
            f.index.refresh()
            reference=SharedTagIndex(generation=lambda:f.version,changes=lambda old:None,
                records=f.records,validate=lambda row:tags(row['tags']))
            try:
                reference.refresh()
                self.assertEqual(f.index.catalog(f.rows,fields),reference.catalog(f.rows,fields))
                self.assertEqual(f.index.summary(f.rows),reference.summary(f.rows))
                self.assertEqual(f.index.matching(f.rows,{'tag':'QC'}),reference.matching(f.rows,{'tag':'QC'}))
            finally:reference.close()

    def test_filter_pagination_does_not_discard_catalog_or_summary_work(self):
        f=self.f;f.index.refresh();fields=list(FIELDS)
        catalog=f.index.catalog(f.rows,fields)
        summary=f.index.summary(f.rows)
        with patch.object(f.index,'_array_sql',side_effect=AssertionError('Do not rebuild catalog arrays while paging')):
            f.index.matching(f.rows[::2],{'tag':'QC'})
            f.index.matching(f.rows,{'tag':'Inherited'})
            self.assertEqual(f.index.catalog(f.rows,fields),catalog)
        self.assertEqual(f.index.summary(f.rows),summary)

    def test_cached_membership_is_generation_fenced_and_budgeted(self):
        f=self.f;f.index.refresh()
        first=f.index.matching(f.rows,{'tag':'QC'})[0]
        self.assertIs(f.index.matching(f.rows,{'tag':'QC'})[0],first)
        with patch('workspace_shared_tag_index.MATCH_CACHE_BYTES',1):
            f.put('epoch','e2','p1',['QC']);f.index.refresh()
            self.assertEqual(f.index.matching(f.rows,{'tag':'QC'})[0],('e0','e1','e2'))
            self.assertEqual(f.index.match_cache_bytes,0)
        f.version+=1
        with self.assertRaises(SharedTagsChanged):f.index.matching(f.rows,{'tag':'QC'})

    def test_repeated_edits_reclaim_unused_tag_and_catalog_dictionary_entries(self):
        f=self.f;f.index.refresh();fields=list(FIELDS)
        f.index.catalog(f.rows,fields);f.index.summary(f.rows)
        for number in range(100):
            f.put('epoch','e2','p1',[f'changed-{number}'])
            f.index.refresh()
        current={tag for row in f.saved.values() for tag in row['tags']}
        self.assertEqual(f.index.connection.execute('SELECT COUNT(*) FROM tag_values').fetchone()[0],len(current))
        self.assertEqual(f.index.connection.execute('SELECT COUNT(*) FROM catalog_examples').fetchone()[0],
            f.index.connection.execute('SELECT COUNT(DISTINCT example_id) FROM catalog_buckets').fetchone()[0])
        self.assertFalse(f.index.connection.execute("SELECT 1 FROM summary_tags WHERE tag='changed-0'").fetchone())

    def test_catalog_digest_collisions_never_merge_distinct_exact_arrays(self):
        f=self.f;f.index.refresh();fields=list(FIELDS)
        f.index.connection.create_function('array_hash',1,lambda value:b'forced collision',deterministic=True)
        f.index.catalog(f.rows,fields)
        f.put('epoch','e2','p1',['new exact array']);f.index.refresh()
        reference=SharedTagIndex(generation=lambda:f.version,changes=lambda old:None,
            records=f.records,validate=lambda row:tags(row['tags']))
        try:
            reference.refresh()
            self.assertEqual(f.index.catalog(f.rows,fields),reference.catalog(f.rows,fields))
            self.assertEqual(f.index.connection.execute('SELECT COUNT(DISTINCT value_hash) FROM catalog_buckets').fetchone()[0],1)
            self.assertGreater(f.index.connection.execute('SELECT COUNT(*) FROM catalog_buckets').fetchone()[0],1)
        finally:reference.close()


if __name__=='__main__':unittest.main()
