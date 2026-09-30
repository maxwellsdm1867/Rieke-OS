"""Compose exact hierarchical predicates from persistent native tag lookups."""
from __future__ import annotations

FIELDS={'annotations/cell/tags':('cell',), 'annotations/epoch/tags':('epoch',),
        'annotations/effective/tags':('cell','epoch')}


def matching(rows,filters,predicate,lookup):
    """Preserve eligible order and intersect cell inheritance with epoch tags."""
    order=[];cells={}
    for row in rows:
        key=row['epoch_uuid'];order.append(key)
        cells.setdefault(row['cell_uuid'],set()).add(key)
    universe=set(order)
    if len(universe)!=len(order):raise ValueError('Expected unique epoch identities in the tag-filter scope')
    memo={}
    def expand(targets):
        result=set()
        for kind,target in targets:
            if kind=='epoch':
                if target in universe:result.add(target)
            elif kind=='cell':result.update(cells.get(target,()))
            else:raise ValueError('Invalid native tag target kind')
        return result
    def contains(field,tag):
        if not isinstance(tag,str) or not 1<=len(tag)<=255:return set()
        key=(field,tag)
        if key not in memo:memo[key]=expand(lookup.targets(tag,FIELDS[field]))
        return memo[key]
    def equal(field,values):
        if (not isinstance(values,list) or any(not isinstance(tag,str) for tag in values)
                or values!=sorted(set(values))):return set()
        result=set(universe)
        for tag in values:
            result.intersection_update(contains(field,tag))
            if not result:return result
        return result-expand(lookup.targets_outside(values,FIELDS[field]))
    def walk(node):
        if 'all' in node:
            result=set(universe)
            for child in node['all']:
                result.intersection_update(walk(child))
                if not result:break
            return result
        if 'any' in node:
            result=set()
            for child in node['any']:result.update(walk(child))
            return result
        if 'not' in node:return universe-walk(node['not'])
        field=node['field'];operator=node['operator']
        if field not in FIELDS:raise ValueError('Unknown shared tag filter field')
        if operator=='exists':return set(universe)
        if operator in ('missing','is_null'):return set()
        value=node['value']
        if operator=='contains':return contains(field,value)
        if operator in ('eq','ne'):
            result=equal(field,value)
            return universe-result if operator=='ne' else result
        if operator in ('in','not_in'):
            result=set()
            for values in value:result.update(equal(field,values))
            return universe-result if operator=='not_in' else result
        return set()
    result=set(universe)
    if 'tag' in filters:result.intersection_update(contains('annotations/effective/tags',filters['tag']))
    if 'tagged' in filters:result.intersection_update(expand(lookup.tagged_targets()))
    if predicate is not None:result.intersection_update(walk(predicate))
    return tuple(key for key in order if key in result)


def suggestions(lookup,query,limit):
    """Rank the compact persisted dictionary; memberships only serve point seeks."""
    from workspace_native_tag_lookup import SCHEMA,TABLE,INDEX,DICTIONARY,AUTHORS
    lookup.fill_fold_keys()
    prefix=query.strip().casefold()
    try:fold=prefix.encode('utf-8')
    except UnicodeEncodeError:fold=None
    where='project_uuid=%s';arguments=(lookup.project_uuid,)
    if fold is None:where+=' AND FALSE'
    elif fold:
        where+=' AND fold_key>=%s AND fold_key<%s';arguments+=(fold,fold+b'\xff')
    dictionary_index='by_prefix' if fold else 'by_rank'
    total=int(lookup._rows(f'SELECT COUNT(*) AS amount FROM `{SCHEMA}`.`{DICTIONARY}` FORCE INDEX (by_prefix) WHERE '+where,arguments)[0]['amount'])
    ranked=lookup._rows(f'SELECT tag,target_count FROM `{SCHEMA}`.`{DICTIONARY}` FORCE INDEX ({dictionary_index}) WHERE '+where+
        ' ORDER BY target_count DESC,fold_key,tag LIMIT %s',arguments+(limit,))
    selected=[(bytes(row['tag']).decode('utf-8'),int(row['target_count'])) for row in ranked]
    authors={tag:[] for tag,_ in selected}
    if selected:
        placeholders=','.join('%s' for _ in selected)
        profiles=lookup._rows(f'SELECT tag,profile_uuid FROM `{SCHEMA}`.`{AUTHORS}` '
            f'WHERE project_uuid=%s AND tag IN ({placeholders})',(lookup.project_uuid,*(tag.encode('utf-8') for tag,_ in selected)))
        winners=[]
        for profile in profiles:
            row=lookup._rows(f'SELECT target_kind,target_uuid FROM `{SCHEMA}`.`{TABLE}` FORCE INDEX ({INDEX}) '
                'WHERE project_uuid=%s AND tag=%s AND profile_uuid=%s ORDER BY target_kind DESC,target_uuid DESC LIMIT 1',
                (lookup.project_uuid,bytes(profile['tag']),profile['profile_uuid']))
            if len(row)!=1:raise ValueError('Shared annotation authors changed during tag suggestions; retry')
            winners.append({'tag':profile['tag'],'profile_uuid':profile['profile_uuid'],
                'position':(row[0]['target_kind']+'/'+row[0]['target_uuid']).encode('ascii')})
        by_key={}
        for row in winners:
            kind,target=bytes(row['position']).decode('ascii').split('/',1)
            key=(kind,target,row['profile_uuid'])
            by_key.setdefault(key,[]).append(bytes(row['tag']).decode('utf-8'))
        keys=list(by_key)
        for offset in range(0,len(keys),200):
            batch=keys[offset:offset+200]
            # Bind complete canonical primary keys. Joining ASCII lookup fields
            # to UTF-8 canonical columns would coerce indexed columns and scan.
            tuples=','.join('(%s,%s,%s)' for _ in batch)
            source=lookup._rows(f'SELECT target_kind,target_uuid,profile_uuid,author_name '
                f'FROM `{SCHEMA}`.`shared_annotation` WHERE project_uuid=%s '
                f'AND (target_kind,target_uuid,profile_uuid) IN ({tuples})',
                (lookup.project_uuid,*(value for key in batch for value in key)))
            found=set()
            for row in source:
                key=(row['target_kind'],row['target_uuid'],row['profile_uuid']);found.add(key)
                for tag in by_key[key]:authors[tag].append({'profile_uuid':row['profile_uuid'],'display_name':row['author_name']})
            if found!=set(batch):raise ValueError('Shared annotation authors changed during tag suggestions; retry')
    return {'tags':[{'tag':tag,'count':count,'authors':sorted(authors[tag],key=lambda a:a['profile_uuid'])} for tag,count in selected],
        'scope':'project_shared_annotations','query':query,'total':total,'limit':limit,
        'count_unit':'distinct_annotation_targets','match':'case_insensitive_prefix','has_more':total>limit}
