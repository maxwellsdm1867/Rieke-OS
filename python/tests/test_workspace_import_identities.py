"""Global identity collisions fail before population, using isolated SQL doubles."""
import contextlib
import copy
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import recording_workspace as workspace


def fixture(epoch_count=1):
    return {'uuid': 'new-experiment', 'animals': [{'uuid':'new-animal','preparations': [{'uuid':'new-preparation','cells': [
        {'uuid': 'new-cell', 'epoch_groups': [{'uuid': 'new-group', 'epoch_blocks': [
            {'uuid': 'new-block', 'epochs': [{'uuid': f'new-epoch-{index}'} for index in range(epoch_count)]}
        ]}]}]}]}]}


class IdentityTable:
    def __init__(self, identities=(), requests=None, selected=None):
        self.identities = set(identities)
        self.requests = [] if requests is None else requests
        self.selected = self.identities if selected is None else selected

    def __and__(self, restriction):
        self.requests.append(restriction)
        keys = {row['h5_uuid'] for row in restriction}
        return IdentityTable(self.identities, self.requests, self.identities & keys)

    def fetch(self, field, limit=None):
        assert field == 'h5_uuid' and limit == 1
        return sorted(self.selected)[:limit]


def catalog_with(**existing):
    return SimpleNamespace(**{name: IdentityTable(existing.get(name, ()))
        for name in ('Animal', 'Preparation', 'Cell', 'EpochGroup', 'EpochBlock', 'Epoch', 'Response', 'Stimulus')})


class MissingRelation:
    def __and__(self, restriction):
        return self

    def __bool__(self):
        return False


class Records:
    def __init__(self, rows):
        self.rows = rows

    def __and__(self, restriction):
        return self

    def __len__(self):
        return len(self.rows)

    def fetch1(self):
        return self.rows[0]

    def to_dicts(self):
        return self.rows

    def proj(self,*fields,**renames):
        return Records([{**{key:row[key] for key in fields},**{new:row[old] for new,old in renames.items()}} for row in self.rows])


