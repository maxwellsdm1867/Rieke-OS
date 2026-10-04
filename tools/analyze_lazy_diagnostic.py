import json,pathlib,statistics,sys
root=pathlib.Path(__file__).resolve().parent
run=root/'evidence'/sys.argv[1];receipt=json.loads((run/'comparison.json').read_text())
def cpu(s):
 total=0
 for part in s.split(':'):total=total*60+float(part)
 return total
rows=[]
for v in receipt['variants']:
 events={x['name']:x['elapsed_ms']/1000 for x in v['events']}
 row={'mode':v['mode'],'sample':v['sample_name'],'passed':v['passed']}
 for name in ['window.available','window.visible','root.usable','project1.selected','project1.backend_ready','project1.authoritative_interaction','science.first_authoritative_result']:
  row[name+'_s']=events[name]
 row['project_selected_to_authority_s']=events['project1.authoritative_interaction']-events['project1.selected']
 row['project_selected_to_exact_trace_s']=events['science.first_authoritative_result']-events['project1.selected']
 row['import_to_exact_trace_s']=events['science.first_authoritative_result']-events['science.import.request']
 row['quit_to_zero_s']=events['quit.zero_owned_processes']-events['quit.request']
 cpu_by_pid={}
 for sample in v['resources']:
  for p in sample['processes']:cpu_by_pid[p['pid']]=max(cpu_by_pid.get(p['pid'],0),cpu(p['cpu_time']))
 row['sampled_cpu_sum_s']=sum(cpu_by_pid.values())
 row['sampled_aggregate_rss_peak_mib']=max(sum(p['rss_kib'] for p in s['processes']) for s in v['resources'])/1024
 chooser_samples=[s for s in v['resources'] if s['elapsed_ms']<=events['root.usable']*1000]
 root_samples=[p for s in chooser_samples for p in s['processes'] if p['pid']==v['root_pid']]
 row['sampled_root_rss_before_chooser_mib']=max(p['rss_kib'] for p in root_samples)/1024 if root_samples else None
 row['sample_count']=len(v['resources']);row['sampling_errors']=v['sampling_errors'];row['phase_spans']=[]
 for path in (run/('phases-'+v['sample_name'])).glob('*.jsonl'):
  marks=[json.loads(line) for line in path.read_text().splitlines()];begins={}
  for mark in marks:
   key=(mark['phase'],mark['span'])
   if mark['state']=='begin':begins[key]=mark
   if mark['state']=='end' and key in begins:
    start=begins[key];pid=mark['pid'];role='root' if pid==v['root_pid'] else 'project' if pid in [p['pid'] for p in v['projects']] else 'import-worker'
    row['phase_spans'].append({'pid':pid,'role':role,'phase':mark['phase'],'seconds':(mark['monotonic_ns']-start['monotonic_ns'])/1e9,'full_hash':any(x['phase']=='runtime.full_hash.completed' and start['monotonic_ns']<=x['monotonic_ns']<=mark['monotonic_ns'] for x in marks)})
 rows.append(row)
summary={'started_at':receipt['started_at'],'ended_at':receipt['ended_at'],'passed':receipt['passed'],'source_commit':'5310eb6c2047ba026dbe9242af9b41f6b50c3694','samples':rows,'means':{},'limits':['Two samples per variant, counterbalanced order; no percentile or release budget.','Fresh profiles, OS cache uncontrolled; no install/cold-cache claim.','CPU is sampled cumulative sum and can miss short-lived processes; aggregate RSS includes shared pages.','Exact trace is authenticated HTTP plus analytic oracle; renderer refresh is separate, not trace-chart paint.']}
for mode in sorted(set(r['mode'] for r in rows)):
 current=[r for r in rows if r['mode']==mode];summary['means'][mode]={key:statistics.mean(r[key] for r in current) for key,value in current[0].items() if (key.endswith('_s') or key.endswith('_mib')) and value is not None}
(run/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({'means':summary['means'],'limits':summary['limits']},indent=2))
