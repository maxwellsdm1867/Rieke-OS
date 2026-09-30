"""Independent ordinal oracle for the production shared-tag SQLite index.

This directly exercises the index; generation/record callbacks are deterministic
fixtures, not native SQL or service/browser performance claims.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import resource
import time
import uuid

import workspace_shared_tag_index as product


def uid(n):return str(uuid.UUID(int=n))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--epochs',type=int,default=100000);ap.add_argument('--tags',type=int,default=5);ap.add_argument('--samples',type=int,default=20);ap.add_argument('--aggregates',action='store_true');ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():ap.error('Choose an unused receipt')
    if args.tags<5:ap.error('This exact-identity fixture requires at least five tags')
    n=args.epochs;profiles=[uid(9000000+p) for p in range(3)];cells=[uid(1000000+c) for c in range((n+99)//100)]
    rows=[{'epoch_uuid':uid(100000+i),'cell_uuid':cells[i//100]} for i in range(n)]
    epoch_ord={row['epoch_uuid']:i for i,row in enumerate(rows)};cell_ord={value:i for i,value in enumerate(cells)}
    epoch_field='annotations/epoch/tags';cell_field='annotations/cell/tags';effective='annotations/effective/tags'
    def original(kind,i,p):
        if kind=='epoch':return ['common','QC' if i%2==0 else 'qc','é' if i%3==0 else 'e\u0301',f'bucket-{i%17}',f'unique-{i}']+[f'extra-{j}-{p}' for j in range(args.tags-5)]
        return ['common','inherited',f'cell-bucket-{i%7}',f'cell-profile-{p}',f'cell-unique-{i}']
    overrides={};state={'generation':0,'epoch':'fixture-v1'};feed={};read_stats={'calls':0,'loaded':0};inject=[False]
    def tags_for(kind,i,p):return overrides.get((kind,i,p),original(kind,i,p))
    def make_record(kind,i,p):
        tags=tags_for(kind,i,p)
        if tags is None:return None
        return {'target_kind':kind,'target_uuid':rows[i]['epoch_uuid'] if kind=='epoch' else cells[i],
                'profile_uuid':profiles[p],'author_name':'Same display name' if p<2 else 'Third author',
                'revision':1,'tags':tags}
    def records(keys):
        read_stats['calls']+=1
        identities=((kind,i,p) for kind,amount in [('cell',len(cells)),('epoch',n)] for i in range(amount) for p in range(3)) if keys is None else (
            (key['target_kind'],(epoch_ord if key['target_kind']=='epoch' else cell_ord)[key['target_uuid']],profiles.index(key['profile_uuid'])) for key in keys)
        for kind,i,p in identities:
            row=make_record(kind,i,p)
            if row is not None:
                read_stats['loaded']+=1;yield row
                if inject[0]:inject[0]=False;mutate('epoch',n-1,2,['racing','QC'])
    def token():return (state['epoch'],state['generation'])
    def changes(old):
        if old[0]!=state['epoch']:return None
        return ([{'target_kind':kind,'target_uuid':rows[i]['epoch_uuid'] if kind=='epoch' else cells[i],'profile_uuid':profiles[p]}
                for (kind,i,p),version in feed.items() if version>old[1]],token())
    def mutate(kind,i,p,values):
        overrides[(kind,i,p)]=values;state['generation']+=1;feed[(kind,i,p)]=state['generation']
    def validate(row):
        assert len(set(row['tags']))==len(row['tags']) and all(isinstance(tag,str) for tag in row['tags'])
        assert row['profile_uuid'] in profiles and row['revision']==1
        return row['tags']
    def expected_tags(kind,i):return set().union(*(set(tags_for(kind,i if kind=='epoch' else i//100,p) or []) for p in range(3)))
    def summary_oracle():
        tag_counts=Counter();cell_counts=Counter()
        for first in range(0,n,100):
            present=set()
            for i in range(first,min(first+100,n)):
                values=expected_tags('epoch',i)|expected_tags('cell',i);tag_counts.update(values);present.update(values)
            cell_counts.update(present)
        ranked=sorted(tag_counts,key=lambda tag:(-tag_counts[tag],tag.casefold(),tag))[:12]
        return {'shared_tagged_cells':len(cells),'shared_tagged_epochs':n,
            'tags':[{'tag':tag,'epoch_count':tag_counts[tag],'cell_count':cell_counts[tag]} for tag in ranked],
            'total_tags':len(tag_counts),'truncated':len(tag_counts)>12}
    def catalog_oracle(field):
        amount=len(cells) if field==cell_field else n if field in (epoch_field,effective) else 1
        choices=[]
        for ordinal in range(min(50,amount)):
            i=ordinal*100 if field==cell_field else ordinal
            values=sorted(expected_tags('cell',i)) if field==cell_field else sorted(expected_tags('epoch',i)) if field==epoch_field else sorted(expected_tags('epoch',i)|expected_tags('cell',i)) if field==effective else ['Same display name','Third author'] if field=='annotations/authors' else profiles
            count=min(100,n-ordinal*100) if field==cell_field else 1 if field in (epoch_field,effective) else n
            choices.append({'value':values,'type':'array','count':count})
        return amount,choices
    # Independent explicit predicate evaluator. No production matcher is called.
    def expected(predicate,i):
        if 'all' in predicate:return all(expected(item,i) for item in predicate['all'])
        if 'any' in predicate:return any(expected(item,i) for item in predicate['any'])
        if 'not' in predicate:return not expected(predicate['not'],i)
        field=predicate['field'];values=sorted(expected_tags('epoch',i) if field==epoch_field else expected_tags('cell',i) if field==cell_field else expected_tags('epoch',i)|expected_tags('cell',i))
        op=predicate['operator'];value=predicate.get('value')
        if op=='contains':return value in values
        if op=='eq':return values==value
        if op=='ne':return values!=value
        if op=='in':return values in value
        if op=='not_in':return values not in value
        if op=='exists':return True
        if op in ('missing','is_null','gt','gte','lt','lte'):return False
        raise AssertionError(op)
    def leaf(field,op,value=None):return {'field':field,'operator':op,'value':value}
    cases=[('exact_case_upper',leaf(epoch_field,'contains','QC')),('exact_case_lower',leaf(epoch_field,'contains','qc')),
           ('unicode_composed',leaf(epoch_field,'contains','é')),('unicode_decomposed',leaf(epoch_field,'contains','e\u0301')),
           ('inherited',leaf(cell_field,'contains','cell-bucket-2')),('direct_does_not_inherit',leaf(epoch_field,'contains','inherited')),
           ('and',{'all':[leaf(epoch_field,'contains','bucket-3'),leaf(cell_field,'contains','cell-bucket-2')]}),
           ('or',{'any':[leaf(epoch_field,'contains','bucket-3'),leaf(cell_field,'contains','cell-bucket-2')]}),
           ('scoped_not',{'not':leaf(epoch_field,'contains','bucket-3')}),
           ('nested',{'all':[{'any':[leaf(epoch_field,'contains','bucket-3'),leaf(cell_field,'contains','cell-bucket-2')]},{'not':leaf(epoch_field,'contains','unique-503')}]}),
           ('empty_array',leaf(effective,'eq',[])),('missing',leaf(effective,'missing')),('numeric_scalar',leaf(epoch_field,'contains',1)),
           ('exact_union',leaf(epoch_field,'eq',sorted(expected_tags('epoch',503)))),
           ('noncanonical_array_order',leaf(epoch_field,'eq',list(reversed(sorted(expected_tags('epoch',503)))))),
           ('repeated_array_tag',leaf(epoch_field,'eq',['common','common'])),
           ('array_in',leaf(epoch_field,'in',[[],sorted(expected_tags('epoch',503))])),
           ('array_not_in',leaf(epoch_field,'not_in',[[],sorted(expected_tags('epoch',503))]))]
    source_hash=hashlib.sha256(Path(product.__file__).read_bytes()).hexdigest()
    def timings_summary(values):
        ordered=sorted(values)
        return {'samples':len(values),'quantile_method':'nearest_rank',
                **{'p'+str(int(q*100)):ordered[max(0,math.ceil(q*len(ordered))-1)] for q in (.5,.95,.99)},
                'maximum':max(values),'sample_seconds':values}
    manifest={'epochs':n,'profiles':profiles,'tags_per_epoch_profile':args.tags,'cell_tags_per_profile':5,'formula_version':2}
    report={'scope':__doc__,'fixture':manifest,'fixture_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
            'source_sha256_before':source_hash,'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':[],'release_ready':False}
    index=product.SharedTagIndex(generation=token,changes=changes,records=records,validate=validate)
    def check(name,condition,**detail):
        item={'name':name,'passed':bool(condition),**detail};report['cases'].append(item);print(json.dumps(item),flush=True)
        if not condition:raise AssertionError(name)
    try:
        start=time.perf_counter();check('cold_build',index.refresh());report['cold_build_seconds']=time.perf_counter()-start
        full_loaded=read_stats['loaded'];check('all_profiles_indexed',full_loaded==3*(n+len(cells)),loaded=full_loaded)
        if hasattr(index,'storage_stats'):report['storage_after_build']=index.storage_stats()
        if args.aggregates:
            # Product overview ordering follows the established casefold then
            # exact-text tie rule, independently reproduced from ordinal sets.
            wanted=summary_oracle()
            start=time.perf_counter();actual=index.summary(rows);report['cold_summary_seconds']=time.perf_counter()-start
            check('summary_independent_exact_counts',actual==wanted,seconds=report['cold_summary_seconds'])
            fields=[cell_field,epoch_field,effective,'annotations/authors','annotations/author_uuids']
            start=time.perf_counter();catalog=index.catalog(rows,fields);report['cold_catalog_seconds']=time.perf_counter()-start
            for field in fields:
                amount,choices=catalog_oracle(field)
                actual=catalog[field]
                check('catalog_'+field,actual['count']==n and actual['distinct_count']==amount and actual['choices']==choices and actual['choices_truncated']==(amount>50),distinct=actual['distinct_count'])
            summary_times=[];catalog_times=[]
            for _ in range(args.samples):
                start=time.perf_counter();assert index.summary(rows)==wanted;summary_times.append(time.perf_counter()-start)
                start=time.perf_counter();assert index.catalog(rows,fields)==catalog;catalog_times.append(time.perf_counter()-start)
            for name,values in [('summary',summary_times),('catalog',catalog_times)]:
                report['warm_'+name+'_seconds']=timings_summary(values)
            if hasattr(index,'storage_stats'):report['storage_after_aggregates']=index.storage_stats()
        for name,predicate in cases:
            eligible=rows[37::3] if name=='scoped_not' else rows
            wanted=tuple(row['epoch_uuid'] for row in eligible if expected(predicate,epoch_ord[row['epoch_uuid']]))
            start=time.perf_counter();actual,_=index.matching(eligible,{},predicate);seconds=time.perf_counter()-start
            check(name,actual==wanted,matched=len(actual),query_seconds=seconds,uuid_sha256=hashlib.sha256(''.join(actual).encode()).hexdigest())
        # Membership queries load no canonical annotation rows after refresh.
        timings=[]
        for _ in range(args.samples):
            start=time.perf_counter();assert index.refresh();result,_=index.matching(rows,{'tag':'bucket-3'});timings.append(time.perf_counter()-start)
        check('warm_queries_read_zero_annotation_rows',read_stats['loaded']==full_loaded)
        report['warm_match_seconds']=timings_summary(timings)
        for count in (1,1000):
            before=read_stats['loaded'];start=time.perf_counter()
            for i in range(min(count,n)):mutate('epoch',i,0,['QC','modified'])
            assert index.refresh();elapsed=time.perf_counter()-start
            actual,_=index.matching(rows,{'tag':'modified'});wanted=tuple(row['epoch_uuid'] for row in rows[:min(count,n)])
            check(f'delta_{count}_same_revision',actual==wanted and read_stats['loaded']-before==min(count,n),rows_loaded=read_stats['loaded']-before,refresh_seconds=elapsed)
            if args.aggregates:
                wanted_summary=summary_oracle();start=time.perf_counter();actual_summary=index.summary(rows);summary_seconds=time.perf_counter()-start
                start=time.perf_counter();actual_catalog=index.catalog(rows,fields);catalog_seconds=time.perf_counter()-start
                good=actual_summary==wanted_summary
                for field in fields:
                    amount,choices=catalog_oracle(field);good=good and actual_catalog[field]['distinct_count']==amount and actual_catalog[field]['choices']==choices
                check(f'delta_{count}_aggregates_remain_exact',good,summary_seconds=summary_seconds,catalog_seconds=catalog_seconds)
            if hasattr(index,'storage_stats'):report[f'storage_after_delta_{count}']=index.storage_stats()
        for p in range(3):mutate('epoch',0,p,[]);mutate('cell',0,p,[])
        assert index.refresh();actual,_=index.matching(rows,{},leaf(effective,'eq',[]))
        check('empty_tag_rows_and_inheritance_removed',actual==(rows[0]['epoch_uuid'],))
        for p in range(3):mutate('epoch',1,p,None)
        assert index.refresh();actual,_=index.matching(rows,{},leaf(epoch_field,'eq',[]))
        check('deleted_records_leave_exact_empty_membership',actual==(rows[0]['epoch_uuid'],rows[1]['epoch_uuid']))
        old_token=index.token;mutate('epoch',2,0,['race fixture']);inject[0]=True
        try:index.refresh()
        except product.SharedTagsChanged:conflict=True
        else:conflict=False
        check('mixed_generation_build_rejected',conflict and index.token==old_token)
        assert index.refresh();actual,_=index.matching(rows,{'tag':'racing'});check('subsequent_delta_recovers_exact_membership',actual==(rows[-1]['epoch_uuid'],))
        report['stats']=index.stats;report['sqlite_bytes']=sum(path.stat().st_size for path in Path(index.folder.name).iterdir())
        report['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report['source_sha256_after']=hashlib.sha256(Path(product.__file__).read_bytes()).hexdigest();report['source_unchanged']=source_hash==report['source_sha256_after']
        report['passed']=report['source_unchanged'] and all(item['passed'] for item in report['cases'])
    except Exception as error:
        import traceback
        report['error']={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()};report['passed']=False;print(traceback.format_exc(),flush=True)
    finally:
        folder=Path(index.folder.name) if index.folder is not None else None;connection=index.connection
        index.close();report['derived_folder_removed']=folder is None or not folder.exists()
        closed=connection is None
        if connection is not None:
            try:connection.execute('SELECT 1')
            except Exception:closed=True
        report['sqlite_connection_closed']=closed
        report['passed']=report.get('passed',False) and report['derived_folder_removed'] and closed
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    return int(not report['passed'])


if __name__=='__main__':raise SystemExit(main())
