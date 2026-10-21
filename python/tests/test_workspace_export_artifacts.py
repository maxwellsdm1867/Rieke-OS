"""The format tail preserves caller objects, lazy adapters and original errors."""
import builtins
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import json
import tempfile

from workspace_export_artifacts import materialize_export_format, stage_export


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
                'disco.decisions.external_tags': SimpleNamespace(prepare_return_folder=prepare)}[name]
        with patch.object(builtins, '__import__', side_effect=imports):
            self.assertEqual(self.materialize('wheeler-sqlite'), self.output / 'recordings.sqlite')
        self.assertEqual(events, ['workspace_sqlite', 'write', 'disco.decisions.external_tags', 'return'])
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


class StageExportTests(unittest.TestCase):
    """The single staging owner: folder, recipe, package, format, marker, publish."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name) / 'exports' / 'one'
        self.recipe = {'export_uuid': 'one'}
        self.package = {'recipe': self.recipe, 'epochs': []}
        self.events = []

    def write_json(self, path, value):
        self.events.append(('json', Path(path).name))
        Path(path).write_text(json.dumps(value))

    def save_snapshot(self, path, value):
        self.events.append(('recipe', Path(path).name))
        Path(path).write_text(json.dumps(value))

    def stage(self, publish, **options):
        return stage_export(self.output, self.recipe, format=options.pop('format', 'reference-json'),
            build_package=options.pop('build_package', lambda: self.package), publish=publish,
            matlab_writer=Mock(), write_json=options.pop('write_json', self.write_json),
            save_snapshot=self.save_snapshot, now=lambda: '2026-10-18T00:00:00+00:00', **options)

    def test_success_orders_recipe_reference_then_publish_and_returns_its_value(self):
        def publish(artifact):
            self.events.append(('publish', artifact.name))
            return {'dataset_uuid': 'saved'}
        self.assertEqual(self.stage(publish), {'dataset_uuid': 'saved'})
        self.assertEqual(self.events, [('recipe', 'recipe.json'), ('json', 'recordings.json'),
                                       ('publish', 'recordings.json')])
        self.assertFalse((self.output / 'failure.json').exists())

    def test_any_failure_writes_one_marker_shape_with_caller_fields_and_reraises(self):
        for stage in ('package', 'publish'):
            with self.subTest(stage=stage):
                self.setUp()
                error = ValueError(stage + ' fault')
                build = Mock(side_effect=error) if stage == 'package' else (lambda: self.package)
                publish = Mock(side_effect=error)
                with self.assertRaises(ValueError) as caught:
                    self.stage(publish, build_package=build, failure_fields={'export_scope': {'kind': 'x'}})
                self.assertIs(caught.exception, error)
                self.assertEqual(json.loads((self.output / 'failure.json').read_text()),
                    {'at': '2026-10-18T00:00:00+00:00', 'status': 'failed', 'error': stage + ' fault',
                     'artifact_published': False, 'export_scope': {'kind': 'x'}})

    def test_marker_oserror_keeps_original_error(self):
        error = ValueError('primary fault')
        def write_json(path, value):
            if Path(path).name == 'failure.json':
                raise OSError('secondary marker fault')
            self.write_json(path, value)
        with self.assertRaises(ValueError) as caught:
            self.stage(Mock(side_effect=error), write_json=write_json)
        self.assertIs(caught.exception, error)

    def test_existing_output_is_never_marked(self):
        self.output.mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            self.stage(Mock())
        self.assertEqual(list(self.output.iterdir()), [])

    def test_linked_format_prepares_package_instead_of_reference_json(self):
        prepared = {'prepared': True}
        prepare = Mock(return_value=prepared)
        bundle = Mock(return_value=self.output / 'bundle.zip')
        fake = SimpleNamespace(prepare_linked_package=prepare, build_linked_export_bundle=bundle)
        with patch.dict('sys.modules', {'workspace_linked_sqlite': fake}):
            self.stage(lambda artifact: artifact, format='linked-sqlite',
                       linked_sources=('manifests', 'root', 'sources'))
        prepare.assert_called_once_with(self.package, 'manifests', 'root', grouping_sources='sources')
        bundle.assert_called_once_with(prepared, self.output)
        self.assertNotIn(('json', 'recordings.json'), self.events)


if __name__ == '__main__':
    unittest.main()
