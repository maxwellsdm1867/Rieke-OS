"""Owned gzip64 full-path diagnostic. SQL remains doubled; source verification and sealed index are canonical."""
import argparse,hashlib,json,os,signal,sys,threading,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
source=args.source.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(source/'python'),str(source/'python/tests')]
from benchmarks.prepared_geometry.fixture import build
fixture,app,meta=build(source,output,1000,200)
app._got_first_request=False
import numpy as np
expected_path=output/'expected-f64le.bin';expected=expected_path.read_bytes()
values=np.frombuffer(expected,dtype='<f8');tracefile=Path(meta['owned_h5_path'])
service=fixture.case.service
reader=app.extensions['protocol_state_reader']
assert reader._native_contract(), 'Canonical protocol policy rejected owned fixture'
assert app.extensions['trace_views']._canonical(), 'Prepared-display canonical policy rejected owned fixture'
import workspace_trace_native as native_trace
native_counts={'admitted':0,'fallback':0};original_native_read=native_trace.read_native_values
def observed_native_read(*values,**options):
 result=original_native_read(*values,**options);native_counts['admitted' if result is not None else 'fallback']+=1;return result
native_trace.read_native_values=observed_native_read
original_reduce=native_trace.reduce_native_display
reduce_counts={'admitted':0,'fallback':0}
def observed_reduce(*values,**options):
 result=original_reduce(*values,**options);reduce_counts['admitted' if result is not None else 'fallback']+=1;return result
native_trace.reduce_native_display=observed_reduce
for name in ['trace_expected','incoming_trace_expected','million_trace_expected']:
 entry=meta[name];entry.update(ramp=False,values_first=float(values[0]),values_last=float(values[entry['count']-1]))
meta['diagnostic']={'authority':'prepared-display-sql-double','native_mysql':False,'layout':{'dtype':[('quantity','<f8'),('units','S10')],'chunks':[64],'gzip':4},'payload_sha256':hashlib.sha256(expected).hexdigest(),'actual_h5_sha256':hashlib.sha256(tracefile.read_bytes()).hexdigest(),'contextual_source_hash_is_admission_double':False, 'sealed_index':True,'cache_condition':'OS-warm created/hashed fixture; H5 handles reopened; fresh renderer each sample; prepared metadata outside trace clock','fixture_bound_override':False}
from flask import Response,request,g,jsonify
@app.get('/__diagnostic__/expected-f64le')
def expected_payload():return Response(expected,mimetype='application/octet-stream')
@app.get('/__diagnostic__/status')
def diagnostic_status():return jsonify(native_contract=reader._native_contract(),authority='prepared-display-sql-double',native_counts=native_counts,reduce_counts=reduce_counts,helper_abi=native_trace._load_helper().disco_trace_inflate_abi() if native_trace._load_helper() else None,prepared_display_canonical=app.extensions['trace_views']._canonical(),source_verifier_canonical=getattr(service._verified_source,'__func__',None).__module__=='workspace_service')
heap=None
if (source/'python/workspace_process_heap.py').is_file():
 from workspace_process_heap import install as install_heap
 heap=install_heap(app)
from flask import send_from_directory
assets=output.parent/'browser'/'production-dist'
@app.get('/__workflow__')
def production_shell():return send_from_directory(assets,'index.html')
@app.get('/__workflow-assets/<path:name>')
def production_asset(name):return send_from_directory(assets,name)
from werkzeug.serving import make_server
server=make_server('127.0.0.1',0,app,threaded=True)
meta['port']=server.server_port;meta['http_server']='werkzeug-threaded';meta['direct_origin']=True
(output/'server.json').write_text(json.dumps(meta,indent=2))
def stop(*_):threading.Thread(target=server.shutdown,daemon=True).start()
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
try:server.serve_forever()
finally:
 server.server_close()
 if fixture.doCleanups() is not True:raise RuntimeError('Owned fixture cleanup failed')
 if heap is not None:heap.close()
 (output/'cleanup.json').write_text(json.dumps({'server_closed':True,'fixture_closed':True}))
