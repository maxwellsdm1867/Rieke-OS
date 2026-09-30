"""Importer conflicts are distinct, atomic, and never auto-rename acquisitions."""
import contextlib
import copy
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import recording_workspace as workspace


class Relation:
    def __init__(self, collision_field=None, selected=False):
        self.collision_field = collision_field
        self.selected = selected

    def __and__(self, restriction):
        return Relation(self.collision_field, self.collision_field in restriction)

    def __bool__(self):
        return self.selected


class ImportConflictTests(unittest.TestCase):
    def test_changed_source_uuid_and_filename_collisions_are_separate_atomic_errors(self):
        for field, kind in (('h5_uuid', 'source_revision_conflict'),
                            ('exp_name', 'experiment_name_collision')):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                data = {'uuid': 'acquisition-uuid', 'label': 'Cell 3', 'animals': []}
                original = copy.deepcopy(data)
                transitions = []

                @contextlib.contextmanager
                def transaction():
                    transitions.append('entered')
                    try:
                        yield
                    except Exception:
                        transitions.append('rolled_back')
                        raise
                    else:
                        transitions.append('committed')

                connection = SimpleNamespace(transaction=transaction(), query=Mock())
                connection.query.return_value.fetchone.return_value = (1,)
                catalog = SimpleNamespace(schema=SimpleNamespace(connection=connection),
                                          Experiment=Relation(field))
                population = SimpleNamespace(configure_tables=Mock(), append_experiment=Mock())
                package = ModuleType('retinanalysis'); package.__path__ = []
                config = ModuleType('retinanalysis.config'); config.schema = catalog
                utils = ModuleType('retinanalysis.utils'); utils.database_pop = population
                source = Relation(); source.insert1 = Mock()
                events = Mock()
                manifest = {'source_path': str(project / '2026-06-11.h5'), 'source_sha256': 'a' * 64}
                with patch.dict(sys.modules, {'retinanalysis': package, 'retinanalysis.config': config,
                                             'retinanalysis.utils': utils}), \
                        patch.object(workspace, 'connect', return_value=object()), \
                        patch.object(workspace, 'workspace_tables', return_value=(Mock(), source, events, Mock())), \
                        patch.object(workspace, 'assert_new_catalog_identities') as guard:
                    with self.assertRaises(workspace.CatalogIdentityConflict) as caught:
                        workspace.import_catalog(project, data, manifest, project, 'disposable-double')
                self.assertEqual(caught.exception.conflict['kind'], kind)
                self.assertEqual(caught.exception.conflict['acquisition_uuid'], data['uuid'])
                self.assertEqual(data, original)
                self.assertEqual(transitions, ['entered', 'rolled_back'])
                guard.assert_not_called()
                population.configure_tables.assert_not_called()
                population.append_experiment.assert_not_called()
                source.insert1.assert_not_called()
                connection.query.assert_any_call("SELECT RELEASE_LOCK('recording_workspace_import')")


if __name__ == '__main__':
    unittest.main()
