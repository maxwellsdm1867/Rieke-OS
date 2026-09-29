import unittest
from workspace_export_names import naming_options, export_download_name


class ExportNamesTests(unittest.TestCase):
    def test_default_name_is_protocol_and_local_date_without_extra_id(self):
        options = naming_options(None, 'VariableMeanNoiseCurInject', '2026-09-28')
        self.assertEqual(options['name'], 'Variable_Mean_Noise_current_injection_2026-09-28')
        record = {'dataset_uuid': 'abcd1234-rest', 'recipe': {'options': options}}
        for extension in ('.sqlite', '.json', '.zip'):
            self.assertEqual(export_download_name(record, extension), options['name'] + extension)

    def test_custom_label_preserved_but_filename_safe_and_date_once(self):
        options = naming_options('My / cell: export_2026-09-28', 'Unused', '2026-09-28')
        self.assertEqual(options['name'], 'My / cell: export_2026-09-28')
        self.assertEqual(export_download_name({'recipe': {'options': options}}, '.zip'),
                         'My_cell_export_2026-09-28.zip')
        self.assertEqual(naming_options('   ', 'Search', '2026-09-28')['name'], 'Search_2026-09-28')

    def test_existing_download_names_remain_unchanged(self):
        legacy = {'dataset_uuid': 'abcd1234-rest', 'recipe': {'options': {'name': 'Old export'}}}
        self.assertEqual(export_download_name(legacy, '.sqlite'), 'recordings-abcd1234.sqlite')

    def test_invalid_dates_and_names_are_rejected(self):
        for date in ('2026-02-30', '2026-9-28', '../2026-09-28', 2026):
            with self.subTest(date=date), self.assertRaises(ValueError):
                naming_options(None, 'Search', date)
        with self.assertRaises(ValueError):
            naming_options(['name'], 'Search', '2026-09-28')
