"""Resolver policy and post-relocation native-import qualification boundaries."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import desktop_build_runtime as build

class ScientificWheelTests(unittest.TestCase):
    def test_resolver_receives_hash_required_direct_wheel_with_all_existing_locks(self):
        interpreter=Path('/owned/runtime/python/bin/python3.11')
        with patch.object(build, 'run') as run:
            build.install_runtime_dependencies(interpreter, {'PYTHONDONTWRITEBYTECODE':'1'})
        command=run.call_args.args[0]
        self.assertIn('--require-hashes', command)
        self.assertIn(ROOT/'python/workspace-runtime.lock', command)
        self.assertIn(ROOT/'desktop/requirements.lock', command)
        self.assertIn(ROOT/'desktop/scientific-wheels.lock', command)
        policy=(ROOT/'desktop/scientific-wheels.lock').read_text()
        self.assertIn('scipy-1.15.0-cp311-cp311-macosx_12_0_arm64.whl', policy)
        self.assertIn('--hash=sha256:82bff2eb01ccf7cea8b6ee5274c2dbeadfdac97919da308ee6d8e5bcbe846443', policy)

    def test_native_preflight_uses_owned_interpreter_and_real_native_modules(self):
        interpreter=Path('/owned/runtime/python/bin/python3.11')
        with patch.object(build.subprocess, 'check_output', return_value='{"native_imports":"passed"}') as call:
            self.assertEqual(build.scientific_preflight(interpreter), {'native_imports':'passed'})
        command=call.call_args.args[0]
        self.assertEqual(command[:4], [interpreter, '-I', '-B', '-c'])
        for module in ('scipy.signal', 'scipy.stats', 'scipy.sparse.linalg', 'scipy.ndimage', 'scipy.io'):
            self.assertIn(module, command[4])
        self.assertIn('macosx_12_0_arm64', command[4])

    def test_native_import_error_is_not_a_pass(self):
        with patch.object(build.subprocess, 'check_output', side_effect=build.subprocess.CalledProcessError(1,['owned-python'])):
            with self.assertRaises(build.subprocess.CalledProcessError):
                build.scientific_preflight(Path('/owned/runtime/python/bin/python3.11'))
