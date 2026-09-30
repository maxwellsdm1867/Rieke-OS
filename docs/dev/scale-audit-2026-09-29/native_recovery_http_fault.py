"""Native Flask 507 and subsequent recovery-gap oracle on synthetic metadata."""
import argparse
import copy
import datetime as dt
import errno
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import traceback
from unittest.mock import patch

from benchmark_service_scale import fixture, Details, uid
from recording_workspace import connect, workspace_tables
from workspace_projects import create_project
from workspace_native_mysql import ensure_native_database, stop_native_database
from workspace_disk_index import DiskMetadataIndex
from workspace_api import create_app
import workspace_recovery_store as mirror
import workspace_state_snapshot as snapshot

ROOT=Path(__file__).resolve().parents[3]
FILES=['workspace_api.py','workspace_annotations.py','workspace_recovery_generation.py','workspace_recovery_store.py','workspace_state_snapshot.py']

def hashes():return {name:hashlib.sha256((ROOT/'python'/name).read_bytes()).hexdigest() for name in FILES}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Choose an unused receipt')
    report={'scope':__doc__,'source_hashes_before':hashes(),'cases':[],'release_ready':False};app=None;dj=None;root=None;clean=False
    temporary=Path(tempfile.mkdtemp(prefix='rieke-native-http-fault-')).resolve()
    def check(name,passed,**detail):
        report['cases'].append({'name':name,'passed':bool(passed),**detail});print(json.dumps(report['cases'][-1]),flush=True)
        if not passed:raise AssertionError(name)
    try:
        root=Path(create_project(temporary/'projects','Native HTTP recovery fault oracle')['path']);ensure_native_database(root)
        dj=connect({'kind':'native-project'},project_dir=root);service,protocol=fixture(1000)
        service.project_dir=root;service.project=json.loads((root/'project.json').read_text());service.config=json.loads((root/'catalog.json').read_text());service.dj=dj
        definition=service.protocols[protocol]['definition'];definition['project_uuid']=service.project['project_uuid']
        definition['query']={'version':1,'all':[{'field':'EpochBlock.protocol_name','operator':'eq','value':'Synthetic'}]}
        index=DiskMetadataIndex.build(root/'cache'/'metadata.sqlite',service.rows,Details(service.rows),service.sources,'synthetic-http-fault',service.project['project_uuid'])
        service.disk_index=index;service.details=index.details
        Project,_,_,_=workspace_tables(dj);Project.insert1({'project_uuid':service.project['project_uuid'],'name':service.project['name'],'directory':str(root)})
        app=create_app(root,ROOT/'.rieke-runtime/retinanalysis',service=service);shared=app.extensions['shared_annotations']
        project=service.project['project_uuid'];author=uid(-100);epoch=next(iter(service.rows));stamp=dt.datetime(2026,9,29,12)
        shared.Profile.insert1({'project_uuid':project,'profile_uuid':author,'display_name':'Exact author','created_at':stamp,'created_by':'oracle'})
        shared.Annotation.insert1({'project_uuid':project,'target_kind':'epoch','target_uuid':epoch,'profile_uuid':author,
            'tags':['QC','qc','é','e\u0301','baseline'],'author_name':'Exact author','revision':1,'updated_at':stamp})
        snapshot.save(root,dj.conn(),service=service);before=snapshot.load(root/'app-state.json');before_mark=copy.deepcopy(mirror.inspect(root)['header']['watermark'])
        client=app.test_client();headers={'X-Workspace-Request':'1','Origin':'http://localhost:8766'}
        body={'target_kind':'epoch','target_uuids':[epoch],'profile_uuid':author,'tags_add':['committed-with-backup-failure'],'expected_revisions':{epoch:1}}
        with patch.object(mirror,'write',side_effect=OSError(errno.ENOSPC,'injected backup disk full')) as failure:
            response=client.post('/api/annotations',json=body,headers=headers)
        check('committed_mutation_returns_http_507_saved_true',response.status_code==507 and response.get_json().get('saved') is True and failure.call_count==1,status=response.status_code,payload=response.get_json())
        def sql_row():
            value=dj.conn().query('SELECT tags,revision FROM recording_workspace.shared_annotation WHERE project_uuid=%s AND target_kind=%s AND target_uuid=%s AND profile_uuid=%s',
                (project,'epoch',epoch,author)).fetchone();return (json.loads(value[0]) if isinstance(value[0],(str,bytes)) else value[0],int(value[1]))
        wanted=sorted(['QC','qc','é','e\u0301','baseline','committed-with-backup-failure'])
        tags,revision=sql_row();check('failed_backup_does_not_rollback_or_replay_committed_sql',sorted(tags)==wanted and revision==2,revision=revision)
        check('failed_backup_preserves_previous_complete_mirror',snapshot.load(root/'app-state.json')==before and mirror.inspect(root)['header']['watermark']==before_mark)
        body={'target_kind':'epoch','target_uuids':[epoch],'profile_uuid':author,'tags_add':['next-independent-mutation'],'expected_revisions':{epoch:2}}
        response=client.post('/api/annotations',json=body,headers=headers);check('next_distinct_mutation_returns_success',response.status_code==200,status=response.status_code)
        wanted=sorted(wanted+['next-independent-mutation']);tags,revision=sql_row()
        loaded=snapshot.load(root/'app-state.json');rows=[row for row in loaded['tables']['shared_annotation'] if row['target_uuid']==epoch and row['profile_uuid']==author]
        check('next_success_durably_covers_both_committed_mutations',sorted(tags)==wanted and revision==3 and len(rows)==1 and sorted(rows[0]['tags'])==wanted and rows[0]['revision']==3)
        check('next_success_advances_recovery_watermark',mirror.inspect(root)['header']['watermark']!=before_mark)
        report['source_hashes_after']=hashes();report['source_unchanged']=report['source_hashes_before']==report['source_hashes_after']
    except Exception as error:report['error']={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()};print(traceback.format_exc(),flush=True)
    finally:
        if app is not None:
            shared=app.extensions.get('shared_annotations');index=getattr(shared,'_shared_tag_index',None)
            if index is not None:index.close()
            lock=app.extensions.get('app_state_session_lock')
            if lock is not None:lock.close()
        if dj is not None:dj.conn().close()
        if root is not None:clean=stop_native_database(root)
        report['owned_runtime_stopped']=clean
        if clean:shutil.rmtree(temporary);report['temporary_project_removed']=True
        else:report['preserved_temporary_project']=str(temporary)
        report['passed']=not report.get('error') and clean and report.get('source_unchanged',False) and all(item['passed'] for item in report['cases'])
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    return int(not report['passed'])

if __name__=='__main__':raise SystemExit(main())
