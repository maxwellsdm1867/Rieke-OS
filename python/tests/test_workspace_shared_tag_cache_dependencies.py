"""Deterministic dependency-cache oracle using canonical rows and plain sets.

The scalar evaluator below does not call the production predicate matcher or
SQLite query builder. Every round primes eight cached queries, mutates canonical
records, refreshes the real SQLite index, then checks exact membership and order.
"""
import random
import unittest

from test_workspace_shared_tag_index import Fixture


FIELDS=('annotations/cell/tags','annotations/epoch/tags','annotations/effective/tags')


def scalar_values(saved,row):
    cell=set();epoch=set()
    for (kind,target,_),record in saved.items():
        if kind=='cell' and target==row['cell_uuid']:cell.update(record['tags'])
        if kind=='epoch' and target==row['epoch_uuid']:epoch.update(record['tags'])
    return {FIELDS[0]:sorted(cell),FIELDS[1]:sorted(epoch),FIELDS[2]:sorted(cell|epoch)}


def scalar_matches(node,values):
    if 'all' in node:return all(scalar_matches(child,values) for child in node['all'])
    if 'any' in node:return any(scalar_matches(child,values) for child in node['any'])
    if 'not' in node:return not scalar_matches(node['not'],values)
    actual=values[node['field']];operator=node['operator']
    # All three annotation fields exist as arrays even without saved records.
    if operator=='exists':return True
    if operator in ('missing','is_null'):return False
    expected=node['value']
    if operator=='contains':return expected in actual
    if operator=='eq':return actual==expected
    if operator=='ne':return actual!=expected
    if operator=='in':return any(actual==candidate for candidate in expected)
    if operator=='not_in':return all(actual!=candidate for candidate in expected)
    raise AssertionError('Unexpected oracle operator: '+operator)


class SharedTagCacheDependencyOracleTests(unittest.TestCase):
    def test_200_mutation_batches_preserve_exact_cached_membership_and_fresh_tokens(self):
        randomizer=random.Random(20260930)
        fixture=Fixture();self.addCleanup(fixture.index.close)
        vocabulary=['QC','qc','Inherited','different','é','e\u0301','new','absent']
        checks=0
        for step in range(200):
            rows=[fixture.rows[index] for index in randomizer.sample(range(6),randomizer.randrange(1,7))]
            queries=[]
            for _ in range(8):
                field=randomizer.choice(FIELDS)
                operator=randomizer.choice(['contains','eq','ne','in','not_in','exists','missing','is_null'])
                node={'field':field,'operator':operator}
                if operator=='contains':node['value']=randomizer.choice(vocabulary)
                elif operator in ('eq','ne'):
                    node['value']=sorted(randomizer.sample(vocabulary,randomizer.randrange(3)))
                elif operator in ('in','not_in'):
                    node['value']=[[],sorted(randomizer.sample(vocabulary,randomizer.randrange(3)))]
                if randomizer.choice([False,True]):node={'not':node}
                if randomizer.choice([False,True]):
                    node={randomizer.choice(['all','any']):[node,{'field':randomizer.choice(FIELDS),
                        'operator':'contains','value':randomizer.choice(vocabulary)}]}
                filters=randomizer.choice([{}, {}, {'tag':randomizer.choice(vocabulary)},{'tagged':'true'}])
                queries.append((filters,node))
            fixture.index.refresh()
            for filters,node in queries:fixture.index.matching(rows,filters,node)

            for _ in range(randomizer.randrange(1,4)):
                kind=randomizer.choice(['cell','epoch'])
                target=(randomizer.choice(['c0','c1','c2']) if kind=='cell'
                    else randomizer.choice([row['epoch_uuid'] for row in fixture.rows]))
                profile=randomizer.choice(['p1','p2','p3']);key=(kind,target,profile)
                action=randomizer.randrange(4)
                if action==0 and key in fixture.saved:
                    del fixture.saved[key]
                    fixture.version+=1;fixture.changes[key]=fixture.version
                elif action==1 and key in fixture.saved:
                    fixture.saved[key]['author_name']='renamed'
                    fixture.version+=1;fixture.changes[key]=fixture.version
                elif action==2 and fixture.saved:
                    old=randomizer.choice(list(fixture.saved));record=fixture.saved.pop(old)
                    fixture.version+=1;fixture.changes[old]=fixture.version
                    record.update(target_kind=kind,target_uuid=target,profile_uuid=profile,revision=fixture.version)
                    fixture.saved[key]=record;fixture.changes[key]=fixture.version
                else:
                    fixture.put(kind,target,profile,randomizer.sample(vocabulary,randomizer.randrange(4)))

            fixture.index.refresh()
            for filters,node in queries:
                expected=[]
                for row in rows:
                    values=scalar_values(fixture.saved,row);effective=values[FIELDS[2]]
                    if (scalar_matches(node,values) and ('tag' not in filters or filters['tag'] in effective)
                            and ('tagged' not in filters or effective)):
                        expected.append(row['epoch_uuid'])
                with self.subTest(batch=step,filters=filters,predicate=node):
                    actual,token=fixture.index.matching(rows,filters,node)
                    self.assertEqual(actual,tuple(expected))
                    self.assertEqual(token,fixture.version)
                    self.assertEqual(fixture.index.match_cache_bytes,
                        sum(entry[1] for entry in fixture.index.match_cache.values()))
                checks+=1
        self.assertEqual(checks,1600)


if __name__=='__main__':unittest.main()
