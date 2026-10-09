"""Authored precision through public routes; native proof is separately retained."""
import copy
import math
import unittest
from unittest.mock import patch

import test_workspace_search_presets as presets_fixture
import test_workspace_compact_explorer as explorer_fixture
from disco.workbench.recipes import checksum

VALUE = 0.15261696363083765
ROUNDED = math.nextafter(VALUE, -math.inf)


class AuthoredPrecisionTests(unittest.TestCase):
    def test_preset_roundtrip_update_version_and_match_membership(self):
        fixture = presets_fixture.SearchPresetTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        service = fixture.fixture.service
        service.details[service.ids[0]]['parameters']['example'] = VALUE
        service.details[service.ids[1]]['parameters']['example'] = ROUNDED
        predicate = {'field':'parameters/example','operator':'eq','value':VALUE}
        response = fixture.create(predicate=predicate)
        self.assertEqual(response.status_code, 201, response.get_json())
        identity = response.get_json()['preset_uuid']
        path = '/api/search-presets/' + identity
        saved = fixture.client.get(path).get_json()
        self.assertEqual(saved['predicate'], predicate)
        preview = service.explore_preview(saved['predicate'], 'cell')
        self.assertEqual([row['uuid'] for row in preview['membership']], service.ids[:1])
        updated = fixture.client.put(path, json={**fixture.body, 'predicate':predicate,
            'name':'Updated', 'expected_version':1}, headers=fixture.headers)
        self.assertEqual(updated.status_code, 200, updated.get_json())
        self.assertEqual(fixture.client.get(path+'/versions/2').get_json()['predicate'], predicate)

    def test_custom_rounding_preset_writer_runs_then_rolls_back(self):
        fixture = presets_fixture.SearchPresetTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        called = []
        original = fixture.table.insert1
        def lossy(row):
            called.append(True)
            row = copy.deepcopy(row); row['predicate']['value'] = ROUNDED
            original(row)
        with patch.object(fixture.table, 'insert1', side_effect=lossy):
            response = fixture.create(predicate={'field':'parameters/example','operator':'eq','value':VALUE})
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(called, [True])
        self.assertEqual(fixture.table.rows, [])
        self.assertEqual(fixture.versions.rows, [])

    def test_sealed_revision_float_survives_fresh_read(self):
        fixture = explorer_fixture.CompactExplorerTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        predicate = {'field':'parameters/example','operator':'eq','value':VALUE}
        created = fixture.save(predicate)
        result = fixture.client.get('/api/explore/revisions/'+created['revision_uuid'])
        self.assertEqual(result.status_code, 200, result.get_json())
        recipe = result.get_json()['recipe']
        self.assertEqual(recipe['predicate'], predicate)
        self.assertEqual(recipe['content_sha256'], checksum({key:value for key,value in recipe.items() if key!='content_sha256'}))

    def test_custom_rounding_revision_writer_rolls_back_before_audit(self):
        fixture = explorer_fixture.CompactExplorerTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        table = fixture.fixture.explorer_revisions
        original = table.insert1
        def lossy(row):
            row = copy.deepcopy(row); row['recipe']['predicate']['value'] = ROUNDED
            original(row)
        with patch.object(table, 'insert1', side_effect=lossy):
            response = fixture.client.post('/api/explore/revisions', json={'predicate':{
                'field':'parameters/example','operator':'eq','value':VALUE},'splits':'cell'}, headers=fixture.headers)
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(table.rows, [])
        self.assertEqual(fixture.fixture.events.rows, [])

    def test_export_recipe_float_roundtrip_and_custom_loss_rollback(self):
        from test_workspace_curation import CurationTests
        from disco.workbench.recipes import seal
        fixture = CurationTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        recipe = fixture.recipe()
        # Export options are sealed authored values, not acquisition metadata.
        recipe['options']['numeric_setting'] = VALUE
        recipe = seal(recipe)
        result = fixture.record(recipe)
        self.assertEqual(fixture.store.get_dataset_revision(result['dataset_uuid'])['recipe'], recipe)
        self.assertEqual(len(fixture.store.list_dataset_revisions(fixture.protocol)), 1)
        before = copy.deepcopy(fixture.datasets.rows)
        recipe = fixture.recipe(); recipe['options']['numeric_setting'] = VALUE; recipe = seal(recipe)
        original = fixture.datasets.insert1
        def lossy(row):
            row = copy.deepcopy(row); row['recipe']['options']['numeric_setting'] = ROUNDED
            original(row)
        with patch.object(fixture.datasets, 'insert1', side_effect=lossy):
            with self.assertRaisesRegex(ValueError, 'preserve exact JSON'):
                fixture.record(recipe)
        self.assertEqual(fixture.datasets.rows, before)
