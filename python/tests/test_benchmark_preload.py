"""React 19 benchmark command contract, without dependencies or measurements."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('benchmark', ROOT / 'tools/benchmark.py')
bench = importlib.util.module_from_spec(spec); spec.loader.exec_module(bench)

class PreloadTests(unittest.TestCase):
    def test_both_commands_preload_committed_hashed_environment(self):
        preload = ROOT / 'workspace-app/src/test-support/reactTestEnvironment.js'
        for correctness in (False, True):
            command = bench.frontend_command(correctness=correctness)
            self.assertEqual(command[:3], ['node', '--import', str(preload)])
            result = subprocess.check_output(command[:3] + ['--eval', 'console.log(globalThis.IS_REACT_ACT_ENVIRONMENT)'], text=True)
            self.assertEqual(result.strip(), 'true')
        self.assertEqual(bench.suite_identity()['files'][str(preload.relative_to(ROOT))], bench.sha(preload.read_bytes()))
