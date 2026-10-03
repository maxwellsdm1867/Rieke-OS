"""Offline checker exit-status regression; synthetic source files, no app/DB."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

CHECKER = Path(__file__).with_name('verify_source_catalog.py')

class SourceCatalogExitTests(unittest.TestCase):
    def check(self, mutation=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); kit=root/'kit'; repo=root/'repo'; sql=repo/'python'
            kit.mkdir(); sql.mkdir(parents=True)
            declaration='id: int\n---\nlabel: varchar(255)'
            source='class Example:\n    definition = '+repr(declaration)+'\n'
            (sql/'table.py').write_text(source)
            dependency=root/'schema.py'; dependency.write_text('# empty synthetic dependency\n')
            (sql/'derived.py').write_text("DDL = 'CREATE TABLE helper(id INTEGER)'\n")
            (sql/'workspace_sqlite.py').write_text("SCHEMA = 'CREATE TABLE exported(id INTEGER)'\n")
            catalog={'baseline_commit':'synthetic','tables':[{'schema':'recording_workspace','table':'example','class':'Example','source':'python/table.py','datajoint_definition':declaration}],
                     'derived_table_ddl_source_literals':[{'source':'python/derived.py','source_literal':"'CREATE TABLE helper(id INTEGER)'"}],
                     'frozen_export_sqlite_v2_ddl':'CREATE TABLE exported(id INTEGER)'}
            if mutation=='definition':(sql/'table.py').write_text(source.replace('varchar(255)','varchar(256)'))
            if mutation=='missing_class':(sql/'table.py').write_text('# deleted\n')
            if mutation=='extra':(sql/'extra.py').write_text('class Extra:\n    definition = "id: int"\n')
            if mutation=='dependency_extra':dependency.write_text('class Extra:\n    definition = "id: int"\n')
            if mutation=='derived':(sql/'derived.py').write_text("DDL = 'CREATE TABLE changed(id INTEGER)'\n")
            if mutation=='export':(sql/'workspace_sqlite.py').write_text("SCHEMA = 'CREATE TABLE changed(id INTEGER)'\n")
            (kit/'current-database-schema.json').write_text(json.dumps(catalog))
            output=root/'report.json'
            args=[str(CHECKER),'--kit',str(kit),'--repo',str(repo),'--retinanalysis-schema',str(dependency),'--output',str(output)]
            with patch.object(sys,'argv',args), patch('subprocess.check_output',return_value='synthetic-head\n'), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:runpy.run_path(str(CHECKER),run_name='__main__')
            report=json.loads(output.read_text())
            return stopped.exception.code,report

    def test_matching_sources_exit_zero(self):
        code,report=self.check(); self.assertEqual(code,0); self.assertTrue(report['passed'])

    def test_each_mismatch_exits_one_and_retains_report(self):
        for mutation in ('definition','missing_class','extra','dependency_extra','derived','export'):
            with self.subTest(mutation=mutation):
                code,report=self.check(mutation); self.assertEqual(code,1); self.assertFalse(report['passed'])

if __name__=='__main__':unittest.main(verbosity=2)
