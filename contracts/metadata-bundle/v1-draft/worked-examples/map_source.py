"""Synthetic tutorial adapter only. Never opens raw assets or writes databases."""
import argparse, copy, hashlib, json, pathlib, sys, uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import validate_bundle
from mapping_coverage import inventory
SCHEMA=json.loads((ROOT/'disco-metadata-bundle.schema.json').read_text())

def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
def leaves(value,path='$'):
    if isinstance(value,dict) and value:
        for k,v in value.items():yield from leaves(v,path+'/'+str(k).replace('~','~0').replace('/','~1'))
    elif isinstance(value,list) and value:
        for i,v in enumerate(value):yield from leaves(v,path+'/'+str(i))
    else:yield path,value

def map_source(s,raw_claim=False):
    report={'format':'disco-adapter-mapping-report','version':'1.0.0-draft.1','status':'synthetic tutorial mapping','source_description':'source.json synthetic nested parser-shaped metadata, NOT an actual parser export','adapter_revision':'worked-1','source_schema_revision':s.get('format'),'parser_revision':'not_used','authority_namespace_uuid':s.get('authority_namespace_uuid'),'authority_owner':'Synthetic Example Lab (tutorial only)','dataset_native_key':s.get('dataset_key'),'dataset_revision':s.get('revision'),'id_ledger_path':'identity-ledger.json','entity_mappings':[],'field_mappings':[],'effective_parameter_precedence':'block defaults then epoch override; original input retained verbatim in demo:source_snapshot','timestamps':[{'source_path':'experiment.start_time','timezone_evidence':'unknown','mapping':'source.start_time status unknown, original retained'}],'raw_references':{'status':'unverified_claims' if raw_claim else 'absent','waveforms_embedded':False},'tag_mapping':{'authorship_status':'claimed','deletions_requested':False},'unsupported_fields':[],'conflicts':[],'assumptions':['Only source temperature null is explicitly defined as not_recorded in this synthetic source. Never infer this for another lab.'],'blockers':[]}
    def keys(obj,allowed,path):
        for k in sorted(set(obj)-set(allowed)):report['blockers'].append({'source_path':path+'/'+k,'reason':'Unsupported source key; add a reviewed explicit mapping, never silently drop.'})
    keys(s,['format','notice','authority_namespace_uuid','dataset_key','revision','experiment','parameter_definitions','reviewer'],'$')
    keys(s['experiment'],['key','label','start_time','cells'],'$/experiment')
    keys(s['reviewer'],['profile_uuid','author_name'],'$/reviewer')
    if s['format']!='synthetic-parser-shaped-v1':report['blockers'].append({'source_path':'$/format','reason':'This teaching mapper only supports its supplied synthetic input format.'})
    ns=uuid.UUID(s['authority_namespace_uuid']);ledger=[]
    def identity(kind,key,native=None):
        ident={'mode':'native_uuid' if native else 'uuid5','native_key':native or key}
        name=json.dumps(['disco-id-v1',kind,key],ensure_ascii=False,separators=(',',':'))
        value=native or str(uuid.uuid5(ns,name))
        ledger.append({'kind':kind,'source_key':key,'public_uuid':value,'identity':ident,'uuid5_name':None if native else name})
        return {'id':value,'identity':ident}
    source=s['experiment'];sid=identity('source',source['key']);did=identity('dataset',s['dataset_key'])
    b={'format':'disco-metadata-bundle','schema_version':'1.0.0-draft.1','bundle_id':'e27a860e-d78c-490c-bbbf-5d67c307ca81','exported_at':'2026-10-03T05:00:00Z','authority':{'namespace_uuid':str(ns),'name':'Synthetic Example Lab'},'producer':{'name':'WorkedTutorialAdapter','version':'1.0','adapter_revision':'worked-1'},'dataset':{**did,'revision':s['revision'],'membership_scope':'subset','label':'Synthetic worked collection'},'sources':[{**sid,'metadata_revision':s['revision'],'label':source['label'],'start_time':{'status':'unknown','original':source['start_time']}}],'protocols':[],'field_definitions':[],'cells':[],'ancestry':[],'epochs':[],'streams':[],'annotations':{'profiles':[s['reviewer']],'entries':[]},'extensions':{'demo:source_snapshot':copy.deepcopy(s),'demo:notice':'Synthetic tutorial. Snapshot preserves original input but does not establish universal queryability or raw verification.'}}
    defs=s['parameter_definitions']
    for name,d in defs.items():
        keys(d,['id','type','unit','null_status'],'$/parameter_definitions/'+name)
        b['field_definitions'].append({'id':d['id'],'label':name,'type':d['type'],'unit':d['unit'],'scope':'epoch'})
        report['field_mappings'].append({'source_path':'epochBlocks[].parameters.'+name+' or epochs[].parameters.'+name,'public_path':'epochs[].fields.'+d['id'],'public_field_id':d['id'],'declared_type':d['type'],'scope':'epoch','unit':d['unit'],'unit_evidence':'explicit synthetic parameter_definitions','missingness_rule':'omission makes no assertion; null uses explicit null_status only','transform':'block default then epoch override; no coercion'})
    protocols={}
    asset=None
    if raw_claim:
        asset=identity('raw_asset',source['key']+'/raw:synthetic-claim')
        b['sources'][0]['raw_assets']=[{**asset,'sha256':'a'*64,'size_bytes':12345,'format':'hdf5','locator':{'kind':'project_local','relative_path':'raw/synthetic-claim.h5'}}]
    def tags(obj,kind,target):
        if obj['tags']:b['annotations']['entries'].append({'target_kind':kind,'target_id':target,'profile_uuid':s['reviewer']['profile_uuid'],'tags':obj['tags']})
    def params(p,path):
        result={}
        for name,value in p.items():
            d=defs.get(name)
            if d is None:report['blockers'].append({'source_path':path+'/'+name,'reason':'No declared type/unit/mapping'});continue
            if value is None:
                if 'null_status' not in d:report['blockers'].append({'source_path':path+'/'+name,'reason':'Ambiguous null requires explicit source evidence'});continue
                result[d['id']]={'status':d['null_status']}
            else:result[d['id']]={'status':'present','value':value}
        return result
    for ci,c in enumerate(source['cells']):
        cp='$/experiment/cells/'+str(ci);keys(c,['key','uuid','label','tags','epochGroups'],cp)
        ck=source['key']+'/'+c['key'];cell=identity('cell',ck,c.get('uuid'))
        b['cells'].append({**cell,'source_id':sid['id'],'label':c['label']});tags(c,'cell',cell['id'])
        for gi,g in enumerate(c['epochGroups']):
            gp=cp+'/epochGroups/'+str(gi);keys(g,['key','epochBlocks'],gp)
            gk=ck+'/'+g['key'];group=identity('group',gk);b['ancestry'].append({**group,'kind':'group','source_id':sid['id'],'parent_id':cell['id']})
            for bi,block in enumerate(g['epochBlocks']):
                bp=gp+'/epochBlocks/'+str(bi);keys(block,['key','protocolID','parameters','epochs'],bp)
                proto=block['protocolID']
                if proto not in protocols:
                    protocols[proto]=identity('protocol',proto);b['protocols'].append({**protocols[proto],'name':proto})
                bk=gk+'/'+block['key'];blk=identity('block',bk);b['ancestry'].append({**blk,'kind':'block','source_id':sid['id'],'parent_id':group['id'],'protocol_id':protocols[proto]['id']})
                params(block['parameters'],bp+'/parameters')
                for ei,e in enumerate(block['epochs']):
                    ep=bp+'/epochs/'+str(ei);keys(e,['key','uuid','parameters','tags','responses'],ep)
                    ek=bk+'/'+e['key'];epoch=identity('epoch',ek,e.get('uuid'));params(e['parameters'],ep+'/parameters')
                    effective={**block['parameters'],**e['parameters']}
                    b['epochs'].append({**epoch,'source_id':sid['id'],'cell_id':cell['id'],'group_id':group['id'],'block_id':blk['id'],'protocol_id':protocols[proto]['id'],'fields':params(effective,ep+'/effective_parameters')});tags(e,'epoch',epoch['id'])
                    for device,r in e['responses'].items():
                        keys(r,['sampleRate','sampleRateUnits','units','sampleCount','h5path'],ep+'/responses/'+device)
                        if r['sampleRateUnits']!='Hz':report['blockers'].append({'source_path':ep+'/responses/'+device+'/sampleRateUnits','reason':'Only explicit Hz accepted; no inferred conversion'})
                        stream={**identity('stream',ek+'/response:'+device),'epoch_id':epoch['id'],'kind':'response','device':device,'trace_state':'referenced' if asset else 'absent','sample_rate_hz':r['sampleRate'],'sample_count':r['sampleCount'],'unit':r['units']}
                        if asset:stream['data_reference']={'asset_id':asset['id'],'object_path':r['h5path']}
                        b['streams'].append(stream)
    report['entity_mappings']=ledger
    report['coverage_version']='1.0.0-draft.1'
    report['losslessness_inventory']=inventory(s,b,raw_claim=raw_claim)
    report['all_field_receiver_readiness']='blocked_unimplemented_query_paths'
    report['coverage_test_status']='not_run_in_mapping_operation'
    report['counts']={k:len(b[k]) for k in ('sources','cells','epochs','streams')}
    validation=validate_bundle.validate(b,SCHEMA)
    if not validation['valid']:report['blockers'].extend({'source_path':e['path'],'reason':e['message'],'code':e['code']} for e in validation['errors'])
    report['status']='blocked' if report['blockers'] else 'mapped_valid_draft'
    return (None if report['blockers'] else b),report,ledger

