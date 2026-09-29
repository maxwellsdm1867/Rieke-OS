import sys,time,tempfile,resource,json
from pathlib import Path
from collections.abc import Mapping
from workspace_disk_index import DiskMetadataIndex
n=int(sys.argv[1]);field_count=int(sys.argv[2])
rows=[dict(epoch_uuid=f'e-{i}',cell_uuid=f'c-{i//100}',cell_label=f'Cell {i//100}',date='2026-09-24',cell_type='ON',block_uuid=f'b-{i//20}',block_start_time=f't-{i//20}',protocol_name='Synthetic',source_sha256='synthetic',group_uuid='g',group_label='g') for i in range(n)]
class Details(Mapping):
 def __getitem__(self,key):
  i=int(key[2:]);return {'parameters':{f'axis{k}':(i//(k+1))%7 for k in range(field_count-8)}}
 def __len__(self):return n
 def __iter__(self):return (r['epoch_uuid'] for r in rows)
p=Path(tempfile.mkdtemp(prefix='rieke-disk-index-bench-'))/'index.sqlite'
t=time.perf_counter();index=DiskMetadataIndex.build(p,rows,Details(),[{'source_sha256':'synthetic'}],'benchmark','fixture');build=time.perf_counter()-t
t=time.perf_counter();opened=DiskMetadataIndex.open(p,'benchmark','fixture');catalog=opened.catalog();warm=time.perf_counter()-t
t=time.perf_counter();vals=dict(opened.values(fields=['date','cell','block']).items());projection=time.perf_counter()-t
t=time.perf_counter();matched=opened.match({'field':'parameters/axis0','operator':'eq','value':3});match=time.perf_counter()-t
print(json.dumps(dict(epochs=n,fields=len(catalog['fields']),build_seconds=build,open_catalog_seconds=warm,three_column_seconds=projection,predicate_seconds=match,matched=len(matched[1]),db_bytes=p.stat().st_size,maxrss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,path=str(p))))
