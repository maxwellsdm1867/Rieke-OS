"""Report fresh timings and preserve exact v1/v2 same-output provenance."""
from pathlib import Path
import hashlib,json,sqlite3,sys
base=Path('/private/tmp/disco-real-typed-sqlite-20261001')
old=json.loads((base/'attempts/v1/receipt.json').read_bytes())
p=base/'evals/v2/receipt.json';new=json.loads(p.read_bytes())
assert old['all_oracles_passed'] and new['all_oracles_passed']
assert old['membership_sha256']==new['membership_sha256']
assert old['full_indexed_values_sha256']==new['full_indexed_values_sha256']
assert old['input_before']==new['input_before']==new['input_after']
assert old['page_walks']==new['page_walks']
old_cases={row['label']:row for row in old['results']}
checks=[]
for row in new['results']:
    prev=old_cases[row['label']]
    for name in ['membership_sha256','expected_payload_sha256','facets_sha256','next_page_sha256']:
        assert prev.get(name)==row.get(name),(row['label'],name)
    for backend in ['production_bounded_preview','typed_sqlite_bounded_preview','production_next_page','typed_sqlite_next_page']:
        assert prev.get(backend,{}).get('sha256')==row.get(backend,{}).get('sha256'),(row['label'],backend)
    checks.append(dict(label=row['label'],count=row['count'],payload_sha256=row['expected_payload_sha256'],all_old_new_hashes_equal=True))
new['runtime']=dict(python=sys.version,sqlite=sqlite3.sqlite_version,executable=sys.executable,metadata_recorded_after_run=True)
new['coverage']=old['coverage']
new['candidate_code_sha256']=hashlib.sha256((base/'model/typed_real.py').read_bytes()).hexdigest()
new['candidate_database_sha256']=hashlib.sha256((base/'model/real-typed.sqlite').read_bytes()).hexdigest()
new['attempt']='v2'
new['paired_v1_output_comparison']=dict(all_hashes_equal=True,scenarios=checks,page_walks_equal=True,original_inputs_equal=True)
new['initial_failure_metadata']=json.loads((base/'attempts/initial-failure.json').read_bytes())
p.write_text(json.dumps(new,indent=2)+'\n')
(base/'evals/v2/v1-v2-oracles.json').write_text(json.dumps(new['paired_v1_output_comparison'],indent=2)+'\n')
lines=['The previous typed SQLite approach tested on real metadata, final v2','',
 'All 20 paired bounded comparisons passed. Every v1/v2 scenario membership, count/page/facet payload and next-page hash is identical. Global47-page and actual601-epoch block11-page walks remain identical. Original native data/code inputs stayed unchanged.',
 '', '| Case | Epochs | Current median ms | Typed median ms | Speedup | Typed v1 ms |',
 '|---|---:|---:|---:|---:|---:|']
for row in new['results']:
    a=row['production_bounded_preview']['warm_median_ms'];b=row['typed_sqlite_bounded_preview']['warm_median_ms'];v1=old_cases[row['label']]['typed_sqlite_bounded_preview']['warm_median_ms']
    lines.append(f"| {row['label']} | {row['count']} | {a:.2f} | {b:.2f} | {a/b:.2f}x | {v1:.2f} |")
lines.extend(['','The original v1 empty-UUID regression came from candidate validation decoding every UUID dictionary value. V2 uses a string representative after construction proved each direct field is completely present and string-valued, matching native UUID fast-path semantics. Original acquisition JSON and metadata tables are unchanged.','','Both backends produce the same exact count, 60 chronological metadata rows, cursor, and two requested typed facets. Timing includes JSON serialization. Each case has 11 samples: first reported separately, then 10 warm samples and maximum. Correctness checks precede timing; the first sample is not a cold application startup.'])
for row in new['results']:
    if 'production_next_page' in row:
        a=row['production_next_page']['warm_median_ms'];b=row['typed_sqlite_next_page']['warm_median_ms']
        lines.append(f"Next-page {row['label']}: current {a:.2f} ms, typed {b:.2f} ms.")
lines.extend(['','Tested actual numeric values, integer/float equality (construction smoke), arrays, missing fields, recorded nulls, mixed string/null fields, text, conjunction/disjunction/negation, empty results and explicit full registered eligible-ID scope. Facets preserve JSON types, numeric semantic equality, first60 chronological appearance, missing counts and truncation. No real boolean fixture was observed, so boolean dataset coverage is unproven.','','These metadata-only backend timings do not measure the full application/UI, annotations, waveform I/O or live MySQL source exclusion policy. All three registered source projections are included. The current full141-field catalog/statistics/suggestions is measured separately and is not equivalent to two requested facets. Real2781-epoch timings do not establish performance at one million. Native baseline global row ranking is preloaded outside timing, consistent with warm service state.', '', f"Elapsed {new['seconds']:.3f} seconds, peak RSS {new['peak_rss_bytes']:,} bytes, cap {new['caps']['process_seconds']} seconds /513MiB. Python {sys.version.split()[0]}, SQLite {sqlite3.sqlite_version}.", '', 'The initial pre-v1 partial attempt stopped on a duplicate facet name chosen by the harness. The harness was corrected, all timings rerun, and that failed attempt is recorded in attempts/initial-failure.json; its partial timings are not used. V1 full receipt/report/code remain under attempts/v1.', '', 'Reproduce:','',f"{sys.executable} -B {base/'evals/compare_preview.py'} --run --out {base/'evals/v2'}",''])
(base/'evals/v2/REPORT.md').write_text('\n'.join(lines))
print(json.dumps(dict(all_old_new_hashes_equal=True,case_count=len(checks),seconds=new['seconds'],peak_rss_bytes=new['peak_rss_bytes'],medians=[dict(label=row['label'],native=row['production_bounded_preview']['warm_median_ms'],typed=row['typed_sqlite_bounded_preview']['warm_median_ms']) for row in new['results']]),indent=2))
