"""Full140 vs priority28: identical payloads, independent real-source counts."""
from pathlib import Path
import argparse,hashlib,json,os,re,resource,shutil,sqlite3,statistics,subprocess,sys,threading,time
ROOT=Path('/private/tmp/disco-priority-benchmark-20261001');PRE=Path('/private/tmp/disco-real-million-20261001')
sys.path[:0]=[str(ROOT/'model'),str(PRE/'typed'),str(PRE/'evals')]
from typed_bounded import TypedBoundedSidecar
from priority_sidecar import PrioritySidecar
import compare_million as previous
canonical=previous.canonical;digest=previous.digest

def save(p,v):
 tmp=p.with_suffix('.part');tmp.write_text(json.dumps(v,indent=2)+'\n');tmp.replace(p)
def prepare():
 ids,rows,_,values,fields,sources=previous.old.load_truth()
 con=sqlite3.connect(f'file:{previous.REAL}?mode=ro&immutable=1',uri=True)
 rr=[dict(epoch_id=i,row=rows[uid]) for i,uid in con.execute('SELECT epoch_id,epoch_uuid FROM epochs')];con.close()
 tail,_=previous.select_tail(rr,1621);tail_ids={r['row']['epoch_uuid'] for r in rr if r['epoch_id'] in tail}
 oldplan=json.loads((PRE/'evals'/'plan.json').read_text());cell=next(c for c in oldplan['cases'] if c['label']=='largest_cell')
 protocols={r['protocol_name'].rsplit('.',1)[-1]:r['protocol_name'] for r in rows.values()}
 def leaf(f,v,op='eq'):return dict(field=f,operator=op,value=v)
 cases=[dict(label='global_page',predicate=None,scope=None,facets=[]),dict(label='cell_page_two_facets',predicate=None,scope=cell['scope'],original_scope=cell['original_scope'],facets=['parameters/currentSpotSize','parameters/useRandomSeed']),
 dict(label='saved_expanding_spot_layout',predicate=None,scope={'protocol':protocols['ExpandingSpots']},facets=['parameters/currentSpotSize']),
 dict(label='saved_history_filter',predicate=leaf('parameters/history1',[0,675]),scope={'protocol':protocols['VariableHistoryNoiseCurInject']},facets=[]),
 dict(label='saved_frequency_filter',predicate=leaf('parameters/frequencyCutoff',100),scope={'protocol':protocols['VariableMeanNoiseCurInject']},facets=[]),
 dict(label='mean_SD_filter',predicate={'all':[leaf('parameters/currentMean',0),leaf('parameters/currentSD',750)]},scope={'protocol':protocols['VariableMeanNoiseCurInject']},facets=[]),
 dict(label='NDF_filter',predicate=leaf('parameters/NDF',4),scope=cell['scope'],original_scope=cell['original_scope'],facets=['parameters/NDF']),
 dict(label='light_path_filter',predicate=leaf('parameters/lightPath','above'),scope=cell['scope'],original_scope=cell['original_scope'],facets=[]),
 dict(label='bath_temperature_filter',predicate=leaf('properties/bathTemperature',31.5),scope=None,facets=[]),
 dict(label='cold_canvas_query',predicate=leaf('parameters/canvasSize',[800,600]),scope=cell['scope'],original_scope=cell['original_scope'],facets=['parameters/canvasSize']),
 dict(label='cold_generator_query',predicate=leaf('parameters/stimulusGenerator','edu.washington.riekelab.chris.stimuli.VariableHistoryNoiseGenerator'),scope=None,facets=[]),
 dict(label='cold_trial_count_query',predicate=leaf('parameters/numberOfTrials',1),scope=cell['scope'],original_scope=cell['original_scope'],facets=[]),
 dict(label='cold_seed_query',predicate=leaf('parameters/seed',0),scope=None,facets=[]),
 dict(label='cold_rig_query',predicate=leaf('metadata/experiment/properties/rig','F (old slice)'),scope=cell['scope'],original_scope=cell['original_scope'],facets=['metadata/experiment/properties/rig']),
 dict(label='global_two_facets',predicate=None,scope=None,facets=['parameters/currentSpotSize','parameters/useRandomSeed'])]
 for case in cases:
  t=dict(case,scope=case.get('original_scope',case['scope']));matched=previous.old.truth_membership(t,ids,values)
  case['count']=len(matched) if 'original_scope' in case else 359*len(matched)+sum(uid in tail_ids for uid in matched)
 plan=dict(cases=cases,real_epochs=2781,replayed_epochs=1000000,shared_core=True,hot_paths=json.loads((ROOT/'hot-fields.json').read_text()))
 save(ROOT/'evals'/'plan.json',plan);print(json.dumps(dict(prepared=True,cases=len(cases),counts={c['label']:c['count'] for c in cases})))

