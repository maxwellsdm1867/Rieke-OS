"""Exact full-catalog engine control on a small fixture before scale runs."""
import tempfile
from pathlib import Path
import unittest

from benchmark_service_scale import fixture, Details
from workspace_disk_index import DiskMetadataIndex
from eav_duck import DuckCatalogIndex, derive_from_typed, digest, import_sqlite
from projection import AnalyticalProjection, generate_csv


class ExactCatalogTests(unittest.TestCase):
    def test_catalogs_predicate_choices_and_scope_order(self):
        with tempfile.TemporaryDirectory(prefix='disco-eav-duck-sanity-') as directory:
            root = Path(directory)
            service, _ = fixture(1000)
            sqlite = DiskMetadataIndex.build(root / 'source.sqlite', service.rows,
                                             Details(service.rows), service.sources,
                                             'test-generation', service.project['project_uuid'])
            import_sqlite(root / 'source.sqlite', root / 'copy.duckdb')
            duck = DuckCatalogIndex(root / 'copy.duckdb')
            try:
                global_catalog = sqlite.catalog()
                self.assertEqual(digest(duck.catalog()), digest(global_catalog))
                for scope in ([], list(service.rows)[3::5], list(reversed(list(service.rows)[3::5]))):
                    self.assertEqual(digest(sqlite.catalog(scope, global_catalog['fields'])),
                                     digest(duck.catalog(scope, global_catalog['fields'])))
                    self.assertEqual(digest(sqlite.predicate_catalog(scope)),
                                     digest(duck.predicate_catalog(scope)))
                # The cached global copy is not sufficient: force full ordinary
                # catalog recomputation on both engines and compare every field.
                sqlite._catalog_cache = None
                duck._catalog_cache = None
                self.assertEqual(digest(sqlite.catalog()), digest(duck.catalog()))
                generate_csv(root / 'fixture.csv', 1000)
                typed = AnalyticalProjection('duckdb', root / 'typed.duckdb')
                typed.build(root / 'fixture.csv')
                typed.close()
                derive_from_typed(root / 'typed.duckdb', root / 'source.sqlite', root / 'derived.duckdb')
                derived = DuckCatalogIndex(root / 'derived.duckdb')
                try:
                    self.assertEqual(digest(derived.catalog()), digest(sqlite.catalog()))
                    subset = list(service.rows)[3::5]
                    self.assertEqual(digest(derived.catalog(subset, global_catalog['fields'])),
                                     digest(sqlite.catalog(subset, global_catalog['fields'])))
                    self.assertEqual(digest(derived.predicate_catalog(subset)),
                                     digest(sqlite.predicate_catalog(subset)))
                finally:
                    derived.close()
            finally:
                sqlite.close()
                duck.close()


if __name__ == '__main__':
    unittest.main()
