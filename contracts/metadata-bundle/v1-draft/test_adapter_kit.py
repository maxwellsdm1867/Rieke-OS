"""Regression checks for this draft handoff, using synthetic data only."""
import copy, json, pathlib, subprocess, sys, unittest
import validate_bundle as v
ROOT=pathlib.Path(__file__).parent
SCHEMA=json.loads((ROOT/'disco-metadata-bundle.schema.json').read_text())
BASE=json.loads((ROOT/'examples/metadata-only.json').read_text())
RAW=json.loads((ROOT/'examples/with-raw-reference.json').read_text())
class ContractTests(unittest.TestCase):
    def result(self,data):return v.validate(data,SCHEMA)
    def reject(self,data,code=None):
        report=self.result(data);self.assertFalse(report['valid'],report)
        if code:self.assertIn(code,{x['code'] for x in report['errors']},report)
    def test_current_database_declared_links(self):
        d=json.loads((ROOT/'current-database-schema.json').read_text());tables={(t['schema'],t['table']):t for t in d['tables']}
        self.assertEqual(tables['recording_workspace','workbench_decision']['primary_key'],['project_uuid','protocol_uuid','candidate_revision_uuid','actor','epoch_uuid'])
        self.assertIn({'target_table':'schema.preparation','local_columns':['parent_id'],'target_columns':['id'],'nullable':False,'in_primary_key':False},tables['schema','cell']['resolved_foreign_keys'])
        self.assertFalse(tables['recording_workspace','source']['resolved_foreign_keys'])
        self.assertFalse(tables['recording_workspace','shared_annotation']['resolved_foreign_keys'])
    def test_valid_examples(self):
        for name in ('metadata-only','with-raw-reference'):
            with self.subTest(name=name):
                report=self.result(json.loads((ROOT/'examples'/f'{name}.json').read_text()));self.assertTrue(report['valid'],report);self.assertEqual(report['raw_assets_verified'],0)
    def test_invalid_fixtures(self):
        for name,code in json.loads((ROOT/'invalid/expected-errors.json').read_text()).items():
            with self.subTest(name=name):self.reject(json.loads((ROOT/'invalid'/f'{name}.json').read_text()),code)
    def test_unknown_structure(self):
        b=copy.deepcopy(BASE);b['sql']='DROP TABLE anything';self.reject(b,'schema')
    def test_schema_required_fields(self):
        for key in SCHEMA['required']:
            with self.subTest(key=key):
                b=copy.deepcopy(BASE);del b[key];self.reject(b)
    def test_cross_source_ownership(self):
        b=copy.deepcopy(BASE);b['epochs'][0]['source_id']='00000000-0000-4000-8000-000000000001';self.reject(b,'ownership')
    def test_unknown_raw_asset(self):
        b=copy.deepcopy(RAW);b['streams'][0]['data_reference']['asset_id']='00000000-0000-4000-8000-000000000001';self.reject(b,'broken_link')
    def test_managed_key_checksum(self):
        b=copy.deepcopy(RAW);b['sources'][0]['raw_assets'][0]['locator']['asset_key']='b'*64;self.reject(b,'asset')
    def test_relative_traversal(self):
        b=copy.deepcopy(RAW);b['sources'][0]['raw_assets'][0]['locator']={'kind':'external','root_uuid':b['authority']['namespace_uuid'],'relative_path':'../private.h5'};self.reject(b,'schema')
    def test_metadata_only_cannot_carry_reference(self):
        b=copy.deepcopy(BASE);b['streams'][0]['data_reference']=RAW['streams'][0]['data_reference'];self.reject(b,'schema')
    def test_generator_response_rejected(self):
        b=copy.deepcopy(BASE);b['streams'][0].update(trace_state='generator_only',generator={'name':'example','revision':'v1'});self.reject(b,'schema')
    def test_generator_seed_exactness(self):
        for seed,valid in [(9007199254740991,True),(-9007199254740991,True),(9007199254740992,False),(-9007199254740992,False),(9007199254740993,False),('9007199254740993',True),('-9007199254740993',True),('01',False),('1.0',False),(True,False)]:
            with self.subTest(seed=seed):
                b=copy.deepcopy(BASE);b['streams'][0].update(kind='stimulus',trace_state='generator_only',generator={'name':'example','revision':'v1','seed':seed})
                if valid:
                    restored=json.loads(json.dumps(b));self.assertTrue(self.result(restored)['valid'])
                    restored_seed=restored['streams'][0]['generator']['seed']
                    self.assertEqual(restored_seed,seed);self.assertIs(type(restored_seed),type(seed))
                    if isinstance(seed,str):self.assertEqual(str(int(restored_seed)),seed)
                else:self.reject(b,'schema')
    def test_valid_generator_stimulus(self):
        b=copy.deepcopy(BASE);b['streams'][0].update(kind='stimulus',trace_state='generator_only',generator={'name':'example','revision':'v1'});self.assertTrue(self.result(b)['valid'])
    def test_wrong_author_or_target_kind(self):
        for prop,value in [('profile_uuid','00000000-0000-4000-8000-000000000001'),('target_kind','epoch')]:
            with self.subTest(prop=prop):
                b=copy.deepcopy(BASE);b['annotations']['entries'][0][prop]=value;self.reject(b,'broken_link')
    def test_duplicate_tag_author_target(self):
        b=copy.deepcopy(BASE);b['annotations']['entries'].append(copy.deepcopy(b['annotations']['entries'][0]));self.reject(b,'duplicate_annotation')
        b=copy.deepcopy(BASE);b['annotations']['entries'][0]['tags']=['candidate','candidate'];self.reject(b,'duplicate_tag')
    def test_null_present_and_zero_not_confused(self):
        b=copy.deepcopy(BASE);b['epochs'][0]['fields']['demo:step_amplitude']['value']=None;self.reject(b,'field_type')
        b['epochs'][0]['fields']['demo:step_amplitude']['value']=0;self.assertTrue(self.result(b)['valid'])
    def test_boolean_not_number(self):
        b=copy.deepcopy(BASE);b['epochs'][0]['fields']['demo:step_amplitude']['value']=True;self.reject(b,'field_type')
    def test_wrong_field_scope(self):
        b=copy.deepcopy(BASE);b['field_definitions'][0]['scope']='cell';self.reject(b,'field_scope')
    def test_missing_unit_declaration(self):
        b=copy.deepcopy(BASE);del b['field_definitions'][0]['unit'];self.reject(b,'schema')
    def test_unknown_unit_sentinel(self):
        b=copy.deepcopy(BASE);b['field_definitions'][0]['unit']='';self.reject(b,'unit')
    def test_decimal_exact_lexeme(self):
        b=copy.deepcopy(BASE);b['field_definitions'][0]['type']='decimal';b['epochs'][0]['fields']['demo:step_amplitude']['value']='0.123456789012345678901';self.assertTrue(self.result(b)['valid'])
    def test_timezone_and_duration(self):
        b=copy.deepcopy(BASE);b['epochs'][0].update(start_time={'status':'known','instant':'2026-10-03T12:00:00'},end_time={'status':'known','instant':'2026-10-03T12:00:01Z'});self.reject(b,'schema')
        b['epochs'][0]['start_time']['instant']='2026-10-03T12:00:00Z';self.reject(b,'time')
        b['epochs'][0]['duration_seconds']=1;self.assertTrue(self.result(b)['valid'])
        b['epochs'][0]['start_time']['timezone']='America/Los_Angeles';self.reject(b,'timezone')
    def test_native_uuid_preserved(self):
        b=copy.deepcopy(BASE);b['cells'][0]['identity']={'mode':'native_uuid','native_key':b['cells'][0]['id']};self.assertTrue(self.result(b)['valid'])
    def test_invalid_json_input_limits(self):
        bad=[b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}',b'{"a":1e999}',b'[\xff]',b'"\\ud800"',b'['*33+b'0'+b']'*33,b' '* (v.MAX_BYTES+1)]
        for i,raw in enumerate(bad):
            with self.subTest(case=i):
                with self.assertRaises((v.InvalidInput,UnicodeDecodeError,ValueError)):v.loads(raw)
    def test_cli_exit_status(self):
        for file,code in [('examples/metadata-only.json',0),('invalid/orphan-epoch.json',1)]:
            p=subprocess.run([sys.executable,str(ROOT/'validate_bundle.py'),str(ROOT/file)],capture_output=True,text=True);self.assertEqual(p.returncode,code);json.loads(p.stdout)
if __name__=='__main__':unittest.main(verbosity=2)
