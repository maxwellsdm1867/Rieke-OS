import importlib.util
from pathlib import Path
import unittest
import json
import subprocess
import tempfile
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))

spec = importlib.util.spec_from_file_location('desktop_release', Path(__file__).resolve().parents[2] / 'tools/desktop_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class DesktopReleaseTests(unittest.TestCase):
    def evidence(self):
        return {'format': 'rieke-desktop-qualification', 'version': 1, 'application_version': '1.0.0',
                'platform': 'darwin', 'architecture': 'arm64', 'source_commit': 'a' * 40,
                'artifacts': {'app.zip': {'sha256': 'b' * 64, 'size': 10}},
                'requirements': {key: {'passed': True, 'receipts': [{'description': 'Reviewed real-artifact run', 'sha256': 'c' * 64}]} for key in release.REQUIREMENTS}}

    def test_incomplete_qualification_and_different_bytes_rejected(self):
        evidence = self.evidence()
        release.validate_evidence(evidence, evidence['artifacts'], '1.0.0')
        with self.assertRaises(ValueError):
            release.validate_evidence(evidence, {}, '1.0.0')
        for requirement in release.REQUIREMENTS:
            evidence = self.evidence()
            evidence['requirements'][requirement]['passed'] = False
            with self.assertRaises(ValueError):
                release.validate_evidence(evidence, evidence['artifacts'], '1.0.0')

    def test_mock_counts_and_unsigned_receipts_cannot_replace_requirement_evidence(self):
        evidence = self.evidence()
        evidence['requirements'] = {'tests_passed': 500}
        with self.assertRaises(ValueError):
            release.validate_evidence(evidence, evidence['artifacts'], '1.0.0')

    def test_stable_version_and_canonical_repository_required(self):
        self.assertEqual(release.REPOSITORY, 'maxwellsdm1867/Rieke-OS')
        for value in ('1.0.0-beta', 'v1.0.0', '01.0.0', None):
            with self.assertRaises(ValueError):
                release.version(value)
        with self.assertRaises(ValueError):
            release.baseline('v1.0.0', 'other/repo')

    def test_testing_baseline_requires_actual_canonical_origin_clean_exact_tag_and_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL)
            for directory in ('desktop', 'workspace-app', 'python'):
                (root / directory).mkdir()
            metadata = {'version': '0.1.3', 'repository': release.REPOSITORY, 'channel': 'stable',
                        'workspace_formats': [1], 'database_compatibility': 1}
            (root / 'rieke-release.json').write_text(json.dumps(metadata))
            for directory in ('desktop', 'workspace-app'):
                (root / directory / 'package.json').write_text('{"version":"0.1.3"}')
            (root / 'desktop/distribution.json').write_text(json.dumps(
                {'format':'rieke-desktop-distribution','version':1,'channel':'unsigned-testing',
                 'repository':release.REPOSITORY}))
            (root / 'desktop/application-profile.json').write_text(json.dumps(
                {'format':'rieke-application-profile','version':1,'python_modules':['core.py'],
                 'source_exclusions':[{'pattern':'*.m'}]}))
            (root / 'python/core.py').write_text('# data application')
            git('init', '-q');git('remote', 'add', 'origin', 'https://github.com/'+release.REPOSITORY+'.git')
            git('add', '.')
            git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Reviewed fixture')
            git('tag','desktop-test-v0.1.3');git('tag','v0.1.3')
            with patch.object(release, 'ROOT', root):
                result = release.testing_baseline('desktop-test-v0.1.3', release.REPOSITORY)
                self.assertEqual(result['source_commit'], git('rev-parse','HEAD').decode().strip())
                self.assertEqual(result['distribution_channel'], 'unsigned-testing')
                self.assertEqual(result['repository'], 'maxwellsdm1867/Rieke-OS')
                self.assertEqual(result['canonical_repository'], 'maxwellsdm1867/Rieke-OS')
                self.assertFalse(result['production_ready'])
                self.assertNotIn('distribution_channel', release.baseline('v0.1.3', release.REPOSITORY))
                legacy = 'maxwellsdm1867/disco'
                git('remote','set-url','origin','https://github.com/'+legacy+'.git')
                bridge = release.testing_baseline('desktop-test-v0.1.3', legacy)
                self.assertEqual(bridge['repository'],legacy)
                self.assertEqual(bridge['canonical_repository'],release.REPOSITORY)
                with self.assertRaisesRegex(ValueError,'Git origin'):
                    release.testing_baseline('desktop-test-v0.1.3', release.REPOSITORY)
                git('remote','set-url','origin','https://github.com/'+release.REPOSITORY+'.git')
                with self.assertRaisesRegex(ValueError,'stable version tag'):
                    release.baseline('desktop-test-v0.1.3', release.REPOSITORY)
                git('remote','set-url','origin','https://github.com/other/EpicTreeGUI.git')
                with self.assertRaisesRegex(ValueError,'Git origin'):
                    release.testing_baseline('desktop-test-v0.1.3', release.REPOSITORY)
                git('remote','set-url','origin','https://github.com/'+release.REPOSITORY+'.git')
                (root / 'unreviewed.txt').write_text('dirty')
                with self.assertRaisesRegex(ValueError,'clean reviewed'):
                    release.testing_baseline('desktop-test-v0.1.3', release.REPOSITORY)
                git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Later source')
                with self.assertRaisesRegex(ValueError,'exact reviewed tag'):
                    release.testing_baseline('desktop-test-v0.1.3', release.REPOSITORY)


if __name__ == '__main__':
    unittest.main()