def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=pathlib.Path);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--raw-claim',action='store_true');p.add_argument('--diagnostics',action='store_true');a=p.parse_args()
    # Parse bounded original bytes before creating output or losing duplicate keys.
    try:
        with a.source.open('rb') as source_file:
            source=validate_bundle.loads(source_file.read(validate_bundle.MAX_BYTES+1))
    except (OSError, ValueError) as error:
        if a.diagnostics:
            from validation_diagnostics import failure
            print(encode(failure(error)))
        else:print('BLOCKED invalid source JSON: '+str(error)+'; no bundle written',file=sys.stderr)
        return 1
    # Require a fresh output directory so a blocked run cannot leave a stale bundle.
    a.out.mkdir(parents=True,exist_ok=False)
    b,r,ledger=map_source(source,a.raw_claim)
    (a.out/'mapping-report.json').write_text(encode(r));(a.out/'identity-ledger.json').write_text(encode(ledger))
    if b is None:print('BLOCKED: inspect mapping-report.json; no bundle written');return 1
    (a.out/'bundle.json').write_text(encode(b));(a.out/'validation-report.json').write_text(encode(validate_bundle.validate(b,SCHEMA)))
    print('VALID DRAFT: 3 cells, 4 epochs, 2 protocols; no production import/raw verification');return 0
if __name__=='__main__':raise SystemExit(main())
