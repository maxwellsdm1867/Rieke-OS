"""Synthetic mapping and pedagogical example regression tests. No DB/raw reads."""
import copy,json,pathlib,subprocess,sys,tempfile,unittest,uuid
from map_source import map_source,encode,validate_bundle,SCHEMA,leaves
ROOT=pathlib.Path(__file__).parent
class WorkedExamples(unittest.TestCase):
    def setUp(self):self.source=json.loads((ROOT/'source.json').read_text())
    def test_complete_collection(self):
        b,r,ledger=map_source(self.source)
        self.assertTrue(validate_bundle.validate(b,SCHEMA)['valid'])
        self.assertEqual([len(b[k]) for k in ('cells','epochs','protocols','streams')],[3,4,2,1])
        self.assertEqual(b,json.loads((ROOT/'expected/bundle.json').read_text()))
        self.assertEqual(b['extensions']['demo:source_snapshot'],self.source)
        self.assertEqual({p for p,v in leaves(self.source)},{i['source_path'] for i in r['losslessness_inventory']})
        self.assertNotIn(b['cells'][2]['id'],{e['cell_id'] for e in b['epochs']})
    def test_uuid4_preserved_uuid5_recomputed_and_stable(self):
        b,r,ledger=map_source(self.source);b2,_,again=map_source(copy.deepcopy(self.source))
        self.assertEqual(ledger,again);self.assertEqual(b,b2)
        self.assertEqual(b['cells'][0]['id'],'7f4e8e7b-3a2d-4c91-8f12-0e9c28a40351')
        for row in ledger:
            if row['identity']['mode']=='uuid5':self.assertEqual(row['public_uuid'],str(uuid.uuid5(uuid.UUID(self.source['authority_namespace_uuid']),row['uuid5_name'])))
    def test_revision_and_labels_do_not_change_identity_or_frozen_members(self):
        a,_,_=map_source(self.source);s=copy.deepcopy(self.source);s['revision']='synthetic-r2';s['experiment']['cells'][0]['label']='Renamed'
        b,_,_=map_source(s)
        for k in ('sources','cells','epochs','protocols','streams','ancestry'):self.assertEqual([x['id'] for x in a[k]],[x['id'] for x in b[k]])
        frozen=json.loads((ROOT/'frozen-selection.demo.json').read_text());before=copy.deepcopy(frozen)
        self.assertEqual(len(frozen['epoch_ids']),len(set(frozen['epoch_ids'])))
        self.assertTrue(set(frozen['epoch_ids']) <= {e['id'] for e in a['epochs']})
        self.assertEqual(frozen,before);self.assertEqual(frozen['dataset_revision'],'synthetic-r1')
    def test_effective_values_missingness_precision(self):
        b,_,_=map_source(self.source);e=b['epochs']
        self.assertEqual(e[0]['fields']['demo:amplitude']['value'],0)
        self.assertIs(e[0]['fields']['demo:enabled']['value'],False)
        self.assertEqual(e[0]['fields']['demo:temperature'],{'status':'not_recorded'})
        self.assertEqual(e[1]['fields']['demo:amplitude']['value'],50)
        self.assertNotIn('demo:seed',e[0]['fields'])
        self.assertEqual(e[2]['fields']['demo:seed']['value'],'9007199254740993')
    def test_claim_does_not_verify_or_change_scientific_ids(self):
        a,_,_=map_source(self.source);b,_,_=map_source(self.source,True)
        self.assertEqual([x['id'] for x in a['epochs']],[x['id'] for x in b['epochs']])
        result=validate_bundle.validate(b,SCHEMA);self.assertTrue(result['valid']);self.assertEqual(result['raw_assets_verified'],0)
        self.assertEqual(b['streams'][0]['trace_state'],'referenced');self.assertEqual(a['streams'][0]['trace_state'],'absent')
    def test_bad_bundles_and_repaired_bundle(self):
        for case in json.loads((ROOT/'bad/cases.json').read_text()):
            with self.subTest(case=case['file']):
                result=validate_bundle.validate(json.loads((ROOT/case['file']).read_text()),SCHEMA)
                self.assertFalse(result['valid']);self.assertIn(case['expected_code'],{e['code'] for e in result['errors']})
                self.assertTrue(validate_bundle.validate(json.loads((ROOT/case['repaired_file']).read_text()),SCHEMA)['valid'])
    def test_unknown_field_and_ambiguous_null_block(self):
        for mode in ('unknown','null'):
            s=copy.deepcopy(self.source);p=s['experiment']['cells'][0]['epochGroups'][0]['epochBlocks'][0]['epochs'][0]['parameters'];p['mystery' if mode=='unknown' else 'amplitude']=None
            b,r,_=map_source(s);self.assertIsNone(b);self.assertTrue(r['blockers'])
    def test_cli_blocked_no_stale_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d)/'blocked'
            result=subprocess.run([sys.executable,'-B',str(ROOT/'map_source.py'),str(ROOT/'source-blocked.json'),'--out',str(out)],capture_output=True,text=True)
            self.assertEqual(result.returncode,1);self.assertTrue((out/'mapping-report.json').exists());self.assertFalse((out/'bundle.json').exists())
    def test_cli_rejects_duplicate_scientific_keys_and_nonfinite_before_mapping(self):
        original=(ROOT/'source.json').read_text()
        marker='"amplitude": 50'
        self.assertIn(marker,original)
        for value,message in [('"amplitude": 50, "amplitude": 60','duplicate JSON object key'),
                              ('"amplitude": NaN','NaN/Infinity'),
                              ('"amplitude": Infinity','NaN/Infinity'),
                              ('"amplitude": 1e999','nonfinite JSON number')]:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as d:
                source=pathlib.Path(d)/'invalid-source.json';out=pathlib.Path(d)/'output'
                source.write_text(original.replace(marker,value,1))
                result=subprocess.run([sys.executable,'-B',str(ROOT/'map_source.py'),str(source),'--out',str(out)],capture_output=True,text=True)
                self.assertEqual(result.returncode,1)
                self.assertIn(message,result.stderr)
                self.assertFalse((out/'bundle.json').exists())
                self.assertFalse(out.exists(),'Invalid bytes must be rejected before mapping/output creation')
    def test_typed_coverage(self):
        b,r,_=map_source(self.source)
        def resolve(value,pointer):
            for token in pointer.split('/')[1:]:
                token=token.replace('~1','/').replace('~0','~')
                value=value[int(token)] if isinstance(value,list) else value[token]
            return value
        for row in r['losslessness_inventory']:
            original=resolve(self.source,row['source_pointer'])
            self.assertEqual(original,resolve(b,row['retention_pointer']))
            self.assertEqual(row['query_support'],'mapped' if row['target_pointers'] else 'retained_only')
            self.assertEqual(row['query_execution'],'unsupported_receiver')
            for target in row['target_pointers']:resolve(b,target)
        self.assertEqual(r['all_field_receiver_readiness'],'blocked_unimplemented_query_paths')
        note=next(row for row in r['losslessness_inventory'] if row['source_pointer']=='/notice')
        self.assertEqual(note['query_support'],'retained_only')
    def test_authority_and_exact_name_bytes(self):
        a,_,_=map_source(self.source)
        changed=copy.deepcopy(self.source);changed['authority_namespace_uuid']='ed2222e9-6d02-4d22-bdd1-7a3714c59fe2'
        b,_,_=map_source(changed)
        self.assertNotEqual(a['dataset']['id'],b['dataset']['id'])
        self.assertEqual(a['cells'][0]['id'],b['cells'][0]['id']) # native UUID preserved
        identities=[]
        for name in ('café','cafe\u0301',' café','café '):
            changed=copy.deepcopy(self.source);changed['dataset_key']=name
            mapped,_,ledger=map_source(changed)
            row=next(row for row in ledger if row['kind']=='dataset')
            self.assertEqual(row['uuid5_name'],json.dumps(['disco-id-v1','dataset',name],ensure_ascii=False,separators=(',',':')))
            identities.append(mapped['dataset']['id'])
        self.assertEqual(len(set(identities)),4)
    def test_locator_change_preserves_ids(self):
        a,_,_=map_source(self.source,True)
        changed=copy.deepcopy(self.source)
        for cell in changed['experiment']['cells']:
            for group in cell['epochGroups']:
                for block in group['epochBlocks']:
                    for epoch in block['epochs']:
                        for response in epoch['responses'].values():response['h5path']='/moved/response'
        b,_,_=map_source(changed,True)
        for key in ('sources','cells','epochs','streams'):
            self.assertEqual([row['id'] for row in a[key]],[row['id'] for row in b[key]])
        self.assertEqual(validate_bundle.validate(b,SCHEMA)['raw_assets_verified'],0)
    def test_escaped_source_coverage_and_deterministic_blockers(self):
        source=copy.deepcopy(self.source)
        source['z/~']=False;source['a/~']=0
        b,r,_=map_source(source)
        self.assertIsNone(b)
        rows={row['source_pointer']:row for row in r['losslessness_inventory']}
        self.assertEqual(rows['/z~1~0']['observed_type'],'boolean')
        self.assertEqual(rows['/a~1~0']['observed_type'],'integer')
        self.assertEqual(rows['/z~1~0']['retention_pointer'],'/extensions/demo:source_snapshot/z~1~0')
        self.assertEqual([x['source_path'] for x in r['blockers'][:2]],['$/a/~','$/z/~'])
    def test_optional_mapping_parse_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=pathlib.Path(temporary)/'bad.json';out=pathlib.Path(temporary)/'out'
            source.write_bytes(b'{"a":1,"a":2}')
            result=subprocess.run([sys.executable,'-B',str(ROOT/'map_source.py'),str(source),'--out',str(out),'--diagnostics'],capture_output=True,text=True)
            self.assertEqual(result.returncode,1);self.assertFalse(out.exists())
            report=json.loads(result.stdout)
            self.assertEqual(report['stages']['parsed']['status'],'failed')
            self.assertIsNone(report['diagnostics'][0]['instance_pointer'])
if __name__=='__main__':unittest.main(verbosity=2)
