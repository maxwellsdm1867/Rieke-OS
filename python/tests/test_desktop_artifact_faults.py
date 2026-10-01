"""Real candidate verifier probes must isolate each packaging fault's cause."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('desktop_artifact_e2e', ROOT / 'tools/desktop_artifact_e2e.py')
artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact)


class ArtifactCompatibilityFaultTests(unittest.TestCase):
    def manifest(self, version):
        return {'format': 'rieke-desktop-runtime', 'version': 1,
                'application_version': version, 'source_dirty': False,
                'source_commit': 'a' * 40, 'parser_commit': 'b' * 40,
                'platform': 'darwin', 'architecture': 'arm64',
                'database_compatibility': 1, 'mysql_version': '8.4.2',
                'workspace_formats': [1, 2], 'resources': {'fixture': {'size': 1}}}

    def test_newer_control_and_each_intended_rejection_on_current_and_future_releases(self):
        for version, newer in [('0.1.4', '0.1.5'), ('2.10.99', '2.10.100')]:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temporary:
                manifest = Path(temporary) / 'manifest.json'
                manifest.write_text(json.dumps(self.manifest(version)))
                cases = artifact.compatibility_fault_checks(manifest)
                self.assertEqual(len(cases), 5)
                self.assertTrue(all(case['rejected'] and case['compatible_control_version'] == newer for case in cases))
                by_name = {case['case']: case['reason'] for case in cases}
                self.assertEqual(by_name['dirty candidate provenance'], 'Update has no clean source provenance.')
                self.assertEqual(by_name['incompatible database'], 'Update requires an unqualified database or workspace migration.')
                self.assertEqual(by_name['incompatible workspace'], 'Update requires an unqualified database or workspace migration.')
                self.assertEqual(by_name['wrong native architecture'], 'Unsupported update platform.')

    def test_blanket_version_rejection_cannot_generate_fault_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'desktop').mkdir()
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps(self.manifest('0.1.4')))
            (root / 'desktop/updater-validation.cjs').write_text(
                "exports.compatibleCandidate=()=>{throw new Error('Update version is mismatched or older than the installed app.');};")
            with patch.object(artifact, 'ROOT', root), self.assertRaises(subprocess.CalledProcessError):
                artifact.compatibility_fault_checks(manifest)

    def test_wrong_architecture_rejection_reason_cannot_generate_fault_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'desktop').mkdir()
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps(self.manifest('0.1.4')))
            verifier = str(ROOT / 'desktop/updater-validation.cjs')
            (root / 'desktop/updater-validation.cjs').write_text(
                'const real=require(' + json.dumps(verifier) + ');exports.compatibleCandidate=(candidate,current,version)=>{'
                "if(candidate.architecture==='x64')throw new Error('Update version is mismatched or older than the installed app.');"
                'return real.compatibleCandidate(candidate,current,version);};')
            with patch.object(artifact, 'ROOT', root), self.assertRaises(subprocess.CalledProcessError):
                artifact.compatibility_fault_checks(manifest)
