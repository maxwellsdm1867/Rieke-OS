"""Offline regression tests; run only in an authorized validation window."""
import copy
import importlib.util
import json
import pathlib
import unittest
import validate_bundle as validator
import validation_diagnostics as diagnostics
ROOT=pathlib.Path(__file__).parent
SCHEMA=json.loads((ROOT/'disco-metadata-bundle.schema.json').read_text())

class DiagnosticsTests(unittest.TestCase):
    def test_full_fixture_parity(self):
        files=list((ROOT/'examples').glob('*.json'))
        files += [p for p in (ROOT/'invalid').glob('*.json') if p.name!='expected-errors.json']
        files += list((ROOT/'worked-examples').glob('expected*/bundle.json'))
        files += [p for p in (ROOT/'worked-examples/bad').glob('*.json') if p.name!='cases.json' and not p.name.endswith('.expected.json')]
        self.assertGreaterEqual(len(files),19)
        for path in sorted(files):
            with self.subTest(path=path.name):
                raw=path.read_bytes();old=validator.validate(validator.loads(raw),SCHEMA)
                new=diagnostics.validate_bytes(raw,SCHEMA)
                self.assertEqual(old,new['legacy_report'])
                self.assertEqual(len(old['errors']),len(new['diagnostics']))
                self.assertEqual(new['stages']['database']['status'],'unsupported')

    def test_escaped_instance_and_schema_tokens(self):
        schema={'type':'object','properties':{'a/~':{'type':'integer'}},'additionalProperties':False}
        locations={};errors=validator.check_schema({'a/~':'bad'},schema,schema,_locations=locations)
        self.assertEqual(errors[0]['path'],'$/a/~')
        self.assertEqual(locations[id(errors[0])]['instance_pointer'],'/a~1~0')
        self.assertEqual(locations[id(errors[0])]['schema_pointer'],'/properties/a~1~0/type')
        self.assertEqual(validator.pointer(('','/~')), '//~1~0')

    def test_root_required_and_branches(self):
        for schema,instance,expected in [({'required':['missing']},{},'/required'),({'oneOf':[{'type':'string'},{'type':'integer'}]},False,'/oneOf')]:
            locations={};errors=validator.check_schema(instance,schema,schema,_locations=locations)
            self.assertEqual(len(errors),1)
            self.assertEqual(locations[id(errors[0])]['instance_pointer'],'')
            self.assertEqual(locations[id(errors[0])]['schema_pointer'],expected)

    def test_parse_and_capability_states(self):
        for raw in (b'{"a":1,"a":2}',b'NaN',b'1e999',b'{'):
            result=diagnostics.validate_bytes(raw,SCHEMA)
            self.assertFalse(result['legacy_report']['valid'])
            self.assertEqual(result['stages']['parsed']['status'],'failed')
            self.assertIsNone(result['diagnostics'][0]['instance_pointer'])
        result=diagnostics.validate_bytes(b'{}',{'unevaluatedProperties':False})
        self.assertEqual(result['stages']['structural']['status'],'unsupported')
        self.assertEqual(result['diagnostics'][0]['code'],'validator_capability')

    def test_schema_short_circuits_semantics(self):
        result=diagnostics.validate_bytes(b'{}',SCHEMA)
        self.assertEqual(result['stages']['structural']['status'],'failed')
        self.assertEqual(result['stages']['semantic']['status'],'not_run')

    def test_compatibility_both_directions(self):
        old={'type':'object','properties':{'id':{'type':'string'}},'required':['id'],'additionalProperties':False}
        new=copy.deepcopy(old);new['properties']['optional_note']={'type':'string'}
        self.assertFalse(validator.check_schema({'id':'x'},new,new)) # old writer -> new reader
        self.assertTrue(validator.check_schema({'id':'x','optional_note':'new'},old,old)) # new writer -> old reader
        self.assertFalse(validator.check_schema({'id':'x'},old,old)) # new writer omits feature -> old reader

if __name__=='__main__':unittest.main()
