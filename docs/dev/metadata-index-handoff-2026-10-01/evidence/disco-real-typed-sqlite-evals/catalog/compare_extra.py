"""Aggregate the two full catalog attribution arms without changing earlier receipts."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
baseline=json.loads((ROOT/'current-measure.json').read_text())
arms={name:json.loads((ROOT/('extra-'+name+'.json')).read_text()) for name in ['analyze-only','typed-current-catalog']}
for arm in arms.values():
    assert arm['all_oracles_passed'] and arm['owned_database_unchanged_during_catalog']
    assert arm['source_hashes']==arm['source_hashes_after']
assert arms['analyze-only']['original_tables']==arms['typed-current-catalog']['original_tables']
assert arms['analyze-only']['source_hashes']==arms['typed-current-catalog']['source_hashes']
rows=[]
for original in baseline['scopes']:
    if original['label'] not in ['global','largest_cell']: continue
    row=dict(label=original['label'],epochs=original['epochs'],earlier_unanalyzed_current_warm_median_ms=original['warm_median_ms'])
    for name,arm in arms.items():
        current=next(s for s in arm['scopes'] if s['label']==original['label'])
        assert current['output_sha256']==original['output_sha256']
        assert current['membership_sha256']==original['membership_sha256']
        row[name]={k:current[k] for k in ['samples_ms','warm_median_ms','warm_min_ms','warm_max_ms','field_count','output_sha256','exact_original_catalog_parity']}
    row['typed_relative_to_analyze_only']=row['typed-current-catalog']['warm_median_ms']/row['analyze-only']['warm_median_ms']
    rows.append(row)
report=dict(status='complete',all_oracles_passed=True,scopes=rows,original_tables=arms['analyze-only']['original_tables'],source_hashes=arms['analyze-only']['source_hashes'],arms={name:dict(receipt=str(ROOT/('extra-'+name+'.json')),owned_sha256=arm['owned_sha256'],sqlite_stat1_rows=arm['sqlite_stat1_rows'],sqlite_stat1_sha256=arm['sqlite_stat1_sha256'],process_peak_rss_mib=arm['process_peak_rss_mib']) for name,arm in arms.items()},conclusion='Adding the typed auxiliary tables does not accelerate unmodified current full catalog computation. ANALYZE-only also leaves global and largest-cell full catalogs far above 100ms. The fast typed bounded filtering/page operation does not fix the existing all-field preview computation unless the application adopts a different catalog query/response path.',sampling='Attribution arms: independent serial processes; one excluded warmup and five measured warm repeats per scope; JSON encoding included. Earlier unanalyzed baseline reports four warm repeats after its first measured call, so its latency comparison is contextual rather than a balanced randomized trial.',limitations=['Only 2781 actual epochs; no million-epoch qualification','Full catalog plus JSON only, not full API preview endpoint or app','Five serial warm samples; performance differences among analyzed full-catalog arms are descriptive; no statistical engine-ranking claim','Full catalog output hashes, all seven original table counts/content hashes and source/module pre/post SHA equality checked'])
(ROOT/'extra-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(status='complete',all_oracles_passed=True,scopes=rows)))
