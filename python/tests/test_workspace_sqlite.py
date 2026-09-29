"""Real SQLite queries against isolated frozen packages, never lab databases."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from workspace_sqlite import build_sqlite_export, load_frozen_record, SCHEMA_VERSION
from workspace_recipes import capture_query, prepare_export
if __package__:
    from . import test_workspace_matlab as matlab_tests
else:
    import test_workspace_matlab as matlab_tests


class SQLiteExportTests(unittest.TestCase):
    def setUp(self):
        self.case = matlab_tests.MatlabExportTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        service = self.case.service
        self.service = service
        self.path = Path(self.case.temp.name) / 'handoff.db'
        self.fingerprint()
        self.package = self.package_for(service.ids)

    def fingerprint(self):
        self.service._fingerprints = {key: hashlib.sha256(json.dumps({
            'epoch':self.service.details[key], 'source_sha256':row['source_sha256']},
            sort_keys=True,allow_nan=False).encode()).hexdigest() for key,row in self.service.rows.items()}

    def package_for(self, ids):
        s = self.service
        result = s.query_result(s.protocol_id)
        result['epochs'] = [{'uuid':key,'metadata_hash':value} for key,value in s._fingerprints.items()]
        result['metadata_fingerprint_version'] = 2
        snapshot = capture_query(s.protocols[s.protocol_id]['definition'], result, str(s.project_dir/'catalog.json'))
        recipe = prepare_export(snapshot,ids,destination='wheeler-sqlite',review_policy='include_unreviewed',actor='fixture')
        records = [s.epoch(key) for key in ids]
        for row in records:
            row['curation']['tags'] = ['keep', "quote'); DROP TABLE cells;--"]
        return {'format':'recording-reference-package','version':1,'recipe':recipe,
                'epochs':records,'sources':[{'source_sha256':source['source_sha256'],'source_path':source['source_path']}
                                           for source in s.sources], 'waveforms':'references-only'}

    def test_sql_joins_identity_units_tags_queries_and_lazy_pointers_roundtrip(self):
        before = copy.deepcopy(self.package)
        with patch('h5py.File',side_effect=AssertionError('No waveform reads during metadata export')):
            result = build_sqlite_export(self.package,self.path)
        self.assertEqual(result['counts']['epochs'],2)
        self.assertEqual(result['counts']['streams'],4)
        self.assertIn('not a drop-in',result['compatibility'])
        with sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual({row[0] for row in db.execute('SELECT epoch_uuid FROM epoch_overview')},set(self.service.ids))
            pointers = db.execute("SELECT st.sample_rate,st.units,s.source_path FROM streams st JOIN epochs e USING(epoch_uuid) JOIN sources s USING(source_sha256) WHERE st.kind='responses'").fetchall()
            self.assertEqual(pointers,[(10000,'pA',self.service.sources[0]['source_path'])]*2)
            recipe = json.loads(db.execute('SELECT recipe_json FROM export_metadata').fetchone()[0])
            self.assertEqual(recipe,self.package['recipe'])
            metadata = json.loads(db.execute('SELECT metadata_json FROM epochs LIMIT 1').fetchone()[0])
            self.assertEqual(metadata['metadata']['epoch']['attributes']['ticks'],639258608779858225)
            self.assertEqual(db.execute('SELECT count(*) FROM epoch_tags').fetchone()[0],4)
            for (sql,) in db.execute('SELECT sql FROM example_queries').fetchall():
                db.execute(sql).fetchall()
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='raw_traces'").fetchone())
            self.assertIn('original H5',db.execute("SELECT compatibility FROM export_metadata").fetchone()[0])
        self.assertEqual(self.package,before)
        with self.assertRaisesRegex(ValueError,'refusing overwrite'):
            build_sqlite_export(self.package,self.path)

    def test_block_end_time_comes_from_recorded_metadata(self):
        for detail in self.service.details.values():
            detail['metadata']['block']['end_time'] = '09/24/2026 12:01:00:123456'
        self.fingerprint()
        build_sqlite_export(self.package_for(self.service.ids), self.path)
        with sqlite3.connect(self.path) as db:
            self.assertEqual({row[0] for row in db.execute('SELECT end_time FROM epoch_blocks')},
                             {'09/24/2026 12:01:00:123456'})

    def test_exported_tables_are_immutable_but_analysis_tables_can_be_added(self):
        build_sqlite_export(self.package,self.path)
        with sqlite3.connect(self.path) as db:
            for sql in ("UPDATE epochs SET included=0",'DELETE FROM export_metadata',"INSERT INTO sources VALUES ('x','y')"):
                with self.subTest(sql=sql),self.assertRaisesRegex(sqlite3.IntegrityError,'Immutable'):
                    db.execute(sql)
            db.execute('CREATE TABLE local_analysis (epoch_uuid TEXT, result REAL)')
            db.execute('INSERT INTO local_analysis VALUES (?,?)',(self.service.ids[0],1.5))
            self.assertEqual(db.execute('SELECT result FROM local_analysis').fetchone()[0],1.5)

    def test_subset_and_numeric_string_boolean_array_null_parameters_are_exact(self):
        key = self.service.ids[0]
        self.service.details[key]['parameters'].update(number=100,string='100',boolean=True,array=[1,2],null=None,
                                                      ticks=639258608779858225)
        self.fingerprint()
        package = self.package_for([key])
        build_sqlite_export(package,self.path)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT epoch_uuid FROM epochs').fetchall(),[(key,)])
            values={row[0]:row[1:] for row in db.execute('SELECT field_id,json_type,value_json,numeric_value,text_value FROM epoch_parameters')}
            self.assertEqual(values['parameters/number'],('number','100',100.0,None))
            self.assertEqual(values['parameters/string'],('string','"100"',None,'100'))
            self.assertEqual(values['parameters/boolean'],('boolean','true',None,None))
            self.assertEqual(values['parameters/array'],('array','[1,2]',None,None))
            self.assertEqual(values['parameters/null'],('null','null',None,None))
            self.assertEqual(values['parameters/ticks'],('number','639258608779858225',None,None))

    def test_tampered_duplicate_out_of_scope_and_source_pointer_fail_before_publish(self):
        cases=[]
        changed=copy.deepcopy(self.package);changed['epochs'][0]['parameters']['example']=999;cases.append(changed)
        duplicate=copy.deepcopy(self.package);duplicate['epochs'].append(duplicate['epochs'][0]);cases.append(duplicate)
        missing=copy.deepcopy(self.package);missing['epochs'].pop();cases.append(missing)
        pointer=copy.deepcopy(self.package);pointer['epochs'][0]['source_reference']['path']='/wrong/file.h5';cases.append(pointer)
        sources=copy.deepcopy(self.package);sources['sources'].append(sources['sources'][0]);cases.append(sources)
        for package in cases:
            with self.subTest(),self.assertRaises(ValueError):
                build_sqlite_export(package,self.path)
            self.assertFalse(self.path.exists())

    def test_duplicate_stream_identity_rolls_back_and_leaves_no_artifact(self):
        package=copy.deepcopy(self.package)
        package['epochs'][0]['streams'].append(package['epochs'][0]['streams'][0])
        with self.assertRaisesRegex(ValueError,'integrity'):
            build_sqlite_export(package,self.path)
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.path.parent.glob('.sqlite-export-*')),[])


    def test_compact_records_are_lossless_and_parameters_are_shared(self):
        for key in self.service.ids:
            self.service.details[key]['parameters'] = {'frequencyCutoff':100,'long_vector':list(range(150)),
                'long_text':'x'*2048,'empty':{},'slash/key':{'~name':True}}
        self.fingerprint()
        package = self.package_for(self.service.ids)
        result = build_sqlite_export(package,self.path)
        self.assertEqual(result['schema_version'],2)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
            self.assertEqual(db.execute('SELECT count(*) FROM parameter_sets').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM parameter_values').fetchone()[0],5)
            self.assertEqual(db.execute('SELECT count(*) FROM epoch_parameters').fetchone()[0],10)
            for record in package['epochs']:
                self.assertEqual(load_frozen_record(db,record['epoch_uuid']),record)
            values = dict(db.execute('SELECT field_id,value_json FROM epoch_parameters WHERE epoch_uuid=?',(self.service.ids[0],)))
            self.assertEqual(json.loads(values['parameters/long_vector']),list(range(150)))
            self.assertEqual(json.loads(values['parameters/long_text']),'x'*2048)
            self.assertEqual(json.loads(values['parameters/slash~1key/~0name']),True)
            self.assertEqual(json.loads(values['parameters/empty']),{})
            raw,compressed=db.execute('SELECT sum(raw_size),sum(length(payload)) FROM frozen_records').fetchone()
            self.assertLess(compressed,raw)
            self.assertEqual(db.execute("SELECT type FROM sqlite_master WHERE name='epoch_parameters'").fetchone()[0],'view')

    def test_cell_spanning_midnight_has_one_identity_and_start_date(self):
        for index,key in enumerate(self.service.ids):
            self.service.details[key]['metadata']['cell']['start_time']='09/24/2026 23:50:00'
            self.service.rows[key]['date']='2026-09-24' if index==0 else '2026-09-25'
        first,second=self.service.ids
        for field in ('cell_uuid','cell_label','cell_type'):
            self.service.rows[second][field]=self.service.rows[first][field]
        self.service.details[second]['metadata']['cell']=copy.deepcopy(self.service.details[first]['metadata']['cell'])
        self.fingerprint()
        package=self.package_for(self.service.ids)
        build_sqlite_export(package,self.path)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT recording_date FROM cells').fetchall(),[('2026-09-24',)])
            self.assertEqual([load_frozen_record(db,key)['date'] for key in self.service.ids],['2026-09-24','2026-09-25'])

    def test_corrupt_or_oversized_frozen_archive_is_rejected(self):
        build_sqlite_export(self.package,self.path)
        with sqlite3.connect(self.path) as db:
            db.execute('DROP TRIGGER freeze_frozen_records_update')
            identity=self.service.ids[0]
            original=db.execute('SELECT raw_size,record_sha256,payload FROM frozen_records WHERE epoch_uuid=?',(identity,)).fetchone()
            for raw_size,sha,payload in [(original[0],'0'*64,original[2]),(original[0]+1,*original[1:]),
                                        (100*1024*1024,*original[1:]),(original[0],original[1],b'corrupt'),
                                        (original[0],original[1],original[2]+b'trailing')]:
                with self.subTest(raw_size=raw_size,sha=sha):
                    db.execute('UPDATE frozen_records SET raw_size=?,record_sha256=?,payload=? WHERE epoch_uuid=?',(raw_size,sha,payload,identity))
                    with self.assertRaises(ValueError):load_frozen_record(db,identity)
