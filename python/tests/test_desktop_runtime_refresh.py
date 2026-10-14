"""Application-only refresh refuses incompatible retained dependency layers."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import desktop_build_runtime as runtime_builder


class RuntimeRefreshTests(unittest.TestCase):
    def test_full_build_does_not_reseal_existing_unattested_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            sentinel = output / 'python' / 'old-runtime'
            sentinel.parent.mkdir()
            sentinel.write_text('old bytes')
            with patch.object(runtime_builder, 'run') as run:
                for receipt in (None, {'runtime_build_inputs': {'version': 0}}):
                    if receipt is not None:
                        (output / 'build-receipt.json').write_text(json.dumps(receipt))
                    with self.subTest(receipt=receipt):
                        with self.assertRaisesRegex(ValueError, 'fresh pinned runtime'):
                            runtime_builder.build(output)
                        self.assertEqual(sentinel.read_text(), 'old bytes')
                        run.assert_not_called()

    def test_refresh_rechecks_inputs_before_copy_and_receipt_publication(self):
        for mutation_stage in ('scientific_preflight', 'build_frontend', 'copy_application'):
            with self.subTest(stage=mutation_stage), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for name in runtime_builder.RUNTIME_BUILD_INPUTS:
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(name)
                output = root / 'runtime'
                output.mkdir()
                receipt_path = output / 'build-receipt.json'
                with patch.object(runtime_builder, 'ROOT', root), \
                        patch.object(sys, 'argv', ['build', '--refresh-application', '--output', str(output)]), \
                        patch.object(runtime_builder, 'scientific_preflight', return_value={}) as preflight, \
                        patch.object(runtime_builder, 'build_frontend') as frontend, \
                        patch.object(runtime_builder, 'copy_application') as copy, \
                        patch.object(runtime_builder, 'refresh_native_license_inventory'), \
                        patch.object(runtime_builder, 'run') as run:
                    original = json.dumps({'runtime_build_inputs': runtime_builder.runtime_build_inputs()})
                    receipt_path.write_text(original)
                    def change_input(*args):
                        (root / runtime_builder.RUNTIME_BUILD_INPUTS[0]).write_text('changed during refresh')
                        return {}
                    operations = {'scientific_preflight': preflight,
                                  'build_frontend': frontend, 'copy_application': copy}
                    operations[mutation_stage].side_effect = change_input
                    with self.assertRaisesRegex(ValueError, 'fresh pinned runtime'):
                        runtime_builder.main()
                    self.assertEqual(receipt_path.read_text(), original)
                    run.assert_not_called()
                    if mutation_stage != 'copy_application':
                        copy.assert_not_called()

    def test_refresh_rejects_legacy_and_each_changed_runtime_input_before_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in runtime_builder.RUNTIME_BUILD_INPUTS:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            output = root / 'runtime'
            output.mkdir()
            receipt_path = output / 'build-receipt.json'
            with patch.object(runtime_builder, 'ROOT', root), \
                    patch.object(sys, 'argv', ['build', '--refresh-application', '--output', str(output)]), \
                    patch.object(runtime_builder, 'scientific_preflight') as preflight, \
                    patch.object(runtime_builder, 'build_frontend') as frontend, \
                    patch.object(runtime_builder, 'copy_application') as copy, \
                    patch.object(runtime_builder, 'refresh_native_license_inventory') as licenses, \
                    patch.object(runtime_builder, 'run') as run:
                current = runtime_builder.runtime_build_inputs()
                receipts = [{}, {'runtime_build_inputs': current}]
                for name in runtime_builder.RUNTIME_BUILD_INPUTS:
                    changed = json.loads(json.dumps(current))
                    changed['sha256'][name] = 'old bytes'
                    receipts.append({'runtime_build_inputs': changed})
                for receipt in [receipts[0], *receipts[2:]]:
                    with self.subTest(receipt=receipt):
                        original = json.dumps(receipt)
                        receipt_path.write_text(original)
                        with self.assertRaisesRegex(ValueError, 'fresh pinned runtime'):
                            runtime_builder.main()
                        self.assertEqual(receipt_path.read_text(), original)
                        for operation in (preflight, frontend, copy, licenses, run):
                            operation.assert_not_called()
                receipt_path.write_text(json.dumps(receipts[1]))
                preflight.return_value = {'native_imports': 'passed'}
                runtime_builder.main()
                for operation in (preflight, frontend, copy, licenses, run):
                    operation.assert_called_once()
                refreshed = json.loads(receipt_path.read_text())
                self.assertEqual(refreshed['runtime_build_inputs'], current)
                self.assertEqual(refreshed['scientific_runtime'], preflight.return_value)
                # Changes to source bytes, not only malformed receipts, refuse reuse.
                path = root / runtime_builder.RUNTIME_BUILD_INPUTS[0]
                path.write_text('updated specification')
                with self.assertRaisesRegex(ValueError, 'fresh pinned runtime'):
                    runtime_builder.require_current_runtime_inputs(refreshed)

