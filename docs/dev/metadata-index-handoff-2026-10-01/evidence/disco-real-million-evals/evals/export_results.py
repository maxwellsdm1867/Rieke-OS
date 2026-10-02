"""Export reproducible scripts/receipts; scientific database files stay private."""
from pathlib import Path
import hashlib,json,shutil,sqlite3,sys
ROOT=Path('/private/tmp/disco-real-million-20261001')
OUT=Path('/PATH/TO/LOCAL_HOME/.codex/visualizations/2026/09/30/44e8c032-ebe9-5595-a229-ef960d4865bd/disco-real-million-evals')
OUT.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads((ROOT/p).read_text())
def items(p):return {r['label']:r for r in read(p)['results']}
current={k:v for k,v in items('evals/native-page-slow5.json').items() if v['status']=='passed'}
current.update({k:v for k,v in items('evals/native-page.json').items() if v['status']=='passed'})
page=items('evals/typed-bounded-page.json');native_facets=items('evals/native-facets.json');facets=items('evals/typed-bounded-facets.json')
old_facets=items('evals/typed-bounded-facets-v2.json');old_page=items('evals/typed-page-v1.json')
base=read('base.receipt.json');build=read('typed/build-million.receipt.json');oracle=read('evals/membership-oracle.json')
assert oracle['all_passed'] and read('evals/final-selective-facets.json')['all_passed']
comparisons=[]
for label,entry in page.items():
 assert entry['status']=='passed'
 prev=current.get(label)
 if prev:assert prev['sha256']==entry['sha256']
 comparisons.append(dict(label=label,count=entry['count'],native_ms=prev['warm_median_ms'] if prev else None,typed_ms=entry['warm_median_ms'],same_payload=bool(prev),native_samples=len(prev['samples_ms']) if prev else 0,typed_samples=len(entry['samples_ms'])))
for label,entry in facets.items():
 assert entry['sha256']==old_facets[label]['sha256']
 prev=native_facets[label]
 if prev['status']=='passed':assert prev['sha256']==entry['sha256']
 independent=next(r for r in oracle['checks'] if r['label']==label)
 assert independent['facets_oracle_passed'] and independent['preview_sha256']==entry['sha256']
summary=dict(dataset=base,build=build,page_comparisons=comparisons,facets={label:dict(native_status=native_facets[label]['status'],native_ms=native_facets[label].get('warm_median_ms'),typed_ms=entry['warm_median_ms'],previous_typed_ms=old_facets[label]['warm_median_ms']) for label,entry in facets.items()},membership_oracle=oracle,input_preservation=read('evals/preservation.json'),extra_actions=read('evals/extra-actions.json'),batched_catalog=read('evals/batched-catalog.json'),full_catalog=read('evals/full-catalog.json'))
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for directory in ['typed','evals']:
 target=OUT/directory;target.mkdir(exist_ok=True)
 for path in (ROOT/directory).iterdir():
  if path.is_file() and path.suffix in {'.py','.json','.log','.md'}:shutil.copy2(path,target/path.name)
shutil.copy2('/private/tmp/disco-duckdb-million-20261001/python/workspace_disk_index.py',OUT/'typed'/'prior_batched_workspace_disk_index.py')
for name in ['replay_real.py','base.receipt.json','base.sqlite.sha256.json','fixture-oracle.json']:
 shutil.copy2(ROOT/name,OUT/name)

def ms(value):return f'{value/1000:.2f} s' if value>=1000 else f'{value:.2f} ms'
def table(rows):return '\n'.join(rows)
page_table=['| Action: exact count + first 60 rows, no facets | Matched epochs | Current native path | Final typed path |','|---|---:|---:|---:|']
for row in comparisons:
 page_table.append(f"| {row['label']} | {row['count']:,} | {ms(row['native_ms']) if row['native_ms'] is not None else 'Not timed'} | {ms(row['typed_ms'])} |")
