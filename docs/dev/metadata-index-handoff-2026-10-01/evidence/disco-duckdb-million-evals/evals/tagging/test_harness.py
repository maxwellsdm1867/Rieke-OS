import importlib.util
from pathlib import Path
import sqlite3
import unittest

spec=importlib.util.spec_from_file_location('tag_benchmark',Path(__file__).with_name('benchmark.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class SQLRowsTests(unittest.TestCase):
    def setUp(self):
        self.database=sqlite3.connect(':memory:')
        self.database.execute('CREATE TABLE epochs(epoch_uuid TEXT PRIMARY KEY,cell_uuid TEXT,cell_label TEXT,metadata_hash TEXT)')
        self.database.executemany('INSERT INTO epochs VALUES(?,?,?,?)',[(f'e{i}',f'c{i//100}',f'Cell{i//100}','b'*64) for i in range(200)])
        self.database.execute('CREATE INDEX cell_members ON epochs(cell_uuid)')
    def tearDown(self):self.database.close()
    def test_selected_membership_does_not_iterate_universe(self):
        rows=module.SQLRows(self.database,'epoch')
        queries=[];self.database.set_trace_callback(queries.append)
        self.assertIn('e1',rows);self.assertNotIn('unknown',rows)
        self.assertEqual(rows['e1']['cell_uuid'],'c0')
        self.assertEqual(len(rows),200)
        self.assertTrue(all('WHERE epoch_uuid=' in query for query in queries))
        self.assertEqual(len(queries),2)
    def test_cell_identity_and_count(self):
        cells=module.SQLRows(self.database,'cell')
        self.assertEqual(len(cells),2)
        self.assertIn('c1',cells);self.assertNotIn('e1',cells)
        self.assertEqual(cells['c1']['cell_label'],'Cell1')
    def test_cache_is_bounded(self):
        self.database.executemany('INSERT INTO epochs VALUES(?,?,?,?)',[(f'e{i}',f'c{i//100}',f'Cell{i//100}','b'*64) for i in range(200,2500)])
        rows=module.SQLRows(self.database,'epoch')
        for i in range(2500):rows[f'e{i}']
        self.assertEqual(len(rows.cache),2048)
        self.assertNotIn('e0',rows.cache)


if __name__=='__main__':unittest.main()
