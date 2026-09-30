"""Comprehensive HTTP/native-MySQL/recording workflow test after ./install.sh.

Usage: .rieke-runtime/venv/bin/python packaging/verify_workflows.py --source /path/to/recording.h5
Creates an isolated workspace, rejects Docker invocations and preserves a receipt.
The H5 is read-only and is never included in the release.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from workspace_installation import initialize_workspace
from workspace_native_mysql import stop_native_database


def request(base, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = Request(base+path, data=body, headers={'Content-Type':'application/json','X-Workspace-Request':'1'})
    with urlopen(req, timeout=360) as response:
        return json.load(response)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args();source=args.source.resolve(strict=True)
    if source.suffix.lower() != '.h5' or source.name.lower().endswith(('.auisql.h5', '.asqul.h5')):
        parser.error('Use original Symphony .h5 recordings only')
    before=hashlib.file_digest(source.open('rb'),'sha256').hexdigest()
    output=Path(tempfile.mkdtemp(prefix='rieke-workflows-'))
    workspace=initialize_workspace(output/'workspace',ROOT)
    trap=output/'tools';trap.mkdir();docker=trap/'docker'
    docker.write_text('#!/bin/sh\necho invoked >> "'+str(output/'docker-invoked')+'"\nexit 99\n');docker.chmod(0o755)
    env={**os.environ,'PATH':str(trap)+os.pathsep+os.environ.get('PATH','')}
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    projects=[]
    log=(output/'launcher.log').open('w')
    launcher=subprocess.Popen([str(ROOT/'start.sh'),'--workspace',str(workspace),'--port',str(port)],env=env,stdout=log,stderr=log)
    proof={'platform':sys.platform,'checks':[], 'source_sha256':before}
    def passed(name):
        proof['checks'].append(name);print('PASS:',name,flush=True)
    try:
        for _ in range(300):
            try:
                assert request(base,'/api/health')['status']=='ready';break
            except (OSError,AssertionError):
                if launcher.poll() is not None:raise RuntimeError((output/'launcher.log').read_text())
                time.sleep(.2)
        else:raise TimeoutError('Launcher did not become ready')
        passed('clean-runtime launcher health')
        with urlopen(base) as response:assert b'<title>Disco</title>' in response.read()
        passed('built browser app served')
        assert request(base,'/api/projects')['projects']==[]
        created=request(base,'/api/projects',{'name':'End-to-end verification'})
        print('Created:',json.dumps(created),flush=True)
        project=created.get('project',created);projects.append(project)
        opened=request(base,f"/api/projects/{project['uuid']}/open",{})
        project_base=opened['url'].rstrip('/')
        assert request(project_base,'/api/overview')['counts']['epochs']==0
        assert request(project_base,'/api/storage')['database']['status']=='running'
        passed('create and open native project without Docker')
        job=request(project_base,'/api/imports',{'source_path':str(source)})
        print('Import:',json.dumps(job),flush=True)
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            jobs=request(project_base,'/api/jobs')['jobs']
            if jobs and jobs[0]['status'] in ('complete','completed','failed','interrupted','complete_with_warnings'):
                assert jobs[0]['status'] in ('complete','completed'), jobs[0]
                break
            time.sleep(.5)
        else:raise TimeoutError('Import did not complete')
        request(project_base,'/api/metadata/refresh',{})
        for _ in range(120):
            overview=request(project_base,'/api/overview')
            if overview['counts']['epochs']>0:break
            time.sleep(.5)
        assert overview['counts']['epochs']>0, overview
        proof['counts']=overview['counts'];passed('real H5 parsed and committed to native SQL')
        run_workflows(project_base, source, output, passed)
        protocol=overview['protocols'][0]['protocol_uuid']
        page=request(project_base,f'/api/protocols/{protocol}/epochs?limit=1')
        epoch=page['epochs'][0]['epoch_uuid']
        detail=request(project_base,f'/api/epochs/{epoch}')
        print('Epoch keys:',list(detail),flush=True)
        response=next(row for row in detail['streams'] if row['kind']=='responses')
        stream=response['uuid']
        trace=request(project_base,f'/api/epochs/{epoch}/trace?stream_uuid={stream}&count=100')
        import h5py
        import numpy as np
        with h5py.File(source, 'r') as h5:
            expected=h5[response['data_path']][:100]['quantity'].astype(float)
        np.testing.assert_array_equal(trace['values'],expected)
        assert trace['decimated'] is False
        passed('HTTP trace samples match independent raw H5 read')
        details=request(project_base,f'/api/protocols/{protocol}')
        exported=request(project_base,f'/api/protocols/{protocol}/exports',
            {'format':'wheeler-sqlite','query_revision':details['query_revision']})
        assert exported
        passed('Wheeler SQLite export published from native SQL')
        # Reopen the same project after cleanly stopping its server and SQL.
        record=json.loads((Path(project['path'])/'logs/workspace-server.json').read_text())
        os.kill(record['pid'],signal.SIGTERM);time.sleep(.5)
        stop_native_database(project['path'])
        reopened=request(base,f"/api/projects/{project['uuid']}/open",{})
        again=request(reopened['url'].rstrip('/'),'/api/overview')
        assert again['counts']['epochs']==overview['counts']['epochs']
        expected=json.loads((output/'restart-expectations.json').read_text())
        reopened_base=reopened['url'].rstrip('/')
        assert request(reopened_base,expected['route']+'/masks/export')==expected['mask']
        assert 'exchange-added' in json.dumps(request(reopened_base,'/api/epochs/'+expected['epoch']+'/annotations'))
        assert request(reopened_base,'/api/search-presets/'+expected['preset_uuid'])['version']==2
        assert len(request(reopened_base,'/api/exports')['exports'])==4
        passed('database stop/restart preserves imports, masks, tags, presets and exports')
        assert hashlib.file_digest(source.open('rb'),'sha256').hexdigest()==before
        assert not (output/'docker-invoked').exists()
        passed('source bytes unchanged; zero Docker invocations')
        proof['status']='passed'
    except Exception as error:
        proof['status']='failed'
        proof['error']=str(error)
        raise
    finally:
        for project in projects:
            try:
                record=json.loads((Path(project['path'])/'logs/workspace-server.json').read_text())
                os.kill(record['pid'],signal.SIGTERM)
            except (OSError,ValueError):pass
            try:stop_native_database(project['path'])
            except Exception as error:print('Cleanup:',error)
        launcher.terminate();launcher.wait(timeout=15);log.close()
        (output/'receipt.json').write_text(json.dumps(proof,indent=2)+'\n')
        print('Evidence:',output,flush=True)



def run_workflows(base, source, output, passed):
    import io, sqlite3, zipfile
    from urllib.error import HTTPError
    from scipy.io import loadmat
    from workspace_matlab_masks import read_ugm, write_ugm
    def api(path, body=None, method=None, expected=(200,201,202), raw=False):
        data=json.dumps(body).encode() if body is not None else None
        req=Request(base+path,data=data,method=method,headers={'X-Workspace-Request':'1','Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=600) as response:code,content=response.status,response.read()
        except HTTPError as error:code,content=error.code,error.read()
        assert code in expected,(path,code,content[:1500])
        return content if raw else json.loads(content)
    overview=api('/api/overview');fields=api('/api/explore/predicate-fields')
    (output/'fields.json').write_text(json.dumps(fields,indent=2))
    preview=api('/api/explore/preview',{'predicate':{'all':[]},'splits':'cell'})
    assert len(preview['membership'])==overview['counts']['epochs']
    protocol=max(overview['protocols'],key=lambda p:p['counts']['epochs'])['protocol_uuid'];original=api('/api/protocols/'+protocol)
    rows=api(f'/api/protocols/{protocol}/epochs?limit=100')['epochs'];epoch=rows[0]['epoch_uuid'];detail=api('/api/epochs/'+epoch)
    (output/'epoch.json').write_text(json.dumps(detail,indent=2))
    field=next(f for f in fields['fields'] if f.get('path')=='EpochBlock.protocol_name' or f['id'] in ('protocol','protocol_name','EpochBlock.protocol_name'))
    protocol_name=detail['protocol_name']
    query={'predicate':{'field':field['id'],'operator':'eq','value':protocol_name},'splits':'cell'}
    selected=api('/api/explore/preview',query);selected_ids={r['uuid'] for r in selected['membership']}
    assert epoch in selected_ids
    revision=api('/api/explore/revisions',{**query,'name':'Verified acquisition query'})
    (output/'revision.json').write_text(json.dumps(revision,indent=2))
    rid=revision['revision_uuid']
    assert api('/api/explore/revisions/'+rid)['recipe']==revision['recipe']
    api('/api/explore/revisions')
    body={**query,'name':'Verified saved method','pinned':True}
    preset=api('/api/search-presets',body);pid=preset['preset_uuid']
    assert api('/api/search-presets/'+pid,{**body,'description':'Tested update','expected_version':1},method='PUT')['version']==2
    api('/api/search-presets/'+pid,{**body,'expected_version':1},method='PUT',expected=(409,))
    api(f'/api/search-presets/{pid}/versions/1');api(f'/api/search-presets/{pid}/download?version=2')
    api('/api/search-presets/resolve',{'predicate':query['predicate']});api('/api/explore/run',query)
    api('/api/explore/preview',{'predicate':{'field':'unknown','operator':'eq','value':1},'splits':''},expected=(400,))
    passed('predicate queries, immutable revisions, pinned versioned presets and stale edit rejection')
    options=api(f'/api/explore/revisions/{rid}/protocol-options')
    pinned=api(f'/api/explore/revisions/{rid}/create-protocol',{'name':'Workflow selection','protocol_id':protocol_name,'expected_recipe_sha256':options['expected_recipe_sha256']})
    protocol=pinned['protocol_uuid'];route='/api/protocols/'+protocol;state=api(route)
    page=api(route+'/epochs?limit=100');epoch=page['epochs'][0]['epoch_uuid'];detail=api('/api/epochs/'+epoch)
    layout=api(route+'/tree-layout')
    saved_layout=api(route+'/tree-layout',{'split_order':['cell','block'],'expected_version':layout['version']},method='PUT')
    assert saved_layout['split_order']==['cell','block']
    api(route+'/tree-layout',{'split_order':['cell'],'expected_version':layout['version']},method='PUT',expected=(409,))
    api(route+'/tree?splits=cell,block')
    passed('create working protocol from saved query and persist tree layout with stale conflict')
    mask=api(route+'/masks/export');assert {r['epoch_uuid'] for r in mask['epochs']}==selected_ids
    mask['epochs'][0]['included']=False;excluded=mask['epochs'][0]['epoch_uuid']
    api(route+'/masks/import',{'mask':mask,'query_revision':state['query_revision']})
    api(route+'/masks/import',{'mask':mask,'query_revision':state['query_revision']},expected=(409,))
    assert api(route+'/masks/export')==mask
    passed('complete JSON inclusion mask roundtrip and stale mask rejection')
    row=next(r for r in api(route+'/epochs?limit=100')['epochs'] if r['epoch_uuid']==epoch)
    curation={'epoch_uuids':[epoch],'changes':{'review_state':'approved','tags_add':['curated-test']},'expected_revisions':{epoch:row['curation']['revision']},'query_revision':api(route)['query_revision']}
    api(route+'/curation',curation)
    api(route+'/curation',curation,expected=(409,))
    row=next(r for r in api(route+'/epochs?limit=100')['epochs'] if r['epoch_uuid']==epoch)
    assert row['curation']['review_state']=='approved' and 'curated-test' in row['curation']['tags']
    passed('protocol curation approval and tags with stale-save conflict')
    profile=api('/api/annotation-profiles',{'display_name':'Workflow scientist'});author=profile['profile_uuid']
    def tag(kind,identity,name,rev=0):
        return api('/api/annotations',{'target_kind':kind,'target_uuids':[identity],'profile_uuid':author,'tags_add':[name],'expected_revisions':{identity:rev}})
    cell=detail['cell_uuid'];tag('cell',cell,'verified-cell');tag('epoch',epoch,'verified-epoch')
    api('/api/annotations',{'target_kind':'epoch','target_uuids':[epoch],'profile_uuid':author,'tags_add':['lost-edit'],'expected_revisions':{epoch:0}},expected=(409,))
    tags=api('/api/epochs/'+epoch+'/annotations');assert 'verified-cell' in json.dumps(tags) and 'verified-epoch' in json.dumps(tags)
    exchange=api('/api/annotations/export')
    document={'format':'rieke-tag-exchange','version':1,'project_uuid':exchange['project_uuid'],'entries':[{'target_kind':'epoch','target_uuid':epoch,'tags':[{'tag':'exchange-added','profile_uuid':author,'author_name':'Workflow scientist'}]}]}
    ex=api('/api/annotations/import/preview',{'document':document});assert ex['addition_count']==1
    tag('epoch',epoch,'concurrent-tag',1)
    api('/api/annotations/import/apply',{'document':document,'preview_token':ex['preview_token'],'profile_uuid':author},expected=(409,))
    ex=api('/api/annotations/import/preview',{'document':document})
    api('/api/annotations/import/apply',{'document':document,'preview_token':ex['preview_token'],'profile_uuid':author})
    assert api('/api/annotations/import/preview',{'document':document})['unchanged_count']==1
    tq={'predicate':{'field':'annotations/epoch/tags','operator':'contains','value':'exchange-added'},'splits':'cell'}
    assert {r['uuid'] for r in api('/api/explore/preview',tq)['membership']}=={epoch}
    passed('author profiles, cell and epoch tags, additive exchange, conflicts, and tag predicates')
    import h5py,numpy as np
    for sample in page['epochs'][:3]:
        d=api('/api/epochs/'+sample['epoch_uuid']);stream=next(s for s in d['streams'] if s['kind']=='responses')
        trace=api(f"/api/epochs/{sample['epoch_uuid']}/trace?stream_uuid={stream['uuid']}&count=100")
        with h5py.File(source,'r') as h5:expected=h5[stream['data_path']][:100]['quantity'].astype(float)
        np.testing.assert_array_equal(trace['values'],expected)
    passed('three HTTP traces exactly match independent original H5 samples')
    verify_qc(api,source,cell,output,passed)
    exports={};included=selected_ids-{excluded}
    download_headers = {}
    for fmt in ('reference-json','wheeler-sqlite','epictree-mat'):
        record=api(route+'/exports',{'format':fmt,'query_revision':api(route)['query_revision'],
            'name':'Client validation export','export_date':'2026-09-28'})
        suffix={'reference-json':'.json','wheeler-sqlite':'.sqlite','epictree-mat':'.zip'}[fmt]
        with urlopen(base+record['download_url'],timeout=600) as response:
            raw=response.read()
            filename=response.info().get_filename()
            assert filename=='Client_validation_export_2026-09-28'+suffix,filename
            download_headers[fmt]={'filename':filename,'content_disposition':response.headers['Content-Disposition']}
        frozen_recipe=json.loads((Path(record['artifact_path']).parent/'recipe.json').read_text())
        assert frozen_recipe['options']['name']=='Client validation export'
        assert frozen_recipe['options']['download_naming']=={'version':1,'date':'2026-09-28'}
        exports[fmt]=(record,raw)
        (output/('download'+suffix)).write_bytes(raw)
    (output/'download-headers.json').write_text(json.dumps(download_headers,indent=2))
    package=json.loads(exports['reference-json'][1]);assert {r['epoch_uuid'] for r in package['epochs']}==included
    with sqlite3.connect(output/'download.sqlite') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert {r[0] for r in db.execute('SELECT epoch_uuid FROM epochs')}==included
        assert db.execute('SELECT count(*) FROM shared_annotations WHERE tag=?',('verified-cell',)).fetchone()[0]>0
    with zipfile.ZipFile(io.BytesIO(exports['epictree-mat'][1])) as z:
        z.extractall(output/'matlab');frozen=json.loads(z.read('recordings.json'));assert {r['epoch_uuid'] for r in frozen['epochs']}==included
    assert 'metadata' in loadmat(output/'matlab/recordings.mat',simplify_cells=True)
    ugm=read_ugm(output/'matlab/selection.ugm');assert set(ugm['epoch_uuids'])==included and all(ugm['mask'])
    passed('named/date-stamped HTTP downloads and frozen naming; JSON, SQLite integrity/relations/tags, MATLAB MAT and UGM membership')
    ugm['mask'][0]=False
    write_ugm(output/'changed.ugm',ugm['epoch_uuids'],ugm['mask'],metadata=ugm['metadata'])
    def upload(dataset):
        boundary='rieke-workflow-upload'
        parts=[]
        for key,value in {'query_revision':api(route)['query_revision'],'dataset_uuid':dataset}.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="changed.ugm"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+(output/'changed.ugm').read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
        request=Request(base+route+'/masks/import-matlab',data=b''.join(parts),headers={'X-Workspace-Request':'1','Content-Type':'multipart/form-data; boundary='+boundary})
        try:
            with urlopen(request,timeout=120) as response:return response.status,response.read()
        except HTTPError as error:return error.code,error.read()
    response=upload(exports['epictree-mat'][0]['dataset_uuid']);assert response[0]==200,response[1]
    updated=api(route+'/masks/export');decisions={r['epoch_uuid']:r['included'] for r in updated['epochs']}
    assert not decisions[excluded] and not decisions[ugm['epoch_uuids'][0]]
    response=upload(exports['reference-json'][0]['dataset_uuid']);assert response[0]==400,response[1]
    for record,raw in exports.values():assert api(record['download_url'],raw=True)==raw
    passed('UGM subset import preserves nonexported decisions; wrong export rejected; exports immutable')
    job=api('/api/imports',{'source_path':str(source)})
    for _ in range(1200):
        jobs=api('/api/jobs')['jobs'];latest=jobs[0]
        if latest['status'] in ('complete','completed','duplicate','failed','interrupted','complete_with_warnings'):
            assert latest['status'] in ('complete','completed','duplicate'),latest
            break
        time.sleep(.5)
    else:raise TimeoutError('Duplicate import')
    assert api('/api/overview')['counts']['epochs']==overview['counts']['epochs']
    passed('duplicate import is idempotent')
    verify_propagation(api,route,query,tq,rid,detail['source_sha256'],passed)
    updated=api(route+'/masks/export')
    (output/'restart-expectations.json').write_text(json.dumps({'route':route,'mask':updated,'epoch':epoch,'preset_uuid':pid}))



def verify_qc(api,source,cell,output,passed):
    import math
    import numpy as np
    import h5py
    qc=api('/api/cells/'+cell+'/qc')
    anchors=api('/api/cells/'+cell+'/qc/block-baselines')
    (output/'qc-baselines.json').write_text(json.dumps(anchors,indent=2))
    def samples(epoch):
        d=api('/api/epochs/'+epoch)
        amp=d['parameters'].get('amp','Amp1')
        stream=next(s for s in d['streams'] if s['kind']=='responses' and s['device']==amp)
        with h5py.File(source,'r') as h5:values=h5[stream['data_path']][:]['quantity'].astype(float)
        return d,stream,values
    for a in anchors['anchors']:
        d,stream,values=samples(a['epoch_uuid']);rate=stream['sample_rate'];n=max(1,math.floor(rate*.001+.5));n2=math.ceil(rate*.002)
        np.testing.assert_allclose([a['mean_mV'],a['median_mV'],a['first_mV'],a['max_2ms_mV']],[values[:n].mean(),np.median(values[:n]),values[0],values[:n2].max()],rtol=1e-12)
        assert a['flags']['first_sample_outside_reference_range']==bool(values[0]<-75 or values[0]>-45)
        assert a['flags']['possible_spike_first_2ms']==bool(values[:n2].max()>-20)
    assert anchors['anchors'],'Source must include eligible block-onset estimates'
    checked=0
    for fam in qc['families']:
        if fam['id'] not in {'expanding_spots','split_field','single_spot','current_step'} or not fam['epoch_count']:continue
        summary=api('/api/cells/'+cell+'/qc/response-summary?family='+fam['id'])
        (output/('qc-summary-'+fam['id']+'.json')).write_text(json.dumps(summary,indent=2))
        for point in summary['points']:
            means=[]
            for m in point['measurements']:
                trial=api('/api/cells/'+cell+'/qc/response?epoch_uuid='+m['epoch_uuid'])
                d,stream,values=samples(m['epoch_uuid']);rate=stream['sample_rate']
                a=math.floor(trial['timing']['pre_ms']*rate/1000+.5);b=math.floor((trial['timing']['pre_ms']+trial['timing']['stim_ms'])*rate/1000+.5)
                np.testing.assert_allclose(m['stim']['mean'],values[a:b].mean(),rtol=1e-12)
                np.testing.assert_allclose(trial['statistics']['stim']['mean'],values[a:b].mean(),rtol=1e-12)
                np.testing.assert_allclose(trial['trace']['values'],values[:trial['trace']['count']],rtol=0,atol=0)
                means.append(values[a:b].mean());checked+=1
            if means:np.testing.assert_allclose(point['response_mean'],np.mean(means),rtol=1e-12)
    assert checked,'Source must include condition responses'
    passed(f'QC block-onset arithmetic ({len(anchors["anchors"])} anchors) and condition/trial response arithmetic ({checked} trials) match independent H5 samples')


def verify_propagation(api,route,query,tag_query,rid,source_sha,passed):
    protocol=route.rsplit('/',1)[1]
    subset=api('/api/explore/revisions',{**tag_query,'name':'One tagged epoch subset','parent_revision_uuid':rid})
    def apply(revision):
        compare=api('/api/explore/revisions/'+revision+'/compare-to-protocol',{'protocol_uuid':protocol})
        body={k:compare[k] for k in ('protocol_uuid','expected_binding_version','expected_query_revision')}
        result=api('/api/explore/revisions/'+revision+'/apply-to-protocol',body)
        api('/api/explore/revisions/'+revision+'/apply-to-protocol',body,expected=(409,))
        return result
    removed=apply(subset['revision_uuid']);assert removed['next_count']==1 and removed['diff_counts']['removed']>0
    restored=apply(rid);assert restored['next_count']>1
    passed('query-to-protocol compare/apply removes exact members, restores original query, rejects stale binding')
    source='/api/data-stores/'+source_sha
    # Lifecycle version is included in detail state; no source bytes are edited.
    detail=api(source)
    def state(action):
        detail=api(source)
        version=detail.get('state',detail).get('version')
        if version is None:version=detail['source']['version']
        return api(source+'/state',{'action':action,'expected_version':version,'reason':'Disposable workflow verification'})
    state('exclude')
    plan=api(source+'/propagation-preview',{})
    item=next(i for i in plan['protocols'] if i['protocol_uuid']==protocol)
    body={'protocol_uuid':protocol,'expected_preview_revision':item['expected_preview_revision']}
    assert api(source+'/propagate',body)['next_count']==0
    api(source+'/propagate',body,expected=(409,))
    state('include')
    plan=api(source+'/propagation-preview',{})
    item=next(i for i in plan['protocols'] if i['protocol_uuid']==protocol)
    assert api(source+'/propagate',{'protocol_uuid':protocol,'expected_preview_revision':item['expected_preview_revision']})['next_count']==restored['next_count']
    passed('source eligibility exclude/include propagation changes working membership and rejects stale preview')

if __name__=='__main__':main()