class ImportIdentityTests(unittest.TestCase):
    def test_acquisition_protocol_delta_uses_only_incoming_names_and_project_sources(self):
        source = Mock()
        experiments = [7, 12]
        class Source:
            def __and__(self, restriction):
                source(restriction)
                return self
            def fetch(self, field):
                assert field == 'experiment_id'
                return experiments
        class Blocks:
            def __and__(self, restriction):
                self.restriction = restriction
                return self
            def proj(self, field):
                self.field = field
                return self
        class Protocols:
            def __init__(self):
                self.restrictions = []
            def __and__(self, restriction):
                self.restrictions.append(restriction)
                return self
            def fetch(self, field):
                self.field = field
                return ['known', 'known']
        blocks, protocols = Blocks(), Protocols()
        catalog = SimpleNamespace(EpochBlock=blocks, Protocol=protocols)
        result = workspace.new_project_protocol_types(catalog, Source(), 'project-a', ['known', 'new', 'new'])
        self.assertEqual(result, {'new'})
        source.assert_called_once_with({'project_uuid': 'project-a'})
        self.assertEqual(blocks.restriction, [{'experiment_id': 7}, {'experiment_id': 12}])
        self.assertEqual(blocks.field, 'protocol_id')
        self.assertEqual(protocols.restrictions, [[{'name': 'known'}, {'name': 'new'}], blocks])
        self.assertEqual(protocols.field, 'name')

    def test_empty_protocol_import_performs_no_catalog_lookup(self):
        self.assertEqual(workspace.new_project_protocol_types(None, None, 'project', []), set())

    def test_each_supported_identity_is_checked_globally(self):
        for name, identity in [('Animal', 'new-animal'), ('Preparation', 'new-preparation'),
                               ('Cell', 'new-cell'), ('EpochGroup', 'new-group'),
                               ('EpochBlock', 'new-block'), ('Epoch', 'new-epoch-0'),
                               ('Response', 'new-response'), ('Stimulus', 'new-stimulus')]:
            with self.subTest(table=name):
                catalog = catalog_with(**{name: [identity]})
                with self.assertRaisesRegex(ValueError, f'Existing {name} source UUID.*reconciliation'):
                    data = fixture()
                    epoch = next(workspace.epochs(data))[-1]
                    epoch.update(responses={'Amp1': {'uuid': 'new-response'}},
                                 stimuli={'LED': {'uuid': 'new-stimulus'}})
                    workspace.assert_new_catalog_identities(data, catalog)

    def test_distinct_identifiers_pass_and_batches_are_bounded(self):
        data = fixture(503)
        original = copy.deepcopy(data)
        catalog = catalog_with(Cell=['other-cell'], Epoch=['other-epoch'])
        workspace.assert_new_catalog_identities(data, catalog, batch_size=200)
        self.assertEqual([len(batch) for batch in catalog.Epoch.requests], [200, 200, 103])
        self.assertEqual(data, original)
        for name in ('Animal', 'Preparation', 'Cell', 'EpochGroup', 'EpochBlock', 'Epoch', 'Response', 'Stimulus'):
            for batch in getattr(catalog, name).requests:
                self.assertTrue(all(set(row) == {'h5_uuid'} for row in batch))

    def test_duplicate_uuid_in_new_hierarchy_fails_without_query(self):
        data = fixture()
        data['animals'][0]['preparations'][0]['cells'].append(
            copy.deepcopy(data['animals'][0]['preparations'][0]['cells'][0]))
        catalog = catalog_with()
        with self.assertRaisesRegex(ValueError, 'Repeated Cell source UUID'):
            workspace.assert_new_catalog_identities(data, catalog)
        self.assertEqual(catalog.Cell.requests, [])

    def test_empty_cell_is_checked_even_without_epochs(self):
        data = fixture(0)
        with self.assertRaisesRegex(ValueError, 'Existing Cell source UUID'):
            workspace.assert_new_catalog_identities(data, catalog_with(Cell=['new-cell']))

    def test_new_file_collision_rejects_inside_transaction_before_population(self):
        for table, identity in [('Cell', 'new-cell'), ('Epoch', 'new-epoch-0')]:
            with self.subTest(table=table), tempfile.TemporaryDirectory() as folder:
                project = Path(folder)
                catalog = catalog_with(**{table: [identity]})
                transaction_state = []

                @contextlib.contextmanager
                def transaction():
                    transaction_state.append('entered')
                    try:
                        yield
                    except Exception:
                        transaction_state.append('rolled_back')
                        raise

                connection = SimpleNamespace(transaction=transaction(), query=Mock())
                connection.query.return_value.fetchone.return_value = (1,)
                catalog.schema = SimpleNamespace(connection=connection)
                catalog.Experiment = MissingRelation()
                population = SimpleNamespace(configure_tables=Mock(), append_experiment=Mock())
                package = ModuleType('retinanalysis')
                package.__path__ = []
                config = ModuleType('retinanalysis.config')
                config.schema = catalog
                utils = ModuleType('retinanalysis.utils')
                utils.database_pop = population
                modules = {'retinanalysis': package, 'retinanalysis.config': config,
                           'retinanalysis.utils': utils}
                Source = MissingRelation()
                Source.insert1 = Mock()
                manifest = {'source_path': str(project / 'novel-file.h5'), 'source_sha256': 'a' * 64}
                with patch.dict(sys.modules, modules), patch.object(workspace, 'connect', return_value=object()), \
                        patch.object(workspace, 'workspace_tables', return_value=(Mock(), Source, Mock(), Mock())):
                    with self.assertRaisesRegex(ValueError, f'Existing {table} source UUID'):
                        workspace.import_catalog(project, fixture(), manifest, project, 'fixture-container')
                population.configure_tables.assert_not_called()
                population.append_experiment.assert_not_called()
                Source.insert1.assert_not_called()
                self.assertEqual(transaction_state, ['entered', 'rolled_back'])

    def test_same_sha_existing_project_bypasses_new_identity_guard(self):
        self.same_sha_existing_project()

    def test_same_sha_mixed_manifest_count_conventions_with_empty_cells(self):
        for new_incoming in (True, False):
            with self.subTest(new_incoming=new_incoming):
                self.same_sha_existing_project(extra_cell=True, new_incoming=new_incoming)

    def test_same_sha_recheck_rejects_wrong_registration_and_cell_parent(self):
        for conflict in ('source_registration', 'catalog_parent'):
            with self.subTest(conflict=conflict):
                self.same_sha_existing_project(conflict=conflict)

    def same_sha_existing_project(self, extra_cell=False, new_incoming=False, conflict=None):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            project_id = '04cf7a0b-aa6a-4401-8c91-942b927421ce'
            workspace.write_json(project / 'project.json', {'project_uuid': project_id, 'name': 'Fixture'})
            data = fixture()
            data['rig_type']='PATCH'
            data['animals'][0]['preparations'][0]['cells'][0]['epoch_groups'][0]['epoch_blocks'][0]['protocolID']='example.Protocol'
            if extra_cell:
                data['animals'][0]['preparations'][0]['cells'].append(
                    {'uuid': 'empty-cell', 'epoch_groups': []})
            epoch = next(workspace.epochs(data))[-1]
            epoch.update(parameters={}, attributes={}, responses={}, stimuli={})
            connection = SimpleNamespace(transaction=contextlib.nullcontext(), query=Mock())
            connection.query.return_value.fetchone.return_value = (1,)
            catalog = SimpleNamespace(schema=SimpleNamespace(connection=connection),
                Experiment=Records([{'id':7,'h5_uuid':'new-experiment','rig_type':'PATCH','is_mea':0}]),
                Animal=Records([{'id':10,'h5_uuid':'new-animal','experiment_id':7,'parent_id':7}]),
                Preparation=Records([{'id':20,'h5_uuid':'new-preparation','experiment_id':7,'parent_id':10}]),
                Cell=Records([{'id':30,'h5_uuid':'new-cell','experiment_id':7,'parent_id':20}] +
                             ([{'id':31,'h5_uuid':'empty-cell','experiment_id':7,'parent_id':20}] if extra_cell else [])),
                EpochGroup=Records([{'id':40,'h5_uuid':'new-group','experiment_id':7,'parent_id':30,'protocol_id':13}]),
                EpochBlock=Records([{'id':50,'h5_uuid':'new-block','experiment_id':7,'parent_id':40,'protocol_id':13}]),
                Epoch=Records([{'h5_uuid':epoch['uuid'],'id':1,'experiment_id':7,'parent_id':50,'parameters':{},'attributes':{}}]),
                Response=Records([]), Stimulus=Records([]),Protocol=Records([{'protocol_id':13,'name':'example.Protocol'}]))
            population = SimpleNamespace(configure_tables=Mock(), append_experiment=Mock())
            package = ModuleType('retinanalysis')
            package.__path__ = []
            config = ModuleType('retinanalysis.config')
            config.schema = catalog
            utils = ModuleType('retinanalysis.utils')
            utils.database_pop = population
            modules = {'retinanalysis': package, 'retinanalysis.config': config, 'retinanalysis.utils': utils}
            source = Records([{'project_uuid': project_id, 'experiment_id': 7, 'experiment_uuid':'new-experiment'}])
            manifest = {'source_path': str(project / 'same-bytes.h5'), 'source_sha256': 'a' * 64,
                'counts': {'cells': 1, 'epochs': 1, 'responses': 0, 'stimuli': 0},
                'warnings': [], 'protocol_epoch_counts': {}}
            if new_incoming:
                manifest['cell_count_semantics'] = 'all-source-cells-v1'
                manifest['counts']['cells'] += int(extra_cell)
            stored_manifest = copy.deepcopy(manifest)
            if new_incoming:
                stored_manifest.pop('cell_count_semantics')
                stored_manifest['counts']['cells'] = 1
            else:
                stored_manifest['cell_count_semantics'] = 'all-source-cells-v1'
                stored_manifest['counts']['cells'] += int(extra_cell)
            source.rows[0]['manifest'] = copy.deepcopy(stored_manifest)
            if conflict == 'source_registration':
                source.rows[0]['experiment_uuid'] = 'different-experiment'
            elif conflict == 'catalog_parent':
                catalog.Cell.rows[0]['parent_id'] = 999
            with patch.dict(sys.modules, modules), \
                    patch.object(workspace, 'connect', return_value=SimpleNamespace(config={'database.port': 3306})), \
                    patch.object(workspace, 'workspace_tables', return_value=(Mock(), source, Mock(), Mock())), \
                    patch.object(workspace, 'assert_new_catalog_identities', side_effect=AssertionError('Must bypass')) as guard:
                if conflict:
                    with self.assertRaises(workspace.CatalogIdentityConflict) as caught:
                        workspace.import_catalog(project, data, manifest, project, 'fixture-container')
                    self.assertEqual(caught.exception.conflict['kind'], conflict)
                    population.append_experiment.assert_not_called()
                    self.assertEqual(source.rows[0]['manifest'], stored_manifest)
                    return
                result = workspace.import_catalog(project, data, manifest, project, 'fixture-container')
            self.assertEqual(result['status'], 'already_imported')
            self.assertEqual(result['catalog_delta'], {'sources_added': 0, 'cells_added': 0,
                'epochs_added': 0, 'responses_added': 0, 'stimuli_added': 0, 'protocol_types_added': 0})
            guard.assert_not_called()
            population.append_experiment.assert_not_called()
            self.assertEqual(source.rows[0]['manifest'], stored_manifest)


if __name__ == '__main__':
    unittest.main()