facet_table=['| Same count/60-row/two-facet payload | Current native path | Typed v2 | Final typed v3 |','|---|---:|---:|---:|']
for label,entry in facets.items():
 previous=native_facets[label]
 facet_table.append(f"| {label} | {ms(previous['warm_median_ms']) if previous['status']=='passed' else '45 s cap; no completed sample'} | {ms(old_facets[label]['warm_median_ms'])} | {ms(entry['warm_median_ms'])} |")
extra=summary['extra_actions']['results'];catalog=summary['full_catalog'];batched=summary['batched_catalog']
assert batched['all_passed'] and batched['sha256']==extra['full_cell_catalog']['sha256']
extra_table=['| Additional backend action | Measurement |','|---|---:|']
for label,value in extra.items():
 if 'warm_median_ms' in value:extra_table.append(f"| {label} | {ms(value['warm_median_ms'])} |")
 elif 'milliseconds' in value:extra_table.append(f"| {label} | {ms(value['milliseconds'])}; {value['fields']} fields / {value['total']} epochs |")
ui_rows=[
('Select epoch and display metadata','96 ms','Native detail/typed detail exactness and backend timings below; complete UI action not retimed.'),
('Search selected metadata','32 ms','Browser operation on loaded detail; no new million-scale UI timing.'),
('Reopen cached cell','65 ms','Cell backend count/page/two facets measured; browser cache action not retimed.'),
('Scroll loaded rows','33 ms','No database query; million-scale UI/frame-time regression remains unqualified.'),
('Expand unloaded cell','2.48 s','Cell page and block-group backend measured; mounted H5/MySQL eligibility and complete rendered action not retimed.'),
('Expand unloaded block','2.40 s','601-epoch block page/two facets measured; complete rendered action not retimed.'),
('Load next 60 cells','2.14 s','Typed group page and next page measured and structurally checked; UI rendering not retimed.'),
('Tag ten epochs','52 ms','Not retimed. Real mount has one annotation row and zero tags. No canonical annotation writes or million-row tag claim.'),
('Preview metadata filter','3.90 s','Count/page and two requested facets measured separately. Complete 141-field cell catalog measured: original 25.59 s, earlier batching 134 ms. Global eager catalog hit memory cap; this remains separate from two facets.')]
ui_table=['| All nine original everyday actions | Previously recorded UI median | Qualification in this experiment |','|---|---:|---|']+[f'| {name} | {baseline} | {scope} |' for name,baseline,scope in ui_rows]
index_seconds=sum(build['timings'][key] for key in ['core_extract_seconds','chronology_assign_seconds','dictionary_extract_seconds','indexes_seconds'])
text=f'''# Typed SQLite at one million epochs: real-record replay

The typed/indexed projection makes bounded browsing much faster at the one-million target. It uses the existing SQLite engine and native metadata, with no new TypeSQL library. The remaining slow operations are broad scientific filters, global field summaries, and the original eager all-field catalog. This is an isolated backend experiment; the installed app and working checkout were not changed.

## Dataset and provenance

- Exactly **{base['epochs']:,} epochs**, **140 stored query fields**, **{base['epoch_value_links']:,} EAV links**.
- Replay of **2,781 actual mounted epochs** from LOCAL_NATIVE_PROJECT: 359 complete acquisitions plus 1,621 epochs in ten complete recorded blocks. Cells, blocks, groups, source IDs and epoch IDs are mapped into independent acquisition namespaces.
- Real scientific values, null/missing distinctions, mixed numeric representations, arrays, protocol mixture, timestamps and ancestor objects are preserved. Scientific values and timestamps repeat; this does **not** test one million independent recordings or growing scientific-value cardinality.
- Original native filtering eligibility remains unchanged: 140 query fields are not all 340 raw detail paths. Oversized arrays and other excluded values stay available through native detail decoding.
- Base database: **{base['bytes']/1e9:.2f} GB**. Its experimental construction/seal took **{base['total_seconds']:.2f} s**. This corpus construction is separate from the incremental typed-index cost.
- The replay uses an experimental v2 fingerprint and omits the original upfront global catalog caches. Native v1 metadata hashes and DTO ownership/checksums are preserved. Replay IDs/paths do not identify newly acquired readable H5 traces. This is a metadata-query qualification, not a complete native acquisition/import qualification.

## Added cost

- Auxiliary typed database: **{build['added_bytes']/1e9:.3f} GB**, **{100*build['added_bytes']/base['bytes']:.1f}%** additional storage. The seven native tables stay in one shared immutable base; their size is not counted twice.
- Extracting core columns/dictionary, assigning chronological ranks and creating indexes: **{index_seconds:.2f} s**.
- Total including exhaustive core-equality proofs, ANALYZE and integrity checks: **{build['wall_seconds']:.2f} s**. Equality proofs alone were {build['timings']['core_equality_proof_seconds']:.2f} s.
- Build peak RSS: **{build['max_rss_bytes']/1e6:.2f} MB**. Final page comparison peak: **{read('evals/typed-bounded-page.json')['peak_rss_bytes']/1e6:.2f} MB**. Final facet comparison peak: **{read('evals/typed-bounded-facets.json')['peak_rss_bytes']/1e6:.2f} MB**.
- The normal native full-file verification/open took **{read('evals/native-page-slow5.json')['native_open_seconds']:.2f} s**, separately from query timing. Subsequent native workers reused that proven generation and unchanged file signature. This startup cost remains relevant to production integration.

## Equal-output page comparison

Both arms return the **exact match count, the first 60 chronological native row DTOs, cursor and empty facets**. Every completed native payload hash equals the final candidate. Current means the unchanged production `DiskMetadataIndex.match`/query methods on this same million corpus, not the currently mounted 2,781-epoch app latency.

{table(page_table)}

The native warm comparator uses a compact UUID-to-rank cache instead of the app's eager million-row JSON cache. It verifies chronology and excludes this cache's setup from query timing. This gives the current query path a viable warm comparator without claiming the full current app can start/render a million epochs within the experiment's memory budget. The current API's MySQL/source eligibility lookups, transport, waveform reads and UI rendering are excluded.

## Equal-output requested metadata summaries

These previews add precisely two real fields, `parameters/useRandomSeed` and `parameters/currentSpotSize`: semantic value counts, exact present/missing counts, chronological first representatives, 60-choice truncation flags, native rows and cursor. They are not the original 141-field filter-editor catalog.

{table(facet_table)}

The candidate's four facet results were independently reconstructed from **every selected epoch's real-source lineage and values**, including global and protocol-wide cases whose native comparison timed out. The completed cell/block native hashes match exactly. A timeout is a retained failure to complete within the budget, not an invented latency or output-equivalence pass.

## Bottlenecks and measured adjustments

1. The earlier typed `_page` joined wide native `row_json` before limiting broad results. The compound filter took **{ms(old_page['compound_all']['warm_median_ms'])}**. Selecting and materializing narrow epoch IDs/ranks before retrieving at most 61 native DTOs reduced it to **{ms(page['compound_all']['warm_median_ms'])}**, with identical payload hashes.
2. The facet plan scanned a project-wide field posting list even for one selected cell. A structurally bounded cell/block/group query now drives from its typed core index and point-reads each epoch's requested values. Cell preview fell from **{ms(old_facets['largest_cell']['warm_median_ms'])}** to **{ms(facets['largest_cell']['warm_median_ms'])}**, with the same output hash. Global/protocol summaries retain the original aggregate plan and stayed near three seconds.
3. Broad scientific predicates still process hundreds of thousands of memberships. Final numeric/array filters are about 0.83–0.87 s; compound predicates about 1.5–1.7 s; the missing-field query about 2.27 s. Typed dictionaries alone do not make all such operations instant.

The changes are query-only, preserve the existing predicate/DTO contract and require no additional database build or library. Final code is `typed/typed_bounded.py`; the earlier versions and all receipts are retained.

## Additional actions and the full catalog

{table(extra_table)}

Original uncached global full-catalog attempt: **{catalog['status']}**; reason **{catalog.get('reason','none')}**; measured peak RSS **{catalog.get('peak_rss_bytes',0)/1e6:.2f} MB**. It calls the unchanged native all-field catalog, including row loading, per-field summaries, derived joint fields, grouping suggestions and layout generation. The experiment intentionally had no persisted global catalog cache. Its result must not be presented as the speed of the cached production global catalog or the two-facet preview.

The previously tried batched full-catalog query was also retested, preserving all 141 fields, derived joint values, suggestions and layout: **25.59 s → {ms(batched['warm_median_ms'])}** for the same 687-epoch cell in the million-row database. All five optimized output hashes equal the native original. This is a separate SQL batching improvement; it does not require the typed tables and does not fix the global eager row load. Its exact earlier source and measurement are retained in `typed/prior_batched_workspace_disk_index.py` and `evals/batched-catalog.json`.

Typed tables are not yet wired into the original all-field catalog. Existing cached detail behavior should be retained; a typed projection does not require replacing the native decoder/cache. Nonempty metadata-derived groups are qualified here; complete native tree behavior, including empty branches, remains an integration check.

## All nine everyday actions retained

{table(ui_table)}

The screenshot medians are historical reference measurements, not rerun million-scale results. Backend equivalents are explicitly distinguished from complete everyday UI actions. No omitted UI/annotation action is silently marked passed.

## Correctness, limits and reproducibility

- Every returned member in all twelve million-scale predicate/scope scenarios was checked against independent Python truth from the actual 2,781-record EAV dataset and replay lineage. Exact expected counts establish completeness; ordered membership hashes are saved.
- All 5,562 two-copy fixture DTOs and EAV records were originally checked against recursive real-source rewrites using the native decoder. The final candidate passed 22 predicate checks, both chronological pages, details, complete metadata-derived group walks and all 140-field validation/error checks.
- Final selective facets passed 140 exact native comparisons spanning every query field across cell and block scopes. Earlier/final page and facet output hashes match wherever timings completed.
- Timings include JSON serialization. Candidate page measurements use five samples; facet measurements use three. Expensive native comparisons use two samples, except the cell page's five retained samples. A two-sample warm median is only one warm observation; these are directional local experiments, not robust p95/p99 estimates. First samples follow setup and are not cold-start UI measurements.
- Owned workers have time/RSS limits; resource-limited and manually interrupted exploration receipts remain visible. All measured arms ran serially. No live MySQL writes, app package rebuilds, or mounted recording modifications occurred.
- Full source/base checksums and before/after code/manifest identities are in `evals/preservation.json`. Scientific `.sqlite` files remain in the private temporary experiment folder and are not copied to this artifact or published to GitHub.
- Reproduction uses the repository's existing Python 3.11.13 / SQLite 3.50.4 runtime. Scripts retain exact source paths and command arguments in logs/receipts. Start with `replay_real.py`, `typed/build_sidecar.py`, `evals/compare_million.py`, and the independent oracle scripts; preserve the safeguards and shared immutable-source packaging.

## Decision

Keep SQLite and this compact typed projection as the candidate for bounded browsing; retain the previously tested batched query for full selected-cell catalogs. The measured upfront index cost buys substantial improvements in small selections and initial pages. Integrate it behind the existing API/DTOs in an isolated testing build, preserve current detail and annotation behavior, and qualify every everyday UI action before merging. Broad filter counts/global summaries should run separately from the initial visible page and can use generation-bound aggregate caches. The complete all-field catalog needs its own projection/cache strategy; this experiment does not establish that it is fast.

DuckDB was not retested on this million real-record corpus. The earlier smaller/synthetic engine comparisons cannot settle its performance here; this result establishes a strong SQLite path without requiring an engine migration.
'''
(OUT/'RESULTS.md').write_text(text)
files={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-sha256.json'}
(OUT/'artifact-sha256.json').write_text(json.dumps(files,indent=2)+'\n')
print(json.dumps(dict(artifact=str(OUT),files=len(files),completed_native_comparisons=len(current),all_oracles_passed=True)))
