"""The format tail preserves caller objects, lazy adapters and original errors."""
import builtins
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from workspace_export_artifacts import materialize_export_format


class ExportArtifactTests(unittest.TestCase):
    def setUp(self):
        self.package = {'recipe': {'frozen': True}, 'epochs': [object(), object()]}
        self.output = Path('/unused-owned-export')
        self.matlab = Mock()
        self.json = Mock()

    def materialize(self, format):
        return materialize_export_format(self.package, self.output, format=format,
            matlab_writer=self.matlab, write_json=self.json)

    def test_reference_needs_no_package_access_adapters_imports_or_directory(self):
        self.package = None
        with patch.object(builtins, '__import__', side_effect=AssertionError('eager import')):
            self.assertEqual(self.materialize('reference-json'), self.output / 'recordings.json')
        self.matlab.assert_not_called()
        self.json.assert_not_called()

    def test_sqlite_preserves_package_identity_and_only_loads_return_adapter_after_write(self):
        events = []
        def build(package, artifact):
            self.assertIs(package, self.package)
            self.assertEqual(artifact, self.output / 'recordings.sqlite')
            events.append('write')
        def prepare(output, package):
            self.assertIs(output, self.output)
            self.assertIs(package, self.package)
            events.append('return')
        def imports(name, *args, **kwargs):
            events.append(name)
            return {'workspace_sqlite': SimpleNamespace(build_sqlite_export=build),
                'workspace_external_tags': SimpleNamespace(prepare_return_folder=prepare)}[name]
        with patch.object(builtins, '__import__', side_effect=imports):
            self.assertEqual(self.materialize('wheeler-sqlite'), self.output / 'recordings.sqlite')
        self.assertEqual(events, ['workspace_sqlite', 'write', 'workspace_external_tags', 'return'])
        self.matlab.assert_not_called()
        self.json.assert_not_called()

    def test_sqlite_failure_preserves_exception_identity_and_never_loads_return_adapter(self):
        error = OSError('owned serializer failure')
        builder = Mock(side_effect=error)
        importer = Mock(return_value=SimpleNamespace(build_sqlite_export=builder))
        with patch.object(builtins, '__import__', importer):
            with self.assertRaises(OSError) as caught:
                self.materialize('wheeler-sqlite')
        self.assertIs(caught.exception, error)
        self.assertEqual([call.args[0] for call in importer.call_args_list], ['workspace_sqlite'])
        self.json.assert_not_called()

    def test_matlab_preserves_recipe_records_and_selected_path_without_loading_sqlite(self):
        records = self.package['epochs']
        def build(recipe, output, *, epoch_records):
            self.assertIs(recipe, self.package['recipe'])
            self.assertIs(epoch_records, records)
            self.assertEqual(output, self.output / 'matlab')
            return {'mat_path': '/adapter/chosen.mat', 'recipe_path': '/adapter/recipe.json',
                'warnings': ['retained'], 'count': 2}
        self.matlab.side_effect = build
        with patch.object(builtins, '__import__', side_effect=AssertionError('eager import')):
            self.assertEqual(self.materialize('matlab-mat'), Path('/adapter/chosen.mat'))
        self.json.assert_called_once_with(self.output / 'matlab' / 'export-report.json',
            {'warnings': ['retained'], 'count': 2})
        self.assertIs(self.package['epochs'], records)

    def test_matlab_report_error_precedes_missing_path_and_keeps_exception_identity(self):
        error = OSError('owned report failure')
        self.matlab.return_value = {'count': 2}
        self.json.side_effect = error
        with self.assertRaises(OSError) as caught:
            self.materialize('matlab-mat')
        self.assertIs(caught.exception, error)

    def test_unsupported_format_has_no_adapter_effects(self):
        with patch.object(builtins, '__import__', side_effect=AssertionError('eager import')):
            with self.assertRaisesRegex(ValueError, 'Unsupported export format'):
                self.materialize('unknown')
        self.matlab.assert_not_called()
        self.json.assert_not_called()


if __name__ == '__main__':
    unittest.main()
