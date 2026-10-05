"""Import provenance only: disposable inert roots, no qualification workload."""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TwoRootImportsTests(unittest.TestCase):
    def run_block(self, filename, preload=None):
        source = Path(__file__).with_name(filename).read_text()
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == ('main' if filename == 'million_controls.py' else 'worker'))
        statements = (function.body if filename == 'million_controls.py' else
                      next(node for node in function.body if isinstance(node, ast.Try)).body)
        start = next(i for i, node in enumerate(statements)
                     if ast.unparse(node).startswith('sys.path.insert('))
        end = next(i for i, node in enumerate(statements[start:], start)
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'TypedMetadataIndex'
                           for target in node.targets))
        block = ast.unparse(ast.Module(body=statements[start:end + 1], type_ignores=[]))
        with tempfile.TemporaryDirectory(prefix='two-root-imports-') as temporary:
            root = Path(temporary)
            for label in ('baseline', 'candidate', 'wrong'):
                python = root / label / 'python'
                package = python / 'disco/metadata'
                package.mkdir(parents=True)
                (python / 'disco/__init__.py').write_text('')
                (package / '__init__.py').write_text('')
                (python / 'workspace_disk_index.py').write_text(f"origin = {label!r}\n")
                (package / 'typed_index.py').write_text(
                    f"class TypedMetadataIndex:\n    origin = {label!r}\n")
                # The moved name must never substitute for the native comparator.
                (package / 'disk_index.py').write_text("raise AssertionError('Wrong native module name')\n")
            prefix = f'''from pathlib import Path
from types import SimpleNamespace
import sys
args = SimpleNamespace(baseline_root=Path({str(root / 'baseline')!r}),
                       implementation_root=Path({str(root / 'candidate')!r}))
'''
            if preload == 'disco':
                prefix += "sys.path.insert(0, str(args.baseline_root / 'python'))\nimport disco\n"
            elif preload == 'native':
                prefix += f"sys.path.insert(0, {str(root / 'wrong/python')!r})\nimport workspace_disk_index\n"
            suffix = "\nassert native_module.origin == 'baseline'\nassert TypedMetadataIndex.origin == 'candidate'\n"
            return subprocess.run([sys.executable, '-I', '-B', '-c', prefix + block + suffix],
                                  capture_output=True, text=True, timeout=10)

    def test_both_roots_with_regular_baseline_package(self):
        for filename in ('million_controls.py', 'million_worker.py'):
            with self.subTest(filename=filename):
                result = self.run_block(filename)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_preloaded_baseline_disco_refuses_candidate_identity(self):
        for filename in ('million_controls.py', 'million_worker.py'):
            with self.subTest(filename=filename):
                result = self.run_block(filename, 'disco')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Typed candidate did not load from the implementation root', result.stderr)

    def test_preloaded_wrong_native_refuses_baseline_identity(self):
        for filename in ('million_controls.py', 'million_worker.py'):
            with self.subTest(filename=filename):
                result = self.run_block(filename, 'native')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Native comparator did not load from the baseline root', result.stderr)


if __name__ == '__main__':
    unittest.main()
