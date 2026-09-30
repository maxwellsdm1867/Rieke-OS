"""Actual pinned population and catalog validator against a disposable native MySQL.

Creates only a fresh temporary project. Never accepts a project/database address,
never uses Docker, and shuts down its verified owned runtime before removing it.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import traceback
import uuid

from workspace_projects import create_project
from workspace_native_mysql import ensure_native_database, stop_native_database, native_binary
from recording_workspace import connect, assert_new_catalog_identities
import workspace_catalog_identity as validator


def fixture(number):
    def item(name, **extra):
        identity = str(uuid.uuid5(uuid.NAMESPACE_URL, f'rieke-disposable-identity/{number}/{name}'))
        return {'uuid':identity, 'label':name, 'properties':{'integer':1,'float':1.0,'boolean':True,'null':None},
                'attributes':{'uuid':identity}, 'start_time':'06/11/2026 12:34:56:123456', **extra}
    source = item('Experiment', rig_type='PATCH', rig='Rig '+str(number), animals=[])
    animal = item('Animal', preparations=[], sex='F', age='42')
    preparation = item('Preparation', cells=[], region='central')
    source['animals']=[animal]; animal['preparations']=[preparation]
    for n in range(2):
        cell = item('cell-'+str(n), type='ON', epoch_groups=[]); cell['label']='Cell3'
        group = item('group-'+str(n), epoch_blocks=[])
        block = item('block-'+str(n), protocolID='example.Protocol', parameters={}, epochs=[])
        epoch = item('epoch-'+str(n), parameters={'contrast':.5,'control':True,'count':1,'float_count':1.0}, responses={}, stimuli={})
        response = item('response-'+str(n), h5path=f'/experiment/{number}/cell/{n}/epoch/responses/Amp1',
                        sampleRate=10000.0,sampleRateUnits='Hz',
                        inputTimeDotNetDateTimeOffsetOffsetHours=-7,
                        inputTimeDotNetDateTimeOffsetTicks=638853284961234567)
        stimulus = item('stimulus-'+str(n), h5path=f'/experiment/{number}/cell/{n}/epoch/stimuli/LED')
        epoch['responses']['Amp1']=response;epoch['stimuli']['LED']=stimulus
        block['epochs']=[epoch];group['epoch_blocks']=[block];cell['epoch_groups']=[group]
        preparation['cells'].append(cell)
    return source


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--strict',action='store_true',help='Return failure for any incorrect scientific outcome, runtime error, or changed helper')
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new output file; historical evidence is preserved')
    report={'native':True,'database_scope':'fresh temporary native project only','cases':[],
            'strict':args.strict,'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'helper_sha256_before':hashlib.sha256(Path(validator.__file__).read_bytes()).hexdigest()}
    project=None;dj=None;clean=False
    temporary=Path(tempfile.mkdtemp(prefix='rieke-catalog-identity-native-'))
    try:
        project=Path(create_project(temporary/'projects','Disposable identity probe')['path'])
        ensure_native_database(project)
        report['mysql_binary']=str(native_binary())
        dj=connect({'kind':'native-project'},project_dir=project)
        from retinanalysis.config import schema as catalog
        from retinanalysis.utils import database_pop as population
        report['pinned_source_sha256']={module.__name__:hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                                       for module in (catalog,population)}
        population.configure_tables(catalog)
        connection=catalog.schema.connection
        report['mysql_version']=connection.query('SELECT VERSION()').fetchone()[0]
        report['timestamp_storage_probes']=[]
        original_mode=connection.query('SELECT @@SESSION.sql_mode').fetchone()[0]
        report['default_sql_mode']=original_mode
        connection.query('CREATE TEMPORARY TABLE `schema`.`catalog_timestamp_probe` (stamp DATETIME(0))')
        try:
            modes=[('server_default',original_mode),('explicit_rounding',','.join(mode for mode in original_mode.split(',') if mode!='TIME_TRUNCATE_FRACTIONAL')),
                   ('truncate_fractional',','.join(sorted(set(original_mode.split(','))|{'TIME_TRUNCATE_FRACTIONAL'})))]
            for mode_name,mode in modes:
                connection.query('SET SESSION sql_mode=%s',(mode,))
                for stamp in ('2026-06-11 12:34:56.123456','2026-06-11 12:34:56.499999',
                              '2026-06-11 12:34:56.500000','2026-06-11 12:34:56.654321',
                              '2026-06-11 23:59:59.999999'):
                    connection.query('DELETE FROM `schema`.`catalog_timestamp_probe`')
                    connection.query('INSERT INTO `schema`.`catalog_timestamp_probe` VALUES (%s)',(dt.datetime.fromisoformat(stamp),))
                    stored=connection.query('SELECT stamp FROM `schema`.`catalog_timestamp_probe`').fetchone()[0]
                    report['timestamp_storage_probes'].append({'mode':mode_name,'input':stamp,'stored':str(stored)})
        finally:
            connection.query('SET SESSION sql_mode=%s',(original_mode,))
            connection.query('DROP TEMPORARY TABLE `schema`.`catalog_timestamp_probe`')
        sources=[fixture(n) for n in (1,2)]
        # The pinned ExperimentObj omits optional scalar keys when unrecorded;
        # population should leave these nullable columns NULL, not invent data.
        sources[1].pop('rig')
        sources[1]['animals'][0]['preparations'][0]['cells'][1]['type']=None
        first,second=[cell['epoch_groups'][0] for cell in sources[1]['animals'][0]['preparations'][0]['cells']]
        moved=second['epoch_blocks'].pop();moved['protocolID']='other.Protocol'
        first['epoch_blocks'].append(moved)  # Actual population: one mixed group, one empty group.
        with connection.transaction:
            for n,source in enumerate(sources):
                population.append_experiment(str(temporary/'metadata.json'),str(temporary/f'rig-{n}.h5'),
                    str(temporary/'tags.json'),source,'disposable-audit',{})
        ids=[(catalog.Experiment & {'h5_uuid':source['uuid']}).fetch1('id') for source in sources]
        report['experiment_ids']=[int(value) for value in ids]
        def validate(name,source,identity):
            try:
                counts=validator.validate_catalog_identity(source,catalog,identity)
            except Exception as error:
                result={'name':name,'accepted':False,'error_type':type(error).__name__,'error':str(error)}
            else:result={'name':name,'accepted':True,'counts':counts}
            report['cases'].append(result);print(json.dumps(result),flush=True)
            return result
        for index in range(2):validate('valid_source_'+str(index+1),sources[index],ids[index])
        protocol_names={row['protocol_id']:row['name'] for row in catalog.Protocol.to_dicts()}
        report['group_protocol_controls']=[{'group_uuid':row['h5_uuid'],'protocol':protocol_names[row['protocol_id']]}
                                           for row in catalog.EpochGroup.to_dicts()]
        stream_relation=catalog.Response & (catalog.Epoch & {'experiment_id':ids[0]}).proj(parent_id='id')
        report['response_semijoin_sql']=str(stream_relation.make_sql())
        report['response_semijoin_count']=len(stream_relation)
        report['all_response_count']=len(catalog.Response())
        def objects(source):
            animal=source['animals'][0];preparation=animal['preparations'][0];cell=preparation['cells'][0]
            group=cell['epoch_groups'][0];block=group['epoch_blocks'][0];epoch=block['epochs'][0]
            return {'Animal':animal,'Preparation':preparation,'Cell':cell,'EpochGroup':group,'EpochBlock':block,
                    'Epoch':epoch,'Response':epoch['responses']['Amp1'],'Stimulus':epoch['stimuli']['LED']}
        report['guard_cases']=[]
        tables=['Experiment',*objects(sources[0]),'Protocol']
        def inventory():
            return hashlib.sha256(json.dumps({name:getattr(catalog,name).to_dicts() for name in tables},
                sort_keys=True,default=str).encode()).hexdigest()
        before_guard=inventory()
        for kind in ('distinct_control',*objects(sources[0])):
            incoming=fixture(3)
            if kind!='distinct_control':objects(incoming)[kind]['uuid']=objects(sources[0])[kind]['uuid']
            try:assert_new_catalog_identities(incoming,catalog)
            except Exception as error:
                passed=kind!='distinct_control' and isinstance(error,ValueError) and str(error).startswith(f'Existing {kind} source UUID ')
                result={'kind':kind,'accepted':False,'passed':passed,'error_type':type(error).__name__,'error':str(error)}
            else:result={'kind':kind,'accepted':True,'passed':kind=='distinct_control'}
            report['guard_cases'].append(result)
        report['guard_preserved_all_catalog_rows']=before_guard==inventory()
        group_ids=(catalog.EpochGroup & {'experiment_id':ids[0]}).fetch('id',order_by='id')
        group_rows=(catalog.EpochGroup & {'experiment_id':ids[0]}).to_dicts()
        mutations=[('swapped_cell_parent',catalog.EpochGroup,'parent_id',group_ids[0],group_rows[1]['parent_id']),
                   ('wrong_is_mea',catalog.Experiment,'is_mea',ids[0],1),
                   ('wrong_group_protocol',catalog.EpochGroup,'protocol_id',group_ids[0],
                    (catalog.Protocol & {'name':'no_group_protocol'}).fetch1('protocol_id')),
                   ('wrong_rig_scalar',catalog.Experiment,'rig',ids[0],'WRONG RIG'),
                   ('wrong_epoch_time',catalog.Epoch,'start_time',(catalog.Epoch & {'experiment_id':ids[0]}).fetch('id')[0],'1999-01-01 00:00:00'),
                   ('wrong_response_offset',catalog.Response,'offset_ticks',stream_relation.fetch('id')[0],'123'),
                   ('wrong_response_rate',catalog.Response,'sample_rate',stream_relation.fetch('id')[0],'20000')]
        for name,table,column,number,value in mutations:
            with connection.transaction:
                original=(table & {'id':number}).fetch1(column)
                connection.query(f'UPDATE {table.full_table_name} SET `{column}`=%s WHERE id=%s',(value,int(number)))
                validate(name,sources[0],ids[0])
                connection.query(f'UPDATE {table.full_table_name} SET `{column}`=%s WHERE id=%s',(original,int(number)))
        with connection.transaction:
            connection.query(f'UPDATE {catalog.Experiment.full_table_name} SET rig=%s WHERE id=%s',('UNRECORDED RIG',int(ids[1])))
            validate('invented_missing_rig',sources[1],ids[1])
            connection.query(f'UPDATE {catalog.Experiment.full_table_name} SET rig=NULL WHERE id=%s',(int(ids[1]),))
        report['stored_time']=str((catalog.Epoch & {'experiment_id':ids[0]}).fetch('start_time')[0])
        report['stored_response_offsets']=stream_relation.fetch1('offset_hours','offset_ticks') if len(stream_relation)==1 else [str(v) for v in stream_relation.fetch('offset_ticks')]
        report['valid_after_mutations']=validate('restored_source',sources[0],ids[0])['accepted']
    except Exception as error:
        report['runtime_error']={'type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc()}
        print(traceback.format_exc(),flush=True)
    finally:
        if dj is not None:
            try:dj.conn().close()
            except Exception:pass
        if project is not None:
            try:
                clean=stop_native_database(project)
                report['clean_native_shutdown']=clean
            except Exception as error:report['shutdown_error']=str(error)
        if clean:
            import shutil
            shutil.rmtree(temporary)
            report['temporary_project_removed']=True
        else:
            report['temporary_project_preserved']=str(temporary)
        report['helper_sha256_after']=hashlib.sha256(Path(validator.__file__).read_bytes()).hexdigest()
        report['helper_changed_during_run']=report['helper_sha256_before']!=report['helper_sha256_after']
        controls={'valid_source_1','valid_source_2','restored_source'}
        report['incorrect_outcomes']=[case['name'] for case in report['cases']
            if (not case['accepted'] if case['name'] in controls else
                case['accepted'] or case.get('error_type')!='CatalogIdentityConflict')]
        report['scientific_contract_passed']=(len(report['cases'])==11 and not report['incorrect_outcomes']
            and len(report.get('guard_cases',[]))==9 and all(case['passed'] for case in report['guard_cases'])
            and report.get('guard_preserved_all_catalog_rows') is True
            and not report.get('runtime_error') and clean and not report['helper_changed_during_run'])
        report['release_ready']=False
        args.output.write_text(json.dumps(report,indent=2,default=str)+'\n')
    return 1 if report.get('runtime_error') or not clean or (args.strict and not report['scientific_contract_passed']) else 0


if __name__=='__main__':raise SystemExit(main())
