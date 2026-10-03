"""Regenerate synthetic worked-example files. Offline only; run outside quiet windows."""
import copy,json,pathlib
from map_source import map_source,encode,validate_bundle,SCHEMA
ROOT=pathlib.Path(__file__).parent

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(encode(data))

def build():
    source=json.loads((ROOT/'source.json').read_text())
    for directory,s,raw in [('expected',source,False),('expected-raw-claim',source,True),('expected-revision-2',{**source,'revision':'synthetic-r2'},False)]:
        b,r,ledger=map_source(s,raw)
        if b is None:raise ValueError(r['blockers'])
        for name,value in [('bundle.json',b),('mapping-report.json',r),('identity-ledger.json',ledger),('validation-report.json',validate_bundle.validate(b,SCHEMA))]:write(ROOT/directory/name,value)
    revised=copy.deepcopy(source);revised['revision']='synthetic-r2';revised['experiment']['cells'][0]['label']='Renamed Cell1'
    write(ROOT/'source-revision-2.json',revised)
    b,r,ledger=map_source(revised)
    for name,value in [('bundle.json',b),('mapping-report.json',r),('identity-ledger.json',ledger),('validation-report.json',validate_bundle.validate(b,SCHEMA))]:write(ROOT/'expected-revision-2'/name,value)
    base,_,_=map_source(source)
    recipes={
      'dangling-uuid':('broken_link','Restore epochs[0].cell_id to cells[0].id; never invent a replacement identity.'),
      'duplicate-identity':('duplicate_id','Remove accidental duplicate row; distinct real records need distinct stable source keys, never random UUID patches.'),
      'bad-unit':('unit','Restore explicit pA from source evidence; do not infer or silently convert.'),
      'wrong-type':('field_type','Restore numeric 0 rather than string "0".'),
      'present-null':('field_type','Restore temperature status not_recorded with no value, based on explicit source null policy.')}
    cases=[]
    for name,(code,fix) in recipes.items():
        bad=copy.deepcopy(base)
        if name=='dangling-uuid':bad['epochs'][0]['cell_id']='00000000-0000-4000-8000-000000000001'
        if name=='duplicate-identity':bad['epochs'].append(copy.deepcopy(bad['epochs'][0]))
        if name=='bad-unit':bad['field_definitions'][0]['unit']=' pA '
        if name=='wrong-type':bad['epochs'][0]['fields']['demo:amplitude']['value']='0'
        if name=='present-null':bad['epochs'][0]['fields']['demo:temperature']={'status':'present','value':None}
        result=validate_bundle.validate(bad,SCHEMA)
        if result['valid'] or code not in {e['code'] for e in result['errors']}:raise AssertionError((name,result))
        write(ROOT/'bad'/f'{name}.json',bad);write(ROOT/'bad'/f'{name}.expected.json',result)
        cases.append({'file':f'bad/{name}.json','expected_code':code,'repair':fix,'repaired_file':'expected/bundle.json'})
    write(ROOT/'bad/cases.json',cases)
    blocked=copy.deepcopy(source);blocked['experiment']['cells'][0]['epochGroups'][0]['epochBlocks'][0]['epochs'][0]['parameters']['unmappedScientificField']=123
    write(ROOT/'source-blocked.json',blocked)
    bundle,report,ledger=map_source(blocked)
    assert bundle is None
    write(ROOT/'expected-blocked/mapping-report.json',report)
    print('Generated synthetic collection, revision/raw variants, five failing bundles and blocked source report.')
if __name__=='__main__':build()
