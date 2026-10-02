"""Verify independent catalog receipts and save a concise aggregate."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
old=json.loads((ROOT/'current-measure.json').read_text())
new=json.loads((ROOT/'optimized-measure.json').read_text())
original=json.loads(Path('/private/tmp/disco-real-data-evals-20261001/engines/receipt.json').read_text())
for key in ['database_sha256','schema_sha256','known_fields_count','known_fields_sha256','python','sqlite']:
    assert old[key]==new[key],key
assert old['sources']['workspace_tree.py']==new['sources']['workspace_tree.py']
assert old['sources']['workspace_predicates.py']==new['sources']['workspace_predicates.py']
assert old['database_unchanged'] and new['database_unchanged']
report=dict(status='complete',data_kind='2781 actual mounted epochs; no synthetic rows',full_catalog_only=True,all_catalog_oracles_passed=True,database_sha256=old['database_sha256'],schema_sha256=old['schema_sha256'],known_fields_count=old['known_fields_count'],known_fields_sha256=old['known_fields_sha256'],sources={'current':old['sources'],'prior_optimized':new['sources']},scopes=[],limitations=old['limitations'],measurement={'processes':'independent serial workers for each implementation','repeats':5,'first_and_four_warm':True,'includes':'catalog result plus canonical JSON encoding','excludes':['scope extraction','DB copy','index open','checksum validation','profiling','API service','browser']},profiles={})
for x,y,z in zip(old['scopes'],new['scopes'],original['scopes']):
    for key in ['label','field','epochs','membership_sha256','output_sha256','output_bytes','field_count','field_ids_sha256','suggestions_sha256','layout_sha256']: assert x[key]==y[key],(x['label'],key)
    for key in ['label','field','epochs','membership_sha256']: assert x[key]==z[key],(x['label'],'original scope',key)
    report['scopes'].append(dict(label=x['label'],field=x['field'],epochs=x['epochs'],membership_sha256=x['membership_sha256'],output_sha256=x['output_sha256'],output_bytes=x['output_bytes'],field_count=x['field_count'],current={k:x[k] for k in ['samples_ms','first_ms','warm_median_ms','warm_max_ms']},prior_optimized={k:y[k] for k in ['samples_ms','first_ms','warm_median_ms','warm_max_ms']},warm_speedup=x['warm_median_ms']/y['warm_median_ms'],fraction_time_reduced=1-y['warm_median_ms']/x['warm_median_ms'],matches_previous_receipt_catalog_hash=x['output_sha256']==z['catalog_plus_json']['sqlite']['output_sha256']))
for name in ['current','optimized']:
    profile=json.loads((ROOT/(name+'-profile.json')).read_text())
    arm=old if name=='current' else new
    by_label={s['label']:s for s in arm['scopes']}
    for scope in profile['scopes']: assert scope['output_sha256']==by_label[scope['label']]['output_sha256']
    report['profiles'][name]=dict(receipt=str(ROOT/(name+'-profile.json')),process_peak_rss_mib=profile['process_peak_rss_mib'],scopes=[dict(label=s['label'],sql_by_category=s['sql_by_category'],top_cumulative=s['top_cumulative'][:8]) for s in profile['scopes']])
report['conclusion']='Prior shared catalog optimization alone saves 24–48% of warm catalog time with exact output parity, without changing datatypes, schema, indexes or sealed database. Still 122–519ms warm across these actual scopes, so full catalog does not meet the proposed 100ms threshold. Batched aggregate statistics and per-cell variation remain the main cost. Typed bounded filters/page test is a separate experiment.'
report['profiling_note']='cProfile and SQL execute/fetch tracing ran in separate untimed calls. Timings in profiles include diagnostic overhead and must not be mixed with latency samples. Trace counts include expanded per-epoch inserts and are retained only by category; no SQL raw values are emitted.'
(ROOT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],scopes=len(report['scopes']),all_oracles_passed=True,all_previous_catalog_hashes_match=all(s['matches_previous_receipt_catalog_hash'] for s in report['scopes']))))