def run(repeats):
 out=ROOT/'evals'/'comparison.json';plan=json.loads((ROOT/'evals'/'plan.json').read_text())
 result=dict(pid=os.getpid(),status='running',results=[],caps=dict(total_seconds=180,operation_seconds=45,peak_rss_bytes=1024**3),source_stats={str(p):[p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns] for p in [PRE/'base.sqlite',PRE/'typed'/'sidecar.sqlite']})
 save(out,result);started=time.monotonic();deadline=[started+47]
 def watch():
  last=0
  while True:
   reason=None
   if time.monotonic()-started>180:reason='180 second worker cap'
   if time.monotonic()>deadline[0]:reason='45 second operation cap'
   if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>1024**3:reason='1GiB RSS cap'
   if time.monotonic()-last>2:
    last=time.monotonic();vm=subprocess.check_output(['/usr/bin/vm_stat'],text=True)
    page=int(re.search(r'page size of (\d+)',vm)[1]);counts={k:int(v) for k,v in re.findall(r'^(Pages[^:]+):\s+(\d+)\.',vm,re.M)}
    if sum(counts.get(k,0) for k in ['Pages free','Pages inactive','Pages speculative'])*page<768*2**20:reason='768MiB RAM floor'
    if shutil.disk_usage(ROOT).free<4*2**30:reason='4GiB disk floor'
   if reason:
    result.update(status='guard_stop',reason=reason,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss);save(out,result);os._exit(91)
   time.sleep(.2)
 threading.Thread(target=watch,daemon=True).start()
 full=TypedBoundedSidecar(PRE/'typed'/'sidecar.sqlite');priority=PrioritySidecar(ROOT/'model'/'priority-million.sqlite')
 result['setup_seconds']=time.monotonic()-started;save(out,result)
 try:
  for case in plan['cases']:
   entry=dict(label=case['label'],count=case['count'],predicate=case['predicate'],scope=case['scope'],facet_fields=case['facets'],status='running',arms={})
   result['results'].append(entry);save(out,result);expected=None
   for sample in range(repeats):
    # Reverse alternating order to reduce systematic order/cache bias.
    order=[('full',full),('priority',priority)] if sample%2==0 else [('priority',priority),('full',full)]
    for label,arm in order:
     deadline[0]=time.monotonic()+47;before=len(priority.materializations);begin=time.perf_counter()
     value=arm.preview(case['predicate'],case['scope'],facet_fields=case['facets']);raw=canonical(value);elapsed=(time.perf_counter()-begin)*1000;deadline[0]=started+180
     assert value['count']==case['count'],(case['label'],value['count'],case['count']);sha=hashlib.sha256(raw).hexdigest()
     if expected is None:expected=sha
     assert sha==expected,case['label']+' payload differs'
     record=entry['arms'].setdefault(label,dict(samples_ms=[],sha256=sha,payload_bytes=len(raw)));record['samples_ms'].append(elapsed)
     if label=='priority':record.setdefault('materializations',[]).extend(priority.materializations[before:])
     save(out,result)
   for record in entry['arms'].values():
    times=record['samples_ms'];record.update(first_ms=times[0],warm_median_ms=statistics.median(times[1:]),max_ms=max(times))
   entry['status']='passed';entry['same_payload']=True
   print(json.dumps(dict(label=case['label'],count=case['count'],full_ms=entry['arms']['full']['warm_median_ms'],priority_ms=entry['arms']['priority']['warm_median_ms'])),flush=True)
   save(out,result)
  result.update(status='complete',all_same_payload=True,materializations=priority.materializations)
 finally:
  result.update(wall_seconds=time.monotonic()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,source_stats_after={p:[Path(p).stat().st_ino,Path(p).stat().st_size,Path(p).stat().st_mtime_ns] for p in result['source_stats']})
  result['source_stats_unchanged']=result['source_stats']==result['source_stats_after'];save(out,result);full.close();priority.close()
  print(json.dumps(dict(status=result['status'],seconds=result['wall_seconds'],peak_rss_bytes=result['peak_rss_bytes'])),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--repeats',type=int,default=5);a=p.parse_args()
 prepare() if a.prepare else run(a.repeats)
