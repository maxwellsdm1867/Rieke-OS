"""Retest the previously tried exact batched full-catalog implementation."""
import importlib.util,json,resource,sys,time,types
from pathlib import Path
ROOT=Path('/private/tmp/disco-real-million-20261001')
sys.path[:0]=[str(ROOT/'typed'),str(ROOT/'evals'),'/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python']
from typed_bounded import TypedBoundedSidecar
from compare_million import save,digest
from collections import OrderedDict
import threading,workspace_disk_index as module
candidate=TypedBoundedSidecar(ROOT/'typed'/'sidecar.sqlite')
seal=json.loads((ROOT/'base.sqlite.sha256.json').read_text());source=ROOT/'base.sqlite';prior=json.loads((ROOT/'evals'/'native-page-slow5.json').read_text())
assert prior['source_stat_unchanged'] and prior['input_stat']==[source.stat().st_ino,source.stat().st_size,source.stat().st_mtime_ns]
n=module.DiskMetadataIndex();n.path=source;n.generation=seal['generation'];n.project_uuid=seal['project_uuid'];n._lease=None;n._closed=False;n._signature=module._signature(source)
n._definitions=candidate.definitions;n._catalog_cache=None;n._predicate_cache=None;n._epoch_count=1000000
n._detail_cache=OrderedDict();n._detail_lock=threading.RLock();n._details_reference=None;n._detail_cache_costs={};n._detail_cache_bytes=0;n._metadata_decoder=module.MetadataDecoder()
code=Path('/private/tmp/disco-duckdb-million-20261001/python/workspace_disk_index.py')
namespace=importlib.util.spec_from_file_location('prior_batched_disk_index',code);batched=importlib.util.module_from_spec(namespace);namespace.loader.exec_module(batched)
n.catalog=types.MethodType(batched.DiskMetadataIndex.catalog,n)
plan=json.loads((ROOT/'evals'/'plan.json').read_text());cell=next(c['scope'] for c in plan['cases'] if c['label']=='largest_cell');ids=list(candidate.iter_membership(scope=cell))
times=[];expected=json.loads((ROOT/'evals'/'extra-actions.json').read_text())['results']['full_cell_catalog']['sha256']
for _ in range(5):
 begin=time.perf_counter();result=n.catalog(ids=ids,known_fields=candidate.definitions);sha=digest(result);times.append((time.perf_counter()-begin)*1000)
 assert sha==expected,'Full native 141-field catalog differs'
import statistics,hashlib
out=dict(all_passed=True,total=result['total'],fields=len(result['fields']),first_ms=times[0],warm_median_ms=statistics.median(times[1:]),samples_ms=times,sha256=sha,source_code_sha256=hashlib.sha256(code.read_bytes()).hexdigest(),source_code_path=str(code),peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,policy='Previously tried batched catalog method only, bound to verified current reader; current values/detail methods unchanged. Same 687-epoch selection and 141-field complete output.')
save(ROOT/'evals'/'batched-catalog.json',out);print(json.dumps(out),flush=True);n.close();candidate.close()
