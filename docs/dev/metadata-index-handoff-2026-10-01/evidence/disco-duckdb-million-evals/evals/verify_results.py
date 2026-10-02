"""Replay receipt correctness/coverage gates; does not certify production release."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).parent
load=lambda relative:json.loads((ROOT/relative).read_text())
score=load('browser/scorecard.json')
required=['select_epoch_metadata','search_selected_epoch_metadata','reopen_cell_cached','scroll_loaded_tree','expand_cell_first_time','expand_block_first_time','next_cell_page_60','first10_selected_action_http_total','api_contrast_filter_preview']
assert [x['key'] for x in score['required_actions']]==required,'Original nine-action coverage changed'
receipts=[load(p) for p in ['measurements/sqlite-normalized/receipt.json','measurements/duckdb-million/receipt.json','measurements/sqlite-adjustment-final/queries/receipt.json']]
assert all(x['passed'] and x['epochs']==1000000 and len(x['operations'])==10 and x['module_sha256']==x['module_sha256_after'] for x in receipts)
for triples in zip(*(x['operations'] for x in receipts)):
 assert len({x['name'] for x in triples})==1 and len({x['result_sha256'] for x in triples})==1
 assert all(x['oracle_passed'] and len(x['samples_seconds'])==10 for x in triples)
browsers=[load('browser/'+engine+'/browser.json') for engine in ('sqlite','duckdb')]
for browser in browsers:
 assert browser['passed'] and browser['epochs']==1000000 and not browser['errors']
 assert browser['required_actions']==required[:7]
 for name in required[:7]:assert sum(x['name']==name for x in browser['measurements'])==5
 assert browser['backend_oracle']['passed']
assert browsers[0]['api_pages']==browsers[1]['api_pages'],'Complete page semantics differ'
assert load('tagging/receipt.json')['passed']
for path in ['measurements/catalog-100k/receipt.json','measurements/catalog-million/receipt.json']:assert load(path)['status']=='passed'
controls=load('measurements/catalog-100k/receipt.json')['operations'];assert controls[0]['catalog_sha256']==controls[1]['catalog_sha256']
adjustment=load('measurements/sqlite-adjustment-final/receipt.json');assert adjustment['passed'] and adjustment['source_database_sha256_before']==adjustment['source_database_sha256_after']
assert score['required_actions'][-1]['one_million_sqlite']['status']!='measured'
assert score['required_actions'][-1]['one_million_duckdb']['status']!='measured'
qualification=load('QUALIFICATION.json');assert not qualification['full_original_million_filter_preview_qualified'] and not qualification['full_million_production_application_qualified']
print('Receipt correctness/coverage gates pass; original million full preview and production release remain unqualified.')
